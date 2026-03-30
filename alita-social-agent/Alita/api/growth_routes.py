"""
api/growth_routes.py
====================
Client Growth Intelligence dashboard — connects GrowthHackingAgent to the portal.

Routes
------
GET  /growth/dashboard              — Main growth dashboard (HTML)
POST /api/growth/generate-report    — Run GrowthHackingAgent and save report (JSON)
GET  /api/growth/reports            — List past reports for current client (JSON)
GET  /growth/report/{report_id}     — View a specific growth hacking report (HTML)
"""

import json
import logging
import os
import sys
import uuid

from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from database.db import get_db
from utils.shared_layout import build_page, get_user_context
from utils.plan_limits import check_limit, increment_usage

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Growth"])

REPORTS_DIR = Path("storage") / "growth_reports"     # legacy fallback

# ──────────────────────────────────────────────────────────────────────────────
# Storage helpers — PostgreSQL-backed (survives Railway redeploys)
# ──────────────────────────────────────────────────────────────────────────────

def _save_report_to_db(report_id: str, client_id: str, goal: str, strategy: dict):
    """Persist a growth report to PostgreSQL with retry + filesystem fallback.

    This is the ONLY canonical save path so reports survive Railway redeploys.
    On failure it:
      1. Retries the DB save once after a short pause
      2. Falls back to a local JSON file (non-ephemeral backup)
      3. Logs the failure loudly
    """
    import time
    from database.models import GrowthReport

    report_json = json.dumps(strategy, default=str, ensure_ascii=False)

    for attempt in (1, 2):
        db = None
        try:
            db = next(get_db())
            existing = db.query(GrowthReport).filter(GrowthReport.id == report_id).first()
            if existing:
                existing.report_json = report_json
                existing.goal = goal
            else:
                row = GrowthReport(
                    id=report_id,
                    client_id=client_id,
                    goal=goal,
                    report_json=report_json,
                    created_at=datetime.utcnow(),
                )
                db.add(row)
            db.commit()
            logger.info(f"[DB] Growth report {report_id} saved to PostgreSQL (attempt {attempt})")
            return  # success
        except Exception as exc:
            logger.error(f"[DB] Growth report save attempt {attempt} failed: {exc}")
            if db:
                try:
                    db.rollback()
                except Exception:
                    pass
            if attempt == 1:
                time.sleep(1)   # brief pause before retry
        finally:
            if db:
                try:
                    db.close()
                except Exception:
                    pass

    # ── Both DB attempts failed — write filesystem emergency backup ───────
    try:
        _emergency_save_dir = Path("storage") / "report_recovery" / client_id
        _emergency_save_dir.mkdir(parents=True, exist_ok=True)
        _emergency_file = _emergency_save_dir / f"{report_id}.json"
        with open(_emergency_file, "w", encoding="utf-8") as f:
            json.dump({
                "report_id": report_id,
                "client_id": client_id,
                "goal": goal,
                "strategy": strategy,
                "saved_at": datetime.utcnow().isoformat(),
                "reason": "db_save_failed",
            }, f, indent=2, default=str, ensure_ascii=False)
        logger.warning(f"[DB] Emergency filesystem backup → {_emergency_file}")
    except Exception as fe:
        logger.critical(f"[DB] BOTH DB and filesystem save failed for report {report_id}: {fe}")


def _reports_for(client_id: str, db=None) -> list:
    """Return sorted list of report metadata dicts (newest first).

    If *db* is provided the caller's session is reused (avoids opening a
    second connection that can exhaust small connection pools).
    """
    from database.models import GrowthReport
    _own_db = db is None
    try:
        if _own_db:
            db = next(get_db())
        rows = (
            db.query(GrowthReport)
            .filter(GrowthReport.client_id == client_id)
            .order_by(GrowthReport.created_at.desc())
            .all()
        )
        items = []
        for row in rows:
            try:
                data = json.loads(row.report_json)
            except Exception:
                data = {}
            items.append({
                "report_id": row.id,
                "created_at": row.created_at.isoformat() if row.created_at else "",
                "goal": row.goal or "",
                "positioning_angle": data.get("positioning_angle", ""),
                "quick_wins_count": len(data.get("quick_wins", [])),
            })
        return items
    except Exception as exc:
        logger.error(f"[DB] _reports_for failed: {exc}")
        return _reports_for_legacy(client_id)
    finally:
        if _own_db and db:
            db.close()


def _reports_for_legacy(client_id: str) -> list:
    """Fallback — read from filesystem (for old reports saved before DB migration)."""
    d = REPORTS_DIR / client_id
    if not d.exists():
        return []
    items = []
    for f in sorted(d.glob("*.json"), reverse=True):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            items.append({
                "report_id": data.get("report_id", f.stem),
                "created_at": data.get("created_at", ""),
                "goal": data.get("goal", ""),
                "positioning_angle": data.get("positioning_angle", ""),
                "quick_wins_count": len(data.get("quick_wins", [])),
            })
        except Exception:
            pass
    return items


def _load_report(client_id: str, report_id: str, db=None) -> dict | None:
    """Load a full report from PostgreSQL (with filesystem fallback).

    If *db* is provided the caller's session is reused (avoids opening a
    second connection that can exhaust small connection pools).
    """
    from database.models import GrowthReport
    _own_db = db is None
    try:
        if _own_db:
            db = next(get_db())
        row = (
            db.query(GrowthReport)
            .filter(GrowthReport.client_id == client_id, GrowthReport.id == report_id)
            .first()
        )
        if row:
            return json.loads(row.report_json)
    except Exception as exc:
        logger.error(f"[DB] _load_report failed: {exc}")
    finally:
        if _own_db and db:
            db.close()
    # Legacy fallback — filesystem
    d = REPORTS_DIR / client_id
    if not d.exists():
        return None
    for f in d.glob("*.json"):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            if data.get("report_id") == report_id:
                return data
        except Exception:
            pass
    return None


# ──────────────────────────────────────────────────────────────────────────────
# Background report generation (runs after API returns 202)
# ──────────────────────────────────────────────────────────────────────────────

def _run_report(client_id: str, profile_data: dict, report_id: str):
    """Sync wrapper — FastAPI runs sync BackgroundTasks in a thread pool,
    keeping the main event loop free."""
    from utils.agent_executor import run_agent_in_background
    run_agent_in_background(_run_report_async(client_id, profile_data, report_id))


