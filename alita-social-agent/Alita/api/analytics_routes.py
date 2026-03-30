"""
Analytics Routes - Multi-Platform Social Media Insights Dashboard

Provides real-time analytics from all connected platforms:
    GET  /analytics/dashboard             -> Unified analytics dashboard UI
    GET  /analytics/instagram/overview    -> Instagram account insights
    GET  /analytics/instagram/posts       -> Instagram post performance
    GET  /analytics/facebook/overview     -> Facebook page insights
    GET  /analytics/facebook/posts        -> Facebook post performance
    GET  /analytics/twitter/overview      -> Twitter/X insights (Late API)
    GET  /analytics/tiktok/overview       -> TikTok insights (Late API)
    GET  /analytics/youtube/overview      -> YouTube channel insights
    GET  /analytics/linkedin/overview     -> LinkedIn insights (Late API)
    GET  /analytics/threads/overview      -> Threads insights (Late API)
"""

import os
import httpx
from typing import Optional, Dict, Any
from fastapi import APIRouter, Request, Cookie, Query
from fastapi.responses import HTMLResponse, JSONResponse
from dotenv import load_dotenv

load_dotenv()

import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from api.meta_oauth import MetaOAuthClient
from api.token_manager import TokenManager

router = APIRouter(prefix="/analytics", tags=["Analytics"])

_oauth_client: Optional[MetaOAuthClient] = None
_token_manager: Optional[TokenManager] = None


def get_oauth_client() -> MetaOAuthClient:
    global _oauth_client
    if _oauth_client is None:
        _oauth_client = MetaOAuthClient()
    return _oauth_client


def get_token_manager() -> TokenManager:
    global _token_manager
    if _token_manager is None:
        _token_manager = TokenManager()
        _token_manager.initialize()
    return _token_manager


def _get_session_user(session_token: Optional[str]) -> Optional[str]:
    if not session_token:
        return None
    tm = get_token_manager()
    return tm.get_session_user(session_token)


# ─── Helper: Facebook Page Access Token ─────────────────────────────────

async def _get_page_access_token(page_id: str, user_access_token: str) -> Optional[str]:
    """Exchange user token for page token (required for page-level API calls)."""
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(
                f"https://graph.facebook.com/v22.0/{page_id}",
                params={"access_token": user_access_token, "fields": "access_token"},
            )
            response.raise_for_status()
            return response.json().get("access_token")
    except Exception:
        return None


# ═══════════════════════════════════════════════════════════════════════════
# Instagram (Meta Graph API v22 - updated metrics)
# ═══════════════════════════════════════════════════════════════════════════

async def fetch_instagram_insights(ig_user_id: str, access_token: str) -> Dict[str, Any]:
    """Fetch IG insights using v22-compatible metrics (split by metric_type)."""
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            # Call 1: time-series metrics (period=day, no metric_type needed)
            r1 = await client.get(
                f"https://graph.facebook.com/v22.0/{ig_user_id}/insights",
                params={"metric": "reach,follower_count", "period": "day", "access_token": access_token}
            )
            r1.raise_for_status()
            data1 = r1.json()

            # Call 2: total_value metrics (require metric_type=total_value)
            r2 = await client.get(
                f"https://graph.facebook.com/v22.0/{ig_user_id}/insights",
                params={
                    "metric": "profile_views,accounts_engaged,total_interactions",
                    "metric_type": "total_value",
                    "period": "day",
                    "access_token": access_token
                }
            )
            r2.raise_for_status()
            data2 = r2.json()

            insights = {}
            # Process time-series data
            for item in data1.get("data", []):
                name = item.get("name")
                values = item.get("values", [])
                if values:
                    total = sum(v.get("value", 0) for v in values)
                    latest = values[-1].get("value", 0)
                    insights[name] = {"total": total, "latest": latest}

            # Process total_value data
            for item in data2.get("data", []):
                name = item.get("name")
                tv = item.get("total_value", {})
                val = tv.get("value", 0)
                insights[name] = {"total": val, "latest": val}

            return {"success": True, "insights": insights}
    except Exception as e:
        return {"success": False, "error": str(e)}


async def fetch_instagram_media(ig_user_id: str, access_token: str, limit: int = 6) -> Dict[str, Any]:
    """Fetch recent IG posts with engagement data."""
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            r = await client.get(
                f"https://graph.facebook.com/v22.0/{ig_user_id}/media",
                params={
                    "fields": "id,caption,media_type,media_url,thumbnail_url,timestamp,like_count,comments_count",
                    "limit": limit,
                    "access_token": access_token
                }
            )
            r.raise_for_status()
            posts = r.json().get("data", [])
            return {"success": True, "posts": posts}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ═══════════════════════════════════════════════════════════════════════════
# Facebook (Page Access Token + New Page Experience compatible)
# ═══════════════════════════════════════════════════════════════════════════

async def fetch_facebook_overview(page_id: str, page_token: str) -> Dict[str, Any]:
    """Fetch FB page info (works with New Page Experience where page_insights is unavailable)."""
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            # Get page-level stats
            r = await client.get(
                f"https://graph.facebook.com/v22.0/{page_id}",
                params={
                    "fields": "name,fan_count,followers_count,talking_about_count,were_here_count,category",
                    "access_token": page_token
                }
            )
            r.raise_for_status()
            page_data = r.json()

            # Calculate engagement from recent posts
            r2 = await client.get(
                f"https://graph.facebook.com/v22.0/{page_id}/published_posts",
                params={
                    "fields": "likes.summary(true),comments.summary(true),shares,reactions.summary(true)",
                    "limit": 25,
                    "access_token": page_token
                }
            )
            total_likes = 0
            total_comments = 0
            total_shares = 0
            total_reactions = 0
            post_count = 0
            if r2.status_code == 200:
                for post in r2.json().get("data", []):
                    total_likes += post.get("likes", {}).get("summary", {}).get("total_count", 0)
                    total_comments += post.get("comments", {}).get("summary", {}).get("total_count", 0)
                    total_shares += post.get("shares", {}).get("count", 0)
                    total_reactions += post.get("reactions", {}).get("summary", {}).get("total_count", 0)
                    post_count += 1

            return {
                "success": True,
                "page": {
                    "name": page_data.get("name", ""),
                    "category": page_data.get("category", ""),
                    "followers": page_data.get("followers_count", 0),
                    "fans": page_data.get("fan_count", 0),
                    "talking_about": page_data.get("talking_about_count", 0),
                },
                "engagement": {
                    "total_likes": total_likes,
                    "total_comments": total_comments,
                    "total_shares": total_shares,
                    "total_reactions": total_reactions,
                    "posts_analyzed": post_count
                }
            }
    except Exception as e:
        return {"success": False, "error": str(e)}


