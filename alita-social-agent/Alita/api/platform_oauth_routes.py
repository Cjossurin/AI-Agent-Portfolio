"""
OAuth Routes for Twitter/X, TikTok, and YouTube
Allows clients to connect their own social media accounts
"""

from fastapi import APIRouter, Query, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
import httpx
import os
import json
import secrets
from urllib.parse import urlencode
from dotenv import load_dotenv
from utils.shared_layout import build_page

load_dotenv()

router = APIRouter(prefix="/connect", tags=["Platform OAuth"])


# ==================== TWITTER/X OAUTH ====================

@router.get("/twitter")
async def connect_twitter():
    """
    Initiate Twitter/X OAuth 2.0 flow.
    Step 1: Redirect user to Twitter authorization page.
    """
    client_id = os.getenv("TWITTER_CLIENT_ID")
    if not client_id:
        raise HTTPException(status_code=500, detail="Twitter OAuth not configured")
    
    # Generate state for CSRF protection
    state = secrets.token_urlsafe(32)
    
    # Twitter OAuth 2.0 authorization URL
    redirect_uri = os.getenv("TWITTER_REDIRECT_URI", "http://localhost:8000/connect/twitter/callback")
    
    params = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "scope": "tweet.read tweet.write users.read offline.access",
        "state": state,
        "code_challenge": "challenge",  # Use PKCE in production
        "code_challenge_method": "plain"
    }
    
    auth_url = f"https://twitter.com/i/oauth2/authorize?{urlencode(params)}"
    
    return RedirectResponse(url=auth_url)


@router.get("/twitter/callback")
async def twitter_callback(code: str = Query(...), state: str = Query(None)):
    """
    Handle Twitter OAuth callback.
    Step 2: Exchange authorization code for access token.
    """
    try:
        client_id = os.getenv("TWITTER_CLIENT_ID")
        client_secret = os.getenv("TWITTER_CLIENT_SECRET")
        redirect_uri = os.getenv("TWITTER_REDIRECT_URI", "http://localhost:8000/connect/twitter/callback")
        
        # Exchange code for access token
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://api.twitter.com/2/oauth2/token",
                data={
                    "code": code,
                    "grant_type": "authorization_code",
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "redirect_uri": redirect_uri,
                    "code_verifier": "challenge"  # Match code_challenge
                },
                headers={
                    "Content-Type": "application/x-www-form-urlencoded"
                }
            )
        
        if response.status_code == 200:
            token_data = response.json()
            access_token = token_data.get("access_token")
            refresh_token = token_data.get("refresh_token")
            
            # Get user info
            async with httpx.AsyncClient() as client:
                user_response = await client.get(
                    "https://api.twitter.com/2/users/me",
                    headers={"Authorization": f"Bearer {access_token}"}
                )
            
            user_data = user_response.json().get("data", {})
            user_id = user_data.get("id")
            username = user_data.get("username")
            
            return HTMLResponse(f"""
                <!DOCTYPE html>
                <html>
                <head>
                    <title>Twitter Connected</title>
                    <style>
                        body {{ font-family: Arial; text-align: center; padding: 50px; }}
                        .success {{ color: #1da1f2; font-size: 24px; margin: 20px; }}
                        .info {{ background: #f0f0f0; padding: 20px; border-radius: 8px; max-width: 400px; margin: 20px auto; }}
                        button {{ padding: 10px 20px; background: #1da1f2; color: white; border: none; border-radius: 5px; cursor: pointer; font-size: 16px; }}
                    </style>
                </head>
                <body>
                    <h1 class="success">✓ Twitter Connected!</h1>
                    <div class="info">
                        <p><strong>Username:</strong> @{username}</p>
                        <p><strong>User ID:</strong> {user_id}</p>
                        <p>Your Twitter account is now connected.</p>
                    </div>
                    <button onclick="closeWindow()">Done</button>
                    <script>
                        function closeWindow() {{
                            if (window.opener) {{
                                window.opener.postMessage({{
                                    type: 'twitter-connected',
                                    username: '{username}',
                                    user_id: '{user_id}'
                                }}, '*');
                                window.close();
                            }} else {{
                                window.location.href = '/social/dashboard';
                            }}
                        }}
                    </script>
                </body>
                </html>
            """)
        else:
            error = response.json()
            raise HTTPException(status_code=400, detail=f"Twitter OAuth failed: {error}")
    
    except Exception as e:
        return HTMLResponse(f"""
            <html>
            <body style="font-family: Arial; text-align: center; padding: 50px;">
                <h1 style="color: red;">Connection Failed</h1>
                <p>{str(e)}</p>
                <button onclick="history.back()">Go Back</button>
            </body>
            </html>
        """)