async def _run_report_async(client_id: str, profile_data: dict, report_id: str):
    """Actual async work — runs GrowthHackingAgent and saves result."""
    try:
        from agents.growth_hacking_agent import GrowthHackingAgent
        from utils.notification_manager import NotificationManager

        agent = GrowthHackingAgent(client_id=client_id, tier=profile_data.get("plan_tier", "pro"))
        notifier = NotificationManager(client_id=client_id)

        # Get connected platforms so agent only recommends actionable tactics
        from utils.connected_platforms import get_connected_platforms
        _platforms = get_connected_platforms(client_id)

        strategy = await agent.generate_strategy(
            business_type=profile_data.get("business_type", "coaching / consulting"),
            current_situation=profile_data.get("current_situation", "Building presence online"),
            goal=profile_data.get("goal", "Grow audience and generate leads"),
            budget=profile_data.get("budget", "low"),
            timeline=profile_data.get("timeline", "90 days"),
            niche=profile_data.get("niche"),
            target_audience=profile_data.get("target_audience"),
            current_online_presence=profile_data.get("current_online_presence"),
            connected_platforms=_platforms,
        )

        # Attach metadata and save to PostgreSQL
        strategy["report_id"]  = report_id
        strategy["client_id"]  = client_id
        strategy["created_at"] = datetime.now().isoformat()
        strategy["goal"]       = profile_data.get("goal", "")

        _save_report_to_db(report_id, client_id, strategy.get("goal", ""), strategy)

        # ── Increment usage quota only AFTER successful save ──────────────────
        try:
            _quota_db = next(get_db())
            try:
                from database.models import ClientProfile as _CP
                _prof = _quota_db.query(_CP).filter(_CP.client_id == client_id).first()
                if _prof:
                    increment_usage(_prof, "growth_strategy", _quota_db)
            finally:
                _quota_db.close()
        except Exception as qe:
            logger.warning(f"[{client_id}] quota increment failed (non-fatal): {qe}")

        # ── Fire notifications for top quick wins ─────────────────────────────
        quick_wins = strategy.get("quick_wins") or []
        for i, tactic in enumerate(quick_wins[:2]):
            notif_type = "content_idea" if i == 0 else "growth_tip"
            impact = tactic.get("expected_impact", "medium")
            prio = "high" if impact in ("high", "massive") else "medium"
            await notifier.send_growth_notification(
                notification_type=notif_type,
                title=f"Growth Hack: {tactic.get('title', 'New Tactic')}",
                message=tactic.get("description", tactic.get("why_it_works", "")),
                priority=prio,
                action_url=f"/growth/report/{report_id}",
                action_label="View Full Report",
                action_type="internal_link",
                extra_meta={"report_id": report_id},
            )

        print(f"✅ Growth report {report_id} saved for {client_id}")

    except Exception as exc:
        print(f"❌ Growth report generation failed: {exc}")
        import traceback; traceback.print_exc()


# ──────────────────────────────────────────────────────────────────────────────
# JSON API
# ──────────────────────────────────────────────────────────────────────────────

@router.post("/api/growth/generate-report")
async def api_generate_report(request: Request, background_tasks: BackgroundTasks):
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

        # Build profile_data from stored profile + optional overrides from request
        profile_data = {
            "business_type": body.get("business_type") or profile.niche or "Coaching / Consulting",
            "niche":         body.get("niche")         or profile.niche,
            "target_audience": body.get("target_audience") or getattr(profile, "target_market_description", None),
            "current_situation": body.get("current_situation") or "Building & growing online presence",
            "goal":          body.get("goal")          or "Grow audience and generate qualified leads",
            "budget":        body.get("budget", "low"),
            "timeline":      body.get("timeline", "90 days"),
            "current_online_presence": body.get("current_online_presence") or getattr(profile, "website_url", None),
            "plan_tier": getattr(profile, "plan_tier", "pro") or "pro",
        }

        # ── Plan gate ──────────────────────────────────────────────────────────
        allowed, msg = check_limit(profile, "growth_strategy")
        if not allowed:
            return JSONResponse({"error": msg, "upgrade_url": "/billing"}, status_code=402)
        # NOTE: increment_usage is called INSIDE _run_report_async AFTER
        # the report is confirmed saved to DB — so quota is only consumed
        # when the report actually exists.

        report_id = uuid.uuid4().hex[:12]
        background_tasks.add_task(_run_report, profile.client_id, profile_data, report_id)

        return JSONResponse({
            "ok": True,
            "report_id": report_id,
            "status": "generating",
            "message": "Your growth report is being generated. This takes 30–60 seconds. Check back shortly.",
            "poll_url": f"/api/growth/reports",
            "view_url": f"/growth/report/{report_id}",
        })
    finally:
        db.close()


@router.get("/api/growth/reports")
async def api_list_reports(request: Request):
    db = next(get_db())
    try:
        user, profile = get_user_context(request, db)
        if not user:
            return JSONResponse({"error": "Unauthorized"}, status_code=401)
        if not profile:
            return JSONResponse({"reports": []})
        reports = _reports_for(profile.client_id)
        return JSONResponse({"reports": reports})
    finally:
        db.close()


# ──────────────────────────────────────────────────────────────────────────────
# GrowthAgent — targeting / follow / engagement campaigns
# ──────────────────────────────────────────────────────────────────────────────

CAMPAIGNS_DIR = Path("storage") / "growth_campaigns"  # legacy fallback


def _save_campaign_to_db(run_id: str, client_id: str, platform: str, dry_run: bool, result: dict):
    """Persist a campaign run to PostgreSQL."""
    from database.models import GrowthCampaignRun
    db = None
    try:
        db = next(get_db())
        row = GrowthCampaignRun(
            id=run_id,
            client_id=client_id,
            platform=platform,
            dry_run=dry_run,
            result_json=json.dumps(result, default=str, ensure_ascii=False),
            created_at=datetime.utcnow(),
        )
        db.add(row)
        db.commit()
        print(f"[DB] Campaign run {run_id} saved to PostgreSQL")
    except Exception as exc:
        print(f"[DB] Failed to save campaign {run_id}: {exc}")
        if db:
            db.rollback()
    finally:
        if db:
            db.close()


