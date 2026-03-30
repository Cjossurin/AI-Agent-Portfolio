"""
api/admin_routes.py
Admin panel for reviewing pending deep research requests before they run.
Access: /admin (requires is_admin=True on User record)
"""
import sys
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import asyncio
import json
import os
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from sqlalchemy.orm import Session

from api.auth_routes import require_admin
from database.db import get_db
from database.models import (
    ClientProfile, DeepResearchRequest, User,
    DeepResearchStatus, OnboardingStatus,
)

router = APIRouter(prefix="/admin", tags=["admin"])


def _require_admin_or_secret(request: Request, db: Session = Depends(get_db)):
    """FastAPI dependency: accepts admin session auth OR matching GROWTH_TEST_SECRET.

    Allows PowerShell testing without a browser session:
        GET /admin/trigger-growth-campaign?secret=<GROWTH_TEST_SECRET>&client_id=default_client
    Returns the admin User object on session auth, or None on secret auth.
    """
    secret = os.getenv("GROWTH_TEST_SECRET", "")
    if secret and request.query_params.get("secret") == secret:
        return None  # token-auth OK — no user object needed
    return require_admin(request, db)

# ─────────────────────────────────────────────────────
# Shared CSS (reuse onboarding style)
# ─────────────────────────────────────────────────────

ADMIN_CSS = """
<style>
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #0f0f14; color: white; }
.topbar { background: rgba(99,102,241,0.15); border-bottom: 1px solid rgba(99,102,241,0.3); padding: 14px 32px; display: flex; justify-content: space-between; align-items: center; }
.topbar .logo { font-size: 1.2rem; font-weight: 800; background: linear-gradient(135deg, #6366f1, #a78bfa); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
.topbar .links a { color: rgba(255,255,255,0.5); text-decoration: none; margin-left: 20px; font-size: 0.85rem; }
.topbar .links a:hover { color: white; }
.content { max-width: 1100px; margin: 0 auto; padding: 32px 24px; }
h2 { font-size: 1.6rem; font-weight: 700; margin-bottom: 6px; }
.sub { color: rgba(255,255,255,0.4); font-size: 0.9rem; margin-bottom: 32px; }
.table-wrap { background: rgba(255,255,255,0.04); border: 1px solid rgba(255,255,255,0.08); border-radius: 16px; overflow: hidden; }
table { width: 100%; border-collapse: collapse; }
th { background: rgba(255,255,255,0.06); padding: 14px 20px; text-align: left; font-size: 0.8rem; font-weight: 700; color: rgba(255,255,255,0.5); text-transform: uppercase; letter-spacing: 0.05em; }
td { padding: 16px 20px; border-top: 1px solid rgba(255,255,255,0.06); font-size: 0.88rem; vertical-align: top; }
tr:hover td { background: rgba(255,255,255,0.03); }
.badge { display: inline-block; padding: 4px 12px; border-radius: 20px; font-size: 0.75rem; font-weight: 700; }
.badge-pending  { background: rgba(251,191,36,0.15); color: #fbbf24; }
.badge-approved { background: rgba(52,211,153,0.15); color: #34d399; }
.badge-rejected { background: rgba(239,68,68,0.15); color: #f87171; }
.badge-running  { background: rgba(99,102,241,0.15); color: #a78bfa; }
.badge-complete { background: rgba(52,211,153,0.15); color: #34d399; }
.badge-failed   { background: rgba(239,68,68,0.15); color: #f87171; }
.btn { display: inline-block; padding: 8px 18px; border-radius: 8px; font-size: 0.82rem; font-weight: 700; cursor: pointer; border: none; text-decoration: none; }
.btn-approve { background: linear-gradient(135deg, #059669, #34d399); color: white; }
.btn-reject  { background: rgba(239,68,68,0.2); color: #f87171; border: 1px solid rgba(239,68,68,0.3); }
.btn-view    { background: rgba(99,102,241,0.15); color: #a78bfa; border: 1px solid rgba(99,102,241,0.2); }
.card { background: rgba(255,255,255,0.04); border: 1px solid rgba(255,255,255,0.08); border-radius: 16px; padding: 28px; margin-bottom: 24px; }
.card h3 { font-size: 1.1rem; font-weight: 700; margin-bottom: 12px; }
.field-label { font-size: 0.75rem; font-weight: 700; color: rgba(255,255,255,0.35); text-transform: uppercase; letter-spacing: 0.05em; margin-top: 16px; margin-bottom: 4px; }
.field-val { font-size: 0.9rem; color: rgba(255,255,255,0.8); line-height: 1.5; white-space: pre-wrap; }
.query-box { background: rgba(99,102,241,0.08); border: 1px solid rgba(99,102,241,0.2); border-radius: 10px; padding: 16px; font-size: 0.88rem; line-height: 1.6; color: rgba(255,255,255,0.8); margin-top: 8px; }
form input[type=text], form textarea { width: 100%; padding: 10px 14px; background: rgba(255,255,255,0.06); border: 1px solid rgba(255,255,255,0.12); border-radius: 8px; color: white; font-size: 0.88rem; outline: none; margin-top: 6px; }
form textarea { min-height: 80px; resize: vertical; }
.action-row { display: flex; gap: 12px; margin-top: 20px; }
.empty-state { text-align: center; padding: 48px; color: rgba(255,255,255,0.3); }
.empty-state .icon { font-size: 3rem; margin-bottom: 12px; }
.stat-row { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 16px; margin-bottom: 32px; }
.stat { background: rgba(255,255,255,0.04); border: 1px solid rgba(255,255,255,0.08); border-radius: 12px; padding: 20px; }
.stat .num { font-size: 2rem; font-weight: 800; background: linear-gradient(135deg, #6366f1, #a78bfa); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
.stat .lbl { font-size: 0.8rem; color: rgba(255,255,255,0.4); margin-top: 4px; }
</style>"""


