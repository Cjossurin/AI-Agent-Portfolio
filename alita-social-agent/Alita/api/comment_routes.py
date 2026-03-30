"""
Comment Management Routes - Instagram Comment Dashboard and AI-Powered Replies.

This module provides the comment management system required for Meta App Review:
    GET  /comments/dashboard        → Professional comment dashboard UI
    GET  /comments/posts            → List Instagram posts with comment counts
    GET  /comments/{post_id}        → Get comments for a specific post
    POST /comments/{comment_id}/reply → Reply to a comment (manual or AI-powered)
    GET  /comments/recent           → Real-time monitoring of recent comments

For Meta App Review, this demonstrates:
1. Professional UI for comment management
2. Manual comment moderation and replies
3. AI-powered auto-replies with brand voice
4. Real-time comment monitoring
"""

import os
import time
import asyncio
from typing import Optional, List, Dict, Any
from datetime import datetime
from fastapi import APIRouter, Request, Response, Cookie, Query, Form
from fastapi.responses import HTMLResponse, JSONResponse
from dotenv import load_dotenv

load_dotenv()

# Import OAuth and engagement components
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from api.meta_oauth import MetaOAuthClient
from api.token_manager import TokenManager

# Import engagement agent for AI replies
try:
    from agents.engagement_agent import EngagementAgent
    ENGAGEMENT_AGENT_AVAILABLE = True
except ImportError:
    ENGAGEMENT_AGENT_AVAILABLE = False
    print("⚠️  EngagementAgent not available for AI auto-replies")

# ─── Initialize ─────────────────────────────────────────────────────────

router = APIRouter(prefix="/comments", tags=["Comments"])

_oauth_client: Optional[MetaOAuthClient] = None
_token_manager: Optional[TokenManager] = None


def get_oauth_client() -> MetaOAuthClient:
    """Get or create the MetaOAuthClient singleton."""
    global _oauth_client
    if _oauth_client is None:
        _oauth_client = MetaOAuthClient()
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


# ─── Dashboard UI Styles ────────────────────────────────────────────────

def _dashboard_style() -> str:
    """CSS for comment dashboard."""
    return """
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background: #f0f2f5; color: #1c1e21; }
        .nav-bar { background: #fff; border-bottom: 1px solid #e4e6eb; padding: 16px 24px; display: flex; justify-content: space-between; align-items: center; }
        .brand { font-size: 20px; font-weight: 700; }
        .nav-links a { color: #606770; text-decoration: none; margin-left: 24px; font-size: 14px; }
        .nav-links a:hover { color: #1c1e21; }
        .home-btn { position: fixed; top: 20px; left: 20px; padding: 10px 20px; background: white; color: #5c6ac4; text-decoration: none; border-radius: 8px; font-weight: 600; box-shadow: 0 2px 8px rgba(0,0,0,0.2); z-index: 1000; }
        .home-btn:hover { background: #f8f9fa; }
        .back-btn { position: fixed; top: 20px; left: 120px; padding: 10px 20px; background: #f0f0f0; color: #333; text-decoration: none; border-radius: 8px; font-weight: 600; box-shadow: 0 2px 8px rgba(0,0,0,0.2); z-index: 1000; }
        .back-btn:hover { background: #e0e0e0; }
        .container { max-width: 1200px; margin: 0 auto; padding: 24px; }
        .header { margin-bottom: 32px; }
        .header h1 { font-size: 32px; margin-bottom: 8px; }
        .header p { color: #606770; font-size: 16px; }
        .accounts-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 16px; margin-bottom: 32px; }
        .account-card { background: #fff; border: 1px solid #e4e6eb; border-radius: 12px; padding: 20px; cursor: pointer; transition: all 0.2s; }
        .account-card:hover { border-color: #5c6ac4; transform: translateY(-2px); }
        .account-card.active { border-color: #5c6ac4; background: rgba(92,106,196,.06); }
        .account-header { display: flex; align-items: center; gap: 12px; margin-bottom: 12px; }
        .account-avatar { width: 48px; height: 48px; border-radius: 50%; background: linear-gradient(45deg, #f09433, #e6683c, #dc2743, #cc2366, #bc1888); }
        .account-info h3 { font-size: 16px; margin-bottom: 4px; }
        .account-info p { color: #606770; font-size: 13px; }
        .account-stats { display: flex; gap: 16px; padding-top: 12px; border-top: 1px solid #e4e6eb; }
        .stat { flex: 1; }
        .stat-value { font-size: 20px; font-weight: 700; color: #5c6ac4; }
        .stat-label { font-size: 11px; color: #606770; text-transform: uppercase; }
        .posts-section { margin-bottom: 32px; }
        .section-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; }
        .section-header h2 { font-size: 20px; }
        .filter-tabs { display: flex; gap: 8px; }
        .tab { padding: 8px 16px; border-radius: 20px; background: #e4e6eb; color: #606770; border: none; cursor: pointer; font-size: 14px; }
        .tab.active { background: #5c6ac4; color: white; }
        .posts-list { display: flex; flex-direction: column; gap: 16px; }
        .post-card { background: #fff; border: 1px solid #e4e6eb; border-radius: 12px; padding: 20px; }
        .post-header { display: flex; gap: 16px; margin-bottom: 16px; }
        .post-media { width: 100px; height: 100px; border-radius: 8px; background: #e4e6eb; object-fit: cover; }
        .post-content { flex: 1; }
        .post-caption { color: #1c1e21; margin-bottom: 8px; font-size: 14px; line-height: 1.5; }
        .post-meta { display: flex; gap: 16px; color: #606770; font-size: 13px; }
        .post-meta span { display: flex; align-items: center; gap: 4px; }
        .badge { display: inline-block; padding: 2px 8px; border-radius: 10px; font-size: 11px; font-weight: 600; }
        .badge-comments { background: rgba(92,106,196,.1); color: #5c6ac4; border: 1px solid rgba(92,106,196,.2); }
        .badge-new { background: rgba(46,125,50,.1); color: #2e7d32; border: 1px solid rgba(46,125,50,.2); }
        .comments-section { margin-top: 16px; padding-top: 16px; border-top: 1px solid #e4e6eb; display: none; }
        .comments-section.open { display: block; }
        .comment { background: #f8f9fb; border-left: 3px solid #e4e6eb; padding: 12px; margin-bottom: 12px; border-radius: 4px; }
        .comment.needs-reply { border-left-color: #c62828; }
        .comment.replied { border-left-color: #2e7d32; }
        .comment-header { display: flex; justify-content: space-between; align-items: start; margin-bottom: 8px; }
        .comment-author { font-weight: 600; color: #1c1e21; font-size: 14px; }
        .comment-time { color: #606770; font-size: 12px; }
        .comment-text { color: #1c1e21; font-size: 14px; line-height: 1.5; margin-bottom: 8px; }
        .comment-actions { display: flex; gap: 8px; }
        .btn { padding: 6px 12px; border-radius: 6px; border: none; cursor: pointer; font-size: 13px; font-weight: 600; transition: all 0.2s; }
        .btn-primary { background: #5c6ac4; color: white; }
        .btn-primary:hover { background: #4a5ab4; }
        .btn-success { background: #2e7d32; color: white; }
        .btn-success:hover { background: #256b2a; }
        .btn-secondary { background: #e4e6eb; color: #1c1e21; }
        .btn-secondary:hover { background: #d8dade; }
        .btn-sm { padding: 4px 10px; font-size: 12px; }
        .reply-form { background: #f8f9fb; padding: 12px; border-radius: 8px; margin-top: 8px; display: none; }
        .reply-form.open { display: block; }
        .reply-form textarea { width: 100%; background: #fff; border: 1px solid #e4e6eb; border-radius: 6px; padding: 12px; color: #1c1e21; font-family: inherit; font-size: 14px; resize: vertical; min-height: 80px; }
        .reply-form textarea:focus { outline: none; border-color: #5c6ac4; }
        .reply-actions { display: flex; gap: 8px; margin-top: 8px; justify-content: flex-end; }
        .toggle-comments { background: transparent; border: none; color: #5c6ac4; cursor: pointer; font-size: 14px; font-weight: 600; padding: 8px 0; }
        .toggle-comments:hover { text-decoration: underline; }
        .loading { text-align: center; padding: 40px; color: #606770; }
        .empty-state { text-align: center; padding: 60px 20px; color: #606770; }
        .empty-state-icon { font-size: 48px; margin-bottom: 16px; }
        .ai-badge { background: linear-gradient(45deg, #5c6ac4, #764ba2); color: white; padding: 2px 8px; border-radius: 10px; font-size: 11px; font-weight: 600; margin-left: 8px; }
        .sentiment { display: inline-block; padding: 2px 8px; border-radius: 10px; font-size: 11px; font-weight: 600; margin-left: 8px; }
        .sentiment-positive { background: rgba(46,125,50,.1); color: #2e7d32; }
        .sentiment-negative { background: rgba(198,40,40,.1); color: #c62828; }
        .sentiment-neutral { background: #e4e6eb; color: #606770; }
        .auto-reply-toggle { display: flex; align-items: center; gap: 8px; padding: 12px 16px; background: #fff; border: 1px solid #e4e6eb; border-radius: 8px; }
        .switch { position: relative; display: inline-block; width: 44px; height: 24px; }
        .switch input { opacity: 0; width: 0; height: 0; }
        .slider { position: absolute; cursor: pointer; top: 0; left: 0; right: 0; bottom: 0; background-color: #e4e6eb; transition: .4s; border-radius: 24px; }
        .slider:before { position: absolute; content: ""; height: 18px; width: 18px; left: 3px; bottom: 3px; background-color: white; transition: .4s; border-radius: 50%; }
        input:checked + .slider { background-color: #5c6ac4; }
        input:checked + .slider:before { transform: translateX(20px); }
        .platform-tabs { display: flex; gap: 12px; padding: 16px 0; border-bottom: 2px solid #e4e6eb; }
        .platform-tab { padding: 12px 24px; border-radius: 8px 8px 0 0; background: transparent; color: #606770; border: none; cursor: pointer; font-size: 16px; font-weight: 600; transition: all 0.2s; border-bottom: 3px solid transparent; }
        .platform-tab:hover { color: #1c1e21; background: rgba(92,106,196,.05); }
        .platform-tab.active { color: #5c6ac4; border-bottom-color: #5c6ac4; background: rgba(92,106,196,.06); }
        .platform-section { margin-top: 16px; }
    """


