"""
OAuth Routes - FastAPI router for Meta OAuth 2.0 flow.

Provides the complete OAuth lifecycle endpoints:
    GET  /auth/login            → Redirect user to Meta consent screen
    GET  /auth/callback         → Handle Meta redirect after user approves
    GET  /auth/status           → Check current connection status
    POST /auth/disconnect       → Revoke tokens and disconnect account
    GET  /auth/accounts         → List connected Instagram accounts
    GET  /auth/dashboard        → User dashboard showing connection status

These routes are mounted on the main FastAPI app in web_app.py.
"""

import os
import time
import secrets
from typing import Optional
from fastapi import APIRouter, BackgroundTasks, Request, Response, Cookie, Query
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from dotenv import load_dotenv

load_dotenv()

# Import our OAuth components
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from api.meta_oauth import MetaOAuthClient, AccessTokenData
from api.token_manager import TokenManager

# ─── Initialize ─────────────────────────────────────────────────────────

router = APIRouter(prefix="/auth", tags=["OAuth"])

# Lazy-initialized singletons (initialized when first route is hit)
_oauth_client: Optional[MetaOAuthClient] = None
_token_manager: Optional[TokenManager] = None


def get_oauth_client(request: Request = None) -> MetaOAuthClient:
    """Get or create the MetaOAuthClient, using the request to derive the redirect URI."""
    global _oauth_client
    # If we have a request, always build a fresh client with the correct domain
    if request is not None:
        try:
            fwd_host = request.headers.get("x-forwarded-host", "").strip()
            if fwd_host:
                proto = request.headers.get("x-forwarded-proto", "https").strip()
                raw = f"{proto}://{fwd_host}"
            else:
                raw = str(request.base_url).rstrip("/")
                if raw.startswith("http://") and request.headers.get("x-forwarded-proto") == "https":
                    raw = "https://" + raw[len("http://"):]
            redirect_uri = os.getenv("META_REDIRECT_URI") or (raw + "/auth/callback")
            return MetaOAuthClient(redirect_uri=redirect_uri)
        except ValueError as e:
            print(f"⚠️  OAuth client not configured: {e}")
            raise
    if _oauth_client is None:
        try:
            _oauth_client = MetaOAuthClient()
        except ValueError as e:
            print(f"⚠️  OAuth client not configured: {e}")
            raise
    return _oauth_client


def get_token_manager() -> TokenManager:
    """Get or create the TokenManager singleton."""
    global _token_manager
    if _token_manager is None:
        _token_manager = TokenManager()
        _token_manager.initialize()
    return _token_manager


def _get_session_user(session_token: Optional[str]) -> Optional[str]:
    """Get user_id from session cookie."""
    if not session_token:
        return None
    tm = get_token_manager()
    return tm.get_session_user(session_token)


# ─── HTML Templates ─────────────────────────────────────────────────────

def _base_style() -> str:
    """Shared CSS for all auth pages."""
    return """
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background: #0f1419; color: #e7e9ea; min-height: 100vh; }
        .auth-container { max-width: 600px; margin: 0 auto; padding: 40px 20px; }
        .auth-card { background: #1a1f25; border: 1px solid #2f3336; border-radius: 16px; padding: 40px; text-align: center; }
        .auth-card h1 { font-size: 28px; margin-bottom: 8px; }
        .auth-card h2 { font-size: 20px; color: #8b98a5; margin-bottom: 24px; font-weight: normal; }
        .auth-card p { color: #8b98a5; line-height: 1.6; margin-bottom: 16px; }
        .logo { font-size: 48px; margin-bottom: 16px; }
        .btn { display: inline-block; padding: 14px 32px; border-radius: 30px; font-size: 16px; font-weight: 600; cursor: pointer; text-decoration: none; border: none; transition: all 0.2s; }
        .btn-primary { background: #1877f2; color: white; }
        .btn-primary:hover { background: #166fe5; transform: scale(1.02); }
        .btn-danger { background: #e4405f; color: white; }
        .btn-danger:hover { background: #d62e4d; }
        .btn-secondary { background: #2f3336; color: #e7e9ea; border: 1px solid #536471; }
        .btn-secondary:hover { background: #3a3f44; }
        .btn-success { background: #00ba7c; color: white; }
        .btn-success:hover { background: #00a36e; }
        .permissions-list { text-align: left; margin: 24px 0; padding: 20px; background: #15191e; border-radius: 12px; }
        .permissions-list h3 { margin-bottom: 12px; color: #e7e9ea; }
        .perm-item { display: flex; align-items: center; padding: 8px 0; border-bottom: 1px solid #2f3336; }
        .perm-item:last-child { border-bottom: none; }
        .perm-icon { margin-right: 12px; font-size: 18px; }
        .perm-text { color: #8b98a5; font-size: 14px; }
        .status-badge { display: inline-block; padding: 4px 12px; border-radius: 12px; font-size: 12px; font-weight: 600; }
        .status-connected { background: #00ba7c22; color: #00ba7c; border: 1px solid #00ba7c44; }
        .status-disconnected { background: #e4405f22; color: #e4405f; border: 1px solid #e4405f44; }
        .account-card { background: #15191e; border: 1px solid #2f3336; border-radius: 12px; padding: 20px; margin: 16px 0; text-align: left; }
        .home-btn { position: fixed; top: 20px; left: 20px; padding: 10px 20px; background: #1877f2; color: white; text-decoration: none; border-radius: 8px; font-weight: 600; box-shadow: 0 2px 8px rgba(0,0,0,0.3); z-index: 1000; transition: all 0.2s; }
        .home-btn:hover { background: #166fe5; transform: scale(1.02); }
        .back-btn { position: fixed; top: 20px; left: 120px; padding: 10px 20px; background: #f0f0f0; color: #333; text-decoration: none; border-radius: 8px; font-weight: 600; box-shadow: 0 2px 8px rgba(0,0,0,0.3); z-index: 1000; transition: all 0.2s; }
        .back-btn:hover { background: #e0e0e0; transform: scale(1.02); }
        .account-card .username { font-size: 18px; font-weight: 600; }
        .account-card .details { color: #8b98a5; font-size: 14px; margin-top: 4px; }
        .nav-bar { background: #1a1f25; border-bottom: 1px solid #2f3336; padding: 12px 20px; display: flex; justify-content: space-between; align-items: center; }
        .nav-bar a { color: #1877f2; text-decoration: none; font-weight: 500; }
        .nav-bar .brand { font-weight: 700; font-size: 20px; color: #e7e9ea; }
        .alert { padding: 12px 16px; border-radius: 8px; margin-bottom: 16px; font-size: 14px; }
        .alert-success { background: #00ba7c22; border: 1px solid #00ba7c44; color: #00ba7c; }
        .alert-error { background: #e4405f22; border: 1px solid #e4405f44; color: #e4405f; }
        .alert-info { background: #1877f222; border: 1px solid #1877f244; color: #6cb4f7; }
        .steps { text-align: left; margin: 20px 0; }
        .step { display: flex; align-items: flex-start; margin: 12px 0; }
        .step-num { background: #1877f2; color: white; width: 28px; height: 28px; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-weight: 600; font-size: 14px; margin-right: 12px; flex-shrink: 0; }
        .step-text { color: #8b98a5; padding-top: 4px; }
        .divider { height: 1px; background: #2f3336; margin: 24px 0; }
        .footer-links { margin-top: 24px; }
        .footer-links a { color: #536471; text-decoration: none; font-size: 13px; margin: 0 8px; }
        .footer-links a:hover { color: #1877f2; }
    """