def _campaigns_for(client_id: str) -> list:
    """Return list of past campaign runs (newest first) from PostgreSQL."""
    from database.models import GrowthCampaignRun
    db = None
    try:
        db = next(get_db())
        rows = (
            db.query(GrowthCampaignRun)
            .filter(GrowthCampaignRun.client_id == client_id)
            .order_by(GrowthCampaignRun.created_at.desc())
            .limit(20)
            .all()
        )
        runs = []
        for row in rows:
            try:
                data = json.loads(row.result_json)
            except Exception:
                data = {}
            data["run_id"] = row.id
            data["client_id"] = row.client_id
            data["platform"] = row.platform
            data["dry_run"] = row.dry_run
            data["created_at"] = row.created_at.isoformat() if row.created_at else ""
            runs.append(data)
        return runs
    except Exception as exc:
        print(f"[DB] _campaigns_for failed, falling back to filesystem: {exc}")
        return _campaigns_for_legacy(client_id)
    finally:
        if db:
            db.close()


def _campaigns_for_legacy(client_id: str) -> list:
    """Fallback — read from filesystem (for old campaign runs before DB migration)."""
    d = CAMPAIGNS_DIR / client_id
    if not d.exists():
        return []
    runs = []
    for f in sorted(d.glob("run_*.json"), reverse=True)[:20]:
        try:
            data = json.loads(f.read_text())
            runs.append(data)
        except Exception:
            pass
    return runs


def _bg_run_growth_campaign(client_id: str, run_id: str, params: dict):
    """Sync wrapper — FastAPI runs sync BackgroundTasks in a thread pool."""
    from utils.agent_executor import run_agent_in_background
    run_agent_in_background(_bg_run_growth_campaign_async(client_id, run_id, params))


async def _bg_run_growth_campaign_async(client_id: str, run_id: str, params: dict):
    """Actual async work — runs GrowthAgent.run_growth_campaign() and saves result."""
    try:
        from agents.growth_agent import GrowthAgent

        agent = GrowthAgent(client_id=client_id)
        result = await agent.run_growth_campaign(
            platform=params.get("platform", "instagram"),
            max_follows=int(params.get("max_follows", 10)),
            max_engagements=int(params.get("max_engagements", 20)),
            dry_run=bool(params.get("dry_run", True)),
        )

        output = {
            "run_id":      run_id,
            "client_id":   client_id,
            "created_at":  datetime.utcnow().isoformat(),
            "platform":    params.get("platform", "instagram"),
            "dry_run":     bool(params.get("dry_run", True)),
            "result":      result if isinstance(result, dict) else {"raw": str(result)},
        }
        _save_campaign_to_db(run_id, client_id, params.get("platform", "instagram"),
                             bool(params.get("dry_run", True)), output)

        # Fire notification
        try:
            import importlib
            nm_mod = importlib.import_module("utils.notification_manager")
            NotificationManager = getattr(nm_mod, "NotificationManager", None)
            if NotificationManager:
                nm = NotificationManager(client_id)
                await nm.send_notification(
                    notification_type="growth_tip",
                    title="Growth Campaign Complete ✅",
                    message=f"Targeting run on {params.get('platform','instagram')} finished. Check your campaign log.",
                    priority="normal",
                    action_url="/growth/dashboard",
                    action_label="View Log",
                )
        except Exception:
            pass

    except Exception as exc:
        logger.error(f"[{client_id}] growth_campaign failed: {exc}", exc_info=True)
        output = {
            "run_id":    run_id,
            "client_id": client_id,
            "created_at": datetime.utcnow().isoformat(),
            "error":     str(exc),
        }
        _save_campaign_to_db(run_id, client_id, params.get("platform", "instagram"),
                             bool(params.get("dry_run", True)), output)


@router.post("/api/growth/run-campaign")
async def api_run_growth_campaign(request: Request, background_tasks: BackgroundTasks):
    """Launch a GrowthAgent targeting / follow campaign (runs in background)."""
    db = next(get_db())
    try:
        user, profile = get_user_context(request, db)
        if not user:
            return JSONResponse({"error": "Unauthorized"}, status_code=401)
        if not profile:
            return JSONResponse({"error": "No profile found"}, status_code=400)

        body: dict = {}
        try:
            body = await request.json()
        except Exception:
            pass

        run_id = uuid.uuid4().hex[:12]
        background_tasks.add_task(_bg_run_growth_campaign, profile.client_id, run_id, body)
        return JSONResponse({
            "ok":      True,
            "run_id":  run_id,
            "message": f"Growth campaign started on {body.get('platform','instagram')}. Results saved when complete.",
            "poll_url": "/api/growth/campaign-log",
        })
    finally:
        db.close()


@router.get("/api/growth/campaign-log")
async def api_campaign_log(request: Request):
    """Return list of past GrowthAgent campaign runs for the current client."""
    db = next(get_db())
    try:
        user, profile = get_user_context(request, db)
        if not user:
            return JSONResponse({"error": "Unauthorized"}, status_code=401)
        if not profile:
            return JSONResponse({"campaigns": []})
        campaigns = _campaigns_for(profile.client_id)
        return JSONResponse({"campaigns": campaigns})
    finally:
        db.close()


# ──────────────────────────────────────────────────────────────────────────────
# HTML pages
# ──────────────────────────────────────────────────────────────────────────────