async def fetch_facebook_posts(page_id: str, page_token: str, limit: int = 6) -> Dict[str, Any]:
    """Fetch FB page posts with engagement metrics."""
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            r = await client.get(
                f"https://graph.facebook.com/v22.0/{page_id}/published_posts",
                params={
                    "fields": "id,message,created_time,full_picture,permalink_url,likes.summary(true),comments.summary(true),shares,reactions.summary(true)",
                    "limit": limit,
                    "access_token": page_token
                }
            )
            r.raise_for_status()
            posts = []
            for post in r.json().get("data", []):
                posts.append({
                    "id": post.get("id"),
                    "message": post.get("message", ""),
                    "created_time": post.get("created_time", ""),
                    "full_picture": post.get("full_picture"),
                    "permalink_url": post.get("permalink_url"),
                    "likes": post.get("likes", {}).get("summary", {}).get("total_count", 0),
                    "comments": post.get("comments", {}).get("summary", {}).get("total_count", 0),
                    "shares": post.get("shares", {}).get("count", 0),
                    "reactions": post.get("reactions", {}).get("summary", {}).get("total_count", 0),
                })
            return {"success": True, "posts": posts}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ═══════════════════════════════════════════════════════════════════════════
# Late API (Twitter, TikTok, LinkedIn, Threads)
# ═══════════════════════════════════════════════════════════════════════════

def _late_headers() -> Dict[str, str]:
    return {
        "Authorization": f"Bearer {os.getenv('LATE_API_KEY', '')}",
        "Content-Type": "application/json",
        "User-Agent": "Alita-AI-Agent/1.0"
    }

LATE_BASE = "https://getlate.dev/api/v1"


async def fetch_late_platform_data(platform: str, account_id: str) -> Dict[str, Any]:
    """
    Fetch platform-specific data from Late API.
    Uses /analytics?platform=X for real per-post analytics (impressions, likes, etc.).
    Uses /accounts for account info + follower counts.
    Uses /accounts/follower-stats for follower growth history.
    """
    api_key = os.getenv("LATE_API_KEY")
    if not api_key:
        return {"success": False, "error": "Late API key not configured"}

    headers = _late_headers()
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            # 1) Account info (includes followerCount with analytics add-on)
            account_info = {}
            try:
                r_acc = await client.get(f"{LATE_BASE}/accounts", headers=headers)
                if r_acc.status_code == 200:
                    for acc in r_acc.json().get("accounts", []):
                        if acc.get("_id") == account_id:
                            account_info = acc
                            break
            except Exception:
                pass

            # 2) Real analytics via /analytics?platform=X (per-post metrics)
            posts = []
            overview = {}
            try:
                r_analytics = await client.get(
                    f"{LATE_BASE}/analytics",
                    headers=headers,
                    params={"platform": platform, "limit": 12, "sortBy": "date", "order": "desc"}
                )
                if r_analytics.status_code == 200:
                    data = r_analytics.json()
                    overview = data.get("overview", {})
                    for p in data.get("posts", []):
                        a = p.get("analytics", {})
                        posts.append({
                            "id": p.get("_id", ""),
                            "content": p.get("content", ""),
                            "published_at": p.get("publishedAt", ""),
                            "platform_post_url": p.get("platformPostUrl", ""),
                            "impressions": a.get("impressions", 0),
                            "reach": a.get("reach", 0),
                            "likes": a.get("likes", 0),
                            "comments": a.get("comments", 0),
                            "shares": a.get("shares", 0),
                            "saves": a.get("saves", 0),
                            "clicks": a.get("clicks", 0),
                            "views": a.get("views", 0),
                            "engagement_rate": a.get("engagementRate", 0),
                            "last_updated": a.get("lastUpdated", ""),
                        })
            except Exception:
                pass

            # 3) Follower stats history
            follower_history = []
            try:
                r_fs = await client.get(
                    f"{LATE_BASE}/accounts/follower-stats",
                    headers=headers,
                    params={"accountIds": account_id}
                )
                if r_fs.status_code == 200:
                    stats = r_fs.json().get("stats", {})
                    follower_history = stats.get(account_id, [])
            except Exception:
                pass

            # Aggregate totals from all posts
            total_impressions = sum(p.get("impressions", 0) for p in posts)
            total_likes = sum(p.get("likes", 0) for p in posts)
            total_comments = sum(p.get("comments", 0) for p in posts)
            total_shares = sum(p.get("shares", 0) for p in posts)
            total_views = sum(p.get("views", 0) for p in posts)
            total_clicks = sum(p.get("clicks", 0) for p in posts)
            total_saves = sum(p.get("saves", 0) for p in posts)
            total_reach = sum(p.get("reach", 0) for p in posts)

            return {
                "success": True,
                "account": {
                    "display_name": account_info.get("displayName", ""),
                    "username": account_info.get("username", ""),
                    "platform": account_info.get("platform", platform),
                    "is_active": account_info.get("isActive", False),
                    "profile_picture": account_info.get("profilePicture", ""),
                    "profile_url": account_info.get("profileUrl", ""),
                    "followers": account_info.get("followersCount", 0),
                },
                "overview": {
                    "total_posts": overview.get("totalPosts", len(posts)),
                    "published_posts": overview.get("publishedPosts", len(posts)),
                    "last_sync": overview.get("lastSync", ""),
                },
                "totals": {
                    "impressions": total_impressions,
                    "reach": total_reach,
                    "likes": total_likes,
                    "comments": total_comments,
                    "shares": total_shares,
                    "views": total_views,
                    "clicks": total_clicks,
                    "saves": total_saves,
                },
                "posts": posts,
                "post_count": len(posts),
                "follower_history": follower_history,
            }
    except Exception as e:
        return {"success": False, "error": str(e)}


