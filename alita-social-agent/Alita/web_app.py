# web_app.py
from fastapi import FastAPI, Form, Response, Request
from fastapi.responses import HTMLResponse, JSONResponse
import os
import sys
sys.path.append('agents')
from agents.engagement_agent import EngagementAgent
from agents.faceless_style_loader import FacelessStyleLoader, get_category_display_name
from agents.content_agent import ContentCreationAgent
import uvicorn
import json
import asyncio

app = FastAPI(title="Alita AI Marketing Platform")
agent = EngagementAgent()
style_loader = FacelessStyleLoader()

# ─── Initialize database tables BEFORE any route imports ─────────────────────
# Route modules may query the DB at import time (RAG rebuild, voice matching, etc.)
# so all tables MUST exist before they load.
try:
    from database.db import init_db as _early_init_db
    _early_init_db()
    print("✅ Database tables pre-initialized (before route imports)")
except Exception as _db_err:
    print(f"⚠️  Early DB init failed: {_db_err}")

# ─── Encryption key check ───────────────────────────────────────────────────
if not os.getenv("TOKEN_ENCRYPTION_KEY"):
    print("⚠️  TOKEN_ENCRYPTION_KEY is NOT set — email/OAuth tokens will be stored UNENCRYPTED. "
          "Set this env var to a Fernet key (python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\")")
if not os.getenv("MICROSOFT_CLIENT_ID"):
    print("ℹ️  MICROSOFT_CLIENT_ID not set — 'Sign in with Microsoft' will be hidden on the Email page.")
if not os.getenv("GMAIL_CLIENT_ID"):
    print("ℹ️  GMAIL_CLIENT_ID not set — 'Sign in with Google' will be hidden on the Email page.")


# ─── Global error handler — show friendly page instead of raw 500 ───
@app.exception_handler(500)
async def _server_error_handler(request: Request, exc: Exception):
    import traceback
    tb = traceback.format_exception(type(exc), exc, exc.__traceback__)
    print(f"[500] {request.method} {request.url}\n{''.join(tb)}")
    return HTMLResponse(
        status_code=500,
        content=(
            '<!DOCTYPE html><html><head><meta charset="UTF-8"><title>Something went wrong</title>'
            '<style>body{font-family:system-ui;background:#0f0c29;color:white;display:flex;'
            'align-items:center;justify-content:center;min-height:100vh;margin:0}'
            '.card{background:rgba(255,255,255,.06);border-radius:16px;padding:48px;'
            'max-width:480px;text-align:center}'
            'h1{font-size:2rem;margin-bottom:12px}p{color:rgba(255,255,255,.6);line-height:1.6}'
            'a{color:#a78bfa;font-weight:600}</style></head><body><div class="card">'
            '<h1>Something went wrong</h1>'
            '<p>We hit an unexpected error. Please try again or '
            '<a href="/account/login">go back to login</a>.</p>'
            '</div></body></html>'
        ),
    )


# ─── Sliding token refresh middleware ──────────────────────────────────────────
# When get_current_user() detects the JWT has < 30 min remaining, it stashes a
# fresh token in request.state._refresh_token.  This middleware copies that into
# the response as a renewed cookie so active users never get logged out.
@app.middleware("http")
async def _sliding_token_middleware(request: Request, call_next):
    response = await call_next(request)
    refresh = getattr(request.state, "_refresh_token", None)
    if refresh:
        is_prod = os.getenv("ENV", "development") == "production"
        response.set_cookie(
            key="alita_token",
            value=refresh,
            httponly=True,
            max_age=60 * 60,       # 1 hour
            samesite="lax",
            secure=is_prod,
        )
    return response


@app.get("/favicon.ico")
async def favicon():
    """Return a minimal 1x1 transparent PNG so browsers stop 404-ing."""
    # 1x1 transparent PNG (68 bytes)
    import base64
    _ICO = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAAC0lEQVQI12NgAAIABQAB"
        "Nl7BcQAAAABJRU5ErkJggg=="
    )
    return Response(content=_ICO, media_type="image/png",
                    headers={"Cache-Control": "public, max-age=604800"})


@app.get("/")
async def home(request: Request):
    """Root â€” redirect to dashboard if logged in, otherwise to login."""
    from fastapi.responses import RedirectResponse
    from database.db import get_db
    from api.auth_routes import get_current_user

    db = next(get_db())
    try:
        user = get_current_user(request, db)
        if user:
            return RedirectResponse("/dashboard", status_code=302)
        return RedirectResponse("/account/login", status_code=302)
    except Exception:
        return RedirectResponse("/account/login", status_code=302)
    finally:
        db.close()


@app.get("/.well-known/appspecific/com.chrome.devtools.json")
async def chrome_devtools_appspecific_json():
    """Silence Chrome's optional appspecific request (non-essential)."""
    return JSONResponse(content={}, status_code=200)


def _empty_sourcemap_response() -> Response:
    # Minimal valid sourcemap structure (prevents DevTools 404 noise)
    return Response(
        content=json.dumps({"version": 3, "sources": [], "names": [], "mappings": ""}),
        media_type="application/json",
        status_code=200,
    )


@app.get("/styles.css.map")
async def styles_css_map():
    return _empty_sourcemap_response()


@app.get("/create-post/styles.css.map")
async def create_post_styles_css_map():
    return _empty_sourcemap_response()

# â”€â”€â”€ Mount OAuth Routes â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
try:
    from api.oauth_routes import router as oauth_router
    app.include_router(oauth_router)
    print("âœ&hellip; OAuth routes mounted: /auth/login, /auth/callback, /auth/dashboard")
except Exception as e:
    print(f"âš ï¸  OAuth routes not loaded: {e}")
    print("   Set META_APP_ID and META_APP_SECRET in .env to enable OAuth")

# â”€â”€â”€ Mount Comment Management Routes â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
try:
    from api.comment_routes import router as comment_router
    app.include_router(comment_router)
    print("âœ&hellip; Comment management routes mounted: /comments/dashboard")
except Exception as e:
    print(f"âš ï¸  Comment routes not loaded: {e}")

# â”€â”€â”€ Mount WhatsApp & Threads Routes â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
try:
    from api.messaging_routes import router as messaging_router
    app.include_router(messaging_router)
    print("âœ&hellip; WhatsApp & Threads routes mounted: /messaging/dashboard")
except Exception as e:
    print(f"âš ï¸  Messaging routes not loaded: {e}")
    print("   Set up WhatsApp Business and Threads to enable messaging features")

# â”€â”€â”€ Mount Unified Social Media Routes â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
try:
    from api.social_media_routes import router as social_router
    app.include_router(social_router)
    print("âœ&hellip; Social media routes mounted: /social/dashboard, /twitter/*, /tiktok/*, /youtube/*")
except Exception as e:
    print(f"âš ï¸  Social media routes not loaded: {e}")
    print("   Configure Late API key and YouTube API key for full functionality")

# â”€â”€â”€ Mount Growth Intelligence Routes â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
try:
    from api.growth_routes import router as growth_router
    app.include_router(growth_router)
    print("âœ&hellip; Growth routes mounted: /growth/dashboard, /api/growth/*")
except Exception as e:
    print(f"âš ï¸  Growth routes not loaded: {e}")

# â”€â”€â”€ Mount Client Connection Routes â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
try:
    from api.client_connections_routes import router as connections_router
    app.include_router(connections_router)
    print("âœ&hellip; Client connection routes mounted: /connect/dashboard")
except Exception as e:
    print(f"âš ï¸  Client connection routes not loaded: {e}")

# â”€â”€â”€ Mount Late API Webhooks â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
try:
    from api.late_webhooks import router as webhook_router
    app.include_router(webhook_router)
    print("âœ&hellip; Webhook routes mounted: /webhooks/late-api/*")
except Exception as e:
    print(f"âš ï¸  Webhook routes not loaded: {e}")

# â”€â”€â”€ Mount Threads Routes â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
try:
    from api.threads_routes import router as threads_router
    app.include_router(threads_router)
    print("âœ&hellip; Threads routes mounted: /threads/dashboard")
except Exception as e:
    print(f"âš ï¸  Threads routes not loaded: {e}")

# â”€â”€â”€ Mount Analytics Routes â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
try:
    from api.analytics_routes import router as analytics_router
    app.include_router(analytics_router)
    print("âœ&hellip; Analytics routes mounted: /analytics/dashboard")
except Exception as e:
    print(f"âš ï¸  Analytics routes not loaded: {e}")

# â”€â”€â”€ Mount Email Routes â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
try:
    from api.email_routes import router as email_router
    app.include_router(email_router)
    print("âœ&hellip; Email routes mounted: /email/dashboard, /api/email/*")
except Exception as e:
    print(f"âš ï¸  Email routes not loaded: {e}")

# â”€â”€â”€ Mount Marketing Intelligence Routes â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
try:
    from api.intelligence_routes import router as intelligence_router
    app.include_router(intelligence_router)
    print("âœ&hellip; Intelligence routes mounted: /intelligence/dashboard, /api/intelligence/*")
except Exception as e:
    print(f"âš ï¸  Intelligence routes not loaded: {e}")

try:
    import api.inbox_routes as inbox_routes_module
    from api.inbox_routes import router as inbox_router
    app.include_router(inbox_router)
    print("âœ&hellip; Inbox routes mounted: /inbox/dashboard")
    print(f"   Inbox routes file: {getattr(inbox_routes_module, '__file__', 'unknown')}")
except Exception as e:
    print(f"âš ï¸  Inbox routes not loaded: {e}")

# â”€â”€â”€ Mount Meta Webhook Receiver (DMs/Comments Auto-Reply) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
try:
    from webhook_receiver import router as meta_webhook_router
    app.include_router(meta_webhook_router)
    print("âœ&hellip; Meta webhook routes mounted: /webhook")
except Exception as e:
    print(f"âš ï¸  Meta webhook routes not loaded: {e}")

# â”€â”€â”€ Mount Post Creation Routes â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
try:
    from api.post_creation_routes import router as post_creation_router
    app.include_router(post_creation_router)
    print("âœ&hellip; Post creation routes mounted: /create-post/dashboard")
except Exception as e:
    print(f"âš ï¸  Post creation routes not loaded: {e}")

# ─── Initialize Client Database (redundant safety — already done above) ───
try:
    from database.db import init_db
    init_db()  # idempotent — safe to re-call
except Exception as e:
    print(f"⚠️  Database init failed: {e}")

# â”€â”€â”€ Mount Client Auth Routes (/account/signup, /account/login) â”€â”€â”€â”€â”€â”€â”€
try:
    from api.auth_routes import router as client_auth_router
    app.include_router(client_auth_router)
    print("âœ&hellip; Client auth routes mounted: /account/signup, /account/login, /account/logout")
except Exception as e:
    print(f"âš ï¸  Client auth routes not loaded: {e}")

# â”€â”€â”€ Mount Client Onboarding Routes â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
try:
    from api.onboarding_routes import router as onboarding_router
    app.include_router(onboarding_router)
    print("âœ&hellip; Onboarding routes mounted: /onboarding")
except Exception as e:
    print(f"âš ï¸  Onboarding routes not loaded: {e}")

# â”€â”€â”€ Mount Admin Review Panel â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
try:
    from api.admin_routes import router as admin_router
    app.include_router(admin_router)
    print("âœ&hellip; Admin routes mounted: /admin")
except Exception as e:
    print(f"âš ï¸  Admin routes not loaded: {e}")

# â”€â”€â”€ Mount Client Settings Routes (/settings/tone, /settings/knowledge) â”€â”€
try:
    from api.settings_routes import router as settings_router
    app.include_router(settings_router)
    print("âœ&hellip; Settings routes mounted: /settings (hub), /settings/tone, /settings/auto-reply, /settings/knowledge, /settings/security, /settings/creative, /settings/email")
except Exception as e:
    print(f"âš ï¸  Settings routes not loaded: {e}")


# â”€â”€â”€ Mount Notification Routes â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
try:
    from api.notification_routes import router as notification_router
    app.include_router(notification_router)
    print("âœ&hellip; Notification routes mounted: /notifications, /api/notifications")
except Exception as e:
    print(f"âš ï¸  Notification routes not loaded: {e}")

# â”€â”€â”€ Mount Calendar Routes â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
try:
    from api.calendar_routes import router as calendar_router
    app.include_router(calendar_router)
    print("âœ&hellip; Calendar routes mounted: /calendar, /api/calendar/*")
except Exception as e:
    print(f"âš ï¸  Calendar routes not loaded: {e}")