@router.get("/growth/dashboard", response_class=HTMLResponse)
async def growth_dashboard(request: Request):
    db = next(get_db())
    try:
        user, profile = get_user_context(request, db)
        if not user:
            return RedirectResponse("/account/login", status_code=303)
        if not profile:
            return RedirectResponse("/onboarding", status_code=303)

        reports     = _reports_for(profile.client_id, db=db)
        report_rows = ""
        if reports:
            for r in reports[:10]:
                ts = r["created_at"][:10] if r.get("created_at") else "—"
                angle_snippet = (r["positioning_angle"][:90] + "…") if len(r.get("positioning_angle","")) > 90 else r.get("positioning_angle","")
                report_rows += f"""
                <tr>
                  <td style="font-size:.82rem;color:#90949c">{ts}</td>
                  <td>{r.get("goal","")}</td>
                  <td style="color:#606770;font-size:.82rem">{angle_snippet}</td>
                  <td><span style="background:#e8f5e9;color:#2e7d32;border-radius:99px;padding:2px 10px;font-size:.75rem;font-weight:700">{r["quick_wins_count"]} tactics</span></td>
                  <td><a href="/growth/report/{r['report_id']}" style="color:#5c6ac4;font-weight:700;font-size:.82rem">View Report &#8594;</a></td>
                </tr>"""
        else:
            report_rows = "<tr><td colspan='5' style='text-align:center;padding:32px;color:#90949c'>No reports yet. Generate your first one above.</td></tr>"

        _body = f"""
  <div class="gr-page">

    <!-- Page header -->
    <div style="margin-bottom:28px">
      <h1 style="font-size:1.5rem;font-weight:800;margin-bottom:6px">&#128640; Growth Intelligence</h1>
      <p style="font-size:.88rem;color:#606770;max-width:560px">
        AI-generated growth hacking reports tailored to your business. Every report delivers tactics 99&#37; of marketers would never think of — from press hacking to perception engineering.
      </p>
    </div>

    <!-- Generate card -->
    <div style="background:#fff;border-radius:14px;box-shadow:0 1px 4px rgba(0,0,0,.06);padding:28px;margin-bottom:28px;border:1px solid #e9ebee">
      <div style="display:flex;align-items:flex-start;justify-content:space-between;flex-wrap:wrap;gap:16px">
        <div>
          <h2 style="font-size:1.05rem;font-weight:700;margin-bottom:6px">&#129504; Generate Growth Hacking Report</h2>
          <p style="font-size:.84rem;color:#606770;max-width:520px;line-height:1.5">
            Describe your goal below and Alita AI will generate a fully custom strategy — quick wins you can execute today, medium-term plays, and long-term compound tactics.
          </p>
        </div>
        <button id="gen-btn" onclick="generateReport()" style="background:linear-gradient(135deg,#5c6ac4,#764ba2);color:#fff;border:none;border-radius:10px;padding:12px 24px;font-size:.9rem;font-weight:700;cursor:pointer;white-space:nowrap;flex-shrink:0">
          &#9889; Generate Report
        </button>
      </div>

      <div style="display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-top:20px" id="gen-form">
        <div>
          <label style="font-size:.78rem;font-weight:600;color:#444;display:block;margin-bottom:5px">What's your goal? *</label>
          <select id="f-goal" style="width:100%;padding:9px 12px;border:1px solid #dde0e4;border-radius:8px;font-size:.85rem;color:#1c1e21;outline:none;background:#fff">
            <option value="Grow my audience">Grow my audience</option>
            <option value="Get more leads" selected>Get more leads</option>
            <option value="Increase sales">Increase sales</option>
            <option value="Build brand awareness">Build brand awareness</option>
            <option value="Launch a new product or service">Launch a new product or service</option>
            <option value="Improve engagement">Improve engagement</option>
            <option value="Expand into a new market">Expand into a new market</option>
          </select>
        </div>
        <div>
          <label style="font-size:.78rem;font-weight:600;color:#444;display:block;margin-bottom:5px">Where are you right now?</label>
          <select id="f-situation" style="width:100%;padding:9px 12px;border:1px solid #dde0e4;border-radius:8px;font-size:.85rem;color:#1c1e21;outline:none;background:#fff">
            <option value="Just getting started">Just getting started</option>
            <option value="Have some followers but need growth" selected>Have some followers but need growth</option>
            <option value="Established but plateauing">Established but plateauing</option>
            <option value="Growing fast, need to scale">Growing fast, need to scale</option>
            <option value="Rebranding or pivoting">Rebranding or pivoting</option>
          </select>
        </div>
        <div>
          <label style="font-size:.78rem;font-weight:600;color:#444;display:block;margin-bottom:5px">Budget</label>
          <select id="f-budget" style="width:100%;padding:9px 12px;border:1px solid #dde0e4;border-radius:8px;font-size:.85rem;color:#1c1e21;outline:none;background:#fff">
            <option value="bootstrap">Bootstrap ($0)</option>
            <option value="low" selected>Low ($0–$200/mo)</option>
            <option value="medium">Medium ($200–$1,000/mo)</option>
            <option value="growth">Growth ($1,000+/mo)</option>
          </select>
        </div>
        <div>
          <label style="font-size:.78rem;font-weight:600;color:#444;display:block;margin-bottom:5px">Timeline</label>
          <select id="f-timeline" style="width:100%;padding:9px 12px;border:1px solid #dde0e4;border-radius:8px;font-size:.85rem;color:#1c1e21;outline:none;background:#fff">
            <option value="30 days">30 Days</option>
            <option value="90 days" selected>90 Days</option>
            <option value="6 months">6 Months</option>
          </select>
        </div>
      </div>

      <div id="gen-status" style="display:none;margin-top:16px;padding:14px 18px;border-radius:10px;font-size:.85rem;font-weight:500"></div>
    </div>

    <!-- Past reports table -->
    <div style="background:#fff;border-radius:14px;box-shadow:0 1px 4px rgba(0,0,0,.06);overflow:hidden;border:1px solid #e9ebee">
      <div style="padding:18px 24px 14px;border-bottom:1px solid #f0f2f5;display:flex;align-items:center;justify-content:space-between">
        <h2 style="font-size:.95rem;font-weight:700">&#128196; Past Reports</h2>
        <span style="font-size:.8rem;color:#90949c">{len(reports)} total</span>
      </div>
      <table style="width:100%;border-collapse:collapse;font-size:.85rem">
        <tr style="background:#fafbfc">
          <th style="text-align:left;padding:10px 24px;font-size:.74rem;font-weight:700;color:#90949c;text-transform:uppercase;letter-spacing:.04em">Date</th>
          <th style="text-align:left;padding:10px 16px;font-size:.74rem;font-weight:700;color:#90949c;text-transform:uppercase;letter-spacing:.04em">Goal</th>
          <th style="text-align:left;padding:10px 16px;font-size:.74rem;font-weight:700;color:#90949c;text-transform:uppercase;letter-spacing:.04em">Positioning Angle</th>
          <th style="text-align:left;padding:10px 16px;font-size:.74rem;font-weight:700;color:#90949c;text-transform:uppercase;letter-spacing:.04em">Tactics</th>
          <th style="text-align:left;padding:10px 16px;font-size:.74rem;font-weight:700;color:#90949c;text-transform:uppercase;letter-spacing:.04em"></th>
        </tr>
        {report_rows}
      </table>
    </div>

  </div>
"""
        return HTMLResponse(build_page(
            title="Growth Intelligence",
            active_nav="social",
            body_content=_body,
            extra_css="""
    .gr-page{max-width:960px;margin:0 auto;padding:0}
    @media(max-width:700px){
      #gen-form{grid-template-columns:1fr !important}
    }
""",
            extra_js="""
async function generateReport() {
  const btn = document.getElementById('gen-btn');
  const status = document.getElementById('gen-status');
  const goal      = document.getElementById('f-goal').value;
  const situation = document.getElementById('f-situation').value;
  const niche     = document.getElementById('f-niche') ? document.getElementById('f-niche').value : '';
  const budget    = document.getElementById('f-budget').value;
  const timeline  = document.getElementById('f-timeline').value;

  btn.disabled = true;
  btn.textContent = '⏳ Generating...';
  status.style.display = 'block';
  status.style.background = '#ede8f5';
  status.style.color = '#5c6ac4';
  status.innerHTML = '&#129504; Alita AI is crafting your custom growth hacking report. This usually takes 30–60 seconds…';

  try {
    const r = await fetch('/api/growth/generate-report', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({goal, current_situation: situation, budget, timeline, niche})
    });
    const data = await r.json();
    if (data.ok) {
      status.style.background = '#f0fdf4';
      status.style.color = '#2e7d32';
      status.innerHTML = '&#10003; Report is generating! You\\'ll get a notification when it\\'s ready. <a href="/growth/report/' + data.report_id + '" style="color:#5c6ac4;font-weight:700">Check status &#8594;</a>';
      btn.textContent = '&#9889; Generate Another Report';
      btn.disabled = false;
      // Poll for completion and refresh list
      setTimeout(() => location.reload(), 65000);
    } else {
      throw new Error(data.error || 'Unknown error');
    }
  } catch(e) {
    status.style.background = '#fce4ec';
    status.style.color = '#c62828';
    status.innerHTML = '&#10007; Error: ' + e.message;
    btn.disabled = false;
    btn.textContent = '&#9889; Generate Report';
  }
}
""",
            user_name=user.full_name,
            business_name=profile.business_name,
        ))
    finally:
        db.close()