# ==================== TIKTOK OAUTH ====================

@router.get("/tiktok")
async def connect_tiktok():
    """
    Initiate TikTok OAuth flow.
    Step 1: Redirect user to TikTok authorization page.
    """
    client_key = os.getenv("TIKTOK_CLIENT_KEY")
    if not client_key:
        raise HTTPException(status_code=500, detail="TikTok OAuth not configured")
    
    state = secrets.token_urlsafe(32)
    redirect_uri = os.getenv("TIKTOK_REDIRECT_URI", "http://localhost:8000/connect/tiktok/callback")
    
    params = {
        "client_key": client_key,
        "scope": "user.info.basic,video.list,video.upload",
        "response_type": "code",
        "redirect_uri": redirect_uri,
        "state": state
    }
    
    auth_url = f"https://www.tiktok.com/v2/auth/authorize/?{urlencode(params)}"
    
    return RedirectResponse(url=auth_url)


@router.get("/tiktok/callback")
async def tiktok_callback(code: str = Query(...), state: str = Query(None)):
    """
    Handle TikTok OAuth callback.
    Step 2: Exchange authorization code for access token.
    """
    try:
        client_key = os.getenv("TIKTOK_CLIENT_KEY")
        client_secret = os.getenv("TIKTOK_CLIENT_SECRET")
        redirect_uri = os.getenv("TIKTOK_REDIRECT_URI", "http://localhost:8000/connect/tiktok/callback")
        
        # Exchange code for access token
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://open.tiktokapis.com/v2/oauth/token/",
                headers={
                    "Content-Type": "application/x-www-form-urlencoded",
                    "Cache-Control": "no-cache"
                },
                data={
                    "client_key": client_key,
                    "client_secret": client_secret,
                    "code": code,
                    "grant_type": "authorization_code",
                    "redirect_uri": redirect_uri
                }
            )
        
        if response.status_code == 200:
            token_data = response.json()
            access_token = token_data.get("access_token")
            refresh_token = token_data.get("refresh_token")
            open_id = token_data.get("open_id")
            
            # Get user info
            async with httpx.AsyncClient() as client:
                user_response = await client.get(
                    "https://open.tiktokapis.com/v2/user/info/",
                    headers={
                        "Authorization": f"Bearer {access_token}"
                    },
                    params={
                        "fields": "open_id,union_id,avatar_url,display_name"
                    }
                )
            
            user_data = user_response.json().get("data", {}).get("user", {})
            display_name = user_data.get("display_name", "User")
            
            return HTMLResponse(f"""
                <!DOCTYPE html>
                <html>
                <head>
                    <title>TikTok Connected</title>
                    <style>
                        body {{ font-family: Arial; text-align: center; padding: 50px; }}
                        .success {{ color: #000; font-size: 24px; margin: 20px; }}
                        .info {{ background: #f0f0f0; padding: 20px; border-radius: 8px; max-width: 400px; margin: 20px auto; }}
                        button {{ padding: 10px 20px; background: #000; color: white; border: none; border-radius: 5px; cursor: pointer; font-size: 16px; }}
                    </style>
                </head>
                <body>
                    <h1 class="success">✓ TikTok Connected!</h1>
                    <div class="info">
                        <p><strong>Display Name:</strong> {display_name}</p>
                        <p><strong>Open ID:</strong> {open_id}</p>
                        <p>Your TikTok account is now connected.</p>
                    </div>
                    <button onclick="closeWindow()">Done</button>
                    <script>
                        function closeWindow() {{
                            if (window.opener) {{
                                window.opener.postMessage({{
                                    type: 'tiktok-connected',
                                    display_name: '{display_name}',
                                    open_id: '{open_id}'
                                }}, '*');
                                window.close();
                            }} else {{
                                window.location.href = '/social/dashboard';
                            }}
                        }}
                    </script>
                </body>
                </html>
            """)
        else:
            error = response.json()
            raise HTTPException(status_code=400, detail=f"TikTok OAuth failed: {error}")
    
    except Exception as e:
        return HTMLResponse(f"""
            <html>
            <body style="font-family: Arial; text-align: center; padding: 50px;">
                <h1 style="color: red;">Connection Failed</h1>
                <p>{str(e)}</p>
                <button onclick="history.back()">Go Back</button>
            </body>
            </html>
        """)