# ═══════════════════════════════════════════════════════════════════════════
# YouTube (Native API)
# ═══════════════════════════════════════════════════════════════════════════

async def fetch_youtube_data() -> Dict[str, Any]:
    """Fetch YouTube channel stats and recent videos."""
    api_key = os.getenv("YOUTUBE_API_KEY")
    channel_id = os.getenv("YOUTUBE_CHANNEL_ID")

    # If no channel ID, try Late API
    if not channel_id or not api_key:
        yt_account = os.getenv("LATE_PROFILE_YOUTUBE_default_client")
        if yt_account:
            return await fetch_late_platform_data("youtube", yt_account)
        return {"success": False, "error": "YouTube not configured"}

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            # Channel info
            r = await client.get(
                "https://www.googleapis.com/youtube/v3/channels",
                params={"key": api_key, "part": "snippet,statistics", "id": channel_id}
            )
            r.raise_for_status()
            items = r.json().get("items", [])
            if not items:
                return {"success": False, "error": "Channel not found"}

            ch = items[0]
            stats = ch.get("statistics", {})
            snippet = ch.get("snippet", {})

            # Recent videos
            sr = await client.get(
                "https://www.googleapis.com/youtube/v3/search",
                params={
                    "key": api_key, "channelId": channel_id,
                    "part": "snippet", "order": "date", "maxResults": 6, "type": "video"
                }
            )
            videos = []
            if sr.status_code == 200:
                video_ids = [i["id"]["videoId"] for i in sr.json().get("items", []) if i.get("id", {}).get("videoId")]
                if video_ids:
                    vr = await client.get(
                        "https://www.googleapis.com/youtube/v3/videos",
                        params={"key": api_key, "part": "snippet,statistics", "id": ",".join(video_ids)}
                    )
                    if vr.status_code == 200:
                        for v in vr.json().get("items", []):
                            s = v.get("statistics", {})
                            sn = v.get("snippet", {})
                            videos.append({
                                "title": sn.get("title", ""),
                                "thumbnail": sn.get("thumbnails", {}).get("medium", {}).get("url", ""),
                                "views": int(s.get("viewCount", 0)),
                                "likes": int(s.get("likeCount", 0)),
                                "comments": int(s.get("commentCount", 0)),
                            })

            return {
                "success": True,
                "channel": {
                    "title": snippet.get("title", ""),
                    "thumbnail": snippet.get("thumbnails", {}).get("default", {}).get("url", ""),
                    "subscribers": int(stats.get("subscriberCount", 0)),
                    "total_views": int(stats.get("viewCount", 0)),
                    "video_count": int(stats.get("videoCount", 0)),
                },
                "videos": videos
            }
    except Exception as e:
        return {"success": False, "error": str(e)}


# ═══════════════════════════════════════════════════════════════════════════
# Dashboard UI
# ═══════════════════════════════════════════════════════════════════════════

DASHBOARD_CSS = """
* { margin: 0; padding: 0; box-sizing: border-box; }
body {
    font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
    background: #f0f2f5;
    color: #1c1e21;
}
.nav-bar {
    background: #fff;
    border-bottom: 1px solid #e4e6eb;
    padding: 16px 24px;
    display: flex;
    justify-content: space-between;
    align-items: center;
}
.brand { font-size: 20px; font-weight: 700; }
.nav-links a {
    color: #606770; text-decoration: none; margin-left: 24px; font-size: 14px;
}
.nav-links a:hover { color: #1c1e21; }
.container { max-width: 1400px; margin: 0 auto; padding: 24px; }
.header { margin-bottom: 32px; }
.header h1 { font-size: 28px; }
.platform-tabs {
    display: flex; gap: 4px; margin-bottom: 32px;
    border-bottom: 2px solid #e4e6eb; overflow-x: auto;
}
.platform-tab {
    padding: 12px 18px; background: transparent; border: none;
    color: #606770; cursor: pointer; font-size: 14px; font-weight: 600;
    border-bottom: 3px solid transparent; transition: all 0.2s; white-space: nowrap;
}
.platform-tab.active { color: #5c6ac4; border-bottom-color: #5c6ac4; }
.platform-tab:hover { color: #1c1e21; }
.metrics-grid {
    display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
    gap: 16px; margin-bottom: 24px;
}
.metric-card {
    background: #fff; border: 1px solid #e4e6eb; border-radius: 12px; padding: 20px;
}
.metric-label {
    color: #606770; font-size: 12px; text-transform: uppercase;
    letter-spacing: 0.5px; margin-bottom: 6px;
}
.metric-value { font-size: 28px; font-weight: 700; color: #1c1e21; margin-bottom: 4px; }
.metric-sub { font-size: 12px; color: #2e7d32; }
.section-card {
    background: #fff; border: 1px solid #e4e6eb; border-radius: 12px;
    padding: 24px; margin-bottom: 24px;
}
.section-title { font-size: 18px; font-weight: 600; margin-bottom: 16px; }
.posts-grid {
    display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 16px;
}
.post-card {
    background: #f8f9fb; border: 1px solid #e4e6eb; border-radius: 12px; overflow: hidden;
}
.post-img { width: 100%; height: 180px; object-fit: cover; }
.post-body { padding: 14px; }
.post-text {
    color: #1c1e21; font-size: 13px; margin-bottom: 10px;
    display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical;
    overflow: hidden; line-height: 1.4;
}
.post-metrics {
    display: flex; gap: 14px; flex-wrap: wrap; font-size: 12px; color: #606770;
}
.post-metrics span { display: flex; align-items: center; gap: 4px; }
.loading { text-align: center; padding: 60px; color: #606770; font-size: 14px; }
.error-box {
    background: rgba(228,64,95,0.1); border: 1px solid rgba(228,64,95,0.3);
    color: #c62828; padding: 16px 20px; border-radius: 8px; font-size: 14px;
}
.not-connected { text-align: center; padding: 40px; color: #606770; }
.platform-content { display: none; }
.platform-content.active { display: block; }
.account-header {
    display: flex; align-items: center; gap: 16px; margin-bottom: 24px;
    padding: 16px; background: #fff; border: 1px solid #e4e6eb; border-radius: 12px;
}
.account-header img {
    width: 48px; height: 48px; border-radius: 50%; object-fit: cover;
}
.account-header .account-name { font-size: 18px; font-weight: 600; }
.account-header .account-handle { font-size: 14px; color: #606770; }
"""