# ──────────────────────────────────────────────────────────────────────────────
# Report viewer
# ──────────────────────────────────────────────────────────────────────────────

@router.get("/growth/report/{report_id}", response_class=HTMLResponse)
async def growth_report_view(request: Request, report_id: str):
    db = next(get_db())
    try:
        user, profile = get_user_context(request, db)
        if not user:
            return RedirectResponse("/account/login", status_code=303)
        if not profile:
            return RedirectResponse("/onboarding", status_code=303)

        logger.info(f"[{profile.client_id}] Loading report {report_id}")
        report = _load_report(profile.client_id, report_id, db=db)
        logger.info(f"[{profile.client_id}] _load_report returned: {'dict' if report else 'None'}")

        # ── Check if report_id exists at all (any client) ─────────────
        # If the row exists for this client but JSON parsing failed,
        # _load_report already logged the error.  If it doesn't exist
        # for *any* client, it was never created → show "not found".
        _report_pending = False
        if not report:
            from database.models import GrowthReport as _GR
            try:
                _row = db.query(_GR.id).filter(_GR.id == report_id).first()
                _report_pending = _row is not None   # row exists → still generating or parse error
            except Exception:
                pass

        if not report and _report_pending:
            _body = f"""
  <div style="max-width:720px;margin:60px auto;text-align:center">
    <div style="font-size:2.5rem;margin-bottom:16px">&#9203;</div>
    <h2 style="font-size:1.2rem;font-weight:700;margin-bottom:10px">Report is being generated…</h2>
    <p style="font-size:.88rem;color:#606770;margin-bottom:20px">
      Alita AI is researching and crafting your custom growth strategy. This typically takes 30–60 seconds.
    </p>
    <p style="font-size:.82rem;color:#90949c">This page will refresh automatically.</p>
    <script>setTimeout(() => location.reload(), 8000);</script>
  </div>"""
            return HTMLResponse(build_page(
                title="Generating Report…", active_nav="social",
                body_content=_body, user_name=user.full_name, business_name=profile.business_name,
            ))
        elif not report:
            _body = f"""
  <div style="max-width:720px;margin:60px auto;text-align:center">
    <div style="font-size:2.5rem;margin-bottom:16px">&#128683;</div>
    <h2 style="font-size:1.2rem;font-weight:700;margin-bottom:10px">Report Not Found</h2>
    <p style="font-size:.88rem;color:#606770;margin-bottom:20px">
      This report doesn't exist or may have been removed.
    </p>
    <a href="/growth/dashboard" style="color:#5c6ac4;font-weight:700;font-size:.88rem">&#8592; Back to Growth Dashboard</a>
  </div>"""
            return HTMLResponse(build_page(
                title="Report Not Found", active_nav="social",
                body_content=_body, user_name=user.full_name, business_name=profile.business_name,
            ))

        # Render report
        def _tactic_card(t: dict, badge_color: str = "#5c6ac4") -> str:
            difficulty_map = {"easy": "#2e7d32", "medium": "#e65100", "hard": "#c62828"}
            impact_map = {"low": "#90949c", "medium": "#2563eb", "high": "#e65100", "massive": "#c62828"}
            steps_html = ""
            for step in (t.get("step_by_step") or t.get("how") or []):
                steps_html += f"<li style='margin-bottom:6px;font-size:.82rem;color:#1c1e21'>{step}</li>"
            tools = ", ".join(t.get("tools_needed") or t.get("tools") or [])
            diff_color = difficulty_map.get(t.get("difficulty","medium"), "#2563eb")
            imp_color  = impact_map.get(t.get("expected_impact", t.get("impact","medium")), "#2563eb")

            return f"""
            <div style="background:#fff;border-radius:12px;border:1px solid #e9ebee;padding:22px 24px;margin-bottom:16px">
              <div style="display:flex;align-items:flex-start;justify-content:space-between;flex-wrap:wrap;gap:8px;margin-bottom:10px">
                <h3 style="font-size:.95rem;font-weight:700;color:#1c1e21">{t.get("title","Tactic")}</h3>
                <div style="display:flex;gap:7px;flex-wrap:wrap">
                  <span style="font-size:.72rem;font-weight:700;color:{diff_color};background:{diff_color}18;border-radius:99px;padding:2px 9px">{str(t.get("difficulty","")).title()}</span>
                  <span style="font-size:.72rem;font-weight:700;color:{imp_color};background:{imp_color}18;border-radius:99px;padding:2px 9px">{str(t.get("expected_impact",t.get("impact",""))).title()} Impact</span>
                  <span style="font-size:.72rem;font-weight:600;color:#606770;background:#f0f2f5;border-radius:99px;padding:2px 9px">{t.get("cost","")}</span>
                  <span style="font-size:.72rem;font-weight:600;color:#606770;background:#f0f2f5;border-radius:99px;padding:2px 9px">{t.get("time_investment","")}</span>
                </div>
              </div>
              <p style="font-size:.84rem;color:#444;line-height:1.55;margin-bottom:12px">{t.get("description") or t.get("why_it_works","")}</p>
              {"<ol style='padding-left:20px;margin-bottom:12px'>" + steps_html + "</ol>" if steps_html else ""}
              {"<p style='font-size:.78rem;color:#90949c;font-style:italic'><strong>Timeline to results:</strong> " + str(t.get("timeline_to_results","")) + "</p>" if t.get("timeline_to_results") else ""}
              {"<p style='font-size:.78rem;color:#5c6ac4;margin-top:6px'><strong>Tools:</strong> " + tools + "</p>" if tools else ""}
            </div>"""

        def _section(title: str, icon: str, tactics: list, color: str) -> str:
            if not tactics:
                return ""
            cards = "".join(_tactic_card(t, color) for t in tactics)
            return f"""
            <div style="margin-bottom:36px">
              <h2 style="font-size:1.05rem;font-weight:800;margin-bottom:16px;display:flex;align-items:center;gap:8px">
                <span style="width:36px;height:36px;border-radius:50%;background:{color}18;display:inline-flex;align-items:center;justify-content:center;font-size:1rem">{icon}</span>
                <span style="color:{color}">{title}</span>
              </h2>
              {cards}
            </div>"""

        try:
            ts_display = report.get("created_at","")[:10]
            pos_angle  = report.get("positioning_angle","")
            authority  = report.get("authority_narrative","")
            warnings   = report.get("important_warnings") or report.get("warnings") or []
            warnings_html = ""
            if warnings:
                items = "".join(f"<li style='font-size:.84rem;color:#b45309;margin-bottom:5px'>{w}</li>" for w in warnings)
                warnings_html = f"<div style='background:#fff7ed;border:1px solid #fed7aa;border-radius:10px;padding:16px 20px;margin-bottom:24px'><strong style='color:#92400e;font-size:.85rem'>&#9888; Important Warnings</strong><ul style='padding-left:18px;margin-top:8px'>{items}</ul></div>"

            _body = f"""
  <div style="max-width:820px;margin:0 auto">

    <!-- Back link -->
    <a href="/growth/dashboard" style="font-size:.83rem;color:#5c6ac4;font-weight:600;display:inline-flex;align-items:center;gap:5px;margin-bottom:20px">&#8592; Back to Growth Dashboard</a>

    <!-- Report header -->
    <div style="background:linear-gradient(135deg,#5c6ac4,#764ba2);color:#fff;border-radius:14px;padding:28px;margin-bottom:28px">
      <div style="font-size:.78rem;font-weight:600;opacity:.7;margin-bottom:8px">GROWTH HACKING REPORT &mdash; {ts_display}</div>
      <h1 style="font-size:1.4rem;font-weight:800;margin-bottom:10px">{report.get("goal","Growth Strategy")}</h1>
      <p style="font-size:.88rem;opacity:.9;line-height:1.55">{pos_angle}</p>
    </div>

    <!-- Authority narrative -->
    {"<div style='background:#fff;border-radius:12px;border-left:4px solid #5c6ac4;padding:20px 24px;margin-bottom:24px;border:1px solid #e9ebee'><p style='font-size:.8rem;font-weight:700;color:#5c6ac4;text-transform:uppercase;letter-spacing:.06em;margin-bottom:6px'>Authority Narrative</p><p style='font-size:.88rem;color:#1c1e21;line-height:1.6'>" + authority + "</p></div>" if authority else ""}

    {warnings_html}

    {_section("Quick Wins — Execute This Week", "&#9889;", report.get("quick_wins",[]), "#16a34a")}
    {_section("Medium-Term Plays (Weeks 2–6)", "&#128640;", report.get("medium_term",[]), "#2563eb")}
    {_section("Long-Term Compound Strategies", "&#127942;", report.get("long_term",[]), "#7c3aed")}

    <!-- Success metrics -->
    {"<div style='background:#fff;border-radius:12px;border:1px solid #e9ebee;padding:22px 24px;margin-bottom:24px'><h2 style='font-size:.95rem;font-weight:700;margin-bottom:14px'>&#128202; Success Metrics to Track</h2><ul style='padding-left:18px'>" + "".join(f"<li style='font-size:.83rem;color:#1c1e21;margin-bottom:6px'>{m}</li>" for m in report.get("success_metrics",[])) + "</ul></div>" if report.get("success_metrics") else ""}

    <div style="text-align:center;padding:24px 0">
      <a href="/growth/dashboard" style="background:linear-gradient(135deg,#5c6ac4,#764ba2);color:#fff;padding:11px 26px;border-radius:10px;font-size:.88rem;font-weight:700;text-decoration:none">&#128640; Generate Another Report</a>
    </div>
  </div>
"""
            return HTMLResponse(build_page(
                title="Growth Report",
                active_nav="social",
                body_content=_body,
                user_name=user.full_name,
                business_name=profile.business_name,
            ))
        except Exception as render_exc:
            logger.error(f"[{profile.client_id}] Report render crashed: {render_exc}", exc_info=True)
            _body = f"""
  <div style="max-width:720px;margin:60px auto;text-align:center">
    <div style="font-size:2.5rem;margin-bottom:16px">&#9888;</div>
    <h2 style="font-size:1.2rem;font-weight:700;margin-bottom:10px">Report Display Error</h2>
    <p style="font-size:.88rem;color:#606770;margin-bottom:20px">
      Something went wrong rendering this report. The report data exists but couldn't be displayed.
    </p>
    <p style="font-size:.78rem;color:#c62828;background:#fef2f2;padding:12px 16px;border-radius:8px;text-align:left;font-family:monospace">{str(render_exc)[:300]}</p>
    <a href="/growth/dashboard" style="color:#5c6ac4;font-weight:700;font-size:.88rem;display:inline-block;margin-top:16px">&#8592; Back to Growth Dashboard</a>
  </div>"""
            return HTMLResponse(build_page(
                title="Report Error", active_nav="social",
                body_content=_body, user_name=user.full_name, business_name=profile.business_name,
            ))
    finally:
        db.close()