# â”€â”€â”€ Mount Alita Assistant Routes â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
try:
    from api.alita_assistant_routes import router as alita_router
    app.include_router(alita_router)
    print("âœ&hellip; Alita Assistant routes mounted: /alita/chat, /api/alita/chat")
except Exception as e:
    print(f"âš ï¸  Alita Assistant routes not loaded: {e}")

# â”€â”€â”€ Mount Billing / Payments Routes â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
try:
    from api.billing_routes import router as billing_router, migrate_billing_columns
    app.include_router(billing_router)
    # Run a safe one-time migration to add billing columns to existing DBs
    from database.db import engine
    migrate_billing_columns(engine)
    print("âœ&hellip; Billing routes mounted: /pricing, /billing, /api/billing/*")
except Exception as e:
    print(f"âš ï¸  Billing routes not loaded: {e}")

# â”€â”€â”€ MFA column migration â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
try:
    from api.auth_routes import migrate_mfa_columns
    from database.db import engine as _engine
    migrate_mfa_columns(_engine)
except Exception as e:
    print(f"âš ï¸  MFA migration warning: {e}")

# â”€â”€â”€ Client Dashboard (post-onboarding) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
@app.get("/dashboard", response_class=HTMLResponse)
async def client_dashboard(request: Request):
    """Main client dashboard shown after onboarding completes."""
    from database.db import get_db
    from database.models import ClientProfile, OnboardingStatus
    from api.auth_routes import get_current_user
    import os, json, traceback

    db = next(get_db())
    try:
        current_user = get_current_user(request, db)
        if not current_user:
            from fastapi.responses import RedirectResponse
            return RedirectResponse("/account/login", status_code=303)

        profile = db.query(ClientProfile).filter(
            ClientProfile.user_id == current_user.id
        ).first()

        if not profile:
            from fastapi.responses import RedirectResponse
            return RedirectResponse("/onboarding", status_code=303)

        # Wizard still in progress? Send back.
        _step = getattr(profile, "onboarding_step", None)
        if _step is not None and 1 <= _step <= 6:
            from fastapi.responses import RedirectResponse
            return RedirectResponse("/onboarding", status_code=303)

        if profile.onboarding_status != OnboardingStatus.complete:
            from fastapi.responses import RedirectResponse
            return RedirectResponse("/onboarding/status", status_code=303)

        # â”€â”€ setup checks â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        # 1. Knowledge base (RAG ready from onboarding)
        kb_ready = profile.rag_ready

        # 2. Social accounts connected — query DB + env vars (survives redeploys)
        social_count = 0
        try:
            from api.client_connections_routes import load_connections, _has_meta_token_for_client
            all_conns = load_connections()                          # merges JSON + DB + env vars
            social_count = len(all_conns.get(profile.client_id, {}))
        except Exception:
            from api.client_connections_routes import _has_meta_token_for_client
        # Also count Meta (Instagram + Facebook) if OAuth token exists in PG
        if _has_meta_token_for_client(profile.client_id):
            social_count += 2  # Instagram + Facebook

        # 3. Tone setup — DB flag survives redeploys; DB column then file check as fallback
        tone_ready = bool(getattr(profile, "tone_configured", False))
        if not tone_ready:
            # Check DB column
            if getattr(profile, "tone_preferences_json", None):
                tone_ready = True
            else:
                tone_path = os.path.join("style_references", profile.client_id, "tone_prefs.json")
                tone_ready = os.path.exists(tone_path)

        # 4. Email connected (client-specific)
        email_ready = bool(os.getenv(f"GMAIL_REFRESH_TOKEN_{profile.client_id}"))

        setup_done = sum([kb_ready, social_count > 0, tone_ready, email_ready])
        setup_total = 4
        pct = int(setup_done / setup_total * 100)

        # Count scheduled posts for today (from DB)
        scheduled_today = 0
        upcoming_posts_html = ""
        try:
            from database.models import ScheduledPost as _SP
            from datetime import datetime as _dtx
            import pytz as _pytz
            _client_tz = _pytz.timezone(os.getenv("DEFAULT_TIMEZONE", "America/New_York"))
            _now_local = _dtx.now(_pytz.utc).astimezone(_client_tz)
            _today_str = _now_local.strftime("%Y-%m-%d")
            scheduled_today = db.query(_SP).filter(
                _SP.client_id == profile.client_id,
                _SP.scheduled_time.like(f"{_today_str}%"),
                _SP.status.in_(["planned", "scheduled", "approved"]),
            ).count()

            # Fetch next 5 upcoming posts for the dashboard card
            _all_upcoming = db.query(_SP).filter(
                _SP.client_id == profile.client_id,
                _SP.status.in_(["planned", "scheduled", "approved"]),
            ).all()
            # Parse and sort by scheduled_time, keep only future posts
            _parsed = []
            for _up in _all_upcoming:
                try:
                    _st = _dtx.fromisoformat((_up.scheduled_time or "").strip())
                    if _st.tzinfo is None:
                        _st = _client_tz.localize(_st)
                    else:
                        _st = _st.astimezone(_client_tz)
                    if _st >= _now_local:
                        _parsed.append((_st, _up))
                except (ValueError, TypeError):
                    continue
            _parsed.sort(key=lambda x: x[0])
            _next5 = _parsed[:5]

            if _next5:
                _plat_colors = {
                    "twitter": ("#1DA1F2", "Twitter/X"),
                    "instagram": ("#E1306C", "Instagram"),
                    "linkedin": ("#0A66C2", "LinkedIn"),
                    "tiktok": ("#000000", "TikTok"),
                    "youtube": ("#FF0000", "YouTube"),
                    "facebook": ("#1877F2", "Facebook"),
                    "threads": ("#000000", "Threads"),
                }
                _rows = []
                for _st, _up in _next5:
                    _pkey = (_up.platform or "unknown").lower()
                    _bg, _pname = _plat_colors.get(_pkey, ("#606770", _up.platform or "Unknown"))
                    _time_str = _st.strftime("%b %d, %I:%M %p").replace(" 0", " ")
                    _ctype = (_up.content_type or "post").capitalize()
                    _topic_snip = ""
                    if _up.topic:
                        _topic_snip = f"<br><small style='color:#90949c'>{(_up.topic or '')[:60]}</small>"
                    _rows.append(
                        f"<div style='display:flex;align-items:center;gap:12px;padding:10px 0;"
                        f"border-bottom:1px solid #f0f2f5'>"
                        f"<span style='background:{_bg};color:#fff;font-size:.7rem;font-weight:700;"
                        f"border-radius:6px;padding:3px 8px;white-space:nowrap'>{_pname}</span>"
                        f"<div style='flex:1;min-width:0'>"
                        f"<span style='font-size:.84rem;font-weight:600'>{_ctype}</span>"
                        f"{_topic_snip}</div>"
                        f"<span style='font-size:.78rem;color:#606770;white-space:nowrap'>{_time_str}</span>"
                        f"</div>"
                    )
                upcoming_posts_html = "".join(_rows)
                _remaining = len(_parsed) - 5
                if _remaining > 0:
                    upcoming_posts_html += (
                        f"<div style='text-align:center;padding:8px 0;font-size:.78rem'>"
                        f"<a href='/calendar/dashboard' style='color:#5c6ac4;font-weight:600'>"
                        f"View all {len(_parsed)} upcoming posts &rarr;</a></div>"
                    )
        except Exception:
            pass

        first_name = current_user.full_name.split()[0]
        first_initial = first_name[0].upper()
        from datetime import datetime as _dt
        try:
            import pytz as _pytz2
            _tz = _pytz2.timezone(os.getenv("DEFAULT_TIMEZONE", "America/New_York"))
            today_str = _dt.now(_tz).strftime("%A, %B %d").replace(" 0", " ")
        except Exception:
            today_str = _dt.now().strftime("%A, %B %d").replace(" 0", " ")

        # â”€â”€ checklist items as structured data â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        checks = [
            (kb_ready,          "Knowledge base",        "/settings/knowledge", "Set up"),
            (social_count > 0,  f"Social accounts ({social_count})", "/connect/dashboard", "Connect"),
            (tone_ready,        "Tone &amp; style",      "/settings/tone",      "Configure"),
            (email_ready,       "Email inbox",           "/settings/email",     "Connect"),
        ]
        checklist_html = ""
        for done, label, url, cta in checks:
            if done:
                checklist_html += (
                    "<li class='cl-item cl-done'>"
                    "<span class='cl-icon'>&#10003;</span>"
                    f"<span class='cl-label'>{label}</span>"
                    "<span class='cl-status'>Done</span>"
                    "</li>"
                )
            else:
                checklist_html += (
                    "<li class='cl-item'>"
                    "<span class='cl-icon'>&#9675;</span>"
                    f"<span class='cl-label'>{label}</span>"
                    f"<a class='cl-btn' href='{url}'>{cta}</a>"
                    "</li>"
                )

        setup_banner = ""
        if setup_done < setup_total:
            setup_banner = (
                "<div class='setup-banner'>"
                "<div class='sb-text'>"
                "<strong>Finish your setup</strong>"
                f"<small>{setup_done} of {setup_total} steps done &mdash; {pct}% complete</small>"
                "</div>"
                f"<div class='sb-bar'><div class='sb-fill' style='width:{pct}%'></div></div>"
                "</div>"
            )

        # ── email verification banner (show until user verifies) ──
        email_verified = getattr(current_user, "email_verified", True)  # default True = no banner for old accounts
        verify_banner = ""
        if not email_verified:
            verify_banner = (
                "<div style='background:rgba(99,102,241,.18);border:1px solid rgba(99,102,241,.45);"
                "border-radius:12px;padding:12px 18px;display:flex;align-items:center;"
                "justify-content:space-between;gap:12px;margin-bottom:16px;flex-wrap:wrap'>"
                "<span style='color:#e0e7ff;font-size:.9rem'>\u26a0\ufe0f "
                "Your email address hasn't been verified yet. Check your inbox or "
                "<a href='/account/resend-verification' "
                "style='color:#a78bfa;font-weight:700'>resend the verification email</a>."
                "</span>"
                "</div>"
            )

        # â”€â”€ activity feed items (pre-computed to avoid emoji in nested strings) â”€â”€
        feed_kb = (
            "<div class='feed-item'>"
            "<div class='feed-dot post'>&#128218;</div>"
            "<div class='feed-content'>"
            "<p>Knowledge base is <strong>ready</strong></p>"
            "<small>AI is trained on your business info</small>"
            "</div></div>"
        ) if kb_ready else ""

        plat_word = "platforms" if social_count != 1 else "platform"
        feed_social = (
            "<div class='feed-item'>"
            "<div class='feed-dot dm'>&#128241;</div>"
            "<div class='feed-content'>"
            f"<p><strong>{social_count} social {plat_word}</strong> connected</p>"
            "<small>Posts &amp; replies are going through</small>"
            "</div></div>"
        ) if social_count > 0 else ""

        feed_tone = (
            "<div class='feed-item'>"
            "<div class='feed-dot system'>&#127897;</div>"
            "<div class='feed-content'>"
            "<p>Tone &amp; style not configured yet</p>"
            "<small><a href='/settings/tone' style='color:#5c6ac4'>Set up your brand voice &rarr;</a></small>"
            "</div></div>"
        ) if not tone_ready else ""

        niche_chip = (
            f"<div class='plat-chip connected'><span>&#127919;</span> {profile.niche}</div>"
            if profile.niche else ""
        )
        location_chip = (
            f"<div class='plat-chip connected'><span>&#128205;</span> {profile.location}</div>"
            if profile.location else ""
        )
        ai_chip_class = "connected" if kb_ready else ""
        ai_chip_label = "AI Ready" if kb_ready else "AI Training..."
        stat_delta_class = "up" if social_count > 0 else "neutral"
        stat_delta_text = "Active" if social_count > 0 else "Connect now"

        # Build the upcoming posts section (dynamic or empty state)
        if upcoming_posts_html:
            upcoming_section = upcoming_posts_html
        else:
            upcoming_section = (
                "<div class='empty-state'>"
                "<div class='em-icon'>&#128197;</div>"
                "<p>No posts scheduled yet.</p>"
                "<a href='/create-post/dashboard' style='color:#5c6ac4;"
                "font-weight:600;font-size:.85rem'>Create your first post &rarr;</a>"
                "</div>"
            )

        from utils.shared_layout import build_page

        _dash_css = """
        .welcome-bar{display:flex;align-items:center;justify-content:space-between;margin-bottom:22px}
        .welcome-bar h1{font-size:1.35rem;font-weight:800;color:#1c1e21}
        .welcome-bar p{font-size:.85rem;color:#606770;margin-top:2px}
        .new-post-btn{background:linear-gradient(135deg,#5c6ac4,#764ba2);color:#fff;border-radius:8px;padding:10px 20px;font-size:.88rem;font-weight:700;display:flex;align-items:center;gap:8px;transition:opacity .15s}
        .new-post-btn:hover{opacity:.88}
        .setup-banner{background:#fff;border-radius:12px;padding:16px 20px;margin-bottom:20px;border-left:4px solid #5c6ac4;box-shadow:0 1px 4px rgba(0,0,0,.06)}
        .sb-text strong{font-size:.92rem;font-weight:700}
        .sb-text small{display:block;font-size:.78rem;color:#606770;margin-top:2px}
        .sb-bar{background:#e4e6eb;border-radius:99px;height:6px;margin-top:10px}
        .sb-fill{background:linear-gradient(90deg,#5c6ac4,#764ba2);height:6px;border-radius:99px;transition:width .4s}
        .stats-row{display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin-bottom:22px}
        @media(max-width:900px){.stats-row{grid-template-columns:repeat(2,1fr)}}
        .stat-card{background:#fff;border-radius:12px;padding:18px 20px;box-shadow:0 1px 4px rgba(0,0,0,.06);display:flex;align-items:center;gap:14px}
        .stat-icon{width:44px;height:44px;border-radius:12px;display:flex;align-items:center;justify-content:center;font-size:1.25rem;flex-shrink:0}
        .stat-icon.purple{background:#ede8f5}
        .stat-icon.blue{background:#e8f0fe}
        .stat-icon.green{background:#e8f5e9}
        .stat-icon.orange{background:#fff3e0}
        .stat-num{font-size:1.5rem;font-weight:800;line-height:1}
        .stat-label{font-size:.78rem;color:#606770;margin-top:3px}
        .stat-delta{font-size:.75rem;margin-top:2px}
        .stat-delta.up{color:#2e7d32}
        .stat-delta.neutral{color:#90949c}
        .two-col{display:grid;grid-template-columns:1fr 340px;gap:18px}
        @media(max-width:900px){.two-col{grid-template-columns:1fr}}
        .card{background:#fff;border-radius:12px;box-shadow:0 1px 4px rgba(0,0,0,.06);overflow:hidden;margin-bottom:18px}
        .card-header{display:flex;align-items:center;justify-content:space-between;padding:16px 20px 0}
        .card-title{font-size:.92rem;font-weight:700;display:flex;align-items:center;gap:8px}
        .card-action{font-size:.8rem;color:#5c6ac4;font-weight:600}
        .card-action:hover{text-decoration:underline}
        .card-body{padding:14px 20px 18px}
        .feed-item{display:flex;align-items:flex-start;gap:12px;padding:10px 0;border-bottom:1px solid #f0f2f5}
        .feed-item:last-child{border-bottom:none}
        .feed-dot{width:34px;height:34px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:.95rem;flex-shrink:0;margin-top:1px}
        .feed-dot.comment{background:#e8f0fe}
        .feed-dot.dm{background:#e8f5e9}
        .feed-dot.post{background:#ede8f5}
        .feed-dot.system{background:#fff3e0}
        .feed-content p{font-size:.85rem;color:#1c1e21;line-height:1.4}
        .feed-content small{font-size:.76rem;color:#90949c}
        .cl-list{list-style:none;padding:0}
        .cl-item{display:flex;align-items:center;gap:10px;padding:9px 0;border-bottom:1px solid #f0f2f5;font-size:.85rem}
        .cl-item:last-child{border-bottom:none}
        .cl-icon{width:22px;height:22px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:.7rem;font-weight:800;flex-shrink:0;background:#e4e6eb;color:#606770}
        .cl-item.cl-done .cl-icon{background:#e8f5e9;color:#2e7d32}
        .cl-label{flex:1;color:#1c1e21}
        .cl-status{font-size:.75rem;color:#2e7d32;font-weight:600}
        .cl-btn{font-size:.75rem;background:#5c6ac4;color:#fff;border-radius:6px;padding:4px 10px;font-weight:600;transition:opacity .12s}
        .cl-btn:hover{opacity:.85}
        .quick-actions{display:flex;flex-direction:column;gap:8px;padding:4px 0}
        .qa-btn{display:flex;align-items:center;gap:10px;padding:10px 14px;border-radius:10px;font-size:.85rem;font-weight:600;color:#1c1e21;background:#f8f9fb;border:1px solid #e4e6eb;transition:background .12s}
        .qa-btn:hover{background:#ede8f5;border-color:#c5b8e8;color:#5c6ac4}
        .qa-icon{font-size:1rem;width:24px;text-align:center}
        .platform-grid{display:flex;flex-wrap:wrap;gap:8px;padding:4px 0}
        .plat-chip{display:flex;align-items:center;gap:6px;background:#f8f9fb;border:1px solid #e4e6eb;border-radius:8px;padding:7px 12px;font-size:.82rem;font-weight:500}
        .plat-chip.connected{border-color:#c5b8e8;background:#ede8f5;color:#5c6ac4}
        .empty-state{text-align:center;padding:32px 20px;font-size:.85rem;color:#90949c}
        .empty-state .em-icon{font-size:2rem;margin-bottom:10px}
        """

        _body = f"""
        <div class="welcome-bar">
          <div>
            <h1>Welcome back, {first_name}! &#128075;</h1>
            <p>Here&rsquo;s what&rsquo;s happening with your business today.</p>
          </div>
          <a class="new-post-btn" href="/create-post/dashboard">&#10022;&nbsp; New Post</a>
        </div>
        {verify_banner}
        {setup_banner}
        <div class="stats-row">
          <div class="stat-card">
            <div class="stat-icon purple">&#128197;</div>
            <div><div class="stat-num">{scheduled_today}</div><div class="stat-label">Scheduled Today</div><div class="stat-delta neutral">View calendar</div></div>
          </div>
          <div class="stat-card">
            <div class="stat-icon blue">&#128232;</div>
            <div><div class="stat-num">3</div><div class="stat-label">New Messages</div><div class="stat-delta up">&#8593; Active</div></div>
          </div>
          <div class="stat-card">
            <div class="stat-icon green">&#128172;</div>
            <div><div class="stat-num">&mdash;</div><div class="stat-label">Comments Handled</div><div class="stat-delta neutral">Auto-reply on</div></div>
          </div>
          <div class="stat-card">
            <div class="stat-icon orange">&#128241;</div>
            <div><div class="stat-num">{social_count}</div><div class="stat-label">Platforms</div><div class="stat-delta {stat_delta_class}">{stat_delta_text}</div></div>
          </div>
        </div>
        <div class="two-col">
          <div>
            <div class="card">
              <div class="card-header">
                <span class="card-title">&#128197; Upcoming Posts</span>
                <a class="card-action" href="/create-post/dashboard">+ Create</a>
              </div>
              <div class="card-body">
                {upcoming_section}
              </div>
            </div>
            <div class="card">
              <div class="card-header">
                <span class="card-title">&#9889; Recent Activity</span>
                <a class="card-action" href="/inbox/dashboard">See all</a>
              </div>
              <div class="card-body">
                <div class="feed-item">
                  <div class="feed-dot system">&#129302;</div>
                  <div class="feed-content"><p>AI auto-reply is <strong>active</strong></p><small>Responding to comments &amp; DMs automatically</small></div>
                </div>
                {feed_kb}{feed_social}{feed_tone}
              </div>
            </div>
          </div>
          <div>
            <div class="card">
              <div class="card-header">
                <span class="card-title">&#128640; Setup Checklist</span>
                <span style="font-size:.8rem;color:#90949c;font-weight:600">{setup_done}/{setup_total}</span>
              </div>
              <div class="card-body"><ul class="cl-list">{checklist_html}</ul></div>
            </div>
            <div class="card">
              <div class="card-header"><span class="card-title">&#9889; Quick Actions</span></div>
              <div class="card-body">
                <div class="quick-actions">
                  <a class="qa-btn" href="/create-post/dashboard"><span class="qa-icon">&#9997;</span> Write a post</a>
                  <a class="qa-btn" href="/inbox/dashboard"><span class="qa-icon">&#128232;</span> Check inbox</a>
                  <a class="qa-btn" href="/comments/dashboard"><span class="qa-icon">&#128172;</span> View comments</a>
                  <a class="qa-btn" href="/analytics/dashboard"><span class="qa-icon">&#128202;</span> See analytics</a>
                  <a class="qa-btn" href="/connect/dashboard"><span class="qa-icon">&#128241;</span> Manage accounts</a>
                </div>
              </div>
            </div>
            <div class="card">
              <div class="card-header"><span class="card-title">&#127970; Business</span></div>
              <div class="card-body">
                <div class="platform-grid">
                  <div class="plat-chip connected"><span>&#127970;</span> {profile.business_name}</div>
                  {niche_chip}{location_chip}
                  <div class="plat-chip {ai_chip_class}"><span>&#129302;</span> {ai_chip_label}</div>
                </div>
              </div>
            </div>
          </div>
        </div>

        """

        _dash_js = ""

        return HTMLResponse(build_page(
            title="Dashboard",
            active_nav="dashboard",
            body_content=_body,
            extra_css=_dash_css,
            extra_js=_dash_js,
            user_name=current_user.full_name,
            business_name=profile.business_name,
        ))

    except Exception as _dash_err:
        tb = traceback.format_exc()
        return HTMLResponse(
            f"<pre style='color:red;padding:20px;font-size:13px'>"
            f"Dashboard error (debug):\n{tb}\n\n{_dash_err}</pre>",
            status_code=500,
        )
    finally:
        db.close()