DASHBOARD_JS = """
var currentPlatform = 'instagram';

function switchPlatform(platform) {
    document.querySelectorAll('.platform-tab').forEach(function(t) { t.classList.remove('active'); });
    event.target.classList.add('active');
    document.querySelectorAll('.platform-content').forEach(function(c) { c.classList.remove('active'); });
    document.getElementById(platform + '-analytics').classList.add('active');
    currentPlatform = platform;
}

function num(n) {
    if (n === undefined || n === null) return '0';
    n = Number(n);
    if (isNaN(n)) return '0';
    if (n >= 1000000) return (n / 1000000).toFixed(1) + 'M';
    if (n >= 1000) return (n / 1000).toFixed(1) + 'K';
    return n.toLocaleString();
}

function trunc(s, len) {
    if (!s) return 'No caption';
    return s.length > len ? s.substring(0, len) + '...' : s;
}

function mc(label, value, sub) {
    return '<div class="metric-card"><div class="metric-label">' + label +
        '</div><div class="metric-value">' + value +
        '</div>' + (sub ? '<div class="metric-sub">' + sub + '</div>' : '') + '</div>';
}

function pc(img, text, metrics) {
    return '<div class="post-card">' +
        (img ? '<img src="' + img + '" class="post-img" alt="Post" onerror="this.style.display=\\'none\\'">' : '') +
        '<div class="post-body"><div class="post-text">' + trunc(text, 120) +
        '</div><div class="post-metrics">' + metrics + '</div></div></div>';
}

function showErr(id, msg) {
    document.getElementById(id).innerHTML = '<div class="error-box">' + msg + '</div>';
}

function showNC(id, platform) {
    document.getElementById(id).innerHTML =
        '<div class="not-connected"><p style="font-size:24px;margin-bottom:12px;">Not Connected</p>' +
        '<p>' + platform + ' is not connected yet.</p></div>';
}

function accountHeader(pic, name, handle) {
    var imgTag = pic ? '<img src="' + pic + '" alt="">' : '';
    return '<div class="account-header">' + imgTag +
        '<div><div class="account-name">' + (name || '') +
        '</div><div class="account-handle">@' + (handle || '') + '</div></div></div>';
}

// ─── Instagram ──────────────────────────────────────────────
async function loadInstagram() {
    var el = document.getElementById('instagram-analytics');
    try {
        var responses = await Promise.all([
            fetch('/analytics/instagram/overview'),
            fetch('/analytics/instagram/posts?limit=6')
        ]);
        var ov = await responses[0].json();
        var pd = await responses[1].json();

        if (!ov.success) { showErr('instagram-analytics', ov.error || 'Could not load Instagram data'); return; }

        var ins = ov.insights || {};
        var html = '<div class="metrics-grid">';
        html += mc('Reach', num(ins.reach ? ins.reach.total : 0), 'Last 7 days');
        html += mc('Profile Views', num(ins.profile_views ? ins.profile_views.total : 0), 'Last 7 days');
        html += mc('Accounts Engaged', num(ins.accounts_engaged ? ins.accounts_engaged.total : 0), 'Last 7 days');
        html += mc('Interactions', num(ins.total_interactions ? ins.total_interactions.total : 0), 'Last 7 days');
        html += mc('Followers', num(ins.follower_count ? ins.follower_count.latest : 0), 'Current');
        html += '</div>';

        var posts = pd.success ? (pd.posts || []) : [];
        if (posts.length > 0) {
            html += '<div class="section-card"><div class="section-title">Recent Posts</div><div class="posts-grid">';
            posts.forEach(function(p) {
                var m = '<span>&#10084; ' + num(p.like_count) + '</span>' +
                        '<span>&#128172; ' + num(p.comments_count) + '</span>';
                html += pc(p.media_url || p.thumbnail_url, p.caption, m);
            });
            html += '</div></div>';
        }
        el.innerHTML = html;
    } catch(e) { showErr('instagram-analytics', 'Failed to load Instagram analytics.'); }
}

// ─── Facebook ───────────────────────────────────────────────
async function loadFacebook() {
    var el = document.getElementById('facebook-analytics');
    try {
        var responses = await Promise.all([
            fetch('/analytics/facebook/overview'),
            fetch('/analytics/facebook/posts?limit=6')
        ]);
        var ov = await responses[0].json();
        var pd = await responses[1].json();

        if (!ov.success) { showErr('facebook-analytics', ov.error || 'Could not load Facebook data'); return; }

        var pg = ov.page || {};
        var eng = ov.engagement || {};
        var html = '<div class="metrics-grid">';
        html += mc('Followers', num(pg.followers), 'Current');
        html += mc('Page Likes', num(pg.fans), 'Current');
        html += mc('Post Reactions', num(eng.total_reactions), 'Last ' + num(eng.posts_analyzed) + ' posts');
        html += mc('Comments', num(eng.total_comments), 'Last ' + num(eng.posts_analyzed) + ' posts');
        html += mc('Shares', num(eng.total_shares), 'Last ' + num(eng.posts_analyzed) + ' posts');
        html += '</div>';

        var posts = pd.success ? (pd.posts || []) : [];
        if (posts.length > 0) {
            html += '<div class="section-card"><div class="section-title">Recent Posts</div><div class="posts-grid">';
            posts.forEach(function(p) {
                var m = '<span>&#10084; ' + num(p.reactions || p.likes) + '</span>' +
                        '<span>&#128172; ' + num(p.comments) + '</span>' +
                        '<span>&#128260; ' + num(p.shares) + '</span>';
                html += pc(p.full_picture, p.message, m);
            });
            html += '</div></div>';
        }
        el.innerHTML = html;
    } catch(e) { showErr('facebook-analytics', 'Failed to load Facebook analytics.'); }
}

// ─── Late API Platform Loader ───────────────────────────────
async function loadLatePlatform(platform, displayName, containerId) {
    var el = document.getElementById(containerId);
    try {
        var res = await fetch('/analytics/' + platform + '/overview');
        var data = await res.json();
        if (!data.success) { showNC(containerId, displayName); return; }

        var acct = data.account || {};
        var posts = data.posts || [];
        var totals = data.totals || {};
        var ov = data.overview || {};
        var fh = data.follower_history || [];

        var html = '';
        if (acct.display_name || acct.username) {
            html += accountHeader(acct.profile_picture, acct.display_name, acct.username);
        }

        // Key metrics from real analytics
        html += '<div class="metrics-grid">';
        html += mc('Followers', num(acct.followers), 'Current');
        html += mc('Posts', num(ov.total_posts || data.post_count), 'Tracked');
        html += mc('Impressions', num(totals.impressions), 'Total');
        if (totals.reach > 0) html += mc('Reach', num(totals.reach), 'Total');
        html += mc('Likes', num(totals.likes), 'Total');
        html += mc('Comments', num(totals.comments), 'Total');
        if (totals.shares > 0) html += mc('Shares', num(totals.shares), 'Total');
        if (totals.views > 0) html += mc('Views', num(totals.views), 'Total');
        if (totals.clicks > 0) html += mc('Clicks', num(totals.clicks), 'Total');
        if (totals.saves > 0) html += mc('Saves', num(totals.saves), 'Total');
        html += '</div>';

        // Follower history chart
        if (fh.length > 1) {
            html += '<div class="section-card"><div class="section-title">Follower Growth (Last ' + fh.length + ' Days)</div>';
            html += '<div style="display:flex;align-items:flex-end;gap:4px;height:80px;padding:10px 0;">';
            var maxF = Math.max.apply(null, fh.map(function(x){return x.followers||0;})) || 1;
            fh.forEach(function(day) {
                var pct = Math.max(4, ((day.followers||0)/maxF)*100);
                html += '<div title="' + day.date + ': ' + num(day.followers) + ' followers" style="flex:1;background:#5c6ac4;border-radius:3px 3px 0 0;height:' + pct + '%;min-width:8px;"></div>';
            });
            html += '</div></div>';
        }

        // Posts with real engagement data
        if (posts.length > 0) {
            html += '<div class="section-card"><div class="section-title">Post Performance on ' + displayName + '</div><div class="posts-grid">';
            posts.forEach(function(p) {
                var text = p.content || '';
                var m = '';
                if (p.impressions > 0) m += '<span>👁 ' + num(p.impressions) + '</span>';
                if (p.reach > 0) m += '<span>🌐 ' + num(p.reach) + '</span>';
                m += '<span>❤ ' + num(p.likes) + '</span>';
                m += '<span>💬 ' + num(p.comments) + '</span>';
                if (p.shares > 0) m += '<span>🔁 ' + num(p.shares) + '</span>';
                if (p.views > 0) m += '<span>▶ ' + num(p.views) + '</span>';
                if (p.engagement_rate > 0) m += '<span>📈 ' + p.engagement_rate.toFixed(1) + '%</span>';
                if (p.platform_post_url) m += '<span><a href="' + p.platform_post_url + '" target="_blank" style="color:#5c6ac4;text-decoration:none;">View ↗</a></span>';
                html += pc(null, text, m);
            });
            html += '</div></div>';
        } else {
            html += '<div class="section-card"><div class="section-title">Posts</div>' +
                    '<p style="color:#606770;">No posts published to ' + displayName + ' yet.</p></div>';
        }

        if (ov.last_sync) {
            html += '<p style="color:#555;font-size:11px;text-align:right;margin-top:8px;">Last sync: ' + new Date(ov.last_sync).toLocaleString() + '</p>';
        }
        el.innerHTML = html;
    } catch(e) { showNC(containerId, displayName); }
}

// ─── YouTube ────────────────────────────────────────────────
async function loadYouTube() {
    var el = document.getElementById('youtube-analytics');
    try {
        var res = await fetch('/analytics/youtube/overview');
        var data = await res.json();
        if (!data.success) { showNC('youtube-analytics', 'YouTube'); return; }

        var ch = data.channel || {};
        var acct = data.account || {};
        var videos = data.videos || [];
        var posts = data.posts || [];
        var totals = data.totals || {};
        var fh = data.follower_history || [];

        var html = '';

        // If we have channel data (native YouTube API)
        if (ch.subscribers !== undefined) {
            html += '<div class="metrics-grid">';
            html += mc('Subscribers', num(ch.subscribers), 'Current');
            html += mc('Total Views', num(ch.total_views), 'Lifetime');
            html += mc('Videos', num(ch.video_count), 'Published');
            html += '</div>';
        } else if (acct.display_name) {
            html += accountHeader(acct.profile_picture, acct.display_name, acct.username);
            html += '<div class="metrics-grid">';
            html += mc('Followers', num(acct.followers || 0), 'Current');
            html += mc('Posts', num(posts.length), 'Tracked');
            if (totals.impressions > 0) html += mc('Impressions', num(totals.impressions), 'Total');
            if (totals.likes > 0) html += mc('Likes', num(totals.likes), 'Total');
            if (totals.views > 0) html += mc('Views', num(totals.views), 'Total');
            html += '</div>';
        }

        // Follower/sub history
        if (fh.length > 1) {
            html += '<div class="section-card"><div class="section-title">Subscriber Growth (Last ' + fh.length + ' Days)</div>';
            html += '<div style="display:flex;align-items:flex-end;gap:4px;height:80px;padding:10px 0;">';
            var maxF = Math.max.apply(null, fh.map(function(x){return x.followers||0;})) || 1;
            fh.forEach(function(day) {
                var pct = Math.max(4, ((day.followers||0)/maxF)*100);
                html += '<div title="' + day.date + ': ' + num(day.followers) + ' subs" style="flex:1;background:#ff0000;border-radius:3px 3px 0 0;height:' + pct + '%;min-width:8px;"></div>';
            });
            html += '</div></div>';
        }

        if (videos.length > 0) {
            html += '<div class="section-card"><div class="section-title">Recent Videos</div><div class="posts-grid">';
            videos.forEach(function(v) {
                var m = '<span>&#128065; ' + num(v.views) + '</span>' +
                        '<span>&#128077; ' + num(v.likes) + '</span>' +
                        '<span>&#128172; ' + num(v.comments) + '</span>';
                html += pc(v.thumbnail, v.title, m);
            });
            html += '</div></div>';
        } else if (posts.length > 0) {
            html += '<div class="section-card"><div class="section-title">Post Performance</div><div class="posts-grid">';
            posts.forEach(function(p) {
                var m = '';
                if (p.impressions > 0) m += '<span>👁 ' + num(p.impressions) + '</span>';
                m += '<span>❤ ' + num(p.likes) + '</span>';
                m += '<span>💬 ' + num(p.comments) + '</span>';
                if (p.views > 0) m += '<span>▶ ' + num(p.views) + '</span>';
                if (p.platform_post_url) m += '<span><a href="' + p.platform_post_url + '" target="_blank" style="color:#ff0000;text-decoration:none;">Watch ↗</a></span>';
                html += pc(null, p.content, m);
            });
            html += '</div></div>';
        } else {
            html += '<div class="section-card"><div class="section-title">Videos</div>' +
                    '<p style="color:#606770;">No YouTube videos found.</p></div>';
        }
        el.innerHTML = html;
    } catch(e) { showNC('youtube-analytics', 'YouTube'); }
}

// ─── AI Insights ───────────────────────────────────────────
async function loadAIInsights() {
    var btn = document.getElementById('ai-insights-btn');
    var el  = document.getElementById('ai-insights-result');
    btn.disabled = true;
    btn.textContent = '⏳ Analyzing…';
    el.innerHTML = '<div class="loading" style="padding:32px;text-align:center">Alita AI is reading your platform metrics… this may take 15–30 seconds.</div>';
    try {
        var res = await fetch('/analytics/ai-insights');
        var d   = await res.json();
        if (!d.success) { el.innerHTML = '<div class="error-box">' + (d.error || 'Failed to generate insights.') + '</div>'; return; }

        var insHtml = (d.insights || []).map(function(i) {
            return '<li style="margin-bottom:8px;font-size:.88rem;line-height:1.5">' + i + '</li>';
        }).join('');
        var recHtml = (d.recommendations || []).map(function(r) {
            return '<li style="margin-bottom:8px;font-size:.88rem;line-height:1.5">' + r + '</li>';
        }).join('');

        var aggKeys = Object.keys(d.aggregates || {});
        var aggHtml = aggKeys.length ? aggKeys.map(function(k) {
            var v = d.aggregates[k];
            return mc(k.replace(/_/g,' ').replace(/\\b\\w/g,function(c){return c.toUpperCase();}), num(v), null);
        }).join('') : '<p style="color:#606770;font-size:.84rem">No aggregate data available.</p>';

        el.innerHTML =
            '<div style="display:grid;gap:16px">' +
            '<div style="background:#fff;border:1px solid #e4e6eb;border-radius:12px;padding:20px">' +
            '<h3 style="font-size:.95rem;font-weight:700;margin-bottom:12px;color:#1c1e21">&#128200; Cross-Platform Aggregates</h3>' +
            '<div class="metrics-grid">' + aggHtml + '</div></div>' +
            '<div style="background:#fff;border:1px solid #e4e6eb;border-radius:12px;padding:20px">' +
            '<h3 style="font-size:.95rem;font-weight:700;margin-bottom:12px;color:#1c1e21">&#128161; AI Insights</h3>' +
            '<ul style="padding-left:20px;margin:0">' + (insHtml || '<li>No insights generated.</li>') + '</ul></div>' +
            '<div style="background:#fff;border:1px solid #e4e6eb;border-radius:12px;padding:20px">' +
            '<h3 style="font-size:.95rem;font-weight:700;margin-bottom:12px;color:#1c1e21">&#128640; Recommendations</h3>' +
            '<ul style="padding-left:20px;margin:0">' + (recHtml || '<li>No recommendations generated.</li>') + '</ul></div></div>';
    } catch(e) {
        el.innerHTML = '<div class="error-box">Error: ' + e.message + '</div>';
    } finally {
        btn.disabled = false;
        btn.textContent = '⚡ Regenerate Insights';
    }
}

// ─── Init ───────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', function() {
    loadInstagram();
    loadFacebook();
    loadLatePlatform('twitter', 'Twitter / X', 'twitter-analytics');
    loadLatePlatform('tiktok', 'TikTok', 'tiktok-analytics');
    loadYouTube();
    loadLatePlatform('linkedin', 'LinkedIn', 'linkedin-analytics');
    loadLatePlatform('threads', 'Threads', 'threads-analytics');
});
"""


