"""
Client Account Connection Dashboard
Allows clients to self-service connect their Twitter, TikTok, LinkedIn, and YouTube accounts
"""

from fastapi import APIRouter, BackgroundTasks, Query, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
import os
import json
import httpx
from datetime import datetime
from typing import Optional

router = APIRouter(prefix="/connect", tags=["Client Connections"])

# Late API configuration
LATE_API_KEY = os.getenv("LATE_API_KEY", "")
LATE_API_BASE = "https://getlate.dev/api/v1"
LATE_PROFILE_ID = "697b0829f4dfa2e3e69a7523"  # Late API workspace profile ID (used for /connect OAuth flows)


def _get_late_profile_for_client(client_id: str) -> str:
    """Return the Late API workspace profile ID used to initiate OAuth connections.

    NOTE: This must always return the *workspace* profile ID (e.g. 697b0829...),
    NOT an individual social-account ID.  Social account IDs (stored per-platform
    in the connections JSON) are only used as `accountId` when posting — they are
    NOT valid values for the `profileId` query-param on /connect/{platform}.
    """
    return LATE_PROFILE_ID

# Platforms available through Late API connect
LATE_PLATFORMS = ["twitter", "tiktok", "linkedin", "threads", "youtube"]

# Simple file-based storage for now (upgrade to database later)
CONNECTIONS_FILE = "storage/client_connections.json"

# Per-client Meta OAuth connections (OAuth flow writes these)
CLIENT_META_CONNECTIONS_DIR = os.path.join("storage", "connections")


def _get_meta_user_id_for_client(client_id: str) -> Optional[str]:
    """Return the Meta (Facebook) user_id for a given Alita client_id.

    Lookup order:
    1. storage/connections/{client_id}.json  (fast, local, written by OAuth callback)
    2. Main PostgreSQL database — ClientProfile.meta_user_id  (survives Railway redeploys)
    3. Scan alita_oauth.db directly  (legacy fallback for old installs)

    Auto-writes the bridge file if found via fallbacks so future calls are fast.
    """
    conn_path = os.path.join(CLIENT_META_CONNECTIONS_DIR, f"{client_id}.json")
    if os.path.exists(conn_path):
        try:
            with open(conn_path) as _f:
                data = json.load(_f)
            meta_uid = data.get("meta_user_id")
            if meta_uid:
                return meta_uid
        except Exception:
            pass

    # ── Fallback 1: main PostgreSQL DB (ClientProfile.meta_user_id) ────────
    try:
        from database.db import SessionLocal as _SL
        from database.models import ClientProfile as _CP
        _db = _SL()
        try:
            _profile = _db.query(_CP).filter(_CP.client_id == client_id).first()
            if _profile and _profile.meta_user_id:
                meta_uid = _profile.meta_user_id
                # Auto-write bridge file for speed on next call
                try:
                    os.makedirs(CLIENT_META_CONNECTIONS_DIR, exist_ok=True)
                    _data = {
                        "meta_user_id": meta_uid,
                        "ig_account_id": _profile.meta_ig_account_id,
                        "ig_username": _profile.meta_ig_username,
                        "connected_at": str(_profile.meta_connected_at or "auto"),
                    }
                    with open(conn_path, "w") as _wf:
                        json.dump(_data, _wf, indent=2)
                    print(f"[connections] Bridge file written from main DB for {client_id} → meta_uid={meta_uid}")
                except Exception:
                    pass
                return meta_uid
        finally:
            _db.close()
    except Exception as _dbe:
        print(f"[connections] Main DB lookup failed: {_dbe}")

    # ── Fallback 2: read alita_oauth.db directly ──────────────────────────
    # If the bridge file doesn't exist we look for any active token row and
    # treat its user_id as the meta_user_id.  Works for single-client setups.
    try:
        import sqlite3 as _sqlite3
        from pathlib import Path as _Path
        _db = str(_Path(__file__).parent.parent / "database" / "alita_oauth.db")
        if os.path.exists(_db):
            _c = _sqlite3.connect(_db)
            _c.row_factory = _sqlite3.Row
            row = _c.execute(
                "SELECT ut.user_id, am.instagram_account_id, am.instagram_username "
                "FROM user_tokens ut "
                "LEFT JOIN account_map am ON am.user_id = ut.user_id "
                "ORDER BY ut.updated_at DESC LIMIT 1"
            ).fetchone()
            _c.close()
            if row and row["user_id"]:
                meta_uid = row["user_id"]
                # Auto-write the bridge file so future calls are fast
                try:
                    os.makedirs(CLIENT_META_CONNECTIONS_DIR, exist_ok=True)
                    _data = {
                        "meta_user_id": meta_uid,
                        "ig_account_id": row["instagram_account_id"],
                        "ig_username": row["instagram_username"],
                        "connected_at": "auto-detected",
                    }
                    with open(conn_path, "w") as _wf:
                        json.dump(_data, _wf, indent=2)
                    print(f"[connections] Auto-created bridge file for {client_id} → meta_uid={meta_uid}")
                except Exception as _we:
                    print(f"[connections] Could not write bridge file: {_we}")
                return meta_uid
    except Exception as _e:
        print(f"[connections] Fallback lookup failed: {_e}")

    return None


def _has_meta_token_for_client(client_id: str) -> bool:
    """
    Return True if the client has a valid Meta OAuth token stored anywhere.
    Checks (in order):
    1. MetaOAuthToken row in the main PostgreSQL DB   (survives redeploys)
    2. TokenManager get_token() against alita_oauth.db (legacy SQLite)
    """
    # ── Primary: main PostgreSQL MetaOAuthToken table ──────────────────────
    try:
        from database.db import SessionLocal as _SL
        from database.models import ClientProfile as _CP, MetaOAuthToken as _MOT
        _db = _SL()
        try:
            _profile = _db.query(_CP).filter(_CP.client_id == client_id).first()
            if _profile:
                _tok = _db.query(_MOT).filter(
                    _MOT.client_profile_id == _profile.id
                ).first()
                if _tok and _tok.access_token_enc:
                    return True
        finally:
            _db.close()
    except Exception as _e:
        print(f"[connections] MetaOAuthToken DB check failed: {_e}")

    # ── Fallback: alita_oauth.db (legacy) ──────────────────────────────────
    meta_uid = _get_meta_user_id_for_client(client_id)
    if meta_uid:
        try:
            from api.token_manager import TokenManager
            tm = TokenManager()
            return tm.get_token(meta_uid) is not None
        except Exception:
            pass

    return False