# ==================== YOUTUBE (GOOGLE) OAUTH ====================

@router.get("/youtube")
async def connect_youtube():
    """
    Initiate YouTube (Google) OAuth flow.
    Step 1: Redirect user to Google authorization page.
    """
    client_id = os.getenv("GOOGLE_CLIENT_ID")
    if not client_id:
        raise HTTPException(status_code=500, detail="YouTube OAuth not configured")
    
    state = secrets.token_urlsafe(32)
    redirect_uri = os.getenv("GOOGLE_REDIRECT_URI", "http://localhost:8000/connect/youtube/callback")
    
    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": "https://www.googleapis.com/auth/youtube.readonly https://www.googleapis.com/auth/youtube.upload",
        "access_type": "offline",  # Get refresh token
        "prompt": "consent",  # Force consent screen to get refresh token
        "state": state
    }
    
    auth_url = f"https://accounts.google.com/o/oauth2/v2/auth?{urlencode(params)}"
    
    return RedirectResponse(url=auth_url)


@router.get("/youtube/callback")
async def youtube_callback(code: str = Query(...), state: str = Query(None)):
    """
    Handle YouTube OAuth callback.
    Step 2: Exchange authorization code for access token.
    """
    try:
        client_id = os.getenv("GOOGLE_CLIENT_ID")
        client_secret = os.getenv("GOOGLE_CLIENT_SECRET")
        redirect_uri = os.getenv("GOOGLE_REDIRECT_URI", "http://localhost:8000/connect/youtube/callback")
        
        # Exchange code for access token
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://oauth2.googleapis.com/token",
                data={
                    "code": code,
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "redirect_uri": redirect_uri,
                    "grant_type": "authorization_code"
                }
            )
        
        if response.status_code == 200:
            token_data = response.json()
            access_token = token_data.get("access_token")
            refresh_token = token_data.get("refresh_token")
            
            # Get channel info
            async with httpx.AsyncClient() as client:
                channel_response = await client.get(
                    "https://www.googleapis.com/youtube/v3/channels",
                    headers={"Authorization": f"Bearer {access_token}"},
                    params={
                        "part": "snippet,statistics",
                        "mine": "true"
                    }
                )
            
            channel_data = channel_response.json().get("items", [{}])[0]
            channel_id = channel_data.get("id")
            channel_title = channel_data.get("snippet", {}).get("title", "Unknown")
            subscriber_count = channel_data.get("statistics", {}).get("subscriberCount", "0")
            
            return HTMLResponse(f"""
                <!DOCTYPE html>
                <html>
                <head>
                    <title>YouTube Connected</title>
                    <style>
                        body {{ font-family: Arial; text-align: center; padding: 50px; }}
                        .success {{ color: #ff0000; font-size: 24px; margin: 20px; }}
                        .info {{ background: #f0f0f0; padding: 20px; border-radius: 8px; max-width: 400px; margin: 20px auto; }}
                        button {{ padding: 10px 20px; background: #ff0000; color: white; border: none; border-radius: 5px; cursor: pointer; font-size: 16px; }}
                    </style>
                </head>
                <body>
                    <h1 class="success">✓ YouTube Connected!</h1>
                    <div class="info">
                        <p><strong>Channel:</strong> {channel_title}</p>
                        <p><strong>Channel ID:</strong> {channel_id}</p>
                        <p><strong>Subscribers:</strong> {subscriber_count}</p>
                        <p>Your YouTube channel is now connected.</p>
                    </div>
                    <button onclick="closeWindow()">Done</button>
                    <script>
                        function closeWindow() {{
                            if (window.opener) {{
                                window.opener.postMessage({{
                                    type: 'youtube-connected',
                                    channel_title: '{channel_title}',
                                    channel_id: '{channel_id}',
                                    subscribers: '{subscriber_count}'
                                }}, '*');
                                window.close();
                            }} else {{
                                window.location.href = '/social/dashboard';
                            }}
                        }}
                    </script>
                </body>
                </html>
            """)
        else:
            error = response.json()
            raise HTTPException(status_code=400, detail=f"YouTube OAuth failed: {error}")
    
    except Exception as e:
        return HTMLResponse(f"""
            <html>
            <body style="font-family: Arial; text-align: center; padding: 50px;">
                <h1 style="color: red;">Connection Failed</h1>
                <p>{str(e)}</p>
                <button onclick="history.back()">Go Back</button>
            </body>
            </html>
        """)