@router.get("/dashboard", response_class=HTMLResponse)
async def analytics_dashboard(
    request: Request,
    session: Optional[str] = Cookie(None, alias="alita_session")
):
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

    u_name = user_obj.full_name if user_obj else "User"
    b_name = profile.business_name if profile else "My Business"

    body = """
        <div class="header"><h1>&#128202; Social Media Analytics</h1></div>
        <div class="platform-tabs">
            <button class="platform-tab active" onclick="switchPlatform('instagram')">Instagram</button>
            <button class="platform-tab" onclick="switchPlatform('facebook')">Facebook</button>
            <button class="platform-tab" onclick="switchPlatform('twitter')">Twitter / X</button>
            <button class="platform-tab" onclick="switchPlatform('tiktok')">TikTok</button>
            <button class="platform-tab" onclick="switchPlatform('youtube')">YouTube</button>
            <button class="platform-tab" onclick="switchPlatform('linkedin')">LinkedIn</button>
            <button class="platform-tab" onclick="switchPlatform('threads')">Threads</button>
            <button class="platform-tab" onclick="switchPlatform('ai_insights')" style="color:#7b1fa2">&#129504; AI Insights</button>
        </div>
        <div id="instagram-analytics" class="platform-content active"><div class="loading">Loading Instagram insights...</div></div>
        <div id="facebook-analytics" class="platform-content"><div class="loading">Loading Facebook insights...</div></div>
        <div id="twitter-analytics" class="platform-content"><div class="loading">Loading Twitter / X insights...</div></div>
        <div id="tiktok-analytics" class="platform-content"><div class="loading">Loading TikTok insights...</div></div>
        <div id="youtube-analytics" class="platform-content"><div class="loading">Loading YouTube insights...</div></div>
        <div id="linkedin-analytics" class="platform-content"><div class="loading">Loading LinkedIn insights...</div></div>
        <div id="threads-analytics" class="platform-content"><div class="loading">Loading Threads insights...</div></div>
        <div id="ai_insights-analytics" class="platform-content">
            <div style="background:#fff;border:1px solid #e4e6eb;border-radius:12px;padding:24px;margin-bottom:20px">
                <div style="display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:12px">
                    <div>
                        <h2 style="font-size:1.1rem;font-weight:700;margin-bottom:6px">&#129504; AI-Powered Cross-Platform Insights</h2>
                        <p style="font-size:.84rem;color:#606770">Alita AI reads all connected platform metrics and generates insights + recommendations via AnalyticsAgent.</p>
                    </div>
                    <button onclick="loadAIInsights()" id="ai-insights-btn"
                        style="background:linear-gradient(135deg,#7b1fa2,#5c6ac4);color:#fff;border:none;border-radius:10px;padding:10px 20px;font-size:.86rem;font-weight:700;cursor:pointer">
                        &#9889; Generate Insights
                    </button>
                </div>
            </div>
            <div id="ai-insights-result"></div>
        </div>
    """

    return HTMLResponse(build_page(
        title="Analytics",
        active_nav="analytics",
        body_content=body,
        extra_css=DASHBOARD_CSS,
        extra_js=DASHBOARD_JS,
        user_name=u_name,
        business_name=b_name,
    ))


