"""
Social Media Dashboard Routes - Unified interface for all platforms
Supports: Facebook, Instagram, WhatsApp, TikTok, Twitter/X, YouTube, Late API
"""

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse
import os
import json
import httpx
from datetime import datetime

router = APIRouter(prefix="/social", tags=["Social Media"])


def _check_connections(client_id: str = "default_client") -> dict:
    """Check real connection status for all platforms.

    Uses the PostgreSQL-backed checks (MetaOAuthToken, PlatformConnection,
    ClientProfile) so status survives Railway redeploys.  Env vars and
    cached JSON are checked as fast-path / fallback only.
    """
    status = {}

    # ── Meta platforms: DB-first, then env-var fallback ────────────────────
    has_meta = False
    ig_username = ""
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
                    has_meta = True
                    ig_username = _profile.meta_ig_username or "Connected via Meta"
        finally:
            _db.close()
    except Exception:
        pass
    # Env-var fallback (e.g. single-user dev setup)
    if not has_meta:
        has_meta = bool(os.getenv("INSTAGRAM_ACCESS_TOKEN"))
        if has_meta:
            ig_username = "Connected via Meta"
    status["instagram"] = {"connected": has_meta, "username": ig_username if has_meta else ""}
    status["facebook"] = {"connected": has_meta, "username": ig_username if has_meta else ""}

    # ── Late API platforms: DB + env vars + cached JSON ───────────────────
    # load_connections() in client_connections_routes already merges all 3
    # sources (JSON, DB, env vars), so reuse it when available.
    _all_conns: dict = {}
    try:
        from api.client_connections_routes import load_connections as _lc
        _all_conns = _lc().get(client_id, {})
        if not _all_conns and client_id != "default_client":
            _all_conns = _lc().get("default_client", {})
    except Exception:
        pass

    for platform in ["tiktok", "twitter", "threads", "linkedin", "youtube"]:
        conn_data = _all_conns.get(platform, {})
        # env-var fallback
        env_var = f"LATE_PROFILE_{platform.upper()}_{client_id}"
        profile_id = os.getenv(env_var)
        if not profile_id and client_id != "default_client":
            profile_id = os.getenv(f"LATE_PROFILE_{platform.upper()}_default_client")
        connected = bool(conn_data.get("profile_id") or conn_data.get("status") == "active" or profile_id)
        username = conn_data.get("username", "Connected via Late API" if connected else "")
        status[platform] = {"connected": connected, "username": username}

    # WhatsApp: env var only
    status["whatsapp"] = {"connected": bool(os.getenv("WHATSAPP_ACCESS_TOKEN")), "username": ""}

    return status


