# api/notification_routes.py
"""
Notification Center Routes
==========================
Provides:
  GET  /api/notifications                  – paginated list + unread count (JSON)
  POST /api/notifications/{id}/read        – mark one notification as read
  POST /api/notifications/mark-all-read    – mark all as read
  POST /api/notifications/{id}/action-click – log that a client clicked the action button
  GET  /notifications                      – full notification center HTML page

Notification types
------------------
URGENT ALERTS  (require client response)
  complaint        – Negative comment / DM detected
  escalation       – Situation needs immediate attention
  sale             – Real buying intent detected
  lead             – New qualified lead in messages
  support          – General support request

GROWTH OPPORTUNITIES  (AI-recommended actions)
  follow_suggestion  – Accounts your audience follows; go connect with them
  group_opportunity  – Facebook / LinkedIn groups worth joining
  competitor_alert   – Competitor content worth knowing about

INTELLIGENCE  (AI insights)
  content_idea     – Trending topic tailored to your brand
  growth_tip       – Platform-specific growth hack

WINS  (positive signals)
  viral_alert      – Post gaining unusual traction
  milestone        – Follower / engagement goal hit

ACCOUNT HEALTH
  budget_alert     – Usage nearing your plan limit  → /billing
  sentiment_alert  – Negative sentiment spike detected
  post             – Post published / scheduled update
  system           – Platform or system-level message
"""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse
from utils.shared_layout import build_page
import json
import os
from pathlib import Path
from datetime import datetime, timedelta

router = APIRouter()

NOTIF_DIR = Path("storage") / "notifications"


# ──────────────────────────────────────────────
# Storage helpers  (PostgreSQL-backed)
# ──────────────────────────────────────────────

def _load(client_id: str) -> list:
    """Load all notifications newest-first from PostgreSQL (excludes cleared)."""
    try:
        from database.db import get_db
        from database.models import ClientNotification
        db = next(get_db())
        try:
            rows = (
                db.query(ClientNotification)
                .filter(
                    ClientNotification.client_id == client_id,
                    ClientNotification.cleared_at == None,          # noqa: E711  — SQLAlchemy IS NULL
                )
                .order_by(ClientNotification.created_at.desc())
                .limit(200)
                .all()
            )
            items = []
            for r in rows:
                meta = {}
                if r.metadata_json:
                    try:
                        meta = json.loads(r.metadata_json)
                    except Exception:
                        pass
                items.append({
                    "id": r.id,
                    "type": r.notification_type,
                    "title": r.title,
                    "message": r.message or "",
                    "priority": r.priority or "medium",
                    "timestamp": r.created_at.strftime("%Y-%m-%dT%H:%M:%SZ") if r.created_at else "",
                    "read": bool(r.read),
                    "metadata": meta,
                })
            return items
        finally:
            db.close()
    except Exception as e:
        import logging as _log_mod
        _log_mod.getLogger("notifications").error(
            f"DB _load failed for {client_id}: {e}", exc_info=True
        )
        # NEVER fall back to filesystem — Railway wipes it on redeploy.
        # Return empty so the failure is visible in logs, not masked by stale files.
        return []


