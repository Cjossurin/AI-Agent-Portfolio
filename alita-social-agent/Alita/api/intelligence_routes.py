"""
api/intelligence_routes.py
===========================
Marketing Intelligence dashboard — connects MarketingIntelligenceAgent to the portal.

Routes (HTML)
-------------
GET  /intelligence/dashboard       — Research & content ideas hub

Routes (JSON API)
-----------------
POST /api/intelligence/ideas       — Generate content ideas (MarketingIntelligenceAgent)
POST /api/intelligence/strategy    — Generate weekly content strategy
GET  /api/intelligence/saved-ideas — List previously generated idea batches
"""

import json
import os
import sys
import uuid
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

router = APIRouter(tags=["Intelligence"])

INTEL_STORAGE = Path("storage") / "intelligence"


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def _saved_batches(client_id: str) -> list:
    d = INTEL_STORAGE / client_id
    if not d.exists():
        return []
    items = []
    for f in sorted(d.glob("*.json"), reverse=True)[:30]:
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            items.append({
                "batch_id": data.get("batch_id", f.stem),
                "created_at": data.get("created_at", "")[:10],
                "type": data.get("type", "ideas"),
                "niche": data.get("niche", ""),
                "ideas_count": len(data.get("ideas", [])),
                "platforms": data.get("platforms", []),
            })
        except Exception:
            pass
    return items


# ──────────────────────────────────────────────────────────────────────────────
# Background tasks
# ──────────────────────────────────────────────────────────────────────────────

def _bg_generate_ideas(client_id: str, batch_id: str, params: dict):
    """Sync wrapper — FastAPI runs sync BackgroundTasks in a thread pool."""
    from utils.agent_executor import run_agent_in_background
    run_agent_in_background(_bg_generate_ideas_async(client_id, batch_id, params))


async def _bg_generate_ideas_async(client_id: str, batch_id: str, params: dict):
    try:
        from agents.marketing_intelligence_agent import MarketingIntelligenceAgent
        from utils.notification_manager import NotificationManager

        agent = MarketingIntelligenceAgent(client_id=client_id)
        notifier = NotificationManager(client_id=client_id)

        ideas = await agent.generate_content_ideas(
            niche=params.get("niche"),
            num_ideas=int(params.get("num_ideas", 5)),
            platforms=params.get("platforms"),
            goals=params.get("goals"),
            themes=params.get("themes"),
            additional_context=params.get("additional_context", ""),
        )

        # Serialize ideas
        ideas_dicts = []
        for idea in ideas:
            try:
                d = idea.to_dict() if hasattr(idea, "to_dict") else idea.__dict__
                # make serializable
                d2 = {}
                for k, v in d.items():
                    if hasattr(v, "value"):
                        d2[k] = v.value
                    elif isinstance(v, list):
                        d2[k] = [x.value if hasattr(x,"value") else str(x) for x in v]
                    else:
                        d2[k] = v
                ideas_dicts.append(d2)
            except Exception:
                ideas_dicts.append({"title": str(idea)})

        # Save
        save_dir = INTEL_STORAGE / client_id
        save_dir.mkdir(parents=True, exist_ok=True)
        payload = {
            "batch_id": batch_id,
            "type": "ideas",
            "created_at": datetime.now().isoformat(),
            "client_id": client_id,
            "niche": params.get("niche", ""),
            "platforms": params.get("platforms", []),
            "ideas": ideas_dicts,
        }
        (save_dir / f"{batch_id}.json").write_text(
            json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
        )

        # Fire top idea as notification
        if ideas_dicts:
            top = ideas_dicts[0]
            await notifier.send_growth_notification(
                notification_type="content_idea",
                title=f"New Content Idea: {top.get('title','')[:60]}",
                message=top.get("hook") or top.get("description") or "",
                priority="medium",
                action_url="/intelligence/dashboard",
                action_label="View All Ideas",
                action_type="internal_link",
                extra_meta={"batch_id": batch_id},
            )

        print(f"✅ Intelligence: {len(ideas_dicts)} ideas saved as {batch_id}")

    except Exception as exc:
        print(f"❌ _bg_generate_ideas failed: {exc}")
        import traceback; traceback.print_exc()