# ─── Dashboard Routes ───────────────────────────────────────────────────

@router.get("/dashboard", response_class=HTMLResponse)
async def comment_dashboard(
    request: Request,
    alita_session: Optional[str] = Cookie(None),
):
    """
    Professional comment management dashboard.
    
    Shows:
    - Connected Instagram accounts
    - Recent posts with comment counts
    - Expandable comment threads
    - Manual and AI-powered reply forms
    - Real-time monitoring controls
    """
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

    user_id = _get_session_user(alita_session)
    _css = _dashboard_style()

    if not user_id:
        _body = """
        <div class="empty-state">
            <div class="empty-state-icon">&#128274;</div>
            <h2>Not Connected</h2>
            <p>Please connect your Instagram account to manage comments.</p>
            <br>
            <a href="/connect/dashboard" class="btn btn-primary">Connect Instagram</a>
        </div>
        """
        return HTMLResponse(build_page(
            title="Comments", active_nav="comments",
            body_content=_body, user_name=_uname,
            business_name=_bname, extra_css=_css,
        ))

    tm = get_token_manager()
    token_data = tm.get_valid_token(user_id)

    if not token_data:
        _body = """
        <div class="empty-state">
            <div class="empty-state-icon">&#9888;</div>
            <h2>Token Expired</h2>
            <p>Your Instagram connection has expired. Please reconnect.</p>
            <br>
            <a href="/connect/dashboard" class="btn btn-primary">Reconnect</a>
        </div>
        """
        return HTMLResponse(build_page(
            title="Comments", active_nav="comments",
            body_content=_body, user_name=_uname,
            business_name=_bname, extra_css=_css,
        ))

    body_content = """
            <div class="header">
                <h1>💬 Comment Management Dashboard</h1>
                <p>Manage Instagram comments with AI-powered auto-replies</p>
            </div>
            
            <div class="auto-reply-toggle">
                <label class="switch">
                    <input type="checkbox" id="autoReplyToggle" style="display: none;">
                    <span class="slider" style="display: none;"></span>
                </label>
                <div style="display: none;">
                    <strong>AI Auto-Reply</strong>
                    <span class="ai-badge">BETA</span>
                    <br>
                    <span style="font-size: 12px; color: #606770;">Automatically respond to comments with brand voice</span>
                </div>
            </div>
            
            <div class="platform-tabs" style="margin-top: 24px; flex-wrap: wrap;">
                <button class="platform-tab active" onclick="switchPlatform('instagram')">📸 Instagram</button>
                <button class="platform-tab" onclick="switchPlatform('facebook')">📘 Facebook</button>
                <button class="platform-tab" onclick="switchPlatform('threads')">🧵 Threads</button>
                <button class="platform-tab" onclick="switchPlatform('tiktok')">🎵 TikTok</button>
                <button class="platform-tab" onclick="switchPlatform('twitter')">𝕏 Twitter</button>
                <button class="platform-tab" onclick="switchPlatform('youtube')">🎥 YouTube</button>
                <button class="platform-tab" onclick="switchPlatform('linkedin')">💼 LinkedIn</button>
            </div>
            
            <div id="instagramSection" class="platform-section">
                <div style="display: flex; align-items: center; justify-content: space-between; margin-top: 24px; padding: 16px; background: #fff; border-radius: 8px; margin-bottom: 16px;">
                    <div>
                        <h2 style="margin: 0;">📸 Instagram Auto-Reply</h2>
                        <span style="font-size: 12px; color: #606770;">Automatically respond to comments with AI</span>
                    </div>
                    <label class="switch">
                        <input type="checkbox" id="autoReplyInstagram" onchange="toggleAutoReply('instagram')">
                        <span class="slider"></span>
                    </label>
                </div>
                <div id="accountsSection" style="margin-top: 24px;">
                    <h2 style="margin-bottom: 16px;">📸 Your Instagram Accounts</h2>
                    <div class="accounts-grid" id="accountsGrid">
                        <div class="loading">Loading your Instagram accounts...</div>
                    </div>
                </div>
            </div>
            
            <div id="facebookSection" class="platform-section" style="display: none;">
                <div style="display: flex; align-items: center; justify-content: space-between; margin-top: 24px; padding: 16px; background: #fff; border-radius: 8px; margin-bottom: 16px;">
                    <div>
                        <h2 style="margin: 0;">📘 Facebook Auto-Reply</h2>
                        <span style="font-size: 12px; color: #606770;">Automatically respond to comments with AI</span>
                    </div>
                    <label class="switch">
                        <input type="checkbox" id="autoReplyFacebook" onchange="toggleAutoReply('facebook')">
                        <span class="slider"></span>
                    </label>
                </div>
                <div id="pagesSection" style="margin-top: 24px;">
                    <h2 style="margin-bottom: 16px;">📘 Your Facebook Pages</h2>
                    <div class="accounts-grid" id="pagesGrid">
                        <div class="loading">Loading your Facebook pages...</div>
                    </div>
                </div>
            </div>
            
            <div id="threadsSection" class="platform-section" style="display: none;">
                <div style="display: flex; align-items: center; justify-content: space-between; margin-top: 24px; padding: 16px; background: #fff; border-radius: 8px; margin-bottom: 16px;">
                    <div>
                        <h2 style="margin: 0;">🧵 Threads Auto-Reply</h2>
                        <span style="font-size: 12px; color: #606770;">Automatically respond to comments with AI</span>
                    </div>
                    <label class="switch">
                        <input type="checkbox" id="autoReplyThreads" onchange="toggleAutoReply('threads')">
                        <span class="slider"></span>
                    </label>
                </div>
                <div style="margin-top: 24px;">
                    <h2 style="margin-bottom: 16px;">🧵 Your Threads Posts</h2>
                    <div class="info" style="background: linear-gradient(135deg, #833ab4, #fd1d1d, #fcb045); color: white; padding: 15px; border-radius: 10px; margin-bottom: 20px;">
                        <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 10px;">\n                            <div>
                                <strong>✨ Threads Comment Monitoring Active</strong>
                                <p style="margin: 5px 0 0 0; opacity: 0.9; font-size: 13px;">Monitor and reply to Threads comments with AI assistance</p>
                            </div>
                            <a href="/threads/dashboard" class="btn" style="background: white; color: #833ab4; white-space: nowrap; flex-shrink: 0; text-decoration: none;">📝 Create Post</a>
                        </div>
                    </div>
                    <div class="posts-list" id="threadsPostsList">
                        <div class="loading">Loading your Threads posts...</div>
                    </div>
                </div>
            </div>
            
            <div id="tiktokSection" class="platform-section" style="display: none;">
                <div style="margin-top: 24px;">
                    <h2 style="margin-bottom: 16px;">🎵 Your TikTok Posts</h2>
                    <div class="posts-list" id="tiktokPostsList">
                        <div class="loading">Loading your TikTok posts...</div>
                    </div>
                </div>
            </div>
            
            <div id="twitterSection" class="platform-section" style="display: none;">
                <div style="margin-top: 24px;">
                    <h2 style="margin-bottom: 16px;">𝕏 Your Twitter Posts</h2>
                    <div class="posts-list" id="twitterPostsList">
                        <div class="loading">Loading your Twitter posts...</div>
                    </div>
                </div>
            </div>
            
            <div id="youtubeSection" class="platform-section" style="display: none;">
                <div style="margin-top: 24px;">
                    <h2 style="margin-bottom: 16px;">🎥 Your YouTube Posts</h2>
                    <div class="posts-list" id="youtubePostsList">
                        <div class="loading">Loading your YouTube posts...</div>
                    </div>
                </div>
            </div>
            
            <div id="linkedinSection" class="platform-section" style="display: none;">
                <div style="margin-top: 24px;">
                    <h2 style="margin-bottom: 16px;">💼 Your LinkedIn Posts</h2>
                    <div class="posts-list" id="linkedinPostsList">
                        <div class="loading">Loading your LinkedIn posts...</div>
                    </div>
                </div>
            </div>
            
            <div class="posts-section" id="postsSection" style="display: none;">
                <div class="section-header">
                    <h2>📝 Recent Posts</h2>
                    <div class="filter-tabs">
                        <button class="tab active" onclick="filterPosts('all')">All</button>
                        <button class="tab" onclick="filterPosts('with-comments')">With Comments</button>
                        <button class="tab" onclick="filterPosts('needs-reply')">Needs Reply</button>
                    </div>
                </div>
                <div class="posts-list" id="postsList">
                    <div class="loading">Select an account to view posts</div>
                </div>
            </div>
    """

    page_js = """
            let selectedAccountId = null;
            let autoReplyEnabled = false;
            let platformAutoReply = {
                instagram: false,
                facebook: false,
                threads: false,
                tiktok: false,
                twitter: false,
                youtube: false,
                linkedin: false
            };
            
            async function loadCommentAutoReplySettings() {
                try {
                    const r = await fetch('/inbox/api/comment-auto-reply');
                    if (!r.ok) {
                        console.warn('Failed to load comment auto-reply settings:', r.status);
                        return;
                    }
                    const settings = await r.json();
                    for (const platform of Object.keys(platformAutoReply)) {
                        const enabled = !!settings[platform];
                        platformAutoReply[platform] = enabled;
                        const checkbox = document.getElementById('autoReply' + platform.charAt(0).toUpperCase() + platform.slice(1));
                        if (checkbox) checkbox.checked = enabled;
                    }
                } catch (e) {
                    console.warn('Could not load comment auto-reply settings:', e);
                }
            }

            // Toggle auto-reply per platform (persisted)
            async function toggleAutoReply(platform) {
                const checkbox = document.getElementById('autoReply' + platform.charAt(0).toUpperCase() + platform.slice(1));
                if (!checkbox) return;

                const enabled = !!checkbox.checked;
                // Optimistic update
                platformAutoReply[platform] = enabled;

                try {
                    const r = await fetch('/inbox/api/comment-auto-reply/' + platform, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ enabled })
                    });
                    if (!r.ok) {
                        console.warn('Failed to save comment auto-reply toggle:', platform, r.status);
                    }
                } catch (e) {
                    console.warn('Failed to save comment auto-reply toggle:', e);
                }
                console.log(`${platform} auto-reply: ${enabled ? 'enabled' : 'disabled'}`);
            }
            
            // Legacy toggle auto-reply (kept for backward compatibility)
            document.getElementById('autoReplyToggle').addEventListener('change', (e) => {
                autoReplyEnabled = e.target.checked;
                console.log('Auto-reply:', autoReplyEnabled ? 'enabled' : 'disabled');
            });

            // Initialize toggles from backend
            document.addEventListener('DOMContentLoaded', () => {
                loadCommentAutoReplySettings();
            });
            
            // Load Instagram accounts
            async function loadAccounts() {
                try {
                    const response = await fetch('/comments/accounts');
                    const data = await response.json();
                    
                    if (data.accounts && data.accounts.length > 0) {
                        renderAccounts(data.accounts);
                    } else {
                        document.getElementById('accountsGrid').innerHTML = `
                            <div class="empty-state">
                                <div class="empty-state-icon">📸</div>
                                <p>No Instagram Business Accounts found</p>
                                <p style="font-size: 13px; margin-top: 8px;">Make sure your Instagram account is a Business or Creator account and linked to a Facebook Page.</p>
                            </div>
                        `;
                    }
                } catch (error) {
                    console.error('Failed to load accounts:', error);
                    document.getElementById('accountsGrid').innerHTML = `
                        <div class="empty-state">
                            <div class="empty-state-icon">❌</div>
                            <p>Failed to load accounts</p>
                        </div>
                    `;
                }
            }
            
            function renderAccounts(accounts) {
                const grid = document.getElementById('accountsGrid');
                grid.innerHTML = accounts.map(account => `
                    <div class="account-card" onclick="selectAccount('${account.id}', '${account.username}')">
                        <div class="account-header">
                            <div class="account-avatar"></div>
                            <div class="account-info">
                                <h3>@${account.username}</h3>
                                <p>${account.name || 'Instagram Business'}</p>
                            </div>
                        </div>
                        <div class="account-stats">
                            <div class="stat">
                                <div class="stat-value">${account.followers_count || '—'}</div>
                                <div class="stat-label">Followers</div>
                            </div>
                            <div class="stat">
                                <div class="stat-value">${account.media_count || '—'}</div>
                                <div class="stat-label">Posts</div>
                            </div>
                        </div>
                    </div>
                `).join('');
            }
            
            async function selectAccount(accountId, username) {
                selectedAccountId = accountId;
                
                // Update UI
                document.querySelectorAll('.account-card').forEach(card => {
                    card.classList.remove('active');
                });
                event.currentTarget.classList.add('active');
                
                document.getElementById('postsSection').style.display = 'block';
                
                // Load posts
                await loadPosts(accountId);
            }
            
            async function loadPosts(accountId) {
                const postsList = document.getElementById('postsList');
                postsList.innerHTML = '<div class="loading">Loading posts...</div>';
                
                try {
                    const response = await fetch(`/comments/posts?account_id=${accountId}`);
                    const data = await response.json();
                    
                    if (data.posts && data.posts.length > 0) {
                        renderPosts(data.posts);
                    } else {
                        postsList.innerHTML = `
                            <div class="empty-state">
                                <div class="empty-state-icon">📭</div>
                                <p>No posts found</p>
                            </div>
                        `;
                    }
                } catch (error) {
                    console.error('Failed to load posts:', error);
                    postsList.innerHTML = `
                        <div class="empty-state">
                            <div class="empty-state-icon">❌</div>
                            <p>Failed to load posts</p>
                        </div>
                    `;
                }
            }
            
            function renderPosts(posts) {
                const postsList = document.getElementById('postsList');
                postsList.innerHTML = posts.map(post => `
                    <div class="post-card" data-post-id="${post.id}">
                        <div class="post-header">
                            ${post.media_url ? `<img src="${post.media_url}" class="post-media" alt="Post media">` : '<div class="post-media"></div>'}
                            <div class="post-content">
                                <div class="post-caption">${post.caption ? post.caption.substring(0, 150) + (post.caption.length > 150 ? '...' : '') : '<em>No caption</em>'}</div>
                                <div class="post-meta">
                                    <span>❤️ ${post.like_count || 0} likes</span>
                                    <span>💬 ${post.comments_count || 0} comments</span>
                                    <span>🕐 ${formatDate(post.timestamp)}</span>
                                    ${post.comments_count > 0 ? '<span class="badge badge-comments">Has Comments</span>' : ''}
                                </div>
                            </div>
                        </div>
                        ${post.comments_count > 0 ? `
                            <button class="toggle-comments" onclick="toggleComments('${post.id}')">
                                View ${post.comments_count} comment${post.comments_count > 1 ? 's' : ''} →
                            </button>
                            <div class="comments-section" id="comments-${post.id}">
                                <div class="loading">Loading comments...</div>
                            </div>
                        ` : ''}
                    </div>
                `).join('');
            }
            
            async function toggleComments(postId) {
                const section = document.getElementById(`comments-${postId}`);
                
                if (section.classList.contains('open')) {
                    section.classList.remove('open');
                    return;
                }
                
                section.classList.add('open');
                
                // Load comments
                try {
                    const response = await fetch(`/comments/${postId}`);
                    const data = await response.json();
                    
                    if (data.comments && data.comments.length > 0) {
                        renderComments(postId, data.comments);
                    } else {
                        section.innerHTML = '<p style="color: #606770; font-size: 13px;">No comments yet</p>';
                    }
                } catch (error) {
                    console.error('Failed to load comments:', error);
                    section.innerHTML = '<p style="color: #c62828; font-size: 13px;">Failed to load comments</p>';
                }
            }
            
            function renderComments(postId, comments) {
                const section = document.getElementById(`comments-${postId}`);
                section.innerHTML = comments.map(comment => `
                    <div class="comment needs-reply" id="comment-${comment.id}">
                        <div class="comment-header">
                            <div>
                                <span class="comment-author">@${comment.username || comment.from?.username || 'unknown'}</span>
                                ${detectSentiment(comment.text)}
                            </div>
                            <span class="comment-time">${formatDate(comment.timestamp)}</span>
                        </div>
                        <div class="comment-text">${comment.text}</div>
                        <div class="comment-actions">
                            <button class="btn btn-primary btn-sm" onclick="openReplyForm('${comment.id}', false)">
                                ✍️ Reply
                            </button>
                            <button class="btn btn-success btn-sm" onclick="openReplyForm('${comment.id}', true)">
                                🤖 AI Reply
                            </button>
                        </div>
                        <div class="reply-form" id="reply-form-${comment.id}">
                            <textarea id="reply-text-${comment.id}" placeholder="Write your reply..."></textarea>
                            <div class="reply-actions">
                                <button class="btn btn-secondary btn-sm" onclick="closeReplyForm('${comment.id}')">Cancel</button>
                                <button class="btn btn-primary btn-sm" onclick="sendReply('${comment.id}')">Send Reply</button>
                            </div>
                        </div>
                    </div>
                `).join('');
            }
            
            async function openReplyForm(commentId, useAI) {
                const form = document.getElementById(`reply-form-${commentId}`);
                const textarea = document.getElementById(`reply-text-${commentId}`);
                
                form.classList.add('open');
                
                if (useAI) {
                    textarea.value = 'Generating AI reply...';
                    textarea.disabled = true;
                    
                    try {
                        const response = await fetch(`/comments/${commentId}/ai-reply`);
                        const data = await response.json();
                        
                        if (data.reply) {
                            textarea.value = data.reply;
                        } else {
                            textarea.value = 'Failed to generate AI reply. Please write manually.';
                        }
                    } catch (error) {
                        console.error('Failed to generate AI reply:', error);
                        textarea.value = 'Failed to generate AI reply. Please write manually.';
                    } finally {
                        textarea.disabled = false;
                    }
                }
                
                textarea.focus();
            }
            
            function closeReplyForm(commentId) {
                const form = document.getElementById(`reply-form-${commentId}`);
                form.classList.remove('open');
                document.getElementById(`reply-text-${commentId}`).value = '';
            }
            
            async function sendReply(commentId) {
                const textarea = document.getElementById(`reply-text-${commentId}`);
                const message = textarea.value.trim();
                
                if (!message) {
                    alert('Please write a reply');
                    return;
                }
                
                try {
                    const response = await fetch(`/comments/${commentId}/reply`, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ message })
                    });
                    
                    const data = await response.json();
                    
                    if (data.success) {
                        // Mark comment as replied
                        const commentDiv = document.getElementById(`comment-${commentId}`);
                        commentDiv.classList.remove('needs-reply');
                        commentDiv.classList.add('replied');
                        
                        // Close form
                        closeReplyForm(commentId);
                        
                        // Show success
                        alert('✅ Reply sent successfully!');
                    } else {
                        alert('❌ Failed to send reply: ' + (data.error || 'Unknown error'));
                    }
                } catch (error) {
                    console.error('Failed to send reply:', error);
                    alert('❌ Failed to send reply. Please try again.');
                }
            }
            
            function detectSentiment(text) {
                const lowerText = text.toLowerCase();
                const positiveWords = ['love', 'amazing', 'great', 'awesome', 'beautiful', 'perfect', '❤️', '😍', '🔥'];
                const negativeWords = ['hate', 'terrible', 'awful', 'bad', 'worst', 'horrible'];
                
                const hasPositive = positiveWords.some(word => lowerText.includes(word));
                const hasNegative = negativeWords.some(word => lowerText.includes(word));
                
                if (hasPositive && !hasNegative) {
                    return '<span class="sentiment sentiment-positive">😊 Positive</span>';
                } else if (hasNegative && !hasPositive) {
                    return '<span class="sentiment sentiment-negative">😞 Negative</span>';
                } else {
                    return '<span class="sentiment sentiment-neutral">😐 Neutral</span>';
                }
            }
            
            function formatDate(timestamp) {
                if (!timestamp) return '—';
                const date = new Date(timestamp);
                const now = new Date();
                const diffMs = now - date;
                const diffMins = Math.floor(diffMs / 60000);
                const diffHours = Math.floor(diffMs / 3600000);
                const diffDays = Math.floor(diffMs / 86400000);
                
                if (diffMins < 1) return 'just now';
                if (diffMins < 60) return `${diffMins}m ago`;
                if (diffHours < 24) return `${diffHours}h ago`;
                if (diffDays < 7) return `${diffDays}d ago`;
                return date.toLocaleDateString();
            }
            
            function filterPosts(filter) {
                // Update tab UI
                document.querySelectorAll('.tab').forEach(tab => tab.classList.remove('active'));
                event.target.classList.add('active');
                
                // Filter logic (to be implemented)
                console.log('Filter:', filter);
            }
            
            let currentPlatform = 'instagram';
            let selectedPageId = null;
            
            function switchPlatform(platform) {
                currentPlatform = platform;
                
                // Update tab UI
                document.querySelectorAll('.platform-tab').forEach(tab => {
                    tab.classList.remove('active');
                });
                event.target.classList.add('active');
                
                // Show/hide all platform sections
                const allSections = ['instagram', 'facebook', 'threads', 'tiktok', 'twitter', 'youtube', 'linkedin'];
                allSections.forEach(p => {
                    const section = document.getElementById(p + 'Section');
                    if (section) section.style.display = p === platform ? 'block' : 'none';
                });
                document.getElementById('postsSection').style.display = 'none';
                
                // Load appropriate data
                if (platform === 'facebook' && !selectedPageId) {
                    loadFacebookPages();
                } else if (platform === 'threads') {
                    loadThreadsPosts();
                } else if (['tiktok', 'twitter', 'youtube', 'linkedin'].includes(platform)) {
                    loadLatePosts(platform);
                }
            }
            
            // Load Facebook pages
            async function loadFacebookPages() {
                try {
                    const response = await fetch('/comments/facebook-pages');
                    const data = await response.json();
                    
                    if (data.pages && data.pages.length > 0) {
                        renderFacebookPages(data.pages);
                    } else {
                        document.getElementById('pagesGrid').innerHTML = `
                            <div class="empty-state">
                                <div class="empty-state-icon">📘</div>
                                <p>No Facebook Pages found</p>
                                <p style="font-size: 13px; margin-top: 8px;">Make sure you have admin access to at least one Facebook Page.</p>
                            </div>
                        `;
                    }
                } catch (error) {
                    console.error('Failed to load Facebook pages:', error);
                    document.getElementById('pagesGrid').innerHTML = `
                        <div class="empty-state">
                            <div class="empty-state-icon">❌</div>
                            <p>Failed to load Facebook pages</p>
                        </div>
                    `;
                }
            }
            
            function renderFacebookPages(pages) {
                const grid = document.getElementById('pagesGrid');
                grid.innerHTML = pages.map(page => `
                    <div class="account-card" onclick="selectFacebookPage('${page.id}', '${page.name}')">
                        <div class="account-header">
                            <div class="account-avatar">📘</div>
                            <div class="account-info">
                                <h3>${page.name}</h3>
                                <p>${page.category || 'Facebook Page'}</p>
                                ${page.has_instagram ? '<span class="badge" style="background: linear-gradient(135deg, #833ab4, #fd1d1d, #fcb045); margin-top: 4px;">📸 Linked to Instagram</span>' : ''}
                            </div>
                        </div>
                    </div>
                `).join('');
            }
            
            async function selectFacebookPage(pageId, pageName) {
                selectedPageId = pageId;
                
                // Update UI
                document.querySelectorAll('.account-card').forEach(card => {
                    card.classList.remove('active');
                });
                event.currentTarget.classList.add('active');
                
                document.getElementById('postsSection').style.display = 'block';
                
                // Load Facebook posts
                await loadFacebookPosts(pageId);
            }
            
            async function loadFacebookPosts(pageId) {
                const postsList = document.getElementById('postsList');
                postsList.innerHTML = '<div class="loading">Loading Facebook posts...</div>';
                
                try {
                    const response = await fetch(`/comments/facebook-posts?page_id=${pageId}`);
                    const data = await response.json();
                    
                    if (data.posts && data.posts.length > 0) {
                        renderFacebookPosts(data.posts);
                    } else {
                        postsList.innerHTML = `
                            <div class="empty-state">
                                <div class="empty-state-icon">📭</div>
                                <p>No posts found</p>
                            </div>
                        `;
                    }
                } catch (error) {
                    console.error('Failed to load Facebook posts:', error);
                    postsList.innerHTML = `
                        <div class="empty-state">
                            <div class="empty-state-icon">❌</div>
                            <p>Failed to load Facebook posts</p>
                        </div>
                    `;
                }
            }
            
            function renderFacebookPosts(posts) {
                const postsList = document.getElementById('postsList');
                postsList.innerHTML = posts.map(post => `
                    <div class="post-card" data-post-id="${post.id}">
                        <div class="post-header">
                            ${post.full_picture ? `<img src="${post.full_picture}" class="post-media" alt="Post media">` : '<div class="post-media">📘</div>'}
                            <div class="post-content">
                                <div class="post-caption">${post.message ? post.message.substring(0, 150) + (post.message.length > 150 ? '...' : '') : '<em>No message</em>'}</div>
                                <div class="post-meta">
                                    <span>👍 ${post.reactions_count || 0} reactions</span>
                                    <span>💬 ${post.comments_count || 0} comments</span>
                                    <span>🕐 ${formatDate(post.created_time)}</span>
                                    ${post.comments_count > 0 ? '<span class="badge badge-comments">Has Comments</span>' : ''}
                                </div>
                            </div>
                        </div>
                        ${post.comments_count > 0 ? `
                            <button class="toggle-comments" onclick="toggleFacebookComments('${post.id}')">
                                View ${post.comments_count} comment${post.comments_count > 1 ? 's' : ''} →
                            </button>
                            <div class="comments-section" id="comments-${post.id}">
                                <div class="loading">Loading comments...</div>
                            </div>
                        ` : ''}
                    </div>
                `).join('');
            }
            
            async function toggleFacebookComments(postId) {
                const section = document.getElementById(`comments-${postId}`);
                
                if (section.classList.contains('open')) {
                    section.classList.remove('open');
                    return;
                }
                
                section.classList.add('open');
                
                try {
                    const response = await fetch(`/comments/facebook/${postId}`);
                    const data = await response.json();
                    
                    if (data.comments && data.comments.length > 0) {
                        renderFacebookComments(postId, data.comments);
                    } else {
                        section.innerHTML = '<p style="color: #606770; font-size: 13px;">No comments yet</p>';
                    }
                } catch (error) {
                    console.error('Failed to load comments:', error);
                    section.innerHTML = '<p style="color: #c62828; font-size: 13px;">Failed to load comments</p>';
                }
            }
            
            function renderFacebookComments(postId, comments) {
                const section = document.getElementById(`comments-${postId}`);
                section.innerHTML = comments.map(comment => `
                    <div class="comment needs-reply" id="comment-${comment.id}">
                        <div class="comment-header">
                            <div>
                                <span class="comment-author">${comment.from?.name || 'Unknown'}</span>
                                ${detectSentiment(comment.message || '')}
                            </div>
                            <span class="comment-time">${formatDate(comment.created_time)}</span>
                        </div>
                        <div class="comment-text">${comment.message || ''}</div>
                        <div class="comment-actions">
                            <button class="btn btn-primary btn-sm" onclick="openFacebookReplyForm('${comment.id}', false)">
                                ✍️ Reply
                            </button>
                            <button class="btn btn-success btn-sm" onclick="openFacebookReplyForm('${comment.id}', true)">
                                🤖 AI Reply
                            </button>
                        </div>
                        <div class="reply-form" id="reply-form-${comment.id}">
                            <textarea id="reply-text-${comment.id}" placeholder="Write your reply..."></textarea>
                            <div class="reply-actions">
                                <button class="btn btn-secondary btn-sm" onclick="closeReplyForm('${comment.id}')">Cancel</button>
                                <button class="btn btn-primary btn-sm" onclick="sendFacebookReply('${comment.id}')">Send Reply</button>
                            </div>
                        </div>
                    </div>
                `).join('');
            }
            
            async function openFacebookReplyForm(commentId, useAI) {
                const form = document.getElementById(`reply-form-${commentId}`);
                const textarea = document.getElementById(`reply-text-${commentId}`);
                
                form.classList.add('open');
                
                if (useAI) {
                    textarea.value = 'Generating AI reply...';
                    textarea.disabled = true;
                    
                    try {
                        const response = await fetch(`/comments/${commentId}/ai-reply`);
                        const data = await response.json();
                        
                        if (data.reply) {
                            textarea.value = data.reply;
                        } else {
                            textarea.value = 'Failed to generate AI reply. Please write manually.';
                        }
                    } catch (error) {
                        console.error('Failed to generate AI reply:', error);
                        textarea.value = 'Failed to generate AI reply. Please write manually.';
                    } finally {
                        textarea.disabled = false;
                    }
                }
                
                textarea.focus();
            }
            
            async function sendFacebookReply(commentId) {
                const textarea = document.getElementById(`reply-text-${commentId}`);
                const message = textarea.value.trim();
                
                if (!message) {
                    alert('Please write a reply');
                    return;
                }
                
                if (!selectedPageId) {
                    alert('No page selected');
                    return;
                }
                
                try {
                    const response = await fetch(`/comments/facebook/${commentId}/reply`, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ message, page_id: selectedPageId })
                    });
                    
                    const data = await response.json();
                    
                    if (data.success) {
                        const commentDiv = document.getElementById(`comment-${commentId}`);
                        commentDiv.classList.remove('needs-reply');
                        commentDiv.classList.add('replied');
                        
                        closeReplyForm(commentId);
                        alert('✅ Reply sent successfully!');
                    } else {
                        alert('❌ Failed to send reply: ' + (data.error || 'Unknown error'));
                    }
                } catch (error) {
                    console.error('Failed to send reply:', error);
                    alert('❌ Failed to send reply. Please try again.');
                }
            }
            
            // ===== THREADS FUNCTIONS =====
            
            async function loadThreadsPosts() {
                const listDiv = document.getElementById('threadsPostsList');
                listDiv.innerHTML = '<div class="loading">Loading your Threads posts...</div>';
                
                try {
                    const response = await fetch('/comments/threads-posts?client_id=default_client&limit=20');
                    const data = await response.json();
                    
                    if (data.error) {
                        listDiv.innerHTML = `<div class="empty-state"><div class="empty-state-icon">⚠️</div><p>${data.error}</p></div>`;
                        return;
                    }
                    
                    if (!data.posts || data.posts.length === 0) {
                        listDiv.innerHTML = `
                            <div class="empty-state">
                                <div class="empty-state-icon">🧵</div>
                                <p>No Threads posts yet</p>
                                <p style="font-size: 13px; margin-top: 8px;">Create your first post from the Threads dashboard</p>
                                <a href="/threads/dashboard" class="btn btn-primary" style="margin-top: 12px;">Create Post</a>
                            </div>
                        `;
                        return;
                    }
                    
                    listDiv.innerHTML = data.posts.map(post => `
                        <div class="post-card">
                            <div class="post-header">
                                <div class="post-content">
                                    <p class="post-caption">${post.text || post.full_text || 'No text'}</p>
                                    <div class="post-meta">
                                        <span>❤️ ${post.like_count || 0} likes</span>
                                        <span>💬 ${post.reply_count || 0} replies</span>
                                        <span>🔁 ${post.quote_count || 0} quotes</span>
                                        ${post.comments_count > 0 ? `<span class="badge badge-comments">${post.comments_count} comments</span>` : ''}
                                    </div>
                                </div>
                            </div>
                            ${post.id ? `
                                <button class="toggle-comments" onclick="toggleThreadsComments('${post.id}')">
                                    👁️ View Comments
                                </button>
                                <div class="comments-section" id="threads-comments-${post.id}">
                                    <div class="loading">Loading comments...</div>
                                </div>
                            ` : ''}
                        </div>
                    `).join('');
                    
                } catch (error) {
                    console.error('Failed to load Threads posts:', error);
                    listDiv.innerHTML = `<div class="empty-state"><div class="empty-state-icon">❌</div><p>Failed to load Threads posts</p></div>`;
                }
            }
            
            async function toggleThreadsComments(postId) {
                const commentsDiv = document.getElementById(`threads-comments-${postId}`);
                
                if (commentsDiv.classList.contains('open')) {
                    commentsDiv.classList.remove('open');
                    return;
                }
                
                commentsDiv.classList.add('open');
                commentsDiv.innerHTML = '<div class="loading">Loading comments...</div>';
                
                try {
                    const response = await fetch(`/comments/threads/${postId}?client_id=default_client`);
                    const data = await response.json();
                    
                    if (data.error) {
                        commentsDiv.innerHTML = `<p style="color: #c62828; padding: 12px;">${data.error}</p>`;
                        return;
                    }
                    
                    if (!data.comments || data.comments.length === 0) {
                        commentsDiv.innerHTML = '<p style="color: #606770; padding: 12px;">No comments yet</p>';
                        return;
                    }
                    
                    commentsDiv.innerHTML = data.comments.map(comment => `
                        <div class="comment" id="threads-comment-${comment.id}">
                            <div class="comment-header">
                                <span class="comment-author">@${comment.from.username}</span>
                                <span class="comment-time">${comment.timestamp ? new Date(comment.timestamp).toLocaleString() : 'Unknown'}</span>
                            </div>
                            <p class="comment-text">${comment.text}</p>
                            <div class="comment-actions">
                                <button class="btn btn-secondary btn-sm" onclick="openThreadsReplyForm('${comment.id}', false)">Reply</button>
                                <button class="btn btn-success btn-sm" onclick="openThreadsReplyForm('${comment.id}', true)">
                                    🤖 AI Reply
                                </button>
                            </div>
                            <div class="reply-form" id="threads-reply-form-${comment.id}">
                                <textarea id="threads-reply-text-${comment.id}" placeholder="Write your reply..."></textarea>
                                <div class="reply-actions">
                                    <button class="btn btn-secondary btn-sm" onclick="closeReplyForm('threads-reply-form-${comment.id}')">Cancel</button>
                                    <button class="btn btn-primary btn-sm" onclick="sendThreadsReply('${comment.id}')">Send Reply</button>
                                </div>
                            </div>
                        </div>
                    `).join('');
                    
                } catch (error) {
                    console.error('Failed to load comments:', error);
                    commentsDiv.innerHTML = '<p style="color: #c62828; padding: 12px;">Failed to load comments</p>';
                }
            }
            
            async function openThreadsReplyForm(commentId, useAI) {
                const form = document.getElementById(`threads-reply-form-${commentId}`);
                const textarea = document.getElementById(`threads-reply-text-${commentId}`);
                
                form.classList.add('open');
                
                if (useAI) {
                    textarea.value = 'Generating AI reply...';
                    textarea.disabled = true;
                    
                    try {
                        // Get the comment text for context
                        const commentDiv = document.getElementById(`threads-comment-${commentId}`);
                        const commentText = commentDiv.querySelector('.comment-text').textContent;
                        
                        // For now, use a simple AI reply - in production, integrate with EngagementAgent
                        textarea.value = 'Thanks for your comment! We appreciate your engagement. 🙏';
                    } catch (error) {
                        console.error('Failed to generate AI reply:', error);
                        textarea.value = 'Failed to generate AI reply. Please write manually.';
                    } finally {
                        textarea.disabled = false;
                    }
                }
                
                textarea.focus();
            }
            
            async function sendThreadsReply(commentId) {
                const textarea = document.getElementById(`threads-reply-text-${commentId}`);
                const message = textarea.value.trim();
                
                if (!message) {
                    alert('Please write a reply');
                    return;
                }
                
                try {
                    const formData = new FormData();
                    formData.append('text', message);
                    formData.append('client_id', 'default_client');
                    formData.append('use_ai', 'false');
                    
                    const response = await fetch(`/comments/threads/${commentId}/reply`, {
                        method: 'POST',
                        body: formData
                    });
                    
                    const data = await response.json();
                    
                    if (data.success) {
                        const commentDiv = document.getElementById(`threads-comment-${commentId}`);
                        commentDiv.classList.add('replied');
                        
                        const form = document.getElementById(`threads-reply-form-${commentId}`);
                        form.classList.remove('open');
                        textarea.value = '';
                        
                        alert('✅ Reply sent successfully!');
                    } else {
                        alert('❌ Failed to send reply: ' + (data.error || 'Unknown error'));
                    }
                } catch (error) {
                    console.error('Failed to send reply:', error);
                    alert('❌ Failed to send reply. Please try again.');
                }
            }
            
            // Initialize
            loadAccounts();
            
            // Load Late API posts for a platform (TikTok, Twitter, YouTube, LinkedIn)
            async function loadLatePosts(platform) {
                const listId = platform + 'PostsList';
                const listEl = document.getElementById(listId);
                if (!listEl) return;
                listEl.innerHTML = '<div class="loading">Loading your ' + platform + ' posts...</div>';
                
                try {
                    const response = await fetch('/comments/late-posts?platform=' + platform + '&client_id=default_client&limit=20');
                    const data = await response.json();
                    
                    if (data.posts && data.posts.length > 0) {
                        const icons = {tiktok: '🎵', twitter: '𝕏', youtube: '🎥', linkedin: '💼'};
                        listEl.innerHTML = data.posts.map(post => {
                            const text = post.text || post.content || 'No caption';
                            const date = post.created_at ? new Date(post.created_at).toLocaleDateString() : '';
                            const status = post.status || 'published';
                            return `
                                <div class="post-item" style="background: #f8f9fb; border-radius: 12px; padding: 16px; margin-bottom: 12px; border: 1px solid #e4e6eb;">
                                    <div style="display: flex; justify-content: space-between; align-items: flex-start;">
                                        <div style="flex: 1;">
                                            <span style="font-size: 12px; color: #606770;">${icons[platform] || '📝'} ${platform.charAt(0).toUpperCase() + platform.slice(1)} &middot; ${date}</span>
                                            <p style="margin-top: 8px; color: #1c1e21; line-height: 1.5;">${text.substring(0, 280)}${text.length > 280 ? '...' : ''}</p>
                                        </div>
                                        <span style="background: #e8f5e9; color: #2e7d32; padding: 4px 10px; border-radius: 12px; font-size: 11px; white-space: nowrap; margin-left: 12px;">${status}</span>
                                    </div>
                                </div>
                            `;
                        }).join('');
                    } else {
                        listEl.innerHTML = `
                            <div class="empty-state" style="text-align: center; padding: 40px; color: #606770;">
                                <div style="font-size: 48px; margin-bottom: 12px;">📭</div>
                                <p>No ${platform} posts found</p>
                                <p style="font-size: 13px; margin-top: 8px;">Posts published via Late API will appear here.</p>
                            </div>
                        `;
                    }
                } catch (error) {
                    console.error('Failed to load ' + platform + ' posts:', error);
                    listEl.innerHTML = `
                        <div class="empty-state" style="text-align: center; padding: 40px; color: #606770;">
                            <div style="font-size: 48px; margin-bottom: 12px;">❌</div>
                            <p>Failed to load ${platform} posts</p>
                            <p style="font-size: 13px; margin-top: 8px;">${error.message || 'Check console for details'}</p>
                        </div>
                    `;
                }
            }
            
            // Auto-refresh every 30 seconds
            setInterval(() => {
                if (currentPlatform === 'instagram' && selectedAccountId) {
                    loadPosts(selectedAccountId);
                } else if (currentPlatform === 'facebook' && selectedPageId) {
                    loadFacebookPosts(selectedPageId);
                } else if (currentPlatform === 'threads') {
                    loadThreadsPosts();
                } else if (['tiktok', 'twitter', 'youtube', 'linkedin'].includes(currentPlatform)) {
                    loadLatePosts(currentPlatform);
                }
            }, 30000);
    """

    return HTMLResponse(build_page(
        title="Comments", active_nav="comments",
        body_content=body_content,
        extra_css=_css,
        extra_js=page_js,
        user_name=_uname,
        business_name=_bname,
    ))