# ──────────────────────────────────────────────────────────────────────────────
# Admin-only: fire growth agent test and generate sample notifications
# ──────────────────────────────────────────────────────────────────────────────

@router.post("/api/growth/admin-test")
async def api_admin_growth_test(request: Request, background_tasks: BackgroundTasks):
    """
    Admin-only endpoint that fires the full growth pipeline and creates
    sample notifications of EVERY type so the dashboard can be verified.

    POST /api/growth/admin-test
    """
    db = next(get_db())
    try:
        user, profile = get_user_context(request, db)
        if not user:
            return JSONResponse({"error": "Unauthorized"}, status_code=401)
        if not getattr(user, "is_admin", False):
            return JSONResponse({"error": "Admin only"}, status_code=403)
        if not profile:
            return JSONResponse({"error": "No profile found"}, status_code=400)

        report_id = uuid.uuid4().hex[:12]

        profile_data = {
            "business_type": profile.niche or "Digital Marketing Agency",
            "niche": profile.niche or "Digital Marketing",
            "target_audience": getattr(profile, "target_market_description", None) or "Small business owners and entrepreneurs",
            "current_situation": "Building & growing online presence, need more leads",
            "goal": "Grow audience, generate qualified leads, and establish authority",
            "budget": "medium",
            "timeline": "90 days",
            "current_online_presence": getattr(profile, "website_url", None) or "Active on major platforms",
        }

        background_tasks.add_task(
            _admin_growth_test_sync,
            profile.client_id,
            profile_data,
            report_id,
        )

        return JSONResponse({
            "ok": True,
            "report_id": report_id,
            "message": (
                "Growth agent test fired! Generating report + all notification types. "
                "Check the notification bell and /growth/dashboard in 30-60 seconds."
            ),
        })
    finally:
        db.close()