def _load_file(client_id: str) -> list:
    """Fallback: load from legacy JSONL file."""
    f = _alerts_file(client_id)
    if not f.exists():
        return []
    items = []
    with open(f, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                try:
                    items.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    items.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
    return items


def _alerts_file(client_id: str) -> Path:
    NOTIF_DIR.mkdir(parents=True, exist_ok=True)
    return NOTIF_DIR / f"{client_id}_dashboard_alerts.jsonl"


def _mark_read_db(client_id: str, notif_id: str = None, mark_all: bool = False) -> bool:
    """Mark one or all notifications as read in PostgreSQL."""
    import logging as _log_mod
    _mrlog = _log_mod.getLogger("notifications")
    try:
        from database.db import get_db
        from database.models import ClientNotification
        db = next(get_db())
        try:
            if mark_all:
                # Use isnot(True) to catch both read=False AND read=NULL rows
                updated = db.query(ClientNotification).filter(
                    ClientNotification.client_id == client_id,
                    ClientNotification.read.isnot(True),
                ).update({"read": True, "read_at": datetime.utcnow()}, synchronize_session="fetch")
                _mrlog.info(f"[notifications] mark_all updated {updated} rows for client {client_id}")
            elif notif_id:
                row = db.query(ClientNotification).filter(
                    ClientNotification.id == notif_id,
                    ClientNotification.client_id == client_id,
                ).first()
                if row:
                    row.read = True
                    row.read_at = datetime.utcnow()
                else:
                    # Try without client_id filter to diagnose mismatches
                    any_row = db.query(ClientNotification).filter(
                        ClientNotification.id == notif_id
                    ).first()
                    if any_row:
                        _mrlog.error(
                            f"[notifications] mark-read MISMATCH: notif {notif_id} exists "
                            f"with client_id='{any_row.client_id}' but caller passed client_id='{client_id}'"
                        )
                    else:
                        _mrlog.warning(f"[notifications] mark-read: notif {notif_id} not found in DB")
                    db.close()
                    return False
            db.commit()
            return True
        finally:
            db.close()
    except Exception as e:
        _mrlog.error(f"[notifications] DB _mark_read failed: {e}", exc_info=True)
        return False


def _update_metadata_db(client_id: str, notif_id: str, meta_updates: dict) -> bool:
    """Update the metadata JSON for a notification (e.g. action_clicked_at)."""
    try:
        from database.db import get_db
        from database.models import ClientNotification
        db = next(get_db())
        try:
            row = db.query(ClientNotification).filter(
                ClientNotification.id == notif_id,
                ClientNotification.client_id == client_id,
            ).first()
            if not row:
                return False
            meta = {}
            if row.metadata_json:
                try:
                    meta = json.loads(row.metadata_json)
                except Exception:
                    pass
            meta.update(meta_updates)
            row.metadata_json = json.dumps(meta)
            row.read = True
            row.read_at = datetime.utcnow()
            db.commit()
            return True
        finally:
            db.close()
    except Exception as e:
        print(f"[notifications] DB _update_metadata failed: {e}")
        return False


# ──────────────────────────────────────────────
# JSON API endpoints
# ──────────────────────────────────────────────

@router.get("/api/notifications")
async def api_get_notifications(
    request: Request,
    unread_only: bool = False,
    notif_type: str = "",
    limit: int = 50,
):
    from database.db import get_db
    from database.models import ClientProfile
    from api.auth_routes import get_current_user

    db = next(get_db())
    try:
        user = get_current_user(request, db)
        if not user:
            return JSONResponse({"error": "Unauthorized"}, status_code=401)

        profile = db.query(ClientProfile).filter(
            ClientProfile.user_id == user.id
        ).first()
        if not profile:
            return JSONResponse({"unread_count": 0, "notifications": []})

        all_notifs = _load(profile.client_id)
        unread_count = sum(1 for n in all_notifs if not n.get("read", False))

        filtered = all_notifs
        if unread_only:
            filtered = [n for n in filtered if not n.get("read", False)]
        if notif_type:
            filtered = [n for n in filtered if n.get("type") == notif_type]

        return JSONResponse({
            "unread_count": unread_count,
            "notifications": filtered[:limit],
        })
    finally:
        db.close()


@router.post("/api/notifications/mark-all-read")
async def api_mark_all_read(request: Request):
    from database.db import get_db
    from database.models import ClientProfile
    from api.auth_routes import get_current_user

    db = next(get_db())
    try:
        user = get_current_user(request, db)
        if not user:
            return JSONResponse({"error": "Unauthorized"}, status_code=401)

        profile = db.query(ClientProfile).filter(
            ClientProfile.user_id == user.id
        ).first()
        if not profile:
            return JSONResponse({"ok": False})

        ok = _mark_read_db(profile.client_id, mark_all=True)
        return JSONResponse({"ok": ok})
    finally:
        db.close()


@router.post("/api/notifications/clear-all")
async def api_clear_all(request: Request):
    """Soft-delete notifications (sets cleared_at).  Undo within 24 h.

    Accepts optional JSON body:
      {"category": "intel"}   — only clear notifications in that category
    If no category is provided, clears ALL notifications.
    """
    from database.db import get_db
    from database.models import ClientProfile, ClientNotification
    from api.auth_routes import get_current_user

    # Category → notification types mapping (mirrors _TYPE_META[...][3])
    _CAT_TYPES = {
        "urgent":      ["complaint", "escalation", "sale", "lead", "support"],
        "opportunity": ["follow_suggestion", "group_opportunity", "competitor_alert", "growth_report"],
        "intel":       ["content_idea", "growth_tip"],
        "win":         ["viral_alert", "milestone"],
        "health":      ["budget_alert", "sentiment_alert", "post", "system"],
    }

    db = next(get_db())
    try:
        user = get_current_user(request, db)
        if not user:
            return JSONResponse({"error": "Unauthorized"}, status_code=401)

        profile = db.query(ClientProfile).filter(
            ClientProfile.user_id == user.id
        ).first()
        if not profile:
            return JSONResponse({"ok": False})

        # Parse optional category from body
        category = None
        try:
            body = await request.json()
            category = body.get("category") if isinstance(body, dict) else None
        except Exception:
            pass

        now = datetime.utcnow()
        query = (
            db.query(ClientNotification)
            .filter(
                ClientNotification.client_id == profile.client_id,
                ClientNotification.cleared_at == None,
            )
        )

        # Scope to category if provided
        if category and category in _CAT_TYPES:
            query = query.filter(
                ClientNotification.notification_type.in_(_CAT_TYPES[category])
            )

        count = query.update({"cleared_at": now}, synchronize_session="fetch")
        db.commit()
        return JSONResponse({"ok": True, "cleared": count, "cleared_at": now.isoformat(), "category": category})
    finally:
        db.close()


@router.post("/api/notifications/undo-clear")
async def api_undo_clear(request: Request):
    """Restore notifications cleared within the last 24 hours."""
    from database.db import get_db
    from database.models import ClientProfile, ClientNotification
    from api.auth_routes import get_current_user

    db = next(get_db())
    try:
        user = get_current_user(request, db)
        if not user:
            return JSONResponse({"error": "Unauthorized"}, status_code=401)

        profile = db.query(ClientProfile).filter(
            ClientProfile.user_id == user.id
        ).first()
        if not profile:
            return JSONResponse({"ok": False})

        cutoff = datetime.utcnow() - timedelta(hours=24)
        count = (
            db.query(ClientNotification)
            .filter(
                ClientNotification.client_id == profile.client_id,
                ClientNotification.cleared_at != None,
                ClientNotification.cleared_at >= cutoff,
            )
            .update({"cleared_at": None})
        )
        db.commit()
        return JSONResponse({"ok": True, "restored": count})
    finally:
        db.close()


@router.post("/api/notifications/{notif_id}/read")
async def api_mark_one_read(request: Request, notif_id: str):
    from database.db import get_db
    from database.models import ClientProfile
    from api.auth_routes import get_current_user

    db = next(get_db())
    try:
        user = get_current_user(request, db)
        if not user:
            return JSONResponse({"error": "Unauthorized"}, status_code=401)

        profile = db.query(ClientProfile).filter(
            ClientProfile.user_id == user.id
        ).first()
        if not profile:
            return JSONResponse({"ok": False})

        ok = _mark_read_db(profile.client_id, notif_id=notif_id)
        return JSONResponse({"ok": ok})
    finally:
        db.close()


@router.post("/api/notifications/{notif_id}/action-click")
async def api_action_click(request: Request, notif_id: str):
    """Log that a client clicked the action button on a notification."""
    from database.db import get_db
    from database.models import ClientProfile
    from api.auth_routes import get_current_user

    db = next(get_db())
    try:
        user = get_current_user(request, db)
        if not user:
            return JSONResponse({"error": "Unauthorized"}, status_code=401)

        profile = db.query(ClientProfile).filter(
            ClientProfile.user_id == user.id
        ).first()
        if not profile:
            return JSONResponse({"ok": False})

        ok = _update_metadata_db(
            profile.client_id, notif_id,
            {"action_clicked_at": datetime.now().isoformat()},
        )
        return JSONResponse({"ok": ok})
    finally:
        db.close()


@router.post("/api/notifications/{notif_id}/recommendation-action")
async def api_recommendation_action(request: Request, notif_id: str):
    """Record that a user followed or dismissed a recommended account.

    Body JSON: {"action": "followed"|"dismissed", "name": "...", "url": "...", "platform": "..."}
    """
    from database.db import get_db
    from database.models import ClientProfile, RecommendationAction, ClientNotification
    from api.auth_routes import get_current_user
    import json as _json

    db = next(get_db())
    try:
        user = get_current_user(request, db)
        if not user:
            return JSONResponse({"error": "Unauthorized"}, status_code=401)

        profile = db.query(ClientProfile).filter(
            ClientProfile.user_id == user.id
        ).first()
        if not profile:
            return JSONResponse({"ok": False, "error": "No profile"})

        body = await request.json()
        action = body.get("action", "")
        name = body.get("name", "").strip()
        url = body.get("url", "").strip()
        platform = body.get("platform", "").strip()

        if action not in ("followed", "dismissed"):
            return JSONResponse({"ok": False, "error": "Invalid action"}, status_code=400)
        if not name:
            return JSONResponse({"ok": False, "error": "Missing name"}, status_code=400)

        # Check for existing action on the same name+url to avoid duplicates
        existing = db.query(RecommendationAction).filter(
            RecommendationAction.client_id == profile.client_id,
            RecommendationAction.name == name,
        ).first()

        if existing:
            existing.action = action
            existing.url = url or existing.url
            db.commit()
        else:
            row = RecommendationAction(
                id=f"ra_{datetime.now().timestamp()}",
                client_id=profile.client_id,
                action=action,
                name=name,
                url=url,
                platform=platform,
            )
            db.add(row)
            db.commit()

        return JSONResponse({"ok": True, "action": action, "name": name})
    finally:
        db.close()


@router.get("/api/recommendations/acted-on")
async def api_get_acted_on(request: Request):
    """Return all followed/dismissed recommendations for the current client."""
    from database.db import get_db
    from database.models import ClientProfile, RecommendationAction
    from api.auth_routes import get_current_user

    db = next(get_db())
    try:
        user = get_current_user(request, db)
        if not user:
            return JSONResponse({"error": "Unauthorized"}, status_code=401)

        profile = db.query(ClientProfile).filter(
            ClientProfile.user_id == user.id
        ).first()
        if not profile:
            return JSONResponse({"items": []})

        rows = (
            db.query(RecommendationAction)
            .filter(RecommendationAction.client_id == profile.client_id)
            .order_by(RecommendationAction.created_at.desc())
            .all()
        )
        return JSONResponse({
            "items": [
                {
                    "id": r.id,
                    "action": r.action,
                    "name": r.name,
                    "url": r.url,
                    "platform": r.platform,
                    "created_at": r.created_at.isoformat() if r.created_at else None,
                }
                for r in rows
            ]
        })
    finally:
        db.close()


# ──────────────────────────────────────────────
# HTML page
# ──────────────────────────────────────────────

# (emoji, css-class, short label, category-group)
_TYPE_META: dict[str, tuple] = {
    # ── Urgent Alerts ────────────────────────────────────────────────────────
    "complaint":         ("&#128545;",  "complaint",         "Customer Complaint",        "urgent"),
    "escalation":        ("&#9888;",    "escalation",        "Needs Your Attention",      "urgent"),
    "sale":              ("&#128176;",  "sale",              "Sale Opportunity",          "urgent"),
    "lead":              ("&#128081;",  "lead",              "New Lead",                  "urgent"),
    "support":           ("&#128172;",  "support",           "Support Request",           "urgent"),
    # ── Growth Opportunities ─────────────────────────────────────────────────
    "follow_suggestion": ("&#128100;",  "follow_suggestion", "Who to Follow",             "opportunity"),
    "group_opportunity": ("&#128101;",  "group_opportunity", "Group to Join",             "opportunity"),
    "competitor_alert":  ("&#128269;",  "competitor_alert",  "Competitor Activity",       "opportunity"),
    "growth_report":     ("&#128200;",  "growth_report",     "Daily Growth Report",       "opportunity"),
    # ── Intelligence ────────────────────────────────────────────────────────
    "content_idea":      ("&#10024;",   "content_idea",      "Content Idea",              "intel"),
    "growth_tip":        ("&#128161;",  "growth_tip",        "Growth Tip",                "intel"),
    # ── Wins ────────────────────────────────────────────────────────────────
    "viral_alert":       ("&#128293;",  "viral_alert",       "Going Viral!",              "win"),
    "milestone":         ("&#127942;",  "milestone",         "Milestone Reached",         "win"),
    # ── Account Health ───────────────────────────────────────────────────────
    "budget_alert":      ("&#9888;",    "budget_alert",      "Usage Limit Warning",       "health"),
    "sentiment_alert":   ("&#128201;",  "sentiment_alert",   "Negative Trend Detected",   "health"),
    "post":              ("&#128197;",  "post",              "Post Update",               "health"),
    "system":            ("&#9881;",    "system",            "System Alert",              "health"),
}

_CATEGORY_META = {
    "urgent":      ("&#128680;", "Urgent — Action Required",   "#dc2626"),
    "opportunity": ("&#128640;", "Growth Opportunities",       "#2563eb"),
    "intel":       ("&#129504;", "AI Intelligence",            "#7c3aed"),
    "win":         ("&#127881;", "Wins",                       "#16a34a"),
    "health":      ("&#129657;", "Account Health",             "#ea580c"),
}

_PRIO_META = {
    "critical": ("#dc2626", "Critical"),
    "high":     ("#ea580c", "High"),
    "medium":   ("#2563eb", "Medium"),
    "low":      ("#16a34a", "Low"),
}


def _build_action_btn(n: dict, notif_id: str) -> str:
    """Build the action button HTML for a notification, if any."""
    meta = n.get("metadata") or {}
    action_url   = meta.get("action_url", "")
    action_label = meta.get("action_label", "")
    action_type  = meta.get("action_type", "")   # open_url | internal_link | view_inbox | open_billing

    if not action_url or not action_label:
        return ""

    on_click  = f"logActionClick('{notif_id}')"

    if action_type == "open_url":
        return (
            f'<a href="{action_url}" target="_blank" rel="noopener noreferrer" '
            f'onclick="{on_click}" '
            f'class="action-link-btn">{action_label}</a>'
        )
    return (
        f'<a href="{action_url}" '
        f'onclick="{on_click}" '
        f'class="action-link-btn">{action_label}</a>'
    )


def _build_notif_html(notifications: list, group_by_category: bool = False) -> str:
    if not notifications:
        return (
            "<div class='empty-state'>"
            "<div class='empty-icon'>&#128276;</div>"
            "<h3>All caught up!</h3>"
            "<p>No notifications yet. We&rsquo;ll alert you when something needs your attention.</p>"
            "</div>"
        )

    def _render_item(n: dict) -> str:
        ntype   = n.get("type", "system")
        tmeta   = _TYPE_META.get(ntype, ("&#128276;", "system", "Notification", "health"))
        icon, icon_cls, type_label, _cat = tmeta
        prio    = n.get("priority", "medium")
        prio_color, prio_label = _PRIO_META.get(prio, ("#2563eb", "Medium"))
        notif_id = n.get("id", "")
        title    = n.get("title", "Notification")
        message  = n.get("message", "")
        is_read  = n.get("read", False)
        read_cls = "read" if is_read else "unread"

        # timestamp — stored as UTC, display as Eastern
        ts = n.get("timestamp", "")
        time_display = ""
        if ts:
            try:
                from zoneinfo import ZoneInfo
                dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                dt_et = dt.astimezone(ZoneInfo("America/New_York"))
                time_display = dt_et.strftime("%-b %-d, %Y %-I:%M %p %Z")
            except Exception:
                time_display = ts[:19].replace("T", " ")

        meta_block  = n.get("metadata") or {}
        platform    = meta_block.get("platform", "")
        platform_tag = f"<span class='meta-tag'>&#127760;&nbsp;{platform.title()}</span>" if platform else ""

        # Was action already clicked?
        action_clicked = bool(meta_block.get("action_clicked_at"))
        action_html    = "" if action_clicked else _build_action_btn(n, notif_id)

        read_btn = (
            f"<button class='mark-read-btn' onclick='markRead(\"{notif_id}\", this)' title='Mark as read'>&#10003; Read</button>"
            if not is_read else
            "<span class='read-badge'>&#10003; Read</span>"
        )

        # Escape message for data attribute (prevent HTML injection in attribute)
        import html as _html
        safe_msg = _html.escape(message, quote=True)
        safe_title = _html.escape(title, quote=True)
        meta_json_attr = _html.escape(json.dumps(meta_block), quote=True) if meta_block else ""

        return (
            f"<div class='notif-item {read_cls}' id='ni-{notif_id}' data-id='{notif_id}' data-type='{ntype}' data-cat='{_cat}'"
            f" data-title='{safe_title}' data-msg='{safe_msg}' data-prio='{prio}'"
            f" data-ts='{time_display}' data-icon='{icon}' data-icon-cls='{icon_cls}'"
            f" data-type-label='{type_label}' data-platform='{platform}'"
            f" data-meta='{meta_json_attr}'"
            f" onclick=\"openPanel('{notif_id}')\">"
            f"  <div class='ni-icon {icon_cls}'>{icon}</div>"
            f"  <div class='ni-body'>"
            f"    <div class='ni-top'>"
            f"      <span class='ni-title'>{title}</span>"
            f"      <span class='ni-prio' style='color:{prio_color};border-color:{prio_color}'>{prio_label}</span>"
            f"    </div>"
            f"    <div class='ni-msg'>{message}</div>"
            f"    <div class='ni-meta'>"
            f"      <span class='ni-time'>&#128336;&nbsp;{time_display}</span>"
            f"      <span class='ni-type-tag'>{type_label}</span>"
            f"      {platform_tag}"
            f"    </div>"
            f"    {action_html}"
            f"  </div>"
            f"  <div class='ni-action'>{read_btn}</div>"
            f"</div>"
        )

    if not group_by_category:
        return "".join(_render_item(n) for n in notifications)

    # Group by category
    from collections import defaultdict
    groups: dict[str, list] = defaultdict(list)
    for n in notifications:
        ntype = n.get("type", "system")
        cat   = _TYPE_META.get(ntype, ("", "", "", "health"))[3]
        groups[cat].append(n)

    category_order = ["urgent", "opportunity", "intel", "win", "health"]
    html = ""
    for cat in category_order:
        items = groups.get(cat, [])
        if not items:
            continue
        cat_icon, cat_label, cat_color = _CATEGORY_META[cat]
        html += (
            f"<div class='cat-section'>"
            f"  <div class='cat-header' style='border-left:4px solid {cat_color}'>"
            f"    <span class='cat-icon'>{cat_icon}</span>"
            f"    <span class='cat-title' style='color:{cat_color}'>{cat_label}</span>"
            f"    <span class='cat-count'>{len(items)}</span>"
            f"  </div>"
            f"  <div class='cat-items'>"
            + "".join(_render_item(n) for n in items)
            + "  </div>"
            f"</div>"
        )
    return html or "<div class='empty-state'><div class='empty-icon'>&#128276;</div><h3>Nothing here</h3></div>"


@router.get("/notifications", response_class=HTMLResponse)
async def notifications_page(request: Request):
    """Full notification center page with sidebar/topbar shell."""
    from database.db import get_db
    from database.models import ClientProfile, OnboardingStatus
    from api.auth_routes import get_current_user
    from fastapi.responses import RedirectResponse

    db = next(get_db())
    try:
        user = get_current_user(request, db)
        if not user:
            return RedirectResponse("/account/login", status_code=303)

        profile = db.query(ClientProfile).filter(
            ClientProfile.user_id == user.id
        ).first()
        if not profile:
            return RedirectResponse("/onboarding", status_code=303)

        if profile.onboarding_status != OnboardingStatus.complete:
            return RedirectResponse("/onboarding/status", status_code=303)

        first_name    = user.full_name.split()[0]
        first_initial = first_name[0].upper()
        today_str     = datetime.now().strftime("%A, %B %d").replace(" 0", " ")

        notifications = _load(profile.client_id)
        unread_count  = sum(1 for n in notifications if not n.get("read", False))

        notif_html    = _build_notif_html(notifications, group_by_category=True)

        def _cat_count(cat_key):
            return sum(
                1 for n in notifications
                if not n.get("read") and _TYPE_META.get(n.get("type","system"), ("","","","health"))[3] == cat_key
            )
        urgent_count = _cat_count("urgent")
        opp_count    = _cat_count("opportunity")
        intel_count  = _cat_count("intel")
        win_count    = _cat_count("win")
        health_count = _cat_count("health")

        unread_badge = (
            f"<span class='nav-badge'>{unread_count}</span>"
            if unread_count > 0 else ""
        )
        bell_dot = "<span class='notif-dot'></span>" if unread_count > 0 else ""

        header_mark_all = (
            "<button class='mark-all-btn' onclick='markAllRead()'>&#10003;&nbsp; Mark all as read</button>"
            if unread_count > 0 else ""
        )

        total_count = len(notifications)
        header_clear_all = (
            "<button class='clear-all-btn' onclick='clearAllNotifs()'>&#128465;&nbsp; Clear All</button>"
            if total_count > 0 else ""
        )

        count_label = (
            f"<span class='uc-label'>{unread_count} unread</span>"
            if unread_count > 0 else
            "<span class='uc-label all-read'>All caught up &#10003;</span>"
        )

        urgent_badge  = f" <span class='tab-badge urgent'>{urgent_count}</span>" if urgent_count else ""
        opp_badge     = f" <span class='tab-badge opp'>{opp_count}</span>" if opp_count else ""
        intel_badge   = f" <span class='tab-badge intel'>{intel_count}</span>" if intel_count else ""
        win_badge     = f" <span class='tab-badge win'>{win_count}</span>" if win_count else ""
        health_badge  = f" <span class='tab-badge health'>{health_count}</span>" if health_count else ""

        _body = f"""
  <div class="notif-page">
    <div class="page-header">
      <div>
        <h1>&#128276;&nbsp; Notifications {count_label}</h1>
        <p class="page-sub">Your AI team keeps you in the loop — every important signal from your audience, plus growth ideas tailored to your brand.</p>
      </div>
      <div style="display:flex;gap:10px;align-items:center">
        {header_mark_all}
        {header_clear_all}
      </div>
    </div>

    <!-- View toggle -->
    <div class="view-toggle">
      <button class="view-btn active" id="btnGrouped"  onclick="setView('grouped',  this)">&#128193;&nbsp; By Category</button>
      <button class="view-btn"        id="btnFlat"     onclick="setView('flat',     this)">&#9776;&nbsp; Flat List</button>
    </div>

    <!-- Filter tabs (shown in flat mode) -->
    <div class="filter-bar" id="filterBar" style="display:none">
      <button class="filter-tab active" onclick="filterNotifs('all',       this)">All</button>
      <button class="filter-tab"        onclick="filterNotifs('unread',    this)">Unread</button>
      <button class="filter-tab"        onclick="filterNotifs('urgent_group',  this)">&#128680;&nbsp;Urgent{urgent_badge}</button>
      <button class="filter-tab"        onclick="filterNotifs('opportunity_group', this)">&#128640;&nbsp;Opportunities{opp_badge}</button>
      <button class="filter-tab"        onclick="filterNotifs('intel_group',  this)">&#129504;&nbsp;Intelligence{intel_badge}</button>
      <button class="filter-tab"        onclick="filterNotifs('win_group',    this)">&#127881;&nbsp;Wins{win_badge}</button>
      <button class="filter-tab"        onclick="filterNotifs('health_group', this)">&#129657;&nbsp;Health{health_badge}</button>
    </div>

    <!-- Split layout: list + detail panel -->
    <div class="notif-split">
      <!-- Notification list -->
      <div class="notif-list-col">
        <div class="notif-list" id="notifList">
{notif_html}
        </div>
      </div>

      <!-- Detail panel (hidden by default) -->
      <div class="detail-panel" id="detailPanel">
        <div class="dp-header">
          <span class="dp-header-label">Notification Details</span>
          <button class="dp-close" onclick="closePanel()" title="Close">&#10005;</button>
        </div>
        <div class="dp-body" id="dpBody">
          <div class="dp-placeholder">
            <div style="font-size:2rem;margin-bottom:10px">&#128072;</div>
            <p>Click a notification to view full details here.</p>
          </div>
        </div>
      </div>
    </div>
  </div>
  <div id="toast"></div>
  <!-- Undo-clear toast -->
  <div id="undo-toast" style="display:none">
    <span id="undo-msg">Notifications cleared.</span>
    <button id="undo-btn" onclick="undoClear()">Undo</button>
    <span id="undo-timer"></span>
  </div>
"""
        return HTMLResponse(build_page(
            title="Notifications",
            active_nav="notifications",
            body_content=_body,
            extra_css="""
    /* ── Page header ─────────────────────────────────── */
    .page-header{display:flex;align-items:flex-start;justify-content:space-between;margin-bottom:18px;flex-wrap:wrap;gap:12px}
    .page-header h1{font-size:1.35rem;font-weight:800;margin-bottom:4px}
    .page-sub{font-size:.82rem;color:#606770;max-width:540px;line-height:1.5}
    .uc-label{font-size:.82rem;color:#606770;margin-left:10px}
    .uc-label.all-read{color:#2e7d32;font-weight:600}
    .mark-all-btn{background:#5c6ac4;color:#fff;padding:8px 16px;border-radius:8px;font-size:.83rem;font-weight:700;transition:opacity .15s;white-space:nowrap}
    .mark-all-btn:hover{opacity:.85}

    /* ── View toggle ─────────────────────────────────── */
    .view-toggle{display:flex;gap:6px;margin-bottom:14px}
    .view-btn{padding:6px 16px;border-radius:8px;font-size:.8rem;font-weight:600;color:#606770;background:#fff;border:1px solid #dde0e4;cursor:pointer;transition:all .12s}
    .view-btn.active{background:#5c6ac4;color:#fff;border-color:#5c6ac4}

    /* ── Filter tabs ─────────────────────────────────── */
    .filter-bar{display:flex;gap:6px;margin-bottom:18px;flex-wrap:wrap}
    .filter-tab{padding:6px 14px;border-radius:20px;font-size:.8rem;font-weight:600;color:#606770;background:#fff;border:1px solid #dde0e4;cursor:pointer;transition:all .12s}
    .filter-tab:hover{background:#f0f2f5}
    .filter-tab.active{background:#5c6ac4;color:#fff;border-color:#5c6ac4}
    .tab-badge{display:inline-flex;align-items:center;justify-content:center;min-width:18px;height:18px;border-radius:99px;font-size:.7rem;font-weight:700;padding:0 5px;margin-left:3px;color:#fff}
    .tab-badge.urgent{background:#dc2626}
    .tab-badge.opp{background:#2563eb}
    .tab-badge.intel{background:#7c3aed}
    .tab-badge.win{background:#16a34a}
    .tab-badge.health{background:#ea580c}

    /* ── Category sections ───────────────────────────── */
    .cat-section{margin-bottom:24px}
    .cat-header{display:flex;align-items:center;gap:10px;padding:10px 16px;background:#fff;border-radius:10px 10px 0 0;border-bottom:1px solid #f0f2f5}
    .cat-icon{font-size:1rem}
    .cat-title{font-size:.85rem;font-weight:800;letter-spacing:.02em}
    .cat-count{margin-left:auto;font-size:.75rem;font-weight:700;background:#f0f2f5;color:#606770;border-radius:99px;padding:1px 9px}
    .cat-items{border-radius:0 0 10px 10px;overflow:hidden}

    /* ── Notification items ──────────────────────────── */
    .notif-list{display:flex;flex-direction:column;gap:0}
    .notif-item{
      background:#fff;
      padding:16px 20px;
      display:flex;align-items:flex-start;gap:14px;
      border-bottom:1px solid #f0f2f5;
      transition:background .12s;
    }
    .notif-item:last-child{border-bottom:none}
    .notif-item.unread{background:#ffffff;border-left:3px solid #5c6ac4}
    .notif-item.read{background:#e9eaec;border-left:3px solid transparent}
    .notif-item.read .ni-title{color:#8b8f96}
    .notif-item.read .ni-msg{color:#9a9ea6}
    .notif-item.read .ni-icon{opacity:.5}
    .notif-item.read .ni-prio{opacity:.45}
    .notif-item.read .action-link-btn{opacity:.5}
    .notif-item:hover{background:#f5f7ff}
    .notif-item.read:hover{background:#e8e9ec}

    /* flat-list mode (no cat-section wrappers) */
    #notifList.flat-mode .notif-item:first-child{border-radius:12px 12px 0 0}
    #notifList.flat-mode .notif-item:last-child{border-radius:0 0 12px 12px;border-bottom:none}
    #notifList.flat-mode .notif-item:only-child{border-radius:12px}

    /* icon circles */
    .ni-icon{width:42px;height:42px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:1.1rem;flex-shrink:0}
    .ni-icon.complaint{background:#fff3e0}
    .ni-icon.escalation{background:#fde8e8}
    .ni-icon.sale{background:#e8f5e9}
    .ni-icon.lead{background:#ede8f5}
    .ni-icon.support{background:#e8f0fe}
    .ni-icon.follow_suggestion{background:#e0f2fe}
    .ni-icon.group_opportunity{background:#e0f2fe}
    .ni-icon.competitor_alert{background:#fff8e1}
    .ni-icon.content_idea{background:#f3e8ff}
    .ni-icon.growth_tip{background:#fef9c3}
    .ni-icon.viral_alert{background:#fff7ed}
    .ni-icon.milestone{background:#f0fdf4}
    .ni-icon.budget_alert{background:#fff7ed}
    .ni-icon.sentiment_alert{background:#fde8e8}
    .ni-icon.post{background:#ede8f5}
    .ni-icon.system{background:#f0f2f5}

    .ni-body{flex:1;min-width:0}
    .ni-top{display:flex;align-items:center;gap:8px;margin-bottom:4px;flex-wrap:wrap}
    .ni-title{font-size:.9rem;font-weight:700;color:#1c1e21}
    .ni-prio{font-size:.72rem;font-weight:700;border:1px solid;border-radius:99px;padding:1px 8px}
    .ni-msg{font-size:.84rem;color:#444;line-height:1.5;margin-bottom:8px}
    .ni-meta{display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin-bottom:8px}
    .ni-time{font-size:.76rem;color:#90949c}
    .ni-type-tag{font-size:.72rem;font-weight:700;color:#5c6ac4;background:#ede8f5;border-radius:6px;padding:1px 7px}
    .meta-tag{font-size:.72rem;color:#606770;background:#f0f2f5;border-radius:6px;padding:1px 7px}

    /* Action link button */
    .action-link-btn{
      display:inline-flex;align-items:center;gap:5px;
      font-size:.8rem;font-weight:700;
      background:#5c6ac4;color:#fff;
      padding:6px 14px;border-radius:8px;
      text-decoration:none;transition:opacity .15s;
      margin-top:2px;
    }
    .action-link-btn:hover{opacity:.85;color:#fff}

    .ni-action{flex-shrink:0;margin-left:8px;margin-top:2px}
    .mark-read-btn{background:#5c6ac4;color:#fff;font-size:.78rem;font-weight:700;padding:6px 14px;border-radius:8px;transition:opacity .12s;white-space:nowrap;border:none;cursor:pointer}
    .mark-read-btn:hover{opacity:.85}
    .read-badge{font-size:.72rem;color:#9a9ea6;font-weight:500;white-space:nowrap;display:inline-flex;align-items:center;gap:4px}

    /* ── Empty ───────────────────────────────────────── */
    .empty-state{text-align:center;padding:60px 20px;background:#fff;border-radius:12px}
    .empty-icon{font-size:2.6rem;margin-bottom:14px}
    .empty-state h3{font-size:1.1rem;font-weight:700;margin-bottom:6px}
    .empty-state p{font-size:.85rem;color:#606770}

    /* ── Toast ───────────────────────────────────────── */
    #toast{position:fixed;bottom:24px;right:24px;background:#1c1e21;color:#fff;padding:10px 20px;border-radius:10px;font-size:.84rem;font-weight:500;opacity:0;transition:opacity .3s;pointer-events:none;z-index:9999}
    .notif-page{max-width:860px;margin:0 auto;padding:0}

    /* ── Clear All button ─────────────────────────────── */
    .clear-all-btn{background:#dc2626;color:#fff;padding:8px 16px;border-radius:8px;font-size:.83rem;font-weight:700;transition:opacity .15s;white-space:nowrap;border:none;cursor:pointer}
    .clear-all-btn:hover{opacity:.85}

    /* ── Undo toast ───────────────────────────────────── */
    #undo-toast{position:fixed;bottom:24px;left:50%;transform:translateX(-50%);background:#1e1e2e;color:#fff;padding:14px 24px;border-radius:12px;font-size:.88rem;font-weight:500;z-index:99999;display:flex;align-items:center;gap:14px;box-shadow:0 6px 28px rgba(0,0,0,.35);font-family:-apple-system,BlinkMacSystemFont,Segoe UI,Roboto,sans-serif}
    #undo-btn{background:#6c5ce7;color:#fff;border:none;border-radius:8px;padding:6px 18px;font-size:.84rem;font-weight:700;cursor:pointer;transition:opacity .15s}
    #undo-btn:hover{opacity:.85}
    #undo-timer{font-size:.78rem;color:#aaa;min-width:50px;text-align:right}

    /* ── Message truncation (3 lines) ────────────────── */
    .ni-msg{display:-webkit-box;-webkit-line-clamp:3;-webkit-box-orient:vertical;overflow:hidden;text-overflow:ellipsis}
    .notif-item{cursor:pointer}
    .notif-item .ni-expand{font-size:.76rem;color:#5c6ac4;font-weight:600;margin-top:2px;display:none}
    .notif-item .ni-msg.clamped ~ .ni-expand{display:inline-block}

    /* ── Split layout ────────────────────────────────── */
    .notif-page{max-width:none;margin:0;padding:0}
    .notif-split{display:flex;gap:0;min-height:calc(100vh - 160px)}
    .notif-list-col{flex:1 1 400px;min-width:340px;overflow-y:auto;max-height:calc(100vh - 160px)}

    /* ── Detail panel ─────────────────────────────────── */
    .detail-panel{width:0;min-width:0;overflow:hidden;opacity:0;transition:width .25s ease,opacity .2s ease,min-width .25s ease;background:#fff;border-left:1px solid #e9ebee;display:flex;flex-direction:column;border-radius:0 12px 12px 0}
    .notif-split.panel-open .detail-panel{width:800px;min-width:800px;opacity:1}
    .dp-header{display:flex;align-items:center;justify-content:space-between;padding:16px 20px;border-bottom:1px solid #e9ebee;flex-shrink:0}
    .dp-header-label{font-size:.88rem;font-weight:700;color:#1c1e21}
    .dp-close{background:none;border:none;font-size:1.1rem;color:#606770;cursor:pointer;width:32px;height:32px;border-radius:50%;display:flex;align-items:center;justify-content:center;transition:background .12s}
    .dp-close:hover{background:#f0f2f5}
    .dp-body{flex:1;overflow-y:auto;padding:24px 28px}
    .dp-placeholder{text-align:center;padding:60px 20px;color:#90949c;font-size:.88rem}

    /* Panel content styles */
    .dp-icon-row{display:flex;align-items:center;gap:12px;margin-bottom:16px}
    .dp-icon{width:48px;height:48px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:1.3rem;flex-shrink:0}
    .dp-title{font-size:1.05rem;font-weight:800;color:#1c1e21}
    .dp-prio{font-size:.72rem;font-weight:700;border:1px solid;border-radius:99px;padding:1px 8px;margin-left:8px}
    .dp-meta-row{display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin-bottom:16px;padding-bottom:14px;border-bottom:1px solid #f0f2f5}
    .dp-meta-row span{font-size:.78rem;color:#606770}
    .dp-meta-row .ni-type-tag{font-size:.74rem;font-weight:700;color:#5c6ac4;background:#ede8f5;border-radius:6px;padding:2px 8px}
    .dp-meta-row .meta-tag{font-size:.74rem;color:#606770;background:#f0f2f5;border-radius:6px;padding:2px 8px}
    .dp-full-msg{font-size:.92rem;color:#1c1e21;line-height:1.7;white-space:pre-wrap;word-break:break-word}
    .dp-action-row{margin-top:20px;padding-top:16px;border-top:1px solid #f0f2f5}

    /* Active card highlight */
    .notif-item.active-card{background:#f0f2ff !important;border-left-color:#5c6ac4 !important}

    /* ── Responsive: panel overlays on narrow screens ─ */
    @media(max-width:900px){
      .notif-split{position:relative}
      .detail-panel{position:absolute;right:0;top:0;bottom:0;z-index:100;box-shadow:-4px 0 24px rgba(0,0,0,.12);border-radius:0}
      .notif-split.panel-open .detail-panel{width:90vw;min-width:0}
    }
""",
            extra_js="""
// ── Category data (mirrors Python _TYPE_META) ────────────────────────
const TYPE_CAT = {
  complaint:'urgent', escalation:'urgent', sale:'urgent', lead:'urgent', support:'urgent',
  follow_suggestion:'opportunity', group_opportunity:'opportunity', competitor_alert:'opportunity', growth_report:'opportunity',
  content_idea:'intel', growth_tip:'intel',
  viral_alert:'win', milestone:'win',
  budget_alert:'health', sentiment_alert:'health', post:'health', system:'health'
};
const TYPE_ICONS = {
  complaint:'&#128545;', escalation:'&#9888;', sale:'&#128176;', lead:'&#128081;', support:'&#128172;',
  follow_suggestion:'&#128100;', group_opportunity:'&#128101;', competitor_alert:'&#128269;', growth_report:'&#128200;',
  content_idea:'&#10024;', growth_tip:'&#128161;',
  viral_alert:'&#128293;', milestone:'&#127942;',
  budget_alert:'&#9888;', sentiment_alert:'&#128201;', post:'&#128197;', system:'&#9881;'
};
const TYPE_LABELS = {
  complaint:'Customer Complaint', escalation:'Needs Your Attention', sale:'Sale Opportunity', lead:'New Lead', support:'Support Request',
  follow_suggestion:'Who to Follow', group_opportunity:'Group to Join', competitor_alert:'Competitor Activity', growth_report:'Daily Growth Report',
  content_idea:'Content Idea', growth_tip:'Growth Tip',
  viral_alert:'Going Viral!', milestone:'Milestone Reached',
  budget_alert:'Usage Limit Warning', sentiment_alert:'Negative Trend Detected', post:'Post Update', system:'System Alert'
};
const CAT_META = {
  urgent:      {icon:'&#128680;', label:'Urgent — Action Required',   color:'#dc2626'},
  opportunity: {icon:'&#128640;', label:'Growth Opportunities',       color:'#2563eb'},
  intel:       {icon:'&#129504;', label:'AI Intelligence',            color:'#7c3aed'},
  win:         {icon:'&#127881;', label:'Wins',                       color:'#16a34a'},
  health:      {icon:'&#129657;', label:'Account Health',             color:'#ea580c'},
};
const CAT_ORDER = ['urgent','opportunity','intel','win','health'];
const PRIO_COLORS = {critical:'#dc2626',high:'#ea580c',medium:'#2563eb',low:'#16a34a'};
const PRIO_LABELS = {critical:'Critical',high:'High',medium:'Medium',low:'Low'};

let _currentView = 'grouped';

// ── Toast helper ─────────────────────────────────────────────────────
function showToast(msg) {
  const t = document.getElementById('toast');
  t.textContent = msg;
  t.style.opacity = '1';
  setTimeout(() => { t.style.opacity = '0'; }, 2800);
}

// ── Auto-mark-as-read helpers ─────────────────────────────────────────
// Click anywhere on an unread notification card (not on buttons/links) to mark read
function _onNotifCardClick(e, notifId) {
  if (e.target.closest('button, a, .ni-action')) return;
  const row = document.getElementById('ni-' + notifId);
  if (!row || !row.classList.contains('unread')) return;
  markRead(notifId, null);
}

// (removed auto-mark-on-view — notifications are only marked read on click)
function _setupAutoMarkOnView() { return null; }
let _viewObserver = null;

// ── Acted-on recommendations cache (loaded once, survives re-renders) ──
let _actedOnMap = {};  // name.toLowerCase() -> action ("followed"|"dismissed")
let _actedOnLoaded = false;

async function _loadActedOn() {
  if (_actedOnLoaded) return;
  try {
    const resp = await fetch('/api/recommendations/acted-on');
    if (resp.ok) {
      const data = await resp.json();
      (data.items || []).forEach(item => {
        _actedOnMap[(item.name || '').toLowerCase()] = item.action;
      });
    }
  } catch(e) { console.warn('Could not load acted-on list', e); }
  _actedOnLoaded = true;
}

function _reattachObserver() {
  // After every render, replace buttons for already-acted-on recommendations
  if (!Object.keys(_actedOnMap).length) return;
  document.querySelectorAll('button[onclick*=\"recAction\"]').forEach(btn => {
    const name = (btn.getAttribute('data-name') || '').toLowerCase();
    if (!name || !_actedOnMap[name]) return;
    const act = _actedOnMap[name];
    const label = act === 'followed' ? '&#10003; Followed' : '&#10007; Dismissed';
    const color = act === 'followed' ? '#10b981' : '#9ca3af';
    btn.parentElement.innerHTML = '<span style=\"font-size:11px;color:' + color + ';font-weight:600\">' + label + '</span>';
  });
}

// Load acted-on data early, then trigger initial render fixup
_loadActedOn().then(() => {
  _reattachObserver();
});

// ── Log action click (mark read + record click) ───────────────────────
async function logActionClick(notifId) {
  try {
    await fetch('/api/notifications/' + notifId + '/action-click', {method:'POST'});
    const row = document.getElementById('ni-' + notifId);
    if (row) { row.classList.remove('unread'); row.classList.add('read'); }
    refreshBadge();
  } catch(e) { /* silent */ }
}

// ── Recommendation follow/dismiss action ──────────────────────────────
async function recAction(btn, action) {
  const name = btn.getAttribute('data-name');
  const url  = btn.getAttribute('data-url');
  const plat = btn.getAttribute('data-platform');
  if (!name) return;

  // Optimistic: update cache + UI immediately to prevent duplicate clicks
  _actedOnMap[name.toLowerCase()] = action;
  const label = action === 'followed' ? '&#10003; Followed' : '&#10007; Dismissed';
  const color = action === 'followed' ? '#10b981' : '#9ca3af';
  const wrapper = btn.parentElement;
  if (wrapper) wrapper.innerHTML = '<span style=\"font-size:11px;color:' + color + ';font-weight:600\">' + label + '</span>';

  // Find parent notification card to get notif ID (fall back to active panel)
  const card = (wrapper ? wrapper.closest('.notif-item') : null);
  const notifId = card ? card.getAttribute('data-id') : (_activePanelId || '');
  try {
    await fetch('/api/notifications/' + notifId + '/recommendation-action', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({action: action, name: name, url: url, platform: plat})
    });
  } catch(e) { console.error('recAction failed:', e); }
}

// ── Mark one as read ─────────────────────────────────────────────────
async function markRead(notifId, btn) {
  try {
    const resp = await fetch('/api/notifications/' + notifId + '/read', {method:'POST'});
    const data = await resp.json();
    if (!resp.ok || !data.ok) {
      console.error('mark-read failed for', notifId, 'response:', data);
      // Still update DOM optimistically but log the failure
    }
    const row = document.getElementById('ni-' + notifId);
    if (row) { row.classList.remove('unread'); row.classList.add('read'); }
    const actionDiv = btn ? btn.closest('.ni-action') : null;
    if (actionDiv) actionDiv.innerHTML = '<span class="read-badge">&#10003; Read</span>';
    if (data.ok) refreshBadge();
    else {
      // Force a fresh badge refresh even on failure so count stays accurate
      refreshBadge();
      if (!resp.ok) showToast('Error marking as read — try again');
    }
  } catch(e) { console.error('markRead error', e); showToast('Error — please try again'); }
}

// ── Mark all as read ─────────────────────────────────────────────────
async function markAllRead() {
  try {
    await fetch('/api/notifications/mark-all-read', {method:'POST'});
    document.querySelectorAll('.notif-item.unread').forEach(el => {
      el.classList.remove('unread'); el.classList.add('read');
      const btn = el.querySelector('.mark-read-btn');
      if (btn && btn.closest('.ni-action'))
        btn.closest('.ni-action').innerHTML = '<span class="read-badge">&#10003; Read</span>';
    });
    const markAllBtn = document.querySelector('.mark-all-btn');
    if (markAllBtn) markAllBtn.remove();
    const ucLabel = document.querySelector('.uc-label');
    if (ucLabel) { ucLabel.textContent = 'All caught up \\u2713'; ucLabel.classList.add('all-read'); }
    refreshBadge();
    showToast('All notifications marked as read');
  } catch(e) { showToast('Error — please try again'); }
}

// ── Set view (grouped / flat) ─────────────────────────────────────────
function setView(mode, btn) {
  closePanel();
  _currentView = mode;
  document.querySelectorAll('.view-btn').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  const filterBar = document.getElementById('filterBar');
  const list = document.getElementById('notifList');
  if (mode === 'flat') {
    filterBar.style.display = 'flex';
    list.classList.add('flat-mode');
    filterNotifs('all', document.querySelector('.filter-tab'));
  } else {
    filterBar.style.display = 'none';
    list.classList.remove('flat-mode');
    reloadGrouped();
  }
}

// ── Reload as grouped (category view) ────────────────────────────────
async function reloadGrouped(notifs) {
  if (!notifs) {
    try {
      const resp = await fetch('/api/notifications?limit=200');
      const data = await resp.json();
      notifs = data.notifications || [];
    } catch(e) { return; }
  }
  const list = document.getElementById('notifList');
  if (!notifs.length) {
    list.innerHTML = "<div class='empty-state'><div class='empty-icon'>&#128276;</div><h3>All caught up!</h3><p>No notifications yet.</p></div>";
    return;
  }
  // Group
  const groups = {};
  notifs.forEach(n => {
    const cat = TYPE_CAT[n.type] || 'health';
    if (!groups[cat]) groups[cat] = [];
    groups[cat].push(n);
  });
  let html = '';
  CAT_ORDER.forEach(cat => {
    const items = groups[cat] || [];
    if (!items.length) return;
    const cm = CAT_META[cat];
    html += '<div class="cat-section">'
      + '<div class="cat-header" style="border-left:4px solid ' + cm.color + '">'
      + '<span class="cat-icon">' + cm.icon + '</span>'
      + '<span class="cat-title" style="color:' + cm.color + '">' + cm.label + '</span>'
      + '<span class="cat-count">' + items.length + '</span>'
      + '</div><div class="cat-items">'
      + items.map(renderItem).join('')
      + '</div></div>';
  });
  list.innerHTML = html;
  _reattachObserver();
}

// ── Filter tabs (flat mode) ───────────────────────────────────────────
async function filterNotifs(type, tabEl) {
  document.querySelectorAll('.filter-tab').forEach(t => t.classList.remove('active'));
  if (tabEl) tabEl.classList.add('active');

  let url = '/api/notifications?limit=200';
  if (type === 'unread') url += '&unread_only=true';

  try {
    const resp = await fetch(url);
    const data = await resp.json();
    let notifs = data.notifications || [];
    // category group filters
    if (type.endsWith('_group')) {
      const cat = type.replace('_group','');
      notifs = notifs.filter(n => (TYPE_CAT[n.type]||'health') === cat);
    }
    renderFlatList(notifs);
  } catch(e) { console.error('Filter error', e); }
}

// ── Format a UTC ISO timestamp → 12-hr Eastern time ─────────────────
function _fmtTs(ts) {
  if (!ts) return '';
  try {
    const d = new Date(ts);
    return d.toLocaleString('en-US', {
      timeZone: 'America/New_York',
      month: 'short', day: 'numeric', year: 'numeric',
      hour: 'numeric', minute: '2-digit', hour12: true, timeZoneName: 'short'
    });
  } catch(e) { return ts.replace('T',' ').slice(0,16); }
}

// ── Render flat list ──────────────────────────────────────────────────
function renderFlatList(notifs) {
  const list = document.getElementById('notifList');
  if (!notifs || !notifs.length) {
    list.innerHTML = "<div class='empty-state'><div class='empty-icon'>&#128276;</div><h3>Nothing here</h3><p>No notifications match this filter.</p></div>";
    return;
  }
  list.innerHTML = notifs.map(renderItem).join('');
  _reattachObserver();
}

// ── Render one notification item (JS) ────────────────────────────────
function renderItem(n) {
  const typ      = n.type || 'system';
  const cat      = TYPE_CAT[typ] || 'health';
  const icon     = TYPE_ICONS[typ] || '&#128276;';
  const typeLabel = TYPE_LABELS[typ] || typ;
  const clr      = PRIO_COLORS[n.priority] || '#2563eb';
  const plbl     = PRIO_LABELS[n.priority] || 'Medium';
  const readCls  = n.read ? 'read' : 'unread';
  const ts       = _fmtTs(n.timestamp);
  const meta     = n.metadata || {};
  const platTag  = meta.platform ? '<span class="meta-tag">&#127760;&nbsp;' + meta.platform + '</span>' : '';
  const actionHtml = buildActionBtn(n);
  const readBtn  = n.read
    ? '<span class="read-badge">&#10003; Read</span>'
    : '<button class="mark-read-btn" onclick="markRead(\\'' + n.id + '\\', this)">&#10003; Read</button>';
  // Escape message for data attribute
  const safeMsg = (n.message||'').replace(/&/g,'&amp;').replace(/'/g,'&#39;').replace(/"/g,'&quot;').replace(/\\x3c/g,'&lt;');
  const safeTitle = (n.title||'Notification').replace(/&/g,'&amp;').replace(/'/g,'&#39;').replace(/"/g,'&quot;').replace(/\\x3c/g,'&lt;');
  const metaJson = JSON.stringify(meta).replace(/&/g,'&amp;').replace(/'/g,'&#39;').replace(/"/g,'&quot;').replace(/\\x3c/g,'&lt;');
  const plat = meta.platform || '';
  return (
    '<div class="notif-item ' + readCls + '" id="ni-' + n.id + '" data-id="' + n.id + '" data-type="' + typ + '" data-cat="' + cat + '"'
    + ' data-title="' + safeTitle.replace(/"/g,'&quot;') + '"'
    + ' data-msg="' + safeMsg.replace(/"/g,'&quot;') + '"'
    + ' data-prio="' + (n.priority||'medium') + '"'
    + ' data-ts="' + ts + '"'
    + ' data-icon="' + icon + '"'
    + ' data-icon-cls="' + typ + '"'
    + ' data-type-label="' + typeLabel + '"'
    + ' data-platform="' + plat + '"'
    + ' data-meta="' + metaJson + '"'
    + ' onclick="openPanel(\\'' + n.id + '\\')"'
    + '>'
    + '<div class="ni-icon ' + typ + '">' + icon + '</div>'
    + '<div class="ni-body">'
    + '<div class="ni-top"><span class="ni-title">' + (n.title||'Notification') + '</span>'
    + '<span class="ni-prio" style="color:' + clr + ';border-color:' + clr + '">' + plbl + '</span></div>'
    + '<div class="ni-msg">' + (n.message||'') + '</div>'
    + '<div class="ni-meta"><span class="ni-time">&#128336;&nbsp;' + ts + '</span>'
    + '<span class="ni-type-tag">' + typeLabel + '</span>' + platTag + '</div>'
    + actionHtml
    + '</div>'
    + '<div class="ni-action">' + readBtn + '</div>'
    + '</div>'
  );
}

// ── Build action button (JS) ─────────────────────────────────────────
function buildActionBtn(n) {
  const meta = n.metadata || {};
  if (!meta.action_url || !meta.action_label) return '';
  if (meta.action_clicked_at) return '';
  const target = (meta.action_type === 'open_url') ? '_blank" rel="noopener noreferrer' : '_self';
  return '<a href="' + meta.action_url + '" target="' + target
    + '" onclick="logActionClick(\\'' + n.id + '\\')" class="action-link-btn">'  
    + meta.action_label + '</a>';
}

// ── Refresh nav badge + header + tab badges ──────────────────────────
async function refreshBadge() {
  try {
    const resp = await fetch('/api/notifications?limit=200');
    if (resp.status === 401) { clearInterval(notifPagePoll); return; }
    const data = await resp.json();
    const cnt  = data.unread_count || 0;
    const notifs = data.notifications || [];

    // ── Sidebar nav badge ───────────────────────────────────────────
    const sidebarBadge = document.querySelector('.nav-item.active .nav-badge');
    if (cnt > 0) {
      if (sidebarBadge) { sidebarBadge.textContent = cnt; sidebarBadge.style.display = ''; }
      else {
        const navItem = document.querySelector('.nav-item.active');
        if (navItem) {
          const badge = document.createElement('span');
          badge.className = 'nav-badge'; badge.textContent = cnt; badge.style.display = '';
          navItem.appendChild(badge);
        }
      }
    } else {
      if (sidebarBadge) sidebarBadge.style.display = 'none';
    }

    // ── Header bell badge ───────────────────────────────────────────
    // Target the actual bell-dot element (id="bell-dot" in shared_layout)
    const bellDotEl = document.getElementById('bell-dot');
    if (bellDotEl) {
      if (cnt > 0) {
        bellDotEl.textContent = cnt > 99 ? '99+' : cnt;
        bellDotEl.style.display = '';
      } else {
        bellDotEl.style.display = 'none';
      }
    }

    // ── Page header count label ─────────────────────────────────────
    const ucLabel = document.querySelector('.uc-label');
    if (ucLabel) {
      if (cnt > 0) {
        ucLabel.textContent = cnt + ' unread';
        ucLabel.classList.remove('all-read');
      } else {
        ucLabel.textContent = 'All caught up \u2713';
        ucLabel.classList.add('all-read');
      }
    }

    // ── "Mark all as read" button visibility ─────────────────────────
    const markAllBtn = document.querySelector('.mark-all-btn');
    if (markAllBtn && cnt === 0) markAllBtn.remove();

    // ── Category tab badges ─────────────────────────────────────────
    const catCounts = {urgent:0, opportunity:0, intel:0, win:0, health:0};
    notifs.forEach(n => {
      if (!n.read) {
        const cat = TYPE_CAT[n.type] || 'health';
        catCounts[cat] = (catCounts[cat] || 0) + 1;
      }
    });
    const badgeMap = {
      urgent_group:'urgent', opportunity_group:'opportunity',
      intel_group:'intel', win_group:'win', health_group:'health'
    };
    document.querySelectorAll('.filter-tab').forEach(tab => {
      const onclick = tab.getAttribute('onclick') || '';
      const match = onclick.match(/filterNotifs\\('(\\w+_group)'/);
      if (!match) return;
      const groupKey = match[1];
      const catKey = badgeMap[groupKey];
      if (!catKey) return;
      let badge = tab.querySelector('.tab-badge');
      const count = catCounts[catKey] || 0;
      if (count > 0) {
        if (!badge) {
          badge = document.createElement('span');
          const cssMap = {opportunity:'opp', urgent:'urgent', intel:'intel', win:'win', health:'health'};
          badge.className = 'tab-badge ' + (cssMap[catKey] || catKey);
          tab.appendChild(badge);
        }
        badge.textContent = count;
      } else {
        if (badge) badge.remove();
      }
    });

  } catch(e) { /* silent */ }
}

// ── Clear all notifications (soft-delete) ─────────────────────────────
let _undoTimer = null;
let _undoCountdown = null;

async function clearAllNotifs() {
  closePanel();
  // Determine if we're in a filtered view — scope the clear to that category
  const activeTab = document.querySelector('.filter-tab.active');
  let category = null;
  let confirmMsg = 'Clear all notifications?  You can undo this within 24 hours.';

  if (_currentView === 'flat' && activeTab) {
    const onclick = activeTab.getAttribute('onclick') || '';
    const m = onclick.match(/filterNotifs\\('(\\w+)_group'/);
    if (m) {
      category = m[1];
      const catLabel = (CAT_META[category] || {}).label || category;
      confirmMsg = 'Clear all ' + catLabel + ' notifications?  You can undo this within 24 hours.';
    }
  }

  if (!confirm(confirmMsg)) return;
  try {
    const body = category ? JSON.stringify({category}) : '{}';
    const resp = await fetch('/api/notifications/clear-all', {
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body: body,
    });
    const data = await resp.json();
    if (!data.ok) { showToast('Error clearing notifications'); return; }

    // If clearing a specific category, just reload the current view
    if (category) {
      if (_currentView === 'grouped') {
        await reloadGrouped();
      } else {
        const tabToClick = activeTab || document.querySelector('.filter-tab');
        await filterNotifs(category + '_group', tabToClick);
      }
    } else {
      // Full clear — wipe the list
      document.getElementById('notifList').innerHTML =
        "<div class='empty-state'><div class='empty-icon'>&#128276;</div><h3>All caught up!</h3><p>No notifications.</p></div>";
      const markAllBtn = document.querySelector('.mark-all-btn');
      if (markAllBtn) markAllBtn.remove();
      const clearBtn = document.querySelector('.clear-all-btn');
      if (clearBtn) clearBtn.remove();
      const ucLabel = document.querySelector('.uc-label');
      if (ucLabel) { ucLabel.textContent = 'All caught up \u2713'; ucLabel.classList.add('all-read'); }
    }
    refreshBadge();

    // Show undo toast with countdown
    showUndoToast(data.cleared || 0);
  } catch(e) { showToast('Error — please try again'); }
}

function showUndoToast(count) {
  const toast = document.getElementById('undo-toast');
  document.getElementById('undo-msg').textContent = count + ' notification' + (count===1?'':'s') + ' cleared.';
  toast.style.display = 'flex';

  let secs = 30;
  document.getElementById('undo-timer').textContent = secs + 's';
  if (_undoCountdown) clearInterval(_undoCountdown);
  _undoCountdown = setInterval(() => {
    secs--;
    document.getElementById('undo-timer').textContent = secs + 's';
    if (secs <= 0) { clearInterval(_undoCountdown); toast.style.display = 'none'; }
  }, 1000);

  if (_undoTimer) clearTimeout(_undoTimer);
  _undoTimer = setTimeout(() => { toast.style.display = 'none'; }, 30000);
}

async function undoClear() {
  try {
    const resp = await fetch('/api/notifications/undo-clear', {method:'POST'});
    const data = await resp.json();
    if (!data.ok) { showToast('Could not undo — please try again'); return; }

    // Hide undo toast
    document.getElementById('undo-toast').style.display = 'none';
    if (_undoCountdown) clearInterval(_undoCountdown);
    if (_undoTimer) clearTimeout(_undoTimer);

    showToast((data.restored || 0) + ' notification' + ((data.restored||0)===1?'':'s') + ' restored!');

    // Reload list
    if (_currentView === 'grouped') {
      await reloadGrouped();
    } else {
      await filterNotifs('all', document.querySelector('.filter-tab'));
    }
    refreshBadge();
    // Re-add clear button if missing
    const hdr = document.querySelector('.page-header > div:last-child');
    if (hdr && !hdr.querySelector('.clear-all-btn')) {
      const btn = document.createElement('button');
      btn.className = 'clear-all-btn';
      btn.innerHTML = '&#128465;&nbsp; Clear All';
      btn.onclick = clearAllNotifs;
      hdr.appendChild(btn);
    }
  } catch(e) { showToast('Error — please try again'); }
}

// ── Poll unread every 60s ─────────────────────────────────────────────
let notifPagePoll = setInterval(refreshBadge, 60000);

// On page load: set up IntersectionObserver to auto-mark items visible on screen
document.addEventListener('DOMContentLoaded', () => { _setupAutoMarkOnView(); });

// ══════════════════════════════════════════════════════════════════════
// ── Detail Panel (Facebook Messenger–style slide-out) ────────────────
// ══════════════════════════════════════════════════════════════════════
let _activePanelId = null;

function openPanel(notifId) {
  // Don't open panel when clicking buttons or links inside the card
  if (event && event.target && event.target.closest('button, a, .ni-action')) return;

  // If clicking the already-open notification, just close
  if (_activePanelId === notifId) { closePanel(); return; }

  const card = document.getElementById('ni-' + notifId);
  if (!card) return;

  // Read data from card attributes
  const title     = card.getAttribute('data-title') || 'Notification';
  const message   = card.getAttribute('data-msg') || '';
  const prio      = card.getAttribute('data-prio') || 'medium';
  const ts        = card.getAttribute('data-ts') || '';
  const icon      = card.getAttribute('data-icon') || '&#128276;';
  const iconCls   = card.getAttribute('data-icon-cls') || 'system';
  const typeLabel = card.getAttribute('data-type-label') || '';
  const platform  = card.getAttribute('data-platform') || '';
  let meta = {};
  try { meta = JSON.parse(card.getAttribute('data-meta') || '{}'); } catch(e) {}

  const prioColor = PRIO_COLORS[prio] || '#2563eb';
  const prioLabel = PRIO_LABELS[prio] || 'Medium';

  // Build action button for panel
  let panelAction = '';
  if (meta.action_url && meta.action_label && !meta.action_clicked_at) {
    const tgt = meta.action_type === 'open_url' ? '_blank" rel="noopener noreferrer' : '_self';
    panelAction = '<div class="dp-action-row"><a href="' + meta.action_url + '" target="' + tgt
      + '" onclick="logActionClick(\\'' + notifId + '\\')" class="action-link-btn" style="font-size:.88rem;padding:10px 22px">' + meta.action_label + '</a></div>';
  }

  const platHtml = platform ? '<span class="meta-tag">&#127760;&nbsp;' + platform + '</span>' : '';

  // Populate panel
  document.getElementById('dpBody').innerHTML =
    '<div class="dp-icon-row">'
    + '<div class="dp-icon ' + iconCls + '">' + icon + '</div>'
    + '<div>'
    + '<span class="dp-title">' + title + '</span>'
    + '<span class="dp-prio" style="color:' + prioColor + ';border-color:' + prioColor + '">' + prioLabel + '</span>'
    + '</div></div>'
    + '<div class="dp-meta-row">'
    + '<span>&#128336;&nbsp;' + ts + '</span>'
    + '<span class="ni-type-tag">' + typeLabel + '</span>'
    + platHtml
    + '</div>'
    + '<div class="dp-full-msg">' + message + '</div>'
    + panelAction;

  // Show panel
  document.querySelector('.notif-split').classList.add('panel-open');
  _activePanelId = notifId;

  // Replace acted-on recommendation buttons in detail panel too
  _reattachObserver();

  // Highlight active card
  document.querySelectorAll('.notif-item.active-card').forEach(el => el.classList.remove('active-card'));
  card.classList.add('active-card');

  // Auto-mark as read
  if (card.classList.contains('unread')) {
    markRead(notifId, null);
  }

  // Scroll card into view in the list
  card.scrollIntoView({behavior:'smooth', block:'nearest'});
}

function closePanel() {
  document.querySelector('.notif-split').classList.remove('panel-open');
  document.querySelectorAll('.notif-item.active-card').forEach(el => el.classList.remove('active-card'));
  _activePanelId = null;
}

// Close panel on Escape key
document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape' && _activePanelId) closePanel();
});
""",
            user_name=user.full_name,
            business_name=profile.business_name,
        ))
    finally:
        db.close()