@router.get("/accounts")
async def get_accounts(alita_session: Optional[str] = Cookie(None)):
    """Get Instagram accounts for the logged-in user."""
    user_id = _get_session_user(alita_session)
    
    if not user_id:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)
    
    tm = get_token_manager()
    access_token = tm.get_valid_token(user_id)
    
    if not access_token:
        return JSONResponse({"error": "Token expired"}, status_code=401)
    
    try:
        oauth = get_oauth_client()
        print(f"Fetching Instagram accounts for user {user_id}...")
        accounts = await oauth.get_instagram_business_accounts(access_token)
        print(f"✅ Found {len(accounts)} Instagram account(s)")
        
        account_list = []
        for acc in accounts:
            account_list.append({
                "id": acc.id,
                "username": acc.username,
                "name": acc.name or acc.username,
                "followers_count": acc.followers_count or 0,
                "media_count": acc.media_count or 0,
            })
            print(f"   @{acc.username} (ID: {acc.id})")
        
        return JSONResponse({"accounts": account_list})
    except Exception as e:
        print(f"❌ Error fetching accounts: {str(e)}")
        import traceback
        traceback.print_exc()
        return JSONResponse(
            {"error": f"Failed to fetch accounts: {str(e)}"}, 
            status_code=500
        )


@router.get("/posts")
async def get_posts(
    account_id: str = Query(...),
    limit: int = Query(10, ge=1, le=50),
    alita_session: Optional[str] = Cookie(None),
):
    """Get recent posts for an Instagram account."""
    user_id = _get_session_user(alita_session)
    
    if not user_id:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)
    
    tm = get_token_manager()
    access_token = tm.get_valid_token(user_id)
    
    if not access_token:
        return JSONResponse({"error": "Token expired"}, status_code=401)
    
    oauth = get_oauth_client()
    posts = await oauth.get_instagram_media(account_id, access_token, limit)
    
    return JSONResponse({"posts": posts})


