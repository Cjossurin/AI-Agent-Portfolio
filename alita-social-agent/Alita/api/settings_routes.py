"""
api/settings_routes.py

Client-facing settings pages:
  GET/POST /settings/tone       – Style & tone setup (sample upload or preset)
  GET/POST /settings/knowledge  – Knowledge base management (add/view entries)
  GET      /settings/email      – Email inbox connect

All routes require an authenticated JWT session.
"""

import os
import json
import base64
from typing import Any, Dict, List, Optional
from datetime import datetime
from fastapi import APIRouter, BackgroundTasks, Request, Form, UploadFile, File, Query, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse

from api.auth_routes import require_auth
from database.db import get_db
from database.models import ClientProfile, TrustedDevice, WebAuthnCredential

router = APIRouter(prefix="/settings", tags=["settings"])


# ── Notification email toggles (per type) ───────────────────────────────────
_NOTIF_EMAIL_TYPES = [
    ("sale", "Sales / pricing inquiry"),
    ("lead", "New lead / interest"),
    ("complaint", "Complaint / negative experience"),
    ("escalation", "Escalation (urgent)"),
    ("support", "Support request"),
    ("follow_suggestion", "Follow suggestion"),
    ("group_opportunity", "Group opportunity"),
    ("competitor_alert", "Competitor alert"),
    ("content_idea", "Content idea"),
    ("growth_tip", "Growth tip"),
    ("viral_alert", "Viral alert"),
    ("milestone", "Milestone"),
    ("budget_alert", "Budget alert"),
    ("sentiment_alert", "Sentiment alert"),
    ("post", "Post / publishing alert"),
    ("system", "System notification"),
]


def _default_notif_email_prefs() -> dict:
    # Default: email notifications ON for all types.
    # (Clients can toggle off any they don't want.)
    return {k: True for k, _ in _NOTIF_EMAIL_TYPES}


def _load_notif_email_prefs(profile: Optional[ClientProfile]) -> dict:
    if not profile:
        return _default_notif_email_prefs()
    raw = getattr(profile, "notification_email_prefs_json", None)
    if not raw:
        return _default_notif_email_prefs()
    try:
        data = json.loads(raw)
        if isinstance(data, dict):
            merged = _default_notif_email_prefs()
            for k, v in data.items():
                if k in merged:
                    merged[k] = bool(v)
            return merged
    except Exception:
        pass
    return _default_notif_email_prefs()


def _save_notif_email_prefs(client_id: str, prefs: dict) -> bool:
    try:
        from database.db import SessionLocal
        _db = SessionLocal()
        try:
            _prof = _db.query(ClientProfile).filter(ClientProfile.client_id == client_id).first()
            if not _prof:
                return False
            _prof.notification_email_prefs_json = json.dumps(prefs)
            _db.commit()
            return True
        finally:
            _db.close()
    except Exception:
        return False

# ── Settings-specific CSS — does NOT re-define shared layout styles ────────
_SETTINGS_CSS = """
/* --- shared layout already supplies body, topbar, sidebar, card, btn-primary, btn-secondary --- */
/* These are extras specific to settings pages only */
label{display:block;font-size:.85rem;font-weight:600;color:#444;margin-bottom:6px;margin-top:14px}
label:first-of-type{margin-top:0}
textarea,input[type=text],input[type=url]{width:100%;padding:10px 14px;border:1.5px solid #dde0e4;
  border-radius:8px;font-size:.9rem;resize:vertical;outline:none;transition:border .15s;color:#1c1e21}
textarea:focus,input[type=text]:focus,input[type=url]:focus{border-color:#5c6ac4}
.s-label{display:block;font-size:.82rem;font-weight:600;color:#444;margin-bottom:6px;margin-top:16px}
.s-label:first-of-type{margin-top:0}
.s-input{width:100%;padding:10px 14px;border:1.5px solid #dde0e4;border-radius:8px;
         font-size:.88rem;color:#1c1e21;background:#fff;transition:border-color .15s;outline:none}
.s-input:focus{border-color:#5c6ac4;box-shadow:0 0 0 3px rgba(92,106,196,.1)}
textarea.s-input{resize:vertical;min-height:90px}
select.s-input{cursor:pointer}
.btn-danger{background:#fff0f0;color:#c0392b;border:1.5px solid #f5c5c0;border-radius:8px;
            padding:10px 20px;font-size:.88rem;font-weight:600;cursor:pointer;display:inline-block}
.btn-danger:hover{background:#ffe0e0}
.s-hr{border:none;border-top:1px solid #eee;margin:20px 0}
.notice{background:#fff8e1;border-left:4px solid #f9a825;padding:12px 16px;
        border-radius:0 8px 8px 0;font-size:.87rem;color:#795548;margin-bottom:20px}
.notice a{color:#5c6ac4}
hr{border:none;border-top:1px solid #eee;margin:20px 0}
/* preset grid */
.preset-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(165px,1fr));gap:12px;margin-top:4px}
.preset{border:2px solid #eee;border-radius:10px;padding:14px 16px;cursor:pointer;
        transition:all .15s;background:#fafafa}
.preset:hover,.preset.active{border-color:#5c6ac4;background:#f0f2ff}
.preset h4{font-size:.9rem;color:#1a1a2e;margin-bottom:4px}
.preset p{font-size:.78rem;color:#777;line-height:1.4}
/* pill */
.pill{display:inline-block;padding:3px 10px;border-radius:12px;font-size:.78rem;font-weight:600}
.pill-green{background:#e8f5e9;color:#2e7d32}
.pill-yellow{background:#fff8e1;color:#b8860b}
.pill-gray{background:#f0f0f0;color:#666}
/* entry list */
.entry{background:#f8f9fa;border-radius:8px;padding:14px 16px;margin-bottom:10px;
       display:flex;align-items:flex-start;gap:12px}
.entry-text{flex:1;font-size:.87rem;color:#333;line-height:1.5}
.entry-meta{font-size:.75rem;color:#999;white-space:nowrap}
.del-btn{background:none;border:none;color:#ccc;cursor:pointer;font-size:1rem;
         padding:2px 6px;border-radius:4px;transition:color .15s;flex-shrink:0}
.del-btn:hover{color:#c0392b}
/* FAQ generator */
.kb-tabs{display:flex;gap:8px;margin-bottom:24px;border-bottom:2px solid #eee}
.kb-tab{padding:10px 20px;font-size:.88rem;font-weight:600;border:none;background:none;
        cursor:pointer;color:#888;border-bottom:3px solid transparent;margin-bottom:-2px;transition:all .15s}
.kb-tab.active{color:#5c6ac4;border-bottom-color:#5c6ac4}
.faq-card{border:1px solid #e0e4ef;border-radius:10px;padding:16px 18px;margin-bottom:12px;
          background:#fff;transition:border .15s}
.faq-card.dup{border-color:#f5c5c0;background:#fff8f8}
.faq-card.added{border-color:#a5d6a7;background:#f1f8f1;opacity:.6}
.faq-q{font-weight:700;font-size:.9rem;color:#1a1a2e;margin-bottom:6px}
.faq-a{font-size:.87rem;color:#555;line-height:1.55}
.faq-footer{display:flex;align-items:center;gap:8px;margin-top:12px}
.dup-badge{font-size:.74rem;background:#fdecea;color:#c0392b;padding:3px 9px;
           border-radius:10px;font-weight:600}
.faq-spinner{display:none;text-align:center;padding:32px;color:#999;font-size:.9rem}
/* platform cards (tone + auto-reply) */
.plat-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:12px;margin-top:8px}
.plat-card{border:1.5px solid #eee;border-radius:10px;padding:14px 16px;cursor:pointer;
           transition:all .15s;background:#fafafa;display:flex;align-items:center;gap:12px}
.plat-card.on{border-color:#5c6ac4;background:#f0f2ff}
.plat-icon{font-size:1.3rem;flex-shrink:0}
.plat-card-info{flex:1}
.plat-card-name{font-weight:600;font-size:.9rem;color:#1c1e21}
.plat-card-sub{font-size:.76rem;color:#90949c;margin-top:2px}
/* toggle switch */
.sw{position:relative;display:inline-flex;width:46px;height:26px;flex-shrink:0}
.sw input{opacity:0;width:0;height:0;position:absolute}
.sw-track{position:absolute;cursor:pointer;inset:0;background:#ccc;border-radius:13px;transition:.25s}
.sw-track:before{content:"";position:absolute;width:20px;height:20px;left:3px;bottom:3px;
                 background:#fff;border-radius:50%;transition:.25s}
.sw input:checked ~ .sw-track{background:#5c6ac4}
.sw input:checked ~ .sw-track:before{transform:translateX(20px)}
/* auto-reply cards */
.ar-card{border:1.5px solid #e4e6eb;border-radius:12px;margin-bottom:14px;
         background:#fff;overflow:hidden;transition:border .15s}
.ar-card.ar-on{border-color:#5c6ac4}
.ar-head{display:flex;align-items:center;gap:14px;padding:18px 20px;cursor:pointer;
         background:#fafafa;user-select:none;transition:background .12s}
.ar-head.ar-on{background:#f0f2ff}
.ar-head-icon{font-size:1.4rem}
.ar-head-info{flex:1}
.ar-head-name{font-weight:700;font-size:.95rem;color:#1c1e21}
.ar-head-status{font-size:.78rem;color:#90949c;margin-top:2px}
.ar-body{padding:18px 20px;border-top:1px solid #eee;display:none;flex-direction:column;gap:14px}
.ar-body.open{display:flex}
.ar-row{display:grid;grid-template-columns:1fr 1fr;gap:12px}
.ar-mini{display:flex;align-items:center;gap:10px;padding:10px 14px;
         border:1.5px solid #eee;border-radius:8px;background:#fafafa;
         font-size:.87rem;font-weight:600;color:#444;cursor:pointer;transition:border .15s}
.ar-mini.on{border-color:#5c6ac4;background:#f0f2ff;color:#5c6ac4}
/* settings hub */
.hub-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(255px,1fr));gap:16px;margin-top:8px}
.hub-card{border:1.5px solid #e4e6eb;border-radius:12px;padding:22px 24px;background:#fff;
          transition:border .15s,box-shadow .15s;display:block;color:inherit;text-decoration:none}
.hub-card:hover{border-color:#5c6ac4;box-shadow:0 4px 16px rgba(92,106,196,.12);text-decoration:none}
.hub-icon{font-size:1.8rem;margin-bottom:12px}
.hub-title{font-weight:700;font-size:.95rem;color:#1c1e21;margin-bottom:5px}
.hub-desc{font-size:.82rem;color:#90949c;line-height:1.55}
.hub-section-title{font-size:.82rem;font-weight:700;color:#90949c;text-transform:uppercase;
                   letter-spacing:.07em;margin:28px 0 12px;display:flex;align-items:center;gap:8px}
/* adjustment tabs + pills */
.adj-tab{padding:8px 14px;border:none;background:none;font-size:.83rem;font-weight:600;
         color:#888;cursor:pointer;border-bottom:3px solid transparent;transition:all .12s;border-radius:6px 6px 0 0}
.adj-tab.active{color:#5c6ac4;border-bottom-color:#5c6ac4;background:#f0f2ff}
.adj-pills-row{display:flex;flex-wrap:wrap;gap:8px;min-height:44px;padding:10px 0}
.adj-pill{display:flex;align-items:center;gap:6px;background:#f0f2ff;border:1.5px solid #c5cce8;
          border-radius:20px;padding:4px 10px 4px 12px;font-size:.82rem;color:#3d4cb5;max-width:100%}
.adj-pill-text{flex:1;word-break:break-word;line-height:1.4}
.adj-pill-del{background:none;border:none;color:#9eaadb;cursor:pointer;font-size:.75rem;
              padding:0 4px;border-radius:50%;transition:color .1s;flex-shrink:0}
.adj-pill-del:hover{color:#c0392b}
/* humor intensity buttons */
.intensity-btn{padding:7px 16px;border:1.5px solid #dde0e4;border-radius:6px;background:#fff;
               color:#555;font-size:.85rem;font-weight:600;cursor:pointer;transition:all .12s}
.intensity-btn.active{border-color:#5c6ac4;background:#5c6ac4;color:#fff}
.comedian-label:hover{border-color:#5c6ac4 !important}
"""


# ── Auto-reply config helpers ─────────────────────────────────────────────────
_AR_DIR = "storage/auto_reply"

_AR_PLATFORMS = [
    ("instagram", "Instagram",  "📸", "DMs & Comments"),
    ("facebook",  "Facebook",   "📘", "Messages & Comments"),
    ("tiktok",    "TikTok",     "🎵", "Comments"),
    ("linkedin",  "LinkedIn",   "💼", "Messages & Comments"),
    ("twitter",   "Twitter / X","🐦", "Mentions & DMs"),
    ("threads",   "Threads",    "🧵", "Replies & DMs"),
]

_AR_DEFAULT_MSG = "Thanks for reaching out! We'll get back to you as soon as possible. 😊"


def _load_ar_prefs(client_id: str) -> dict:
    path = os.path.join(_AR_DIR, f"{client_id}.json")
    if os.path.exists(path):
        try:
            with open(path) as f:
                return json.load(f)
        except Exception:
            pass
    return {"platforms": {}}


def _save_ar_prefs(client_id: str, prefs: dict):
    os.makedirs(_AR_DIR, exist_ok=True)
    with open(os.path.join(_AR_DIR, f"{client_id}.json"), "w") as f:
        json.dump(prefs, f, indent=2)


# ── helper: get logged-in user + profile ──────────────────────────────
async def _get_profile(request: Request):
    from api.auth_routes import get_current_user
    db = next(get_db())
    try:
        user = get_current_user(request, db)
        if not user:
            return None, None, db
        profile = db.query(ClientProfile).filter(
            ClientProfile.user_id == user.id
        ).first()
        return user, profile, db
    except Exception:
        return None, None, db


# ══════════════════════════════════════════════════════════════════════
# SETTINGS HUB  (/settings)
# ══════════════════════════════════════════════════════════════════════

@router.get("", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse)
async def settings_hub(request: Request):
    """Main settings overview — grid of all settings sections."""
    user, profile, db = await _get_profile(request)
    db.close()
    if not user:
        return RedirectResponse("/account/login", status_code=303)

    hub_body = """
<p style="color:#90949c;font-size:.9rem;margin-bottom:24px">
  Manage every aspect of your Alita AI account from one place.
</p>

<div class="hub-section-title">&#9881; Configuration</div>
<div class="hub-grid">
  <a class="hub-card" href="/connect/dashboard">
    <div class="hub-icon">&#128241;</div>
    <div class="hub-title">Social Accounts</div>
    <div class="hub-desc">Connect Instagram, Facebook, TikTok, LinkedIn, Twitter/X, Threads &amp; YouTube.</div>
  </a>
  <a class="hub-card" href="/settings/auto-reply">
    <div class="hub-icon">&#129302;</div>
    <div class="hub-title">Auto-Reply</div>
    <div class="hub-desc">Set automatic replies for comments and DMs on every platform — with per-platform controls.</div>
  </a>
    <a class="hub-card" href="/settings/notifications">
        <div class="hub-icon">&#128276;</div>
        <div class="hub-title">Notifications</div>
        <div class="hub-desc">Control which email notifications you receive — per notification type.</div>
    </a>
  <a class="hub-card" href="/settings/tone">
    <div class="hub-icon">&#127897;</div>
    <div class="hub-title">Tone &amp; Style</div>
    <div class="hub-desc">Define your brand voice and choose which platforms it applies to.</div>
  </a>
  <a class="hub-card" href="/settings/knowledge">
    <div class="hub-icon">&#128218;</div>
    <div class="hub-title">Knowledge Base</div>
    <div class="hub-desc">Manage FAQs, business facts, and context your AI uses to respond accurately.</div>
  </a>
  <a class="hub-card" href="/settings/creative">
    <div class="hub-icon">&#127912;</div>
    <div class="hub-title">Creative Style</div>
    <div class="hub-desc">Upload brand reference images to guide AI-generated visuals and videos.</div>
  </a>
  <a class="hub-card" href="/email?tab=connect">
    <div class="hub-icon">&#128231;</div>
    <div class="hub-title">Email</div>
    <div class="hub-desc">Connect your email inbox — Gmail, Outlook, Yahoo, or any provider.</div>
  </a>
  <a class="hub-card" href="/settings/growth-interests">
    <div class="hub-icon">&#127793;</div>
    <div class="hub-title">Growth Interests</div>
    <div class="hub-desc">Set the topics and interests for your daily follow recommendations — override your niche.</div>
  </a>
</div>

<div class="hub-section-title">&#128179; Account</div>
<div class="hub-grid">
  <a class="hub-card" href="/billing">
    <div class="hub-icon">&#128179;</div>
    <div class="hub-title">Billing &amp; Plan</div>
    <div class="hub-desc">View your current plan, manage add-ons, and update payment details.</div>
  </a>
  <a class="hub-card" href="/settings/security">
    <div class="hub-icon">&#128274;</div>
    <div class="hub-title">Security</div>
    <div class="hub-desc">Two-factor authentication, trusted devices, and passkey management.</div>
  </a>
</div>
"""
    from utils.shared_layout import build_page
    return HTMLResponse(build_page(
        title="Settings",
        active_nav="settings",
        body_content=hub_body,
        extra_css=_SETTINGS_CSS,
        user_name=user.full_name,
        business_name=profile.business_name if profile else "",
        topbar_title="Settings",
    ))


# ══════════════════════════════════════════════════════════════════════
# NOTIFICATION SETTINGS  (/settings/notifications)
# ══════════════════════════════════════════════════════════════════════

@router.get("/notifications", response_class=HTMLResponse)
async def notifications_settings_page(request: Request):
        user, profile, db = await _get_profile(request)
        db.close()
        if not user:
                return RedirectResponse("/account/login", status_code=303)

        prefs = _load_notif_email_prefs(profile)

        rows = ""
        for key, label in _NOTIF_EMAIL_TYPES:
                checked = "checked" if prefs.get(key, True) else ""
                rows += f"""
<div class="entry" style="align-items:center">
    <div class="entry-text">
        <div style="font-weight:700;color:#1c1e21">{label}</div>
        <div style="font-size:.78rem;color:#90949c;margin-top:2px">Email notification</div>
    </div>
    <label class="sw" title="Toggle email notification">
        <input type="checkbox" id="notif-email-{key}" {checked}
                     onchange="setNotifEmail('{key}', this.checked)">
        <span class="sw-track"></span>
    </label>
</div>
"""

        body = f"""
<p style="color:#90949c;font-size:.88rem;margin-bottom:12px">
    Toggle which <strong>email</strong> notifications you receive. These settings do not affect in-app dashboard notifications.
</p>
<div class="notice" style="margin-bottom:18px">
    Emails send to your signup address: <strong>{user.email}</strong>
</div>
<div id="notif-save-status" style="display:none;margin-bottom:16px;font-size:.82rem;color:#90949c"></div>

{rows}

<div style="margin-top:24px;display:flex;gap:12px;align-items:center">
    <a href="/settings" class="btn-secondary">Back to Settings</a>
</div>
"""

        js = r"""
async function setNotifEmail(typeKey, enabled) {
    const status = document.getElementById('notif-save-status');
    if (status) {
        status.style.display = 'block';
        status.textContent = 'Saving…';
    }
    try {
        const res = await fetch('/settings/notifications/email', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ type: typeKey, enabled: !!enabled })
        });
        const data = await res.json().catch(() => ({}));
        if (!res.ok || !data.ok) {
            throw new Error(data.error || 'Save failed');
        }
        if (status) {
            status.textContent = 'Saved';
            setTimeout(() => { status.style.display = 'none'; }, 1200);
        }
    } catch (e) {
        const cb = document.getElementById('notif-email-' + typeKey);
        if (cb) cb.checked = !enabled;
        if (status) {
            status.textContent = 'Could not save. Please try again.';
        }
    }
}
"""

        from utils.shared_layout import build_page
        return HTMLResponse(build_page(
                title="Notification Settings",
                active_nav="notifications",
                body_content=body,
                extra_css=_SETTINGS_CSS,
                extra_js=js,
                user_name=user.full_name,
                business_name=profile.business_name if profile else "",
                topbar_title="Notification Settings",
        ))


@router.get("/notifications/email")
async def notifications_email_get(request: Request):
    user, profile, db = await _get_profile(request)
    db.close()
    if not user:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)
    return JSONResponse({"ok": True, "prefs": _load_notif_email_prefs(profile)})


@router.post("/notifications/email")
async def notifications_email_set(request: Request):
    user, profile, db = await _get_profile(request)
    db.close()
    if not user or not profile:
        return JSONResponse({"ok": False, "error": "Not authenticated"}, status_code=401)

    try:
        payload = await request.json()
    except Exception:
        payload = {}

    type_key = (payload.get("type") or "").strip()
    enabled = payload.get("enabled", None)

    allowed = {k for k, _ in _NOTIF_EMAIL_TYPES}
    if type_key not in allowed:
        return JSONResponse({"ok": False, "error": "Unknown notification type"}, status_code=400)
    if enabled is None:
        return JSONResponse({"ok": False, "error": "Missing enabled"}, status_code=400)

    prefs = _load_notif_email_prefs(profile)
    prefs[type_key] = bool(enabled)

    if not _save_notif_email_prefs(profile.client_id, prefs):
        return JSONResponse({"ok": False, "error": "Save failed"}, status_code=500)

    return JSONResponse({"ok": True})


# ══════════════════════════════════════════════════════════════════════
# AUTO-REPLY SETTINGS  (/settings/auto-reply)
# ══════════════════════════════════════════════════════════════════════