def _bg_generate_strategy(client_id: str, batch_id: str, niche: str):
    """Sync wrapper — FastAPI runs sync BackgroundTasks in a thread pool."""
    from utils.agent_executor import run_agent_in_background
    run_agent_in_background(_bg_generate_strategy_async(client_id, batch_id, niche))


async def _bg_generate_strategy_async(client_id: str, batch_id: str, niche: str):
    try:
        from agents.marketing_intelligence_agent import MarketingIntelligenceAgent
        from utils.notification_manager import NotificationManager

        agent = MarketingIntelligenceAgent(client_id=client_id)
        notifier = NotificationManager(client_id=client_id)

        strategy = await agent.generate_weekly_strategy(niche=niche)

        # Save
        save_dir = INTEL_STORAGE / client_id
        save_dir.mkdir(parents=True, exist_ok=True)

        def _ser(obj):
            if hasattr(obj, "__dict__"):
                return {k: _ser(v) for k, v in obj.__dict__.items()}
            if hasattr(obj, "value"):
                return obj.value
            if isinstance(obj, list):
                return [_ser(x) for x in obj]
            if isinstance(obj, dict):
                return {k: _ser(v) for k, v in obj.items()}
            return obj

        raw_ideas = _ser(getattr(strategy, "ideas", []))
        # Ensure ideas is always a list of dicts
        if isinstance(raw_ideas, dict):
            raw_ideas = list(raw_ideas.values()) if raw_ideas else []
        elif not isinstance(raw_ideas, list):
            raw_ideas = []

        payload = {
            "batch_id": batch_id,
            "type": "strategy",
            "created_at": datetime.now().isoformat(),
            "client_id": client_id,
            "niche": niche,
            "strategy": _ser(strategy) if strategy else {},
            "ideas": raw_ideas,
            "themes": _ser(getattr(strategy, "themes", [])),
            "content_mix": _ser(getattr(strategy, "content_mix", {})),
            "posting_frequency": getattr(strategy, "posting_frequency", None),
            "period": getattr(strategy, "period", "weekly"),
            "start_date": getattr(strategy, "start_date", ""),
            "end_date": getattr(strategy, "end_date", ""),
            "notes": getattr(strategy, "notes", ""),
        }
        (save_dir / f"{batch_id}.json").write_text(
            json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
        )

        await notifier.send_growth_notification(
            notification_type="growth_tip",
            title="Weekly Marketing Strategy Ready",
            message=f"Your {niche} content strategy for the week has been generated.",
            priority="medium",
            action_url="/intelligence/dashboard",
            action_label="View Strategy",
            action_type="internal_link",
            extra_meta={"batch_id": batch_id},
        )

        print(f"✅ Intelligence: weekly strategy saved as {batch_id}")

    except Exception as exc:
        print(f"❌ _bg_generate_strategy failed: {exc}")
        import traceback; traceback.print_exc()


# ──────────────────────────────────────────────────────────────────────────────
# JSON API
# ──────────────────────────────────────────────────────────────────────────────

@router.post("/api/intelligence/ideas")
async def api_generate_ideas(request: Request, background_tasks: BackgroundTasks):
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
        allowed, msg = check_limit(profile, "competitive_research")
        if not allowed:
            return JSONResponse({"error": msg, "upgrade_url": "/billing"}, status_code=402)
        increment_usage(profile, "competitive_research", db)

        batch_id = uuid.uuid4().hex[:12]
        params = {
            "niche": body.get("niche") or profile.niche,
            "num_ideas": body.get("num_ideas", 5),
            "platforms": body.get("platforms"),
            "goals": body.get("goals"),
            "themes": body.get("themes"),
            "additional_context": body.get("additional_context", ""),
        }
        background_tasks.add_task(_bg_generate_ideas, profile.client_id, batch_id, params)
        return JSONResponse({
            "ok": True, "batch_id": batch_id,
            "message": "Generating content ideas. This takes 15–30 seconds.",
        })
    finally:
        db.close()


