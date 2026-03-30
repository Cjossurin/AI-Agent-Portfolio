"""
api/email_routes.py
===================
Email Intelligence dashboard — connects EmailSupportAgent and EmailMarketingAgent
to the client portal.

Routes (HTML)
-------------
GET  /email/dashboard             — Unified email hub (support + marketing tabs)
GET  /email/campaigns             — Email marketing campaigns tab
GET  /email/support               — Email support inbox tab

Routes (JSON API)
-----------------
POST /api/email/plan-campaign     — Run EmailMarketingAgent.plan_campaign()
POST /api/email/process-inbox     — Run EmailSupportAgent.fetch_inbox_gmail() + process
GET  /api/email/campaign-stats    — Campaign stats from EmailMarketingAgent
GET  /api/email/support-stats     — Support conversation stats
"""

import os
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from database.db import get_db
from utils.shared_layout import build_page, get_user_context
from utils.plan_limits import check_limit, increment_usage

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

router = APIRouter(tags=["Email"])

EMAIL_STORAGE = Path("storage") / "email_campaigns"


# ──────────────────────────────────────────────────────────────────────────────
# JSON API — Email Marketing
# ──────────────────────────────────────────────────────────────────────────────

@router.post("/api/email/plan-campaign")
async def api_plan_campaign(request: Request):
    """Plan an email campaign using EmailMarketingAgent."""
    db = next(get_db())
    try:
        user, profile = get_user_context(request, db)
        if not user:
            return JSONResponse({"error": "Unauthorized"}, status_code=401)
        if not profile:
            return JSONResponse({"error": "No profile found"}, status_code=400)

        body = {}
        try:
            body = await request.json()
        except Exception:
            pass

        # ── Plan gate ──────────────────────────────────────────────────────────
        allowed, msg = check_limit(profile, "campaigns_sent")
        if not allowed:
            return JSONResponse({"error": msg, "upgrade_url": "/billing"}, status_code=402)
        increment_usage(profile, "campaigns_sent", db)

        from agents.email_marketing_agent import (
            EmailMarketingAgent, CampaignType, CampaignGoal, AudienceSegment
        )

        # Map string inputs to enums (fall back to defaults)
        def _ct(v):
            try: return CampaignType(v)
            except Exception: return CampaignType.NEWSLETTER

        def _cg(v):
            try: return CampaignGoal(v)
            except Exception: return CampaignGoal.ENGAGEMENT

        def _seg(v):
            try: return AudienceSegment(v)
            except Exception: return AudienceSegment.ALL_SUBSCRIBERS

        agent = EmailMarketingAgent(client_id=profile.client_id)
        agent.set_tier(getattr(profile, "plan_tier", "pro") or "pro")

        # Offload sync SDK call to thread pool so we don't block the event loop
        import asyncio
        from utils.agent_executor import AGENT_POOL
        loop = asyncio.get_running_loop()
        rec = await loop.run_in_executor(
            AGENT_POOL,
            lambda: agent.plan_campaign(
                campaign_type=_ct(body.get("campaign_type", "newsletter")),
                campaign_goal=_cg(body.get("campaign_goal", "engagement")),
                target_segment=_seg(body.get("target_segment", "all_subscribers")),
                content_brief=body.get("content_brief", f"Campaign for {profile.business_name}"),
                client_knowledge=body.get("client_knowledge", ""),
                industry=body.get("industry", profile.niche or "default"),
            )
        )

        # Persist to disk
        save_dir = EMAIL_STORAGE / "marketing" / profile.client_id
        save_dir.mkdir(parents=True, exist_ok=True)
        plan_id = f"campaign_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        rec_dict = {
            "plan_id": plan_id,
            "created_at": datetime.now().isoformat(),
            "client_id": profile.client_id,
            "campaign_type": body.get("campaign_type", "newsletter"),
            "campaign_goal": body.get("campaign_goal", "engagement"),
            "subject_lines": [s if isinstance(s, str) else str(s) for s in (rec.subject_lines or [])],
            "recommended_send_times": [t if isinstance(t, str) else str(t) for t in (rec.recommended_send_times or [])],
            "segmentation_recommendations": rec.segmentation_recommendations or [],
            "content_recommendations": rec.content_recommendations or [],
            "estimated_open_rate": rec.estimated_open_rate,
            "estimated_click_rate": rec.estimated_click_rate,
            "ab_test_suggestions": rec.ab_test_suggestions or [],
            "deliverability_tips": rec.deliverability_tips or [],
        }
        (save_dir / f"{plan_id}.json").write_text(
            json.dumps(rec_dict, indent=2, ensure_ascii=False), encoding="utf-8"
        )

        return JSONResponse({"ok": True, "plan_id": plan_id, "plan": rec_dict})

    except Exception as e:
        import traceback; traceback.print_exc()
        return JSONResponse({"error": str(e)}, status_code=500)
    finally:
        db.close()