@router.get("/auto-reply", response_class=HTMLResponse)
async def auto_reply_page(request: Request):
    user, profile, db = await _get_profile(request)
    db.close()
    if not user:
        return RedirectResponse("/account/login", status_code=303)

    prefs  = _load_ar_prefs(profile.client_id)
    platforms_cfg = prefs.get("platforms", {})
    msg = request.query_params.get("msg", "")
    success_banner = (
        f'<div style="background:#e8f5e9;border-left:4px solid #27ae60;padding:12px 16px;'
        f'border-radius:0 8px 8px 0;margin-bottom:20px;font-size:.88rem;color:#2e7d32">{msg}</div>'
    ) if msg else ""

    # Build platform cards
    cards_html = ""
    for plat_key, plat_label, plat_icon, plat_hint in _AR_PLATFORMS:
        cfg       = platforms_cfg.get(plat_key, {})
        enabled   = cfg.get("enabled", False)
        comments  = cfg.get("comments", True)
        dms       = cfg.get("dms", True)
        delay     = cfg.get("delay_minutes", 1)
        fallback  = cfg.get("fallback_message", _AR_DEFAULT_MSG)
        card_cls  = "ar-card ar-on" if enabled else "ar-card"
        head_cls  = "ar-head ar-on" if enabled else "ar-head"
        body_cls  = "ar-body open" if enabled else "ar-body"
        status_str = "Active" if enabled else "Off"
        delay_opts = ""
        for val, lbl in [(0,"Instant"),(1,"1 min"),(5,"5 min"),(15,"15 min"),(30,"30 min")]:
            sel = "selected" if delay == val else ""
            delay_opts += f'<option value="{val}" {sel}>{lbl}</option>'
        comm_cls = "ar-mini on" if comments else "ar-mini"
        dm_cls   = "ar-mini on" if dms else "ar-mini"
        sw_checked_en = "checked" if enabled else ""
        sw_checked_co = "checked" if comments else ""
        sw_checked_dm = "checked" if dms else ""

        cards_html += f"""
<div class="{card_cls}" id="ar-{plat_key}">
  <div class="{head_cls}" onclick="toggleAR('{plat_key}')">
    <div class="ar-head-icon">{plat_icon}</div>
    <div class="ar-head-info">
      <div class="ar-head-name">{plat_label}</div>
      <div class="ar-head-status" id="ar-status-{plat_key}">{plat_hint} &middot; {status_str}</div>
    </div>
    <label class="sw" onclick="event.stopPropagation()" title="Enable auto-reply for {plat_label}">
      <input type="checkbox" name="{plat_key}_enabled" value="1" {sw_checked_en}
             onchange="onEnableChange('{plat_key}', this)">
      <span class="sw-track"></span>
    </label>
  </div>
  <div class="{body_cls}" id="ar-body-{plat_key}">
    <div class="ar-row">
      <label class="{comm_cls}" id="ar-comm-lbl-{plat_key}"
             onclick="toggleMini('{plat_key}','comments')">
        <label class="sw" onclick="event.stopPropagation()">
          <input type="checkbox" name="{plat_key}_comments" value="1" {sw_checked_co}
                 id="ar-comments-{plat_key}">
          <span class="sw-track"></span>
        </label>
        &#128172; Auto-reply Comments
      </label>
      <label class="{dm_cls}" id="ar-dm-lbl-{plat_key}"
             onclick="toggleMini('{plat_key}','dms')">
        <label class="sw" onclick="event.stopPropagation()">
          <input type="checkbox" name="{plat_key}_dms" value="1" {sw_checked_dm}
                 id="ar-dms-{plat_key}">
          <span class="sw-track"></span>
        </label>
        &#128232; Auto-reply DMs
      </label>
    </div>
    <div>
      <label class="s-label">Reply Delay</label>
      <select name="{plat_key}_delay" class="s-input"
              style="max-width:200px;display:inline-block">
        {delay_opts}
      </select>
      <span style="font-size:.8rem;color:#90949c;margin-left:8px">after message arrives</span>
    </div>
    <div>
      <label class="s-label">Fallback Message</label>
      <textarea name="{plat_key}_fallback" class="s-input" rows="2"
                placeholder="Default reply when AI can't find a specific answer...">{fallback}</textarea>
      <p style="font-size:.76rem;color:#90949c;margin-top:4px">
        This message is sent when your AI doesn't find a relevant answer in the Knowledge Base.
      </p>
    </div>
  </div>
</div>"""

    ar_js = r"""
function toggleAR(key) {
  const body = document.getElementById('ar-body-' + key);
  if (body) body.classList.toggle('open');
}
function onEnableChange(key, cb) {
  const card = document.getElementById('ar-' + key);
  const head = card ? card.querySelector('.ar-head') : null;
  const status = document.getElementById('ar-status-' + key);
  const body = document.getElementById('ar-body-' + key);
  if (cb.checked) {
    if (card) card.classList.add('ar-on');
    if (head) head.classList.add('ar-on');
    if (body) body.classList.add('open');
    if (status) { const old = status.textContent.replace(' · Off','').replace(' · Active',''); status.textContent = old + ' · Active'; }
  } else {
    if (card) card.classList.remove('ar-on');
    if (head) head.classList.remove('ar-on');
    if (body) body.classList.remove('open');
    if (status) { const old = status.textContent.replace(' · Off','').replace(' · Active',''); status.textContent = old + ' · Off'; }
  }
}
function toggleMini(key, type) {
  const cb = document.getElementById('ar-' + type + '-' + key);
  if (!cb) return;
  cb.checked = !cb.checked;
  const lbl = document.getElementById('ar-' + (type === 'comments' ? 'comm' : 'dm') + '-lbl-' + key);
  if (lbl) lbl.classList.toggle('on', cb.checked);
}
"""

    ar_body = f"""
{success_banner}
<p style="color:#90949c;font-size:.88rem;margin-bottom:20px">
  Control automatic replies per platform. Toggle each platform on to activate AI replies.
  Your <a href="/settings/tone" style="color:#5c6ac4">tone settings</a> and
  <a href="/settings/knowledge" style="color:#5c6ac4">knowledge base</a> power every reply.
</p>
<form method="post" action="/settings/auto-reply" id="ar-form">
{cards_html}
  <div style="margin-top:24px;display:flex;gap:12px;align-items:center">
    <button type="submit" class="btn-primary">Save All Auto-Reply Settings</button>
    <a href="/settings" class="btn-secondary">Back to Settings</a>
  </div>
</form>
"""
    from utils.shared_layout import build_page
    return HTMLResponse(build_page(
        title="Auto-Reply Settings",
        active_nav="auto-reply",
        body_content=ar_body,
        extra_css=_SETTINGS_CSS,
        extra_js=ar_js,
        user_name=user.full_name,
        business_name=profile.business_name if profile else "",
        topbar_title="Auto-Reply Settings",
    ))


@router.post("/auto-reply", response_class=HTMLResponse)
async def auto_reply_save(request: Request):
    user, profile, db = await _get_profile(request)
    db.close()
    if not user:
        return RedirectResponse("/account/login", status_code=303)

    form = await request.form()
    platforms_cfg = {}
    for plat_key, *_ in _AR_PLATFORMS:
        platforms_cfg[plat_key] = {
            "enabled":          form.get(f"{plat_key}_enabled") == "1",
            "comments":         form.get(f"{plat_key}_comments") == "1",
            "dms":              form.get(f"{plat_key}_dms") == "1",
            "delay_minutes":    int(form.get(f"{plat_key}_delay", 1) or 1),
            "fallback_message": (form.get(f"{plat_key}_fallback") or _AR_DEFAULT_MSG).strip(),
        }

    _save_ar_prefs(profile.client_id, {"platforms": platforms_cfg})
    enabled_count = sum(1 for v in platforms_cfg.values() if v["enabled"])
    return RedirectResponse(
        f"/settings/auto-reply?msg=Saved!+{enabled_count}+platform(s)+active",
        status_code=303,
    )


# ══════════════════════════════════════════════════════════════════════
# TONE / STYLE SETUP
# ══════════════════════════════════════════════════════════════════════

PRESET_TONES = {
    "professional": {
        "label": "Professional",
        "desc": "Polished and authoritative. Best for B2B, finance, legal.",
        "system": "Respond in a professional, authoritative tone. Use complete sentences. Avoid slang.",
    },
    "conversational": {
        "label": "Conversational",
        "desc": "Friendly and approachable. Great for service businesses.",
        "system": "Respond in a warm, conversational tone. Short sentences. Feels human.",
    },
    "playful": {
        "label": "Playful",
        "desc": "Fun and energetic. Perfect for lifestyle, fashion, food.",
        "system": "Respond with energy and personality. Use emojis sparingly. Keep it fun.",
    },
    "educational": {
        "label": "Educational",
        "desc": "Clear and informative. Best for coaches, consultants.",
        "system": "Respond in a clear, educational tone. Explain concepts simply. Use examples.",
    },
    "bold": {
        "label": "Bold & Direct",
        "desc": "Confident and punchy. Great for fitness, entrepreneurs.",
        "system": "Respond boldly and directly. Short punchy sentences. No fluff.",
    },
    "empathetic": {
        "label": "Empathetic",
        "desc": "Warm and understanding. Health, wellness, support.",
        "system": "Respond with warmth and empathy. Acknowledge feelings first. Be supportive.",
    },
}

TONE_PREFS_DIR = "style_references"

# ── Per-provider IMAP/SMTP defaults (used by /email/detect-provider) ─────────
PROVIDER_IMAP_CONFIG = {
    "gmail.com":      {"provider": "gmail",   "label": "Gmail"},
    "googlemail.com": {"provider": "gmail",   "label": "Gmail"},
    "outlook.com":    {"provider": "outlook", "label": "Outlook",
                       "imap_host": "outlook.office365.com", "imap_port": 993,
                       "smtp_host": "smtp-mail.outlook.com",  "smtp_port": 587,
                       "app_password_url": "https://account.microsoft.com/security",
                       "instructions": "Enable 2-step verification at account.microsoft.com, then create an App password under Security."},
    "hotmail.com":    {"provider": "outlook", "label": "Outlook (Hotmail)",
                       "imap_host": "outlook.office365.com", "imap_port": 993,
                       "smtp_host": "smtp-mail.outlook.com",  "smtp_port": 587,
                       "app_password_url": "https://account.microsoft.com/security",
                       "instructions": "Enable 2-step verification at account.microsoft.com, then create an App password under Security."},
    "live.com":       {"provider": "outlook", "label": "Outlook (Live)",
                       "imap_host": "outlook.office365.com", "imap_port": 993,
                       "smtp_host": "smtp-mail.outlook.com",  "smtp_port": 587,
                       "app_password_url": "https://account.microsoft.com/security",
                       "instructions": "Enable 2-step verification at account.microsoft.com, then create an App password under Security."},
    "msn.com":        {"provider": "outlook", "label": "Outlook (MSN)",
                       "imap_host": "outlook.office365.com", "imap_port": 993,
                       "smtp_host": "smtp-mail.outlook.com",  "smtp_port": 587,
                       "app_password_url": "https://account.microsoft.com/security",
                       "instructions": "Enable 2-step verification at account.microsoft.com, then create an App password under Security."},
    "yahoo.com":      {"provider": "yahoo",   "label": "Yahoo Mail",
                       "imap_host": "imap.mail.yahoo.com",   "imap_port": 993,
                       "smtp_host": "smtp.mail.yahoo.com",    "smtp_port": 587,
                       "app_password_url": "https://login.yahoo.com/account/security",
                       "instructions": "Go to Yahoo Account Security, enable 2-step verification, then generate an App Password."},
    "ymail.com":      {"provider": "yahoo",   "label": "Yahoo Mail",
                       "imap_host": "imap.mail.yahoo.com",   "imap_port": 993,
                       "smtp_host": "smtp.mail.yahoo.com",    "smtp_port": 587,
                       "app_password_url": "https://login.yahoo.com/account/security",
                       "instructions": "Go to Yahoo Account Security, enable 2-step verification, then generate an App Password."},
    "icloud.com":     {"provider": "icloud",  "label": "iCloud Mail",
                       "imap_host": "imap.mail.me.com",      "imap_port": 993,
                       "smtp_host": "smtp.mail.me.com",       "smtp_port": 587,
                       "app_password_url": "https://appleid.apple.com/sign-in",
                       "instructions": "Go to appleid.apple.com \u2192 Security, then create an App-Specific Password."},
    "me.com":         {"provider": "icloud",  "label": "iCloud Mail",
                       "imap_host": "imap.mail.me.com",      "imap_port": 993,
                       "smtp_host": "smtp.mail.me.com",       "smtp_port": 587,
                       "app_password_url": "https://appleid.apple.com/sign-in",
                       "instructions": "Go to appleid.apple.com \u2192 Security, then create an App-Specific Password."},
    "mac.com":        {"provider": "icloud",  "label": "iCloud Mail",
                       "imap_host": "imap.mail.me.com",      "imap_port": 993,
                       "smtp_host": "smtp.mail.me.com",       "smtp_port": 587,
                       "app_password_url": "https://appleid.apple.com/sign-in",
                       "instructions": "Go to appleid.apple.com \u2192 Security, then create an App-Specific Password."},
    "zoho.com":       {"provider": "zoho",    "label": "Zoho Mail",
                       "imap_host": "imap.zoho.com",         "imap_port": 993,
                       "smtp_host": "smtp.zoho.com",          "smtp_port": 587,
                       "app_password_url": "https://accounts.zoho.com/home#security",
                       "instructions": "Go to Zoho Account \u2192 Security \u2192 App Passwords to create one."},
    "zohomail.com":   {"provider": "zoho",    "label": "Zoho Mail",
                       "imap_host": "imap.zoho.com",         "imap_port": 993,
                       "smtp_host": "smtp.zoho.com",          "smtp_port": 587,
                       "app_password_url": "https://accounts.zoho.com/home#security",
                       "instructions": "Go to Zoho Account \u2192 Security \u2192 App Passwords to create one."},
    "protonmail.com": {"provider": "proton",  "label": "Proton Mail",
                       "imap_host": "127.0.0.1",             "imap_port": 1143,
                       "smtp_host": "127.0.0.1",              "smtp_port": 1025,
                       "app_password_url": "https://proton.me/support/proton-mail-bridge",
                       "instructions": "Proton Mail requires the Proton Mail Bridge app to be installed and running. Download it from proton.me/mail/bridge."},
    "pm.me":          {"provider": "proton",  "label": "Proton Mail",
                       "imap_host": "127.0.0.1",             "imap_port": 1143,
                       "smtp_host": "127.0.0.1",              "smtp_port": 1025,
                       "app_password_url": "https://proton.me/support/proton-mail-bridge",
                       "instructions": "Proton Mail requires the Proton Mail Bridge app to be installed and running. Download it from proton.me/mail/bridge."},
    "proton.me":      {"provider": "proton",  "label": "Proton Mail",
                       "imap_host": "127.0.0.1",             "imap_port": 1143,
                       "smtp_host": "127.0.0.1",              "smtp_port": 1025,
                       "app_password_url": "https://proton.me/support/proton-mail-bridge",
                       "instructions": "Proton Mail requires the Proton Mail Bridge app to be installed and running. Download it from proton.me/mail/bridge."},
    # ── AOL / AIM ──────────────────────────────────────────────────────────
    "aol.com":        {"provider": "aol",     "label": "AOL Mail",
                       "imap_host": "imap.aol.com",          "imap_port": 993,
                       "smtp_host": "smtp.aol.com",           "smtp_port": 587,
                       "app_password_url": "https://login.aol.com/account/security",
                       "instructions": "Go to AOL Account Security, enable 2-step verification, then generate an App Password."},
    "aim.com":        {"provider": "aol",     "label": "AOL Mail (AIM)",
                       "imap_host": "imap.aol.com",          "imap_port": 993,
                       "smtp_host": "smtp.aol.com",           "smtp_port": 587,
                       "app_password_url": "https://login.aol.com/account/security",
                       "instructions": "Go to AOL Account Security, enable 2-step verification, then generate an App Password."},
    "verizon.net":    {"provider": "aol",     "label": "Verizon Mail (AOL)",
                       "imap_host": "imap.aol.com",          "imap_port": 993,
                       "smtp_host": "smtp.aol.com",           "smtp_port": 587,
                       "app_password_url": "https://login.aol.com/account/security",
                       "instructions": "Verizon email is now managed by AOL. Go to AOL Account Security to generate an App Password."},
    # ── Yahoo regional + legacy ────────────────────────────────────────────
    "rocketmail.com": {"provider": "yahoo",   "label": "Yahoo Mail (Rocketmail)",
                       "imap_host": "imap.mail.yahoo.com",   "imap_port": 993,
                       "smtp_host": "smtp.mail.yahoo.com",    "smtp_port": 587,
                       "app_password_url": "https://login.yahoo.com/account/security",
                       "instructions": "Go to Yahoo Account Security, enable 2-step verification, then generate an App Password."},
    "yahoo.co.uk":    {"provider": "yahoo",   "label": "Yahoo Mail",
                       "imap_host": "imap.mail.yahoo.com",   "imap_port": 993,
                       "smtp_host": "smtp.mail.yahoo.com",    "smtp_port": 587,
                       "app_password_url": "https://login.yahoo.com/account/security",
                       "instructions": "Go to Yahoo Account Security, enable 2-step verification, then generate an App Password."},
    "yahoo.co.in":    {"provider": "yahoo",   "label": "Yahoo Mail",
                       "imap_host": "imap.mail.yahoo.com",   "imap_port": 993,
                       "smtp_host": "smtp.mail.yahoo.com",    "smtp_port": 587,
                       "app_password_url": "https://login.yahoo.com/account/security",
                       "instructions": "Go to Yahoo Account Security, enable 2-step verification, then generate an App Password."},
    "yahoo.ca":       {"provider": "yahoo",   "label": "Yahoo Mail",
                       "imap_host": "imap.mail.yahoo.com",   "imap_port": 993,
                       "smtp_host": "smtp.mail.yahoo.com",    "smtp_port": 587,
                       "app_password_url": "https://login.yahoo.com/account/security",
                       "instructions": "Go to Yahoo Account Security, enable 2-step verification, then generate an App Password."},
    "yahoo.com.au":   {"provider": "yahoo",   "label": "Yahoo Mail",
                       "imap_host": "imap.mail.yahoo.com",   "imap_port": 993,
                       "smtp_host": "smtp.mail.yahoo.com",    "smtp_port": 587,
                       "app_password_url": "https://login.yahoo.com/account/security",
                       "instructions": "Go to Yahoo Account Security, enable 2-step verification, then generate an App Password."},
    "yahoo.com.br":   {"provider": "yahoo",   "label": "Yahoo Mail",
                       "imap_host": "imap.mail.yahoo.com",   "imap_port": 993,
                       "smtp_host": "smtp.mail.yahoo.com",    "smtp_port": 587,
                       "app_password_url": "https://login.yahoo.com/account/security",
                       "instructions": "Go to Yahoo Account Security, enable 2-step verification, then generate an App Password."},
    "yahoo.co.jp":    {"provider": "yahoo",   "label": "Yahoo Mail",
                       "imap_host": "imap.mail.yahoo.com",   "imap_port": 993,
                       "smtp_host": "smtp.mail.yahoo.com",    "smtp_port": 587,
                       "app_password_url": "https://login.yahoo.com/account/security",
                       "instructions": "Go to Yahoo Account Security, enable 2-step verification, then generate an App Password."},
    "yahoo.de":       {"provider": "yahoo",   "label": "Yahoo Mail",
                       "imap_host": "imap.mail.yahoo.com",   "imap_port": 993,
                       "smtp_host": "smtp.mail.yahoo.com",    "smtp_port": 587,
                       "app_password_url": "https://login.yahoo.com/account/security",
                       "instructions": "Go to Yahoo Account Security, enable 2-step verification, then generate an App Password."},
    "yahoo.fr":       {"provider": "yahoo",   "label": "Yahoo Mail",
                       "imap_host": "imap.mail.yahoo.com",   "imap_port": 993,
                       "smtp_host": "smtp.mail.yahoo.com",    "smtp_port": 587,
                       "app_password_url": "https://login.yahoo.com/account/security",
                       "instructions": "Go to Yahoo Account Security, enable 2-step verification, then generate an App Password."},
    "yahoo.it":       {"provider": "yahoo",   "label": "Yahoo Mail",
                       "imap_host": "imap.mail.yahoo.com",   "imap_port": 993,
                       "smtp_host": "smtp.mail.yahoo.com",    "smtp_port": 587,
                       "app_password_url": "https://login.yahoo.com/account/security",
                       "instructions": "Go to Yahoo Account Security, enable 2-step verification, then generate an App Password."},
    # ── Outlook / Hotmail / Live regional ──────────────────────────────────
    "outlook.co.uk":  {"provider": "outlook", "label": "Outlook",
                       "imap_host": "outlook.office365.com", "imap_port": 993,
                       "smtp_host": "smtp-mail.outlook.com",  "smtp_port": 587,
                       "app_password_url": "https://account.microsoft.com/security",
                       "instructions": "Enable 2-step verification at account.microsoft.com, then create an App password under Security."},
    "outlook.de":     {"provider": "outlook", "label": "Outlook",
                       "imap_host": "outlook.office365.com", "imap_port": 993,
                       "smtp_host": "smtp-mail.outlook.com",  "smtp_port": 587,
                       "app_password_url": "https://account.microsoft.com/security",
                       "instructions": "Enable 2-step verification at account.microsoft.com, then create an App password under Security."},
    "outlook.fr":     {"provider": "outlook", "label": "Outlook",
                       "imap_host": "outlook.office365.com", "imap_port": 993,
                       "smtp_host": "smtp-mail.outlook.com",  "smtp_port": 587,
                       "app_password_url": "https://account.microsoft.com/security",
                       "instructions": "Enable 2-step verification at account.microsoft.com, then create an App password under Security."},
    "outlook.es":     {"provider": "outlook", "label": "Outlook",
                       "imap_host": "outlook.office365.com", "imap_port": 993,
                       "smtp_host": "smtp-mail.outlook.com",  "smtp_port": 587,
                       "app_password_url": "https://account.microsoft.com/security",
                       "instructions": "Enable 2-step verification at account.microsoft.com, then create an App password under Security."},
    "outlook.it":     {"provider": "outlook", "label": "Outlook",
                       "imap_host": "outlook.office365.com", "imap_port": 993,
                       "smtp_host": "smtp-mail.outlook.com",  "smtp_port": 587,
                       "app_password_url": "https://account.microsoft.com/security",
                       "instructions": "Enable 2-step verification at account.microsoft.com, then create an App password under Security."},
    "hotmail.co.uk":  {"provider": "outlook", "label": "Outlook (Hotmail)",
                       "imap_host": "outlook.office365.com", "imap_port": 993,
                       "smtp_host": "smtp-mail.outlook.com",  "smtp_port": 587,
                       "app_password_url": "https://account.microsoft.com/security",
                       "instructions": "Enable 2-step verification at account.microsoft.com, then create an App password under Security."},
    "hotmail.fr":     {"provider": "outlook", "label": "Outlook (Hotmail)",
                       "imap_host": "outlook.office365.com", "imap_port": 993,
                       "smtp_host": "smtp-mail.outlook.com",  "smtp_port": 587,
                       "app_password_url": "https://account.microsoft.com/security",
                       "instructions": "Enable 2-step verification at account.microsoft.com, then create an App password under Security."},
    "hotmail.de":     {"provider": "outlook", "label": "Outlook (Hotmail)",
                       "imap_host": "outlook.office365.com", "imap_port": 993,
                       "smtp_host": "smtp-mail.outlook.com",  "smtp_port": 587,
                       "app_password_url": "https://account.microsoft.com/security",
                       "instructions": "Enable 2-step verification at account.microsoft.com, then create an App password under Security."},
    "hotmail.it":     {"provider": "outlook", "label": "Outlook (Hotmail)",
                       "imap_host": "outlook.office365.com", "imap_port": 993,
                       "smtp_host": "smtp-mail.outlook.com",  "smtp_port": 587,
                       "app_password_url": "https://account.microsoft.com/security",
                       "instructions": "Enable 2-step verification at account.microsoft.com, then create an App password under Security."},
    "hotmail.es":     {"provider": "outlook", "label": "Outlook (Hotmail)",
                       "imap_host": "outlook.office365.com", "imap_port": 993,
                       "smtp_host": "smtp-mail.outlook.com",  "smtp_port": 587,
                       "app_password_url": "https://account.microsoft.com/security",
                       "instructions": "Enable 2-step verification at account.microsoft.com, then create an App password under Security."},
    "hotmail.com.br": {"provider": "outlook", "label": "Outlook (Hotmail)",
                       "imap_host": "outlook.office365.com", "imap_port": 993,
                       "smtp_host": "smtp-mail.outlook.com",  "smtp_port": 587,
                       "app_password_url": "https://account.microsoft.com/security",
                       "instructions": "Enable 2-step verification at account.microsoft.com, then create an App password under Security."},
    "live.co.uk":     {"provider": "outlook", "label": "Outlook (Live)",
                       "imap_host": "outlook.office365.com", "imap_port": 993,
                       "smtp_host": "smtp-mail.outlook.com",  "smtp_port": 587,
                       "app_password_url": "https://account.microsoft.com/security",
                       "instructions": "Enable 2-step verification at account.microsoft.com, then create an App password under Security."},
    "live.de":        {"provider": "outlook", "label": "Outlook (Live)",
                       "imap_host": "outlook.office365.com", "imap_port": 993,
                       "smtp_host": "smtp-mail.outlook.com",  "smtp_port": 587,
                       "app_password_url": "https://account.microsoft.com/security",
                       "instructions": "Enable 2-step verification at account.microsoft.com, then create an App password under Security."},
    "live.fr":        {"provider": "outlook", "label": "Outlook (Live)",
                       "imap_host": "outlook.office365.com", "imap_port": 993,
                       "smtp_host": "smtp-mail.outlook.com",  "smtp_port": 587,
                       "app_password_url": "https://account.microsoft.com/security",
                       "instructions": "Enable 2-step verification at account.microsoft.com, then create an App password under Security."},
    # ── Zoho regional ──────────────────────────────────────────────────────
    "zoho.eu":        {"provider": "zoho",    "label": "Zoho Mail (EU)",
                       "imap_host": "imap.zoho.eu",          "imap_port": 993,
                       "smtp_host": "smtp.zoho.eu",           "smtp_port": 587,
                       "app_password_url": "https://accounts.zoho.eu/home#security",
                       "instructions": "Go to Zoho Account \u2192 Security \u2192 App Passwords to create one."},
    "zoho.in":        {"provider": "zoho",    "label": "Zoho Mail (India)",
                       "imap_host": "imap.zoho.in",          "imap_port": 993,
                       "smtp_host": "smtp.zoho.in",           "smtp_port": 587,
                       "app_password_url": "https://accounts.zoho.in/home#security",
                       "instructions": "Go to Zoho Account \u2192 Security \u2192 App Passwords to create one."},
    "zoho.com.au":    {"provider": "zoho",    "label": "Zoho Mail (AU)",
                       "imap_host": "imap.zoho.com.au",      "imap_port": 993,
                       "smtp_host": "smtp.zoho.com.au",       "smtp_port": 587,
                       "app_password_url": "https://accounts.zoho.com.au/home#security",
                       "instructions": "Go to Zoho Account \u2192 Security \u2192 App Passwords to create one."},
    # ── Fastmail ───────────────────────────────────────────────────────────
    "fastmail.com":   {"provider": "fastmail","label": "Fastmail",
                       "imap_host": "imap.fastmail.com",     "imap_port": 993,
                       "smtp_host": "smtp.fastmail.com",      "smtp_port": 587,
                       "app_password_url": "https://www.fastmail.com/settings/security/devicekeys",
                       "instructions": "Go to Fastmail Settings \u2192 Privacy & Security \u2192 App Passwords, then create a new password."},
    "fastmail.fm":    {"provider": "fastmail","label": "Fastmail",
                       "imap_host": "imap.fastmail.com",     "imap_port": 993,
                       "smtp_host": "smtp.fastmail.com",      "smtp_port": 587,
                       "app_password_url": "https://www.fastmail.com/settings/security/devicekeys",
                       "instructions": "Go to Fastmail Settings \u2192 Privacy & Security \u2192 App Passwords, then create a new password."},
    # ── GMX / Mail.com ─────────────────────────────────────────────────────
    "gmx.com":        {"provider": "gmx",     "label": "GMX Mail",
                       "imap_host": "imap.gmx.com",          "imap_port": 993,
                       "smtp_host": "mail.gmx.com",           "smtp_port": 587,
                       "app_password_url": "https://www.gmx.com",
                       "instructions": "Go to GMX Settings \u2192 POP3 & IMAP, enable IMAP access, then use your regular password."},
    "gmx.net":        {"provider": "gmx",     "label": "GMX Mail",
                       "imap_host": "imap.gmx.net",          "imap_port": 993,
                       "smtp_host": "mail.gmx.net",           "smtp_port": 587,
                       "app_password_url": "https://www.gmx.net",
                       "instructions": "Go to GMX Settings \u2192 POP3 & IMAP, enable IMAP access, then use your regular password."},
    "gmx.de":         {"provider": "gmx",     "label": "GMX Mail",
                       "imap_host": "imap.gmx.net",          "imap_port": 993,
                       "smtp_host": "mail.gmx.net",           "smtp_port": 587,
                       "app_password_url": "https://www.gmx.net",
                       "instructions": "Go to GMX Settings \u2192 POP3 & IMAP, enable IMAP access, then use your regular password."},
    "mail.com":       {"provider": "mailcom", "label": "Mail.com",
                       "imap_host": "imap.mail.com",         "imap_port": 993,
                       "smtp_host": "smtp.mail.com",          "smtp_port": 587,
                       "app_password_url": "https://www.mail.com",
                       "instructions": "Go to Mail.com Settings \u2192 POP3 & IMAP, enable IMAP access, then use your regular password."},
    # ── ISP / Telecom providers ────────────────────────────────────────────
    "comcast.net":    {"provider": "comcast", "label": "Xfinity (Comcast)",
                       "imap_host": "imap.comcast.net",      "imap_port": 993,
                       "smtp_host": "smtp.comcast.net",       "smtp_port": 587,
                       "app_password_url": "https://login.xfinity.com/login",
                       "instructions": "Go to Xfinity account settings, enable third-party email access, then use your Xfinity password."},
    "att.net":        {"provider": "att",     "label": "AT&T Mail",
                       "imap_host": "imap.mail.att.net",     "imap_port": 993,
                       "smtp_host": "smtp.mail.att.net",      "smtp_port": 465,
                       "app_password_url": "https://www.att.com",
                       "instructions": "Go to AT&T Mail Settings, generate a Secure Mail Key to use as your password."},
    "sbcglobal.net":  {"provider": "att",     "label": "AT&T Mail (SBCGlobal)",
                       "imap_host": "imap.mail.att.net",     "imap_port": 993,
                       "smtp_host": "smtp.mail.att.net",      "smtp_port": 465,
                       "app_password_url": "https://www.att.com",
                       "instructions": "Go to AT&T Mail Settings, generate a Secure Mail Key to use as your password."},
    # ── GoDaddy Workspace ──────────────────────────────────────────────────
    "secureserver.net":{"provider": "godaddy","label": "GoDaddy Workspace",
                       "imap_host": "imap.secureserver.net",  "imap_port": 993,
                       "smtp_host": "smtpout.secureserver.net","smtp_port": 465,
                       "app_password_url": "https://sso.godaddy.com/",
                       "instructions": "Use your GoDaddy Workspace email password. If issues persist, reset it at workspace.godaddy.com."},
    # ── Cox / Charter Spectrum ─────────────────────────────────────────────
    "cox.net":        {"provider": "cox",     "label": "Cox Mail",
                       "imap_host": "imap.cox.net",          "imap_port": 993,
                       "smtp_host": "smtp.cox.net",           "smtp_port": 587,
                       "app_password_url": "https://www.cox.com",
                       "instructions": "Use your Cox account password. Enable IMAP in Cox email settings if not already on."},
    "charter.net":    {"provider": "spectrum","label": "Spectrum (Charter)",
                       "imap_host": "mobile.charter.net",    "imap_port": 993,
                       "smtp_host": "mobile.charter.net",     "smtp_port": 587,
                       "app_password_url": "https://www.spectrum.net",
                       "instructions": "Use your Spectrum account password for IMAP access."},
}