def load_connections():
    """Load client connections from file + DB + env vars."""
    connections = {}

    # ── 1. Load from JSON file (may not exist after redeploy) ──
    try:
        if os.path.exists(CONNECTIONS_FILE):
            with open(CONNECTIONS_FILE, 'r') as f:
                connections = json.load(f)
    except Exception:
        pass

    # ── 2. Overlay with DB rows (survives redeploys) ──
    try:
        from database.db import SessionLocal
        from database.models import PlatformConnection
        _db = SessionLocal()
        try:
            rows = _db.query(PlatformConnection).all()
            for row in rows:
                cid = row.client_id
                if cid not in connections:
                    connections[cid] = {}
                connections[cid][row.platform] = {
                    "profile_id": row.account_id or "",
                    "username": row.username or "",
                    "connected_at": str(row.connected_at or ""),
                    "status": "active",
                }
        finally:
            _db.close()
    except Exception:
        pass  # table may not exist yet

    # ── 3. Env-var fallback (LATE_PROFILE_{PLATFORM}_{client_id}) ──
    # These survive Railway redeploys because they are service variables.
    # Scan all known env vars and reconstruct connections if missing.
    _LATE_PLATFORMS = ["twitter", "tiktok", "linkedin", "threads", "youtube"]
    for key, val in os.environ.items():
        key_upper = key.upper()
        if not key_upper.startswith("LATE_PROFILE_"):
            continue
        # Pattern: LATE_PROFILE_{PLATFORM}_{client_id}
        rest = key[len("LATE_PROFILE_"):]
        for _p in _LATE_PLATFORMS:
            prefix = _p.upper() + "_"
            if rest.upper().startswith(prefix):
                cid = rest[len(prefix):]
                if cid and val:
                    if cid not in connections:
                        connections[cid] = {}
                    if _p not in connections[cid]:
                        connections[cid][_p] = {
                            "profile_id": val,
                            "username": "",
                            "connected_at": "env-var",
                            "status": "active",
                        }
                break

    return connections


def save_connections(connections):
    """Save client connections to both file and DB."""
    # ── File (fast local cache) ──
    try:
        os.makedirs(os.path.dirname(CONNECTIONS_FILE), exist_ok=True)
        with open(CONNECTIONS_FILE, 'w') as f:
            json.dump(connections, indent=2, fp=f)
    except Exception:
        pass

    # ── DB (persistent across redeploys) ──
    try:
        import uuid as _uuid
        from database.db import SessionLocal
        from database.models import PlatformConnection
        _db = SessionLocal()
        try:
            for cid, plats in connections.items():
                for platform, details in plats.items():
                    existing = (
                        _db.query(PlatformConnection)
                        .filter(
                            PlatformConnection.client_id == cid,
                            PlatformConnection.platform == platform,
                        )
                        .first()
                    )
                    if existing:
                        existing.account_id = details.get("profile_id", existing.account_id)
                        existing.username = details.get("username", existing.username)
                    else:
                        _db.add(PlatformConnection(
                            id=str(_uuid.uuid4()),
                            client_id=cid,
                            platform=platform,
                            account_id=details.get("profile_id", ""),
                            username=details.get("username", ""),
                        ))
            _db.commit()
        finally:
            _db.close()
    except Exception as exc:
        print(f"[connections] DB save warning: {exc}")


def add_connection(client_id: str, platform: str, profile_id: str, username: str):
    """Add a new connection"""
    connections = load_connections()
    
    if client_id not in connections:
        connections[client_id] = {}
    
    connections[client_id][platform] = {
        "profile_id": profile_id,
        "username": username,
        "connected_at": datetime.now().isoformat(),
        "status": "active"
    }
    
    save_connections(connections)
    
    # Also append to .env format file for easy copying
    with open("storage/new_connections_env.txt", "a") as f:
        f.write(f"LATE_PROFILE_{platform.upper()}_{client_id}={profile_id}  # @{username} - {datetime.now().strftime('%Y-%m-%d')}\n")


def remove_connection(client_id: str, platform: str) -> bool:
    """Remove a Late API platform connection from the JSON store and DB."""
    removed = False
    connections = load_connections()
    if client_id in connections and platform in connections[client_id]:
        del connections[client_id][platform]
        save_connections(connections)
        removed = True

    # Also remove from DB
    try:
        from database.db import SessionLocal
        from database.models import PlatformConnection
        _db = SessionLocal()
        try:
            row = (
                _db.query(PlatformConnection)
                .filter(
                    PlatformConnection.client_id == client_id,
                    PlatformConnection.platform == platform,
                )
                .first()
            )
            if row:
                _db.delete(row)
                _db.commit()
                removed = True
        finally:
            _db.close()
    except Exception:
        pass
    return removed


# ── Platform button config ────────────────────────────────────────────────────
_PLATFORM_BTN_CONFIG = {
    "twitter":  {"icon": "fab fa-x-twitter",  "name": "Twitter/X",  "style": "background: #1DA1F2;"},
    "tiktok":   {"icon": "fab fa-tiktok",      "name": "TikTok",     "style": "background: #000000;"},
    "linkedin": {"icon": "fab fa-linkedin",    "name": "LinkedIn",   "style": "background: #0A66C2;"},
    "threads":  {"icon": "fab fa-threads",     "name": "Threads",    "style": "background: linear-gradient(135deg, #833ab4, #fd1d1d, #fcb045);"},
    "youtube":  {"icon": "fab fa-youtube",     "name": "YouTube",    "style": "background: #FF0000;"},
}