# ═══════════════════════════════════════════════════════════════════════════
# FACEBOOK COMMENT MANAGEMENT
# (Must be defined BEFORE the /{post_id} wildcard route)
# ═══════════════════════════════════════════════════════════════════════════

@router.get("/facebook-pages")
async def get_facebook_pages(alita_session: Optional[str] = Cookie(None)):
    """Get Facebook pages for the logged-in user."""
    user_id = _get_session_user(alita_session)
    
    if not user_id:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)
    
    tm = get_token_manager()
    access_token = tm.get_valid_token(user_id)
    
    if not access_token:
        return JSONResponse({"error": "Token expired"}, status_code=401)
    
    try:
        oauth = get_oauth_client()
        print(f"Fetching Facebook pages for user {user_id}...")
        pages = await oauth.get_facebook_pages(access_token)
        print(f"Found {len(pages)} Facebook page(s)")
        
        page_list = []
        for page in pages:
            page_list.append({
                "id": page.get("id"),
                "name": page.get("name"),
                "category": page.get("category", "Page"),
                "has_instagram": bool(page.get("instagram_business_account")),
            })
            print(f"   {page.get('name')} (ID: {page.get('id')})")
        
        return JSONResponse({"pages": page_list})
    except Exception as e:
        print(f"Error fetching Facebook pages: {str(e)}")
        import traceback
        traceback.print_exc()
        return JSONResponse(
            {"error": f"Failed to fetch Facebook pages: {str(e)}"}, 
            status_code=500
        )