@router.get("/api/email/campaign-stats")
async def api_campaign_stats(request: Request):
    """Return saved campaign plans for current client."""
    db = next(get_db())
    try:
        user, profile = get_user_context(request, db)
        if not user:
            return JSONResponse({"error": "Unauthorized"}, status_code=401)
        if not profile:
            return JSONResponse({"plans": []})

        save_dir = EMAIL_STORAGE / "marketing" / profile.client_id
        plans = []
        if save_dir.exists():
            for f in sorted(save_dir.glob("*.json"), reverse=True)[:20]:
                try:
                    d = json.loads(f.read_text(encoding="utf-8"))
                    plans.append({
                        "plan_id": d.get("plan_id"),
                        "created_at": d.get("created_at","")[:10],
                        "campaign_type": d.get("campaign_type",""),
                        "campaign_goal": d.get("campaign_goal",""),
                        "est_open_rate": d.get("estimated_open_rate"),
                        "est_click_rate": d.get("estimated_click_rate"),
                        "subject_lines_count": len(d.get("subject_lines",[])),
                    })
                except Exception:
                    pass
        return JSONResponse({"plans": plans})
    finally:
        db.close()


# ──────────────────────────────────────────────────────────────────────────────
# JSON API — Email Support
# ──────────────────────────────────────────────────────────────────────────────

@router.post("/api/email/process-inbox")
async def api_process_inbox(request: Request, background_tasks: BackgroundTasks):
    """Fetch Gmail inbox and process queued support emails (background task)."""
    db = next(get_db())
    try:
        user, profile = get_user_context(request, db)
        if not user:
            return JSONResponse({"error": "Unauthorized"}, status_code=401)
        if not profile:
            return JSONResponse({"error": "No profile found"}, status_code=400)

        body = {}
        try:
            body = await request.json()
        except Exception:
            pass

        max_emails = int(body.get("max_emails", 10))
        background_tasks.add_task(_bg_process_inbox, profile.client_id, max_emails)

        return JSONResponse({
            "ok": True,
            "status": "processing",
            "message": f"Fetching up to {max_emails} emails from Gmail inbox. Check support stats shortly.",
        })
    finally:
        db.close()


def _bg_process_inbox(client_id: str, max_emails: int):
    """Sync wrapper — FastAPI runs sync BackgroundTasks in a thread pool."""
    from utils.agent_executor import run_agent_in_background
    run_agent_in_background(_bg_process_inbox_async(client_id, max_emails))


async def _bg_process_inbox_async(client_id: str, max_emails: int):
    try:
        from agents.email_support_agent import EmailSupportAgent, EmailMessage
        from utils.notification_manager import NotificationManager

        agent = EmailSupportAgent(client_id=client_id)
        notifier = NotificationManager(client_id=client_id)

        # fetch_inbox dispatches to Gmail API or IMAP based on stored credentials
        emails = await agent.fetch_inbox(client_id=client_id, max_results=max_emails)

        processed = 0
        escalated = 0
        for raw in emails:
            try:
                msg = EmailMessage(
                    message_id=raw.get("id",""),
                    sender_email=raw.get("from",""),
                    sender_name=raw.get("from_name",""),
                    subject=raw.get("subject",""),
                    body=raw.get("body",""),
                    received_at=raw.get("received_at", datetime.now().isoformat()),
                    thread_id=raw.get("thread_id"),
                )
                reply = await agent.process_incoming_email(msg)
                processed += 1
                if reply.should_escalate:
                    escalated += 1
                    await notifier.send_notification(
                        notification_type="message_received",
                        title=f"Email Escalation: {msg.subject[:60]}",
                        message=f"From {msg.sender_email} — needs human review",
                        priority="high",
                        metadata={
                            "action_url": "/email/support",
                            "action_label": "Review Email",
                            "action_type": "internal_link",
                            "sender": msg.sender_email,
                        }
                    )
            except Exception as exc:
                print(f"Email processing error: {exc}")
                continue

        # Save stats
        stats_dir = EMAIL_STORAGE / "support" / client_id
        stats_dir.mkdir(parents=True, exist_ok=True)
        stats = {
            "last_run": datetime.now().isoformat(),
            "processed": processed,
            "escalated": escalated,
        }
        (stats_dir / "stats.json").write_text(json.dumps(stats, indent=2), encoding="utf-8")
        print(f"✅ Email support: processed={processed}, escalated={escalated}")

    except Exception as exc:
        print(f"❌ _bg_process_inbox failed: {exc}")
        import traceback; traceback.print_exc()