def _build_late_buttons(
    client_id: str,
    allowed: list,
    tier: str,
    upgrade_hints: dict,
) -> list[str]:
    """Return HTML strings for each Late API platform — unlocked or locked."""
    from utils.plan_limits import PLAN_DISPLAY_NAMES
    buttons = []
    for platform in ["twitter", "tiktok", "linkedin", "threads", "youtube"]:
        cfg = _PLATFORM_BTN_CONFIG[platform]
        icon_tag = f'<i class="{cfg["icon"]}" style="margin-right:6px;"></i>'
        if platform in allowed:
            # Unlocked — show normal connect button
            buttons.append(
                f'<a href="/connect/late/{platform}?client_id={client_id}" '
                f'class="connect-btn" style="{cfg["style"]}">'
                f'{icon_tag}{cfg["name"]}</a>'
            )
        else:
            # Locked — show upgrade CTA
            hint_tier, hint_extra = upgrade_hints.get(platform, ("a higher", ""))
            tier_name = PLAN_DISPLAY_NAMES.get(hint_tier.lower(), hint_tier)
            buttons.append(
                f'<div class="connect-btn" style="background:#777;cursor:default;opacity:0.7;" title="Upgrade to unlock">'
                f'<i class="fas fa-lock" style="margin-right:6px;"></i>{icon_tag}{cfg["name"]}'
                f'<span style="display:block;font-size:11px;margin-top:4px;">'
                f'Requires {tier_name}{hint_extra} — '
                f'<a href="/billing" style="color:#ffe;text-decoration:underline;">Upgrade &#x2192;</a>'
                f'</span></div>'
            )
    return buttons