async def add_knowledge(knowledge: str = Form(...), client_id: str = Form(...)):
    agent.rag.add_knowledge(text=knowledge, client_id=client_id)
    return HTMLResponse(f"<h2>âœ&hellip; Knowledge Added!</h2><p>{knowledge}</p><a href='/'>â† Back</a>")

@app.post("/ask")
async def ask_question(question: str = Form(...), client_id: str = Form(...)):
    response = agent.respond_to_message(message=question, client_id=client_id)
    return HTMLResponse(f"""
        <h2>â“ Question:</h2><p>{question}</p>
        <h2>ðŸ¤– Answer:</h2><p>{response}</p>
        <a href='/'>â† Back</a>
    """)

@app.get("/api/usage-stats")
async def api_usage_stats(request: Request):
    """Return current usage + limits for images and videos (JSON)."""
    from api.auth_routes import get_current_user
    from database.db import get_db
    from database.models import ClientProfile
    from utils.plan_limits import get_effective_limit, _parse_active_addons, PLAN_DISPLAY_NAMES

    db = next(get_db())
    try:
        user = get_current_user(request, db)
        if not user:
            return JSONResponse({"error": "Not authenticated"}, status_code=401)
        profile = db.query(ClientProfile).filter(ClientProfile.user_id == user.id).first()
        if not profile:
            return JSONResponse({"error": "No profile"}, status_code=404)

        tier = getattr(profile, "plan_tier", "free")
        addons = _parse_active_addons(profile)

        images_used  = getattr(profile, "usage_images_created", 0) or 0
        videos_used  = getattr(profile, "usage_videos_created", 0) or 0
        images_limit = get_effective_limit(tier, "images_created", addons)
        videos_limit = get_effective_limit(tier, "videos_created", addons)

        return JSONResponse({
            "tier": tier,
            "tier_name": PLAN_DISPLAY_NAMES.get(tier, tier.title()),
            "images_used":  images_used,
            "images_limit": images_limit,   # -1 = unlimited
            "videos_used":  videos_used,
            "videos_limit": videos_limit,   # -1 = unlimited
        })
    finally:
        db.close()