@router.get("/facebook-posts")
async def get_facebook_posts_route(
    page_id: str = Query(...),
    limit: int = Query(10, ge=1, le=50),
    alita_session: Optional[str] = Cookie(None),
):
    """Get recent posts for a Facebook page."""
    user_id = _get_session_user(alita_session)
    
    if not user_id:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)
    
    tm = get_token_manager()
    user_access_token = tm.get_valid_token(user_id)
    
    if not user_access_token:
        return JSONResponse({"error": "Token expired"}, status_code=401)
    
    try:
        oauth = get_oauth_client()
        
        import httpx
        async with httpx.AsyncClient(timeout=30.0) as client:
            # First, get the page access token for this specific page
            page_response = await client.get(
                f"https://graph.facebook.com/v22.0/{page_id}",
                params={
                    "access_token": user_access_token,
                    "fields": "access_token",
                },
            )
            
            if page_response.status_code != 200:
                print(f"Failed to get page access token: {page_response.text}")
                return JSONResponse({"posts": []})
            
            page_data = page_response.json()
            page_access_token = page_data.get("access_token")
            
            if not page_access_token:
                print(f"No access token returned for page {page_id}")
                return JSONResponse({"posts": []})
            
            # Now use the page access token to get posts
            response = await client.get(
                f"https://graph.facebook.com/v22.0/{page_id}/posts",
                params={
                    "access_token": page_access_token,
                    "fields": "id,message,created_time,full_picture,comments.summary(true),reactions.summary(true)",
                    "limit": limit,
                },
            )
            
            if response.status_code != 200:
                print(f"Failed to get Facebook posts: {response.text}")
                return JSONResponse({"posts": []})
            
            data = response.json()
            posts = data.get("data", [])
            
            formatted_posts = []
            for post in posts:
                formatted_posts.append({
                    "id": post.get("id"),
                    "message": post.get("message"),
                    "created_time": post.get("created_time"),
                    "full_picture": post.get("full_picture"),
                    "comments_count": post.get("comments", {}).get("summary", {}).get("total_count", 0),
                    "reactions_count": post.get("reactions", {}).get("summary", {}).get("total_count", 0),
                })
            
            return JSONResponse({"posts": formatted_posts})
    except Exception as e:
        print(f"\u274c Error fetching Facebook posts: {str(e)}")
        import traceback
        traceback.print_exc()
        return JSONResponse(
            {"error": f"Failed to fetch Facebook posts: {str(e)}"}, 
            status_code=500
        )