@router.get("/dashboard", response_class=HTMLResponse)
async def social_dashboard(request: Request, client_id: str = Query("default_client")):
    """Unified social media dashboard for all platforms."""
    
    conn = _check_connections(client_id)
    
    def _card(platform_key, icon, name, desc, color, manage_url, comments_url=None):
        c = conn.get(platform_key, {})
        is_connected = c.get("connected", False)
        username = c.get("username", "")
        
        status_html = f'<span class="status connected">Connected</span>' if is_connected else '<span class="status pending">Setup Required</span>'
        if is_connected and username and username not in ("Connected via Meta", "Connected via Late API", "Connected"):
            status_html = f'<span class="status connected">Connected &middot; @{username}</span>'
        
        buttons = ""
        if is_connected:
            buttons = f'<a href="{manage_url}" class="btn">Manage</a>'
            if comments_url:
                buttons += f' <a href="{comments_url}" class="btn secondary" style="margin-left: 10px;">View Comments</a>'
        else:
            buttons = f'<a href="/connect/dashboard?client_id={client_id}" class="btn">Connect</a>'
        
        return f"""
                <div class="platform-card" style="border-left-color: {color};">
                    <h3>{icon} {name}</h3>
                    <p>{desc}</p>
                    {status_html}
                    <br><br>
                    {buttons}
                </div>"""
    
    cards = "".join([
        _card("facebook", "📘", "Facebook Pages", "Manage posts, comments, and engagement on Facebook Pages", "#1877f2", "/comments/dashboard", "/comments/dashboard"),
        _card("instagram", "📷", "Instagram", "Post photos, videos, manage comments and messages", "#e1306c", "/comments/dashboard", "/comments/dashboard"),
        _card("tiktok", "🎵", "TikTok", "Upload videos, track analytics, view trending content", "#000000", "/comments/dashboard"),
        _card("twitter", "𝕏", "Twitter/X", "Post tweets, track engagement, search conversations", "#1da1f2", "/comments/dashboard"),
        _card("youtube", "🎥", "YouTube", "Upload videos, track analytics, manage playlists", "#ff0000", "/comments/dashboard"),
        _card("whatsapp", "💬", "WhatsApp Business", "Send messages, manage templates, business profile", "#25d366", "/messaging/dashboard"),
        _card("threads", "🧵", "Threads", "Post to Threads, manage comments, track engagement", "#000000", "/threads/dashboard", "/comments/dashboard"),
        _card("linkedin", "💼", "LinkedIn", "Post updates, articles, manage connections, B2B outreach", "#0077b5", "/comments/dashboard"),
    ])
    from database.db import get_db
    from utils.shared_layout import build_page, get_user_context

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

    _social_css = """
        <style>
            * { margin: 0; padding: 0; box-sizing: border-box; }
            body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background: #f8f9fa; }
            .container { max-width: 1400px; margin: 0 auto; padding: 20px; }
            .header { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 30px; border-radius: 10px; margin-bottom: 30px; }
            .header h1 { font-size: 32px; margin-bottom: 10px; }
            .header p { opacity: 0.9; }
            
            .platforms-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 20px; margin-bottom: 30px; }
            
            .platform-card {
                background: white;
                border-radius: 10px;
                padding: 20px;
                box-shadow: 0 2px 8px rgba(0,0,0,0.1);
                border-left: 4px solid #667eea;
                cursor: pointer;
                transition: all 0.3s ease;
            }
            
            .platform-card:hover { transform: translateY(-5px); box-shadow: 0 4px 16px rgba(0,0,0,0.15); }
            
            .platform-card h3 { margin-bottom: 10px; font-size: 20px; }
            .platform-card p { color: #666; font-size: 14px; margin-bottom: 15px; }
            
            .btn { padding: 10px 20px; background: #667eea; color: white; border: none; border-radius: 5px; cursor: pointer; font-size: 14px; text-decoration: none; display: inline-block; }
            .btn:hover { background: #764ba2; }
            .btn.secondary { background: #e9ecef; color: #333; }
            
            .metrics { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 15px; margin-bottom: 20px; }
            .metric-item { background: white; padding: 15px; border-radius: 8px; text-align: center; }
            .metric-item .value { font-size: 28px; font-weight: bold; color: #667eea; }
            .metric-item .label { color: #666; font-size: 12px; margin-top: 5px; }
            
            .status { display: inline-block; padding: 5px 10px; border-radius: 20px; font-size: 12px; font-weight: bold; }
            .status.connected { background: #d4edda; color: #155724; }
            .status.pending { background: #fff3cd; color: #856404; }
            .status.error { background: #f8d7da; color: #721c24; }
            .home-btn { position: fixed; top: 20px; left: 20px; padding: 10px 20px; background: white; color: #667eea; text-decoration: none; border-radius: 8px; font-weight: 600; box-shadow: 0 2px 8px rgba(0,0,0,0.2); z-index: 1000; }
            .home-btn:hover { background: #f8f9fa; }
            .back-btn { position: fixed; top: 20px; left: 120px; padding: 10px 20px; background: #f0f0f0; color: #333; text-decoration: none; border-radius: 8px; font-weight: 600; box-shadow: 0 2px 8px rgba(0,0,0,0.2); z-index: 1000; }
            .back-btn:hover { background: #e0e0e0; }
    """

    body_content = f"""
        <a href="/" class="home-btn">🏠 Home</a>
        <a href="/" class="back-btn">← Back</a>
        <div class="container">
            <div class="header">
                <h1>📱 Unified Social Media Dashboard</h1>
                <p>Manage all your social media platforms from one place</p>
            </div>
            
            <div class="platforms-grid">
                {cards}
            </div>
            
            <div style="background: white; padding: 20px; border-radius: 10px; margin-top: 30px;">
                <h2>📊 Analytics Overview</h2>
                <div class="metrics" id="metrics">
                    <div class="metric-item">
                        <div class="value">{sum(1 for c in conn.values() if c.get('connected'))}</div>
                        <div class="label">Platforms Connected</div>
                    </div>
                    <div class="metric-item">
                        <div class="value">-</div>
                        <div class="label">Total Engagement</div>
                    </div>
                    <div class="metric-item">
                        <div class="value">{sum(1 for c in conn.values() if c.get('connected'))}/8</div>
                        <div class="label">Platform Coverage</div>
                    </div>
                    <div class="metric-item">
                        <div class="value">-</div>
                        <div class="label">Average Reach</div>
                    </div>
                </div>
            </div>
    """

    return HTMLResponse(build_page(
        title="Growth",
        active_nav="social",
        body_content=body_content,
        extra_css=_social_css,
        user_name=_uname,
        business_name=_bname,
    ))