def _admin_page(title: str, body: str, current_admin_email: str = "") -> str:
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title} — Alita Admin</title>
{ADMIN_CSS}
</head>
<body>
<div class="topbar">
  <div class="logo">Alita AI — Admin</div>
  <div class="links">
    <a href="/admin">Dashboard</a>
    <a href="/admin/research">Research Queue</a>
    <a href="/admin/clients">Clients</a>
    <a href="/account/logout">Sign out ({current_admin_email})</a>
  </div>
</div>
<div class="content">{body}</div>
</body>
</html>"""


# ─────────────────────────────────────────────────────
# Admin dashboard
# ─────────────────────────────────────────────────────

@router.get("", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse)
async def admin_home(
    request: Request,
    db: Session = Depends(get_db),
    admin=Depends(require_admin),
):
    total_clients  = db.query(User).filter(User.is_admin == False).count()
    onboarded      = db.query(ClientProfile).filter(ClientProfile.rag_ready == True).count()
    pending_review = db.query(DeepResearchRequest).filter(
        DeepResearchRequest.status == DeepResearchStatus.pending
    ).count()
    total_research = db.query(DeepResearchRequest).count()

    body = f"""
    <h2>System Overview</h2>
    <p class="sub">Alita AI — Admin Panel</p>
    <div class="stat-row">
      <div class="stat"><div class="num">{total_clients}</div><div class="lbl">Total Clients</div></div>
      <div class="stat"><div class="num">{onboarded}</div><div class="lbl">RAG Ready</div></div>
      <div class="stat"><div class="num">{pending_review}</div><div class="lbl">Pending Review</div></div>
      <div class="stat"><div class="num">{total_research}</div><div class="lbl">Total Research Jobs</div></div>
    </div>
    {'<div style="background:rgba(251,191,36,0.1);border:1px solid rgba(251,191,36,0.3);border-radius:12px;padding:16px;margin-bottom:24px;font-size:0.9rem;color:#fbbf24">⚠️ ' + str(pending_review) + ' research request(s) waiting for your review. <a href="/admin/research" style="color:#a78bfa;font-weight:700">Review now →</a></div>' if pending_review > 0 else ""}
    <div class="table-wrap">
      <table>
        <tr>
          <th>Quick Links</th>
        </tr>
        <tr><td><a href="/admin/research" class="btn btn-view">📋 Research Queue ({pending_review} pending)</a></td></tr>
        <tr><td><a href="/admin/clients" class="btn btn-view">👥 Client List</a></td></tr>
        <tr><td>
          <button class="btn btn-approve" id="seed-btn" onclick="seedNotifications()">🔔 Seed Test Notifications (All 16 Types)</button>
          <div id="seed-result" style="margin-top:12px;font-size:0.85rem;display:none"></div>
        </td></tr>
      </table>
    </div>
    <script>
    async function seedNotifications() {{
      const btn = document.getElementById('seed-btn');
      const res = document.getElementById('seed-result');
      btn.disabled = true;
      btn.textContent = '⏳ Sending notifications...';
      res.style.display = 'none';
      try {{
        const r = await fetch('/admin/seed-test-notifications', {{method: 'POST'}});
        const data = await r.json();
        if (data.ok) {{
          btn.textContent = '✅ Done — ' + data.sent + ' notifications sent';
          btn.style.background = 'linear-gradient(135deg,#059669,#34d399)';
          res.style.display = 'block';
          res.style.color = '#34d399';
          res.innerHTML = data.sent + ' notifications fired. <a href="/notifications" style="color:#a78bfa;font-weight:700">View notifications →</a>';
        }} else {{
          throw new Error(JSON.stringify(data));
        }}
      }} catch(e) {{
        btn.disabled = false;
        btn.textContent = '🔔 Seed Test Notifications (All 16 Types)';
        res.style.display = 'block';
        res.style.color = '#f87171';
        res.textContent = 'Error: ' + e.message;
      }}
    }}
    </script>"""
    return HTMLResponse(_admin_page("Dashboard", body, admin.email))


# ─────────────────────────────────────────────────────
# Research queue — list all pending requests
# ─────────────────────────────────────────────────────

@router.get("/research", response_class=HTMLResponse)
async def research_queue(
    request: Request,
    db: Session = Depends(get_db),
    admin=Depends(require_admin),
):
    requests_all = (
        db.query(DeepResearchRequest, ClientProfile, User)
        .join(ClientProfile, DeepResearchRequest.client_profile_id == ClientProfile.id)
        .join(User, ClientProfile.user_id == User.id)
        .order_by(DeepResearchRequest.created_at.desc())
        .all()
    )

    if not requests_all:
        rows = '<tr><td colspan="5"><div class="empty-state"><div class="icon">✅</div><p>No research requests yet.</p></div></td></tr>'
    else:
        rows = ""
        for dr, profile, user in requests_all:
            badge_map = {
                "pending":  "badge-pending",
                "approved": "badge-approved",
                "rejected": "badge-rejected",
                "running":  "badge-running",
                "complete": "badge-complete",
                "failed":   "badge-failed",
            }
            badge_cls = badge_map.get(dr.status.value, "badge-pending")
            created = dr.created_at.strftime("%b %d, %Y %I:%M %p") if dr.created_at else "—"
            rows += f"""
            <tr>
              <td><strong>{profile.business_name}</strong><br><span style="color:rgba(255,255,255,0.4);font-size:0.8rem">{user.email}</span></td>
              <td>{profile.niche or "—"}</td>
              <td><span class="badge {badge_cls}">{dr.status.value}</span></td>
              <td>{created}</td>
              <td><a href="/admin/research/{dr.id}" class="btn btn-view">Review</a></td>
            </tr>"""

    body = f"""
    <h2>Research Request Queue</h2>
    <p class="sub">Review each request before AI research runs. This protects you from wasting API credits on incorrect queries.</p>
    <div class="table-wrap">
      <table>
        <tr>
          <th>Client</th><th>Niche</th><th>Status</th><th>Submitted</th><th>Action</th>
        </tr>
        {rows}
      </table>
    </div>"""
    return HTMLResponse(_admin_page("Research Queue", body, admin.email))


# ─────────────────────────────────────────────────────
# Research detail — view + approve/reject
# ─────────────────────────────────────────────────────

@router.get("/research/{request_id}", response_class=HTMLResponse)
async def research_detail(
    request_id: str,
    request: Request,
    db: Session = Depends(get_db),
    admin=Depends(require_admin),
):
    dr = db.query(DeepResearchRequest).filter(DeepResearchRequest.id == request_id).first()
    if not dr:
        return HTMLResponse("<p>Not found.</p>", status_code=404)

    profile = db.query(ClientProfile).filter(ClientProfile.id == dr.client_profile_id).first()
    user    = db.query(User).filter(User.id == profile.user_id).first() if profile else None

    try:
        details = json.loads(dr.raw_business_details)
    except Exception:
        details = {}

    def field(label, val):
        return f'<div class="field-label">{label}</div><div class="field-val">{val or "—"}</div>'

    details_html = "".join(
        field(k.replace("_", " ").title(), v) for k, v in details.items()
    )

    badge_map = {
        "pending":  "badge-pending",  "approved": "badge-approved",
        "rejected": "badge-rejected", "running":  "badge-running",
        "complete": "badge-complete", "failed":   "badge-failed",
    }
    badge_cls = badge_map.get(dr.status.value, "badge-pending")

    # Action form only for pending
    action_html = ""
    if dr.status == DeepResearchStatus.pending:
        action_html = f"""
        <div class="card">
          <h3>Your Decision</h3>
          <p style="font-size:0.85rem;color:rgba(255,255,255,0.4);margin-bottom:20px">
            Review the proposed research query above. You can edit it before approving.
          </p>
          <form method="post" action="/admin/research/{dr.id}/decide">
            <div class="field-label">Edit Research Query (optional)</div>
            <textarea name="research_query" rows="4">{dr.research_query}</textarea>

            <div class="field-label" style="margin-top:16px">Notes (optional — shown internally only)</div>
            <input type="text" name="admin_notes" placeholder="e.g. Approved after confirming niche...">

            <div class="action-row">
              <button type="submit" name="action" value="approve" class="btn btn-approve">✅ Approve & Run Research</button>
              <button type="submit" name="action" value="reject"  class="btn btn-reject">❌ Reject</button>
            </div>
          </form>
        </div>"""

    body = f"""
    <div style="margin-bottom:16px"><a href="/admin/research" style="color:#a78bfa;text-decoration:none;font-size:0.88rem">← Back to queue</a></div>
    <h2>{profile.business_name if profile else "Unknown"}</h2>
    <p class="sub">{user.email if user else "—"} · <span class="badge {badge_cls}">{dr.status.value}</span> · Submitted {dr.created_at.strftime("%b %d, %Y %I:%M %p") if dr.created_at else "—"}</p>

    <div class="card">
      <h3>Business Details (what client submitted)</h3>
      {details_html}
    </div>

    <div class="card">
      <h3>Proposed Research Query</h3>
      <p style="font-size:0.82rem;color:rgba(255,255,255,0.35);margin-bottom:8px">This is the query that will be sent to the AI research system. Review it carefully.</p>
      <div class="query-box">{dr.research_query}</div>
      {f'<div class="field-label" style="margin-top:16px">Admin Notes</div><div class="field-val">{dr.admin_notes}</div>' if dr.admin_notes else ""}
    </div>

    {action_html}

    {f'<div class="card"><h3>Research Results</h3><div class="field-val">{dr.research_results}</div></div>' if dr.research_results else ""}"""

    return HTMLResponse(_admin_page(f"Review: {profile.business_name if profile else ''}", body, admin.email))


@router.post("/research/{request_id}/decide")
async def research_decide(
    request_id: str,
    background_tasks: BackgroundTasks,
    request: Request,
    action: str = Form(...),
    research_query: str = Form(...),
    admin_notes: str = Form(""),
    db: Session = Depends(get_db),
    admin=Depends(require_admin),
):
    dr = db.query(DeepResearchRequest).filter(DeepResearchRequest.id == request_id).first()
    if not dr:
        return RedirectResponse("/admin/research", status_code=303)

    dr.research_query = research_query.strip()
    dr.admin_notes    = admin_notes.strip()
    dr.reviewed_by    = admin.email
    dr.reviewed_at    = datetime.utcnow()

    if action == "approve":
        dr.status = DeepResearchStatus.approved

        # Update client profile status
        profile = db.query(ClientProfile).filter(ClientProfile.id == dr.client_profile_id).first()
        if profile:
            profile.onboarding_status = OnboardingStatus.research_run

        db.commit()

        # Fire deep research in background
        background_tasks.add_task(
            _run_deep_research,
            request_id=dr.id,
            client_profile_id=dr.client_profile_id,
        )
    else:
        dr.status = DeepResearchStatus.rejected
        # Send client back to form
        profile = db.query(ClientProfile).filter(ClientProfile.id == dr.client_profile_id).first()
        if profile:
            profile.onboarding_status = OnboardingStatus.pending
            profile.onboarding_error  = f"Our team reviewed your submission and needs more details. Notes: {admin_notes or 'Please contact support.'}"
        db.commit()

    return RedirectResponse("/admin/research", status_code=303)


# ─────────────────────────────────────────────────────
# Background: run deep research + ingest into RAG
# ─────────────────────────────────────────────────────

def _run_deep_research(request_id: str, client_profile_id: str):
    """Sync wrapper — FastAPI runs sync BackgroundTasks in a thread pool."""
    from utils.agent_executor import run_agent_in_background
    run_agent_in_background(_run_deep_research_async(request_id, client_profile_id))


async def _run_deep_research_async(request_id: str, client_profile_id: str):
    """
    Uses Gemini (deep research mode) or Claude to research the query,
    then ingests results into the client's RAG knowledge base.
    """
    from database.db import SessionLocal
    from agents.rag_system import RAGSystem

    db = SessionLocal()
    try:
        dr      = db.query(DeepResearchRequest).filter(DeepResearchRequest.id == request_id).first()
        profile = db.query(ClientProfile).filter(ClientProfile.id == client_profile_id).first()
        if not dr or not profile:
            return

        dr.status = DeepResearchStatus.running
        db.commit()

        research_text = await _execute_research(dr.research_query, profile.business_name)

        if research_text:
            # Ingest into RAG
            rag = RAGSystem()
            rag.add_knowledge(
                text=research_text,
                client_id=profile.client_id,
                source="deep_research",
                category="market_research",
                tags=["deep_research", "onboarding", "market_analysis"],
            )

            # Also ingest the raw business details
            try:
                details = json.loads(dr.raw_business_details)
                details_text = "\n".join(f"{k.replace('_',' ').title()}: {v}" for k, v in details.items() if v)
                rag.add_knowledge(
                    text=f"Business Profile:\n{details_text}",
                    client_id=profile.client_id,
                    source="manual_onboarding",
                    category="business_profile",
                    tags=["profile", "onboarding"],
                )
            except Exception:
                pass

            dr.research_results = research_text[:10000]  # store preview
            dr.status           = DeepResearchStatus.complete
            dr.ingested_at      = datetime.utcnow()
            profile.onboarding_status = OnboardingStatus.complete
            profile.rag_ready         = True
        else:
            dr.status = DeepResearchStatus.failed
            profile.onboarding_status = OnboardingStatus.failed
            profile.onboarding_error  = "Deep research returned no content. Please contact support."

        db.commit()

    except Exception as e:
        try:
            dr      = db.query(DeepResearchRequest).filter(DeepResearchRequest.id == request_id).first()
            profile = db.query(ClientProfile).filter(ClientProfile.id == client_profile_id).first()
            if dr:
                dr.status = DeepResearchStatus.failed
            if profile:
                profile.onboarding_status = OnboardingStatus.failed
                profile.onboarding_error  = str(e)
            db.commit()
        except Exception:
            pass
    finally:
        db.close()


async def _execute_research(query: str, business_name: str) -> Optional[str]:
    """Run the actual research — tries Gemini deep research first, falls back to Claude."""
    import anthropic

    # Try Gemini deep research
    gemini_key = os.getenv("GEMINI_API_KEY")
    if gemini_key:
        try:
            import httpx
            headers = {"Content-Type": "application/json"}
            payload = {
                "contents": [{"parts": [{"text": query}], "role": "user"}],
                "generationConfig": {"temperature": 0.3, "maxOutputTokens": 8192},
                "tools": [{"googleSearch": {}}],
            }
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash-exp:generateContent?key={gemini_key}"
            async with httpx.AsyncClient(timeout=120) as client:
                resp = await client.post(url, headers=headers, json=payload)
                if resp.status_code == 200:
                    data = resp.json()
                    parts = data.get("candidates", [{}])[0].get("content", {}).get("parts", [])
                    text = " ".join(p.get("text", "") for p in parts if "text" in p)
                    if text.strip():
                        return f"Market Research for {business_name}\n\nQuery: {query}\n\n{text}"
        except Exception as e:
            print(f"Gemini research error: {e}")

    # Fallback: Claude Sonnet
    try:
        client  = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
        model   = os.getenv("CLAUDE_SONNET_MODEL", "claude-sonnet-4-5-20250929")
        prompt  = f"""You are conducting market research for a client's AI marketing system.