@router.post("/api/intelligence/strategy")
async def api_generate_strategy(request: Request, background_tasks: BackgroundTasks):
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
        allowed, msg = check_limit(profile, "growth_strategy")
        if not allowed:
            return JSONResponse({"error": msg, "upgrade_url": "/billing"}, status_code=402)
        increment_usage(profile, "growth_strategy", db)

        batch_id = uuid.uuid4().hex[:12]
        niche = body.get("niche") or profile.niche or "business"
        background_tasks.add_task(_bg_generate_strategy, profile.client_id, batch_id, niche)
        return JSONResponse({
            "ok": True, "batch_id": batch_id,
            "message": "Generating weekly marketing strategy. Takes 30–60 seconds.",
        })
    finally:
        db.close()


@router.get("/api/intelligence/saved-ideas")
async def api_saved_ideas(request: Request):
    db = next(get_db())
    try:
        user, profile = get_user_context(request, db)
        if not user:
            return JSONResponse({"error": "Unauthorized"}, status_code=401)
        if not profile:
            return JSONResponse({"batches": []})
        return JSONResponse({"batches": _saved_batches(profile.client_id)})
    finally:
        db.close()


@router.get("/api/intelligence/batch/{batch_id}")
async def api_batch_detail(request: Request, batch_id: str):
    db = next(get_db())
    try:
        user, profile = get_user_context(request, db)
        if not user:
            return JSONResponse({"error": "Unauthorized"}, status_code=401)
        if not profile:
            return JSONResponse({"error": "Not found"}, status_code=404)

        f = INTEL_STORAGE / profile.client_id / f"{batch_id}.json"
        if not f.exists():
            return JSONResponse({"status": "generating"})
        return JSONResponse(json.loads(f.read_text(encoding="utf-8")))
    finally:
        db.close()


# ──────────────────────────────────────────────────────────────────────────────
# HTML dashboard
# ──────────────────────────────────────────────────────────────────────────────