# ── MX-record based provider inference for custom domains ─────────────────────
# Maps MX hostname substrings to the config that should be returned.
_MX_PROVIDER_HINTS = {
    "google":            {"provider": "gmail",   "label": "Gmail (Google Workspace)"},
    "googlemail":        {"provider": "gmail",   "label": "Gmail (Google Workspace)"},
    "outlook.com":       {"provider": "outlook", "label": "Microsoft 365",
                          "imap_host": "outlook.office365.com", "imap_port": 993,
                          "smtp_host": "smtp-mail.outlook.com",  "smtp_port": 587,
                          "app_password_url": "https://account.microsoft.com/security",
                          "instructions": "This domain uses Microsoft 365. Sign in with Microsoft above, or enable 2-step verification at account.microsoft.com and create an App password."},
    "protection.outlook": {"provider": "outlook", "label": "Microsoft 365",
                          "imap_host": "outlook.office365.com", "imap_port": 993,
                          "smtp_host": "smtp-mail.outlook.com",  "smtp_port": 587,
                          "app_password_url": "https://account.microsoft.com/security",
                          "instructions": "This domain uses Microsoft 365. Sign in with Microsoft above, or enable 2-step verification at account.microsoft.com and create an App password."},
    "yahoodns":          {"provider": "yahoo",   "label": "Yahoo Mail (custom domain)",
                          "imap_host": "imap.mail.yahoo.com",   "imap_port": 993,
                          "smtp_host": "smtp.mail.yahoo.com",    "smtp_port": 587,
                          "app_password_url": "https://login.yahoo.com/account/security",
                          "instructions": "This domain uses Yahoo. Go to Yahoo Account Security, enable 2-step verification, then generate an App Password."},
    "zoho":              {"provider": "zoho",    "label": "Zoho Mail (custom domain)",
                          "imap_host": "imap.zoho.com",         "imap_port": 993,
                          "smtp_host": "smtp.zoho.com",          "smtp_port": 587,
                          "app_password_url": "https://accounts.zoho.com/home#security",
                          "instructions": "This domain uses Zoho Mail. Go to Zoho Account \u2192 Security \u2192 App Passwords."},
    "mimecast":          {"provider": "custom",  "label": "Mimecast-filtered (ask IT for IMAP host)"},
    "proofpoint":        {"provider": "custom",  "label": "Proofpoint-filtered (ask IT for IMAP host)"},
}


def _mx_lookup(domain: str) -> Optional[Dict[str, Any]]:
    """Do a DNS MX lookup and try to match the mail host to a known provider."""
    try:
        import dns.resolver
        answers = dns.resolver.resolve(domain, "MX")
        for rdata in sorted(answers, key=lambda r: r.preference):
            mx_host = str(rdata.exchange).lower().rstrip(".")
            for hint, cfg in _MX_PROVIDER_HINTS.items():
                if hint in mx_host:
                    return cfg
    except Exception:
        pass
    return None


# ── Humor prompt building ─────────────────────────────────────────────────────
COMEDIAN_STYLES = {
    "kevin_hart": {
        "label": "Kevin Hart",
        "desc": "High-energy, self-deprecating storytelling",
        "mechanics": (
            "Build humor using self-deprecating story arcs where YOU are the butt of the joke. "
            "Use escalating stakes — start with a mundane situation, then raise the absurdity with each sentence. "
            "Employ the 'And I said to myself...' internal monologue setup to pull the reader into your perspective. "
            "Rhythm: short punchy sentences build pressure, then a longer payoff sentence releases it. "
            "Ground every joke in a relatable, everyday situation before exaggerating it into comedy. "
            "Energy is everything — write like you're performing, not just typing."
        ),
    },
    "dave_chappelle": {
        "label": "Dave Chappelle",
        "desc": "Observational with sharp social pivots",
        "mechanics": (
            "Construct humor through slow, deliberate observation that suddenly pivots to an unexpected social truth. "
            "Let the premise breathe — don't rush to the punchline. The audience should almost be comfortable before the shift. "
            "Use frame-shifting: introduce a subject from one angle, then reveal it from a completely opposite angle. "
            "Lean into discomfort confidently. Taboo topics land when the writer owns the awkwardness rather than apologizing for it. "
            "Pause beats matter: a short one-word sentence mid-paragraph signals the pivot is coming."
        ),
    },
    "trevor_noah": {
        "label": "Trevor Noah",
        "desc": "Calm, wry cross-cultural observations",
        "mechanics": (
            "Deploy humor through cross-cultural or cross-perspective comparison — show how the same situation looks "
            "completely different depending on where you stand. "
            "Maintain calm, measured prose throughout; the wit comes from precision of observation, not volume. "
            "Use the 'In [Context A], X. But in [Context B]...' structure to reveal absurdity through contrast. "
            "Wry understatement is the signature move: describe outrageous things in the most matter-of-fact tone possible. "
            "Never sound shocked — sound mildly curious. The gap between calm tone and wild content IS the joke."
        ),
    },
    "amy_schumer": {
        "label": "Amy Schumer",
        "desc": "Radical honesty and disarming awkwardness",
        "mechanics": (
            "Lead with radical honesty about something others avoid saying. The humor comes from saying the quiet part loud. "
            "Own awkward truths before anyone else can point them out — this defuses tension and creates intimacy with the reader. "
            "Use self-aware vulnerability: acknowledge the absurdity of your own position in the situation. "
            "The formula: [uncomfortable truth] + [casual delivery] = comedy. The relaxed tone signals it's safe to laugh. "
            "Avoid setup-punchline structure; instead let the entire observation be funny through its matter-of-fact honesty."
        ),
    },
    "john_mulaney": {
        "label": "John Mulaney",
        "desc": "Precise word choice — the detail IS the punchline",
        "mechanics": (
            "Specificity is your primary comedic tool. Never say 'a dog' — say 'a 17-year-old beagle named Gerald who hates you.' "
            "The more precisely you describe something ordinary, the funnier it becomes. "
            "Construct long, carefully balanced sentences that feel like they're going somewhere serious — then undercut them. "
            "Musical sentence structure: vary the rhythm deliberately. A well-placed short sentence after a long buildup is the punchline architecture. "
            "Callbacks: reference something from earlier in the conversation or message as if completing a thought. "
            "Deadpan delivery is key — describe absurd events with the same gravity as serious ones."
        ),
    },
    "desi_lydic": {
        "label": "Desi Lydic",
        "desc": "Sharp, confident, quick wit",
        "mechanics": (
            "Move fast — sharp wit means short setups and immediate payoffs. No wasted words. "
            "Use confident, slightly sardonic observations that signal intelligence without being condescending. "
            "The best Desi-style lines feel like someone who just noticed something everyone else missed and casually pointed it out. "
            "Employ rhetorical questions that expose the obvious absurdity in a situation. "
            "Punchy, declarative humor: state the joke as a fact rather than hedging it as a question or suggestion."
        ),
    },
}

_ADJ_PLATFORMS = [
    ("instagram_dm",      "Instagram DMs",      "📸"),
    ("instagram_comment", "Instagram Comments", "💬"),
    ("facebook_dm",       "Facebook DMs",       "📘"),
    ("facebook_comment",  "Facebook Comments",  "💬"),
    ("email",             "Email Replies",      "📧"),
    ("linkedin",          "LinkedIn",           "💼"),
    ("twitter",           "Twitter / X",        "🐦"),
    ("tiktok",            "TikTok",             "🎵"),
    ("threads",           "Threads",            "🧵"),
]


def _generate_humor_prompt(humor_prefs: dict) -> str:
    """Build a metaprompt-quality humor instruction block from saved humor settings."""
    if not humor_prefs or not humor_prefs.get("enabled"):
        return ""

    intensity = humor_prefs.get("intensity", "balanced")
    selected_comedians = humor_prefs.get("comedians", [])

    intensity_guidance = {
        "subtle": (
            "Humor should be light and understated — a well-placed wry observation or a slightly unexpected word choice. "
            "Never force a joke. Let wit emerge naturally from precise language. Aim: 1 light humorous beat per 3-4 responses."
        ),
        "balanced": (
            "Use humor thoughtfully — enough that the personality shines, not so much it overshadows the message. "
            "Mix witty observations with genuine helpfulness. Aim: 1 clear funny moment per 1-2 responses."
        ),
        "bold": (
            "Lead with personality. Humor is a primary communication tool here, not an accent. "
            "Every response should have clear comedic energy. Aim: humor present in every response without sacrificing helpfulness."
        ),
    }.get(intensity, "")

    comedian_blocks = []
    for slug in selected_comedians:
        if slug in COMEDIAN_STYLES:
            c = COMEDIAN_STYLES[slug]
            comedian_blocks.append(f"  [{c['label']}] {c['mechanics']}")

    style_blend = ""
    if comedian_blocks:
        style_blend = (
            "\n\n### COMEDIC STYLE MECHANICS\n"
            "Draw from the following comedic techniques (blend them naturally, do not imitate superficially):\n\n"
            + "\n\n".join(comedian_blocks)
        )
    else:
        style_blend = (
            "\n\n### COMEDIC STYLE MECHANICS\n"
            "Use observational humor, precise word choice, and self-aware wit. "
            "Avoid clichéd jokes or trying too hard. Let humor arise from specificity and honest observation."
        )

    return f"""
### HUMOR INSTRUCTIONS
You have permission to be genuinely funny. This is NOT a license to make random jokes —
it is permission to let real wit, personality, and comedic timing emerge naturally in your responses.

{intensity_guidance}

Core rules for effective humor in this context:
1. NEVER sacrifice clarity or helpfulness for a joke.
2. Timing comes from sentence rhythm — a short sentence after a longer one signals the punchline.
3. Specificity IS comedy: "a 12-step customer service process" is funnier than "a process".
4. Self-awareness lands better than targeting others.
5. Forced humor is worse than no humor. If a moment isn't ripe, let it pass.
{style_blend}
"""


def _load_tone_prefs(client_id: str) -> dict:
    # 1. Try PostgreSQL first (survives Railway redeploys)
    try:
        from database.db import SessionLocal
        from database.models import ClientProfile
        _db = SessionLocal()
        try:
            _prof = _db.query(ClientProfile).filter(ClientProfile.client_id == client_id).first()
            if _prof and getattr(_prof, "tone_preferences_json", None):
                return json.loads(_prof.tone_preferences_json)
        finally:
            _db.close()
    except Exception:
        pass
    # 2. Fall back to filesystem cache
    path = os.path.join(TONE_PREFS_DIR, client_id, "tone_prefs.json")
    if os.path.exists(path):
        try:
            with open(path) as f:
                data = json.load(f)
            # Back-fill DB so next read hits DB
            _backfill_tone_prefs_to_db(client_id, data)
            return data
        except Exception:
            pass
    return {}


def _backfill_tone_prefs_to_db(client_id: str, prefs: dict):
    try:
        from database.db import SessionLocal
        from database.models import ClientProfile
        _db = SessionLocal()
        try:
            _prof = _db.query(ClientProfile).filter(ClientProfile.client_id == client_id).first()
            if _prof:
                _prof.tone_preferences_json = json.dumps(prefs)
                _db.commit()
        finally:
            _db.close()
    except Exception:
        pass


def _save_tone_prefs(client_id: str, prefs: dict):
    # 1. Write to PostgreSQL (primary — survives Railway redeploys)
    try:
        from database.db import SessionLocal
        from database.models import ClientProfile
        _db = SessionLocal()
        try:
            _prof = _db.query(ClientProfile).filter(ClientProfile.client_id == client_id).first()
            if _prof:
                _prof.tone_preferences_json = json.dumps(prefs)
                if not getattr(_prof, "tone_configured", False):
                    _prof.tone_configured = True
                _db.commit()
        finally:
            _db.close()
    except Exception:
        pass
    # 2. Also write to filesystem cache (for fast reads)
    try:
        folder = os.path.join(TONE_PREFS_DIR, client_id)
        os.makedirs(folder, exist_ok=True)
        with open(os.path.join(folder, "tone_prefs.json"), "w") as f:
            json.dump(prefs, f, indent=2)
    except Exception:
        pass


def _load_samples(client_id: str) -> str:
    # 1. Try PostgreSQL first (survives Railway redeploys)
    try:
        from database.db import SessionLocal
        from database.models import ClientProfile
        _db = SessionLocal()
        try:
            _prof = _db.query(ClientProfile).filter(ClientProfile.client_id == client_id).first()
            if _prof and getattr(_prof, "normalized_samples_text", None):
                return _prof.normalized_samples_text
        finally:
            _db.close()
    except Exception:
        pass
    # 2. Fall back to filesystem cache
    path = os.path.join(TONE_PREFS_DIR, client_id, "normalized_samples.txt")
    if os.path.exists(path):
        try:
            with open(path) as f:
                text = f.read()
            # Back-fill DB
            _backfill_samples_to_db(client_id, text)
            return text
        except Exception:
            pass
    return ""


def _backfill_samples_to_db(client_id: str, text: str):
    try:
        from database.db import SessionLocal
        from database.models import ClientProfile
        _db = SessionLocal()
        try:
            _prof = _db.query(ClientProfile).filter(ClientProfile.client_id == client_id).first()
            if _prof:
                _prof.normalized_samples_text = text
                _db.commit()
        finally:
            _db.close()
    except Exception:
        pass


def _save_samples(client_id: str, text: str):
    # 1. Write to PostgreSQL (primary — survives Railway redeploys)
    try:
        from database.db import SessionLocal
        from database.models import ClientProfile
        _db = SessionLocal()
        try:
            _prof = _db.query(ClientProfile).filter(ClientProfile.client_id == client_id).first()
            if _prof:
                _prof.normalized_samples_text = text
                _db.commit()
        finally:
            _db.close()
    except Exception:
        pass
    # 2. Also write to filesystem cache
    try:
        folder = os.path.join(TONE_PREFS_DIR, client_id)
        os.makedirs(folder, exist_ok=True)
        with open(os.path.join(folder, "normalized_samples.txt"), "w") as f:
            f.write(text)
    except Exception:
        pass