# ═══════════════════════════════════════════════════════════════════════════
# API Endpoints
# ═══════════════════════════════════════════════════════════════════════════

@router.get("/instagram/overview")
async def instagram_overview(session: Optional[str] = Cookie(None, alias="alita_session")):
    user_id = _get_session_user(session)
    if not user_id:
        return JSONResponse({"success": False, "error": "Not authenticated"}, status_code=401)
    tm = get_token_manager()
    token_data = tm.get_token(user_id)
    if not token_data or token_data.is_expired:
        return JSONResponse({"success": False, "error": "Token expired"}, status_code=401)
    ig_user_id = os.getenv("INSTAGRAM_BUSINESS_ACCOUNT_ID")
    if not ig_user_id:
        return JSONResponse({"success": False, "error": "Instagram Business Account not configured"}, status_code=400)
    return JSONResponse(await fetch_instagram_insights(ig_user_id, token_data.access_token))


@router.get("/instagram/posts")
async def instagram_posts(limit: int = Query(6, ge=1, le=50), session: Optional[str] = Cookie(None, alias="alita_session")):
    user_id = _get_session_user(session)
    if not user_id:
        return JSONResponse({"success": False, "error": "Not authenticated"}, status_code=401)
    tm = get_token_manager()
    token_data = tm.get_token(user_id)
    if not token_data or token_data.is_expired:
        return JSONResponse({"success": False, "error": "Token expired"}, status_code=401)
    ig_user_id = os.getenv("INSTAGRAM_BUSINESS_ACCOUNT_ID")
    if not ig_user_id:
        return JSONResponse({"success": False, "error": "Instagram Business Account not configured"}, status_code=400)
    return JSONResponse(await fetch_instagram_media(ig_user_id, token_data.access_token, limit))