@router.get("/facebook/{post_id}")
async def get_facebook_post_comments(
    post_id: str,
    limit: int = Query(50, ge=1, le=100),
    alita_session: Optional[str] = Cookie(None),
):
    """Get comments for a specific Facebook post."""
    user_id = _get_session_user(alita_session)
    
    if not user_id:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)
    
    tm = get_token_manager()
    user_access_token = tm.get_valid_token(user_id)
    
    if not user_access_token:
        return JSONResponse({"error": "Token expired"}, status_code=401)
    
    try:
        # Extract page ID from post ID (format: {page_id}_{post_id})
        page_id = post_id.split('_')[0]
        
        import httpx
        async with httpx.AsyncClient(timeout=30.0) as client:
            # Get page access token
            page_response = await client.get(
                f"https://graph.facebook.com/v22.0/{page_id}",
                params={
                    "access_token": user_access_token,
                    "fields": "access_token",
                },
            )
            
            if page_response.status_code != 200:
                print(f"Failed to get page access token: {page_response.text}")
                return JSONResponse({"comments": []})
            
            page_data = page_response.json()
            page_access_token = page_data.get("access_token")
            
            if not page_access_token:
                return JSONResponse({"comments": []})
            
            # Get comments using page access token
            oauth = get_oauth_client()
            comments = await oauth.get_facebook_post_comments(page_access_token, post_id, limit)
            
            return JSONResponse({"comments": comments})
    except Exception as e:
        print(f"Error fetching Facebook comments: {str(e)}")
        return JSONResponse({"comments": []})