@app.get("/faceless-video", response_class=HTMLResponse)
async def faceless_video_page(request: Request):
    """Faceless Video Style Selection Interface — with shared layout + usage tracking"""
    from utils.shared_layout import build_page, get_user_context
    from database.db import get_db

    db = next(get_db())
    try:
        user_obj, profile = get_user_context(request, db)
    except Exception:
        user_obj, profile = None, None
    finally:
        db.close()

    if not user_obj:
        from fastapi.responses import RedirectResponse
        return RedirectResponse("/account/login", status_code=303)

    _uname = user_obj.full_name if user_obj else "User"
    _bname = profile.business_name if profile else "My Business"

    # ── Load creative style reference images from profile ──
    _vid_ref_imgs = []
    _vid_use_for_videos = False
    if profile:
        try:
            import json as _json_vp
            _raw_vp = getattr(profile, "creative_preferences_json", None)
            if _raw_vp:
                _vp = _json_vp.loads(_raw_vp)
                _vid_use_for_videos = bool(_vp.get("use_for_videos", False))
                _vid_ref_imgs = _vp.get("reference_images", []) or []
        except Exception:
            pass

    _vid_ref_thumbs_html = ""
    _vid_ref_urls_json = "[]"
    if _vid_ref_imgs:
        import json as _json_vp2
        _vid_urls = []
        for _vri in _vid_ref_imgs[:10]:
            _vrurl = _vri.get("url", "") if isinstance(_vri, dict) else str(_vri)
            _vrname = _vri.get("name", "") if isinstance(_vri, dict) else ""
            if _vrurl:
                _vid_urls.append(_vrurl)
                _vid_ref_thumbs_html += (
                    f'<div style="position:relative;width:64px;height:64px;border-radius:8px;overflow:hidden;border:2px solid #e4e6eb;flex-shrink:0" title="{_vrname}">'
                    f'<img src="{_vrurl}" style="width:100%;height:100%;object-fit:cover" loading="lazy" alt="{_vrname}">'
                    f'<div class="vid-ref-check" style="display:none;position:absolute;top:2px;right:2px;background:#5c6ac4;color:#fff;border-radius:50%;width:16px;height:16px;font-size:10px;line-height:16px;text-align:center">&#10003;</div>'
                    f'</div>'
                )
        _vid_ref_urls_json = _json_vp2.dumps(_vid_urls)
    _vid_ref_checked = "checked" if _vid_use_for_videos else ""
    _vid_ref_section_display = "" if _vid_ref_imgs else "display:none;"

    categories = style_loader.list_categories()

    # Build category options with style counts
    category_options = ""
    for cat in categories:
        display_name = get_category_display_name(cat)
        styles = style_loader.list_styles_by_category(cat)
        count = len(styles)
        category_options += f'<option value="{cat}">{display_name} ({count} styles)</option>\n'

    body = f"""
<div style="max-width:860px;margin:0 auto">
  <div style="margin-bottom:20px">
    <h1 style="font-size:1.3rem;font-weight:800">&#127916; Faceless Video Creator</h1>
    <p style="font-size:.83rem;color:#606770;margin-top:3px">Generate production specs for faceless videos. Our AI creates optimized content ideas and matches them to your selected style.</p>
  </div>

  <!-- Usage Status Bar -->
  <div id="usage-bar" class="card" style="margin-bottom:18px">
    <div class="card-body" style="padding:14px 18px">
      <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:8px">
        <span style="font-size:.85rem;font-weight:700;color:#1a1a2e">Videos This Month</span>
        <span id="usage-label" style="font-size:.82rem;color:#606770">Loading&hellip;</span>
      </div>
      <div style="background:#e4e6eb;border-radius:99px;height:10px;overflow:hidden">
        <div id="usage-fill" style="height:100%;border-radius:99px;width:0%;transition:width .6s ease;background:linear-gradient(90deg,#5c6ac4,#7c3aed)"></div>
      </div>
      <div id="usage-note" style="font-size:.76rem;color:#90949c;margin-top:6px"></div>
    </div>
  </div>

  <!-- Blocked Banner (hidden by default) -->
  <div id="limit-blocked" style="display:none;background:#fce4ec;border:1px solid #e57373;border-radius:10px;padding:16px;color:#c62828;font-size:.88rem;margin-bottom:20px">
    <strong>&#128683; Video limit reached.</strong> <span id="limit-msg"></span>
    <a href="/billing" style="color:#5c6ac4;font-weight:700;margin-left:6px">Upgrade Plan &rarr;</a>
  </div>

  <form id="video-form" action="/create-video-specs" method="post" onsubmit="return onVideoSubmit()">
    <!-- Step 1: Content Strategy -->
    <div class="card" style="margin-bottom:18px">
      <div class="card-header"><div class="card-title">Step 1: Content Strategy</div></div>
      <div class="card-body">
        <label class="form-label">Content Goal</label>
        <select name="content_goal" id="content_goal" class="form-input" required>
          <option value="engagement">&#128202; Engagement &mdash; Maximize views, likes, comments</option>
          <option value="growth">&#128200; Growth &mdash; Build followers and audience</option>
          <option value="sales">&#128176; Sales &mdash; Drive conversions and revenue</option>
        </select>
      </div>
    </div>

    <!-- Step 2: Business Information -->
    <div class="card" style="margin-bottom:18px">
      <div class="card-header"><div class="card-title">Step 2: Business Information</div></div>
      <div class="card-body">
        <label class="form-label">Business Name *</label>
        <input type="text" name="business_name" class="form-input" placeholder="e.g., AI Automation Solutions" required>
        <label class="form-label" style="margin-top:12px">Industry / Niche *</label>
        <input type="text" name="industry" class="form-input" placeholder="e.g., B2B SaaS, E-commerce, Real Estate" required>
        <label class="form-label" style="margin-top:12px">Target Audience *</label>
        <input type="text" name="target_audience" class="form-input" placeholder="e.g., Small business owners, Entrepreneurs" required>
        <label class="form-label" style="margin-top:12px">Content Topic <span style="font-weight:400;color:#90949c">(optional &mdash; AI will generate if blank)</span></label>
        <textarea name="content_topic" class="form-input" rows="2" placeholder="Leave blank to let AI generate topic based on your goal"></textarea>
      </div>
    </div>

    <!-- Step 3: Select Video Style -->
    <div class="card" style="margin-bottom:18px">
      <div class="card-header"><div class="card-title">Step 3: Video Style</div></div>
      <div class="card-body">
        <label class="form-label">Style Category *</label>
        <select name="category" id="category" class="form-input" onchange="loadStyles()" required>
          <option value="">-- Select a Category --</option>
          {category_options}
        </select>
        <label class="form-label" style="margin-top:12px">Specific Style *</label>
        <select name="style" id="style" class="form-input" onchange="previewStyle()" required>
          <option value="">-- First select a category --</option>
        </select>
        <div id="stylePreview" style="background:#f8f9fb;padding:14px;border-radius:8px;margin-top:10px;display:none;font-size:.85rem"></div>
      </div>
    </div>

    <!-- Step 4: Quality & Platform -->
    <div class="card" style="margin-bottom:18px">
      <div class="card-header"><div class="card-title">Step 4: Quality &amp; Platform</div></div>
      <div class="card-body">
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px">
          <div>
            <label class="form-label">Video Quality</label>
            <select name="video_quality" class="form-input" required>
              <option value="tier1">Tier 1 &mdash; Stock Footage (Free)</option>
              <option value="tier2" selected>Tier 2 &mdash; Flux Pro Images</option>
              <option value="tier3">Tier 3 &mdash; AI Animation (Premium)</option>
            </select>
          </div>
          <div>
            <label class="form-label">Target Platform</label>
            <select name="platform" class="form-input" required>
              <option value="youtube_shorts">YouTube Shorts</option>
              <option value="tiktok">TikTok</option>
              <option value="instagram_reels">Instagram Reels</option>
              <option value="youtube">YouTube (Long-form)</option>
              <option value="facebook">Facebook</option>
            </select>
          </div>
        </div>
        <label class="form-label" style="margin-top:12px">Video Duration</label>
        <select name="duration_pref" class="form-input">
          <option value="short">Short (15&ndash;30s)</option>
          <option value="medium">Medium (30&ndash;60s)</option>
          <option value="long">Long (60s+)</option>
        </select>
      </div>
    </div>

    <!-- Creative Style Reference Images (from Settings) -->
    <div id="vid-creative-ref-section" class="card" style="margin-bottom:18px;{_vid_ref_section_display}">
      <div class="card-header" style="display:flex;align-items:center;justify-content:space-between">
        <div class="card-title">&#127912; Your Creative Style References</div>
        <label style="display:flex;align-items:center;gap:6px;font-size:.82rem;font-weight:600;cursor:pointer;margin:0">
          <input type="checkbox" id="vid-use-creative-refs" {_vid_ref_checked} onchange="toggleVidCreativeRefs()">
          Use these
        </label>
      </div>
      <div class="card-body" style="padding:12px 18px">
        <p style="font-size:.8rem;color:#606770;margin-bottom:10px">
          These reference images are from your <a href="/settings/creative" style="color:#5c6ac4;font-weight:600">Creative Style settings</a>.
          Enable the toggle to apply their visual style to generated video frames.
        </p>
        <div style="display:flex;gap:8px;flex-wrap:wrap">
          {_vid_ref_thumbs_html}
        </div>
        <p id="vid-creative-ref-status" style="font-size:.76rem;color:#16a34a;margin-top:8px;display:none">
          &#10003; Creative style references will be applied to video visuals.
        </p>
        <input type="hidden" name="creative_ref_urls" id="vid-creative-ref-input" value="">
      </div>
    </div>

    <!-- Generate button -->
    <div style="display:flex;gap:12px;justify-content:flex-end;margin-bottom:24px">
      <button type="submit" id="video-gen-btn" class="btn-primary" style="padding:12px 32px;font-size:.95rem">
        &#127916; Generate Production Specs
      </button>
    </div>
  </form>

  <!-- Loading overlay -->
  <div id="video-loading" style="display:none">
    <div class="card" style="text-align:center;padding:48px 24px">
      <div class="gen-spinner"></div>
      <h3 id="video-loading-title" style="margin:20px 0 8px;color:#5c6ac4">Generating production specs&hellip;</h3>
      <p style="color:#6b7280;font-size:.88rem;margin:0">Our AI is creating optimized content and matching your selected style.<br>This usually takes 30&ndash;60 seconds.</p>
      <div style="margin-top:20px;display:flex;gap:6px;justify-content:center">
        <span class="gen-dot" style="animation-delay:0s"></span>
        <span class="gen-dot" style="animation-delay:.2s"></span>
        <span class="gen-dot" style="animation-delay:.4s"></span>
      </div>
    </div>
  </div>

  <div id="video-error" style="display:none;background:#fce4ec;border:1px solid #e57373;border-radius:10px;padding:16px;color:#c62828;font-size:.88rem;margin-bottom:20px"></div>
</div>
"""

    extra_css = """
  .gen-spinner{width:48px;height:48px;border:4px solid #e4e6eb;border-top-color:#5c6ac4;border-radius:50%;margin:0 auto;animation:gen-spin .8s linear infinite}
  @keyframes gen-spin{to{transform:rotate(360deg)}}
  .gen-dot{width:8px;height:8px;background:#5c6ac4;border-radius:50%;animation:gen-pulse 1.2s ease-in-out infinite}
  @keyframes gen-pulse{0%,80%,100%{opacity:.3;transform:scale(.8)}40%{opacity:1;transform:scale(1.1)}}
"""

    extra_js = r"""
let _videoLimitOk = true;

// ── Load usage stats on page load ──
async function loadVideoUsage() {
  try {
    const r = await fetch('/api/usage-stats');
    if (!r.ok) return;
    const d = await r.json();
    const used  = d.videos_used  || 0;
    const limit = d.videos_limit;
    const label = document.getElementById('usage-label');
    const fill  = document.getElementById('usage-fill');
    const note  = document.getElementById('usage-note');
    const blocked = document.getElementById('limit-blocked');

    if (limit === 0) {
      label.textContent = 'Not available on ' + (d.tier_name || 'Free') + ' plan';
      fill.style.width = '100%';
      fill.style.background = '#e57373';
      note.textContent = 'Upgrade your plan to unlock Faceless Video creation.';
      blocked.style.display = '';
      document.getElementById('limit-msg').textContent = 'Your ' + (d.tier_name || 'Free') + ' plan does not include faceless videos.';
      document.getElementById('video-gen-btn').disabled = true;
      document.getElementById('video-gen-btn').style.opacity = '0.5';
      _videoLimitOk = false;
    } else if (limit === -1) {
      label.textContent = used + ' used (unlimited)';
      fill.style.width = '0%';
      note.textContent = 'Your ' + (d.tier_name || 'Pro') + ' plan has unlimited video generation.';
    } else {
      const pct = Math.min(100, Math.round((used / limit) * 100));
      label.textContent = used + ' / ' + limit + ' used';
      fill.style.width = pct + '%';
      if (pct >= 100) {
        fill.style.background = '#e57373';
        note.textContent = 'Monthly limit reached. Upgrade for more.';
        blocked.style.display = '';
        document.getElementById('limit-msg').textContent = "You've used all " + limit + " videos this month on the " + (d.tier_name || '') + ' plan.';
        document.getElementById('video-gen-btn').disabled = true;
        document.getElementById('video-gen-btn').style.opacity = '0.5';
        _videoLimitOk = false;
      } else if (pct >= 80) {
        fill.style.background = 'linear-gradient(90deg,#f59e0b,#ef4444)';
        note.textContent = (limit - used) + ' remaining this month on the ' + (d.tier_name || '') + ' plan.';
      } else {
        note.textContent = (limit - used) + ' remaining this month on the ' + (d.tier_name || '') + ' plan.';
      }
    }
  } catch(e) { console.warn('Usage stats failed:', e); }
}

async function loadStyles() {
  const category = document.getElementById('category').value;
  const styleSelect = document.getElementById('style');
  if (!category) return;
  try {
    const response = await fetch('/api/styles/' + encodeURIComponent(category));
    const styles = await response.json();
    styleSelect.innerHTML = '<option value="">-- Select a Style --</option>';
    styles.forEach(function(s) {
      var opt = document.createElement('option');
      opt.value = s.name;
      opt.textContent = s.name;
      styleSelect.appendChild(opt);
    });
  } catch(e) { console.warn('loadStyles error:', e); }
}

async function previewStyle() {
  const category = document.getElementById('category').value;
  const styleName = document.getElementById('style').value;
  if (!category || !styleName) return;
  try {
    const response = await fetch('/api/style/' + encodeURIComponent(category) + '/' + encodeURIComponent(styleName));
    const style = await response.json();
    const preview = document.getElementById('stylePreview');
    preview.style.display = 'block';
    preview.innerHTML = (
      '<strong>' + escHtml(style.name) + '</strong><br>' +
      '<span style="color:#606770">Platform:</span> ' + escHtml(style.platform || 'N/A') + '&nbsp;&nbsp;' +
      '<span style="color:#606770">Type:</span> ' + escHtml(style.video_type || 'N/A') + '&nbsp;&nbsp;' +
      '<span style="color:#606770">Voice:</span> ' + escHtml((style.audio_config||{}).voice_type || 'N/A')
    );
  } catch(e) { console.warn('previewStyle error:', e); }
}

function escHtml(s) {
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}

function onVideoSubmit() {
  if (!_videoLimitOk) {
    var err = document.getElementById('video-error');
    err.style.display = '';
    err.textContent = '\u274C You have reached your monthly video limit. Please upgrade your plan.';
    return false;
  }
  var btn = document.getElementById('video-gen-btn');
  var overlay = document.getElementById('video-loading');
  btn.disabled = true;
  btn.innerHTML = '<span class="gen-spinner" style="width:16px;height:16px;border-width:2px;display:inline-block;vertical-align:middle;margin-right:6px"></span>Working\u2026';
  overlay.style.display = '';
  overlay.scrollIntoView({behavior:'smooth'});
  var msgs = ['Analyzing your content strategy\u2026','Generating AI content ideas\u2026','Matching production templates\u2026','Building your specs\u2026'];
  var mi = 0;
  setInterval(function() {
    mi = (mi+1) % msgs.length;
    var t = document.getElementById('video-loading-title');
    if (t) t.textContent = msgs[mi];
  }, 5000);
  return true;
}

""" + f"""
const _vidCreativeRefUrls = {_vid_ref_urls_json};

function toggleVidCreativeRefs() {{
  const cb = document.getElementById('vid-use-creative-refs');
  const status = document.getElementById('vid-creative-ref-status');
  const checks = document.querySelectorAll('.vid-ref-check');
  const input  = document.getElementById('vid-creative-ref-input');
  if (cb && cb.checked) {{
    if (status) status.style.display = '';
    checks.forEach(c => c.style.display = '');
    if (input) input.value = JSON.stringify(_vidCreativeRefUrls);
  }} else {{
    if (status) status.style.display = 'none';
    checks.forEach(c => c.style.display = 'none');
    if (input) input.value = '';
  }}
}}

document.addEventListener('DOMContentLoaded', function() {{ loadVideoUsage(); toggleVidCreativeRefs(); }});
"""

    return HTMLResponse(
        build_page(
            title="Faceless Video",
            active_nav="faceless-video",
            body_content=body,
            extra_css=extra_css,
            extra_js=extra_js,
            user_name=_uname,
            business_name=_bname,
        ),
        headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
    )