@router.get("/tone", response_class=HTMLResponse)
async def tone_page(request: Request):
    user, profile, db = await _get_profile(request)
    db.close()
    if not user:
        return RedirectResponse("/account/login", status_code=303)

    prefs = _load_tone_prefs(profile.client_id)
    active_preset = prefs.get("preset", "")
    has_samples = bool(_load_samples(profile.client_id))
    msg = request.query_params.get("msg", "")

    # ── New settings state ────────────────────────────────────────────
    humor_prefs     = prefs.get("humor", {})
    humor_enabled   = humor_prefs.get("enabled", False)
    humor_intensity = humor_prefs.get("intensity", "balanced")
    humor_comedians = humor_prefs.get("comedians", [])
    casual_conv     = prefs.get("casual_conversation", False)
    adj_prefs       = prefs.get("platform_adjustments", {})

    # Auto-learn status
    try:
        from utils.style_learner import get_learn_status
        learn = get_learn_status(profile.client_id)
    except Exception:
        learn = {"enabled": False, "learned": False, "status": "never",
                 "post_count": None, "ig_handle": None, "learned_at": None}

    # Check if IG is connected so we can show re-analyze button
    # Must check meta_pages (Meta OAuth) — the old local JSON file doesn't
    # exist on Railway's ephemeral filesystem.
    _ig_connected = False
    try:
        _mp_raw = getattr(profile, "meta_pages", None) or "[]"
        _mp = json.loads(_mp_raw) if isinstance(_mp_raw, str) else _mp_raw
        if isinstance(_mp, list):
            for _pg in _mp:
                if _pg.get("instagram_connected") or _pg.get("instagram_id"):
                    _ig_connected = True
                    break
    except Exception:
        pass
    # Fallback: check for legacy local JSON file
    if not _ig_connected:
        _ig_connected = os.path.exists(
            os.path.join("storage", "connections", f"{profile.client_id}.json")
        )

    # Build auto-learn status badge
    _status = learn["status"]
    if _status == "complete" and learn["learned"]:
        _handle_str = f" from {learn['ig_handle']}" if learn["ig_handle"] else ""
        _count_str = f"{learn['post_count']} posts" if learn["post_count"] else "posts"
        _learn_badge = (f'<span class="pill pill-green" style="font-size:.82rem">'  
                        f'✅ {_count_str} analyzed{_handle_str} · {learn["learned_at"]}</span>')
        _relearn_btn = (
            f'<form method="post" action="/settings/tone/relearn" style="margin-top:12px">'
            f'<button type="submit" class="btn btn-secondary" style="font-size:.82rem">'
            f'🔄 Re-analyze posts</button></form>'
            if _ig_connected else ""
        )
    elif _status == "running":
        _learn_badge = '<span class="pill pill-yellow" style="font-size:.82rem">⌛ Analyzing your posts… check back in a moment</span>'
        _relearn_btn = ""
    elif _status == "no_content":
        _learn_badge = '<span class="pill pill-gray" style="font-size:.82rem">⚠️ No captions found on your account</span>'
        _relearn_btn = ""
    elif _status == "error":
        _learn_badge = '<span class="pill" style="background:#fff0f0;color:#c0392b;font-size:.82rem">❌ Analysis failed — try re-analyzing</span>'
        _relearn_btn = (
            f'<form method="post" action="/settings/tone/relearn" style="margin-top:12px">'
            f'<button type="submit" class="btn btn-secondary" style="font-size:.82rem">'  
            f'🔄 Retry analysis</button></form>'
            if _ig_connected else ""
        )
    else:
        _learn_badge = '<span class="pill pill-gray" style="font-size:.82rem">○ Not yet analyzed — connect Instagram to enable</span>'
        _relearn_btn = ""

    _auto_checked = 'checked' if learn["enabled"] else ''
    _auto_learn_card = f"""
    <div class="card" style="border:2px solid {'#5c6ac4' if learn['enabled'] else '#eee'}">
      <h2>Auto-Learn from Instagram Posts</h2>
      <div class="sub">When your Instagram account is connected, Alita can read your recent posts
        and automatically build a style profile from your real writing. No manual samples needed.</div>
      <div style="display:flex;align-items:center;gap:10px;margin:16px 0 8px">
        <label style="display:flex;align-items:center;gap:8px;cursor:pointer;margin:0">
          <input type="checkbox" name="auto_learn" value="1" {_auto_checked}
                 onchange="this.form.submit()" form="tone-form"
                 style="width:18px;height:18px;accent-color:#5c6ac4">
          <span style="font-size:.9rem;font-weight:600">Automatically learn from my posts when I connect Instagram</span>
        </label>
      </div>
      <div style="margin-top:8px">{_learn_badge}</div>
      {_relearn_btn}
    </div>"""  

    preset_html = ""
    for key, tone in PRESET_TONES.items():
        active_cls = "active" if key == active_preset else ""
        preset_html += f"""
        <label class="preset {active_cls}" onclick="selectPreset('{key}')">
          <input type="radio" name="preset" value="{key}" {'checked' if key == active_preset else ''} style="display:none">
          <h4>{tone['label']}</h4>
          <p>{tone['desc']}</p>
        </label>"""

    success_banner = f"""<div style="background:#e8f5e9;border-left:4px solid #27ae60;padding:12px 16px;border-radius:0 8px 8px 0;margin-bottom:20px;font-size:.88rem;color:#2e7d32">{msg}</div>""" if msg else ""

    _tone_js = r"""
function selectPreset(key) {
  document.querySelectorAll('.preset').forEach(p => p.classList.remove('active'));
  const el = document.querySelector('.preset[onclick="selectPreset(\'' + key + '\')"]');
  if (el) { el.classList.add('active'); el.querySelector('input[type=radio]').checked = true; }
}
function togglePlat(key) {
  const cb = document.getElementById('pchk-' + key);
  const card = document.getElementById('plat-' + key);
  const sub  = document.getElementById('plat-sub-' + key);
  if (!cb) return;
  cb.checked = !cb.checked;
  if (cb.checked) { if(card) card.classList.add('on');    if(sub) sub.textContent = 'Active'; }
  else             { if(card) card.classList.remove('on'); if(sub) sub.textContent = 'Off'; }
}

/* ── Humor settings ───────────────────────────────────────────────── */
function toggleHumor() {
  const enabled = document.getElementById('humor-enabled').checked;
  document.getElementById('humor-details').style.display = enabled ? 'block' : 'none';
  const card = document.getElementById('humor-card');
  if (card) card.classList.toggle('ar-on', enabled);
  saveHumor();
}
function setIntensity(btn) {
  document.querySelectorAll('.intensity-btn').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  saveHumor();
}
function saveHumor() {
  const enabled = document.getElementById('humor-enabled').checked;
  const ib = document.querySelector('.intensity-btn.active');
  const intensity = ib ? ib.dataset.val : 'balanced';
  const comedians = Array.from(document.querySelectorAll('.comedian-cb:checked')).map(cb => cb.value);
  fetch('/settings/tone/humor', {
    method: 'POST', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({enabled, intensity, comedians})
  }).then(r => r.json()).then(() => {
    const ind = document.getElementById('humor-saved');
    if (ind) { ind.style.opacity = '1'; setTimeout(() => { ind.style.opacity = '0'; }, 2000); }
  }).catch(e => console.error('Humor save failed', e));
}

/* ── Conversation mode ────────────────────────────────────────────── */
function saveConversation() {
  const enabled = document.getElementById('casual-enabled').checked;
  const card = document.getElementById('convo-card');
  if (card) card.classList.toggle('ar-on', enabled);
  fetch('/settings/tone/conversation', {
    method: 'POST', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({enabled})
  }).then(r => r.json()).then(() => {
    const ind = document.getElementById('conv-saved');
    if (ind) { ind.style.opacity = '1'; setTimeout(() => { ind.style.opacity = '0'; }, 2000); }
  }).catch(e => console.error('Conversation save failed', e));
}

/* ── Platform adjustments ─────────────────────────────────────────── */
var _activeAdjTab = sessionStorage.getItem('adj_tab') || 'instagram_dm';
function switchAdjTab(key) {
  _activeAdjTab = key;
  sessionStorage.setItem('adj_tab', key);
  document.querySelectorAll('.adj-tab').forEach(t => t.classList.toggle('active', t.dataset.key === key));
  document.querySelectorAll('.adj-panel').forEach(p => {
    p.style.display = p.dataset.key === key ? 'block' : 'none';
  });
  cancelAdjustment();
}
function previewAdjustment() {
  const text = document.getElementById('adj-input').value.trim();
  if (!text) { alert('Please describe an adjustment first.'); return; }
  const btn = document.getElementById('adj-preview-btn');
  if (btn) { btn.disabled = true; btn.textContent = '\u23f3 Analyzing\u2026'; }
  fetch('/settings/tone/adjustment/preview', {
    method: 'POST', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({text, platform: _activeAdjTab})
  }).then(r => r.json()).then(d => {
    if (btn) { btn.disabled = false; btn.textContent = '\\ud83d\\udc41 Preview Effect'; }
    document.getElementById('adj-desc-text').textContent = d.description || d.error || 'Could not generate preview.';
    document.getElementById('adj-preview-box').style.display = 'block';
  }).catch(e => {
    if (btn) { btn.disabled = false; btn.textContent = '\\ud83d\\udc41 Preview Effect'; }
    console.error(e);
  });
}
function confirmAdjustment() {
  const text = document.getElementById('adj-input').value.trim();
  const extra = Array.from(document.querySelectorAll('.adj-apply-cb:checked')).map(cb => cb.value);
  if (!text) return;
  const platforms = extra.length ? extra : [_activeAdjTab];
  fetch('/settings/tone/adjustment/save', {
    method: 'POST', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({text, platforms})
  }).then(() => {
    document.getElementById('adj-input').value = '';
    cancelAdjustment();
    sessionStorage.setItem('adj_tab', _activeAdjTab);
    window.location.reload();
  }).catch(e => console.error(e));
}
function cancelAdjustment() {
  const box = document.getElementById('adj-preview-box');
  if (box) box.style.display = 'none';
  const inp = document.getElementById('adj-input');
  if (inp) inp.value = '';
}
function deleteAdjustment(platform, idx) {
  if (!confirm('Remove this adjustment?')) return;
  fetch('/settings/tone/adjustment/delete', {
    method: 'POST', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({platform, index: idx})
  }).then(() => {
    sessionStorage.setItem('adj_tab', platform);
    window.location.reload();
  }).catch(e => console.error(e));
}

/* ── Test sandbox ─────────────────────────────────────────────────── */
function runTest() {
  const channel = document.getElementById('test-channel').value;
  const message = document.getElementById('test-message').value.trim();
  if (!message) { alert('Please enter a test message.'); return; }
  const btn = document.getElementById('test-btn');
  const resultEl = document.getElementById('test-result');
  if (btn) { btn.disabled = true; btn.textContent = '\u23f3 Generating\u2026'; }
  resultEl.style.display = 'none';
  fetch('/settings/tone/test', {
    method: 'POST', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({channel, message})
  }).then(r => r.json()).then(d => {
    if (btn) { btn.disabled = false; btn.textContent = 'Generate Response'; }
    const pills = (d.active_settings || [])
      .map(s => '<span class="pill pill-gray" style="font-size:.72rem;margin:2px 2px 0 0">' + s + '</span>')
      .join('');
    resultEl.innerHTML =
      '<div style="background:#f0f2ff;border-radius:12px 12px 12px 2px;padding:14px 18px;margin-top:14px;' +
      'font-size:.9rem;color:#1c1e21;line-height:1.6;border:1.5px solid #c5cce8">' +
      '<div style="font-size:.74rem;font-weight:700;color:#5c6ac4;margin-bottom:8px;text-transform:uppercase;letter-spacing:.04em">AI Response</div>' +
      (d.reply || d.error || 'No response generated.') +
      '</div>' +
      (pills ? '<div style="margin-top:8px">' + pills + '</div>' : '');
    resultEl.style.display = 'block';
  }).catch(e => {
    if (btn) { btn.disabled = false; btn.textContent = 'Generate Response'; }
    console.error(e);
  });
}

/* ── Init ────────────────────────────────────────────────────────── */
document.addEventListener('DOMContentLoaded', function() {
  switchAdjTab(sessionStorage.getItem('adj_tab') || 'instagram_dm');
  const he = document.getElementById('humor-enabled');
  if (he) {
    document.getElementById('humor-details').style.display = he.checked ? 'block' : 'none';
  }
});
"""
    # ── Platform active toggles ──────────────────────────────────────
    plat_active = prefs.get("platform_active", {})
    _plat_items = [
        ("instagram", "Instagram",  "📸"),
        ("facebook",  "Facebook",   "📘"),
        ("tiktok",    "TikTok",     "🎵"),
        ("linkedin",  "LinkedIn",   "💼"),
        ("twitter",   "Twitter / X","🐦"),
        ("threads",   "Threads",    "🧵"),
    ]
    plat_cards_html = ""
    for pk, pl, pi in _plat_items:
        is_on = plat_active.get(pk, True)
        on_cls  = "plat-card on" if is_on else "plat-card"
        checked = "checked" if is_on else ""
        status  = "Active" if is_on else "Off"
        plat_cards_html += (
            f'<label class="{on_cls}" id="plat-{pk}" onclick="togglePlat(\'{pk}\')">'
            f'<input type="checkbox" name="plat_{pk}" value="1" {checked} style="display:none" id="pchk-{pk}">'
            f'<span class="plat-icon">{pi}</span>'
            f'<div class="plat-card-info">'
            f'<div class="plat-card-name">{pl}</div>'
            f'<div class="plat-card-sub" id="plat-sub-{pk}">{status}</div>'
            f'</div></label>'
        )
    _plat_card = (
        '<div class="card"><h2>Active Platforms</h2>'
        '<div class="sub">Choose which platforms this tone &amp; style applies to. '
        'Platforms turned off will use a neutral default voice.</div>'
        f'<div class="plat-grid">{plat_cards_html}</div></div>'
    )

    # ── Humor & Conversation mode cards ───────────────────────────────────────
    _comedian_html = ""
    for _slug, _cm in COMEDIAN_STYLES.items():
        _ck = 'checked' if _slug in humor_comedians else ''
        _comedian_html += (
            f'<label class="comedian-label" style="display:flex;align-items:flex-start;gap:8px;'
            f'padding:8px 10px;border:1.5px solid #eee;border-radius:8px;cursor:pointer;background:#fafafa">'
            f'<input type="checkbox" class="comedian-cb" value="{_slug}" {_ck} onchange="saveHumor()" '
            f'style="margin-top:2px;width:14px;height:14px;accent-color:#5c6ac4">'
            f'<div><div style="font-weight:600;font-size:.82rem">{_cm["label"]}</div>'
            f'<div style="font-size:.74rem;color:#90949c;margin-top:1px">{_cm["desc"]}</div></div>'
            f'</label>'
        )

    _intensity_html = ""
    for _ival, _ilbl in [("subtle", "Subtle"), ("balanced", "Balanced"), ("bold", "Bold 🔥")]:
        _ia = "active" if humor_intensity == _ival else ""
        _intensity_html += (
            f'<button type="button" class="intensity-btn {_ia}" data-val="{_ival}" '
            f'onclick="setIntensity(this)">{_ilbl}</button>'
        )

    _humor_card_cls = "ar-on" if humor_enabled else ""
    _humor_details_display = "block" if humor_enabled else "none"
    _humor_enabled_checked = "checked" if humor_enabled else ""
    _convo_card_cls = "ar-on" if casual_conv else ""
    _casual_checked = "checked" if casual_conv else ""

    _humor_convo_html = (
        '<div style="display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-top:20px">'
        # Humor card
        f'<div class="card {_humor_card_cls}" id="humor-card" style="margin-bottom:0">'
        '<div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:4px">'
        '<h2 style="margin:0">🎭 Humor Settings</h2>'
        '<div style="display:flex;align-items:center;gap:10px">'
        '<span id="humor-saved" style="font-size:.75rem;color:#5c6ac4;opacity:0;transition:opacity .3s">Saved ✓</span>'
        f'<label class="sw"><input type="checkbox" id="humor-enabled" {_humor_enabled_checked} '
        f'onchange="toggleHumor()"><span class="sw-track"></span></label>'
        '</div></div>'
        '<div class="sub" style="margin-bottom:14px">Let the AI be genuinely funny — real wit, not random jokes.</div>'
        f'<div id="humor-details" style="display:{_humor_details_display}">'
        '<div style="font-size:.82rem;font-weight:600;color:#444;margin-bottom:8px">Intensity</div>'
        f'<div style="display:flex;gap:6px;margin-bottom:18px">{_intensity_html}</div>'
        '<div style="font-size:.82rem;font-weight:600;color:#444;margin-bottom:10px">Draw inspiration from</div>'
        f'<div style="display:grid;grid-template-columns:1fr 1fr;gap:8px">{_comedian_html}</div>'
        '</div></div>'
        # Conversation mode card
        f'<div class="card {_convo_card_cls}" id="convo-card" style="margin-bottom:0">'
        '<div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:4px">'
        '<h2 style="margin:0">💬 Conversation Mode</h2>'
        '<div style="display:flex;align-items:center;gap:10px">'
        '<span id="conv-saved" style="font-size:.75rem;color:#5c6ac4;opacity:0;transition:opacity .3s">Saved ✓</span>'
        f'<label class="sw"><input type="checkbox" id="casual-enabled" {_casual_checked} '
        f'onchange="saveConversation()"><span class="sw-track"></span></label>'
        '</div></div>'
        '<div class="sub">When on, the AI engages naturally in small talk — not just business topics.</div>'
        '<div style="margin-top:16px;background:#f8f9fa;border-radius:8px;padding:14px;font-size:.84rem;color:#555;line-height:1.6">'
        '🧠 Uses the <strong>Conversation Categorizer</strong> to detect <em>GENERAL</em> messages. '
        'Only activates casual mode when the classifier confidence is &gt;60%. '
        'Business questions (sales, complaints, support) always receive professional replies regardless of this setting.'
        '</div></div>'
        '</div>'
    )

    # ── Platform Adjustments ──────────────────────────────────────────────────
    _adj_tabs_html = ""
    _adj_panels_html = ""
    for _pk, _pl, _pi in _ADJ_PLATFORMS:
        _adj_tabs_html += (
            f'<button type="button" class="adj-tab" data-key="{_pk}" '
            f'onclick="switchAdjTab(\'{_pk}\')">{_pi} {_pl}</button>'
        )
        _items = adj_prefs.get(_pk, [])
        _pills = "".join(
            f'<div class="adj-pill"><span class="adj-pill-text">{_item}</span>'
            f'<button type="button" class="adj-pill-del" '
            f'onclick="deleteAdjustment(\'{_pk}\',{_idx})">✕</button></div>'
            for _idx, _item in enumerate(_items)
        ) or '<div style="color:#bbb;font-size:.84rem;padding:6px 0">No adjustments yet for this channel.</div>'
        _adj_panels_html += (
            f'<div class="adj-panel" data-key="{_pk}" style="display:none">'
            f'<div class="adj-pills-row">{_pills}</div></div>'
        )

    _apply_checks_html = "".join(
        f'<label style="display:flex;align-items:center;gap:5px;font-size:.8rem;cursor:pointer;white-space:nowrap">'
        f'<input type="checkbox" class="adj-apply-cb" value="{_pk}" style="accent-color:#5c6ac4"> {_pi} {_pl}</label>'
        for _pk, _pl, _pi in _ADJ_PLATFORMS
    )

    _adj_html = (
        '<div class="card" style="margin-top:20px">'
        '<h2>🎯 Platform-Specific Adjustments</h2>'
        '<div class="sub">Add custom behaviour instructions per channel. '
        'An adjustment only affects the channels you assign it to — '
        'tweaking your email tone won\'t touch your Instagram DMs.</div>'
        f'<div class="adj-tabs" style="display:flex;flex-wrap:wrap;gap:4px;'
        f'margin:16px 0 0;border-bottom:2px solid #eee;padding-bottom:8px">{_adj_tabs_html}</div>'
        f'<div id="adj-panels" style="margin-top:4px">{_adj_panels_html}</div>'
        '<div style="margin-top:16px">'
        '<label style="font-size:.82rem;font-weight:600;color:#444;margin-bottom:6px;display:block">'
        'Describe a new adjustment</label>'
        '<textarea id="adj-input" rows="3" class="s-input" style="min-height:70px;resize:vertical" '
        'placeholder="e.g. Use shorter sentences when replying to complaints"></textarea>'
        '<div style="margin-top:10px">'
        '<button type="button" id="adj-preview-btn" onclick="previewAdjustment()" '
        'style="background:#5c6ac4;color:#fff;border:none;border-radius:8px;padding:9px 18px;'
        'font-size:.87rem;font-weight:600;cursor:pointer">👁 Preview Effect</button>'
        '</div></div>'
        '<div id="adj-preview-box" style="display:none;margin-top:16px;border:1.5px solid #5c6ac4;'
        'border-radius:10px;padding:16px;background:#f8f9ff">'
        '<div style="font-size:.8rem;font-weight:700;color:#5c6ac4;margin-bottom:8px;'
        'text-transform:uppercase;letter-spacing:.05em">📋 What this adjustment will do</div>'
        '<div id="adj-desc-text" style="font-size:.9rem;color:#333;line-height:1.6;margin-bottom:14px"></div>'
        '<div style="font-size:.8rem;font-weight:600;color:#444;margin-bottom:8px">Also apply to these channels:</div>'
        f'<div style="display:flex;flex-wrap:wrap;gap:12px;margin-bottom:16px">{_apply_checks_html}</div>'
        '<div style="display:flex;gap:8px">'
        '<button type="button" onclick="confirmAdjustment()" style="background:#27ae60;color:#fff;border:none;'
        'border-radius:8px;padding:9px 18px;font-size:.87rem;font-weight:600;cursor:pointer">✅ Confirm &amp; Save</button>'
        '<button type="button" onclick="cancelAdjustment()" style="background:#fff;color:#666;'
        'border:1.5px solid #dde0e4;border-radius:8px;padding:9px 18px;'
        'font-size:.87rem;font-weight:600;cursor:pointer">Cancel</button>'
        '</div></div></div>'
    )

    # ── Test Sandbox ──────────────────────────────────────────────────────────
    _channel_opts = "".join(
        f'<option value="{_pk}">{_pi} {_pl}</option>'
        for _pk, _pl, _pi in _ADJ_PLATFORMS
    )
    _test_html = (
        '<div class="card" style="margin-top:20px;margin-bottom:0">'
        '<h2>🧪 Test Your Settings</h2>'
        '<div class="sub">Send a test message as a customer would and see exactly how the AI responds with your '
        'current tone preset, humor settings, and channel adjustments all applied.</div>'
        '<div style="display:grid;grid-template-columns:200px 1fr;gap:16px;margin-top:16px;align-items:start">'
        '<div><label style="font-size:.82rem;font-weight:600;color:#444;margin-bottom:6px;display:block">Channel</label>'
        f'<select id="test-channel" class="s-input">{_channel_opts}</select></div>'
        '<div><label style="font-size:.82rem;font-weight:600;color:#444;margin-bottom:6px;display:block">Customer message</label>'
        '<textarea id="test-message" rows="4" class="s-input" '
        'placeholder="e.g. Hey I\'ve been waiting 3 days and no one is responding…"></textarea></div>'
        '</div>'
        '<button type="button" id="test-btn" onclick="runTest()" style="background:#5c6ac4;color:#fff;'
        'border:none;border-radius:8px;padding:10px 24px;margin-top:12px;font-size:.88rem;'
        'font-weight:600;cursor:pointer">Generate Response</button>'
        '<div id="test-result" style="display:none"></div>'
        '</div>'
    )

    _tone_body = (
        f"{success_banner}"
        # ── Page intro ─────────────────────────────────────────────────
        '<div style="margin-bottom:24px">'
        '<h1 style="font-size:1.4rem;font-weight:700;color:#1c1e21;margin:0 0 6px">Tone &amp; Style</h1>'
        '<p style="color:#90949c;font-size:.9rem;margin:0">'
        'Define how Alita sounds when representing your brand across every channel.'
        '</p>'
        '</div>'
        # ── Main form ─────────────────────────────────────────────────────────
        '<form method="post" action="/settings/tone" id="tone-form">'
        # Save row — top
        '<div style="display:flex;gap:12px;margin-bottom:24px">'
        '<button type="submit" class="btn-primary">💾 Save Changes</button>'
        '<a href="/settings" class="btn-secondary">← Back to Settings</a>'
        '</div>'
        # ── Section 1: Your Voice ───────────────────────────────────────────
        '<div class="card">'
        '<h2>🎙️ Your Voice</h2>'
        '<div class="sub">Pick the personality your brand communicates with. You can change this any time.</div>'
        f'<div class="preset-grid">{preset_html}</div>'
        '</div>'
        # ── Section 2: Active Platforms ─────────────────────────────────────
        + _plat_card
        # ── Section 3: Train Your Voice ─────────────────────────────────────
        + '<div class="card">'
        + '<h2>🧠 Train Your Voice</h2>'
        + '<div class="sub">The more real examples Alita has, the more it sounds like you.</div>'
        # Auto-learn sub-block
        + ('<div style="border:1.5px solid #5c6ac4;border-radius:10px;padding:16px;margin-bottom:20px">'
           if learn["enabled"] else
           '<div style="border:1.5px solid #eee;border-radius:10px;padding:16px;margin-bottom:20px">')
        + '<label style="display:flex;align-items:center;gap:8px;cursor:pointer;margin:0 0 8px;font-weight:700;font-size:.9rem">'
        + f'<input type="checkbox" name="auto_learn" value="1" {_auto_checked} '
        'onchange="this.form.submit()" form="tone-form" '
        'style="width:18px;height:18px;accent-color:#5c6ac4">'
        + '📸 Auto-learn from my Instagram posts'
        + '</label>'
        + '<div style="font-size:.82rem;color:#90949c;margin-bottom:10px">'
        'When Instagram is connected, Alita reads your recent posts and builds a style profile '
        'automatically — no manual samples needed.'
        '</div>'
        + f'<div>{_learn_badge}</div>'
        + f'{_relearn_btn}'
        + '</div>'
        # Style samples sub-block
        + '<label style="margin-top:4px;font-size:.85rem;font-weight:600;color:#444">Or paste your own writing samples</label>'
        + '<div class="notice" style="margin-top:8px">Paste 3–10 real messages, DMs, captions, or email snippets. '
        'The AI extracts your tone, vocabulary, and rhythm. '
        '<strong>Do not include sensitive information.</strong></div>'
        + f'<textarea name="samples" class="s-input" rows="10" placeholder="Paste your messages here...">{_load_samples(profile.client_id)}</textarea>'
        + ('<p style="font-size:.8rem;color:#27ae60;margin-top:8px">&#x2705; Samples saved — AI is using your voice</p>'
           if has_samples else '')
        + '</div>'
        # Save row — bottom
        + '<div style="display:flex;gap:12px;margin:20px 0 0">'
        + '<button type="submit" class="btn-primary">💾 Save Changes</button>'
        + '<a href="/settings" class="btn-secondary">← Back to Settings</a>'
        + '</div>'
        + '</form>'
        # ── Section 4: Advanced (outside form — uses fetch()) ─────────────────
        + '<div style="margin:32px 0 8px"><div class="hub-section-title">⚙️ Advanced Personalization</div></div>'
        + _humor_convo_html
        + _adj_html
        # ── Section 5: Test It ──────────────────────────────────────────────
        + '<div style="margin:32px 0 8px"><div class="hub-section-title">🧪 Test Your Settings</div></div>'
        + _test_html
    )
    from utils.shared_layout import build_page
    return HTMLResponse(build_page(
        title="Tone & Style",
        active_nav="tone",
        body_content=_tone_body,
        extra_css=_SETTINGS_CSS,
        extra_js=_tone_js,
        user_name=user.full_name,
        business_name=profile.business_name,
    ))