@router.get("/api/email/support-stats")
async def api_support_stats(request: Request):
    db = next(get_db())
    try:
        user, profile = get_user_context(request, db)
        if not user:
            return JSONResponse({"error": "Unauthorized"}, status_code=401)
        if not profile:
            return JSONResponse({"stats": {}})

        stats_path = EMAIL_STORAGE / "support" / profile.client_id / "stats.json"
        if stats_path.exists():
            return JSONResponse({"stats": json.loads(stats_path.read_text(encoding="utf-8"))})
        return JSONResponse({"stats": {"last_run": None, "processed": 0, "escalated": 0}})
    finally:
        db.close()


# ──────────────────────────────────────────────────────────────────────────────
# HTML Pages
# ──────────────────────────────────────────────────────────────────────────────

@router.get("/email/dashboard", response_class=HTMLResponse)
async def email_dashboard(request: Request):
    db = next(get_db())
    try:
        user, profile = get_user_context(request, db)
        if not user:
            return RedirectResponse("/account/login", status_code=303)
        if not profile:
            return RedirectResponse("/onboarding", status_code=303)

        # Campaign enums for dropdowns
        try:
            from agents.email_marketing_agent import CampaignType, CampaignGoal, AudienceSegment
            ct_opts = "".join(f'<option value="{e.value}">{e.value.replace("_"," ").title()}</option>' for e in CampaignType)
            cg_opts = "".join(f'<option value="{e.value}">{e.value.replace("_"," ").title()}</option>' for e in CampaignGoal)
            seg_opts = "".join(f'<option value="{e.value}">{e.value.replace("_"," ").title()}</option>' for e in AudienceSegment)
        except Exception:
            ct_opts = '<option value="newsletter">Newsletter</option><option value="promotional">Promotional</option>'
            cg_opts = '<option value="engagement">Engagement</option><option value="sales">Sales</option>'
            seg_opts = '<option value="all_subscribers">All Subscribers</option>'

        _body = f"""
  <div style="max-width:960px;margin:0 auto">

    <!-- Header -->
    <div style="margin-bottom:24px">
      <h1 style="font-size:1.5rem;font-weight:800;margin-bottom:6px">&#128140; Email Intelligence</h1>
      <p style="font-size:.87rem;color:#606770;max-width:560px">AI-powered email support and campaign planning, both fully driven by your client knowledge base.</p>
    </div>

    <!-- Tabs -->
    <div style="display:flex;gap:0;border-bottom:2px solid #e9ebee;margin-bottom:28px">
      <button onclick="showTab('marketing')" id="tab-marketing"
        style="padding:10px 22px;background:none;border:none;border-bottom:3px solid #5c6ac4;font-size:.88rem;font-weight:700;color:#5c6ac4;cursor:pointer;margin-bottom:-2px">
        &#128231; Campaign Planner
      </button>
      <button onclick="showTab('support')" id="tab-support"
        style="padding:10px 22px;background:none;border:none;border-bottom:3px solid transparent;font-size:.88rem;font-weight:600;color:#606770;cursor:pointer;margin-bottom:-2px">
        &#128232; Email Support
      </button>
    </div>

    <!-- ── MARKETING TAB ── -->
    <div id="pane-marketing">
      <div style="background:#fff;border-radius:14px;border:1px solid #e9ebee;padding:26px;margin-bottom:24px">
        <h2 style="font-size:1rem;font-weight:700;margin-bottom:16px">&#128202; Plan a New Campaign</h2>
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:14px">
          <div>
            <label style="font-size:.78rem;font-weight:600;color:#444;display:block;margin-bottom:5px">Campaign Type</label>
            <select id="f-ct" style="width:100%;padding:9px 12px;border:1px solid #dde0e4;border-radius:8px;font-size:.84rem;background:#fff">{ct_opts}</select>
          </div>
          <div>
            <label style="font-size:.78rem;font-weight:600;color:#444;display:block;margin-bottom:5px">Campaign Goal</label>
            <select id="f-cg" style="width:100%;padding:9px 12px;border:1px solid #dde0e4;border-radius:8px;font-size:.84rem;background:#fff">{cg_opts}</select>
          </div>
          <div>
            <label style="font-size:.78rem;font-weight:600;color:#444;display:block;margin-bottom:5px">Audience Segment</label>
            <select id="f-seg" style="width:100%;padding:9px 12px;border:1px solid #dde0e4;border-radius:8px;font-size:.84rem;background:#fff">{seg_opts}</select>
          </div>
          <input id="f-ind" type="hidden" value="{profile.niche or ''}" />
          <div style="grid-column:1/-1">
            <label style="font-size:.78rem;font-weight:600;color:#444;display:block;margin-bottom:5px">Content Brief *</label>
            <textarea id="f-brief" rows="3" placeholder="Describe the campaign: what's the offer, hook, or message?"
              style="width:100%;padding:9px 12px;border:1px solid #dde0e4;border-radius:8px;font-size:.84rem;resize:vertical"></textarea>
          </div>
        </div>
        <div style="display:flex;align-items:center;gap:12px;margin-top:16px">
          <button onclick="planCampaign()"
            style="background:linear-gradient(135deg,#5c6ac4,#764ba2);color:#fff;border:none;border-radius:10px;padding:11px 22px;font-size:.88rem;font-weight:700;cursor:pointer">
            &#129504; Generate Campaign Plan
          </button>
          <span id="m-status" style="font-size:.83rem;color:#606770"></span>
        </div>
      </div>

      <!-- Plans list -->
      <div id="plans-container">
        <div style="background:#fff;border-radius:14px;border:1px solid #e9ebee;padding:26px">
          <h2 style="font-size:.95rem;font-weight:700;margin-bottom:16px">&#128196; Past Campaign Plans</h2>
          <div id="plans-list"><p style="color:#90949c;font-size:.84rem">Loading...</p></div>
        </div>
      </div>
    </div>

    <!-- ── SUPPORT TAB ── -->
    <div id="pane-support" style="display:none">
      <div style="background:#fff;border-radius:14px;border:1px solid #e9ebee;padding:26px;margin-bottom:24px">
        <div style="display:flex;align-items:flex-start;justify-content:space-between;flex-wrap:wrap;gap:14px">
          <div>
            <h2 style="font-size:1rem;font-weight:700;margin-bottom:6px">&#128231; Gmail Support Inbox</h2>
            <p style="font-size:.83rem;color:#606770;max-width:480px;line-height:1.5">
              Alita AI fetches your Gmail inbox, categorizes emails, auto-drafts replies, and escalates leads + urgent requests.
              Requires Gmail OAuth setup in Settings.
            </p>
          </div>
          <button onclick="processInbox()"
            style="background:#16a34a;color:#fff;border:none;border-radius:10px;padding:11px 22px;font-size:.88rem;font-weight:700;cursor:pointer;white-space:nowrap;flex-shrink:0">
            &#128279; Fetch &amp; Process Inbox
          </button>
        </div>
        <div id="support-stats" style="margin-top:20px"></div>
        <div id="s-status" style="margin-top:12px;font-size:.84rem;color:#606770"></div>
      </div>

      <!-- Gmail setup instructions -->
      <div style="background:#fff8e1;border:1px solid #ffe082;border-radius:12px;padding:20px 24px">
        <p style="font-weight:700;color:#b45309;font-size:.87rem;margin-bottom:8px">&#9432; Gmail OAuth Setup Required</p>
        <p style="font-size:.82rem;color:#92400e;line-height:1.5">
          To enable real inbox processing, set <code>GMAIL_REFRESH_TOKEN_{profile.client_id.upper()}</code> in your <code>.env</code> file.
          Run <code>python setup_gmail_oauth.py</code> to generate the refresh token via the Gmail OAuth flow.
          Once set, Alita AI can read + reply to emails from your Gmail account.
        </p>
      </div>
    </div>

  </div>
"""
        return HTMLResponse(build_page(
            title="Email Intelligence",
            active_nav="email",
            body_content=_body,
            extra_js="""
function showTab(tab) {
  document.getElementById('pane-marketing').style.display = tab==='marketing' ? '' : 'none';
  document.getElementById('pane-support').style.display = tab==='support' ? '' : 'none';
  document.getElementById('tab-marketing').style.cssText = tab==='marketing'
    ? 'padding:10px 22px;background:none;border:none;border-bottom:3px solid #5c6ac4;font-size:.88rem;font-weight:700;color:#5c6ac4;cursor:pointer;margin-bottom:-2px'
    : 'padding:10px 22px;background:none;border:none;border-bottom:3px solid transparent;font-size:.88rem;font-weight:600;color:#606770;cursor:pointer;margin-bottom:-2px';
  document.getElementById('tab-support').style.cssText = tab==='support'
    ? 'padding:10px 22px;background:none;border:none;border-bottom:3px solid #5c6ac4;font-size:.88rem;font-weight:700;color:#5c6ac4;cursor:pointer;margin-bottom:-2px'
    : 'padding:10px 22px;background:none;border:none;border-bottom:3px solid transparent;font-size:.88rem;font-weight:600;color:#606770;cursor:pointer;margin-bottom:-2px';
}

async function planCampaign() {
  const status = document.getElementById('m-status');
  status.textContent = '⏳ Generating campaign plan...';
  try {
    const r = await fetch('/api/email/plan-campaign', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({
        campaign_type: document.getElementById('f-ct').value,
        campaign_goal: document.getElementById('f-cg').value,
        target_segment: document.getElementById('f-seg').value,
        industry: document.getElementById('f-ind').value,
        content_brief: document.getElementById('f-brief').value,
      })
    });
    const data = await r.json();
    if (data.ok) {
      status.textContent = '✓ Plan created: ' + data.plan_id;
      loadPlans();
    } else {
      status.textContent = '✗ Error: ' + (data.error || 'Unknown');
    }
  } catch(e) { status.textContent = '✗ ' + e.message; }
}

async function loadPlans() {
  try {
    const r = await fetch('/api/email/campaign-stats');
    const data = await r.json();
    const el = document.getElementById('plans-list');
    if (!data.plans || data.plans.length === 0) {
      el.innerHTML = '<p style="color:#90949c;font-size:.84rem">No plans yet. Generate your first one above.</p>';
      return;
    }
    let html = data.plans.map(p => `
      <div style="display:flex;align-items:center;justify-content:space-between;padding:12px 0;border-bottom:1px solid #f0f2f5;flex-wrap:wrap;gap:8px">
        <div>
          <span style="font-size:.82rem;font-weight:700">${p.campaign_type} &rarr; ${p.campaign_goal}</span>
          <span style="font-size:.76rem;color:#90949c;margin-left:10px">${p.created_at}</span>
        </div>
        <div style="display:flex;gap:10px;flex-wrap:wrap">
          <span style="font-size:.76rem;background:#e8f5e9;color:#2e7d32;padding:2px 9px;border-radius:99px;font-weight:700">~${p.est_open_rate || '?'}% open rate</span>
          <span style="font-size:.76rem;background:#e8eaf6;color:#3949ab;padding:2px 9px;border-radius:99px;font-weight:700">${p.subject_lines_count} subject lines</span>
        </div>
      </div>`).join('');
    el.innerHTML = html;
  } catch(e) { document.getElementById('plans-list').innerHTML = '<p style="color:#c62828">Error loading plans</p>'; }
}

async function processInbox() {
  const status = document.getElementById('s-status');
  status.textContent = '⏳ Fetching & processing inbox...';
  try {
    const r = await fetch('/api/email/process-inbox', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({max_emails: 10})});
    const data = await r.json();
    status.textContent = data.ok ? '✓ ' + data.message : '✗ ' + data.error;
    setTimeout(loadSupportStats, 5000);
  } catch(e) { status.textContent = '✗ ' + e.message; }
}

async function loadSupportStats() {
  try {
    const r = await fetch('/api/email/support-stats');
    const data = await r.json();
    const s = data.stats || {};
    const el = document.getElementById('support-stats');
    if (!s.last_run) { el.innerHTML = ''; return; }
    el.innerHTML = `<div style="display:flex;gap:16px;flex-wrap:wrap">
      <div style="background:#f0fdf4;border:1px solid #bbf7d0;border-radius:10px;padding:12px 18px;text-align:center">
        <div style="font-size:1.4rem;font-weight:800;color:#16a34a">${s.processed||0}</div>
        <div style="font-size:.75rem;color:#15803d">Processed</div>
      </div>
      <div style="background:#fef3f2;border:1px solid #fecaca;border-radius:10px;padding:12px 18px;text-align:center">
        <div style="font-size:1.4rem;font-weight:800;color:#dc2626">${s.escalated||0}</div>
        <div style="font-size:.75rem;color:#b91c1c">Escalated</div>
      </div>
      <div style="background:#eff6ff;border:1px solid #bfdbfe;border-radius:10px;padding:12px 18px;text-align:center;flex:1">
        <div style="font-size:.8rem;color:#1d4ed8;font-weight:600">Last run</div>
        <div style="font-size:.78rem;color:#1e40af">${s.last_run ? s.last_run.substring(0,16).replace('T',' ') : '—'}</div>
      </div>
    </div>`;
  } catch(e) {}
}

document.addEventListener('DOMContentLoaded', function() {
  loadPlans();
  loadSupportStats();
});
""",
            user_name=user.full_name,
            business_name=profile.business_name,
        ))
    finally:
        db.close()