Business: {business_name}
Research Query: {query}

Please provide comprehensive research covering:
1. Industry overview and key trends (2024-2026)
2. Target customer pain points and desires
3. Effective content marketing strategies for this niche
4. Key topics and themes for social media content
5. Competitor positioning and market gaps
6. Best platforms and content formats for this industry
7. Common objections and how to address them
8. Seasonal trends or events relevant to this business

Be thorough and specific. This will be used to train an AI marketing system."""
        msg = client.messages.create(
            model=model,
            max_tokens=4096,
            messages=[{"role": "user", "content": prompt}]
        )
        return msg.content[0].text
    except Exception as e:
        print(f"Claude research fallback error: {e}")
        return None


# ─────────────────────────────────────────────────────
# Client list
# ─────────────────────────────────────────────────────

@router.get("/clients", response_class=HTMLResponse)
async def client_list(
    request: Request,
    db: Session = Depends(get_db),
    admin=Depends(require_admin),
):
    clients = (
        db.query(User, ClientProfile)
        .outerjoin(ClientProfile, User.id == ClientProfile.user_id)
        .filter(User.is_admin == False)
        .order_by(User.created_at.desc())
        .all()
    )

    if not clients:
        rows = '<tr><td colspan="5"><div class="empty-state"><div class="icon">👤</div><p>No clients yet.</p></div></td></tr>'
    else:
        rows = ""
        for user, profile in clients:
            status_val = profile.onboarding_status.value if profile else "no profile"
            rag_badge  = '<span class="badge badge-complete">RAG Ready</span>' if (profile and profile.rag_ready) else '<span class="badge badge-pending">Not Ready</span>'
            joined     = user.created_at.strftime("%b %d, %Y") if user.created_at else "—"
            rows += f"""
            <tr>
              <td><strong>{user.full_name}</strong><br><span style="color:rgba(255,255,255,0.4);font-size:0.8rem">{user.email}</span></td>
              <td>{profile.business_name if profile else "—"}</td>
              <td>{profile.niche or "—" if profile else "—"}</td>
              <td>{rag_badge} <span style="color:rgba(255,255,255,0.4);font-size:0.8rem">{status_val}</span></td>
              <td>{joined}</td>
            </tr>"""

    body = f"""
    <h2>All Clients</h2>
    <p class="sub">Every client account and their onboarding status.</p>
    <div class="table-wrap">
      <table>
        <tr>
          <th>Client</th><th>Business</th><th>Niche</th><th>Status</th><th>Joined</th>
        </tr>
        {rows}
      </table>
    </div>"""
    return HTMLResponse(_admin_page("Clients", body, admin.email))


# ─────────────────────────────────────────────────────
# Seed test notifications (all 16 types) for a client
# ─────────────────────────────────────────────────────

@router.post("/seed-test-notifications")
async def seed_test_notifications(
    request: Request,
    admin=Depends(require_admin),
):
    """
    Fire one sample notification for every type so you can preview the
    full client-facing experience on the /notifications page.

    Usage:
        POST /admin/seed-test-notifications?client_id=<id>
        (omit client_id to default to the requesting admin's own account)
    """
    from utils.notification_manager import NotificationManager

    params     = dict(request.query_params)
    client_id  = params.get("client_id") or str(admin.id)

    notifier   = NotificationManager(client_id=client_id)

    # ── Samples ──────────────────────────────────────────────────────────
    samples = [
        # ── URGENT ───────────────────────────────────────────────────────
        dict(
            fn="send_notification",
            kwargs=dict(
                notification_type="complaint",
                title="Customer Complaint Received",
                message="@fitnessbyjamila left a heated comment on your latest reel: "
                        "'This program is a scam — I saw zero results in 30 days.' "
                        "Recommend a direct reply within 2 hours to protect brand sentiment.",
                priority="critical",
                channels=["dashboard"],
                metadata={"platform": "instagram", "sender": "@fitnessbyjamila",
                           "action_url": "https://instagram.com/", "action_label": "View Comment",
                           "action_type": "open_url"},
            ),
        ),
        dict(
            fn="send_notification",
            kwargs=dict(
                notification_type="escalation",
                title="Escalation — Refund Demand",
                message="@coachwealthmindset DM'd a second time demanding a refund after no reply "
                        "for 24 hrs. This conversation has been flagged as high-risk. "
                        "Respond now to avoid a chargeback.",
                priority="critical",
                channels=["dashboard"],
                metadata={"platform": "instagram", "sender": "@coachwealthmindset",
                           "action_url": "https://instagram.com/direct/inbox/", "action_label": "Open DM",
                           "action_type": "open_url"},
            ),
        ),
        dict(
            fn="send_notification",
            kwargs=dict(
                notification_type="sale",
                title="New Sale Inquiry — High Intent",
                message="@livefitwithjess replied to your Story with: "
                        "'I'm ready to invest in myself — what's the next step?' "
                        "This looks like a warm close. Send your booking link now.",
                priority="high",
                channels=["dashboard"],
                metadata={"platform": "instagram", "sender": "@livefitwithjess",
                           "action_url": "https://instagram.com/direct/inbox/", "action_label": "Reply in DMs",
                           "action_type": "open_url"},
            ),
        ),
        dict(
            fn="send_notification",
            kwargs=dict(
                notification_type="lead",
                title="New Lead Captured",
                message="@trainingwithkemi commented 'INFO' on your transformation post. "
                        "Auto-reply sent with your lead magnet link. "
                        "Follow up in 24 hrs to nurture this lead into a discovery call.",
                priority="high",
                channels=["dashboard"],
                metadata={"platform": "instagram", "sender": "@trainingwithkemi",
                           "action_url": "https://instagram.com/direct/inbox/", "action_label": "View Lead",
                           "action_type": "open_url"},
            ),
        ),
        dict(
            fn="send_notification",
            kwargs=dict(
                notification_type="support",
                title="Support Question — Program Access",
                message="@mindsetwithprince DM'd: 'Hey! I paid for the 12-week plan but "
                        "can't access Module 3.' This is a technical support request — "
                        "reply to prevent a negative review.",
                priority="medium",
                channels=["dashboard"],
                metadata={"platform": "instagram", "sender": "@mindsetwithprince",
                           "action_url": "https://instagram.com/direct/inbox/", "action_label": "View DM",
                           "action_type": "open_url"},
            ),
        ),
        # ── OPPORTUNITY ──────────────────────────────────────────────────
        dict(
            fn="send_growth_notification",
            kwargs=dict(
                notification_type="follow_suggestion",
                title="Follow Suggestion — Warm Prospect",
                message="@transformationcoachtyra (12.4K followers) consistently engages with "
                        "fitness and mindset content similar to yours. She commented on 3 of your "
                        "posts this week. A follow + DM could start a valuable relationship.",
                priority="medium",
                platform="instagram",
                action_url="https://instagram.com/transformationcoachtyra",
                action_label="View Profile",
                action_type="open_url",
            ),
        ),
        dict(
            fn="send_growth_notification",
            kwargs=dict(
                notification_type="group_opportunity",
                title="Facebook Group Worth Joining",
                message="'Online Coaches & Consultants — Scale to 6 Figures' has 48K members "
                        "and high daily engagement. Your content style aligns with the group rules. "
                        "Joining and posting weekly could drive 50–150 new followers per month.",
                priority="medium",
                platform="facebook",
                action_url="https://facebook.com/groups/onlinecoaches/",
                action_label="Join Group",
                action_type="open_url",
            ),
        ),
        dict(
            fn="send_growth_notification",
            kwargs=dict(
                notification_type="competitor_alert",
                title="Competitor Launched New Offer",
                message="@fitcoachpro just launched a '7-Day Free Challenge' funnel and gained "
                        "2,300 new followers in 48 hours. The entry point is a Reels series. "
                        "Consider a similar challenge format to capture the same audience.",
                priority="high",
                platform="instagram",
                action_url="https://instagram.com/fitcoachpro",
                action_label="View Competitor",
                action_type="open_url",
            ),
        ),
        # ── INTEL ────────────────────────────────────────────────────────
        dict(
            fn="send_growth_notification",
            kwargs=dict(
                notification_type="content_idea",
                title="Content Idea — Trending Audio",
                message="The audio 'No More Excuses' is trending on Reels with 1.8M uses this week. "
                        "A 'morning routine transformation' Reel with this audio could hit 50K+ views "
                        "based on your current engagement rate. Best posting window: Tue 7–9 AM EST.",
                priority="medium",
                platform="instagram",
                action_url="https://www.instagram.com/reels/audio/trending",
                action_label="Browse Trending Audio",
                action_type="open_url",
            ),
        ),
        dict(
            fn="send_growth_notification",
            kwargs=dict(
                notification_type="growth_tip",
                title="Growth Tip — Boost Story Replies",
                message="Your Stories average 3.2% reply rate — the industry benchmark for coaches "
                        "is 6–8%. Adding a 'Poll' or 'Question Box' sticker to your next 5 Stories "
                        "could double reply volume and signal to the algorithm you have high intent followers.",
                priority="low",
                platform="instagram",
                action_url="/settings/content",
                action_label="Edit Content Strategy",
                action_type="internal_link",
            ),
        ),
        # ── WINS ─────────────────────────────────────────────────────────
        dict(
            fn="send_growth_notification",
            kwargs=dict(
                notification_type="viral_alert",
                title="Viral Alert — Reel Taking Off!",
                message="Your Reel 'How I lost 20 lbs in 90 days' just hit 47K views — "
                        "4x your average performance. Engagement is accelerating (1,200 likes, "
                        "340 comments, 890 shares). Pin it to your profile NOW to maximize reach.",
                priority="high",
                platform="instagram",
                action_url="https://instagram.com/",
                action_label="View Reel",
                action_type="open_url",
            ),
        ),
        dict(
            fn="send_growth_notification",
            kwargs=dict(
                notification_type="milestone",
                title="Milestone Unlocked — 5,000 Followers!",
                message="You just crossed 5,000 Instagram followers! This is a key credibility "
                        "threshold for coaching clients. Update your bio link, consider enabling "
                        "Close Friends Stories for your paid community, and celebrate with a gratitude post.",
                priority="medium",
                platform="instagram",
                action_url="https://instagram.com/",
                action_label="View Profile",
                action_type="open_url",
            ),
        ),
        # ── HEALTH ───────────────────────────────────────────────────────
        dict(
            fn="send_growth_notification",
            kwargs=dict(
                notification_type="budget_alert",
                title="Ad Budget Alert — 80% Spent",
                message="Your Meta Ads campaign 'January Coaching Promo' has used $160 of your "
                        "$200 monthly budget. At the current spend rate, budget will hit zero "
                        "in ~2 days. Consider pausing low-performing ad sets or increasing budget.",
                priority="high",
                platform="facebook",
                action_url="/billing",
                action_label="Review Budget",
                action_type="internal_link",
            ),
        ),
        dict(
            fn="send_growth_notification",
            kwargs=dict(
                notification_type="sentiment_alert",
                title="Sentiment Shift Detected",
                message="Comment sentiment on your last 5 posts has dropped from +82% to +61% "
                        "positive over the past 7 days. The decline correlates with your recent "
                        "promotional content ratio. Your audience responds better to value-first posts.",
                priority="medium",
                platform="instagram",
                action_url="/analytics",
                action_label="View Analytics",
                action_type="internal_link",
            ),
        ),
        dict(
            fn="send_notification",
            kwargs=dict(
                notification_type="post",
                title="Post Published — Reel Scheduled",
                message="Your Reel 'Top 3 mistakes killing your gains' was successfully published "
                        "to Instagram at 7:02 AM EST. Early signals: 142 views in the first 15 min. "
                        "Check back in 2 hours for full engagement stats.",
                priority="low",
                channels=["dashboard"],
                metadata={"platform": "instagram",
                           "action_url": "https://instagram.com/", "action_label": "View Post",
                           "action_type": "open_url"},
            ),
        ),
        dict(
            fn="send_notification",
            kwargs=dict(
                notification_type="system",
                title="System — Instagram Token Refreshed",
                message="Your Instagram connection token was automatically refreshed. "
                        "All scheduled posts and DM automation are running normally. "
                        "No action required.",
                priority="low",
                channels=["dashboard"],
                metadata={"platform": "instagram",
                           "action_url": "/connections", "action_label": "View Connections",
                           "action_type": "internal_link"},
            ),
        ),
    ]

    sent, failed = 0, 0
    results = []

    for sample in samples:
        try:
            fn   = sample["fn"]
            kw   = sample["kwargs"]
            ntype = kw["notification_type"]

            if fn == "send_growth_notification":
                await notifier.send_growth_notification(**kw)
            else:
                await notifier.send_notification(**kw)

            sent += 1
            results.append({"type": ntype, "status": "sent"})
        except Exception as exc:
            failed += 1
            results.append({"type": kw.get("notification_type", "?"), "status": "error", "error": str(exc)})

    return {
        "ok": True,
        "client_id": client_id,
        "sent": sent,
        "failed": failed,
        "results": results,
        "view_url": "/notifications",
    }


# ─────────────────────────────────────────────────────
# Diagnostic: show ALL notifications (including cleared)
# ─────────────────────────────────────────────────────

@router.get("/debug-notifications")
async def debug_notifications(
    request: Request,
    admin=Depends(require_admin),
):
    """
    Return a JSON dump of ALL notifications for a client, including cleared ones.
    Helps diagnose why notifications disappear.

    Usage: GET /admin/debug-notifications?client_id=<id>
    """
    from database.db import get_db
    from database.models import ClientNotification, ClientProfile, GrowthReport
    import json as _json

    params    = dict(request.query_params)
    client_id = params.get("client_id", "")

    db = next(get_db())
    try:
        # If no client_id supplied, use admin's profile
        if not client_id:
            profile = db.query(ClientProfile).filter(
                ClientProfile.user_id == str(admin.id)
            ).first()
            client_id = profile.client_id if profile else "unknown"

        # All notifications — no cleared_at filter
        all_rows = (
            db.query(ClientNotification)
            .filter(ClientNotification.client_id == client_id)
            .order_by(ClientNotification.created_at.desc())
            .all()
        )

        notifs = []
        for r in all_rows:
            notifs.append({
                "id": r.id,
                "type": r.notification_type,
                "title": r.title,
                "message": (r.message or "")[:120],
                "priority": r.priority,
                "read": r.read,
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "cleared_at": r.cleared_at.isoformat() if r.cleared_at else None,
                "read_at": r.read_at.isoformat() if r.read_at else None,
            })

        visible = [n for n in notifs if n["cleared_at"] is None]
        cleared = [n for n in notifs if n["cleared_at"] is not None]

        # Growth reports (to confirm they exist)
        reports = (
            db.query(GrowthReport)
            .filter(GrowthReport.client_id == client_id)
            .order_by(GrowthReport.created_at.desc())
            .all()
        )
        report_list = [
            {"id": r.id, "goal": r.goal or "", "created_at": r.created_at.isoformat() if r.created_at else None}
            for r in reports
        ]

        return {
            "client_id": client_id,
            "total_notifications": len(notifs),
            "visible": len(visible),
            "cleared": len(cleared),
            "growth_reports": len(report_list),
            "reports": report_list,
            "notifications_all": notifs,
        }
    finally:
        db.close()


# ─────────────────────────────────────────────────────
# Report health diagnostics
# ─────────────────────────────────────────────────────

@router.get("/report-health")
async def report_health(request: Request, admin=Depends(require_admin)):
    """
    Returns a JSON health-check of growth reports:
    - Total reports in DB per client
    - Notifications referencing reports
    - Orphan notification references (notification links to a deleted report)
    """
    from utils.report_watchdog import verify_report_integrity
    return verify_report_integrity()


@router.post("/recover-orphan-reports")
async def recover_orphan_reports(request: Request, admin=Depends(require_admin)):
    """
    Scan filesystem for JSON report files not yet in PostgreSQL
    and import them.  Returns summary of what was imported.
    """
    from utils.report_watchdog import recover_orphaned_reports
    return recover_orphaned_reports()


@router.api_route("/trigger-growth-campaign", methods=["GET", "POST"])
async def trigger_growth_campaign(request: Request, admin=Depends(_require_admin_or_secret)):
    """
    Manually fire the 9 AM growth-campaign job for a client right now.
    Accepts admin session auth OR ?secret=<GROWTH_TEST_SECRET> for PowerShell testing.

    Usage:
        GET /admin/trigger-growth-campaign?client_id=<id>&secret=<GROWTH_TEST_SECRET>
    """
    import asyncio
    from agents.agent_scheduler import _job_growth_campaign_work
    from utils.agent_executor import AGENT_POOL, run_agent_in_background

    params = dict(request.query_params)
    client_id = params.get("client_id") or (str(admin.id) if admin else "default_client")

    # Fire-and-forget: dispatch to thread pool WITHOUT awaiting.
    # The old code did `await submit_agent_task(...)` which blocked the HTTP
    # response for up to 600s, causing request timeouts.
    loop = asyncio.get_running_loop()
    loop.run_in_executor(
        AGENT_POOL,
        run_agent_in_background,
        _job_growth_campaign_work(client_id),
        600,
    )

    return JSONResponse({
        "status": "dispatched",
        "client_id": client_id,
        "version": "v3-fire-and-forget",
        "message": (
            f"Growth campaign job dispatched for '{client_id}'. "
            "Claude-first recommendation engine (no Tavily mining)."
        ),
    })


# ─────────────────────────────────────────────────────
# Debug: test recommendations directly (bypasses scheduler)
# ─────────────────────────────────────────────────────

@router.api_route("/test-recommendations", methods=["GET"])
async def test_recommendations_direct(request: Request, admin=Depends(_require_admin_or_secret)):
    """Call generate_follow_recommendations() directly and return the raw result.
    This bypasses the scheduler, background executor, and timeout — so we can see
    exactly what Claude returns (or what error occurs).

    Usage:
        GET /admin/test-recommendations?client_id=default_client&secret=<secret>
    """
    import traceback
    import time as _time_test
    from agents.growth_agent import GrowthAgent

    params = dict(request.query_params)
    client_id = params.get("client_id", "default_client")

    agent = GrowthAgent(client_id=client_id)
    _start = _time_test.time()
    try:
        recs = await agent.generate_follow_recommendations(
            platforms=["instagram", "facebook", "tiktok", "twitter_x", "linkedin"],
            per_platform_limits={"instagram": 5, "facebook": 3, "tiktok": 3, "twitter_x": 3, "linkedin": 3},
            num_groups=3,
        )
        _elapsed = round(_time_test.time() - _start, 1)
        people = recs.get("people", [])
        groups = recs.get("groups", [])
        return JSONResponse({
            "ok": True,
            "client_id": client_id,
            "elapsed_seconds": _elapsed,
            "people_count": len(people),
            "groups_count": len(groups),
            "people": people[:5],
            "groups": groups[:3],
        })
    except Exception as e:
        _elapsed = round(_time_test.time() - _start, 1)
        return JSONResponse({
            "ok": False,
            "client_id": client_id,
            "elapsed_seconds": _elapsed,
            "error": str(e),
            "traceback": traceback.format_exc()[-2000:],
        }, status_code=500)


# ─────────────────────────────────────────────────────
# Debug: tail scheduler logs
# ─────────────────────────────────────────────────────

@router.api_route("/scheduler-logs", methods=["GET"])
async def scheduler_logs(request: Request, admin=Depends(_require_admin_or_secret)):
    """Return the last N lines of logs/scheduler.log filtered by optional keyword."""
    import os
    params = dict(request.query_params)
    n = int(params.get("n", "50"))
    keyword = params.get("q", "").lower()

    log_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "logs", "scheduler.log")
    if not os.path.exists(log_path):
        return JSONResponse({"error": "logs/scheduler.log not found"}, status_code=404)

    with open(log_path, "r", encoding="utf-8", errors="replace") as f:
        all_lines = f.readlines()

    if keyword:
        all_lines = [l for l in all_lines if keyword in l.lower()]

    tail = all_lines[-n:]
    return JSONResponse({
        "total_lines": len(all_lines),
        "returned": len(tail),
        "keyword": keyword or "(none)",
        "lines": [l.rstrip() for l in tail],
    })


# ─────────────────────────────────────────────────────
# Debug: check recent growth notifications
# ─────────────────────────────────────────────────────

@router.api_route("/check-growth-notifications", methods=["GET"])
async def check_growth_notifications(request: Request, admin=Depends(_require_admin_or_secret)):
    """Return the 10 most recent growth-related notifications for debugging."""
    from database.db import get_db
    from database.models import ClientNotification, ClientProfile

    params = dict(request.query_params)
    client_id = params.get("client_id", "default_client")

    db = next(get_db())
    try:
        type_filter = params.get("type")
        q = db.query(ClientNotification).filter(
            ClientNotification.client_id == client_id,
        )
        if type_filter:
            q = q.filter(ClientNotification.notification_type == type_filter)
        else:
            q = q.filter(
                ClientNotification.notification_type.in_([
                    "growth_report", "growth_tip", "follow_suggestion",
                    "group_opportunity",
                ]),
            )
        rows = (
            q.order_by(ClientNotification.created_at.desc())
            .limit(20)
            .all()
        )
        return JSONResponse({
            "client_id": client_id,
            "count": len(rows),
            "notifications": [
                {
                    "id": str(r.id),
                    "type": r.notification_type,
                    "title": r.title,
                    "created_at": r.created_at.isoformat() if r.created_at else None,
                    "cleared_at": r.cleared_at.isoformat() if r.cleared_at else None,
                    "message_preview": (r.message or "")[:200],
                }
                for r in rows
            ],
        })
    finally:
        db.close()


# ─────────────────────────────────────────────────────
# Debug: check growth reports in DB
# ─────────────────────────────────────────────────────

@router.api_route("/check-growth-reports", methods=["GET"])
async def check_growth_reports(request: Request, admin=Depends(_require_admin_or_secret)):
    """Return growth reports for a client — shows IDs, goals, JSON length/validity."""
    from database.models import GrowthReport
    import json as _json

    params = dict(request.query_params)
    client_id = params.get("client_id", "default_client")

    db = next(get_db())
    try:
        rows = (
            db.query(GrowthReport)
            .filter(GrowthReport.client_id == client_id)
            .order_by(GrowthReport.created_at.desc())
            .limit(10)
            .all()
        )
        items = []
        for r in rows:
            json_ok = False
            json_len = len(r.report_json) if r.report_json else 0
            keys = []
            error = None
            try:
                data = _json.loads(r.report_json)
                json_ok = True
                keys = list(data.keys())[:15]
            except Exception as je:
                error = str(je)[:200]
            items.append({
                "id": r.id,
                "goal": r.goal or "",
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "json_length": json_len,
                "json_valid": json_ok,
                "json_keys": keys,
                "json_error": error,
            })
        return JSONResponse({
            "client_id": client_id,
            "count": len(items),
            "reports": items,
        })
    finally:
        db.close()


# ─────────────────────────────────────────────────────
# Clear growth-report dedup so the campaign can re-run
# ─────────────────────────────────────────────────────

@router.api_route("/clear-growth-dedup", methods=["GET", "POST"])
async def clear_growth_dedup(request: Request, admin=Depends(_require_admin_or_secret)):
    """
    Delete recent growth_report notifications so the 20-hour dedup gate
    is reset and /admin/trigger-growth-campaign can run again immediately.
    Accepts admin session auth OR ?secret=<GROWTH_TEST_SECRET> for PowerShell testing.

    Usage:
        GET /admin/clear-growth-dedup?client_id=default_client&secret=<GROWTH_TEST_SECRET>
    """
    from database.db import get_db
    from database.models import ClientNotification, ClientProfile
    from datetime import datetime, timedelta

    params = dict(request.query_params)
    client_id = params.get("client_id", "")
    ntype = params.get("type", "growth_report")

    db = next(get_db())
    try:
        if not client_id and admin:
            profile = db.query(ClientProfile).filter(
                ClientProfile.user_id == str(admin.id)
            ).first()
            client_id = profile.client_id if profile else ""

        if not client_id:
            client_id = "default_client"  # fallback for secret-auth calls

        cutoff = datetime.utcnow() - timedelta(hours=25)
        deleted = (
            db.query(ClientNotification)
            .filter(
                ClientNotification.client_id == client_id,
                ClientNotification.notification_type == ntype,
                ClientNotification.created_at >= cutoff,
            )
            .delete(synchronize_session="fetch")
        )
        db.commit()
        return JSONResponse({
            "ok": True,
            "client_id": client_id,
            "deleted": deleted,
            "message": f"Cleared {deleted} recent {ntype} row(s). You can now trigger again.",
        })
    finally:
        db.close()


# ─────────────────────────────────────────────────────
# Restore cleared notifications (un-clear by type/all)
# ─────────────────────────────────────────────────────

@router.post("/restore-notifications")
async def restore_notifications(
    request: Request,
    admin=Depends(require_admin),
):
    """
    Un-clear (restore) notifications that were soft-deleted.

    Usage:
        POST /admin/restore-notifications?client_id=<id>
        POST /admin/restore-notifications?client_id=<id>&types=content_idea,growth_tip
        POST /admin/restore-notifications              (uses admin's own profile)

    Removes cleared_at on matching rows so they reappear in the notification center.
    """
    from database.db import get_db
    from database.models import ClientNotification, ClientProfile

    params    = dict(request.query_params)
    client_id = params.get("client_id", "")
    types_csv = params.get("types", "")

    db = next(get_db())
    try:
        if not client_id:
            profile = db.query(ClientProfile).filter(
                ClientProfile.user_id == str(admin.id)
            ).first()
            client_id = profile.client_id if profile else "unknown"

        query = (
            db.query(ClientNotification)
            .filter(
                ClientNotification.client_id == client_id,
                ClientNotification.cleared_at != None,
            )
        )
        if types_csv:
            type_list = [t.strip() for t in types_csv.split(",") if t.strip()]
            query = query.filter(ClientNotification.notification_type.in_(type_list))

        count = query.update({"cleared_at": None}, synchronize_session="fetch")
        db.commit()

        return {
            "ok": True,
            "client_id": client_id,
            "restored": count,
            "types_filter": types_csv or "(all)",
        }
    finally:
        db.close()