@router.get("/facebook/overview")
async def facebook_overview(session: Optional[str] = Cookie(None, alias="alita_session")):
    user_id = _get_session_user(session)
    if not user_id:
        return JSONResponse({"success": False, "error": "Not authenticated"}, status_code=401)
    tm = get_token_manager()
    token_data = tm.get_token(user_id)
    if not token_data or token_data.is_expired:
        return JSONResponse({"success": False, "error": "Token expired"}, status_code=401)
    page_id = os.getenv("FACEBOOK_PAGE_ID")
    if not page_id:
        return JSONResponse({"success": False, "error": "Facebook Page not configured"}, status_code=400)
    # Get page access token
    page_token = await _get_page_access_token(page_id, token_data.access_token)
    if not page_token:
        page_token = os.getenv("FACEBOOK_PAGE_ACCESS_TOKEN")
    if not page_token:
        return JSONResponse({"success": False, "error": "Could not get page access token"}, status_code=400)
    return JSONResponse(await fetch_facebook_overview(page_id, page_token))


@router.get("/facebook/posts")
async def facebook_posts_endpoint(limit: int = Query(6, ge=1, le=50), session: Optional[str] = Cookie(None, alias="alita_session")):
    user_id = _get_session_user(session)
    if not user_id:
        return JSONResponse({"success": False, "error": "Not authenticated"}, status_code=401)
    tm = get_token_manager()
    token_data = tm.get_token(user_id)
    if not token_data or token_data.is_expired:
        return JSONResponse({"success": False, "error": "Token expired"}, status_code=401)
    page_id = os.getenv("FACEBOOK_PAGE_ID")
    if not page_id:
        return JSONResponse({"success": False, "error": "Facebook Page not configured"}, status_code=400)
    page_token = await _get_page_access_token(page_id, token_data.access_token)
    if not page_token:
        page_token = os.getenv("FACEBOOK_PAGE_ACCESS_TOKEN")
    if not page_token:
        return JSONResponse({"success": False, "error": "Could not get page access token"}, status_code=400)
    return JSONResponse(await fetch_facebook_posts(page_id, page_token, limit))