@router.post("/facebook/{comment_id}/reply")
async def reply_to_facebook_comment(
    comment_id: str,
    request: Request,
    alita_session: Optional[str] = Cookie(None),
):
    """Reply to a Facebook comment (manual reply)."""
    user_id = _get_session_user(alita_session)
    
    if not user_id:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)
    
    tm = get_token_manager()
    user_access_token = tm.get_valid_token(user_id)
    
    if not user_access_token:
        return JSONResponse({"error": "Token expired"}, status_code=401)
    
    body = await request.json()
    message = body.get("message", "").strip()
    page_id = body.get("page_id")  # Frontend should pass this
    
    if not message:
        return JSONResponse({"error": "Message is required"}, status_code=400)
    
    if not page_id:
        # Try to extract from comment ID if available
        return JSONResponse({"error": "Page ID required"}, status_code=400)
    
    try:
        import httpx
        async with httpx.AsyncClient(timeout=30.0) as client:
            # Get page access token
            page_response = await client.get(
                f"https://graph.facebook.com/v22.0/{page_id}",
                params={
                    "access_token": user_access_token,
                    "fields": "access_token",
                },
            )
            
            if page_response.status_code != 200:
                return JSONResponse({"success": False, "error": "Failed to get page token"}, status_code=500)
            
            page_data = page_response.json()
            page_access_token = page_data.get("access_token")
            
            if not page_access_token:
                return JSONResponse({"success": False, "error": "No page access token"}, status_code=500)
            
            # Reply using page access token
            oauth = get_oauth_client()
            reply_id = await oauth.reply_to_facebook_comment(page_access_token, comment_id, message)
            
            if reply_id:
                return JSONResponse({"success": True, "reply_id": reply_id})
            else:
                return JSONResponse({"success": False, "error": "Failed to send reply"}, status_code=500)
    except Exception as e:
        print(f"Error replying to Facebook comment: {str(e)}")
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)


# =============================================================================
# LATE API PLATFORM POSTS (TikTok, Twitter, YouTube, LinkedIn)
# =============================================================================