# ─── Routes ─────────────────────────────────────────────────────────────

@router.get("/login", response_class=HTMLResponse)
async def login_page(
    request: Request,
    session: Optional[str] = Cookie(None, alias="alita_session"),
):
    """
    Show the login / connect page.
    
    If user already has a session, show their connection status.
    Otherwise, show the "Connect Instagram" button.
    """
    user_id = _get_session_user(session)
    
    # Check if user is already connected
    if user_id:
        tm = get_token_manager()
        stored_token = tm.get_token(user_id)
        if stored_token and not stored_token.is_expired:
            return RedirectResponse("/auth/dashboard")
    
    return HTMLResponse(f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Connect Your Account - Alita</title>
        <style>{_base_style()}</style>
    </head>
    <body>        <a href="/" class="home-btn">🏠 Home</a>        <a href="/social/dashboard" class="back-btn">← Back</a>        <div class="nav-bar">
            <span class="brand">🤖 Alita</span>
            <a href="/">← Back to Home</a>
        </div>
        
        <div class="auth-container">
            <div class="auth-card">
                <div class="logo">📸</div>
                <h1>Connect Your Instagram</h1>
                <h2>Link your Instagram Business Account to Alita</h2>
                
                <div class="steps">
                    <div class="step">
                        <div class="step-num">1</div>
                        <div class="step-text">Click "Connect with Facebook" below</div>
                    </div>
                    <div class="step">
                        <div class="step-num">2</div>
                        <div class="step-text">Log in with your Facebook account that manages your Instagram Business page</div>
                    </div>
                    <div class="step">
                        <div class="step-num">3</div>
                        <div class="step-text">Review and approve the permissions Alita needs</div>
                    </div>
                    <div class="step">
                        <div class="step-num">4</div>
                        <div class="step-text">You're connected! Alita can now manage comments on your posts</div>
                    </div>
                </div>
                
                <div class="divider"></div>
                
                <div class="permissions-list">
                    <h3>🔒 Permissions Alita will request:</h3>
                    <div class="perm-item">
                        <span class="perm-icon">💬</span>
                        <span class="perm-text">Read and reply to comments on your Instagram posts</span>
                    </div>
                    <div class="perm-item">
                        <span class="perm-icon">📨</span>
                        <span class="perm-text">Read and send Instagram Direct Messages</span>
                    </div>
                    <div class="perm-item">
                        <span class="perm-icon">📊</span>
                        <span class="perm-text">View your Instagram Business profile and insights</span>
                    </div>
                    <div class="perm-item">
                        <span class="perm-icon">📄</span>
                        <span class="perm-text">View and manage your Facebook Pages</span>
                    </div>
                </div>
                
                <a href="/auth/start" class="btn btn-primary" style="display: inline-block; margin-top: 16px; font-size: 18px; padding: 16px 40px;">
                    🔗 Connect with Facebook
                </a>
                
                <p style="margin-top: 16px; font-size: 13px; color: #536471;">
                    By connecting, you agree to let Alita access your Instagram Business Account.
                    You can disconnect at any time.
                </p>
                
                <div class="footer-links">
                    <a href="/">Home</a>
                    <a href="/faceless-video">Video Creator</a>
                </div>
            </div>
        </div>
    </body>
    </html>
    """)


@router.get("/start")
async def start_oauth(
    request: Request,
    client_id: Optional[str] = Query(None),
):
    """
    Start the OAuth flow: redirect user to Meta's consent screen.

    Optional ?client_id=<slug> links this OAuth grant to a specific Alita client
    account so the callback can store the token under that client and
    optionally trigger post-analysis for auto style-learning.
    """
    try:
        oauth = get_oauth_client(request)
        tm = get_token_manager()
    except ValueError as e:
        return HTMLResponse(f"""
        <!DOCTYPE html>
        <html><head><style>{_base_style()}</style></head>
        <body><div class="auth-container"><div class="auth-card">
            <div class="logo">⚠️</div>
            <h1>OAuth Not Configured</h1>
            <p>Meta App credentials are not set up yet.</p>
            <div class="alert alert-error">
                <strong>Missing:</strong> Set META_APP_ID and META_APP_SECRET in your .env file.
            </div>
            <a href="/" class="btn btn-secondary">← Back to Home</a>
        </div></div></body></html>
        """, status_code=500)

    # Generate authorization URL with state token
    auth_data = oauth.get_authorization_url()
    state = auth_data["state"]
    url = auth_data["url"]

    # Store state — piggyback client_id onto the existing user_id column so the
    # callback knows which client just connected (no schema changes required).
    tm.store_oauth_state(state, user_id=client_id)

    print(f"🔗 Redirecting user to Meta OAuth consent screen")
    print(f"   State: {state[:16]}…  client_id={client_id or '(agency)'}")
    print(f"   URL: {url[:80]}...")

    return RedirectResponse(url)


@router.get("/callback", response_class=HTMLResponse)
async def oauth_callback(
    request: Request,
    background_tasks: BackgroundTasks,
    code: Optional[str] = Query(None),
    state: Optional[str] = Query(None),
    error: Optional[str] = Query(None),
    error_reason: Optional[str] = Query(None),
    error_description: Optional[str] = Query(None),
):
    """
    Handle the OAuth callback from Meta.
    
    After the user approves (or denies) permissions on Meta's consent screen,
    they are redirected here with either:
    - ?code=AUTHORIZATION_CODE&state=STATE (success)
    - ?error=ERROR&error_reason=REASON (user denied)
    """
    tm = get_token_manager()
    
    # ─── Handle Errors ──────────────────────────────────────────────
    if error:
        error_msg = error_description or error_reason or error
        print(f"❌ OAuth callback error: {error} | {error_reason} | {error_description}")

        # Detect Facebook-specific "feature unavailable" or permission errors
        _lower = (error_msg or "").lower()
        if "feature" in _lower and "unavailable" in _lower:
            extra_guidance = (
                "<p><strong>This usually means:</strong></p>"
                "<ul style='text-align:left; margin: 12px auto; max-width: 420px;'>"
                "<li>The Meta App is in <b>Development Mode</b> and your Facebook "
                "account has not been added as a Tester.</li>"
                "<li>Ask the admin to add your Facebook account as a Tester at "
                "<a href='https://developers.facebook.com' target='_blank' "
                "style='color:#0095f6;'>developers.facebook.com</a> → "
                "App Roles → Testers, or switch the app to <b>Live Mode</b>.</li>"
                "</ul>"
            )
        elif "denied" in _lower or "declined" in _lower:
            extra_guidance = (
                "<p>You declined the permission request. "
                "Alita needs these permissions to post content and "
                "manage your business accounts.</p>"
            )
        else:
            extra_guidance = (
                "<p>If this keeps happening, please contact support "
                "with the error details shown above.</p>"
            )

        return HTMLResponse(f"""
        <!DOCTYPE html>
        <html><head><style>{_base_style()}</style></head>
        <body>
        <div class="nav-bar"><span class="brand">🤖 Alita</span><a href="/">Home</a></div>
        <div class="auth-container"><div class="auth-card">
            <div class="logo">❌</div>
            <h1>Connection Failed</h1>
            <div class="alert alert-error">{error_msg}</div>
            {extra_guidance}
            <a href="/auth/login" class="btn btn-primary" style="margin-top: 16px;">Try Again</a>
            <br><br>
            <a href="/" class="btn btn-secondary">← Back to Home</a>
        </div></div></body></html>
        """)
    
    # ─── Validate State (CSRF Protection) ───────────────────────────
    if not state or not code:
        return HTMLResponse(f"""
        <!DOCTYPE html>
        <html><head><style>{_base_style()}</style></head>
        <body>
        <div class="nav-bar"><span class="brand">🤖 Alita</span><a href="/">Home</a></div>
        <div class="auth-container"><div class="auth-card">
            <div class="logo">⚠️</div>
            <h1>Invalid Request</h1>
            <p>Missing authorization code or state parameter.</p>
            <a href="/auth/login" class="btn btn-primary">Try Again</a>
        </div></div></body></html>
        """, status_code=400)
    
    state_data = tm.verify_and_consume_state(state)
    if not state_data:
        return HTMLResponse(f"""
        <!DOCTYPE html>
        <html><head><style>{_base_style()}</style></head>
        <body>
        <div class="nav-bar"><span class="brand">🤖 Alita</span><a href="/">Home</a></div>
        <div class="auth-container"><div class="auth-card">
            <div class="logo">🔒</div>
            <h1>Security Check Failed</h1>
            <p>The state token is invalid or expired. This could be a CSRF attack, or the link expired.</p>
            <a href="/auth/login" class="btn btn-primary">Start Over</a>
        </div></div></body></html>
        """, status_code=403)
    
    # ─── Exchange Code for Token ────────────────────────────────────
    try:
        oauth = get_oauth_client(request)
        
        # Step 1: Exchange code for short-lived token
        print(f"🔄 Exchanging authorization code for token...")
        short_token = await oauth.exchange_code_for_token(code)
        
        # Step 2: Exchange for long-lived token (60 days)
        print(f"🔄 Exchanging for long-lived token...")
        long_token = await oauth.exchange_for_long_lived_token(short_token.access_token)
        
        # Step 3: Discover Instagram Business Accounts
        print(f"🔍 Discovering Instagram Business Accounts...")
        ig_accounts = await oauth.get_instagram_business_accounts(long_token.access_token)
        fb_pages = await oauth.get_facebook_pages(long_token.access_token)
        
        # Step 4: Create user (use Meta user ID as user_id)
        user_id = long_token.user_id or short_token.user_id or f"user_{secrets.token_hex(8)}"
        
        user = tm.create_user(
            user_id=user_id,
            meta_user_id=long_token.user_id,
        )
        
        # Step 5: Store encrypted token
        ig_id = ig_accounts[0].id if ig_accounts else None
        fb_id = fb_pages[0]["id"] if fb_pages else None
        
        tm.store_token(
            user_id=user_id,
            access_token=long_token.access_token,
            expires_at=long_token.expires_at,
            scopes=long_token.scopes,
            is_long_lived=True,
            instagram_account_id=ig_id,
            facebook_page_id=fb_id,
        )
        
        # Step 6: Map Instagram accounts for webhook routing
        for ig in ig_accounts:
            tm.map_instagram_account(
                instagram_account_id=ig.id,
                user_id=user_id,
                instagram_username=ig.username,
                facebook_page_id=ig.facebook_page_id,
                facebook_page_name=ig.facebook_page_name,
            )
        
        # Step 7: Create session
        session_id = tm.create_session(user_id)

        # ─── Client-specific handling ────────────────────────────────
        # client_id was passed through the OAuth state (stored in user_id column)
        client_id = state_data.get("user_id")  # repurposed field

        if client_id:
            # Persist the Meta user_id → client_id mapping in a connections file
            # so the rest of the app knows this client has IG connected
            import json as _json
            _conn_dir = os.path.join("storage", "connections")
            os.makedirs(_conn_dir, exist_ok=True)
            _conn_path = os.path.join(_conn_dir, f"{client_id}.json")
            _existing = {}
            if os.path.exists(_conn_path):
                try:
                    with open(_conn_path) as _f:
                        _existing = _json.load(_f)
                except Exception:
                    pass
            _existing["meta_user_id"] = user_id
            _existing["ig_account_id"] = ig_id
            _existing["ig_username"] = ig_accounts[0].username if ig_accounts else None
            _existing["connected_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            with open(_conn_path, "w") as _f:
                _json.dump(_existing, _f, indent=2)

            # ── Also persist to the main PostgreSQL DB so tokens survive Railway redeploys ──
            try:
                import uuid as _uuid
                from database.db import SessionLocal as _SL
                from database.models import ClientProfile as _CP, MetaOAuthToken as _MOT
                from api.token_manager import encrypt_value as _enc_val
                from datetime import datetime as _dt

                _db = _SL()
                try:
                    _profile = _db.query(_CP).filter(_CP.client_id == client_id).first()
                    if _profile:
                        # Update connection columns on the profile
                        _profile.meta_user_id          = user_id
                        _profile.meta_ig_account_id    = ig_id
                        _profile.meta_ig_username      = ig_accounts[0].username if ig_accounts else None
                        _profile.meta_facebook_page_id = fb_id
                        _profile.meta_connected_at     = _dt.utcnow()

                        # Upsert the encrypted token row
                        _tok_row = _db.query(_MOT).filter(
                            _MOT.client_profile_id == _profile.id
                        ).first()
                        _enc = _enc_val(long_token.access_token)
                        if _tok_row:
                            _tok_row.meta_user_id     = user_id
                            _tok_row.access_token_enc = _enc
                            _tok_row.token_type       = long_token.token_type or "bearer"
                            _tok_row.scopes           = ",".join(long_token.scopes) if long_token.scopes else ""
                            _tok_row.is_long_lived    = True
                            _tok_row.expires_at       = str(long_token.expires_at) if long_token.expires_at else None
                            _tok_row.ig_account_id    = ig_id
                            _tok_row.facebook_page_id = fb_id
                            _tok_row.updated_at       = _dt.utcnow()
                        else:
                            _tok_row = _MOT(
                                id=str(_uuid.uuid4()),
                                client_profile_id=_profile.id,
                                meta_user_id=user_id,
                                access_token_enc=_enc,
                                token_type=long_token.token_type or "bearer",
                                scopes=",".join(long_token.scopes) if long_token.scopes else "",
                                is_long_lived=True,
                                expires_at=str(long_token.expires_at) if long_token.expires_at else None,
                                ig_account_id=ig_id,
                                facebook_page_id=fb_id,
                            )
                            _db.add(_tok_row)
                        _db.commit()
                        print(f"[oauth] Saved Meta token to main DB for client_id={client_id}")
                    else:
                        print(f"[oauth] No ClientProfile for client_id={client_id} — token not saved to main DB")
                finally:
                    _db.close()
            except Exception as _dbe:
                print(f"[oauth] WARNING: Could not save token to main DB: {_dbe}")

            # ── Notify calendar agent and regenerate calendar immediately ──────
            try:
                from utils.platform_events import on_platform_connected
                if ig_id:
                    background_tasks.add_task(on_platform_connected, client_id, "instagram")
                if fb_id:
                    background_tasks.add_task(on_platform_connected, client_id, "facebook")
                print(f"[oauth] Queued calendar regeneration for client={client_id} (platforms: "
                      f"{'instagram ' if ig_id else ''}{'facebook' if fb_id else ''})")
            except Exception as _pe:
                print(f"[oauth] WARNING: Could not queue platform event: {_pe}")

            # Fire auto style-learn if the client opted in
            try:
                from utils.style_learner import learn_from_instagram, _load_prefs
                _prefs = _load_prefs(client_id)
                if _prefs.get("auto_learn", False) and ig_id and long_token.access_token:
                    # Mark as running so UI shows spinner
                    _prefs["auto_learn_status"] = "running"
                    from utils.style_learner import _save_prefs
                    _save_prefs(client_id, _prefs)
                    background_tasks.add_task(
                        learn_from_instagram,
                        client_id,
                        long_token.access_token,
                        ig_id,
                    )
                    print(f"[oauth] Queued auto style-learn for client={client_id}")
            except Exception as _e:
                print(f"[oauth] Could not queue style-learn: {_e}")

        # Build success HTML
        accounts_html = ""
        for ig in ig_accounts:
            followers = f"{ig.followers_count:,}" if ig.followers_count else "N/A"
            accounts_html += f"""
            <div class="account-card">
                <div class="username">📸 @{ig.username}</div>
                <div class="details">{ig.name} • {followers} followers • {ig.media_count or 0} posts</div>
                <div class="details" style="margin-top: 4px;">Facebook Page: {ig.facebook_page_name or 'N/A'}</div>
            </div>
            """
        
        if not accounts_html:
            accounts_html = '<div class="alert alert-info">No Instagram Business Accounts found. Make sure your Instagram is connected to a Facebook Page as a Business account.</div>'
        
        scopes_html = ""
        for scope in long_token.scopes[:10]:
            scopes_html += f'<div class="perm-item"><span class="perm-icon">✅</span><span class="perm-text">{scope}</span></div>'
        
        expiry_days = int((long_token.expires_at - time.time()) / 86400) if long_token.expires_at else 60
        
        # ── Build success page using shared layout ──────────────────────
        _cid = client_id or ""
        _success_css = """
.success-card{border:1.5px solid #e4e6eb;border-radius:12px;padding:28px 32px;background:#fff;margin-bottom:20px}
.success-card h2{font-size:1.1rem;margin:0 0 6px}
.success-card .sub{font-size:.87rem;color:#90949c;margin-bottom:16px}
.account-card-sm{display:flex;align-items:center;gap:14px;background:#f8f9fa;border-radius:10px;padding:14px 18px;margin-bottom:10px}
.account-card-sm .icon{font-size:1.6rem;flex-shrink:0}
.account-card-sm .info{flex:1}
.account-card-sm .name{font-weight:700;font-size:.95rem;color:#1c1e21}
.account-card-sm .meta{font-size:.82rem;color:#90949c;margin-top:2px}
.perm-item-sm{display:inline-block;background:#e8f5e9;color:#2e7d32;padding:4px 12px;border-radius:12px;font-size:.8rem;font-weight:600;margin:3px 4px 3px 0}
.next-step{display:flex;align-items:flex-start;gap:12px;margin-bottom:14px}
.next-step .check{color:#27ae60;font-weight:700;font-size:1.1rem}
.next-step .text{font-size:.9rem;color:#444;line-height:1.5}
"""
        _success_body = f"""
<div style="margin-bottom:24px">
  <h1 style="font-size:1.4rem;font-weight:700;color:#1c1e21;margin:0 0 6px">&#x1F389; Successfully Connected!</h1>
  <p style="color:#90949c;font-size:.9rem;margin:0">Your Instagram Business Account is now linked to Alita.</p>
</div>

<div class="success-card">
  <div style="background:#e8f5e9;border-left:4px solid #27ae60;padding:12px 16px;border-radius:0 8px 8px 0;font-size:.88rem;color:#2e7d32;margin-bottom:20px">
    &#x2705; OAuth token obtained and stored securely (encrypted). Token expires in {expiry_days} days. Alita will auto-refresh before expiry.
  </div>
  <h2>Connected Accounts</h2>
  {accounts_html}
</div>

<div class="success-card">
  <h2>Granted Permissions ({len(long_token.scopes)})</h2>
  <div style="margin-top:10px">
    {scopes_html}
  </div>
</div>

<div class="success-card">
  <h2>What's Next?</h2>
  <div style="margin-top:14px">
    <div class="next-step"><span class="check">&#x2713;</span><span class="text">Alita will automatically respond to Instagram comments using AI</span></div>
    <div class="next-step"><span class="check">&#x2713;</span><span class="text">DMs will be handled by the engagement agent in your brand&rsquo;s voice</span></div>
    <div class="next-step"><span class="check">&#x2713;</span><span class="text">You can post content to Instagram and Facebook directly</span></div>
  </div>
</div>

<div style="display:flex;gap:12px;margin-top:20px">
  <a href="/connect/dashboard" class="btn-primary" style="text-decoration:none;display:inline-block;padding:12px 24px;border-radius:8px;font-weight:600;font-size:.9rem">Go to Dashboard &#x2192;</a>
  <a href="/settings" class="btn-secondary" style="text-decoration:none;display:inline-block;padding:12px 24px;border-radius:8px;font-weight:600;font-size:.9rem">&#x2190; Settings</a>
</div>
"""
        from utils.shared_layout import build_page
        _user_name = ""
        _biz_name  = ""
        _auth_user_id = None  # used to set alita_token JWT below
        if client_id:
            try:
                from database.db import SessionLocal as _SL
                from database.models import ClientProfile as _CP
                _dbl = _SL()
                _p = _dbl.query(_CP).filter(_CP.client_id == client_id).first()
                if _p:
                    _biz_name = _p.business_name or ""
                    if _p.user_id:
                        from database.models import User as _U
                        _u = _dbl.query(_U).filter(_U.id == _p.user_id).first()
                        if _u:
                            _user_name = _u.full_name or ""
                            _auth_user_id = _u.id
                _dbl.close()
            except Exception:
                pass

        # If the user was already logged in, prefer their existing session user
        if not _auth_user_id:
            try:
                from api.auth_routes import get_current_user as _gcu
                from database.db import SessionLocal as _SL2
                _dbl2 = _SL2()
                _req_user = _gcu(request, _dbl2)
                if _req_user:
                    _auth_user_id = _req_user.id
                _dbl2.close()
            except Exception:
                pass

        response = HTMLResponse(build_page(
            title="Connected!",
            active_nav="connect",
            body_content=_success_body,
            extra_css=_success_css,
            user_name=_user_name,
            business_name=_biz_name,
        ))
        
        # Set session cookie (legacy)
        response.set_cookie(
            key="alita_session",
            value=session_id,
            httponly=True,
            samesite="lax",
            max_age=86400,  # 24 hours
        )

        # Set JWT cookie so dashboard/settings links work immediately after OAuth
        if _auth_user_id:
            try:
                from api.auth_routes import create_access_token as _cat
                _jwt = _cat(_auth_user_id)
                is_prod = os.getenv("ENV", "development") == "production"
                response.set_cookie(
                    key="alita_token",
                    value=_jwt,
                    httponly=True,
                    samesite="lax",
                    max_age=60 * 60,  # 1 hour (matches JWT lifetime)
                    secure=is_prod,
                )
                print(f"[oauth] Set alita_token JWT for user_id={_auth_user_id}")
            except Exception as _je:
                print(f"[oauth] WARNING: Could not set alita_token JWT: {_je}")
        
        print(f"✅ OAuth flow complete for user {user_id}")
        print(f"   Connected {len(ig_accounts)} Instagram account(s)")
        print(f"   Token expires in {expiry_days} days")
        
        return response
        
    except Exception as e:
        print(f"❌ OAuth callback error: {e}")
        import traceback
        traceback.print_exc()
        
        return HTMLResponse(f"""
        <!DOCTYPE html>
        <html><head><style>{_base_style()}</style></head>
        <body>
        <div class="nav-bar"><span class="brand">🤖 Alita</span><a href="/">Home</a></div>
        <div class="auth-container"><div class="auth-card">
            <div class="logo">❌</div>
            <h1>Connection Failed</h1>
            <div class="alert alert-error">
                <strong>Error:</strong> {str(e)}
            </div>
            <p>Please try again. If this persists, check your Meta App configuration.</p>
            <a href="/auth/login" class="btn btn-primary" style="margin-top: 16px;">Try Again</a>
            <br><br>
            <a href="/" class="btn btn-secondary">← Back to Home</a>
        </div></div></body></html>
        """, status_code=500)


@router.get("/dashboard", response_class=HTMLResponse)
async def auth_dashboard(
    request: Request,
    session: Optional[str] = Cookie(None, alias="alita_session"),
):
    """
    Legacy OAuth dashboard — redirects to the main app's Connect page.
    Kept alive so old bookmarks / links still work.
    """
    # Always redirect to the main app's social accounts page
    return RedirectResponse("/connect/dashboard", status_code=302)


@router.get("/dashboard-legacy", response_class=HTMLResponse)
async def auth_dashboard_legacy(
    request: Request,
    session: Optional[str] = Cookie(None, alias="alita_session"),
):
    """
    Legacy detailed OAuth account view (kept for debugging).
    """
    user_id = _get_session_user(session)

    if not user_id:
        return RedirectResponse("/auth/login")
    
    tm = get_token_manager()
    user = tm.get_user(user_id)
    stored_token = tm.get_token(user_id)
    
    if not user or not stored_token:
        return RedirectResponse("/auth/login")
    
    # Get connection details
    is_expired = stored_token.is_expired
    status_class = "status-disconnected" if is_expired else "status-connected"
    status_text = "Expired" if is_expired else "Connected"
    
    expiry_text = "Unknown"
    if stored_token.expires_at:
        days_left = int((stored_token.expires_at - time.time()) / 86400)
        if days_left > 0:
            expiry_text = f"{days_left} days remaining"
        else:
            expiry_text = "Expired"
    
    scopes_count = len(stored_token.scope_list)
    
    # Get linked accounts
    conn = tm._get_conn()
    try:
        accounts = conn.execute(
            "SELECT * FROM account_map WHERE user_id = ?", (user_id,)
        ).fetchall()
    finally:
        conn.close()
    
    accounts_html = ""
    for acc in accounts:
        accounts_html += f"""
        <div class="account-card">
            <div style="display: flex; justify-content: space-between; align-items: center;">
                <div>
                    <div class="username">📸 @{acc['instagram_username'] or acc['instagram_account_id']}</div>
                    <div class="details">Facebook Page: {acc['facebook_page_name'] or 'N/A'}</div>
                    <div class="details">Connected: {acc['connected_at'] or 'N/A'}</div>
                </div>
                <span class="status-badge {status_class}">{status_text}</span>
            </div>
        </div>
        """
    
    if not accounts_html:
        accounts_html = '<div class="alert alert-info">No accounts connected yet.</div>'
    
    # Permission badges
    perm_html = ""
    key_permissions = {
        "instagram_manage_comments": "💬 Manage Comments",
        "instagram_manage_messages": "📨 Manage Messages",
        "pages_manage_posts": "📝 Manage Posts",
        "instagram_basic": "📊 Basic Access",
        "pages_show_list": "📄 View Pages",
    }
    for scope in stored_token.scope_list:
        display = key_permissions.get(scope, scope)
        perm_html += f'<span style="display: inline-block; background: #1877f222; color: #6cb4f7; padding: 4px 10px; border-radius: 8px; font-size: 12px; margin: 2px;">{display}</span> '
    
    return HTMLResponse(f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Account Dashboard - Alita</title>
        <style>{_base_style()}</style>
    </head>
    <body>
        <div class="nav-bar">
            <span class="brand">🤖 Alita</span>
            <div>
                <a href="/" style="margin-right: 16px;">Home</a>
                <a href="/auth/logout" style="color: #e4405f;">Logout</a>
            </div>
        </div>
        
        <div class="auth-container">
            <div class="auth-card" style="text-align: left;">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 24px;">
                    <div>
                        <h1 style="font-size: 24px;">Account Dashboard</h1>
                        <p style="color: #8b98a5; margin: 0;">User: {user_id}</p>
                    </div>
                    <span class="status-badge {status_class}" style="font-size: 14px; padding: 6px 16px;">{status_text}</span>
                </div>
                
                <div class="alert alert-{'success' if not is_expired else 'error'}">
                    <strong>Token Status:</strong> {'✅ Active' if not is_expired else '❌ Expired — reconnect required'}<br>
                    <strong>Type:</strong> {'Long-lived (60-day)' if stored_token.is_long_lived else 'Short-lived'}<br>
                    <strong>Expiry:</strong> {expiry_text}<br>
                    <strong>Permissions:</strong> {scopes_count} granted
                </div>
                
                <h3 style="margin: 20px 0 8px;">Connected Accounts</h3>
                {accounts_html}
                
                <h3 style="margin: 20px 0 8px;">Permissions</h3>
                <div style="margin-bottom: 20px;">{perm_html}</div>
                
                <div class="divider"></div>
                
                <div style="display: flex; gap: 12px; flex-wrap: wrap;">
                    {'<a href="/auth/refresh" class="btn btn-primary">🔄 Refresh Token</a>' if not is_expired else '<a href="/auth/start" class="btn btn-primary">🔗 Reconnect</a>'}
                    <a href="/auth/test-api" class="btn btn-success">🧪 Test API Access</a>
                    <form action="/auth/disconnect" method="post" style="display: inline;" 
                          onsubmit="return confirm('Are you sure? This will disconnect your Instagram account.')">
                        <button type="submit" class="btn btn-danger">🔌 Disconnect Account</button>
                    </form>
                </div>
            </div>
        </div>
    </body>
    </html>
    """)


@router.get("/status")
async def auth_status(
    session: Optional[str] = Cookie(None, alias="alita_session"),
):
    """
    API endpoint: Check current authentication status.
    Returns JSON with connection details.
    """
    user_id = _get_session_user(session)
    
    if not user_id:
        return JSONResponse({
            "authenticated": False,
            "message": "No active session",
        })
    
    tm = get_token_manager()
    stored_token = tm.get_token(user_id)
    
    if not stored_token:
        return JSONResponse({
            "authenticated": True,
            "connected": False,
            "user_id": user_id,
            "message": "User exists but no Instagram token",
        })
    
    return JSONResponse({
        "authenticated": True,
        "connected": True,
        "user_id": user_id,
        "token_valid": not stored_token.is_expired,
        "is_long_lived": stored_token.is_long_lived,
        "expires_at": stored_token.expires_at,
        "scopes": stored_token.scope_list,
        "instagram_account_id": stored_token.instagram_account_id,
    })


@router.post("/disconnect")
async def disconnect_account(
    request: Request,
    session: Optional[str] = Cookie(None, alias="alita_session"),
):
    """
    Disconnect the user's Instagram account.
    Revokes tokens on Meta's side and removes local storage.
    """
    user_id = _get_session_user(session)
    
    if not user_id:
        return RedirectResponse("/auth/login")
    
    tm = get_token_manager()
    stored_token = tm.get_token(user_id)
    
    # Revoke token on Meta's side
    if stored_token:
        try:
            oauth = get_oauth_client()
            await oauth.revoke_token(stored_token.access_token)
        except Exception as e:
            print(f"⚠️  Token revocation on Meta failed: {e}")
    
    # Remove local tokens and mappings
    tm.delete_tokens(user_id)
    
    print(f"✅ Account disconnected for user {user_id}")
    
    return RedirectResponse("/auth/login")


@router.get("/refresh")
async def refresh_token(
    session: Optional[str] = Cookie(None, alias="alita_session"),
):
    """Refresh the user's long-lived token."""
    user_id = _get_session_user(session)
    
    if not user_id:
        return RedirectResponse("/auth/login")
    
    tm = get_token_manager()
    stored_token = tm.get_token(user_id)
    
    if not stored_token:
        return RedirectResponse("/auth/login")
    
    try:
        oauth = get_oauth_client()
        new_token = await oauth.refresh_long_lived_token(stored_token.access_token)
        
        tm.store_token(
            user_id=user_id,
            access_token=new_token.access_token,
            expires_at=new_token.expires_at,
            scopes=new_token.scopes,
            is_long_lived=True,
            instagram_account_id=stored_token.instagram_account_id,
            facebook_page_id=stored_token.facebook_page_id,
        )
        
        return RedirectResponse("/auth/dashboard")
    except Exception as e:
        print(f"❌ Token refresh failed: {e}")
        return RedirectResponse("/auth/start")


@router.get("/test-api", response_class=HTMLResponse)
async def test_api_access(
    session: Optional[str] = Cookie(None, alias="alita_session"),
):
    """
    Test API access with the user's token.
    Calls Meta API endpoints to verify everything works.
    """
    user_id = _get_session_user(session)
    
    if not user_id:
        return RedirectResponse("/auth/login")
    
    tm = get_token_manager()
    token_str = tm.get_valid_token(user_id)
    
    if not token_str:
        return RedirectResponse("/auth/start")
    
    results = []
    
    try:
        oauth = get_oauth_client()
        
        # Test 1: Debug token
        debug_info = await oauth.debug_token(token_str)
        results.append({
            "test": "Token Validation",
            "passed": debug_info.get("is_valid", False),
            "details": f"Valid: {debug_info.get('is_valid')}, Scopes: {len(debug_info.get('scopes', []))}",
        })
        
        # Test 2: Get Facebook Pages
        pages = await oauth.get_facebook_pages(token_str)
        results.append({
            "test": "Facebook Pages",
            "passed": len(pages) > 0,
            "details": f"Found {len(pages)} page(s)" + (f": {pages[0]['name']}" if pages else ""),
        })
        
        # Test 3: Get Instagram Business Accounts
        ig_accounts = await oauth.get_instagram_business_accounts(token_str)
        results.append({
            "test": "Instagram Business Accounts",
            "passed": len(ig_accounts) > 0,
            "details": f"Found {len(ig_accounts)} account(s)" + (f": @{ig_accounts[0].username}" if ig_accounts else ""),
        })
        
        # Test 4: Get recent posts (if IG account exists)
        if ig_accounts:
            try:
                async with __import__('httpx').AsyncClient(timeout=15.0) as client:
                    resp = await client.get(
                        f"https://graph.facebook.com/v22.0/{ig_accounts[0].id}/media",
                        params={"access_token": token_str, "fields": "id,caption,timestamp", "limit": 3},
                    )
                    posts = resp.json().get("data", [])
                    results.append({
                        "test": "Instagram Posts Access",
                        "passed": len(posts) > 0,
                        "details": f"Found {len(posts)} recent post(s)",
                    })
            except Exception as e:
                results.append({"test": "Instagram Posts Access", "passed": False, "details": str(e)})
        
    except Exception as e:
        results.append({"test": "API Connection", "passed": False, "details": str(e)})
    
    # Build results HTML
    results_html = ""
    for r in results:
        icon = "✅" if r["passed"] else "❌"
        color = "#00ba7c" if r["passed"] else "#e4405f"
        results_html += f"""
        <div style="display: flex; align-items: center; padding: 12px 0; border-bottom: 1px solid #2f3336;">
            <span style="font-size: 20px; margin-right: 12px;">{icon}</span>
            <div>
                <div style="font-weight: 600; color: {color};">{r['test']}</div>
                <div style="color: #8b98a5; font-size: 13px;">{r['details']}</div>
            </div>
        </div>
        """
    
    all_passed = all(r["passed"] for r in results)
    
    return HTMLResponse(f"""
    <!DOCTYPE html>
    <html><head><style>{_base_style()}</style></head>
    <body>
    <div class="nav-bar"><span class="brand">🤖 Alita</span><a href="/auth/dashboard">← Dashboard</a></div>
    <div class="auth-container"><div class="auth-card" style="text-align: left;">
        <h1>{'✅ All Tests Passed!' if all_passed else '⚠️ Some Tests Failed'}</h1>
        <p style="color: #8b98a5;">Testing your Meta API access with your stored OAuth token.</p>
        <div style="margin: 20px 0;">{results_html}</div>
        <a href="/auth/dashboard" class="btn btn-secondary">← Back to Dashboard</a>
    </div></div></body></html>
    """)


@router.get("/logout")
async def logout(
    response: Response,
    session: Optional[str] = Cookie(None, alias="alita_session"),
):
    """Log out (clear session, keep token)."""
    if session:
        tm = get_token_manager()
        tm.delete_session(session)
    
    resp = RedirectResponse("/auth/login")
    resp.delete_cookie("alita_session")
    return resp