@router.get("/dashboard", response_class=HTMLResponse)
async def connection_dashboard(
    request: Request,
    client_id: str = Query(None, description="Client identifier"),
):
    """
    Client self-service dashboard to connect social media accounts.
    Reads client_id from authenticated JWT session; query param is admin-only override.
    """
    # ── Resolve client_id from auth session ──────────────────────────────────
    from database.db import SessionLocal
    from database.models import ClientProfile
    from api.auth_routes import get_current_user
    from utils.plan_limits import PLAN_PLATFORMS, _parse_active_addons, has_feature_with_addons, PLAN_DISPLAY_NAMES
    import asyncio

    authed_client_id = None
    _plan_tier = "free"
    _active_addons: dict = {}
    user = None
    profile = None
    db = SessionLocal()
    try:
        user = get_current_user(request, db)
        if user:
            profile = db.query(ClientProfile).filter(
                ClientProfile.user_id == user.id
            ).first()
            if profile:
                authed_client_id = profile.client_id
                _plan_tier    = getattr(profile, "plan_tier",    "free") or "free"
                _active_addons = _parse_active_addons(profile)
    except Exception:
        pass  # No valid session — falls back to query param or login redirect
    finally:
        db.close()

    # ── Build allowed platform list for this client ───────────────────────────
    _allowed_platforms = list(PLAN_PLATFORMS.get(_plan_tier, ["instagram", "facebook"]))
    # YouTube add-on unlocks youtube even on non-Pro plans
    if has_feature_with_addons(_plan_tier, "youtube_access", _active_addons):
        if "youtube" not in _allowed_platforms:
            _allowed_platforms.append("youtube")

    # Upgrade hints per platform (what tier first unlocks it)
    _PLATFORM_UPGRADE_HINT = {
        "twitter":  ("Starter", ""),
        "tiktok":   ("Starter", ""),
        "linkedin": ("Growth",  ""),
        "threads":  ("Growth",  ""),
        "youtube":  ("Pro",     " or add the YouTube Add-on ($29/mo)"),
    }

    # Authenticated users always use their own client_id; only allow query param
    # override when there's no logged-in user (legacy / admin testing)
    if authed_client_id:
        client_id = authed_client_id
    elif not client_id:
        return RedirectResponse("/account/login", status_code=303)

    # Load existing connections for this client
    connections = load_connections()
    client_connections = connections.get(client_id, {})

    # Check if THIS CLIENT (not the agency) has a Meta OAuth token.
    # Uses main PostgreSQL DB first (survives Railway redeploys), then falls back to SQLite.
    has_meta_token = _has_meta_token_for_client(client_id)

    # Build connection status HTML
    connection_status = ""

    # Instagram & Facebook (via Meta OAuth – client must connect themselves)
    if has_meta_token:
        connection_status += f"""
            <div class="connection-item connected">
                <span class="platform-icon"><i class="fab fa-instagram"></i></span>
                <div style="flex:1">
                  <strong>Instagram &amp; Facebook</strong>
                  <div style="font-size:12px;color:#28a745">Connected via Meta</div>
                </div>
                <button class="disconnect-btn" onclick="disconnectAccount('meta')">Disconnect</button>
            </div>
        """
    else:
        connection_status += f"""
            <div class="connection-item disconnected">
                <span class="platform-icon"><i class="fab fa-instagram"></i></span>
                <div style="flex:1">
                  <strong>Instagram &amp; Facebook</strong>
                  <div style="font-size:12px;color:#999">Not connected</div>
                </div>
                <a href="/auth/start?client_id={client_id}" class="connect-small-btn">Connect</a>
            </div>
        """

    # Late API platforms (Twitter, TikTok, LinkedIn, Threads, YouTube) – client-specific only
    _LATE_ICONS = {"twitter": "<i class='fab fa-x-twitter'></i>", "tiktok": "<i class='fab fa-tiktok'></i>", "linkedin": "<i class='fab fa-linkedin'></i>", "threads": "<i class='fab fa-threads'></i>", "youtube": "<i class='fab fa-youtube'></i>"}
    for platform in ["twitter", "tiktok", "linkedin", "threads", "youtube"]:
        env_var = f"LATE_PROFILE_{platform.upper()}_{client_id}"
        profile_id = os.getenv(env_var)  # no default_client fallback

        # Also check connections JSON
        conn_data = client_connections.get(platform, {})
        has_connection = bool(profile_id) or bool(conn_data)
        icon = _LATE_ICONS.get(platform, "<i class='fas fa-link'></i>")

        if has_connection:
            username = conn_data.get('username') if conn_data else None
            display_name = f"@{username}" if username and username != 'Connected via Late API' else 'Connected'
            connection_status += f"""
                <div class="connection-item connected">
                    <span class="platform-icon">{icon}</span>
                    <div style="flex:1">
                      <strong>{platform.title()}</strong>
                      <div style="font-size:12px;color:#28a745">{display_name}</div>
                    </div>
                    <button class="disconnect-btn" onclick="disconnectAccount('{platform}')">Disconnect</button>
                </div>
            """
        else:
            is_locked = platform not in _allowed_platforms
            if is_locked:
                hint_tier, hint_extra = _PLATFORM_UPGRADE_HINT.get(platform, ("a higher plan", ""))
                tier_name = PLAN_DISPLAY_NAMES.get(hint_tier.lower(), hint_tier)
                connection_status += f"""
                    <div class="connection-item locked">
                        <span class="platform-icon">{icon}</span>
                        <div style="flex:1">
                          <strong>{platform.title()}</strong>
                          <div style="font-size:12px;color:#856404">🔒 Requires {tier_name}{hint_extra}</div>
                        </div>
                        <a href="/billing" class="connect-small-btn" style="background:#f0ad4e">Upgrade</a>
                    </div>
                """
            else:
                connection_status += f"""
                    <div class="connection-item disconnected">
                        <span class="platform-icon">{icon}</span>
                        <div style="flex:1">
                          <strong>{platform.title()}</strong>
                          <div style="font-size:12px;color:#999">Not connected</div>
                        </div>
                        <a href="/connect/late/{platform}?client_id={client_id}" class="connect-small-btn">Connect</a>
                    </div>
                """
    

    from utils.shared_layout import build_page
    _uname = user.full_name if user else "User"
    _bname = profile.business_name if profile else "My Business"

    _connect_css = """
            .header {
                text-align: center;
                margin-bottom: 40px;
            }
            .header h1 { 
                font-size: 28px; 
                color: #333;
                margin-bottom: 10px;
            }
            .header p { 
                color: #666; 
                font-size: 16px;
            }
            .client-id {
                background: #f0f0f0;
                padding: 10px 15px;
                border-radius: 5px;
                text-align: center;
                margin-bottom: 30px;
                font-family: monospace;
                color: #667eea;
            }
            .platform-card { 
                border: 2px solid #e0e0e0;
                padding: 25px; 
                margin: 20px 0; 
                border-radius: 12px;
                transition: all 0.3s ease;
            }
            .platform-card:hover {
                border-color: #667eea;
                box-shadow: 0 4px 12px rgba(102, 126, 234, 0.1);
            }
            .platform-card h3 { 
                margin-bottom: 10px;
                color: #333;
                font-size: 22px;
            }
            .platform-card p { 
                color: #666; 
                margin-bottom: 20px;
                line-height: 1.6;
            }
            .connect-btn {
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
                padding: 14px 28px;
                border: none;
                border-radius: 8px;
                font-size: 16px;
                font-weight: 600;
                cursor: pointer;
                text-decoration: none;
                display: inline-block;
                transition: all 0.3s ease;
            }
            .connect-btn:hover { 
                transform: translateY(-2px);
                box-shadow: 0 6px 20px rgba(102, 126, 234, 0.4);
            }
            .connect-btn.secondary {
                background: #f0f0f0;
                color: #333;
            }
            .connect-btn.secondary:hover {
                background: #e0e0e0;
            }
            .status-section {
                background: #f8f9fa;
                padding: 25px;
                border-radius: 10px;
                margin-top: 40px;
            }
            .status-section h3 {
                margin-bottom: 20px;
                color: #333;
            }
            .connection-item {
                background: white;
                padding: 15px;
                margin: 10px 0;
                border-radius: 8px;
                display: flex;
                align-items: center;
                gap: 15px;
                border-left: 4px solid #ddd;
            }
            .connection-item.connected {
                border-left-color: #28a745;
            }
            .connection-item.disconnected {
                border-left-color: #ccc;
            }
            .connection-item.locked {
                border-left-color: #f0ad4e;
                background: #fffbf2;
            }
            .disconnect-btn {
                padding: 6px 14px;
                background: transparent;
                color: #dc3545;
                border: 1.5px solid #dc3545;
                border-radius: 6px;
                font-size: 12px;
                font-weight: 600;
                cursor: pointer;
                white-space: nowrap;
                transition: all .15s;
            }
            .disconnect-btn:hover {
                background: #dc3545;
                color: white;
            }
            .connect-small-btn {
                padding: 6px 14px;
                background: #667eea;
                color: white;
                border: none;
                border-radius: 6px;
                font-size: 12px;
                font-weight: 600;
                cursor: pointer;
                text-decoration: none;
                white-space: nowrap;
                display: inline-block;
                transition: all .15s;
            }
            .connect-small-btn:hover { opacity: .85; }
            .platform-icon {
                font-size: 24px;
            }
            .date {
                margin-left: auto;
                font-size: 12px;
                color: #999;
            }
            .instructions {
                background: #fff3cd;
                border: 1px solid #ffc107;
                padding: 20px;
                border-radius: 8px;
                margin: 20px 0;
            }
            .instructions h4 {
                color: #856404;
                margin-bottom: 10px;
            }
            .instructions ol {
                margin-left: 20px;
                color: #856404;
                line-height: 1.8;
            }
            .footer {
                text-align: center;
                margin-top: 40px;
                padding-top: 20px;
                border-top: 1px solid #e0e0e0;
                color: #999;
                font-size: 14px;
            }
    """

    body_content = f"""
            <div class="header">
                <h1>🔗 Connect Your Social Accounts</h1>
                <p>Link your social media accounts to enable automated posting</p>
            </div>
            
            <div class="platform-card">
                <h3><i class="fas fa-link" style="margin-right:8px;color:#667eea"></i>Connect Social Accounts</h3>
                <p>Connect your social media accounts to enable automated posting and engagement. 
                   Click any platform below to authorize access.</p>
                
                <div class="instructions">
                    <h4>📋 How to Connect:</h4>
                    <ol>
                        <li>Click the platform button below</li>
                        <li>You'll be redirected to that platform's authorization page</li>
                        <li>Log in with your account credentials and authorize</li>
                        <li>You'll be redirected back here automatically</li>
                    </ol>
                </div>
                
                <h4 style="margin-top: 20px; margin-bottom: 10px; color: #555; font-size: 14px;">Meta Platforms (Instagram &amp; Facebook)</h4>
                <div style="display: flex; flex-wrap: wrap; gap: 10px;">
                    <a href="/auth/start?client_id={client_id}" class="connect-btn" style="background: linear-gradient(45deg, #f09433, #e6683c, #dc2743, #cc2366, #bc1888);">
                        <i class="fab fa-instagram" style="margin-right:6px"></i>Connect Instagram &amp; Facebook
                    </a>
                </div>
                
                <h4 style="margin-top: 20px; margin-bottom: 10px; color: #555; font-size: 14px;">Other Platforms</h4>
                <div style="display: flex; flex-wrap: wrap; gap: 10px;">
                    {"".join(_build_late_buttons(client_id, _allowed_platforms, _plan_tier, _PLATFORM_UPGRADE_HINT))}
                </div>
                
                <button onclick="window.location.reload()" class="connect-btn secondary" style="margin-top: 15px;">
                    <i class="fas fa-sync" style="margin-right:6px"></i>Refresh Status
                </button>
            </div>
            
            <div class="status-section">
                <h3><i class="fas fa-check-circle" style="margin-right:8px;color:#28a745"></i>Connection Status</h3>
                {connection_status}
            </div>
            
            <div class="footer">
                <p>🔒 Your credentials are securely stored and encrypted</p>
            </div>
    """

    _connect_js = f"""
            async function disconnectAccount(platform) {{
                const labels = {{
                    meta: 'Instagram & Facebook',
                    twitter: 'Twitter/X', tiktok: 'TikTok', linkedin: 'LinkedIn',
                    threads: 'Threads', youtube: 'YouTube'
                }};
                const name = labels[platform] || platform;
                if (!confirm(`Disconnect ${{name}}? You can reconnect at any time.`)) return;

                const r = await fetch(`/connect/disconnect/${{platform}}`, {{
                    method: 'POST',
                    headers: {{'Content-Type': 'application/json'}},
                    body: JSON.stringify({{client_id: '{client_id}'}})
                }});
                const d = await r.json();
                if (d.ok) {{
                    location.reload();
                }} else {{
                    alert('Could not disconnect: ' + (d.error || 'Unknown error'));
                }}
            }}
    """

    return HTMLResponse(build_page(
        title="Social Accounts",
        active_nav="connect",
        body_content=body_content,
        extra_css=_connect_css,
        extra_js=_connect_js,
        user_name=_uname,
        business_name=_bname,
    ))