@router.get("/twitter/overview")
async def twitter_overview():
    account_id = os.getenv("LATE_PROFILE_TWITTER_default_client")
    if not account_id:
        return JSONResponse({"success": False, "error": "Twitter not connected"})
    return JSONResponse(await fetch_late_platform_data("twitter", account_id))


@router.get("/tiktok/overview")
async def tiktok_overview():
    account_id = os.getenv("LATE_PROFILE_TIKTOK_default_client")
    if not account_id:
        return JSONResponse({"success": False, "error": "TikTok not connected"})
    return JSONResponse(await fetch_late_platform_data("tiktok", account_id))


@router.get("/youtube/overview")
async def youtube_overview():
    return JSONResponse(await fetch_youtube_data())


@router.get("/linkedin/overview")
async def linkedin_overview():
    account_id = os.getenv("LATE_PROFILE_LINKEDIN_default_client")
    if not account_id:
        return JSONResponse({"success": False, "error": "LinkedIn not connected"})
    return JSONResponse(await fetch_late_platform_data("linkedin", account_id))


@router.get("/threads/overview")
async def threads_overview():
    account_id = os.getenv("LATE_PROFILE_THREADS_default_client")
    if not account_id:
        return JSONResponse({"success": False, "error": "Threads not connected"})
    return JSONResponse(await fetch_late_platform_data("threads", account_id))


# ═══════════════════════════════════════════════════════════════════════════
# AnalyticsAgent — AI Insights endpoint
# Connects agents/analytics_agent.py to the HTTP layer.
# Called by the analytics dashboard "AI Insights" panel.
# ═══════════════════════════════════════════════════════════════════════════

@router.get("/ai-insights")
async def analytics_ai_insights(request: Request, session: Optional[str] = Cookie(None, alias="alita_session")):
    """
    Run AnalyticsAgent.generate_insights() + generate_recommendations()
    against the metrics already being fetched by the dashboard.
    Returns JSON: {insights: [...], recommendations: [...], aggregates: {...}}
    """
    from database.db import get_db
    from utils.shared_layout import get_user_context

    db = next(get_db())
    try:
        user_obj, profile = get_user_context(request, db)
    except Exception:
        user_obj, profile = None, None
    finally:
        db.close()

    if not user_obj:
        return JSONResponse({"success": False, "error": "Not authenticated"}, status_code=401)

    try:
        from agents.analytics_agent import AnalyticsAgent
        client_id = profile.client_id if profile else "default_client"
        agent = AnalyticsAgent(client_id=client_id)

        # Resolve credentials
        ig_creds, fb_creds = None, None
        user_id = _get_session_user(session)
        if user_id:
            try:
                tm = get_token_manager()
                token_data = tm.get_token(user_id)
                if token_data and not token_data.is_expired:
                    ig_account = os.getenv("INSTAGRAM_BUSINESS_ACCOUNT_ID")
                    if ig_account:
                        ig_creds = {"ig_user_id": ig_account, "access_token": token_data.access_token}
                    fb_page = os.getenv("FACEBOOK_PAGE_ID")
                    fb_token = os.getenv("FACEBOOK_PAGE_ACCESS_TOKEN")
                    if fb_page and fb_token:
                        fb_creds = {"page_id": fb_page, "page_token": fb_token}
            except Exception:
                pass

        metrics = await agent.collect_all_metrics(
            instagram_credentials=ig_creds,
            facebook_credentials=fb_creds,
        )

        if not metrics:
            return JSONResponse({
                "success": True,
                "insights": ["Connect at least one platform to generate AI insights."],
                "recommendations": [],
                "aggregates": {},
            })

        aggregates    = agent.calculate_aggregates(metrics)
        insights      = await agent.generate_insights(metrics)
        recommendations = await agent.generate_recommendations(metrics, insights)

        # Persist weekly report to disk for the scheduler / history
        from datetime import timedelta
        from pathlib import Path
        import json as _json
        report_dir = Path("storage/analytics") / client_id
        report_dir.mkdir(parents=True, exist_ok=True)
        report_file = report_dir / f"report_{datetime.now().strftime('%Y_%m_%d')}.json"
        _json.dump(
            {"generated_at": datetime.now().isoformat(), "aggregates": aggregates,
             "insights": insights, "recommendations": recommendations},
            open(report_file, "w"), indent=2
        )

        return JSONResponse({
            "success": True,
            "insights": insights,
            "recommendations": recommendations,
            "aggregates": aggregates,
        })

    except Exception as e:
        import traceback; traceback.print_exc()
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)