@router.get("/twitter/post")
async def twitter_post(text: str = Query(..., min_length=1, max_length=280)):
    """Post a tweet."""
    try:
        from api.twitter_client import TwitterClient
        
        client = TwitterClient()
        response = await client.post_tweet(text)
        
        return {
            "success": response.success,
            "tweet_id": response.tweet_id,
            "error": response.error
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/twitter/analytics/{tweet_id}")
async def twitter_analytics(tweet_id: str):
    """Get tweet analytics."""
    try:
        from api.twitter_client import TwitterClient
        
        client = TwitterClient()
        analytics = await client.get_tweet_analytics(tweet_id)
        
        return analytics
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/twitter/profile")
async def twitter_profile():
    """Get Twitter profile information."""
    try:
        from api.twitter_client import TwitterClient
        
        client = TwitterClient()
        profile = await client.get_user_profile()
        
        return profile
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/tiktok/profile")
async def tiktok_profile():
    """Get TikTok profile information."""
    try:
        from api.tiktok_client import TikTokClient
        
        client = TikTokClient()
        profile = await client.get_user_profile()
        
        return profile
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/tiktok/videos")
async def tiktok_videos(max_results: int = Query(10, le=100)):
    """Get TikTok videos."""
    try:
        from api.tiktok_client import TikTokClient
        
        client = TikTokClient()
        videos = await client.get_user_videos(max_results=max_results)
        
        return videos
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/tiktok/analytics/{video_id}")
async def tiktok_analytics(video_id: str):
    """Get TikTok video analytics."""
    try:
        from api.tiktok_client import TikTokClient
        
        client = TikTokClient()
        analytics = await client.get_video_analytics(video_id)
        
        return analytics
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/tiktok/trending/sounds")
async def tiktok_trending_sounds(max_results: int = Query(20, le=100)):
    """Get trending TikTok sounds."""
    try:
        from api.tiktok_client import TikTokClient
        
        client = TikTokClient()
        sounds = await client.get_trending_sounds(max_results=max_results)
        
        return sounds
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/youtube/channel")
async def youtube_channel():
    """Get YouTube channel information."""
    try:
        from api.youtube_client import YouTubeClient
        
        client = YouTubeClient()
        channel = await client.get_channel_info()
        
        return channel
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/youtube/videos")
async def youtube_videos(max_results: int = Query(10, le=50)):
    """Get YouTube channel videos."""
    try:
        from api.youtube_client import YouTubeClient
        
        client = YouTubeClient()
        videos = await client.get_channel_videos(max_results=max_results)
        
        return videos
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/youtube/analytics/{video_id}")
async def youtube_analytics(video_id: str):
    """Get YouTube video analytics."""
    try:
        from api.youtube_client import YouTubeClient
        
        client = YouTubeClient()
        analytics = await client.get_video_analytics(video_id)
        
        return analytics
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/youtube/trending")
async def youtube_trending(max_results: int = Query(10, le=50)):
    """Get trending YouTube videos."""
    try:
        from api.youtube_client import YouTubeClient
        
        client = YouTubeClient()
        videos = await client.get_trending_videos(max_results=max_results)
        
        return videos
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/late-api/status")
async def late_api_status():
    """Check Late API status and configured platforms."""
    try:
        from api.late_client import LateAPIClient
        
        api_key = os.getenv("LATE_API_KEY")
        if not api_key:
            return {"status": "not_configured", "message": "LATE_API_KEY not found in .env"}
        
        return {
            "status": "configured",
            "platforms": ["TikTok", "LinkedIn", "Twitter/X", "Threads", "Reddit", "Pinterest", "Bluesky"],
            "message": "Late API is configured and ready for multi-platform posting"
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}