@router.get("/intelligence/dashboard", response_class=HTMLResponse)
async def intelligence_dashboard(request: Request):
    db = next(get_db())
    try:
        user, profile = get_user_context(request, db)
        if not user:
            return RedirectResponse("/account/login", status_code=303)
        if not profile:
            return RedirectResponse("/onboarding", status_code=303)

        batches = _saved_batches(profile.client_id)
        batch_rows = ""
        if batches:
            for b in batches[:15]:
                type_badge = (
                    '<span style="background:#e8eaf6;color:#3949ab;border-radius:99px;padding:2px 9px;font-size:.72rem;font-weight:700">Strategy</span>'
                    if b["type"] == "strategy" else
                    '<span style="background:#f3e5f5;color:#7b1fa2;border-radius:99px;padding:2px 9px;font-size:.72rem;font-weight:700">Ideas</span>'
                )
                plats = ", ".join(b["platforms"]) if b.get("platforms") else "all"
                batch_rows += f"""
                <tr style="border-bottom:1px solid #f0f2f5">
                  <td style="padding:12px 20px;font-size:.8rem;color:#90949c">{b["created_at"]}</td>
                  <td style="padding:12px 12px">{type_badge}</td>
                  <td style="padding:12px 12px;font-size:.82rem">{b.get("niche","")}</td>
                  <td style="padding:12px 12px;font-size:.8rem;color:#606770">{plats}</td>
                  <td style="padding:12px 12px;text-align:center">
                    <span style="background:#e8f5e9;color:#2e7d32;border-radius:99px;padding:2px 9px;font-size:.75rem;font-weight:700">{b["ideas_count"]} ideas</span>
                  </td>
                  <td style="padding:12px 12px">
                    <button onclick="viewBatch('{b['batch_id']}')" style="background:#5c6ac4;color:#fff;border:none;border-radius:8px;padding:5px 14px;font-size:.78rem;cursor:pointer">View</button>
                  </td>
                </tr>"""
        else:
            batch_rows = "<tr><td colspan='6' style='text-align:center;padding:32px;color:#90949c;font-size:.84rem'>No content research yet. Generate your first batch above.</td></tr>"

        niche_default = profile.niche or "coaching"

        _body = f"""
<div style="max-width:980px;margin:0 auto">

  <!-- Header -->
  <div style="margin-bottom:24px">
    <h1 style="font-size:1.5rem;font-weight:800;margin-bottom:6px">&#129504; Marketing Intelligence</h1>
    <p style="font-size:.87rem;color:#606770;max-width:580px">
      Research-backed content ideas and weekly marketing strategies powered by competitive intelligence, trending topics, and your client knowledge base.
    </p>
  </div>

  <!-- Action cards row -->
  <div style="display:grid;grid-template-columns:1fr 1fr;gap:18px;margin-bottom:28px">

    <!-- Ideas card -->
    <div style="background:#fff;border-radius:14px;border:1px solid #e9ebee;padding:24px">
      <h2 style="font-size:.95rem;font-weight:700;margin-bottom:12px">&#128161; Generate Content Ideas</h2>
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-bottom:10px">
        <div>
          <label style="font-size:.76rem;font-weight:600;color:#444;display:block;margin-bottom:4px">How many ideas?</label>
          <select id="ideas-count" style="width:100%;padding:8px 11px;border:1px solid #dde0e4;border-radius:8px;font-size:.83rem;background:#fff">
            <option value="5">5</option><option value="10" selected>10</option><option value="15">15</option>
          </select>
        </div>
      </div>
      <div style="margin-bottom:12px">
        <label style="font-size:.76rem;font-weight:600;color:#444;display:block;margin-bottom:6px">Platforms</label>
        <div style="display:flex;flex-wrap:wrap;gap:8px">
          <label style="display:flex;align-items:center;gap:4px;font-size:.82rem;cursor:pointer;background:#fafbfc;padding:5px 10px;border-radius:8px;border:1px solid #e4e6eb">
            <input type="checkbox" class="plat-cb" value="Instagram" checked> Instagram
          </label>
          <label style="display:flex;align-items:center;gap:4px;font-size:.82rem;cursor:pointer;background:#fafbfc;padding:5px 10px;border-radius:8px;border:1px solid #e4e6eb">
            <input type="checkbox" class="plat-cb" value="TikTok"> TikTok
          </label>
          <label style="display:flex;align-items:center;gap:4px;font-size:.82rem;cursor:pointer;background:#fafbfc;padding:5px 10px;border-radius:8px;border:1px solid #e4e6eb">
            <input type="checkbox" class="plat-cb" value="LinkedIn"> LinkedIn
          </label>
          <label style="display:flex;align-items:center;gap:4px;font-size:.82rem;cursor:pointer;background:#fafbfc;padding:5px 10px;border-radius:8px;border:1px solid #e4e6eb">
            <input type="checkbox" class="plat-cb" value="Facebook"> Facebook
          </label>
          <label style="display:flex;align-items:center;gap:4px;font-size:.82rem;cursor:pointer;background:#fafbfc;padding:5px 10px;border-radius:8px;border:1px solid #e4e6eb">
            <input type="checkbox" class="plat-cb" value="YouTube"> YouTube
          </label>
          <label style="display:flex;align-items:center;gap:4px;font-size:.82rem;cursor:pointer;background:#fafbfc;padding:5px 10px;border-radius:8px;border:1px solid #e4e6eb">
            <input type="checkbox" class="plat-cb" value="X / Twitter"> X / Twitter
          </label>
          <label style="display:flex;align-items:center;gap:4px;font-size:.82rem;cursor:pointer;background:#fafbfc;padding:5px 10px;border-radius:8px;border:1px solid #e4e6eb">
            <input type="checkbox" class="plat-cb" value="Threads"> Threads
          </label>
        </div>
      </div>
      <button onclick="generateIdeas()"
        style="width:100%;background:linear-gradient(135deg,#7b1fa2,#5c6ac4);color:#fff;border:none;border-radius:9px;padding:10px;font-size:.86rem;font-weight:700;cursor:pointer">
        &#9889; Generate Ideas
      </button>
      <div id="ideas-status" style="margin-top:10px;font-size:.8rem;color:#606770"></div>
    </div>

    <!-- Strategy card -->
    <div style="background:#fff;border-radius:14px;border:1px solid #e9ebee;padding:24px">
      <h2 style="font-size:.95rem;font-weight:700;margin-bottom:12px">&#128197; Weekly Marketing Strategy</h2>
      <p style="font-size:.82rem;color:#606770;line-height:1.5;margin-bottom:14px">
        Full week content plan with topics, formats, timing, and engagement angles based on competitive research and your industry trends.
      </p>
      <p style="font-size:.8rem;color:#90949c;margin-bottom:14px;background:#fafbfc;padding:8px 12px;border-radius:8px">
        &#128204; Your niche is pulled from your client profile automatically.
      </p>
      <button onclick="generateStrategy()"
        style="width:100%;background:linear-gradient(135deg,#16a34a,#15803d);color:#fff;border:none;border-radius:9px;padding:10px;font-size:.86rem;font-weight:700;cursor:pointer">
        &#128200; Generate Weekly Strategy
      </button>
      <div id="strat-status" style="margin-top:10px;font-size:.8rem;color:#606770"></div>
    </div>
  </div>

  <!-- Ideas viewer pane (hidden until batch loaded) -->
  <div id="batch-view" style="display:none;background:#fff;border-radius:14px;border:1px solid #e9ebee;padding:26px;margin-bottom:28px">
    <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:16px">
      <h2 style="font-size:.95rem;font-weight:700" id="batch-title">Ideas</h2>
      <button onclick="document.getElementById('batch-view').style.display='none'"
        style="background:none;border:none;font-size:.85rem;color:#90949c;cursor:pointer">&#10005; Close</button>
    </div>
    <div id="batch-content"></div>
  </div>

  <!-- History table -->
  <div style="background:#fff;border-radius:14px;border:1px solid #e9ebee;overflow:hidden">
    <div style="padding:16px 22px 14px;border-bottom:1px solid #f0f2f5;display:flex;align-items:center;justify-content:space-between">
      <h2 style="font-size:.92rem;font-weight:700">&#128196; Research History</h2>
      <span style="font-size:.78rem;color:#90949c">{len(batches)} batches</span>
    </div>
    <table style="width:100%;border-collapse:collapse;font-size:.84rem">
      <tr style="background:#fafbfc">
        <th style="text-align:left;padding:10px 20px;font-size:.72rem;font-weight:700;color:#90949c;text-transform:uppercase">Date</th>
        <th style="text-align:left;padding:10px 12px;font-size:.72rem;font-weight:700;color:#90949c;text-transform:uppercase">Type</th>
        <th style="text-align:left;padding:10px 12px;font-size:.72rem;font-weight:700;color:#90949c;text-transform:uppercase">Niche</th>
        <th style="text-align:left;padding:10px 12px;font-size:.72rem;font-weight:700;color:#90949c;text-transform:uppercase">Platforms</th>
        <th style="text-align:left;padding:10px 12px;font-size:.72rem;font-weight:700;color:#90949c;text-transform:uppercase">Ideas</th>
        <th></th>
      </tr>
      {batch_rows}
    </table>
  </div>

</div>
"""
        return HTMLResponse(build_page(
            title="Marketing Intelligence",
            active_nav="intelligence",
            body_content=_body,
            extra_js="""
async function generateIdeas() {
  const status = document.getElementById('ideas-status');
  status.textContent = '⏳ Generating ideas...';
  const platforms = Array.from(document.querySelectorAll('.plat-cb:checked')).map(cb => cb.value);
  try {
    const r = await fetch('/api/intelligence/ideas', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({
        num_ideas: parseInt(document.getElementById('ideas-count').value),
        platforms: platforms.length ? platforms : null,
      })
    });
    const data = await r.json();
    if (data.ok) {
      status.textContent = '✓ ' + data.message;
      setTimeout(() => pollBatch(data.batch_id, 'ideas-status'), 20000);
    } else { status.textContent = '✗ ' + data.error; }
  } catch(e) { status.textContent = '✗ ' + e.message; }
}

async function generateStrategy() {
  const status = document.getElementById('strat-status');
  status.textContent = '⏳ Generating strategy...';
  try {
    const r = await fetch('/api/intelligence/strategy', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({})
    });
    const data = await r.json();
    if (data.ok) {
      status.textContent = '✓ ' + data.message;
      setTimeout(() => location.reload(), 65000);
    } else { status.textContent = '✗ ' + data.error; }
  } catch(e) { status.textContent = '✗ ' + e.message; }
}

async function pollBatch(batchId, statusId) {
  try {
    const r = await fetch('/api/intelligence/batch/' + batchId);
    const data = await r.json();
    if (data.status === 'generating') {
      document.getElementById(statusId).textContent = '⏳ Still generating...';
      setTimeout(() => pollBatch(batchId, statusId), 10000);
      return;
    }
    document.getElementById(statusId).textContent = '✓ Done! ' + (data.ideas||[]).length + ' ideas generated.';
    location.reload();
  } catch(e) {}
}

async function viewBatch(batchId) {
  const pane = document.getElementById('batch-view');
  const content = document.getElementById('batch-content');
  const title = document.getElementById('batch-title');
  content.innerHTML = '<p style="color:#90949c">Loading...</p>';
  pane.style.display = '';
  pane.scrollIntoView({behavior:'smooth'});

  try {
    const r = await fetch('/api/intelligence/batch/' + batchId);
    const data = await r.json();
    if (data.status === 'generating') {
      content.innerHTML = '<p style="color:#606770">Still generating... refresh in 30s.</p>';
      return;
    }
    title.textContent = (data.type === 'strategy' ? '📅 Weekly Strategy' : '💡 Content Ideas') + ' — ' + (data.niche || '');

    // Strategy view: show strategy metadata + ideas
    if (data.type === 'strategy') {
      let html = '';
      // Strategy header info
      const themes = data.themes || (data.strategy && data.strategy.themes) || [];
      const mix = data.content_mix || (data.strategy && data.strategy.content_mix) || {};
      const freq = data.posting_frequency || (data.strategy && data.strategy.posting_frequency) || '';
      const period = data.period || (data.strategy && data.strategy.period) || '';
      const notes = data.notes || (data.strategy && data.strategy.notes) || '';
      const startD = data.start_date || (data.strategy && data.strategy.start_date) || '';
      const endD = data.end_date || (data.strategy && data.strategy.end_date) || '';

      html += '<div style="background:linear-gradient(135deg,#e8eaf6,#f3e5f5);border-radius:10px;padding:16px 18px;margin-bottom:16px">';
      if (startD || endD) html += '<p style="font-size:.78rem;color:#606770;margin-bottom:6px">📅 ' + startD + ' → ' + endD + '</p>';
      if (freq) html += '<p style="font-size:.85rem;margin-bottom:4px"><strong>Posts/week:</strong> ' + freq + '</p>';
      if (themes.length) html += '<p style="font-size:.85rem;margin-bottom:4px"><strong>Themes:</strong> ' + themes.join(', ') + '</p>';
      if (Object.keys(mix).length) {
        const mixStr = Object.entries(mix).map(([k,v]) => k + ' ' + v + '%').join(', ');
        html += '<p style="font-size:.85rem;margin-bottom:4px"><strong>Content mix:</strong> ' + mixStr + '</p>';
      }
      if (notes) html += '<p style="font-size:.82rem;color:#444;line-height:1.5;margin-top:8px">' + notes + '</p>';
      html += '</div>';

      // Strategy ideas
      const ideas = data.ideas || (data.strategy && data.strategy.ideas) || [];
      if (ideas.length) {
        html += '<h3 style="font-size:.92rem;font-weight:700;margin-bottom:10px">📝 Content Ideas (' + ideas.length + ')</h3>';
        html += ideas.map((idea, i) => {
          const t = idea.topic || idea.title || ('Idea ' + (i+1));
          const angle = idea.angle || idea.description || idea.hook || '';
          const plats = (idea.recommended_platforms || []).join(', ') || idea.platform || '';
          const fmt = idea.format || idea.content_format || '';
          const pri = idea.priority || '';
          const hooks = (idea.hooks || []).slice(0,2);
          const kw = (idea.keywords || []).slice(0,5);
          return `<div style="background:#fafbfc;border:1px solid #e9ebee;border-radius:10px;padding:14px 16px;margin-bottom:12px">
            <div style="display:flex;align-items:flex-start;justify-content:space-between;gap:8px;margin-bottom:6px">
              <strong style="font-size:.88rem;color:#1c1e21">${t}</strong>
              <div style="display:flex;gap:6px;flex-shrink:0;flex-wrap:wrap">
                ${plats ? `<span style="background:#e8eaf6;color:#3949ab;border-radius:99px;padding:1px 8px;font-size:.72rem;font-weight:600">${plats}</span>` : ''}
                ${fmt ? `<span style="background:#f3e5f5;color:#7b1fa2;border-radius:99px;padding:1px 8px;font-size:.72rem;font-weight:600">${fmt}</span>` : ''}
                ${pri ? `<span style="background:${pri==='high'?'#fce4ec':'#e8f5e9'};color:${pri==='high'?'#c62828':'#2e7d32'};border-radius:99px;padding:1px 8px;font-size:.72rem;font-weight:600">${pri}</span>` : ''}
              </div>
            </div>
            ${angle ? `<p style="font-size:.82rem;color:#444;line-height:1.5;margin:0 0 6px">${angle}</p>` : ''}
            ${hooks.length ? `<p style="font-size:.78rem;color:#606770;margin:0"><strong>Hooks:</strong> ${hooks.join(' | ')}</p>` : ''}
            ${kw.length ? `<p style="font-size:.75rem;color:#90949c;margin:4px 0 0">🏷️ ${kw.join(', ')}</p>` : ''}
          </div>`;
        }).join('');
      } else {
        html += '<p style="color:#90949c;font-size:.85rem">Strategy generated — no individual ideas were returned.</p>';
      }
      content.innerHTML = html;
      return;
    }

    // Ideas view
    const ideas = data.ideas || [];
    if (!ideas.length) { content.innerHTML = '<p>No ideas found in this batch.</p>'; return; }
    content.innerHTML = ideas.map((idea, i) => {
      const title_text = idea.title || idea.topic || ('Idea ' + (i+1));
      const desc = idea.description || idea.hook || idea.content_angle || idea.angle || '';
      const platform = (idea.recommended_platforms || []).join(', ') || idea.platform || '';
      const format = idea.content_format || idea.format || '';
      const priority = idea.priority || idea.score || '';
      return `<div style="background:#fafbfc;border:1px solid #e9ebee;border-radius:10px;padding:14px 16px;margin-bottom:12px">
        <div style="display:flex;align-items:flex-start;justify-content:space-between;gap:8px;margin-bottom:6px">
          <strong style="font-size:.88rem;color:#1c1e21">${title_text}</strong>
          <div style="display:flex;gap:6px;flex-shrink:0;flex-wrap:wrap">
            ${platform ? `<span style="background:#e8eaf6;color:#3949ab;border-radius:99px;padding:1px 8px;font-size:.72rem;font-weight:600">${platform}</span>` : ''}
            ${format ? `<span style="background:#f3e5f5;color:#7b1fa2;border-radius:99px;padding:1px 8px;font-size:.72rem;font-weight:600">${format}</span>` : ''}
          </div>
        </div>
        ${desc ? `<p style="font-size:.82rem;color:#444;line-height:1.5;margin:0">${desc}</p>` : ''}
      </div>`;
    }).join('');
  } catch(e) { content.innerHTML = '<p style="color:#c62828">Error: ' + e.message + '</p>'; }
}
""",
            user_name=user.full_name,
            business_name=profile.business_name,
        ))
    finally:
        db.close()