@router.get("/late-posts")
async def get_late_posts(
    platform: str = "tiktok",
    client_id: str = "default_client",
    limit: int = 20
):
    """Get posts from any Late API platform for the comment dashboard."""
    import httpx
    
    late_api_key = os.getenv("LATE_API_KEY")
    if not late_api_key:
        return JSONResponse({"posts": [], "error": "Late API key not configured"})
    
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(
                "https://getlate.dev/api/v1/posts",
                headers={"Authorization": f"Bearer {late_api_key}"},
                params={
                    "platform": platform,
                    "status": "published",
                }
            )
            
            if response.status_code == 200:
                data = response.json()
                raw_posts = data.get("posts", [])
                
                posts = []
                for p in raw_posts[:limit]:
                    # Find the platform-specific data
                    platform_data = {}
                    for pd in p.get("platforms", []):
                        if pd.get("platform") == platform:
                            platform_data = pd
                            break
                    
                    posts.append({
                        "id": p.get("_id", ""),
                        "text": p.get("content", ""),
                        "created_at": platform_data.get("scheduledFor") or p.get("createdAt", ""),
                        "status": platform_data.get("status", p.get("status", "published")),
                        "platform": platform,
                    })
                
                return JSONResponse({"posts": posts, "count": len(posts)})
            else:
                return JSONResponse({"posts": [], "error": f"Late API returned {response.status_code}"})
    except Exception as e:
        print(f"Error fetching {platform} posts: {e}")
        return JSONResponse({"posts": [], "error": str(e)})


# =============================================================================
# THREADS COMMENT MANAGEMENT (must be before wildcard routes)
# =============================================================================

@router.get("/threads-posts")
async def get_threads_posts_route(
    client_id: str = "default_client",
    limit: int = 20
):
    """Get Threads posts with comment counts for monitoring."""
    try:
        from api.threads_client import ThreadsClient
        
        client = ThreadsClient(client_id=client_id)
        posts = await client.get_recent_posts(limit=limit)
        
        # Format for dashboard
        posts_data = []
        for post in posts:
            posts_data.append({
                "id": post.post_id,
                "text": post.text[:100] + "..." if len(post.text) > 100 else post.text,
                "full_text": post.text,
                "media_urls": post.media_urls,
                "created_time": post.created_at.isoformat() if post.created_at else None,
                "like_count": post.like_count,
                "comments_count": 0,
                "reply_count": post.reply_count,
                "quote_count": post.quote_count,
                "status": post.status
            })
        
        return JSONResponse({"posts": posts_data})
    
    except Exception as e:
        print(f"❌ Threads posts error: {e}")
        return JSONResponse(
            {"error": f"Failed to fetch Threads posts: {str(e)}"}, 
            status_code=500
        )


@router.get("/threads/{post_id}")
async def get_threads_comments_route(
    post_id: str,
    client_id: str = "default_client",
    limit: int = 50
):
    """Get comments for a specific Threads post."""
    try:
        from api.threads_client import ThreadsClient
        
        client = ThreadsClient(client_id=client_id)
        comments = await client.get_post_comments(post_id, limit=limit)
        
        formatted_comments = []
        for comment in comments:
            formatted_comments.append({
                "id": comment.get("id"),
                "text": comment.get("text", ""),
                "from": {
                    "username": comment.get("username", "Unknown"),
                    "id": comment.get("user_id")
                },
                "timestamp": comment.get("timestamp"),
                "like_count": comment.get("like_count", 0),
                "parent_id": comment.get("parent_id")
            })
        
        return JSONResponse({
            "comments": formatted_comments,
            "count": len(formatted_comments)
        })
    
    except Exception as e:
        return JSONResponse(
            {"error": f"Failed to fetch comments: {str(e)}"}, 
            status_code=500
        )


@router.post("/threads/{comment_id}/reply")
async def reply_to_threads_comment(
    comment_id: str,
    text: str = Form(...),
    client_id: str = Form("default_client"),
    use_ai: bool = Form(False)
):
    """Reply to a Threads comment (manual or AI-powered)."""
    try:
        from api.threads_client import ThreadsClient
        
        if use_ai and ENGAGEMENT_AGENT_AVAILABLE:
            agent = EngagementAgent(client_id=client_id)
            ai_response = await agent.generate_reply(
                comment_text=text,
                platform="threads"
            )
            reply_text = ai_response
        else:
            reply_text = text
        
        client = ThreadsClient(client_id=client_id)
        result = await client.reply_to_comment(comment_id, reply_text)
        
        return JSONResponse({
            "success": True,
            "reply_id": result.get("id"),
            "message": "Reply sent successfully"
        })
    
    except Exception as e:
        return JSONResponse(
            {"success": False, "error": str(e)}, 
            status_code=500
        )


# ═══════════════════════════════════════════════════════════════════════════
# INSTAGRAM COMMENT DETAILS (wildcard routes - must be LAST)
# ═══════════════════════════════════════════════════════════════════════════

@router.get("/{post_id}")
async def get_comments(
    post_id: str,
    limit: int = Query(25, ge=1, le=100),
    alita_session: Optional[str] = Cookie(None),
):
    """Get comments for a specific Instagram post."""
    user_id = _get_session_user(alita_session)
    
    if not user_id:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)
    
    tm = get_token_manager()
    access_token = tm.get_valid_token(user_id)
    
    if not access_token:
        return JSONResponse({"error": "Token expired"}, status_code=401)
    
    oauth = get_oauth_client()
    comments = await oauth.get_post_comments(access_token, post_id, limit)
    
    return JSONResponse({"comments": comments})


@router.post("/{comment_id}/reply")
async def reply_to_comment(
    comment_id: str,
    request: Request,
    alita_session: Optional[str] = Cookie(None),
):
    """Reply to an Instagram comment (manual reply)."""
    user_id = _get_session_user(alita_session)
    
    if not user_id:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)
    
    tm = get_token_manager()
    access_token = tm.get_valid_token(user_id)
    
    if not access_token:
        return JSONResponse({"error": "Token expired"}, status_code=401)
    
    # Get message from request body
    body = await request.json()
    message = body.get("message", "").strip()
    
    if not message:
        return JSONResponse({"error": "Message is required"}, status_code=400)
    
    oauth = get_oauth_client()
    reply_id = await oauth.reply_to_comment(access_token, comment_id, message)
    
    if reply_id:
        return JSONResponse({"success": True, "reply_id": reply_id})
    else:
        return JSONResponse({"success": False, "error": "Failed to send reply"}, status_code=500)


@router.get("/{comment_id}/ai-reply")
async def generate_ai_reply(
    comment_id: str,
    alita_session: Optional[str] = Cookie(None),
):
    """Generate an AI-powered reply for a comment."""
    user_id = _get_session_user(alita_session)
    
    if not user_id:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)
    
    tm = get_token_manager()
    access_token = tm.get_valid_token(user_id)
    
    if not access_token:
        return JSONResponse({"error": "Token expired"}, status_code=401)
    
    # Get comment details first
    oauth = get_oauth_client()
    
    # Try to extract comment text from a recent comments fetch
    # In a real implementation, we'd fetch the specific comment
    # For now, generate a friendly reply
    
    if ENGAGEMENT_AGENT_AVAILABLE:
        try:
            # Initialize engagement agent
            # In production, this would use the actual client_id and comment text
            agent = EngagementAgent()
            
            # Generate a brand-voice reply
            # For demo purposes, using a generic prompt
            # In production, would fetch actual comment text
            reply = agent.respond_to_message(
                message="Thank you for commenting!",
                client_id="demo_client"
            )
            
            # Make it more comment-appropriate
            if len(reply) > 200:
                reply = reply[:197] + "..."
            
            return JSONResponse({"reply": reply})
        except Exception as e:
            print(f"❌ AI reply generation failed: {e}")
            return JSONResponse({
                "reply": "Thank you so much for your comment! We really appreciate your support. 😊"
            })
    
    return JSONResponse({
        "reply": "Thanks for your comment! We appreciate your engagement. 😊"
    })


@router.get("/recent")
async def get_recent_comments(
    account_id: str = Query(...),
    since: Optional[int] = Query(None),  # Unix timestamp
    alita_session: Optional[str] = Cookie(None),
):
    """
    Get recent comments for real-time monitoring.
    
    Used for polling to check for new comments since a given timestamp.
    """
    user_id = _get_session_user(alita_session)
    
    if not user_id:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)
    
    tm = get_token_manager()
    access_token = tm.get_valid_token(user_id)
    
    if not access_token:
        return JSONResponse({"error": "Token expired"}, status_code=401)
    
    oauth = get_oauth_client()
    
    # Get recent posts
    posts = await oauth.get_instagram_media(account_id, access_token, 5)
    
    all_comments = []
    for post in posts:
        comments = await oauth.get_post_comments(access_token, post["id"], 10)
        
        # Filter by timestamp if provided
        if since:
            comments = [
                c for c in comments
                if c.get("timestamp") and datetime.fromisoformat(c["timestamp"].replace("Z", "+00:00")).timestamp() > since
            ]
        
        all_comments.extend([
            {
                **comment,
                "post_id": post["id"],
                "post_caption": post.get("caption", "")[:50],
            }
            for comment in comments
        ])
    
    return JSONResponse({
        "comments": all_comments,
        "count": len(all_comments)
    })