@app.get("/api/styles/{category}")
async def get_styles_by_category(category: str):
    """API endpoint to get styles for a category"""
    styles = style_loader.list_styles_by_category(category)
    return JSONResponse([{"name": style} for style in styles])

@app.get("/api/style/{category}/{style_name}")
async def get_style_details(category: str, style_name: str):
    """API endpoint to get style details"""
    style = style_loader.get_style(category, style_name)
    if style:
        return JSONResponse({
            "name": style.template_name,
            "category": style.category,
            "platform": style.platform,
            "video_type": style.video_type,
            "audio_config": style.get_audio_config() or {},
            "visual_config": style.get_visual_config() or {}
        })
    return JSONResponse({"error": "Style not found"}, status_code=404)

@app.get("/image-generator", response_class=HTMLResponse)
async def image_generator_page(request: Request):
    """Image Generation with Visual Reference Style System"""
    from utils.shared_layout import build_page, get_user_context
    from database.db import get_db

    db = next(get_db())
    try:
        user_obj, profile = get_user_context(request, db)
    except Exception:
        user_obj, profile = None, None
    finally:
        db.close()

    if not user_obj:
        from fastapi.responses import RedirectResponse
        return RedirectResponse("/account/login", status_code=303)

    _uname = user_obj.full_name if user_obj else "User"
    _bname = profile.business_name if profile else "My Business"

    # ── Load creative style reference images from profile ──
    _creative_ref_imgs = []
    _creative_use_for_images = False
    if profile:
        try:
            import json as _json_cp
            _raw_cp = getattr(profile, "creative_preferences_json", None)
            if _raw_cp:
                _cp = _json_cp.loads(_raw_cp)
                _creative_use_for_images = bool(_cp.get("use_for_images", False))
                _creative_ref_imgs = _cp.get("reference_images", []) or []
        except Exception:
            pass

    # Build reference image thumbnail HTML
    _ref_thumbs_html = ""
    if _creative_ref_imgs:
        for _ri in _creative_ref_imgs[:10]:
            _rurl = _ri.get("url", "") if isinstance(_ri, dict) else str(_ri)
            _rname = _ri.get("name", "") if isinstance(_ri, dict) else ""
            if _rurl:
                _ref_thumbs_html += (
                    f'<div class="creative-ref-thumb" data-url="{_rurl}" style="position:relative;width:72px;height:72px;border-radius:8px;overflow:hidden;border:2px solid #e4e6eb;flex-shrink:0;cursor:pointer" title="{_rname}">'
                    f'<img src="{_rurl}" style="width:100%;height:100%;object-fit:cover" loading="lazy" alt="{_rname}">'
                    f'<div class="creative-ref-check" style="display:none;position:absolute;top:2px;right:2px;background:#5c6ac4;color:#fff;border-radius:50%;width:18px;height:18px;font-size:12px;line-height:18px;text-align:center">&#10003;</div>'
                    f'</div>'
                )
    _ref_checked = "checked" if _creative_use_for_images else ""
    _ref_section_display = "" if _creative_ref_imgs else "display:none;"

    body = f"""
<div style="max-width:860px;margin:0 auto">
  <div style="margin-bottom:20px">
    <h1 style="font-size:1.3rem;font-weight:800">&#127912; Create an Image</h1>
    <p style="font-size:.83rem;color:#606770;margin-top:3px">Describe what you want and pick a quality level. Alita handles the rest.</p>
  </div>

  <!-- Usage Status Bar -->
  <div id="img-usage-bar" class="card" style="margin-bottom:18px">
    <div class="card-body" style="padding:14px 18px">
      <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:8px">
        <span style="font-size:.85rem;font-weight:700;color:#1a1a2e">Images This Month</span>
        <span id="img-usage-label" style="font-size:.82rem;color:#606770">Loading&hellip;</span>
      </div>
      <div style="background:#e4e6eb;border-radius:99px;height:10px;overflow:hidden">
        <div id="img-usage-fill" style="height:100%;border-radius:99px;width:0%;transition:width .6s ease;background:linear-gradient(90deg,#5c6ac4,#7c3aed)"></div>
      </div>
      <div id="img-usage-note" style="font-size:.76rem;color:#90949c;margin-top:6px"></div>
    </div>
  </div>

  <!-- Blocked Banner (hidden by default) -->
  <div id="img-limit-blocked" style="display:none;background:#fce4ec;border:1px solid #e57373;border-radius:10px;padding:16px;color:#c62828;font-size:.88rem;margin-bottom:20px">
    <strong>&#128683; Image limit reached.</strong> <span id="img-limit-msg"></span>
    <a href="/billing" style="color:#5c6ac4;font-weight:700;margin-left:6px">Upgrade Plan &rarr;</a>
  </div>

  <!-- Quality Level -->
  <div class="card" style="margin-bottom:18px">
    <div class="card-header"><div class="card-title">Quality Level</div></div>
    <div class="card-body">
      <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:12px" id="tier-grid">
        <div class="tier-card" data-tier="budget" onclick="selectTier('budget')">
          <div style="font-size:.7rem;font-weight:700;background:#95a5a6;color:#fff;border-radius:99px;padding:2px 10px;display:inline-block;margin-bottom:6px">BASIC</div>
          <div style="font-weight:700;margin-bottom:8px;font-size:.95rem">Good</div>
          <ul style="list-style:none;font-size:.8rem;color:#444;padding:0;line-height:1.8">
            <li>&#10003; Fast (under 10 seconds)</li>
            <li>&#10003; Best for text &amp; flyers</li>
          </ul>
        </div>
        <div class="tier-card" data-tier="standard" onclick="selectTier('standard')">
          <div style="font-size:.7rem;font-weight:700;background:#3498db;color:#fff;border-radius:99px;padding:2px 10px;display:inline-block;margin-bottom:6px">RECOMMENDED</div>
          <div style="font-weight:700;margin-bottom:8px;font-size:.95rem">Great</div>
          <ul style="list-style:none;font-size:.8rem;color:#444;padding:0;line-height:1.8">
            <li>&#10003; Photorealistic results</li>
            <li>&#10003; Matches reference styles</li>
          </ul>
        </div>
        <div class="tier-card" data-tier="premium" onclick="selectTier('premium')">
          <div style="font-size:.7rem;font-weight:700;background:#9b59b6;color:#fff;border-radius:99px;padding:2px 10px;display:inline-block;margin-bottom:6px">PREMIUM</div>
          <div style="font-weight:700;margin-bottom:8px;font-size:.95rem">Best</div>
          <ul style="list-style:none;font-size:.8rem;color:#444;padding:0;line-height:1.8">
            <li>&#10003; Highest quality available</li>
            <li>&#10003; Copies any visual style</li>
          </ul>
        </div>
      </div>
    </div>
  </div>

  <!-- Describe Your Image -->
  <div class="card" style="margin-bottom:18px">
    <div class="card-header"><div class="card-title">Describe Your Image</div></div>
    <div class="card-body">
      <label class="form-label">What do you want the image to look like? *</label>
      <textarea id="img-prompt" class="form-input" rows="3" placeholder="Example: A bright coffee shop with warm lighting, cozy vibes, no people"></textarea>

      <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-top:14px">
        <div>
          <label class="form-label">Where will you use this?</label>
          <select id="img-platform" class="form-input">
            <option value="">General use</option>
            <option value="instagram_post">Instagram Post</option>
            <option value="instagram_reel">Instagram Story / Reel</option>
            <option value="facebook_post">Facebook Post</option>
            <option value="youtube_thumbnail">YouTube Thumbnail</option>
            <option value="tiktok">TikTok</option>
            <option value="linkedin_post">LinkedIn</option>
            <option value="x_post">X / Twitter</option>
            <option value="threads">Threads</option>
          </select>
        </div>
        <div>
          <label class="form-label">Shape</label>
          <select id="img-size" class="form-input">
            <option value="1080x1080">Square (best for posts)</option>
            <option value="1080x1920">Tall / Vertical (stories &amp; reels)</option>
            <option value="1920x1080">Wide / Landscape (YouTube)</option>
            <option value="1024x1024">Standard square</option>
          </select>
        </div>
      </div>
      <div style="margin-top:12px">
        <label class="form-label">Style <span style="font-weight:400;color:#90949c">(optional)</span></label>
        <select id="img-style" class="form-input">
            <option value="">No preference</option>
            <option value="photorealistic">Photorealistic</option>
            <option value="minimalist, clean">Minimalist / Clean</option>
            <option value="cinematic, dramatic lighting">Cinematic</option>
            <option value="watercolor, artistic">Watercolor / Artistic</option>
            <option value="neon lights, vibrant colors">Neon / Vibrant</option>
            <option value="vintage, retro film grain">Vintage / Retro</option>
            <option value="flat illustration, vector">Flat Illustration</option>
            <option value="3d render, modern">3D Rendered</option>
            <option value="hand drawn, sketch">Hand Drawn / Sketch</option>
        </select>
      </div>
    </div>
  </div>

  <!-- Creative Style Reference Images (from Settings) -->
  <div id="creative-ref-section" class="card" style="margin-bottom:18px;{_ref_section_display}">
    <div class="card-header" style="display:flex;align-items:center;justify-content:space-between">
      <div class="card-title">&#127912; Your Creative Style References</div>
      <label style="display:flex;align-items:center;gap:6px;font-size:.82rem;font-weight:600;cursor:pointer;margin:0">
        <input type="checkbox" id="use-creative-refs" {_ref_checked} onchange="toggleCreativeRefs()">
        Use these
      </label>
    </div>
    <div class="card-body" style="padding:12px 18px">
      <p style="font-size:.8rem;color:#606770;margin-bottom:10px">
        These reference images are from your <a href="/settings/creative" style="color:#5c6ac4;font-weight:600">Creative Style settings</a>.
        Enable the toggle to automatically apply their style.
      </p>
      <div id="creative-ref-grid" style="display:flex;gap:8px;flex-wrap:wrap">
        {_ref_thumbs_html}
      </div>
      <p id="creative-ref-status" style="font-size:.76rem;color:#16a34a;margin-top:8px;display:none">
        &#10003; Creative style references will be applied to your image.
      </p>
    </div>
  </div>

  <!-- Reference Image (collapsed by default) -->
  <details style="margin-bottom:18px" id="ref-section">
    <summary style="cursor:pointer;font-size:.88rem;font-weight:700;color:#5c6ac4;padding:12px 0">
      &#127912; Advanced: Match a reference image style (optional)
    </summary>
    <div class="card" style="margin-top:8px">
      <div class="card-body">
        <p style="font-size:.82rem;color:#606770;margin-bottom:12px">
          Paste a link to an image whose <strong>look and feel</strong> you want to copy.
          <span style="color:#90949c">(These are in addition to any creative style references above.)</span>
        </p>
        <div id="ref-inputs">
          <div class="ref-row" style="display:flex;gap:8px;margin-bottom:8px">
            <input type="url" class="form-input ref-url" placeholder="https://example.com/my-inspiration.jpg" style="flex:1">
            <button class="btn-secondary" onclick="removeRef(this)" style="padding:6px 10px;flex-shrink:0">&#10005;</button>
          </div>
        </div>
        <button class="btn-secondary" onclick="addRefField()" style="font-size:.78rem;padding:5px 10px;margin-bottom:12px">&#43; Add another</button>
        <div>
          <label class="form-label">How closely should we match the reference?</label>
          <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin-top:6px" id="strength-grid">
            <button class="strength-btn" data-strength="subtle" onclick="selectStrength('subtle')">
              A little
            </button>
            <button class="strength-btn selected" data-strength="balanced" onclick="selectStrength('balanced')">
              Moderate
            </button>
            <button class="strength-btn" data-strength="strong" onclick="selectStrength('strong')">
              Very close
            </button>
            <button class="strength-btn" data-strength="override" onclick="selectStrength('override')">
              Exact copy
            </button>
          </div>
          <p id="strength-note" style="font-size:.76rem;color:#90949c;margin-top:6px">Moderate: follows the reference style while keeping your description.</p>
        </div>
      </div>
    </div>
  </details>

  <!-- Generate button -->
  <div style="display:flex;gap:12px;justify-content:flex-end;margin-bottom:24px">
    <button id="gen-btn" class="btn-primary" style="padding:12px 32px;font-size:.95rem" onclick="generateImage()">
      &#127912; Generate Image
    </button>
  </div>

  <!-- Loading overlay -->
  <div id="gen-loading" style="display:none">
    <div class="card" style="text-align:center;padding:48px 24px">
      <div class="gen-spinner"></div>
      <h3 id="gen-loading-title" style="margin:20px 0 8px;color:#5c6ac4">Generating your image&hellip;</h3>
      <p id="gen-loading-sub" style="color:#6b7280;font-size:.88rem;margin:0">This usually takes 10&ndash;30 seconds depending on the quality tier.</p>
      <div style="margin-top:20px;display:flex;gap:6px;justify-content:center">
        <span class="gen-dot" style="animation-delay:0s"></span>
        <span class="gen-dot" style="animation-delay:.2s"></span>
        <span class="gen-dot" style="animation-delay:.4s"></span>
      </div>
    </div>
  </div>

  <!-- Result area -->
  <div id="gen-result" style="display:none">
    <div class="card">
      <div class="card-header"><div class="card-title" id="result-title">&#9989; Image Ready</div></div>
      <div class="card-body">
        <div style="text-align:center;margin-bottom:16px">
          <img id="result-img" src="" alt="Generated image" style="max-width:100%;border-radius:10px;box-shadow:0 4px 20px rgba(0,0,0,.15)">
        </div>
        <div id="result-meta" style="background:#f8f9fb;border-radius:8px;padding:12px;font-size:.83rem;margin-bottom:12px"></div>
        <div style="display:flex;gap:10px;flex-wrap:wrap;justify-content:center">
          <button class="btn-secondary" onclick="copyUrl()">&#128203; Copy Link</button>
          <button class="btn-secondary" onclick="openInNew()">&#128279; Open Full Size</button>
          <button class="btn-primary"   onclick="useInPost()">&#128197; Use in a Post</button>
        </div>
      </div>
    </div>
  </div>
  <div id="gen-error" style="display:none;background:#fce4ec;border:1px solid #e57373;border-radius:10px;padding:16px;color:#c62828;font-size:.88rem;margin-bottom:20px"></div>
</div>
"""

    extra_css = """
  .tier-card{border:2px solid #e4e6eb;border-radius:12px;padding:16px;cursor:pointer;transition:all .2s;background:#fff}
  .tier-card:hover{border-color:#5c6ac4;transform:translateY(-2px);box-shadow:0 4px 12px rgba(92,106,196,.2)}
  .tier-card.selected{border-color:#5c6ac4;background:#f5f0fb}
  .strength-btn{padding:9px 6px;border-radius:8px;border:1px solid #dde0e4;background:#fff;font-size:.82rem;font-weight:600;cursor:pointer;transition:all .15s;text-align:center}
  .strength-btn:hover{border-color:#5c6ac4;color:#5c6ac4}
  .strength-btn.selected{background:#5c6ac4;color:#fff;border-color:#5c6ac4}
  .gen-spinner{width:48px;height:48px;border:4px solid #e4e6eb;border-top-color:#5c6ac4;border-radius:50%;margin:0 auto;animation:gen-spin .8s linear infinite}
  @keyframes gen-spin{to{transform:rotate(360deg)}}
  .gen-dot{width:8px;height:8px;background:#5c6ac4;border-radius:50%;animation:gen-pulse 1.2s ease-in-out infinite}
  @keyframes gen-pulse{0%,80%,100%{opacity:.3;transform:scale(.8)}40%{opacity:1;transform:scale(1.1)}}
"""

    extra_js = """
let selectedTier     = 'standard';
let selectedStrength = 'balanced';
let lastResultUrl    = '';
let _imgLimitOk      = true;

// ── Load image usage stats on page open ──
async function loadImageUsage() {
  try {
    const r = await fetch('/api/usage-stats');
    if (!r.ok) return;
    const d = await r.json();
    const used  = d.images_used  || 0;
    const limit = d.images_limit;
    const label = document.getElementById('img-usage-label');
    const fill  = document.getElementById('img-usage-fill');
    const note  = document.getElementById('img-usage-note');
    const blocked = document.getElementById('img-limit-blocked');

    if (limit === 0) {
      label.textContent = 'Not available on ' + (d.tier_name || 'Free') + ' plan';
      fill.style.width = '100%';
      fill.style.background = '#e57373';
      note.textContent = 'Upgrade your plan to unlock image generation.';
      blocked.style.display = '';
      document.getElementById('img-limit-msg').textContent = 'Your ' + (d.tier_name || 'Free') + ' plan does not include AI images.';
      document.getElementById('gen-btn').disabled = true;
      document.getElementById('gen-btn').style.opacity = '0.5';
      _imgLimitOk = false;
    } else if (limit === -1) {
      label.textContent = used + ' used (unlimited)';
      fill.style.width = '0%';
      note.textContent = 'Your ' + (d.tier_name || 'Pro') + ' plan has unlimited image generation.';
    } else {
      const pct = Math.min(100, Math.round((used / limit) * 100));
      label.textContent = used + ' / ' + limit + ' used';
      fill.style.width = pct + '%';
      if (pct >= 100) {
        fill.style.background = '#e57373';
        note.textContent = 'Monthly limit reached. Upgrade for more.';
        blocked.style.display = '';
        document.getElementById('img-limit-msg').textContent = "You've used all " + limit + " images this month on the " + (d.tier_name || '') + ' plan.';
        document.getElementById('gen-btn').disabled = true;
        document.getElementById('gen-btn').style.opacity = '0.5';
        _imgLimitOk = false;
      } else if (pct >= 80) {
        fill.style.background = 'linear-gradient(90deg,#f59e0b,#ef4444)';
        note.textContent = (limit - used) + ' remaining this month on the ' + (d.tier_name || '') + ' plan.';
      } else {
        note.textContent = (limit - used) + ' remaining this month on the ' + (d.tier_name || '') + ' plan.';
      }
    }
  } catch(e) { console.warn('Image usage stats failed:', e); }
}

function refreshImageUsage() { loadImageUsage(); }

const strengthNotes = {
  subtle:   'A little: adds a hint of the reference style. â€” your prompt drives most of the image.',
  balanced: 'Moderate: follows the reference style while keeping your description.',
  strong:   'Very close: the reference style takes over most of the image.',
  override: 'Exact copy: makes the image look as close to the reference as possible.',
};

function selectTier(tier) {
  selectedTier = tier;
  document.querySelectorAll('.tier-card').forEach(c => c.classList.remove('selected'));
  const t = document.querySelector('.tier-card[data-tier="' + tier + '"]');
  if (t) t.classList.add('selected');

  // Show/hide ref section hint based on tier
  const note = document.getElementById('ref-section');
  if (note) {
    const badge = note.querySelector('.card-title span');
    if (badge) {
      badge.textContent = tier === 'budget' ? '(not used for DALL-E budget tier)' : '(optional â€” enhances style matching)';
      badge.style.color = tier === 'budget' ? '#e65100' : '#90949c';
    }
  }
}

function selectStrength(s) {
  selectedStrength = s;
  document.querySelectorAll('.strength-btn').forEach(b => b.classList.remove('selected'));
  const b = document.querySelector('.strength-btn[data-strength="' + s + '"]');
  if (b) b.classList.add('selected');
  const note = document.getElementById('strength-note');
  if (note) note.textContent = strengthNotes[s] || '';
}

function addRefField() {
  const container = document.getElementById('ref-inputs');
  const row = document.createElement('div');
  row.className = 'ref-row';
  row.style.cssText = 'display:flex;gap:8px;margin-bottom:8px';
  row.innerHTML = (
    '<input type="url" class="form-input ref-url" placeholder="https://example.com/reference-image.jpg" style="flex:1">' +
    '<button class="btn-secondary" onclick="removeRef(this)" style="padding:6px 10px;flex-shrink:0">&#10005;</button>'
  );
  container.appendChild(row);
}

function removeRef(btn) {
  const rows = document.querySelectorAll('.ref-row');
  if (rows.length <= 1) {
    // Just clear the input instead of removing last row
    const input = btn.closest('.ref-row').querySelector('.ref-url');
    if (input) input.value = '';
    return;
  }
  btn.closest('.ref-row').remove();
}

let _genBusy = false;
async function generateImage() {
  if (_genBusy) return;          // prevent double-click
  if (!_imgLimitOk) {
    const errorDiv = document.getElementById('gen-error');
    errorDiv.style.display='';
    errorDiv.textContent='\u274c You have reached your monthly image limit. Please upgrade your plan.';
    return;
  }
  const prompt   = (document.getElementById('img-prompt').value || '').trim();
  const platform = document.getElementById('img-platform').value;
  const size     = document.getElementById('img-size').value;
  const style    = document.getElementById('img-style').value;
  // Collect manually entered refs
  const manualRefs = Array.from(document.querySelectorAll('.ref-url'))
                       .map(i => i.value.trim()).filter(Boolean);
  // Collect creative style refs if toggle is on
  const useCreative = document.getElementById('use-creative-refs');
  let creativeRefs = [];
  if (useCreative && useCreative.checked) {
    creativeRefs = Array.from(document.querySelectorAll('.creative-ref-thumb'))
                       .map(el => el.dataset.url).filter(Boolean);
  }
  const refs = [...new Set([...creativeRefs, ...manualRefs])];

  const resultDiv  = document.getElementById('gen-result');
  const errorDiv   = document.getElementById('gen-error');
  const loadingDiv = document.getElementById('gen-loading');
  const btn        = document.getElementById('gen-btn');

  errorDiv.style.display   = 'none';
  resultDiv.style.display  = 'none';
  loadingDiv.style.display = 'none';

  if (!prompt) { errorDiv.style.display=''; errorDiv.textContent='\u274c Please enter a prompt.'; return; }
  if (!selectedTier) { errorDiv.style.display=''; errorDiv.textContent='\u274c Please select a quality tier.'; return; }

  _genBusy        = true;
  btn.disabled    = true;
  btn.innerHTML   = '<span class="gen-spinner" style="width:16px;height:16px;border-width:2px;display:inline-block;vertical-align:middle;margin-right:6px"></span>Generating\u2026';
  loadingDiv.style.display = '';
  loadingDiv.scrollIntoView({behavior:'smooth'});

  // Cycle status messages while waiting
  const msgs = ['Crafting your prompt\u2026','Calling the AI model\u2026','Rendering pixels\u2026','Almost there\u2026'];
  let mi = 0;
  const msgTimer = setInterval(() => {
    mi = (mi+1) % msgs.length;
    const t = document.getElementById('gen-loading-title');
    if (t) t.textContent = msgs[mi];
  }, 6000);

  try {
    const payload = {
      prompt,
      quality_tier:    selectedTier,
      platform:        platform || null,
      size,
      style_modifier:  style || null,
      reference_images: refs,
      style_strength:  selectedStrength,
    };

    const r = await fetch('/api/generate-image', {
      method: 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify(payload),
    });
    const d = await r.json();

    if (d.success && d.image_url) {
      lastResultUrl = d.image_url;
      document.getElementById('result-img').src = d.image_url;
      document.getElementById('result-title').textContent = '\\u2705 Image Generated (' + (d.api_used || selectedTier) + ')';
      document.getElementById('result-meta').innerHTML = (
        '<strong>Tier:</strong> ' + (d.tier_name || selectedTier) + '&nbsp;&nbsp;' +
        '<strong>Prompt length:</strong> ' + (d.prompt_chars || '?') + ' chars&nbsp;&nbsp;' +
        (d.style_descriptor ? '<strong>Style extracted:</strong> ' + escHtml(d.style_descriptor.slice(0,80)) + '&hellip;' : '') +
        (refs.length ? '<br><strong>References used:</strong> ' + refs.length : '')
      );
      resultDiv.style.display = '';
      resultDiv.scrollIntoView({behavior:'smooth'});
      refreshImageUsage();  // update the status bar after successful generation
    } else {
      errorDiv.style.display = '';
      errorDiv.textContent = '\\u274C ' + (d.error || 'Image generation failed');
    }
  } catch(e) {
    errorDiv.style.display = '';
    errorDiv.textContent = '\\u274C Network error: ' + e.message;
  }

  clearInterval(msgTimer);
  loadingDiv.style.display = 'none';
  btn.disabled    = false;
  btn.innerHTML   = '\\u{1F3A8} Generate Image';
  _genBusy        = false;
}

function copyUrl() {
  if (!lastResultUrl) return;
  navigator.clipboard.writeText(lastResultUrl).then(() => alert('URL copied!')).catch(() => {
    prompt('Copy this URL:', lastResultUrl);
  });
}

function openInNew() {
  if (lastResultUrl) window.open(lastResultUrl, '_blank');
}

function useInPost() {
  if (!lastResultUrl) return;
  // Navigate to create-post with image URL pre-filled
  window.location.href = '/create-post/dashboard?image_url=' + encodeURIComponent(lastResultUrl);
}

function escHtml(s) {
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}

function toggleCreativeRefs() {
  const cb = document.getElementById('use-creative-refs');
  const status = document.getElementById('creative-ref-status');
  const thumbs = document.querySelectorAll('.creative-ref-thumb .creative-ref-check');
  if (cb && cb.checked) {
    if (status) status.style.display = '';
    thumbs.forEach(t => t.style.display = '');
  } else {
    if (status) status.style.display = 'none';
    thumbs.forEach(t => t.style.display = 'none');
  }
}

// Pre-select standard tier on load + load usage stats + init creative refs
document.addEventListener('DOMContentLoaded', () => { selectTier('standard'); loadImageUsage(); toggleCreativeRefs(); });
"""

    return HTMLResponse(
        build_page(
            title="Image Generator",
            active_nav="image-generator",
            body_content=body,
            extra_css=extra_css,
            extra_js=extra_js,
            user_name=_uname,
            business_name=_bname,
        ),
        headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
    )