@router.post("/tone", response_class=HTMLResponse)
async def tone_save(
    request: Request,
    preset: str = Form(""),
    samples: str = Form(""),
    auto_learn: str = Form(""),
):
    user, profile, db = await _get_profile(request)
    db.close()
    if not user:
        return RedirectResponse("/account/login", status_code=303)

    form_data = await request.form()

    # Load existing prefs so we preserve auto-learned metadata fields
    prefs = _load_tone_prefs(profile.client_id)

    if preset and preset in PRESET_TONES:
        prefs["preset"] = preset
        prefs["system_prompt"] = PRESET_TONES[preset]["system"]
        prefs["label"] = PRESET_TONES[preset]["label"]

    # auto_learn checkbox: "1" when checked, "" when unchecked
    prefs["auto_learn"] = (auto_learn == "1")
    prefs["updated_at"] = datetime.utcnow().isoformat()

    # Save per-platform active toggles
    _plat_keys = ["instagram", "facebook", "tiktok", "linkedin", "twitter", "threads"]
    platform_active = {pk: (form_data.get(f"plat_{pk}") == "1") for pk in _plat_keys}
    prefs["platform_active"] = platform_active

    _save_tone_prefs(profile.client_id, prefs)

    if samples.strip():
        _save_samples(profile.client_id, samples.strip())

    msg = "Tone settings saved!"
    if preset:
        msg += f" Using: {PRESET_TONES.get(preset, {}).get('label', preset)}"
    if samples.strip():
        msg += " Writing samples saved."
    if prefs["auto_learn"]:
        msg += " Auto-learn enabled."

    return RedirectResponse(f"/settings/tone?msg={msg.replace(' ', '+')}", status_code=303)


@router.post("/tone/relearn", response_class=HTMLResponse)
async def tone_relearn(request: Request, background_tasks: BackgroundTasks):
    """
    Trigger a fresh auto-learn pass from the client's connected Instagram account.
    Reads token from TokenManager and fires learn_from_instagram as a BackgroundTask.
    """
    user, profile, db = await _get_profile(request)
    db.close()
    if not user:
        return RedirectResponse("/account/login", status_code=303)

    client_id = profile.client_id
    error_msg = None

    # ── Resolve IG credentials from meta_pages (Meta OAuth) or legacy file ──
    ig_account_id = None
    access_token  = None

    # Method 1: meta_pages in DB  (primary — works on Railway)
    try:
        _mp_raw = getattr(profile, "meta_pages", None) or "[]"
        _mp = json.loads(_mp_raw) if isinstance(_mp_raw, str) else _mp_raw
        if isinstance(_mp, list):
            for _pg in _mp:
                if _pg.get("instagram_connected") or _pg.get("instagram_id"):
                    ig_account_id = _pg.get("instagram_id")
                    access_token  = _pg.get("access_token", "")
                    break
    except Exception:
        pass

    # Method 2: legacy local JSON file
    if not ig_account_id:
        conn_path = os.path.join("storage", "connections", f"{client_id}.json")
        if os.path.exists(conn_path):
            try:
                with open(conn_path) as _f:
                    conn_info = json.load(_f)
                ig_account_id = conn_info.get("ig_account_id")
                meta_user_id  = conn_info.get("meta_user_id")
                if meta_user_id and not access_token:
                    from api.token_manager import TokenManager
                    tm = TokenManager()
                    token_data = tm.get_valid_token(meta_user_id)
                    if token_data:
                        access_token = token_data.access_token
            except Exception:
                pass

    if not ig_account_id or not access_token:
        error_msg = "Instagram not connected or token expired. Connect your account from the Connections page first."
    else:
        try:
            from utils.style_learner import learn_from_instagram, _load_prefs, _save_prefs
            prefs = _load_prefs(client_id)
            prefs["auto_learn_status"] = "running"
            _save_prefs(client_id, prefs)
            background_tasks.add_task(
                learn_from_instagram,
                client_id,
                access_token,
                ig_account_id,
            )
        except Exception as e:
            error_msg = f"Could not start analysis: {e}"

    if error_msg:
        redirect_url = f"/settings/tone?msg=Error:+{error_msg.replace(' ', '+')}"
    else:
        redirect_url = "/settings/tone?msg=Re-analysis+started.+Check+back+in+a+moment."

    return RedirectResponse(redirect_url, status_code=303)


@router.post("/tone/humor")
async def tone_humor_save(request: Request):
    """Save humor preferences (enabled, intensity, comedians)."""
    user, profile, db = await _get_profile(request)
    db.close()
    if not user:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)
    data = await request.json()
    prefs = _load_tone_prefs(profile.client_id)
    prefs.setdefault("humor", {})
    prefs["humor"]["enabled"]   = bool(data.get("enabled", False))
    prefs["humor"]["intensity"] = data.get("intensity", "balanced")
    prefs["humor"]["comedians"] = data.get("comedians", [])
    prefs["updated_at"] = datetime.utcnow().isoformat()
    _save_tone_prefs(profile.client_id, prefs)
    return JSONResponse({"ok": True})


@router.post("/tone/conversation")
async def tone_conversation_save(request: Request):
    """Save casual-conversation mode toggle."""
    user, profile, db = await _get_profile(request)
    db.close()
    if not user:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)
    data = await request.json()
    prefs = _load_tone_prefs(profile.client_id)
    prefs["casual_conversation"] = bool(data.get("enabled", False))
    prefs["updated_at"] = datetime.utcnow().isoformat()
    _save_tone_prefs(profile.client_id, prefs)
    return JSONResponse({"ok": True})


@router.post("/tone/adjustment/preview")
async def tone_adjustment_preview(request: Request):
    """Use Claude Haiku to describe in plain English what an adjustment will change."""
    user, profile, db = await _get_profile(request)
    db.close()
    if not user:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)
    data = await request.json()
    text = (data.get("text") or "").strip()
    platform = (data.get("platform") or "this channel").replace("_", " ")
    if not text:
        return JSONResponse({"error": "No adjustment text provided."}, status_code=400)
    try:
        from anthropic import Anthropic as _Anthropic
        _client = _Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
        _haiku = os.getenv("CLAUDE_HAIKU_MODEL", "claude-haiku-4-5-20251001")
        _prompt = (
            f"A client wants to add this adjustment instruction to how an AI engagement agent "
            f"replies on {platform}:\n\n\"{text}\"\n\n"
            f"In 2-3 plain sentences, describe ONLY what concrete changes this will make to the "
            f"AI's writing behaviour on that channel. Be specific and practical. "
            f"Do NOT include technical jargon, code, or prompt language. "
            f"Start with 'This adjustment will...' and finish with one example contrast if helpful "
            f"(e.g. 'Instead of X, the AI will Y.')."
        )
        _resp = _client.messages.create(
            model=_haiku,
            max_tokens=200,
            messages=[{"role": "user", "content": _prompt}]
        )
        description = _resp.content[0].text.strip()
        return JSONResponse({"description": description})
    except Exception as e:
        return JSONResponse({"description": f"Preview unavailable: {e}"})


@router.post("/tone/adjustment/save")
async def tone_adjustment_save(request: Request):
    """Append an adjustment text to one or more platform keys."""
    user, profile, db = await _get_profile(request)
    db.close()
    if not user:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)
    data = await request.json()
    text = (data.get("text") or "").strip()
    platforms = data.get("platforms") or []
    if not text or not platforms:
        return JSONResponse({"error": "Missing text or platforms."}, status_code=400)
    valid_keys = {pk for pk, _, _ in _ADJ_PLATFORMS}
    prefs = _load_tone_prefs(profile.client_id)
    adj = prefs.setdefault("platform_adjustments", {})
    for pk in platforms:
        if pk in valid_keys:
            adj.setdefault(pk, [])
            if text not in adj[pk]:          # deduplicate
                adj[pk].append(text)
    prefs["updated_at"] = datetime.utcnow().isoformat()
    _save_tone_prefs(profile.client_id, prefs)
    return JSONResponse({"ok": True})


@router.post("/tone/adjustment/delete")
async def tone_adjustment_delete(request: Request):
    """Remove one adjustment by platform key + index."""
    user, profile, db = await _get_profile(request)
    db.close()
    if not user:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)
    data = await request.json()
    platform = data.get("platform", "")
    idx      = data.get("index", -1)
    prefs = _load_tone_prefs(profile.client_id)
    adj_list = prefs.get("platform_adjustments", {}).get(platform, [])
    if 0 <= idx < len(adj_list):
        adj_list.pop(idx)
        prefs.setdefault("platform_adjustments", {})[platform] = adj_list
        prefs["updated_at"] = datetime.utcnow().isoformat()
        _save_tone_prefs(profile.client_id, prefs)
    return JSONResponse({"ok": True})


@router.post("/tone/test")
async def tone_test(request: Request):
    """Generate a test AI response using all current tone/humor/adjustment settings."""
    user, profile, db = await _get_profile(request)
    db.close()
    if not user:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)
    data = await request.json()
    channel = (data.get("channel") or "instagram_dm").strip()
    message = (data.get("message") or "").strip()
    if not message:
        return JSONResponse({"error": "No message provided."}, status_code=400)
    try:
        from agents.engagement_agent import EngagementAgent
        platform, _, chan = channel.partition("_")
        chan = chan or "dm"
        agent = EngagementAgent(client_id=profile.client_id, use_voice_matching=True)
        # Build list of active settings for UI display
        prefs = _load_tone_prefs(profile.client_id)
        humor_prefs = prefs.get("humor", {})
        adj_list = prefs.get("platform_adjustments", {}).get(channel, [])
        active_settings = []
        _preset = prefs.get("label") or prefs.get("preset", "")
        if _preset:
            active_settings.append(f"Preset: {_preset}")
        if humor_prefs.get("enabled"):
            _intensity = humor_prefs.get("intensity", "balanced")
            active_settings.append(f"Humor: {_intensity}")
            _comedian_names = [COMEDIAN_STYLES[c]["label"] for c in humor_prefs.get("comedians", []) if c in COMEDIAN_STYLES]
            if _comedian_names:
                active_settings.append("Inspired by: " + ", ".join(_comedian_names))
        if prefs.get("casual_conversation"):
            active_settings.append("Conversation mode: on")
        if adj_list:
            active_settings.append(f"{len(adj_list)} adjustment(s) for {channel.replace('_', ' ')}")
        reply = agent.respond_to_message(
            message=message,
            client_id=profile.client_id,
            sender_id="test_sandbox",
            use_memory=False,
            channel=chan,
            platform=platform or "instagram",
        )
        return JSONResponse({"reply": reply, "active_settings": active_settings})
    except Exception as e:
        return JSONResponse({"error": f"Test failed: {e}"}, status_code=500)


# ══════════════════════════════════════════════════════════════════════
# KNOWLEDGE BASE MANAGEMENT
# ══════════════════════════════════════════════════════════════════════