def _admin_growth_test_sync(client_id: str, profile_data: dict, report_id: str):
    """Sync wrapper — FastAPI runs sync BackgroundTasks in a thread pool."""
    from utils.agent_executor import run_agent_in_background
    run_agent_in_background(_admin_growth_test_bg(client_id, profile_data, report_id))


async def _admin_growth_test_bg(client_id: str, profile_data: dict, report_id: str):
    """Actual async work: run growth agent + create every notification type."""
    import traceback

    try:
        from agents.growth_hacking_agent import GrowthHackingAgent
        from utils.notification_manager import NotificationManager

        notifier = NotificationManager(client_id=client_id)

        # ── 1. Generate a REAL growth strategy report ─────────────────────────
        print(f"\n{'='*60}")
        print(f"[ADMIN TEST] Generating growth report {report_id} for {client_id}")
        print(f"{'='*60}\n")

        agent = GrowthHackingAgent(client_id=client_id, tier=profile_data.get("plan_tier", "pro"))
        strategy = await agent.generate_strategy(
            business_type=profile_data.get("business_type", "coaching / consulting"),
            current_situation=profile_data.get("current_situation", "Building presence"),
            goal=profile_data.get("goal", "Grow audience and leads"),
            budget=profile_data.get("budget", "medium"),
            timeline=profile_data.get("timeline", "90 days"),
            niche=profile_data.get("niche"),
            target_audience=profile_data.get("target_audience"),
            current_online_presence=profile_data.get("current_online_presence"),
        )

        # Save report
        strategy["report_id"] = report_id
        strategy["client_id"] = client_id
        strategy["created_at"] = datetime.now().isoformat()
        strategy["goal"] = profile_data.get("goal", "")

        _save_report_to_db(report_id, client_id, strategy.get("goal", ""), strategy)
        print(f"[ADMIN TEST] Report saved: {report_id}")

        # ── 2. Quick win notifications (from real report) ─────────────────────
        quick_wins = strategy.get("quick_wins") or []
        for i, tactic in enumerate(quick_wins[:2]):
            notif_type = "content_idea" if i == 0 else "growth_tip"
            impact = tactic.get("expected_impact", "medium")
            prio = "high" if impact in ("high", "massive") else "medium"
            await notifier.send_growth_notification(
                notification_type=notif_type,
                title=f"Growth Hack: {tactic.get('title', 'New Tactic')}",
                message=tactic.get("description", tactic.get("why_it_works", "")),
                priority=prio,
                action_url=f"/growth/report/{report_id}",
                action_label="View Full Report",
                action_type="internal_link",
                extra_meta={"report_id": report_id},
            )

        # ── 3. "People to Follow" suggestions ────────────────────────────────
        follow_suggestions = [
            {
                "name": "Sarah Chen — Marketing Strategist",
                "platform": "LinkedIn",
                "reason": "Shares growth frameworks your audience engages with. 15K+ followers in your niche.",
                "url": "https://linkedin.com/in/example-sarah",
            },
            {
                "name": "Mike Torres — Content Creator",
                "platform": "Instagram",
                "reason": "Creates viral reels in the digital marketing space. High engagement rate.",
                "url": "https://instagram.com/example-mike",
            },
            {
                "name": "Alex Rivera — SaaS Growth Lead",
                "platform": "Twitter/X",
                "reason": "Tweets about growth hacking tactics. Active in your target community.",
                "url": "https://x.com/example-alex",
            },
        ]
        for person in follow_suggestions:
            await notifier.send_growth_notification(
                notification_type="follow_suggestion",
                title=f"Follow: {person['name']}",
                message=person["reason"],
                priority="medium",
                platform=person["platform"],
                action_url=person["url"],
                action_label=f"View on {person['platform']}",
                action_type="open_url",
            )

        # ── 4. "Groups to Join" opportunities ────────────────────────────────
        group_suggestions = [
            {
                "name": "Digital Marketing Mastery (Facebook Group)",
                "platform": "Facebook",
                "reason": "45K members — active daily. Great for positioning yourself as an authority and finding leads.",
                "url": "https://facebook.com/groups/example-dm-mastery",
            },
            {
                "name": "Growth Hackers (LinkedIn Group)",
                "platform": "LinkedIn",
                "reason": "28K members discussing growth tactics. High-quality audience matching your ICP.",
                "url": "https://linkedin.com/groups/example-growth",
            },
            {
                "name": "r/Entrepreneur (Reddit)",
                "platform": "Reddit",
                "reason": "2M+ members. Answer questions to drive traffic and establish expertise.",
                "url": "https://reddit.com/r/Entrepreneur",
            },
        ]
        for group in group_suggestions:
            await notifier.send_growth_notification(
                notification_type="group_opportunity",
                title=f"Join: {group['name']}",
                message=group["reason"],
                priority="medium",
                platform=group["platform"],
                action_url=group["url"],
                action_label="Open Group",
                action_type="open_url",
            )

        # ── 5. Competitor alert ───────────────────────────────────────────────
        await notifier.send_growth_notification(
            notification_type="competitor_alert",
            title="Competitor Gained 2K Followers This Week",
            message=(
                "A competitor in your niche posted a viral carousel about '5 Marketing Mistakes'. "
                "Consider creating a response piece or a better version."
            ),
            priority="high",
            platform="Instagram",
            action_url=f"/growth/report/{report_id}",
            action_label="View Growth Plan",
            action_type="internal_link",
        )

        # ── 6. Mock comment notifications (urgent alerts) ─────────────────────
        mock_comments = [
            {
                "type": "sale",
                "title": "Potential Sale — Instagram Comment",
                "message": "User @jessica_biz commented: 'How much does this cost? I'd love to work with you on our Q2 campaign!'",
                "platform": "Instagram",
                "priority": "high",
            },
            {
                "type": "lead",
                "title": "New Lead — LinkedIn Comment",
                "message": "John M. commented on your post: 'This is exactly what we need. Can you DM me about consulting availability?'",
                "platform": "LinkedIn",
                "priority": "high",
            },
            {
                "type": "complaint",
                "title": "Customer Complaint — Facebook Comment",
                "message": "User Maria Lopez commented: 'I've been waiting 3 days for a response. Really disappointed with the service.'",
                "platform": "Facebook",
                "priority": "critical",
            },
            {
                "type": "support",
                "title": "Support Request — Instagram Comment",
                "message": "User @startup_founder commented: 'Having trouble accessing my dashboard. Can someone help?'",
                "platform": "Instagram",
                "priority": "medium",
            },
            {
                "type": "escalation",
                "title": "Escalation — Negative Thread Detected",
                "message": "Multiple users are discussing a bad experience in a Twitter thread mentioning your brand. Immediate response recommended.",
                "platform": "Twitter/X",
                "priority": "critical",
            },
        ]
        for comment in mock_comments:
            await notifier.send_growth_notification(
                notification_type=comment["type"],
                title=comment["title"],
                message=comment["message"],
                priority=comment["priority"],
                platform=comment["platform"],
                action_url="/inbox",
                action_label="Open Inbox",
                action_type="internal_link",
            )

        # ── 7. Mock DM / message notifications ───────────────────────────────
        mock_dms = [
            {
                "type": "sale",
                "title": "Sale Inquiry — Instagram DM",
                "message": "DM from @luxury_brands_co: 'We have a $10K budget for influencer marketing. Are you available for a partnership?'",
                "platform": "Instagram",
                "priority": "critical",
            },
            {
                "type": "lead",
                "title": "New Lead — Facebook Message",
                "message": "Message from David Park: 'Saw your ad about social media management. We're a team of 50 and need help with our LinkedIn strategy.'",
                "platform": "Facebook",
                "priority": "high",
            },
            {
                "type": "support",
                "title": "Support Request — LinkedIn Message",
                "message": "Message from a current client: 'Hi, I need to update my billing information. Can you guide me through the process?'",
                "platform": "LinkedIn",
                "priority": "medium",
            },
        ]
        for dm in mock_dms:
            await notifier.send_growth_notification(
                notification_type=dm["type"],
                title=dm["title"],
                message=dm["message"],
                priority=dm["priority"],
                platform=dm["platform"],
                action_url="/inbox",
                action_label="View Messages",
                action_type="internal_link",
            )

        # ── 8. Win / milestone notifications ──────────────────────────────────
        await notifier.send_growth_notification(
            notification_type="viral_alert",
            title="Your Reel is Going Viral!",
            message="Your Instagram Reel '5 Growth Hacks' has reached 12K views in 4 hours — 8x your average. Engage with commenters now!",
            priority="high",
            platform="Instagram",
            action_url="/analytics",
            action_label="View Analytics",
            action_type="internal_link",
        )

        await notifier.send_growth_notification(
            notification_type="milestone",
            title="Milestone: 1,000 Followers on LinkedIn!",
            message="Congratulations! You've hit 1,000 LinkedIn followers. Your growth rate is 3x faster than average for your niche.",
            priority="medium",
            platform="LinkedIn",
            action_url="/analytics",
            action_label="View Growth Stats",
            action_type="internal_link",
        )

        # ── 9. Account health notifications ───────────────────────────────────
        await notifier.send_growth_notification(
            notification_type="budget_alert",
            title="Usage Limit Warning",
            message="You've used 85% of your monthly post generation quota (26/30). Consider upgrading to the Growth plan for 90 posts/month.",
            priority="high",
            action_url="/billing",
            action_label="Upgrade Plan",
            action_type="internal_link",
        )

        await notifier.send_growth_notification(
            notification_type="sentiment_alert",
            title="Sentiment Dip Detected",
            message="Overall comment sentiment dropped 12% this week vs last week. Top negative theme: 'response time'. Consider addressing this publicly.",
            priority="medium",
            platform="Instagram",
            action_url="/analytics",
            action_label="Review Sentiment",
            action_type="internal_link",
        )

        await notifier.send_growth_notification(
            notification_type="post",
            title="Scheduled Post Published",
            message="Your post 'Top 10 Marketing Trends for 2025' was published to LinkedIn and Instagram on schedule.",
            priority="low",
            action_url="/calendar",
            action_label="View Calendar",
            action_type="internal_link",
        )

        await notifier.send_growth_notification(
            notification_type="system",
            title="System: Growth Agent Run Complete",
            message=f"Growth test completed successfully. Generated 1 report with {len(quick_wins)} quick wins, "
                    f"{len(strategy.get('medium_term', []))} medium-term plays, and {len(strategy.get('long_term', []))} long-term strategies.",
            priority="low",
            action_url=f"/growth/report/{report_id}",
            action_label="View Report",
            action_type="internal_link",
        )

        total_notifs = (
            min(len(quick_wins), 2)
            + len(follow_suggestions)
            + len(group_suggestions)
            + 1  # competitor
            + len(mock_comments)
            + len(mock_dms)
            + 2  # wins
            + 4  # health
        )
        print(f"\n{'='*60}")
        print(f"[ADMIN TEST] Complete! Created {total_notifs} notifications + 1 report")
        print(f"[ADMIN TEST] Report ID: {report_id}")
        print(f"{'='*60}\n")

    except Exception as exc:
        print(f"[ADMIN TEST] Failed: {exc}")
        traceback.print_exc()