@app.post("/api/generate-image")
async def api_generate_image(request: Request):
    """JSON endpoint: generate image via ImageGeneratorAgent"""
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON"}, status_code=400)

    prompt         = (body.get("prompt") or "").strip()
    quality_tier   = (body.get("quality_tier") or "standard").strip().lower()
    platform       = body.get("platform") or None
    size           = (body.get("size") or "1080x1080").strip()
    style_modifier = body.get("style_modifier") or None
    reference_images = [u for u in (body.get("reference_images") or []) if u]
    style_strength = (body.get("style_strength") or "balanced").strip()

    if not prompt:
        return JSONResponse({"error": "prompt is required", "success": False}, status_code=400)

    try:
        from agents.image_generator import ImageGeneratorAgent, ImageQuality

        tier_map = {
            "budget":   ImageQuality.BUDGET,
            "standard": ImageQuality.STANDARD,
            "premium":  ImageQuality.PREMIUM,
        }
        tier_names = {
            "budget":   "DALL-E 3",
            "standard": "Flux Pro",
            "premium":  "Midjourney",
        }

        quality = tier_map.get(quality_tier, ImageQuality.STANDARD)

        # Resolve client_id from session if available
        from api.auth_routes import get_current_user
        from database.db import get_db
        from database.models import ClientProfile

        db    = next(get_db())
        client_id = "default_client"
        try:
            user = get_current_user(request, db)
            if user:
                p = db.query(ClientProfile).filter(ClientProfile.user_id == user.id).first()
                if p:
                    client_id = p.client_id
                    # ── Pre-flight limit check ──
                    from utils.plan_limits import check_limit
                    ok, msg = check_limit(p, "images_created")
                    if not ok:
                        db.close()
                        return JSONResponse({"success": False, "error": msg}, status_code=403)
        except Exception:
            pass
        finally:
            db.close()

        agent  = ImageGeneratorAgent(client_id=client_id)
        result = await agent.generate_image(
            prompt=prompt,
            quality=quality,
            platform=platform,
            size=size,
            style=style_modifier,
            reference_images=reference_images if reference_images else None,
            use_client_references=(not reference_images),   # auto-load if none provided
        )

        if result.success and result.url:
            # ── Increment usage counter ──────────────────────────────────
            try:
                from utils.plan_limits import increment_usage
                _db2 = next(get_db())
                try:
                    from database.models import ClientProfile as _CP2
                    from api.auth_routes import get_current_user as _gcu2
                    _u2 = _gcu2(request, _db2)
                    if _u2:
                        _p2 = _db2.query(_CP2).filter(_CP2.user_id == _u2.id).first()
                        if _p2:
                            increment_usage(_p2, "images_created", _db2)
                finally:
                    _db2.close()
            except Exception:
                pass
            # ────────────────────────────────────────────────────────────
            return JSONResponse({
                "success":         True,
                "image_url":       result.url,
                "api_used":        result.api_used or quality_tier,
                "tier_name":       tier_names.get(quality_tier, quality_tier),
                "prompt_chars":    len((result.metadata or {}).get("prompt", "")),
                "style_descriptor": result.metadata.get("style_descriptor", "") if result.metadata else "",
            })
        else:
            return JSONResponse({
                "success": False,
                "error":   result.error or "Image generation failed",
            }, status_code=500)

    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)