@router.get("/status")
async def get_connection_status(client_id: str = Query(..., description="Client identifier")):
    """
    API endpoint to check connection status for a client
    """
    connections = load_connections()
    client_connections = connections.get(client_id, {})
    
    return JSONResponse({
        "client_id": client_id,
        "connections": [
            {
                "platform": platform,
                "username": data["username"],
                "profile_id": data["profile_id"],
                "connected_at": data["connected_at"],
                "status": data["status"]
            }
            for platform, data in client_connections.items()
        ],
        "total_connected": len(client_connections)
    })


@router.post("/disconnect/{platform}")
async def disconnect_account(platform: str, request: Request, background_tasks: BackgroundTasks):
    """
    Disconnect a social media account for the authenticated client.
    - 'meta' revokes the stored Meta OAuth token (Instagram + Facebook)
    - Any Late API platform removes the entry from the connections JSON store
    """
    from database.db import SessionLocal
    from database.models import ClientProfile
    from api.auth_routes import get_current_user

    db = SessionLocal()
    try:
        user = get_current_user(request, db)
        if not user:
            return JSONResponse({"ok": False, "error": "Not authenticated"}, status_code=401)
        profile = db.query(ClientProfile).filter(ClientProfile.user_id == user.id).first()
        if not profile:
            return JSONResponse({"ok": False, "error": "No profile found"}, status_code=400)
        client_id = profile.client_id
    finally:
        db.close()

    platform = platform.lower().strip()

    if platform == "meta":
        # ── Step 0: Grab the access token BEFORE we delete anything so we can
        #           call Meta's API to actually revoke the app permission.
        _revoke_token: Optional[str] = None
        _revoke_uid:   Optional[str] = None
        try:
            from database.db import SessionLocal as _SL_rev
            from database.models import ClientProfile as _CP_rev, MetaOAuthToken as _MOT_rev
            _db_rev = _SL_rev()
            try:
                _prof_rev = _db_rev.query(_CP_rev).filter(_CP_rev.client_id == client_id).first()
                if _prof_rev:
                    _revoke_uid = _prof_rev.meta_user_id
                    _tok_rev = _db_rev.query(_MOT_rev).filter(
                        _MOT_rev.client_profile_id == _prof_rev.id
                    ).first()
                    if _tok_rev and _tok_rev.access_token_enc:
                        try:
                            import os as _os_rev
                            from cryptography.fernet import Fernet as _Fernet
                            _fkey = _os_rev.getenv("TOKEN_ENCRYPTION_KEY", "")
                            if _fkey:
                                _revoke_token = _Fernet(_fkey.encode()).decrypt(
                                    _tok_rev.access_token_enc.encode()
                                ).decode()
                        except Exception:
                            pass
            finally:
                _db_rev.close()
        except Exception:
            pass
        # Fallback: get token from legacy alita_oauth.db
        if not _revoke_token:
            try:
                from api.token_manager import TokenManager as _TM_rev
                _tm_rev = _TM_rev()
                _meta_uid_rev = _get_meta_user_id_for_client(client_id)
                if _meta_uid_rev:
                    _tok_data = _tm_rev.get_token(_meta_uid_rev)
                    if _tok_data and _tok_data.get("access_token"):
                        _revoke_token = _tok_data["access_token"]
                        _revoke_uid = _revoke_uid or _meta_uid_rev
            except Exception:
                pass

        # ── Step 1: Revoke on Meta's side (best-effort — won't block disconnect)
        if _revoke_token and _revoke_uid:
            try:
                import httpx as _httpx
                _meta_app_id     = os.getenv("META_APP_ID", "")
                _meta_app_secret = os.getenv("META_APP_SECRET", "")
                # DELETE /{user-id}/permissions revokes all app permissions
                _revoke_url = f"https://graph.facebook.com/v21.0/{_revoke_uid}/permissions"
                _resp = _httpx.delete(
                    _revoke_url,
                    params={"access_token": _revoke_token},
                    timeout=10,
                )
                if _resp.status_code == 200 and _resp.json().get("success"):
                    print(f"✅ Meta app permissions revoked for uid={_revoke_uid}")
                else:
                    print(f"⚠️  Meta revoke returned: {_resp.status_code} {_resp.text[:200]}")
            except Exception as _rev_err:
                print(f"⚠️  Meta revoke call failed (continuing): {_rev_err}")
        else:
            print(f"⚠️  No token found to revoke on Meta side for {client_id}")

        # Remove the stored Meta OAuth token for this client.
        # 2. Clear from main PostgreSQL DB (MetaOAuthToken + ClientProfile columns)
        try:
            from database.db import SessionLocal as _SL2
            from database.models import ClientProfile as _CP2, MetaOAuthToken as _MOT2
            from datetime import datetime as _dt2
            _db2 = _SL2()
            try:
                _profile2 = _db2.query(_CP2).filter(_CP2.client_id == client_id).first()
                if _profile2:
                    _tok_row2 = _db2.query(_MOT2).filter(
                        _MOT2.client_profile_id == _profile2.id
                    ).first()
                    if _tok_row2:
                        _db2.delete(_tok_row2)
                    _profile2.meta_user_id          = None
                    _profile2.meta_ig_account_id    = None
                    _profile2.meta_ig_username      = None
                    _profile2.meta_facebook_page_id = None
                    _profile2.meta_connected_at     = None
                    _db2.commit()
                    print(f"🔌 Meta disconnected from main DB for {client_id}")
            finally:
                _db2.close()
        except Exception as _dbe2:
            print(f"⚠️  Could not clear Meta from main DB: {_dbe2}")

        # 2. Also delete from legacy alita_oauth.db (best-effort)
        from api.token_manager import TokenManager
        tm = TokenManager()
        _meta_uid = _get_meta_user_id_for_client(client_id)
        if _meta_uid:
            tm.delete_tokens(_meta_uid)
            print(f"🔌 Meta disconnected from alita_oauth.db for {client_id} (meta_user_id={_meta_uid})")
        # 3. Remove the per-client connections bridge file
        _meta_conn_path = os.path.join(CLIENT_META_CONNECTIONS_DIR, f"{client_id}.json")
        if os.path.exists(_meta_conn_path):
            try:
                os.remove(_meta_conn_path)
                print(f"🗑️  Removed {_meta_conn_path}")
            except Exception as _rm_err:
                print(f"⚠️  Could not remove connections file: {_rm_err}")
        # Notify calendar agent about Meta (instagram + facebook) disconnection
        from utils.platform_events import on_platform_disconnected
        background_tasks.add_task(on_platform_disconnected, client_id, "instagram")
        background_tasks.add_task(on_platform_disconnected, client_id, "facebook")
        return JSONResponse({"ok": True, "platform": "meta"})

    elif platform in LATE_PLATFORMS:
        removed = remove_connection(client_id, platform)
        # Also clear any env var that may have been set at runtime (doesn't persist restart)
        env_key = f"LATE_PROFILE_{platform.upper()}_{client_id}"
        if env_key in os.environ:
            del os.environ[env_key]
        print(f"🔌 {platform} disconnected for {client_id} (was in store: {removed})")
        # Notify calendar agent about the disconnection
        from utils.platform_events import on_platform_disconnected
        background_tasks.add_task(on_platform_disconnected, client_id, platform)
        return JSONResponse({"ok": True, "platform": platform})

    else:
        return JSONResponse({"ok": False, "error": f"Unknown platform: {platform}"}, status_code=400)