@router.get("/knowledge", response_class=HTMLResponse)
async def knowledge_page(request: Request):
    user, profile, db = await _get_profile(request)
    db.close()
    if not user:
        return RedirectResponse("/account/login", status_code=303)

    # Load existing KB entries
    entries_html = ""
    kb_count = 0
    try:
        from agents.rag_system import RAGSystem
        rag = RAGSystem()
        docs = rag.list_documents(client_id=profile.client_id)
        kb_count = len(docs)
        for doc in docs[-40:]:
            preview  = doc.get("text_preview", "")
            source   = doc.get("source",   "manual")
            cat      = doc.get("category", "")
            point_id = doc.get("id", "")
            tag      = f'<span class="pill pill-green">{cat}</span>' if cat else f'<span class="pill pill-gray">{source}</span>'
            del_btn  = (
                f'<button class="del-btn" title="Remove" '
                f'onclick="deleteEntry({repr(str(point_id))}, this)">&times;</button>'
                if point_id else ""
            )
            entries_html += (
                f'<div class="entry" id="entry-{point_id}">'
                f'<div class="entry-text">{preview}</div>'
                f'<div class="entry-meta">{tag}</div>'
                f'{del_btn}</div>'
            )
    except Exception as e:
        entries_html = f'<p style="color:#999;font-size:.87rem">Could not load entries: {e}</p>'

    msg = request.query_params.get("msg", "")
    tab = request.query_params.get("tab", "add")
    success_banner = (
        f'<div style="background:#e8f5e9;border-left:4px solid #27ae60;'
        f'padding:12px 16px;border-radius:0 8px 8px 0;margin-bottom:20px;'
        f'font-size:.88rem;color:#2e7d32">{msg}</div>'
    ) if msg else ""

    empty_msg = "<p style='color:#999;font-size:.87rem'>No entries yet &mdash; add some context to get started.</p>"
    client_id_repr = repr(profile.client_id)

    # ── KB page JavaScript (raw string — no Python interpolation needed) ──
    _kb_js = r"""
/* ── Import mode toggle ─────────────────────────────────────── */
var _webMode  = 'append';
var _fileMode = 'append';

function setImportMode(section, mode) {
  if (section === 'web')  _webMode  = mode;
  if (section === 'file') _fileMode = mode;
  ['append','replace'].forEach(m => {
    const btn = document.getElementById(section + '-mode-' + m);
    if (btn) btn.classList.toggle('active', m === mode);
  });
}

function setStatus(id, html, type) {
  const el = document.getElementById(id);
  if (!el) return;
  const bg = {
    info:    'background:#f0f2ff;border-left:4px solid #5c6ac4;color:#3d4cb5',
    success: 'background:#e8f5e9;border-left:4px solid #27ae60;color:#2e7d32',
    error:   'background:#fff0f0;border-left:4px solid #c0392b;color:#c0392b',
  }[type] || 'background:#f0f2ff;border-left:4px solid #5c6ac4;color:#3d4cb5';
  el.innerHTML = `<div style="${bg};padding:12px 16px;border-radius:0 8px 8px 0;font-size:.87rem;margin-top:14px">${html}</div>`;
}

/* ── Website import ─────────────────────────────────────────── */
async function importWebsite() {
  const url = document.getElementById('web-url').value.trim();
  if (!url) { setStatus('web-status', 'Please enter a website URL.', 'error'); return; }
  const btn = document.getElementById('web-import-btn');
  btn.disabled = true; btn.textContent = '⏳ Scraping…';
  setStatus('web-status', '🔍 Scraping your website in the background — this takes 20–40 seconds. You can keep working; the AI will have your content shortly.', 'info');
  try {
    const res  = await fetch('/settings/knowledge/website-import', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({url, replace: _webMode === 'replace'})
    });
    const data = await res.json();
    if (data.ok) {
      setStatus('web-status', data.message || '✅ Import started! Your knowledge base will update in the background.', 'success');
      document.getElementById('web-url').value = '';
    } else {
      setStatus('web-status', '❌ ' + (data.error || 'Import failed.'), 'error');
    }
  } catch(e) {
    setStatus('web-status', '❌ Error: ' + e.message, 'error');
  }
  btn.disabled = false; btn.textContent = '🔄 Import from Website';
}

/* ── File upload ─────────────────────────────────────────────── */
var _selectedFiles = null;

function renderFileList(files) {
  _selectedFiles = files;
  const list = document.getElementById('files-list');
  const btn  = document.getElementById('files-upload-btn');
  if (!files || !files.length) { list.innerHTML = ''; btn.disabled = true; btn.style.opacity = '.4'; btn.style.cursor = 'not-allowed'; return; }
  const EXT_ICON = {pdf:'📄', docx:'📝', doc:'📝', txt:'📃', md:'📋', markdown:'📋'};
  const fmt = s => s < 1024 ? s + ' B' : s < 1048576 ? (s/1024).toFixed(1) + ' KB' : (s/1048576).toFixed(1) + ' MB';
  let html = '<div style="margin-top:12px;display:flex;flex-direction:column;gap:6px">';
  Array.from(files).forEach(f => {
    const ext  = f.name.split('.').pop().toLowerCase();
    const icon = EXT_ICON[ext] || '📎';
    html += `<div style="display:flex;align-items:center;gap:10px;background:#f8f9fa;border-radius:8px;padding:8px 12px;font-size:.85rem">
      <span>${icon}</span>
      <span style="flex:1;font-weight:600;color:#333">${esc(f.name)}</span>
      <span style="color:#999">${fmt(f.size)}</span>
    </div>`;
  });
  html += '</div>';
  list.innerHTML = html;
  btn.disabled = false; btn.style.opacity = '1'; btn.style.cursor = 'pointer';
}

async function uploadFiles() {
  if (!_selectedFiles || !_selectedFiles.length) {
    setStatus('files-status', 'Please select at least one file.', 'error'); return;
  }
  const btn = document.getElementById('files-upload-btn');
  btn.disabled = true; btn.textContent = '⏳ Uploading…';
  setStatus('files-status', '📤 Uploading and ingesting your documents — this runs in the background. The AI will have your content in about 15 seconds.', 'info');
  try {
    const fd = new FormData();
    Array.from(_selectedFiles).forEach(f => fd.append('files', f));
    fd.append('replace', _fileMode === 'replace' ? '1' : '0');
    const res  = await fetch('/settings/knowledge/file-import', {method: 'POST', body: fd});
    const data = await res.json();
    if (data.ok) {
      setStatus('files-status', data.message || '✅ Files queued for ingestion! Your knowledge base will update shortly.', 'success');
      document.getElementById('files-input').value = '';
      document.getElementById('files-list').innerHTML = '';
      _selectedFiles = null;
      btn.disabled = true; btn.style.opacity = '.4'; btn.style.cursor = 'not-allowed';
    } else {
      setStatus('files-status', '❌ ' + (data.error || 'Upload failed.'), 'error');
      btn.disabled = false; btn.style.opacity = '1'; btn.style.cursor = 'pointer';
    }
  } catch(e) {
    setStatus('files-status', '❌ Error: ' + e.message, 'error');
    btn.disabled = false; btn.style.opacity = '1'; btn.style.cursor = 'pointer';
  }
  btn.textContent = '📤 Upload & Ingest';
}

/* ── FAQ generator ───────────────────────────────────────────── */
async function generateFaqs() {
  const query = document.getElementById('faq-query').value.trim();
  if (!query) { alert('Please enter a research query first.'); return; }
  document.getElementById('faq-spinner').style.display = 'block';
  document.getElementById('faq-results').innerHTML = '';
  const genBtn = document.getElementById('faq-gen-btn');
  if (genBtn) { genBtn.disabled = true; genBtn.textContent = '⏳ Researching…'; }
  try {
    const res  = await fetch('/settings/knowledge/faq-generate', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({query})
    });
    const data = await res.json();
    document.getElementById('faq-spinner').style.display = 'none';
    if (data.error) {
      document.getElementById('faq-results').innerHTML =
        `<div class="notice" style="border-color:#e74c3c;background:#fff0f0;color:#c0392b">${data.error}</div>`;
      return;
    }
    const faqs = data.faqs || [];
    if (!faqs.length) {
      document.getElementById('faq-results').innerHTML = '<p style="color:#999">No FAQs generated. Try a more specific query.</p>';
      return;
    }
    const dups = faqs.filter(f => f.is_duplicate).length;
    let html = `<div style="font-size:.85rem;color:#777;margin-bottom:16px">Generated <strong>${faqs.length} FAQs</strong>`;
    if (dups) html += ` &mdash; <span style="color:#c0392b">${dups} already in your knowledge base</span>`;
    html += `</div>`;
    faqs.forEach((faq, i) => {
      const isDup = faq.is_duplicate;
      html += `<div class="faq-card ${isDup ? 'dup' : ''}" id="faq-card-${i}">
        <div class="faq-q">Q: ${esc(faq.q)}</div>
        <div class="faq-a">A: ${esc(faq.a)}</div>
        <div class="faq-footer">`;
      if (isDup) {
        html += `<span class="dup-badge">&#x26A0; Already in KB</span>`;
        if (faq.dup_preview) html += `<span style="font-size:.76rem;color:#999">&ldquo;${esc(faq.dup_preview.slice(0,80))}&hellip;&rdquo;</span>`;
      } else {
        html += `<button class="btn btn-primary" style="padding:6px 16px;font-size:.82rem"
          onclick="addFaq(${i},this)" data-q=${JSON.stringify(faq.q)} data-a=${JSON.stringify(faq.a)}>Add to KB</button>
          <button class="btn" style="padding:6px 14px;font-size:.82rem;background:#f5f6fa;color:#888"
          onclick="dismissFaq(${i})">Skip</button>`;
      }
      html += `</div></div>`;
    });
    document.getElementById('faq-results').innerHTML = html;
  } catch(e) {
    document.getElementById('faq-spinner').style.display = 'none';
    document.getElementById('faq-results').innerHTML =
      `<div class="notice" style="border-color:#e74c3c;background:#fff0f0;color:#c0392b">Error: ${e.message}</div>`;
  }
  if (genBtn) { genBtn.disabled = false; genBtn.textContent = '🔍 Generate FAQs'; }
}

async function addFaq(i, btn) {
  const q = btn.dataset.q, a = btn.dataset.a;
  btn.disabled = true; btn.textContent = 'Adding\u2026';
  try {
    const res  = await fetch('/settings/knowledge/faq-add', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({q, a})
    });
    const data = await res.json();
    if (data.ok) {
      const card = document.getElementById('faq-card-' + i);
      card.classList.add('added');
      card.querySelector('.faq-footer').innerHTML =
        '<span style="color:#27ae60;font-size:.85rem;font-weight:600">&#x2713; Added to Knowledge Base</span>';
    } else { btn.textContent = 'Error'; btn.disabled = false; }
  } catch(e) { btn.textContent = 'Error'; btn.disabled = false; }
}

function dismissFaq(i) {
  const card = document.getElementById('faq-card-' + i);
  card.style.opacity = '.35';
  card.querySelector('.faq-footer').innerHTML = '<span style="color:#aaa;font-size:.82rem">Skipped</span>';
}

async function deleteEntry(pointId, btn) {
  if (!confirm('Remove this entry from your knowledge base?')) return;
  btn.textContent = '\u2026';
  try {
    const res  = await fetch('/settings/knowledge/delete', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({point_id: pointId})
    });
    const data = await res.json();
    if (data.ok) {
      const row = document.getElementById('entry-' + pointId);
      if (row) row.remove();
    } else { btn.textContent = '\u00d7'; }
  } catch(e) { btn.textContent = '\u00d7'; }
}

function esc(s) { const d = document.createElement('div'); d.textContent = s; return d.innerHTML; }

/* ── Drop zone wiring (runs after DOM ready) ─────────────────── */
document.addEventListener('DOMContentLoaded', function() {
  const drop = document.getElementById('files-drop');
  const inp  = document.getElementById('files-input');
  if (!drop || !inp) return;
  drop.addEventListener('click', () => inp.click());
  inp.addEventListener('change', () => renderFileList(inp.files));
  drop.addEventListener('dragover',  e => { e.preventDefault(); drop.classList.add('dragover'); });
  drop.addEventListener('dragleave', ()  => drop.classList.remove('dragover'));
  drop.addEventListener('drop', e => {
    e.preventDefault();
    drop.classList.remove('dragover');
    const dt = new DataTransfer();
    Array.from(e.dataTransfer.files).forEach(f => dt.items.add(f));
    inp.files = dt.files;
    renderFileList(inp.files);
  });
});
"""

    # ── Extra CSS for new KB elements ────────────────────────────────────────
    _kb_extra_css = """
.import-mode-btn{padding:6px 18px;border:1.5px solid #dde0e4;border-radius:6px;background:#fff;
  color:#666;font-size:.84rem;font-weight:600;cursor:pointer;transition:all .12s}
.import-mode-btn.active{border-color:#5c6ac4;background:#5c6ac4;color:#fff}
.drop-zone{border:2px dashed #c5cbdf;border-radius:10px;padding:32px 20px;text-align:center;
  cursor:pointer;transition:border .15s,background .15s;background:#fafbff;margin-top:8px}
.drop-zone:hover,.drop-zone.dragover{border-color:#5c6ac4;background:#f0f2ff}
.drop-icon{font-size:2rem;margin-bottom:8px}
.drop-text{font-size:.9rem;color:#666;font-weight:600}
.drop-hint{font-size:.8rem;color:#aaa;margin-top:4px}
"""

    _kb_body = f"""
  {success_banner}

  <!-- ── Page header ─────────────────────────────────────────── -->
  <div style="margin-bottom:24px">
    <h1 style="font-size:1.4rem;font-weight:700;color:#1c1e21;margin:0 0 6px">&#x1F4DA; Knowledge Base</h1>
    <p style="color:#90949c;font-size:.9rem;margin:0">Everything you add here shapes how your AI writes content, replies to comments, and answers messages across every platform.</p>
  </div>

  <!-- ── SECTION: Quick Import ───────────────────────────────── -->
  <div class="hub-section-title">&#x26A1; Quick Import</div>

  <!-- Website Import -->
  <div class="card" id="card-website">
    <h2>&#x1F310; Import from Your Website</h2>
    <div class="sub">Paste your website URL and we'll automatically scrape every page — products, services, about, FAQ, pricing — and load it all into your knowledge base.</div>
    <div class="notice">&#x1F4CC; This works the same way as your initial onboarding setup. Use it any time your website is updated to keep the AI current.</div>
    <label>Website URL</label>
    <input type="url" id="web-url" class="s-input" placeholder="https://yourbusiness.com" style="margin-bottom:16px">
    <div style="font-size:.82rem;font-weight:600;color:#444;margin-bottom:8px">If you've imported before, what should happen?</div>
    <div style="display:flex;gap:8px;flex-wrap:wrap">
      <button type="button" id="web-mode-append"  class="import-mode-btn active" onclick="setImportMode('web','append')">&#x2795; Add to existing</button>
      <button type="button" id="web-mode-replace" class="import-mode-btn"        onclick="setImportMode('web','replace')">&#x1F504; Replace website entries</button>
    </div>
    <div style="font-size:.78rem;color:#aaa;margin:6px 0 16px">Replace mode removes all previous website-scraped entries before importing fresh content.</div>
    <button type="button" id="web-import-btn" class="btn btn-primary" onclick="importWebsite()">&#x1F504; Import from Website</button>
    <div id="web-status"></div>
  </div>

  <!-- File Upload -->
  <div class="card" id="card-files">
    <h2>&#x1F4C2; Upload Documents</h2>
    <div class="sub">Upload files directly — pricing guides, service menus, brand bibles, policies, scripts, or any document you want your AI to reference.</div>
    <div class="notice">&#x1F4CC; Supported formats: <strong>.pdf &bull; .docx &bull; .txt &bull; .md</strong> &mdash; up to 10 files at once.</div>
    <div id="files-drop" class="drop-zone">
      <div class="drop-icon">&#x1F4C1;</div>
      <div class="drop-text">Drag &amp; drop files here, or click to browse</div>
      <div class="drop-hint">.pdf &nbsp;&bull;&nbsp; .docx &nbsp;&bull;&nbsp; .txt &nbsp;&bull;&nbsp; .md</div>
    </div>
    <input type="file" id="files-input" multiple accept=".pdf,.docx,.txt,.md,.markdown" style="display:none">
    <div id="files-list"></div>
    <div style="font-size:.82rem;font-weight:600;color:#444;margin:16px 0 8px">If you've uploaded before, what should happen?</div>
    <div style="display:flex;gap:8px;flex-wrap:wrap">
      <button type="button" id="file-mode-append"  class="import-mode-btn active" onclick="setImportMode('file','append')">&#x2795; Add to existing</button>
      <button type="button" id="file-mode-replace" class="import-mode-btn"        onclick="setImportMode('file','replace')">&#x1F504; Replace uploaded docs</button>
    </div>
    <div style="font-size:.78rem;color:#aaa;margin:6px 0 16px">Replace mode removes all previously uploaded document entries before ingesting the new files.</div>
    <button type="button" id="files-upload-btn" class="btn btn-primary" onclick="uploadFiles()" disabled style="opacity:.4;cursor:not-allowed">&#x1F4E4; Upload &amp; Ingest</button>
    <div id="files-status"></div>
  </div>

  <!-- ── SECTION: Add Content Manually ───────────────────────── -->
  <div class="hub-section-title">&#x270F;&#xFE0F; Add Content Manually</div>

  <div class="card">
    <h2>&#x270F;&#xFE0F; Quick Add</h2>
    <div class="sub">Type anything you want your AI to know — a product detail, a policy, a team bio, a common question and answer. Every entry improves how your AI represents your brand.</div>
    <div class="notice">
      Examples: &ldquo;We offer 3 monthly packages starting at $99&rdquo; &bull;
      &ldquo;Our return policy is 30 days, no questions asked&rdquo; &bull;
      &ldquo;Our founder Sarah Chen has 10 years of industry experience&rdquo;
    </div>
    <form method="post" action="/settings/knowledge">
      <label>What would you like to add?</label>
      <textarea name="text" rows="5" placeholder="e.g. We specialize in luxury wedding photography with 10 years of experience. Our packages start at $2,500 and include a full gallery within 3 weeks." required></textarea>
      <label>Label <span style="font-weight:400;color:#999">(optional)</span></label>
      <input type="text" name="label" placeholder="e.g. Pricing, FAQ, Product, Brand Story, Policy, Team">
      <div style="margin-top:16px">
        <button type="submit" class="btn btn-primary">&#x2795; Add to Knowledge Base</button>
      </div>
    </form>
  </div>

  <!-- ── SECTION: AI-Powered FAQ Builder ─────────────────────── -->
  <div class="hub-section-title">&#x1F9E0; AI-Powered FAQ Builder</div>

  <div class="card">
    <h2>&#x1F9E0; Generate FAQs with Deep Research</h2>
    <div class="sub">Describe your business or a topic and we'll use AI + live web research to generate 8&ndash;12 detailed Q&amp;A pairs. Each FAQ is checked against your existing knowledge base — duplicates are flagged automatically so you stay clean.</div>
    <div class="notice">
      Try: &ldquo;What do customers ask about our massage services?&rdquo; &bull;
      &ldquo;Common questions about pricing for a photography studio&rdquo; &bull;
      &ldquo;FAQ for a luxury cruise travel agency&rdquo;
    </div>
    <label>Research query</label>
    <textarea id="faq-query" class="s-input" rows="3" placeholder="e.g. What are the most common questions people ask about luxury travel packages?"></textarea>
    <div style="margin-top:16px">
      <button id="faq-gen-btn" class="btn btn-primary" onclick="generateFaqs()">&#x1F50D; Generate FAQs</button>
    </div>
    <div class="faq-spinner" id="faq-spinner">
      <div style="font-size:2rem;margin-bottom:8px">&#x1F50D;</div>
      Running deep research &mdash; this takes 20&ndash;40 seconds&hellip;
    </div>
    <div id="faq-results"></div>
  </div>

  <!-- ── SECTION: Browse & Manage ────────────────────────────── -->
  <div class="hub-section-title">&#x1F4CB; Browse &amp; Manage</div>

  <div class="card">
    <h2>Your Knowledge Base &nbsp;<span class="pill pill-gray" style="font-size:.8rem">{kb_count} entries</span></h2>
    <div class="sub">Showing the most recent 40 entries. Click &times; to remove any entry. Re-import or upload new files above to refresh your content.</div>
    <div id="entries-container">
      {entries_html if entries_html else empty_msg}
    </div>
  </div>
"""
    from utils.shared_layout import build_page
    return HTMLResponse(build_page(
        title="Knowledge Base",
        active_nav="knowledge",
        body_content=_kb_body,
        extra_css=_SETTINGS_CSS + _kb_extra_css,
        extra_js=_kb_js,
        user_name=user.full_name,
        business_name=profile.business_name,
    ))


# ══════════════════════════════════════════════════════════════════════
# Knowledge Base — Website Import  (POST /settings/knowledge/website-import)
# ══════════════════════════════════════════════════════════════════════

@router.post("/knowledge/website-import")
async def kb_website_import(
    background_tasks: BackgroundTasks,
    request: Request,
):
    """Scrape a website and load content into the RAG knowledge base."""
    user, profile, db = await _get_profile(request)
    db.close()
    if not user:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)

    body    = await request.json()
    url     = (body.get("url") or "").strip()
    replace = bool(body.get("replace", False))

    if not url:
        return JSONResponse({"error": "URL is required."}, status_code=400)
    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    # Replace mode — delete previous website entries for this client
    if replace:
        try:
            from agents.rag_system import RAGSystem
            rag  = RAGSystem()
            for cat in ("website", "business_profile"):
                docs = rag.list_documents(client_id=profile.client_id, category=cat, limit=10000)
                for doc in docs:
                    try:
                        rag.delete_document(doc["id"])
                    except Exception:
                        pass
        except Exception as del_err:
            print(f"[KB] Website replace-delete warning: {del_err}")

    background_tasks.add_task(
        _kb_run_website_scrape,
        client_id=profile.client_id,
        business_name=profile.business_name or "",
        url=url,
    )
    mode_label = "Replacing old website entries and importing" if replace else "Importing"
    return JSONResponse({
        "ok": True,
        "message": (
            f"✅ {mode_label} <strong>{url}</strong> — scraping in the background. "
            f"Your knowledge base will update in 20–40 seconds."
        ),
    })


async def _kb_run_website_scrape(client_id: str, business_name: str, url: str):
    """Background helper: scrape → RAG (no profile status side-effects)."""
    try:
        from utils.website_scraper import scrape_and_ingest
        await scrape_and_ingest(url=url, client_id=client_id, business_name=business_name)
    except Exception as e:
        print(f"[KB] Website scrape error for {client_id}: {e}")


# ══════════════════════════════════════════════════════════════════════
# Knowledge Base — File Import  (POST /settings/knowledge/file-import)
# ══════════════════════════════════════════════════════════════════════

@router.post("/knowledge/file-import")
async def kb_file_import(
    background_tasks: BackgroundTasks,
    request: Request,
    files: List[UploadFile] = File(...),
    replace: str = Form("0"),
):
    """Upload documents and ingest them into the RAG knowledge base."""
    user, profile, db = await _get_profile(request)
    db.close()
    if not user:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)

    do_replace   = replace in ("1", "true", "True")
    allowed_ext  = {".pdf", ".docx", ".txt", ".md", ".markdown"}

    from pathlib import Path
    import uuid

    upload_dir = Path("storage") / "uploaded_docs" / profile.client_id
    upload_dir.mkdir(parents=True, exist_ok=True)

    saved_paths: list = []
    for uf in files:
        ext = Path(uf.filename).suffix.lower()
        if ext not in allowed_ext:
            continue
        dest     = upload_dir / f"{uuid.uuid4().hex[:8]}_{uf.filename}"
        contents = await uf.read()
        dest.write_bytes(contents)
        saved_paths.append(str(dest))

    if not saved_paths:
        return JSONResponse(
            {"error": "No valid files found. Supported formats: .pdf, .docx, .txt, .md"},
            status_code=400,
        )

    # Replace mode — delete previous uploaded_document entries
    if do_replace:
        try:
            from agents.rag_system import RAGSystem
            rag  = RAGSystem()
            docs = rag.list_documents(client_id=profile.client_id, category="uploaded_document", limit=10000)
            for doc in docs:
                try:
                    rag.delete_document(doc["id"])
                except Exception:
                    pass
        except Exception as del_err:
            print(f"[KB] File replace-delete warning: {del_err}")

    background_tasks.add_task(
        _kb_run_file_ingest,
        client_id=profile.client_id,
        file_paths=saved_paths,
    )
    count      = len(saved_paths)
    noun       = "file" if count == 1 else "files"
    mode_label = "Replacing old uploaded entries and ingesting" if do_replace else "Ingesting"
    return JSONResponse({
        "ok": True,
        "message": (
            f"✅ {mode_label} <strong>{count} {noun}</strong> — "
            f"processing in the background. Your knowledge base will update in about 15 seconds."
        ),
    })


async def _kb_run_file_ingest(client_id: str, file_paths: list):
    """Background helper: extract text from uploaded files → ingest into RAG."""
    from agents.rag_system import RAGSystem
    from utils.file_reader import extract_text_from_file
    from pathlib import Path
    _CHUNK = 4_000
    try:
        rag = RAGSystem()
        for fpath in file_paths:
            fname = Path(fpath).name
            try:
                text = extract_text_from_file(fpath)
                if not text or not text.strip():
                    continue
                for i in range(0, len(text), _CHUNK):
                    chunk = text[i:i + _CHUNK].strip()
                    if not chunk:
                        continue
                    rag.add_knowledge(
                        text=chunk,
                        client_id=client_id,
                        source=fname,
                        category="uploaded_document",
                        tags=["file_upload", Path(fpath).suffix.lstrip(".")],
                    )
            except Exception as fe:
                print(f"[KB] File ingest error {fname}: {fe}")
    except Exception as e:
        print(f"[KB] File ingest task error for {client_id}: {e}")


@router.post("/knowledge", response_class=HTMLResponse)
async def knowledge_add(
    request: Request,
    text: str = Form(...),
    label: str = Form(""),
):
    user, profile, db = await _get_profile(request)
    db.close()
    if not user:
        return RedirectResponse("/account/login", status_code=303)

    if not text.strip():
        return RedirectResponse("/settings/knowledge?msg=Nothing+to+add", status_code=303)

    try:
        from agents.rag_system import RAGSystem
        rag = RAGSystem()
        source_label = label.strip() or "manual"
        rag.add_knowledge(
            text=text.strip(),
            client_id=profile.client_id,
            metadata={"source": "manual", "category": source_label, "added_at": datetime.utcnow().isoformat()},
        )
        # Also persist to disk so the chatbot can use it across restarts
        try:
            from agents.alita_assistant import save_client_knowledge_entry
            save_client_knowledge_entry(
                client_id=profile.client_id,
                text=text.strip(),
                source="manual",
                category=source_label,
            )
        except Exception as disk_err:
            print(f"[KB] Disk persist warning: {disk_err}")
        msg = "Added+to+knowledge+base!"
    except Exception as e:
        msg = f"Error:+{str(e)[:80]}"

    return RedirectResponse(f"/settings/knowledge?msg={msg}&tab=add", status_code=303)


# ══════════════════════════════════════════════════════════════════════
# FAQ Generator — JSON endpoints
# ══════════════════════════════════════════════════════════════════════

@router.post("/knowledge/faq-generate")
async def knowledge_faq_generate(request: Request):
    """Generate deduplicated FAQ Q&A pairs via deep research. Returns JSON."""
    from fastapi.responses import JSONResponse
    import re as _re, json as _json
    import anthropic as _anthropic
    import httpx as _httpx

    user, profile, db = await _get_profile(request)
    db.close()
    if not user:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)

    body  = await request.json()
    query = (body.get("query") or "").strip()
    if not query:
        return JSONResponse({"error": "Query is required"}, status_code=400)

    business_name = profile.business_name or "the business"

    faq_prompt = (
        f"You are building a FAQ knowledge base for {business_name}.\n\n"
        f"Research query: {query}\n\n"
        f"Generate between 8 and 12 frequently-asked questions AND detailed answers "
        f"that real customers would ask.\n\n"
        f"Rules:\n"
        f"- Questions must be specific and practical (not generic)\n"
        f"- Answers should be 2-4 sentences, friendly and professional\n"
        f"- Cover different angles: pricing, process, benefits, common concerns, comparisons\n\n"
        f'Return ONLY a valid JSON array, no markdown:\n'
        f'[{{"q": "Question here?", "a": "Answer here."}}, ...]'
    )

    raw_faqs = None

    # Try Gemini + Google Search first
    gemini_key = os.getenv("GEMINI_API_KEY")
    if gemini_key:
        try:
            payload = {
                "contents": [{"parts": [{"text": faq_prompt}], "role": "user"}],
                "generationConfig": {"temperature": 0.4, "maxOutputTokens": 4096},
                "tools": [{"googleSearch": {}}],
            }
            gurl = (
                "https://generativelanguage.googleapis.com/v1beta/"
                f"models/gemini-2.0-flash-exp:generateContent?key={gemini_key}"
            )
            async with _httpx.AsyncClient(timeout=90) as hc:
                resp = await hc.post(gurl, headers={"Content-Type": "application/json"}, json=payload)
                if resp.status_code == 200:
                    gdata  = resp.json()
                    parts  = gdata.get("candidates", [{}])[0].get("content", {}).get("parts", [])
                    raw_faqs = " ".join(p.get("text", "") for p in parts if "text" in p).strip()
        except Exception as ge:
            print(f"[FAQ] Gemini error: {ge}")

    # Fallback: Claude Sonnet
    if not raw_faqs:
        try:
            ac  = _anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
            res = ac.messages.create(
                model=os.getenv("CLAUDE_SONNET_MODEL", "claude-sonnet-4-5-20250929"),
                max_tokens=3000,
                messages=[{"role": "user", "content": faq_prompt}],
            )
            raw_faqs = res.content[0].text.strip()
        except Exception as ce:
            return JSONResponse({"error": f"Research failed: {ce}"}, status_code=500)

    # Parse JSON array
    faqs: list = []
    try:
        clean = _re.sub(r'^```[\w]*\n?', '', raw_faqs.strip(), flags=_re.MULTILINE)
        clean = _re.sub(r'```\s*$', '', clean.strip())
        m = _re.search(r'\[.*\]', clean, _re.DOTALL)
        if m:
            faqs = _json.loads(m.group())
    except Exception:
        try:
            ac   = _anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
            fix  = ac.messages.create(
                model=os.getenv("CLAUDE_HAIKU_MODEL", "claude-haiku-4-5-20251001"),
                max_tokens=3000,
                messages=[{"role": "user", "content":
                    f"Extract FAQ pairs from the text below as a JSON array with keys q and a. "
                    f"Return ONLY the JSON array:\n\n{raw_faqs[:4000]}"}],
            )
            m2 = _re.search(r'\[.*\]', fix.content[0].text, _re.DOTALL)
            if m2:
                faqs = _json.loads(m2.group())
        except Exception:
            return JSONResponse({"error": "Could not parse FAQ output. Try rephrasing your query."}, status_code=500)

    if not faqs:
        return JSONResponse({"error": "No FAQs generated. Try a more specific query."}, status_code=400)

    # Deduplicate against existing RAG entries
    try:
        from agents.rag_system import RAGSystem
        rag = RAGSystem()
        result_faqs = []
        for item in faqs:
            q = str(item.get("q", "")).strip()
            a = str(item.get("a", "")).strip()
            if not q or not a:
                continue
            hits     = rag.search(query=f"Q: {q}\nA: {a}", client_id=profile.client_id,
                                  limit=1, score_threshold=0.88)
            is_dup   = bool(hits)
            dup_prev = hits[0]["text"][:120] if is_dup else ""
            result_faqs.append({"q": q, "a": a, "is_duplicate": is_dup, "dup_preview": dup_prev})
    except Exception:
        result_faqs = [
            {"q": str(f.get("q", "")), "a": str(f.get("a", "")), "is_duplicate": False, "dup_preview": ""}
            for f in faqs
        ]

    return JSONResponse({"faqs": result_faqs, "total": len(result_faqs)})