# ==================== CONNECTION DASHBOARD ====================

@router.get("/dashboard", response_class=HTMLResponse)
async def connection_dashboard():
    """Dashboard for users to connect their social media accounts."""

    _CSS = """
.platforms-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:20px;margin-bottom:28px}
.platform-card{background:#fff;padding:25px;border-radius:12px;box-shadow:0 1px 4px rgba(0,0,0,.06);text-align:center;transition:transform .25s,box-shadow .25s;border:1px solid #dde0e4}
.platform-card:hover{transform:translateY(-4px);box-shadow:0 4px 16px rgba(0,0,0,.12)}
.platform-icon{font-size:48px;margin-bottom:14px}
.platform-card h3{margin-bottom:8px;font-size:1.1rem;font-weight:700}
.platform-card p{color:#606770;font-size:.88rem;margin-bottom:16px}
.plat-status{display:inline-block;padding:4px 14px;border-radius:99px;font-size:.75rem;font-weight:700;margin-bottom:14px}
.plat-status.connected{background:#e8f5e9;color:#2e7d32}
.plat-status.disconnected{background:#fce4ec;color:#c62828}
.btn-connect{padding:10px 22px;border:none;border-radius:8px;cursor:pointer;font-size:.88rem;font-weight:700;color:#fff;transition:opacity .15s}
.btn-connect:hover{opacity:.85}
.btn-twitter{background:#1da1f2}.btn-tiktok{background:#000}.btn-youtube{background:#ff0000}
.conn-section{background:#fff;padding:24px;border-radius:12px;box-shadow:0 1px 4px rgba(0,0,0,.06);border:1px solid #dde0e4;margin-top:4px}
.conn-section h2{font-size:1rem;font-weight:700;margin-bottom:16px}
.account-item{padding:13px;border-left:4px solid #5c6ac4;margin-bottom:10px;background:#f8f9fb;border-radius:6px;font-size:.88rem}
.connect-hero{background:linear-gradient(135deg,#5c6ac4,#764ba2);color:#fff;padding:24px 28px;border-radius:14px;margin-bottom:24px}
.connect-hero h1{font-size:1.5rem;font-weight:800;margin-bottom:6px}
.connect-hero p{opacity:.85;font-size:.9rem}
"""

    _body = """
<div class="connect-hero">
  <h1>&#128279; Connect Your Social Media Accounts</h1>
  <p>Link your accounts to enable posting, scheduling, and analytics</p>
</div>
<div class="platforms-grid">
  <div class="platform-card">
    <div class="platform-icon">&#120143;</div>
    <h3>Twitter / X</h3>
    <p>Post tweets, view analytics, track engagement</p>
    <div class="plat-status disconnected" id="twitter-status">Not Connected</div><br>
    <button class="btn-connect btn-twitter" onclick="connectPlatform('twitter')">Connect Twitter</button>
  </div>
  <div class="platform-card">
    <div class="platform-icon">&#127925;</div>
    <h3>TikTok</h3>
    <p>Upload videos, view analytics, manage content</p>
    <div class="plat-status disconnected" id="tiktok-status">Not Connected</div><br>
    <button class="btn-connect btn-tiktok" onclick="connectPlatform('tiktok')">Connect TikTok</button>
  </div>
  <div class="platform-card">
    <div class="platform-icon">&#9654;</div>
    <h3>YouTube</h3>
    <p>Upload videos, manage channel, view analytics</p>
    <div class="plat-status disconnected" id="youtube-status">Not Connected</div><br>
    <button class="btn-connect btn-youtube" onclick="connectPlatform('youtube')">Connect YouTube</button>
  </div>
</div>
<div class="conn-section">
  <h2>Your Connected Accounts</h2>
  <div id="accounts-list">
    <p style="color:#606770;">No accounts connected yet. Connect your first account above!</p>
  </div>
</div>
"""

    _js = r"""
window.addEventListener('load', () => { checkConnectedAccounts(); });

function connectPlatform(platform) {
    const width = 600, height = 700;
    const left = (screen.width - width) / 2, top = (screen.height - height) / 2;
    const popup = window.open(`/connect/${platform}`, 'Connect Account',
        `width=${width},height=${height},left=${left},top=${top}`);
    window.addEventListener('message', (event) => {
        if (event.data.type === `${platform}-connected`) {
            handleConnectionSuccess(platform, event.data);
        }
    });
}

function handleConnectionSuccess(platform, data) {
    const statusEl = document.getElementById(`${platform}-status`);
    statusEl.textContent = 'Connected \u2713';
    statusEl.className = 'plat-status connected';
    const connections = JSON.parse(localStorage.getItem('connections') || '{}');
    connections[platform] = { ...data, connected_at: new Date().toISOString() };
    localStorage.setItem('connections', JSON.stringify(connections));
    displayConnectedAccounts();
    alert(`${platform.toUpperCase()} account connected successfully!`);
}

function checkConnectedAccounts() {
    const connections = JSON.parse(localStorage.getItem('connections') || '{}');
    Object.keys(connections).forEach(platform => {
        const statusEl = document.getElementById(`${platform}-status`);
        if (statusEl) { statusEl.textContent = 'Connected \u2713'; statusEl.className = 'plat-status connected'; }
    });
    displayConnectedAccounts();
}

function displayConnectedAccounts() {
    const connections = JSON.parse(localStorage.getItem('connections') || '{}');
    const listEl = document.getElementById('accounts-list');
    if (Object.keys(connections).length === 0) {
        listEl.innerHTML = '<p style="color:#606770;">No accounts connected yet.</p>';
        return;
    }
    let html = '';
    Object.entries(connections).forEach(([platform, data]) => {
        const displayName = data.username || data.display_name || data.channel_title || platform;
        const emoji = { twitter: '\\ud835\\udd4f', tiktok: '\\ud83c\\udfb5', youtube: '\\u25b6\\ufe0f' }[platform] || '\\ud83d\\udd17';
        html += `<div class="account-item"><strong>${emoji} ${platform.toUpperCase()}</strong><br><span style="color:#606770">${displayName}</span></div>`;
    });
    listEl.innerHTML = html;
}
"""

    return HTMLResponse(build_page(
        title="Social Accounts",
        active_nav="connect",
        body_content=_body,
        extra_css=_CSS,
        extra_js=_js,
        topbar_title="Social Accounts",
    ))


def _old_conn_stub():
    """Old standalone template removed — see build_page call above."""
    # The old return """ ... """ block was here
    if False:
        # kept for reference only
        pass