# Keep old form-POST route as a redirect shim for backward compat
@app.post("/generate-image")
async def generate_image_legacy(request: Request):
    from fastapi.responses import RedirectResponse
    return RedirectResponse("/image-generator", status_code=303)




@app.post("/create-video-specs")
async def create_video_specs(
    request: Request,
    content_goal: str = Form(...),
    business_name: str = Form(...),
    industry: str = Form(...),
    target_audience: str = Form(...),
    content_topic: str = Form(""),
    category: str = Form(...),
    style: str = Form(...),
    video_quality: str = Form("tier2"),
    platform: str = Form(...),
    duration_pref: str = Form(...),
    creative_ref_urls: str = Form(""),
):
    """Create production-ready video specifications using Content Agent + Faceless Video styles"""

    # ── Server-side plan limit check ────────────────────────────────────────
    from api.auth_routes import get_current_user
    from database.db import get_db
    from database.models import ClientProfile
    from utils.plan_limits import check_limit, increment_usage

    db = next(get_db())
    profile = None
    try:
        user = get_current_user(request, db)
        if user:
            profile = db.query(ClientProfile).filter(ClientProfile.user_id == user.id).first()
        if profile:
            ok, msg = check_limit(profile, "videos_created")
            if not ok:
                db.close()
                return HTMLResponse(
                    f'<div style="max-width:600px;margin:80px auto;font-family:system-ui;text-align:center">'
                    f'<h2 style="color:#c62828">&#128683; Video Limit Reached</h2>'
                    f'<p style="color:#555;line-height:1.6">{msg}</p>'
                    f'<a href="/billing" style="display:inline-block;margin:16px 8px;padding:10px 24px;background:#5c6ac4;color:#fff;border-radius:8px;text-decoration:none;font-weight:600">Upgrade Plan</a>'
                    f'<a href="/faceless-video" style="display:inline-block;margin:16px 8px;padding:10px 24px;background:#e4e6eb;color:#333;border-radius:8px;text-decoration:none;font-weight:600">&larr; Back</a>'
                    f'</div>'
                )
    except Exception:
        pass
    finally:
        db.close()
    # ────────────────────────────────────────────────────────────────────────
    
    # Initialize Content Agent for this client
    client_id = business_name.lower().replace(" ", "_")
    content_agent = ContentCreationAgent(client_id=client_id)
    
    # Get content from Marketing Intelligence Agent based on goal
    # Generate content ideas using Content Agent
    try:
        ideas = await content_agent.get_content_ideas(
            niche=industry,
            num_ideas=1,
            platforms=[platform.replace("_", "")],  # Convert youtube_shorts â†’ youtube
            content_types=[content_goal]  # "engagement", "growth", or "sales"
        )
        
        if not ideas:
            return HTMLResponse("<h2>âŒ Error: Could not generate content ideas</h2><a href='/faceless-video'>â† Back</a>")
        
        # Use the first idea
        idea = ideas[0]
        
        # Override topic if user provided one
        if content_topic.strip():
            idea.topic = content_topic
        
        # Extract content data
        content_data = {
            "topic": idea.topic,
            "hooks": idea.hooks[:3] if idea.hooks else ["Discover something new"],
            "key_points": [idea.angle] + (idea.keywords[:4] if idea.keywords else []),
            "cta": idea.call_to_action or "Follow for more",
            "target_platform": platform,
            "goal": content_goal,
            "keywords": idea.keywords if idea.keywords else [],
            "reasoning": idea.reasoning
        }
        
    except Exception as e:
        # Fallback to manual input if provided
        if not content_topic.strip():
            return HTMLResponse(f"<h2>âŒ Error: {str(e)}</h2><a href='/faceless-video'>â† Back</a>")
        
        content_data = {
            "topic": content_topic,
            "hooks": ["Check this out"],
            "key_points": ["Learn more about this topic"],
            "cta": "Follow for more",
            "target_platform": platform,
            "goal": content_goal,
            "keywords": [],
            "reasoning": "Manual input"
        }
    
    # Get the selected style
    selected_style = style_loader.get_style(category, style)
    
    if not selected_style:
        return HTMLResponse("<h2>âŒ Error: Style not found</h2><a href='/faceless-video'>â† Back</a>")
    
    # Create enhanced content package (Content Agent output + Style specs)
    enhanced_content = {
        # Business context
        "business_name": business_name,
        "industry": industry,
        "target_audience": target_audience,
        "content_goal": content_goal,
        
        # Content from Marketing Intelligence Agent
        "topic": content_data["topic"],
        "hooks": content_data["hooks"],
        "key_points": content_data["key_points"],
        "cta": content_data["cta"],
        "keywords": content_data["keywords"],
        "reasoning": content_data["reasoning"],
        "target_platform": platform,
        "duration_preference": duration_pref,
        "video_quality_tier": video_quality,
        
        # Style applied
        "style_applied": True,
        "style_name": selected_style.template_name,
        "style_category": selected_style.category,
        
        # Production specs from style
        "audio_config": selected_style.get_audio_config(),
        "visual_config": selected_style.get_visual_config(),
        "pacing_config": selected_style.get_pacing_config(),
        "content_guidelines": selected_style.get_content_guidelines(),
        "platform_settings": selected_style.get_platform_settings(platform),
        "elevenlabs_settings": selected_style.get_elevenlabs_settings(),
        "technical_specs": selected_style.technical_specs,
        "script_generation_prompt": selected_style.get_script_writing_prompt(),
    }

    # Parse creative reference image URLs from the form
    _parsed_creative_refs = []
    if creative_ref_urls and creative_ref_urls.strip():
        try:
            import json as _json_cru
            _parsed_creative_refs = _json_cru.loads(creative_ref_urls)
            if not isinstance(_parsed_creative_refs, list):
                _parsed_creative_refs = []
        except Exception:
            _parsed_creative_refs = []
    if _parsed_creative_refs:
        enhanced_content["reference_images"] = _parsed_creative_refs

    # ── Increment video usage counter on success ────────────────────────────
    if profile:
        try:
            from database.db import get_db as _get_db2
            _db2 = next(_get_db2())
            _p2 = _db2.query(ClientProfile).filter(ClientProfile.client_id == profile.client_id).first()
            if _p2:
                increment_usage(_p2, "videos_created", _db2)
            _db2.close()
        except Exception as _inc_err:
            print(f"[video-specs] Usage increment failed: {_inc_err}")
    # ────────────────────────────────────────────────────────────────────────
    
    # Format the response
    audio = enhanced_content.get('audio_config', {})
    visual = enhanced_content.get('visual_config', {})
    pacing = enhanced_content.get('pacing_config', [])
    guidelines = enhanced_content.get('content_guidelines', [])
    
    audio_html = f"""
        <p><strong>Voice Type:</strong> {audio.get('voice_type', 'N/A')}</p>
        <p><strong>Music:</strong> {str(audio.get('music', 'N/A'))[:100]}...</p>
        <p><strong>Voice Level:</strong> {audio.get('voice_db', 'N/A')} dB</p>
        <p><strong>Music Level:</strong> {audio.get('music_db', 'N/A')} dB</p>
    """ if audio else "<p>No audio config available</p>"
    
    visual_html = f"""
        <p><strong>Scene Duration:</strong> {visual.get('scene_duration', 'N/A')}</p>
        <p><strong>Transitions:</strong> {visual.get('transition_style', 'N/A')}</p>
        <p><strong>Color Scheme:</strong> {visual.get('color_scheme', 'N/A')}</p>
    """ if visual else "<p>No visual config available</p>"
    
    pacing_html = ""
    if pacing and isinstance(pacing, list):
        for seg in pacing[:4]:
            pacing_html += f"<li><strong>{seg.get('segment', 'N/A')}</strong> ({seg.get('timing', 'N/A')}): {seg.get('content', seg.get('action', 'N/A'))}</li>"
    
    guidelines_html = ""
    if guidelines:
        for g in guidelines[:5]:
            guidelines_html += f"<li>{g}</li>"
    
    return HTMLResponse(f"""
    <html>
        <head>
            <title>Production Specs - Alita</title>
            <style>
                body {{ font-family: Arial, sans-serif; max-width: 1200px; margin: 50px auto; padding: 0 20px; background: #f5f5f5; }}
                .container {{ background: white; padding: 30px; border-radius: 10px; margin-bottom: 20px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }}
                h1 {{ color: #27ae60; }}
                h2 {{ color: #2c3e50; border-bottom: 2px solid #ecf0f1; padding-bottom: 10px; }}
                .spec-section {{ background: #f8f9fa; padding: 15px; border-radius: 5px; margin: 15px 0; border-left: 4px solid #3498db; }}
                button {{ background: #3498db; color: white; padding: 10px 20px; border: none; border-radius: 5px; cursor: pointer; margin: 5px; }}
                button:hover {{ background: #2980b9; }}
                .download {{ background: #27ae60; }}
                .download:hover {{ background: #229954; }}
            </style>
        </head>
        <body>
            <div class="container">
                <h1>âœ&hellip; Production Specs Generated!</h1>
                
                <div class="spec-section">
                    <h3>ðŸ“‹ Project Details</h3>
                    <p><strong>Business:</strong> {business_name}</p>
                    <p><strong>Industry:</strong> {industry}</p>
                    <p><strong>Content Goal:</strong> {content_goal.upper()} ({{'engagement': 'Maximize views & interaction', 'growth': 'Build followers', 'sales': 'Drive conversions'}}[content_goal])</p>
                    <p><strong>Topic:</strong> {enhanced_content['topic']}</p>
                    <p><strong>Style:</strong> {selected_style.template_name}</p>
                    <p><strong>Platform:</strong> {platform}</p>
                    <p><strong>Video Quality:</strong> {video_quality.replace('tier', 'Tier ').upper()}</p>
                </div>
                
                <div class="spec-section">
                    <h3>ðŸ’¡ AI-Generated Content Strategy</h3>
                    <p><strong>Hooks:</strong></p>
                    <ul>{"".join([f"<li>{hook}</li>" for hook in enhanced_content['hooks']])}</ul>
                    <p><strong>Key Points:</strong></p>
                    <ul>{"".join([f"<li>{kp}</li>" for kp in enhanced_content['key_points']])}</ul>
                    <p><strong>Call to Action:</strong> {enhanced_content['cta']}</p>
                    <p><strong>Keywords:</strong> {', '.join(enhanced_content.get('keywords', [])[:5])}</p>
                </div>
                
                <div class="spec-section">
                    <h3>ðŸŽ™ï¸ Audio Configuration</h3>
                    {audio_html}
                </div>
                
                <div class="spec-section">
                    <h3>ðŸŽ¬ Visual Configuration</h3>
                    {visual_html}
                </div>
                
                <div class="spec-section">
                    <h3>â±ï¸ Pacing Structure</h3>
                    <ol>{pacing_html}</ol>
                </div>
                
                <div class="spec-section">
                    <h3>ðŸ“ Content Guidelines</h3>
                    <ul>{guidelines_html}</ul>
                </div>
                
                <div class="spec-section">
                    <h3>ðŸ¤– AI Script Prompt</h3>
                    <p>{enhanced_content.get('script_generation_prompt', 'Use production guidelines')[:300]}...</p>
                </div>
                
                <button onclick="window.print()">ðŸ–¨ï¸ Print Specs</button>
                <button class="download" onclick="downloadJSON()">â¬‡ï¸ Download JSON</button>
                <button onclick="location.href='/faceless-video'">â† Create Another</button>
                <button onclick="location.href='/'">ðŸ  Home</button>
                
                <script>
                    function downloadJSON() {{
                        const specs = {json.dumps(enhanced_content)};
                        const blob = new Blob([JSON.stringify(specs, null, 2)], {{type: 'application/json'}});
                        const url = URL.createObjectURL(blob);
                        const a = document.createElement('a');
                        a.href = url;
                        a.download = 'video_production_specs.json';
                        a.click();
                    }}
                </script>
            </div>
        </body>
    </html>
    """)