@router.post("/knowledge/faq-add")
async def knowledge_faq_add(request: Request):
    """Add a single FAQ Q&A pair to the RAG knowledge base."""
    from fastapi.responses import JSONResponse

    user, profile, db = await _get_profile(request)
    db.close()
    if not user:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)

    body = await request.json()
    q    = (body.get("q") or "").strip()
    a    = (body.get("a") or "").strip()
    if not q or not a:
        return JSONResponse({"error": "q and a are required"}, status_code=400)

    faq_text = f"Q: {q}\nA: {a}"
    try:
        from agents.rag_system import RAGSystem
        rag = RAGSystem()
        rag.add_knowledge(
            text=faq_text,
            client_id=profile.client_id,
            source="faq_research",
            category="faq",
            tags=["faq", "deep_research"],
            metadata={"question": q, "added_at": datetime.utcnow().isoformat()},
        )
        try:
            from agents.alita_assistant import save_client_knowledge_entry
            save_client_knowledge_entry(
                client_id=profile.client_id, text=faq_text,
                source="faq_research", category="faq",
            )
        except Exception:
            pass
        return JSONResponse({"ok": True})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@router.post("/knowledge/delete")
async def knowledge_delete_entry(request: Request):
    """Delete a single RAG entry by Qdrant point_id."""
    from fastapi.responses import JSONResponse

    user, profile, db = await _get_profile(request)
    db.close()
    if not user:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)

    body     = await request.json()
    point_id = body.get("point_id")
    if not point_id:
        return JSONResponse({"error": "point_id required"}, status_code=400)

    try:
        from agents.rag_system import RAGSystem
        rag = RAGSystem()
        try:
            point_id = int(point_id)
        except (ValueError, TypeError):
            pass
        ok = rag.delete_document(point_id)
        return JSONResponse({"ok": ok})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


# ══════════════════════════════════════════════════════════════════════
# EMAIL INBOX CONNECT  (self-service Gmail OAuth)
# ══════════════════════════════════════════════════════════════════════

def _get_gmail_token(profile, db):
    """Check if this client has a stored Gmail OAuth token."""
    from database.models import GmailOAuthToken
    return db.query(GmailOAuthToken).filter(
        GmailOAuthToken.client_profile_id == profile.id
    ).first()


def _encrypt_token(raw: str) -> str:
    """Fernet-encrypt a refresh token for DB storage."""
    from cryptography.fernet import Fernet
    key = os.getenv("TOKEN_ENCRYPTION_KEY")
    if not key:
        # Fallback: store plaintext (not recommended)
        return raw
    return Fernet(key.encode()).encrypt(raw.encode()).decode()


def _decrypt_token(enc: str) -> str:
    """Fernet-decrypt a stored refresh token."""
    from cryptography.fernet import Fernet
    key = os.getenv("TOKEN_ENCRYPTION_KEY")
    if not key:
        return enc
    try:
        return Fernet(key.encode()).decrypt(enc.encode()).decode()
    except Exception:
        return enc   # might be plaintext from fallback


@router.get("/email", response_class=HTMLResponse)
async def email_page(request: Request):
    """Redirect to the unified /email hub."""
    return RedirectResponse("/email?tab=connect", status_code=303)


# ── Gmail OAuth: Step 1 — redirect to Google consent screen ──────────

@router.get("/email/authorize")
async def gmail_authorize(request: Request):
    """Redirect the user to Google's OAuth consent screen."""
    import secrets as _sec
    from urllib.parse import urlencode as _ue

    user, profile, db = await _get_profile(request)

    # Block if user hasn't accepted the email AI agreement
    if profile and not getattr(profile, "email_ai_agreed_at", None):
        db.close()
        return RedirectResponse("/email?tab=connect&error=agreement_required", status_code=303)

    db.close()
    if not user:
        return RedirectResponse("/account/login", status_code=303)

    client_id = os.getenv("GMAIL_CLIENT_ID")
    if not client_id:
        raise HTTPException(status_code=500, detail="Gmail OAuth not configured (GMAIL_CLIENT_ID missing)")

    redirect_uri = os.getenv(
        "GMAIL_REDIRECT_URI",
        os.getenv("APP_BASE_URL", "http://localhost:8000") + "/settings/email/callback"
    )

    # State encodes the profile id so we know who to store the token for
    state = f"{profile.id}:{_sec.token_urlsafe(16)}"

    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": "https://www.googleapis.com/auth/gmail.readonly https://www.googleapis.com/auth/gmail.send https://www.googleapis.com/auth/userinfo.email",
        "access_type": "offline",
        "prompt": "consent",   # always show consent so we get a refresh_token
        "state": state,
        "login_hint": user.email,
    }
    auth_url = f"https://accounts.google.com/o/oauth2/v2/auth?{_ue(params)}"
    return RedirectResponse(url=auth_url)


# ── Gmail OAuth: Step 2 — handle callback from Google ────────────────

@router.get("/email/callback", response_class=HTMLResponse)
async def gmail_callback(request: Request, code: str = Query(...), state: str = Query("")):
    """Exchange the authorization code for tokens and store the refresh token."""
    import httpx
    import uuid as _uuid

    # Validate state
    parts = state.split(":", 1)
    if len(parts) != 2:
        raise HTTPException(status_code=400, detail="Invalid state parameter")
    profile_id = parts[0]

    client_id = os.getenv("GMAIL_CLIENT_ID")
    client_secret = os.getenv("GMAIL_CLIENT_SECRET")
    redirect_uri = os.getenv(
        "GMAIL_REDIRECT_URI",
        os.getenv("APP_BASE_URL", "http://localhost:8000") + "/settings/email/callback"
    )

    # Exchange code for tokens
    async with httpx.AsyncClient() as client:
        resp = await client.post("https://oauth2.googleapis.com/token", data={
            "code": code,
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
        })

    if resp.status_code != 200:
        err = resp.json().get("error_description", resp.text[:200])
        raise HTTPException(status_code=400, detail=f"Google token exchange failed: {err}")

    token_data = resp.json()
    access_token = token_data.get("access_token", "")
    refresh_token = token_data.get("refresh_token", "")

    if not refresh_token:
        raise HTTPException(
            status_code=400,
            detail="Google did not return a refresh token. Try revoking app access at myaccount.google.com/permissions then retry."
        )

    # Fetch the user's email address from Google
    gmail_email = ""
    async with httpx.AsyncClient() as client:
        info_resp = await client.get(
            "https://www.googleapis.com/oauth2/v2/userinfo",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        if info_resp.status_code == 200:
            gmail_email = info_resp.json().get("email", "")

    # Store the refresh token in the database (encrypted)
    from database.models import GmailOAuthToken
    db = next(get_db())
    try:
        existing = db.query(GmailOAuthToken).filter(
            GmailOAuthToken.client_profile_id == profile_id
        ).first()

        enc_token = _encrypt_token(refresh_token)

        if existing:
            existing.refresh_token_enc = enc_token
            existing.email_address = gmail_email or existing.email_address
            existing.scopes = "gmail.readonly,gmail.send,userinfo.email"
            existing.updated_at = datetime.utcnow()
        else:
            existing = GmailOAuthToken(
                id=str(_uuid.uuid4()),
                client_profile_id=profile_id,
                email_address=gmail_email,
                refresh_token_enc=enc_token,
                scopes="gmail.readonly,gmail.send,userinfo.email",
            )
            db.add(existing)

        db.commit()
    finally:
        db.close()

    # Also set the env-var style key for backward compat with email_support_agent
    profile_db = next(get_db())
    try:
        from database.models import ClientProfile as _CP2
        _prof = profile_db.query(_CP2).filter(_CP2.id == profile_id).first()
        if _prof:
            os.environ[f"GMAIL_REFRESH_TOKEN_{_prof.client_id}"] = refresh_token
    finally:
        profile_db.close()

    # Redirect back to settings with success banner
    return RedirectResponse(url="/email?tab=connect&connected=1", status_code=303)


# ── Gmail Disconnect ─────────────────────────────────────────────────

@router.post("/email/disconnect", response_class=HTMLResponse)
async def gmail_disconnect(request: Request):
    """Revoke Gmail access and delete stored token."""
    import httpx

    user, profile, db = await _get_profile(request)
    if not user:
        db.close()
        return RedirectResponse("/account/login", status_code=303)

    from database.models import GmailOAuthToken
    tok = db.query(GmailOAuthToken).filter(
        GmailOAuthToken.client_profile_id == profile.id
    ).first()

    if tok:
        # Try to revoke the token at Google
        try:
            raw_token = _decrypt_token(tok.refresh_token_enc)
            async with httpx.AsyncClient() as client:
                await client.post(
                    "https://oauth2.googleapis.com/revoke",
                    params={"token": raw_token},
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                )
        except Exception as e:
            print(f"[Gmail] Revoke error (non-fatal): {e}")

        db.delete(tok)
        db.commit()

    # Clear env-var fallback
    env_key = f"GMAIL_REFRESH_TOKEN_{profile.client_id}"
    os.environ.pop(env_key, None)

    db.close()
    return RedirectResponse(url="/email?tab=connect&disconnected=1", status_code=303)


# ── Provider auto-detection ───────────────────────────────────────────

@router.get("/email/detect-provider")
async def email_detect_provider(email: str = Query(...)):
    """Return IMAP/SMTP config for the given email address domain.
    Priority: static lookup \u2192 MX-record inference \u2192 custom fallback."""
    domain = email.split("@")[-1].strip().lower() if "@" in email else ""

    # 1. Static lookup
    cfg = PROVIDER_IMAP_CONFIG.get(domain)
    if cfg:
        return JSONResponse({
            "provider":         cfg["provider"],
            "label":            cfg["label"],
            "imap_host":        cfg.get("imap_host", ""),
            "imap_port":        cfg.get("imap_port", 993),
            "smtp_host":        cfg.get("smtp_host", ""),
            "smtp_port":        cfg.get("smtp_port", 587),
            "app_password_url": cfg.get("app_password_url", ""),
            "instructions":     cfg.get("instructions", ""),
        })

    # 2. MX-record inference (catches custom domains on Google Workspace, M365, Yahoo, Zoho)
    if domain:
        mx_cfg = _mx_lookup(domain)
        if mx_cfg:
            return JSONResponse({
                "provider":         mx_cfg.get("provider", "custom"),
                "label":            mx_cfg.get("label", f"{domain}"),
                "imap_host":        mx_cfg.get("imap_host", ""),
                "imap_port":        mx_cfg.get("imap_port", 993),
                "smtp_host":        mx_cfg.get("smtp_host", ""),
                "smtp_port":        mx_cfg.get("smtp_port", 587),
                "app_password_url": mx_cfg.get("app_password_url", ""),
                "instructions":     mx_cfg.get("instructions", ""),
            })

    # 3. Unknown — show manual fields
    label = f"{domain} (IMAP)" if domain else "Custom (IMAP)"
    return JSONResponse({
        "provider":         "custom",
        "label":            label,
        "imap_host":        "",
        "imap_port":        993,
        "smtp_host":        "",
        "smtp_port":        587,
        "app_password_url": "",
        "instructions":     "Enter your IMAP and SMTP server details below. Check your email provider\u2019s help page for IMAP settings.",
    })


# ── IMAP Connect ──────────────────────────────────────────────────────

@router.post("/email/connect-imap", response_class=HTMLResponse)
async def email_connect_imap(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    provider: str = Form(...),
    imap_host: str = Form(...),
    imap_port: int = Form(993),
    smtp_host: str = Form(...),
    smtp_port: int = Form(587),
):
    """Validate IMAP credentials then store them encrypted in the DB."""
    import imaplib
    import uuid as _uuid

    user, profile, db = await _get_profile(request)
    if not user:
        db.close()
        return RedirectResponse("/account/login", status_code=303)

    # Block if user hasn't accepted the email AI agreement
    if not getattr(profile, "email_ai_agreed_at", None):
        db.close()
        return RedirectResponse("/email?tab=connect&error=agreement_required", status_code=303)

    if not imap_host.strip() or not smtp_host.strip():
        db.close()
        return RedirectResponse("/email?tab=connect&error=missing_hosts", status_code=303)

    # Test IMAP login before storing credentials
    try:
        _mail = imaplib.IMAP4_SSL(imap_host.strip(), imap_port)
        _mail.login(email.strip(), password)
        _mail.logout()
    except imaplib.IMAP4.error:
        db.close()
        return RedirectResponse("/email?tab=connect&error=imap_auth", status_code=303)
    except Exception:
        db.close()
        return RedirectResponse("/email?tab=connect&error=imap_connect", status_code=303)

    enc_password = _encrypt_token(password)

    from database.models import EmailIMAPConnection
    existing = db.query(EmailIMAPConnection).filter(
        EmailIMAPConnection.client_profile_id == profile.id
    ).first()
    if existing:
        existing.email_address = email.strip()
        existing.provider      = provider
        existing.imap_host     = imap_host.strip()
        existing.imap_port     = imap_port
        existing.smtp_host     = smtp_host.strip()
        existing.smtp_port     = smtp_port
        existing.password_enc  = enc_password
        existing.updated_at    = datetime.utcnow()
    else:
        existing = EmailIMAPConnection(
            id                = str(_uuid.uuid4()),
            client_profile_id = profile.id,
            email_address     = email.strip(),
            provider          = provider,
            imap_host         = imap_host.strip(),
            imap_port         = imap_port,
            smtp_host         = smtp_host.strip(),
            smtp_port         = smtp_port,
            password_enc      = enc_password,
        )
        db.add(existing)

    db.commit()
    db.close()
    return RedirectResponse("/email?tab=connect&connected=1", status_code=303)


# ── IMAP Disconnect ───────────────────────────────────────────────────

@router.post("/email/disconnect-imap", response_class=HTMLResponse)
async def email_disconnect_imap(request: Request):
    """Remove the stored IMAP connection for this client."""
    user, profile, db = await _get_profile(request)
    if not user:
        db.close()
        return RedirectResponse("/account/login", status_code=303)

    from database.models import EmailIMAPConnection
    tok = db.query(EmailIMAPConnection).filter(
        EmailIMAPConnection.client_profile_id == profile.id
    ).first()
    if tok:
        db.delete(tok)
        db.commit()

    db.close()
    return RedirectResponse("/email?tab=connect&disconnected=1", status_code=303)


# ══════════════════════════════════════════════════════════════════════
# CREATIVE STYLE — Reference Images + Generation Toggles
# ══════════════════════════════════════════════════════════════════════

MAX_REFERENCE_IMAGES = 10


def _load_creative_prefs(client_id: str) -> dict:
    _default = {"use_for_images": False, "use_for_videos": False, "reference_images": []}
    # 1. Try PostgreSQL first (survives Railway redeploys)
    try:
        from database.db import SessionLocal
        from database.models import ClientProfile
        _db = SessionLocal()
        try:
            _prof = _db.query(ClientProfile).filter(ClientProfile.client_id == client_id).first()
            if _prof and getattr(_prof, "creative_preferences_json", None):
                return json.loads(_prof.creative_preferences_json)
        finally:
            _db.close()
    except Exception:
        pass
    # 2. Fall back to filesystem cache
    path = os.path.join(TONE_PREFS_DIR, client_id, "creative_prefs.json")
    if os.path.exists(path):
        try:
            with open(path) as f:
                data = json.load(f)
            # Back-fill DB
            try:
                from database.db import SessionLocal
                from database.models import ClientProfile
                _db2 = SessionLocal()
                try:
                    _p = _db2.query(ClientProfile).filter(ClientProfile.client_id == client_id).first()
                    if _p:
                        _p.creative_preferences_json = json.dumps(data)
                        _db2.commit()
                finally:
                    _db2.close()
            except Exception:
                pass
            return data
        except Exception:
            pass
    return _default


def _save_creative_prefs(client_id: str, prefs: dict):
    # 1. Write to PostgreSQL (primary — survives Railway redeploys)
    try:
        from database.db import SessionLocal
        from database.models import ClientProfile
        _db = SessionLocal()
        try:
            _prof = _db.query(ClientProfile).filter(ClientProfile.client_id == client_id).first()
            if _prof:
                _prof.creative_preferences_json = json.dumps(prefs)
                _db.commit()
        finally:
            _db.close()
    except Exception:
        pass
    # 2. Also write to filesystem cache
    try:
        folder = os.path.join(TONE_PREFS_DIR, client_id)
        os.makedirs(folder, exist_ok=True)
        with open(os.path.join(folder, "creative_prefs.json"), "w") as f:
            json.dump(prefs, f, indent=2)
    except Exception:
        pass


async def _upload_to_imgbb(file_bytes: bytes) -> Optional[str]:
    """Upload raw image bytes to ImgBB and return its public URL."""
    import httpx
    api_key = (os.getenv("IMGBB_API_KEY") or "").strip()
    if not api_key:
        return None
    try:
        image_b64 = base64.b64encode(file_bytes).decode()
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                "https://api.imgbb.com/1/upload",
                data={"key": api_key, "image": image_b64},
            )
        if resp.status_code == 200:
            return resp.json()["data"]["url"]
    except Exception:
        pass
    return None


def _toggle_html(enabled: bool, name: str, icon: str, title: str, desc: str) -> str:
    border = "#5c6ac4" if enabled else "#eee"
    bg = "#f0f2ff" if enabled else "#fafafa"
    track_bg = "#5c6ac4" if enabled else "#ccc"
    knob_pos = "right:2px" if enabled else "left:2px"
    checked = "checked" if enabled else ""
    return f'''
<label style="display:flex;align-items:center;gap:14px;padding:16px;border-radius:10px;
              border:2px solid {border};cursor:pointer;background:{bg};transition:all .2s">
  <input type="checkbox" name="{name}" value="1" {checked}
         style="display:none" onchange="this.closest('form').submit()">
  <div style="width:44px;height:24px;border-radius:12px;background:{track_bg};
              position:relative;flex-shrink:0;transition:background .2s">
    <div style="position:absolute;top:2px;{knob_pos};width:20px;height:20px;
                border-radius:50%;background:#fff;transition:all .2s"></div>
  </div>
  <div>
    <div style="font-weight:700;color:#1a1a2e;font-size:.95rem">{icon} {title}</div>
    <div style="font-size:.83rem;color:#777;margin-top:3px">{desc}</div>
  </div>
</label>'''