@router.post("/manual-add")
async def manually_add_connection(
    background_tasks: BackgroundTasks,
    client_id: str = Query(...),
    platform: str = Query(...),
    profile_id: str = Query(...),
    username: str = Query(...)
):
    """
    Manually add a connection
    """
    add_connection(client_id, platform, profile_id, username)

    # Notify calendar agent and regenerate schedule immediately
    from utils.platform_events import on_platform_connected
    background_tasks.add_task(on_platform_connected, client_id, platform)
    
    return JSONResponse({
        "status": "success",
        "message": f"Added {platform} connection for {client_id}",
        "connection": {
            "client_id": client_id,
            "platform": platform,
            "profile_id": profile_id,
            "username": username
        }
    })


@router.get("/late/callback")
async def late_api_callback(request: Request, background_tasks: BackgroundTasks, client_id: str = "default_client", platform: str = ""):
    """
    Handle Late API OAuth callback after user authorizes.
    Late redirects here with connected=platform&profileId=X&username=Y
    """
    params = dict(request.query_params)
    
    # Late API sometimes appends ?connected=X to the platform param, causing corruption
    # e.g. platform="linkedin?connected=linkedin" — clean it up
    raw_platform = params.get("platform", platform)
    if "?" in raw_platform:
        raw_platform = raw_platform.split("?")[0]
    
    connected_platform = params.get("connected", raw_platform).lower().strip()
    profile_id = params.get("profileId", "")
    account_id = params.get("accountId", "")  # Late API sends accountId for some platforms
    username = params.get("username", "Connected")
    error = params.get("error", "")
    
    # Handle error responses from Late API OAuth
    if error:
        return HTMLResponse(f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Connection Failed - Alita</title>
            <style>
                body {{ font-family: 'Segoe UI', sans-serif; text-align: center; padding: 80px 20px;
                       background: #f8f9fa; color: #333; min-height: 100vh; }}
                .card {{ background: white; color: #333; max-width: 500px; margin: 0 auto;
                        border-radius: 15px; padding: 40px; box-shadow: 0 10px 40px rgba(0,0,0,0.1); }}
                .emoji {{ font-size: 64px; margin-bottom: 20px; }}
                h1 {{ margin-bottom: 10px; color: #dc3545; }}
                p {{ color: #666; line-height: 1.6; }}
                .btn {{ display: inline-block; margin-top: 20px; padding: 12px 30px;
                       background: #667eea; color: white; text-decoration: none;
                       border-radius: 8px; font-weight: 600; }}
            </style>
            <meta http-equiv="refresh" content="5;url=/connect/dashboard?client_id={client_id}">
        </head>
        <body>
            <div class="card">
                <div class="emoji">❌</div>
                <h1>{connected_platform.title()} Connection Failed</h1>
                <p>The OAuth authorization for <strong>{connected_platform.title()}</strong> was not completed.</p>
                <p>Error: <code>{error}</code></p>
                <p style="font-size: 13px; margin-top: 15px;">Please try connecting again from the dashboard.</p>
                <a href="/connect/dashboard?client_id={client_id}" class="btn">← Back to Dashboard</a>
            </div>
        </body>
        </html>
        """)
    
    # Use the best available ID: accountId > profileId
    best_id = account_id or profile_id
    
    if connected_platform and best_id:
        # Save the connection
        add_connection(client_id, connected_platform, best_id, username)

        # Notify calendar agent and regenerate schedule immediately
        from utils.platform_events import on_platform_connected
        background_tasks.add_task(on_platform_connected, client_id, connected_platform)
        
        # Also try to fetch the account details from Late API
        try:
            async with httpx.AsyncClient(timeout=15.0) as http_client:
                response = await http_client.get(
                    f"{LATE_API_BASE}/accounts",
                    headers={"Authorization": f"Bearer {LATE_API_KEY}"}
                )
                if response.status_code == 200:
                    accounts = response.json().get("accounts", [])
                    for acc in accounts:
                        if acc.get("platform") == connected_platform:
                            username = acc.get("username", username)
                            final_id = acc.get("_id", best_id)
                            add_connection(client_id, connected_platform, final_id, username)
                            break
        except Exception as e:
            pass
    
    # Show success page using shared layout, then auto-redirect
    _late_success_css = """
.success-card{border:1.5px solid #e4e6eb;border-radius:12px;padding:28px 32px;background:#fff;margin-bottom:20px}
.success-card h2{font-size:1.1rem;margin:0 0 6px}
"""
    _late_success_body = f"""
<div style="margin-bottom:24px">
  <h1 style="font-size:1.4rem;font-weight:700;color:#1c1e21;margin:0 0 6px">&#x2705; {connected_platform.title()} Connected!</h1>
  <p style="color:#90949c;font-size:.9rem;margin:0">Your <strong>{connected_platform.title()}</strong> account {f'(@{username})' if username != 'Connected' else ''} has been connected successfully.</p>
</div>

<div class="success-card">
  <p style="font-size:.87rem;color:#555">Redirecting to your dashboard in 3 seconds&hellip;</p>
  <a href="/connect/dashboard" class="btn-primary" style="text-decoration:none;display:inline-block;padding:12px 24px;border-radius:8px;font-weight:600;font-size:.9rem;margin-top:8px">&#x2190; Back to Dashboard</a>
</div>

<script>setTimeout(function(){{ window.location.href = '/connect/dashboard'; }}, 3000);</script>
"""
    from utils.shared_layout import build_page
    return HTMLResponse(build_page(
        title=f"{connected_platform.title()} Connected!",
        active_nav="connect",
        body_content=_late_success_body,
        extra_css=_late_success_css,
        user_name="",
        business_name="",
    ))


@router.get("/late/{platform}")
async def connect_via_late_api(platform: str, request: Request, client_id: str = Query("default_client")):
    """
    Initiate OAuth connection via Late API for a given platform.
    Calls Late API GET /v1/connect/{platform} and redirects user to the authUrl.
    """
    valid_platforms = ["twitter", "tiktok", "linkedin", "threads", "youtube",
                       "facebook", "instagram", "reddit", "pinterest", "bluesky"]
    
    if platform not in valid_platforms:
        return HTMLResponse(f"""
        <html><body style='font-family:Arial;text-align:center;padding:60px;'>
            <h2>❌ Invalid platform: {platform}</h2>
            <p>Supported: {', '.join(valid_platforms)}</p>
            <a href='/connect/dashboard?client_id={client_id}'>← Back</a>
        </body></html>
        """, status_code=400)

    # ── Plan gating: verify the client is allowed to connect this platform ────
    from database.db import SessionLocal
    from database.models import ClientProfile
    from api.auth_routes import get_current_user
    from utils.plan_limits import PLAN_PLATFORMS, _parse_active_addons, has_feature_with_addons, PLAN_DISPLAY_NAMES

    _tier = "free"
    _addons: dict = {}
    _db = SessionLocal()
    try:
        _user = get_current_user(request, _db)
        if _user:
            _profile = _db.query(ClientProfile).filter(
                ClientProfile.user_id == _user.id
            ).first()
            if _profile:
                _tier   = getattr(_profile, "plan_tier", "free") or "free"
                _addons = _parse_active_addons(_profile)
    finally:
        _db.close()

    _allowed = list(PLAN_PLATFORMS.get(_tier, ["instagram", "facebook"]))
    if has_feature_with_addons(_tier, "youtube_access", _addons) and "youtube" not in _allowed:
        _allowed.append("youtube")

    _LATE_GATED = ["twitter", "tiktok", "linkedin", "threads", "youtube"]  # meta handled elsewhere
    if platform in _LATE_GATED and platform not in _allowed:
        _UPGRADE_TIER = {
            "twitter": "Starter", "tiktok": "Starter",
            "linkedin": "Growth", "threads": "Growth", "youtube": "Pro",
        }
        _extra = " or add the YouTube Add-on ($29/mo)" if platform == "youtube" else ""
        needed = PLAN_DISPLAY_NAMES.get(_UPGRADE_TIER.get(platform, "").lower(), _UPGRADE_TIER.get(platform, "a higher plan"))
        return HTMLResponse(f"""
        <html><body style='font-family:Arial;text-align:center;padding:60px;'>
            <h2>🔒 Platform Not Included in Your Plan</h2>
            <p>Your current plan ({PLAN_DISPLAY_NAMES.get(_tier, _tier.title())}) doesn't include {platform.title()}.</p>
            <p>Upgrade to <strong>{needed}</strong>{_extra} to connect this account.</p>
            <a href='/billing' style='background:#667eea;color:white;padding:10px 24px;border-radius:8px;text-decoration:none;display:inline-block;margin:10px;'>⬆️ Upgrade Plan</a>
            <a href='/connect/dashboard' style='background:#f0f0f0;color:#333;padding:10px 24px;border-radius:8px;text-decoration:none;display:inline-block;margin:10px;'>← Back</a>
        </body></html>
        """, status_code=403)

    # ── Social-account-count gate ────────────────────────────────────────────
    from utils.plan_limits import get_effective_limit
    _acct_limit = get_effective_limit(_tier, "social_accounts", _addons)
    if _acct_limit != -1:
        _existing = load_connections().get(client_id, {})
        _current_count = len(_existing)
        # Also count Meta OAuth connections (IG/FB) from the DB
        try:
            from database.models import PlatformConnection
            _db2 = SessionLocal()
            _meta_count = _db2.query(PlatformConnection).filter(
                PlatformConnection.client_id == client_id,
            ).count()
            _db2.close()
            _current_count = max(_current_count, _meta_count)  # avoid double-counting — use higher
        except Exception:
            pass
        if _current_count >= _acct_limit:
            return HTMLResponse(f"""
            <html><body style='font-family:Arial;text-align:center;padding:60px;'>
                <h2>🔒 Account Limit Reached</h2>
                <p>Your {PLAN_DISPLAY_NAMES.get(_tier, _tier.title())} plan allows up to <strong>{_acct_limit}</strong> social accounts. You currently have {_current_count} connected.</p>
                <p>Upgrade your plan or add the Account Expansion add-on for more connections.</p>
                <a href='/billing' style='background:#667eea;color:white;padding:10px 24px;border-radius:8px;text-decoration:none;display:inline-block;margin:10px;'>⬆️ Upgrade Plan</a>
                <a href='/connect/dashboard' style='background:#f0f0f0;color:#333;padding:10px 24px;border-radius:8px;text-decoration:none;display:inline-block;margin:10px;'>← Back</a>
            </body></html>
            """, status_code=403)
    
    if not LATE_API_KEY:
        return HTMLResponse("""
        <html><body style='font-family:Arial;text-align:center;padding:60px;'>
            <h2>❌ Late API key not configured</h2>
            <p>Set LATE_API_KEY in your .env file</p>
        </body></html>
        """, status_code=500)
    
    try:
        # Call Late API connect endpoint
        # IMPORTANT: Use urllib to properly encode the callback URL so Late API's 
        # appended params (e.g. ?connected=linkedin) don't corrupt our query params
        from urllib.parse import urlencode, quote
        _app_base = os.getenv("APP_BASE_URL", "https://web-production-00e4.up.railway.app").rstrip("/")
        callback_base = f"{_app_base}/connect/late/callback"
        callback_params = urlencode({"client_id": client_id, "platform": platform})
        callback_url = f"{callback_base}?{callback_params}"
        
        async with httpx.AsyncClient(timeout=30.0) as http_client:
            response = await http_client.get(
                f"{LATE_API_BASE}/connect/{platform}",
                headers={"Authorization": f"Bearer {LATE_API_KEY}"},
                params={
                    "profileId": _get_late_profile_for_client(client_id),
                    "redirect_url": callback_url
                }
            )
            
            if response.status_code == 200:
                data = response.json()
                auth_url = data.get("authUrl")
                if auth_url:
                    return RedirectResponse(url=auth_url)
                else:
                    return HTMLResponse(f"""
                    <html><body style='font-family:Arial;text-align:center;padding:60px;'>
                        <h2>⚠️ No auth URL returned</h2>
                        <p>Late API response: {json.dumps(data)}</p>
                        <a href='/connect/dashboard?client_id={client_id}'>← Back</a>
                    </body></html>
                    """)
            else:
                error_text = response.text
                return HTMLResponse(f"""
                <html><body style='font-family:Arial;text-align:center;padding:60px;'>
                    <h2>❌ Connection failed</h2>
                    <p>Late API returned {response.status_code}: {error_text[:200]}</p>
                    <a href='/connect/dashboard?client_id={client_id}'>← Back</a>
                </body></html>
                """, status_code=502)
    
    except Exception as e:
        return HTMLResponse(f"""
        <html><body style='font-family:Arial;text-align:center;padding:60px;'>
            <h2>❌ Connection error</h2>
            <p>{str(e)}</p>
            <a href='/connect/dashboard?client_id={client_id}'>← Back</a>
        </body></html>
        """, status_code=500)