# â”€â”€â”€ Agent Scheduler â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# Starts / stops with the FastAPI application lifecycle.
# All per-client jobs (strategy, content gen, posting, growth, analytics)
# are registered automatically for every fully-onboarded client.
try:
    from agents.agent_scheduler import scheduler as _agent_scheduler

    @app.on_event("startup")
    async def _start_scheduler():
        # Ensure admin account + DB tables always exist (covers Railway ephemeral FS)
        try:
            from init_db import init_admin
            init_admin()
        except Exception as _e:
            print(f"[warn] init_db skipped: {_e}")

        # -- Report Integrity Watchdog --
        # Imports any orphaned filesystem reports into PostgreSQL so nothing
        # is lost when Railway replaces the container.
        try:
            from utils.report_watchdog import startup_watchdog
            startup_watchdog()
        except Exception as _rw:
            print(f"[warn] report_watchdog skipped: {_rw}")

        await _agent_scheduler.start()
        print("[ok] Agent scheduler started (weekly strategy, daily posting, growth, analytics)")

    @app.on_event("shutdown")
    async def _stop_scheduler():
        await _agent_scheduler.shutdown()
        print("ðŸ›‘ Agent scheduler stopped")

    # â”€â”€ Admin scheduler control routes â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    from fastapi import Query as _Query

    @app.get("/admin/scheduler/status")
    async def scheduler_status(request: Request):
        """Return current scheduler status (all jobs + next run times)."""
        from api.auth_routes import require_admin
        from database.db import get_db as _get_db
        db = next(_get_db())
        try:
            require_admin(request, db)
        except Exception:
            from fastapi.responses import JSONResponse as _JR
            return _JR({"error": "Unauthorized"}, status_code=403)
        finally:
            db.close()
        from fastapi.responses import JSONResponse as _JR
        return _JR(_agent_scheduler.get_status())

    @app.post("/admin/scheduler/run/{job_type}")
    async def scheduler_run_now(
        job_type: str,
        request: Request,
        client_id: str = _Query(..., description="Client slug to run the job for"),
    ):
        """Trigger a specific scheduler job immediately (admin only)."""
        from api.auth_routes import require_admin
        from database.db import get_db as _get_db
        from fastapi.responses import JSONResponse as _JR
        db = next(_get_db())
        try:
            require_admin(request, db)
        except Exception:
            return _JR({"error": "Unauthorized"}, status_code=403)
        finally:
            db.close()
        result = await _agent_scheduler.run_now(job_type, client_id)
        return _JR(result)

    @app.post("/admin/scheduler/add-client/{client_id}")
    async def scheduler_add_client(client_id: str, request: Request):
        """Register scheduler jobs for a newly-onboarded client (admin only)."""
        from api.auth_routes import require_admin
        from database.db import get_db as _get_db
        from fastapi.responses import JSONResponse as _JR
        db = next(_get_db())
        try:
            require_admin(request, db)
        except Exception:
            return _JR({"error": "Unauthorized"}, status_code=403)
        finally:
            db.close()
        _agent_scheduler.add_client(client_id)
        return _JR({"success": True, "client_id": client_id, "message": "Jobs registered"})

    @app.post("/admin/scheduler/remove-client/{client_id}")
    async def scheduler_remove_client(client_id: str, request: Request):
        """Remove all scheduled jobs for a client (admin only)."""
        from api.auth_routes import require_admin
        from database.db import get_db as _get_db
        from fastapi.responses import JSONResponse as _JR
        db = next(_get_db())
        try:
            require_admin(request, db)
        except Exception:
            return _JR({"error": "Unauthorized"}, status_code=403)
        finally:
            db.close()
        _agent_scheduler.remove_client(client_id)
        return _JR({"success": True, "client_id": client_id, "message": "Jobs removed"})

    print("âœ&hellip; Agent scheduler configured: /admin/scheduler/status|run|add-client|remove-client")
except Exception as _sched_err:
    print(f"âš ï¸  Agent scheduler not loaded: {_sched_err}")


if __name__ == "__main__":
    print(" Starting web server at http://localhost:8000")
    reload_enabled = os.getenv("ALITA_DEV_RELOAD", "").strip().lower() in {"1", "true", "yes"}
    if reload_enabled:
        print("ðŸ” Auto-reload enabled (ALITA_DEV_RELOAD=1)")
        uvicorn.run("web_app:app", host="0.0.0.0", port=8000, reload=True)
    else:
        uvicorn.run(app, host="0.0.0.0", port=8000)