@router.get("/creative", response_class=HTMLResponse)
async def creative_page(request: Request):
    user, profile, db = await _get_profile(request)
    db.close()
    if not user:
        return RedirectResponse("/account/login", status_code=303)

    prefs = _load_creative_prefs(profile.client_id)
    images: List[dict] = prefs.get("reference_images", [])
    use_img = prefs.get("use_for_images", False)
    use_vid = prefs.get("use_for_videos", False)
    msg = request.query_params.get("msg", "")
    err = request.query_params.get("err", "")

    # ── Build image grid ──────────────────────────────────────────────
    if images:
        img_html = '<div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(140px,1fr));gap:14px;margin-top:16px">'
        for idx, img in enumerate(images):
            safe_url = img["url"].replace('"', "")
            safe_name = img.get("name", f"Image {idx+1}")[:30]
            img_html += (
                f'<div style="position:relative;border-radius:10px;overflow:hidden;background:#f0f2f5;aspect-ratio:1">'
                f'  <img src="{safe_url}" alt="Ref {idx+1}" style="width:100%;height:100%;object-fit:cover">'
                f'  <form method="post" action="/settings/creative/delete" style="position:absolute;top:6px;right:6px">'
                f'    <input type="hidden" name="url" value="{safe_url}">'
                f'    <button type="submit" title="Remove" style="background:rgba(0,0,0,.55);border:none;color:#fff;'
                f'border-radius:50%;width:26px;height:26px;cursor:pointer;font-size:13px">&#10005;</button>'
                f'  </form>'
                f'  <div style="position:absolute;bottom:0;left:0;right:0;background:rgba(0,0,0,.5);'
                f'color:#fff;font-size:.7rem;padding:4px 6px;white-space:nowrap;overflow:hidden;'
                f'text-overflow:ellipsis">{safe_name}</div>'
                f'</div>'
            )
        img_html += '</div>'
    else:
        img_html = (
            '<div style="text-align:center;padding:40px;color:#aaa;border:2px dashed #dde;'
            'border-radius:10px;margin-top:16px">No reference images yet. Upload some below.</div>'
        )

    count_note = f'<span style="font-size:.82rem;color:#888">{len(images)}/{MAX_REFERENCE_IMAGES} uploaded</span>'
    at_limit = len(images) >= MAX_REFERENCE_IMAGES
    upload_disabled = 'disabled' if at_limit else ''
    upload_note = '(Limit reached — delete an image to upload more)' if at_limit else 'PNG, JPG, WEBP &middot; Max 5 MB each &middot; Up to 10 images'

    msg_html = f'<div class="notice" style="background:#e8f5e9;border-color:#66bb6a;color:#2e7d32">{msg}</div>' if msg else ""
    err_html = f'<div class="notice" style="background:#fff3e0;border-color:#ff9800;color:#e65100">{err}</div>' if err else ""

    toggle_img = _toggle_html(
        use_img, "use_for_images", "&#128247;",
        "Use for Image Generation",
        "Reference images guide the visual style of AI-generated images (flyers, social posts, product shots)."
    )
    toggle_vid = _toggle_html(
        use_vid, "use_for_videos", "&#127916;",
        "Use for Video Generation",
        "Reference images influence the AI frames in Tier 2 (Generated Images) and Tier 3 (AI Animation) videos. Stock video (Tier 1) is unaffected."
    )

    body = f"""
{msg_html}{err_html}
<div class="card">
  <h2>&#127912; Reference Images</h2>
  <p class="sub">Upload brand photos, style inspiration, product images, or mood boards. {count_note}</p>
  {img_html}
  <form method="post" action="/settings/creative/upload" enctype="multipart/form-data"
        style="margin-top:20px;display:flex;align-items:center;gap:12px;flex-wrap:wrap">
    <label style="margin:0;display:flex;align-items:center;gap:10px;background:#f0f2f5;
                  border:1.5px dashed #bbb;border-radius:8px;padding:10px 16px;
                  cursor:pointer;flex:1;min-width:200px">
      <span style="font-size:1.3rem">&#128190;</span>
      <span style="font-size:.88rem;color:#555">Choose images to upload
        &nbsp;<span style="color:#999;font-size:.78rem">{upload_note}</span>
      </span>
      <input type="file" name="files" accept="image/*" multiple style="display:none" {upload_disabled}>
    </label>
    <button type="submit" class="btn btn-primary" {upload_disabled}>Upload</button>
  </form>
</div>

<div class="card">
  <h2>&#9881;&#65039; Generation Preferences</h2>
  <p class="sub">Choose which generation types should use your reference images as visual style guides.</p>
  <form method="post" action="/settings/creative/prefs">
    <div style="display:flex;flex-direction:column;gap:16px;margin-top:8px">
      {toggle_img}
      {toggle_vid}
    </div>
    <button type="submit" class="btn btn-primary" style="margin-top:20px">Save Preferences</button>
  </form>
</div>

<div class="card" style="background:#f8f9ff;border:1px solid #e0e4ff">
  <h2 style="color:#5c6ac4">&#128161; How Reference Images Work</h2>
  <ul style="font-size:.87rem;color:#555;line-height:1.9;padding-left:18px;margin-top:10px">
    <li><strong>Image Generation</strong>: Reference images are passed as style context.
        Midjourney uses them as <code>--sref</code> style references. DALL-E &amp; Flux incorporate
        them as visual inspiration descriptors in the prompt.</li>
    <li><strong>Video Generation</strong>: Influences AI frames in Tier 2 &amp; Tier 3 videos.
        Stock video (Tier 1) is unaffected since it uses real footage.</li>
    <li><strong>Best images to upload</strong>: Brand color palettes, product photos,
        mood/aesthetic shots, logo variations, style inspiration images.</li>
    <li><strong>Avoid</strong>: Screenshots, text-heavy images, very low-quality photos —
        these confuse the AI style extraction.</li>
  </ul>
</div>
"""

    from utils.shared_layout import build_page
    return HTMLResponse(build_page(
        title="Creative Style",
        active_nav="creative",
        body_content=body,
        extra_css=_SETTINGS_CSS,
        user_name=user.full_name,
        business_name=profile.business_name,
    ))


@router.post("/creative/upload", response_class=HTMLResponse)
async def creative_upload(request: Request, files: List[UploadFile] = File(...)):
    user, profile, db = await _get_profile(request)
    db.close()
    if not user:
        return RedirectResponse("/account/login", status_code=303)

    prefs = _load_creative_prefs(profile.client_id)
    images: List[dict] = prefs.get("reference_images", [])

    uploaded = 0
    errors = []
    for f in files:
        if len(images) >= MAX_REFERENCE_IMAGES:
            errors.append("Upload limit reached")
            break
        try:
            size = getattr(f, "size", None)
            if size and size > 5 * 1024 * 1024:
                errors.append(f"{f.filename} too large (max 5 MB)")
                continue
            if not (f.content_type or "").startswith("image/"):
                errors.append(f"{f.filename} is not an image")
                continue
            file_bytes = await f.read()
            url = await _upload_to_imgbb(file_bytes)
            if url:
                images.append({
                    "url": url,
                    "name": f.filename or f"image_{uploaded+1}",
                    "uploaded_at": datetime.utcnow().isoformat(),
                })
                uploaded += 1
            else:
                errors.append(f"{f.filename} failed (check IMGBB_API_KEY)")
        except Exception as ex:
            errors.append(str(ex)[:60])

    prefs["reference_images"] = images
    _save_creative_prefs(profile.client_id, prefs)

    if errors:
        err_str = ", ".join(errors[:2]).replace(" ", "+")
        return RedirectResponse(f"/settings/creative?err={err_str}", status_code=303)
    return RedirectResponse(f"/settings/creative?msg={uploaded}+image(s)+uploaded+successfully", status_code=303)


@router.post("/creative/delete", response_class=HTMLResponse)
async def creative_delete(request: Request, url: str = Form(...)):
    user, profile, db = await _get_profile(request)
    db.close()
    if not user:
        return RedirectResponse("/account/login", status_code=303)

    prefs = _load_creative_prefs(profile.client_id)
    before = len(prefs.get("reference_images", []))
    prefs["reference_images"] = [i for i in prefs.get("reference_images", []) if i["url"] != url]
    _save_creative_prefs(profile.client_id, prefs)
    return RedirectResponse("/settings/creative?msg=Image+removed", status_code=303)


@router.post("/creative/prefs", response_class=HTMLResponse)
async def creative_save_prefs(request: Request):
    user, profile, db = await _get_profile(request)
    db.close()
    if not user:
        return RedirectResponse("/account/login", status_code=303)

    form = await request.form()
    prefs = _load_creative_prefs(profile.client_id)
    prefs["use_for_images"] = form.get("use_for_images") == "1"
    prefs["use_for_videos"] = form.get("use_for_videos") == "1"
    _save_creative_prefs(profile.client_id, prefs)
    return RedirectResponse("/settings/creative?msg=Preferences+saved", status_code=303)


# ══════════════════════════════════════════════════════════════════════
# SECURITY (Two-Factor Authentication)
# ══════════════════════════════════════════════════════════════════════

@router.get("/security", response_class=HTMLResponse)
async def security_page(request: Request):
    user, profile, db = await _get_profile(request)
    if not user:
        db.close()
        return RedirectResponse("/account/login", status_code=303)

    msg = request.query_params.get("msg", "")
    success_banner = (
        f'<div style="background:#e8f5e9;border-left:4px solid #27ae60;padding:12px 16px;'
        f'border-radius:0 8px 8px 0;margin-bottom:20px;font-size:.88rem;color:#2e7d32">{msg}</div>'
    ) if msg else ""

    mfa_enabled = bool(getattr(user, "mfa_enabled", False))
    mfa_method  = getattr(user, "mfa_method", None) or ""

    # ── Trusted Devices ───────────────────────────────────────────────
    trusted_devices = db.query(TrustedDevice).filter(
        TrustedDevice.user_id   == user.id,
        TrustedDevice.expires_at > datetime.utcnow(),
    ).order_by(TrustedDevice.last_used_at.desc().nullslast()).all()

    # ── Registered Passkeys ───────────────────────────────────────────
    passkeys = db.query(WebAuthnCredential).filter(WebAuthnCredential.user_id == user.id).all()
    db.close()

    # ── 2FA status block ──────────────────────────────────────────────
    method_labels = {
        "totp":    "Authenticator App (TOTP)",
        "email":   "Email OTP",
        "sms":     "SMS OTP",
        "passkey": "Fingerprint / Passkey (WebAuthn)",
    }
    if mfa_enabled:
        method_label = method_labels.get(mfa_method, mfa_method)
        status_badge = f'<span class="pill pill-green">&#10003; Enabled &mdash; {method_label}</span>'
        current_block = f"""
        <div style="background:#f0faf0;border:1px solid #c8e6c9;border-radius:10px;padding:16px 20px;
                    margin-bottom:20px;display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:12px">
          <div>
            <p style="font-size:.9rem;font-weight:700;color:#2e7d32;margin-bottom:4px">&#128274; 2FA is active</p>
            <p style="font-size:.84rem;color:#555">Method: <strong>{method_label}</strong></p>
          </div>
          <form method="post" action="/account/2fa/disable"
                onsubmit="return confirm('Disable two-factor authentication? Your account will be less secure.')">
            <button class="btn btn-danger" type="submit">Disable 2FA</button>
          </form>
        </div>"""
        method_cards = ""
    else:
        status_badge = '<span class="pill pill-yellow">&#9888; Not enabled</span>'
        current_block = ('<div style="background:#fff8e1;border-left:4px solid #f9a825;padding:12px 16px;'
                         'border-radius:0 8px 8px 0;font-size:.87rem;color:#795548;margin-bottom:20px">'
                         '&#9888;&nbsp; Two-factor authentication is <strong>not enabled</strong>. '
                         'We strongly recommend turning it on to protect your account.</div>')
        method_cards = """
        <div class="card">
          <h2>Choose a 2FA Method</h2>
          <div class="sub">Pick the method that works best for you. You can change it any time.</div>
          <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:14px;margin-top:8px">

            <div style="border:2px solid #e4e6eb;border-radius:12px;padding:20px;background:#fafafa;transition:border-color .15s"
                 onmouseover="this.style.borderColor='#5c6ac4'" onmouseout="this.style.borderColor='#e4e6eb'">
              <div style="font-size:1.5rem;margin-bottom:8px">&#128274;</div>
              <h3 style="font-size:.93rem;font-weight:700;color:#1a1a2e;margin-bottom:4px">Fingerprint / Passkey</h3>
              <p style="font-size:.8rem;color:#666;line-height:1.5;margin-bottom:14px">Use Touch ID, Face ID, Windows Hello, or any fingerprint reader. No code needed &mdash; just biometrics.</p>
              <a href="/account/2fa/setup?method=passkey" class="btn btn-primary" style="font-size:.82rem;padding:8px 16px">Set Up</a>
            </div>

            <div style="border:2px solid #e4e6eb;border-radius:12px;padding:20px;background:#fafafa;transition:border-color .15s"
                 onmouseover="this.style.borderColor='#5c6ac4'" onmouseout="this.style.borderColor='#e4e6eb'">
              <div style="font-size:1.5rem;margin-bottom:8px">&#128241;</div>
              <h3 style="font-size:.93rem;font-weight:700;color:#1a1a2e;margin-bottom:4px">Authenticator App</h3>
              <p style="font-size:.8rem;color:#666;line-height:1.5;margin-bottom:14px">Works with Google Authenticator, Microsoft Authenticator, Authy, and any TOTP app. Best security, works offline.</p>
              <a href="/account/2fa/setup?method=totp" class="btn btn-primary" style="font-size:.82rem;padding:8px 16px">Set Up</a>
            </div>

            <div style="border:2px solid #e4e6eb;border-radius:12px;padding:20px;background:#fafafa;transition:border-color .15s"
                 onmouseover="this.style.borderColor='#5c6ac4'" onmouseout="this.style.borderColor='#e4e6eb'">
              <div style="font-size:1.5rem;margin-bottom:8px">&#128140;</div>
              <h3 style="font-size:.93rem;font-weight:700;color:#1a1a2e;margin-bottom:4px">Email Code</h3>
              <p style="font-size:.8rem;color:#666;line-height:1.5;margin-bottom:14px">We'll email you a one-time code each time you sign in. Easy to set up, no extra app needed.</p>
              <a href="/account/2fa/setup?method=email" class="btn btn-primary" style="font-size:.82rem;padding:8px 16px">Set Up</a>
            </div>

            <div style="border:2px solid #e4e6eb;border-radius:12px;padding:20px;background:#fafafa;transition:border-color .15s"
                 onmouseover="this.style.borderColor='#5c6ac4'" onmouseout="this.style.borderColor='#e4e6eb'">
              <div style="font-size:1.5rem;margin-bottom:8px">&#128244;</div>
              <h3 style="font-size:.93rem;font-weight:700;color:#1a1a2e;margin-bottom:4px">SMS / Text Message</h3>
              <p style="font-size:.8rem;color:#666;line-height:1.5;margin-bottom:14px">We'll text you a one-time code to your phone. Convenient, but requires mobile signal.</p>
              <a href="/account/2fa/setup?method=sms" class="btn btn-primary" style="font-size:.82rem;padding:8px 16px">Set Up</a>
            </div>

          </div>
        </div>"""

    # ── Also allow adding passkey when 2FA is on (but not passkey) ────
    add_passkey_card = ""
    if mfa_enabled and mfa_method != "passkey" and not passkeys:
        add_passkey_card = """
        <div class="card">
          <h2>&#128274; Also add Fingerprint / Passkey</h2>
          <div class="sub">You can register your fingerprint or device biometric as an additional sign-in method alongside your current 2FA, but it must be set as your primary 2FA method to use during login. Switch to passkey if preferred.</div>
          <a href="/account/2fa/setup?method=passkey" class="btn btn-primary" style="margin-top:16px">Register Fingerprint</a>
        </div>"""

    # ── Trusted Devices section ───────────────────────────────────────
    if trusted_devices:
        device_rows = ""
        for d in trusted_devices:
            last_used = d.last_used_at.strftime("%b %d, %Y") if d.last_used_at else "Never"
            expires   = d.expires_at.strftime("%b %d, %Y")
            label     = d.device_name or "Unknown Device"
            device_rows += f"""
            <tr>
              <td style="padding:10px 12px;font-size:.85rem">{label[:60]}</td>
              <td style="padding:10px 12px;font-size:.82rem;color:#666">{last_used}</td>
              <td style="padding:10px 12px;font-size:.82rem;color:#999">{expires}</td>
              <td style="padding:10px 12px;text-align:right">
                <form method="post" action="/account/2fa/trusted-devices/{d.id}/revoke" style="display:inline">
                  <button type="submit" class="btn btn-danger" style="padding:4px 10px;font-size:.78rem"
                          onclick="return confirm('Remove this trusted device?')">Remove</button>
                </form>
              </td>
            </tr>"""
        trusted_section = f"""
        <div class="card">
          <div style="display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:10px;margin-bottom:12px">
            <div>
              <h2>&#128187; Trusted Devices</h2>
              <div class="sub">These devices skip 2FA for {30} days. Remove any you don't recognize.</div>
            </div>
            <form method="post" action="/account/2fa/trusted-devices/revoke-all"
                  onsubmit="return confirm('Remove ALL trusted devices?')">
              <button type="submit" class="btn btn-danger" style="font-size:.82rem;padding:7px 14px">Remove All</button>
            </form>
          </div>
          <table style="width:100%;border-collapse:collapse">
            <thead><tr style="border-bottom:1px solid #e4e6eb">
              <th style="padding:8px 12px;text-align:left;font-size:.8rem;color:#888;font-weight:600">Device</th>
              <th style="padding:8px 12px;text-align:left;font-size:.8rem;color:#888;font-weight:600">Last Used</th>
              <th style="padding:8px 12px;text-align:left;font-size:.8rem;color:#888;font-weight:600">Expires</th>
              <th></th>
            </tr></thead>
            <tbody>{device_rows}</tbody>
          </table>
        </div>"""
    else:
        trusted_section = ""

    _body = f"""
  {success_banner}
  <div class="card">
    <h2>&#128274; Two-Factor Authentication &nbsp;{status_badge}</h2>
    <div class="sub">
      Add an extra layer of security to your account. When enabled, you'll need to verify your
      identity with a second method each time you sign in.
    </div>
    {current_block}
  </div>
  {method_cards}
  {add_passkey_card}
  {trusted_section}
"""
    from utils.shared_layout import build_page
    return HTMLResponse(build_page(
        title="Security",
        active_nav="security",
        body_content=_body,
        extra_css=_SETTINGS_CSS,
        user_name=user.full_name,
        business_name=profile.business_name if profile else "",
    ))


# ══════════════════════════════════════════════════════════════════════
# GROWTH INTERESTS  (/settings/growth-interests)
# ══════════════════════════════════════════════════════════════════════

def _load_growth_interests(profile) -> list:
    """Return list of interest strings from profile JSON, or []."""
    import json as _json
    raw = getattr(profile, "growth_interests_json", None) if profile else None
    if not raw:
        return []
    try:
        data = _json.loads(raw)
        return data.get("interests", [])
    except (ValueError, TypeError):
        return []


def _save_growth_interests(client_id: str, interests: list) -> bool:
    """Persist growth interests list to the client profile."""
    import json as _json
    try:
        db = next(get_db())
        try:
            row = db.query(ClientProfile).filter(ClientProfile.client_id == client_id).first()
            if not row:
                return False
            row.growth_interests_json = _json.dumps({"interests": interests})
            db.commit()
            return True
        finally:
            db.close()
    except Exception:
        return False


@router.get("/growth-interests", response_class=HTMLResponse)
async def growth_interests_page(request: Request):
    user, profile, db = await _get_profile(request)
    db.close()
    if not user:
        return RedirectResponse("/account/login", status_code=303)

    interests = _load_growth_interests(profile)
    niche = (profile.niche or profile.business_name or "your niche") if profile else "your niche"

    # Build pills for existing interests
    pills_html = ""
    for i, interest in enumerate(interests):
        safe = interest.replace("&", "&amp;").replace("<", "&lt;").replace('"', "&quot;")
        pills_html += (
            f'<span class="adj-pill" data-idx="{i}">'
            f'<span class="adj-pill-text">{safe}</span>'
            f'<button class="adj-pill-del" onclick="removeInterest({i})" title="Remove">&times;</button>'
            f'</span>'
        )

    body = f"""
<p style="color:#90949c;font-size:.88rem;margin-bottom:8px">
  Tell Alita what kind of people and groups you want in your daily growth recommendations.
</p>
<div class="notice" style="margin-bottom:20px">
  If no interests are set, recommendations default to your niche: <strong>{niche}</strong>
</div>

<div id="gi-save-status" style="display:none;margin-bottom:14px;font-size:.82rem;color:#2e7d32;
     background:#e8f5e9;padding:10px 14px;border-radius:8px"></div>

<label class="s-label">Your Growth Interests</label>
<p style="font-size:.82rem;color:#90949c;margin-bottom:10px">
  Add topics describing the kind of people you want to connect with.
  Examples: <em>"social media saas"</em>, <em>"people looking to outsource social media management"</em>,
  <em>"small business owners"</em>
</p>

<div id="gi-pills" class="adj-pills-row" style="min-height:48px;border:1.5px solid #e4e6eb;border-radius:10px;padding:10px 14px;background:#fafafa;margin-bottom:14px">
  {pills_html if pills_html else '<span id="gi-empty" style="color:#bbb;font-size:.85rem">No interests set &mdash; using niche fallback</span>'}
</div>

<div style="display:flex;gap:10px;align-items:center;margin-bottom:20px">
  <input type="text" id="gi-input" class="s-input" placeholder="e.g. people looking for social media help"
         style="flex:1" onkeydown="if(event.key==='Enter'){{event.preventDefault();addInterest()}}">
  <button class="btn-primary" onclick="addInterest()" style="white-space:nowrap;padding:10px 20px">+ Add</button>
</div>

<div style="display:flex;gap:12px;align-items:center;margin-top:8px">
  <button class="btn-primary" onclick="saveInterests()" id="gi-save-btn" style="padding:10px 24px">Save Interests</button>
  <a href="/settings" class="btn-secondary">Back to Settings</a>
</div>
"""

    js = r"""
let interests = """ + repr(interests) + r""";

function renderPills() {
  const c = document.getElementById('gi-pills');
  if (!interests.length) {
    c.innerHTML = '<span id="gi-empty" style="color:#bbb;font-size:.85rem">No interests set &mdash; using niche fallback</span>';
    return;
  }
  c.innerHTML = interests.map((t, i) =>
    '<span class="adj-pill"><span class="adj-pill-text">' + t.replace(/</g, '&lt;') +
    '</span><button class="adj-pill-del" onclick="removeInterest(' + i + ')" title="Remove">&times;</button></span>'
  ).join('');
}

function addInterest() {
  const inp = document.getElementById('gi-input');
  const val = (inp.value || '').trim();
  if (!val) return;
  if (interests.length >= 10) { alert('Maximum 10 interests'); return; }
  if (interests.some(x => x.toLowerCase() === val.toLowerCase())) { inp.value = ''; return; }
  interests.push(val);
  inp.value = '';
  renderPills();
}

function removeInterest(idx) {
  interests.splice(idx, 1);
  renderPills();
}

async function saveInterests() {
  const btn = document.getElementById('gi-save-btn');
  const status = document.getElementById('gi-save-status');
  btn.disabled = true;
  btn.textContent = 'Saving\u2026';
  try {
    const res = await fetch('/settings/growth-interests', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ interests })
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok || !data.ok) throw new Error(data.error || 'Save failed');
    status.style.display = 'block';
    status.textContent = '\u2705 Interests saved! Your next growth report will use these topics.';
    setTimeout(() => { status.style.display = 'none'; }, 4000);
  } catch (e) {
    status.style.display = 'block';
    status.style.background = '#fff0f0';
    status.style.color = '#c0392b';
    status.textContent = 'Could not save: ' + e.message;
  } finally {
    btn.disabled = false;
    btn.textContent = 'Save Interests';
  }
}
"""

    from utils.shared_layout import build_page
    return HTMLResponse(build_page(
        title="Growth Interests",
        active_nav="settings",
        body_content=body,
        extra_css=_SETTINGS_CSS,
        extra_js=js,
        user_name=user.full_name,
        business_name=profile.business_name if profile else "",
        topbar_title="Growth Interests",
    ))


@router.post("/growth-interests")
async def growth_interests_save(request: Request):
    user, profile, db = await _get_profile(request)
    db.close()
    if not user or not profile:
        return JSONResponse({"ok": False, "error": "Not authenticated"}, status_code=401)

    try:
        payload = await request.json()
    except Exception:
        return JSONResponse({"ok": False, "error": "Invalid JSON"}, status_code=400)

    raw_interests = payload.get("interests", [])
    if not isinstance(raw_interests, list):
        return JSONResponse({"ok": False, "error": "interests must be a list"}, status_code=400)

    # Sanitize: strip, deduplicate, cap at 10, max 200 chars each
    seen = set()
    clean = []
    for item in raw_interests:
        text = str(item).strip()[:200]
        if text and text.lower() not in seen:
            seen.add(text.lower())
            clean.append(text)
        if len(clean) >= 10:
            break

    if not _save_growth_interests(profile.client_id, clean):
        return JSONResponse({"ok": False, "error": "Save failed"}, status_code=500)

    return JSONResponse({"ok": True, "interests": clean})
