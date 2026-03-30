"""
WhatsApp & Threads Management Routes
====================================
Dashboard routes for WhatsApp Business messaging and Threads posting.

ROUTES:
- /messaging/dashboard - Main dashboard with platform tabs
- /messaging/whatsapp-templates - Get message templates
- /messaging/whatsapp-send - Send WhatsApp message
- /messaging/whatsapp-conversations - Get active conversations
- /messaging/threads-posts - Get Threads posts
- /messaging/threads-create - Create Threads post
- /messaging/threads-schedule - Schedule Threads post
"""

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse
from typing import Optional
from pydantic import BaseModel
import os
import sys

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from api.whatsapp_client import WhatsAppBusinessClient, MessageTemplate
from api.threads_client import ThreadsClient
from api.threads_meta_client import ThreadsMetaClient
from api.token_manager import TokenManager

router = APIRouter(prefix="/messaging", tags=["messaging"])
tm = TokenManager()


# =============================================================================
# REQUEST MODELS
# =============================================================================

class WhatsAppSendRequest(BaseModel):
    to: str
    message: str
    message_type: str = "text"  # text, template, image, video
    template_name: Optional[str] = None
    template_params: Optional[list] = None
    media_url: Optional[str] = None


class ThreadsPostRequest(BaseModel):
    text: str
    media_urls: Optional[list] = None
    scheduled_time: Optional[str] = None


# =============================================================================
# DASHBOARD
# =============================================================================

@router.get("/dashboard", response_class=HTMLResponse)
async def get_messaging_dashboard():
    """Main dashboard for WhatsApp & Threads management."""
    
    html = """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Messaging Dashboard | Alita AI</title>
        <style>
            * {
                margin: 0;
                padding: 0;
                box-sizing: border-box;
            }
            
            .home-btn {
                position: fixed;
                top: 20px;
                left: 20px;
                padding: 10px 20px;
                background: rgba(255,255,255,0.1);
                color: white;
                text-decoration: none;
                border-radius: 8px;
                font-weight: 600;
                box-shadow: 0 2px 8px rgba(0,0,0,0.3);
                z-index: 1000;
                backdrop-filter: blur(10px);
                transition: all 0.2s;
            }
            .home-btn:hover {
                background: rgba(255,255,255,0.2);
                transform: scale(1.02);
            }
            
            .back-btn {
                position: fixed;
                top: 20px;
                left: 120px;
                padding: 10px 20px;
                background: rgba(255,255,255,0.1);
                color: white;
                text-decoration: none;
                border-radius: 8px;
                font-weight: 600;
                box-shadow: 0 2px 8px rgba(0,0,0,0.3);
                z-index: 1000;
                backdrop-filter: blur(10px);
                transition: all 0.2s;
            }
            .back-btn:hover {
                background: rgba(255,255,255,0.2);
                transform: scale(1.02);
            }
            
            body {
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
                background: linear-gradient(135deg, #0a0e27 0%, #1a1f3a 100%);
                color: #e0e0e0;
                min-height: 100vh;
                padding: 20px;
            }
            
            .header {
                text-align: center;
                padding: 30px 20px;
                background: rgba(255,255,255,0.05);
                border-radius: 15px;
                margin-bottom: 30px;
                backdrop-filter: blur(10px);
            }
            
            .home-btn {
                position: fixed;
                top: 20px;
                left: 20px;
                padding: 10px 20px;
                background: rgba(255,255,255,0.1);
                color: white;
                text-decoration: none;
                border-radius: 8px;
                font-weight: 600;
                box-shadow: 0 2px 8px rgba(0,0,0,0.3);
                z-index: 1000;
                backdrop-filter: blur(10px);
                transition: all 0.2s;
            }
            .home-btn:hover {
                background: rgba(255,255,255,0.2);
                transform: scale(1.02);
            }
            
            .header h1 {
                color: #00d9ff;
                font-size: 2.5em;
                margin-bottom: 10px;
                text-shadow: 0 0 20px rgba(0,217,255,0.5);
            }
            
            .header p {
                color: #b0b0b0;
                font-size: 1.1em;
            }
            
            .platform-tabs {
                display: flex;
                justify-content: center;
                gap: 20px;
                margin-bottom: 30px;
                flex-wrap: wrap;
            }
            
            .tab-button {
                padding: 15px 30px;
                background: rgba(255,255,255,0.05);
                border: 2px solid rgba(255,255,255,0.1);
                border-radius: 10px;
                color: #e0e0e0;
                cursor: pointer;
                transition: all 0.3s ease;
                font-size: 1.1em;
                backdrop-filter: blur(10px);
            }
            
            .tab-button:hover {
                background: rgba(255,255,255,0.1);
                border-color: rgba(0,217,255,0.5);
                transform: translateY(-2px);
            }
            
            .tab-button.active {
                background: linear-gradient(135deg, #00d9ff 0%, #0099cc 100%);
                border-color: #00d9ff;
                color: #000;
                font-weight: bold;
                box-shadow: 0 0 20px rgba(0,217,255,0.3);
            }
            
            .platform-content {
                display: none;
                animation: fadeIn 0.5s ease;
            }
            
            .platform-content.active {
                display: block;
            }
            
            @keyframes fadeIn {
                from { opacity: 0; transform: translateY(20px); }
                to { opacity: 1; transform: translateY(0); }
            }
            
            .section {
                background: rgba(255,255,255,0.05);
                border-radius: 15px;
                padding: 25px;
                margin-bottom: 20px;
                border: 1px solid rgba(255,255,255,0.1);
                backdrop-filter: blur(10px);
            }
            
            .section h2 {
                color: #00d9ff;
                margin-bottom: 20px;
                font-size: 1.5em;
            }
            
            .form-group {
                margin-bottom: 20px;
            }
            
            .form-group label {
                display: block;
                margin-bottom: 8px;
                color: #b0b0b0;
                font-weight: 500;
            }
            
            input[type="text"],
            input[type="tel"],
            textarea,
            select {
                width: 100%;
                padding: 12px 15px;
                background: rgba(0,0,0,0.3);
                border: 1px solid rgba(255,255,255,0.2);
                border-radius: 8px;
                color: #e0e0e0;
                font-size: 1em;
                transition: all 0.3s ease;
            }
            
            input:focus,
            textarea:focus,
            select:focus {
                outline: none;
                border-color: #00d9ff;
                box-shadow: 0 0 10px rgba(0,217,255,0.3);
            }
            
            textarea {
                min-height: 100px;
                resize: vertical;
                font-family: inherit;
            }
            
            button {
                padding: 12px 30px;
                background: linear-gradient(135deg, #00d9ff 0%, #0099cc 100%);
                border: none;
                border-radius: 8px;
                color: #000;
                font-size: 1em;
                font-weight: bold;
                cursor: pointer;
                transition: all 0.3s ease;
            }
            
            button:hover {
                transform: translateY(-2px);
                box-shadow: 0 5px 20px rgba(0,217,255,0.4);
            }
            
            button:disabled {
                background: #555;
                cursor: not-allowed;
                transform: none;
            }
            
            .message-list {
                max-height: 400px;
                overflow-y: auto;
            }
            
            .message-item {
                background: rgba(0,0,0,0.3);
                border-left: 3px solid #00d9ff;
                padding: 15px;
                margin-bottom: 10px;
                border-radius: 8px;
            }
            
            .message-item.sent {
                border-left-color: #4CAF50;
            }
            
            .message-item.received {
                border-left-color: #00d9ff;
            }
            
            .post-item {
                background: rgba(0,0,0,0.3);
                padding: 15px;
                margin-bottom: 15px;
                border-radius: 8px;
                border: 1px solid rgba(255,255,255,0.1);
            }
            
            .post-item h3 {
                color: #00d9ff;
                margin-bottom: 10px;
                font-size: 1.1em;
            }
            
            .post-stats {
                display: flex;
                gap: 20px;
                margin-top: 10px;
                color: #b0b0b0;
                font-size: 0.9em;
            }
            
            .stat {
                display: flex;
                align-items: center;
                gap: 5px;
            }
            
            .status {
                display: inline-block;
                padding: 4px 12px;
                border-radius: 12px;
                font-size: 0.85em;
                font-weight: bold;
            }
            
            .status.success { background: #4CAF50; color: #000; }
            .status.pending { background: #FFC107; color: #000; }
            .status.error { background: #F44336; color: #fff; }
            
            .loading {
                text-align: center;
                padding: 40px;
                color: #b0b0b0;
            }
            
            .spinner {
                border: 3px solid rgba(255,255,255,0.1);
                border-radius: 50%;
                border-top: 3px solid #00d9ff;
                width: 40px;
                height: 40px;
                animation: spin 1s linear infinite;
                margin: 0 auto 20px;
            }
            
            @keyframes spin {
                0% { transform: rotate(0deg); }
                100% { transform: rotate(360deg); }
            }
            
            .alert {
                padding: 15px 20px;
                border-radius: 8px;
                margin-bottom: 20px;
            }
            
            .alert.success {
                background: rgba(76, 175, 80, 0.2);
                border: 1px solid #4CAF50;
                color: #4CAF50;
            }
            
            .alert.error {
                background: rgba(244, 67, 54, 0.2);
                border: 1px solid #F44336;
                color: #F44336;
            }
        </style>
    </head>
    <body>
        <a href="/" class="home-btn">🏠 Home</a>
        <a href="/social/dashboard" class="back-btn">← Back</a>
        <div class="header">
            <h1>💬 WhatsApp Business Dashboard</h1>
            <p>Manage WhatsApp Business messaging</p>
        </div>
        
        <!-- WhatsApp Content -->
        <div id="whatsapp-content" class="platform-content active">
            <div class="section">
                <h2>📤 Send WhatsApp Message</h2>
                <div id="whatsapp-alert"></div>
                <form onsubmit="sendWhatsAppMessage(event)">
                    <div class="form-group">
                        <label for="whatsapp-to">Recipient Phone Number (with country code, no +)</label>
                        <input type="tel" id="whatsapp-to" placeholder="1234567890" required>
                    </div>
                    
                    <div class="form-group">
                        <label for="message-type">Message Type</label>
                        <select id="message-type" onchange="toggleMessageFields()">
                            <option value="text">Text Message</option>
                            <option value="template">Template Message</option>
                            <option value="image">Image</option>
                        </select>
                    </div>
                    
                    <div class="form-group" id="text-field">
                        <label for="whatsapp-message">Message</label>
                        <textarea id="whatsapp-message" placeholder="Type your message here..." required></textarea>
                    </div>
                    
                    <div class="form-group" id="template-field" style="display:none;">
                        <label for="template-name">Template Name</label>
                        <select id="template-name">
                            <option value="">Loading templates...</option>
                        </select>
                    </div>
                    
                    <div class="form-group" id="media-field" style="display:none;">
                        <label for="media-url">Media URL</label>
                        <input type="text" id="media-url" placeholder="https://example.com/image.jpg">
                    </div>
                    
                    <button type="submit">Send Message</button>
                </form>
            </div>
            
            <div class="section">
                <h2>💬 Recent Conversations</h2>
                <div id="conversations-list" class="message-list">
                    <div class="loading">
                        <div class="spinner"></div>
                        <p>Loading conversations...</p>
                    </div>
                </div>
            </div>
            
            <div class="section">
                <h2>📋 Message Templates</h2>
                <div id="templates-list">
                    <div class="loading">
                        <div class="spinner"></div>
                        <p>Loading templates...</p>
                    </div>
                </div>
            </div>
        </div>
        
        <!-- Threads Content -->
        <div id="threads-content" class="platform-content">
            <div class="section">
                <h2>✍️ Create Threads Post</h2>
                <div id="threads-alert"></div>
                <form onsubmit="createThreadsPost(event)">
                    <div class="form-group">
                        <label for="threads-text">Post Text (max 500 characters)</label>
                        <textarea id="threads-text" maxlength="500" placeholder="What's on your mind?" required oninput="updateCharCount()"></textarea>
                        <small id="char-count" style="color: #b0b0b0;">0 / 500 characters</small>
                    </div>
                    
                    <div class="form-group">
                        <label for="threads-media">Media URL (optional)</label>
                        <input type="text" id="threads-media" placeholder="https://example.com/image.jpg">
                    </div>
                    
                    <div class="form-group">
                        <label>
                            <input type="checkbox" id="schedule-post" onchange="toggleSchedule()">
                            Schedule for later
                        </label>
                    </div>
                    
                    <div class="form-group" id="schedule-field" style="display:none;">
                        <label for="schedule-time">Schedule Time</label>
                        <input type="datetime-local" id="schedule-time">
                    </div>
                    
                    <button type="submit">Post to Threads</button>
                </form>
            </div>
            
            <div class="section">
                <h2>📊 Recent Posts</h2>
                <div id="threads-posts-list">
                    <div class="loading">
                        <div class="spinner"></div>
                        <p>Loading posts...</p>
                    </div>
                </div>
            </div>
            
            <div class="section">
                <h2>📈 Account Analytics</h2>
                <div id="threads-analytics">
                    <div class="loading">
                        <div class="spinner"></div>
                        <p>Loading analytics...</p>
                    </div>
                </div>
            </div>
        </div>
        
        <script>
            // Platform switching
            function switchPlatform(platform) {
                // Update tabs
                document.querySelectorAll('.tab-button').forEach(btn => {
                    btn.classList.remove('active');
                });
                event.target.classList.add('active');
                
                // Update content
                document.querySelectorAll('.platform-content').forEach(content => {
                    content.classList.remove('active');
                });
                document.getElementById(platform + '-content').classList.add('active');
                
                // Load data for platform
                if (platform === 'whatsapp') {
                    loadWhatsAppTemplates();
                    loadConversations();
                } else if (platform === 'threads') {
                    loadThreadsPosts();
                    loadThreadsAnalytics();
                }
            }
            
            // WhatsApp Functions
            function toggleMessageFields() {
                const type = document.getElementById('message-type').value;
                document.getElementById('text-field').style.display = type === 'text' ? 'block' : 'none';
                document.getElementById('template-field').style.display = type === 'template' ? 'block' : 'none';
                document.getElementById('media-field').style.display = (type === 'image' || type === 'video') ? 'block' : 'none';
            }
            
            async function loadWhatsAppTemplates() {
                try {
                    const response = await fetch('/messaging/whatsapp-templates');
                    const data = await response.json();
                    
                    const select = document.getElementById('template-name');
                    const listDiv = document.getElementById('templates-list');
                    
                    if (data.templates && data.templates.length > 0) {
                        select.innerHTML = data.templates.map(t => 
                            `<option value="${t.name}">${t.name} (${t.status})</option>`
                        ).join('');
                        
                        listDiv.innerHTML = data.templates.map(t => `
                            <div class="message-item">
                                <strong>${t.name}</strong>
                                <span class="status ${t.status.toLowerCase()}">${t.status}</span>
                                <p style="margin-top: 8px; color: #b0b0b0;">${t.category}</p>
                            </div>
                        `).join('');
                    } else {
                        select.innerHTML = '<option value="">No templates available</option>';
                        listDiv.innerHTML = '<p style="color: #b0b0b0;">No message templates found. Create templates in Meta Business Suite.</p>';
                    }
                } catch (error) {
                    console.error('Error loading templates:', error);
                }
            }
            
            async function loadConversations() {
                const listDiv = document.getElementById('conversations-list');
                listDiv.innerHTML = '<p style="color: #b0b0b0; padding: 20px;">No active conversations. Send a message to start.</p>';
            }
            
            async function sendWhatsAppMessage(event) {
                event.preventDefault();
                
                const type = document.getElementById('message-type').value;
                const payload = {
                    to: document.getElementById('whatsapp-to').value,
                    message_type: type,
                    message: type === 'text' ? document.getElementById('whatsapp-message').value : '',
                    template_name: type === 'template' ? document.getElementById('template-name').value : null,
                    media_url: (type === 'image' || type === 'video') ? document.getElementById('media-url').value : null
                };
                
                const alertDiv = document.getElementById('whatsapp-alert');
                alertDiv.innerHTML = '<div class="loading"><div class="spinner"></div><p>Sending message...</p></div>';
                
                try {
                    const response = await fetch('/messaging/whatsapp-send', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify(payload)
                    });
                    
                    const result = await response.json();
                    
                    if (result.success) {
                        alertDiv.innerHTML = '<div class="alert success">Message sent successfully!</div>';
                        event.target.reset();
                    } else {
                        alertDiv.innerHTML = `<div class="alert error">Failed: ${result.error}</div>`;
                    }
                } catch (error) {
                    alertDiv.innerHTML = `<div class="alert error">Error: ${error.message}</div>`;
                }
                
                setTimeout(() => { alertDiv.innerHTML = ''; }, 5000);
            }
            
            // Threads Functions
            function toggleSchedule() {
                const scheduleField = document.getElementById('schedule-field');
                scheduleField.style.display = document.getElementById('schedule-post').checked ? 'block' : 'none';
            }
            
            function updateCharCount() {
                const text = document.getElementById('threads-text').value;
                document.getElementById('char-count').textContent = `${text.length} / 500 characters`;
            }
            
            async function loadThreadsPosts() {
                const listDiv = document.getElementById('threads-posts-list');
                listDiv.innerHTML = '<p style="color: #b0b0b0; padding: 20px;">No recent posts. Create your first post above!</p>';
            }
            
            async function loadThreadsAnalytics() {
                const analyticsDiv = document.getElementById('threads-analytics');
                analyticsDiv.innerHTML = '<p style="color: #b0b0b0; padding: 20px;">Analytics will appear here after posting.</p>';
            }
            
            async function createThreadsPost(event) {
                event.preventDefault();
                
                const text = document.getElementById('threads-text').value;
                const mediaUrl = document.getElementById('threads-media').value;
                const scheduled = document.getElementById('schedule-post').checked;
                const scheduleTime = document.getElementById('schedule-time').value;
                
                const payload = {
                    text: text,
                    media_urls: mediaUrl ? [mediaUrl] : null,
                    scheduled_time: scheduled ? new Date(scheduleTime).toISOString() : null
                };
                
                const alertDiv = document.getElementById('threads-alert');
                alertDiv.innerHTML = '<div class="loading"><div class="spinner"></div><p>Creating post...</p></div>';
                
                try {
                    const response = await fetch('/messaging/threads-create', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify(payload)
                    });
                    
                    const result = await response.json();
                    
                    if (result.success) {
                        alertDiv.innerHTML = '<div class="alert success">Post created successfully!</div>';
                        event.target.reset();
                        updateCharCount();
                        loadThreadsPosts();
                    } else {
                        alertDiv.innerHTML = `<div class="alert error">Failed: ${result.error}</div>`;
                    }
                } catch (error) {
                    alertDiv.innerHTML = `<div class="alert error">Error: ${error.message}</div>`;
                }
                
                setTimeout(() => { alertDiv.innerHTML = ''; }, 5000);
            }
            
            // Initial load
            loadWhatsAppTemplates();
            loadConversations();
        </script>
    </body>
    </html>
    """
    
    return html


# =============================================================================
# WHATSAPP ROUTES
# =============================================================================

@router.get("/whatsapp-templates")
async def get_whatsapp_templates():
    """Get all WhatsApp message templates."""
    try:
        client = WhatsAppBusinessClient()
        templates = await client.get_message_templates()
        
        if "error" in templates:
            return {"templates": [], "error": templates["error"]}
        
        # Parse templates
        template_list = []
        for template in templates.get("data", []):
            template_list.append({
                "name": template.get("name"),
                "status": template.get("status"),
                "category": template.get("category"),
                "language": template.get("language")
            })
        
        return {"templates": template_list}
    except Exception as e:
        return {"templates": [], "error": str(e)}


@router.post("/whatsapp-send")
async def send_whatsapp_message(request: WhatsAppSendRequest):
    """Send a WhatsApp message."""
    try:
        client = WhatsAppBusinessClient()
        
        if request.message_type == "text":
            result = await client.send_text_message(
                to=request.to,
                text=request.message
            )
        elif request.message_type == "template":
            result = await client.send_template_message(
                to=request.to,
                template_name=request.template_name,
                parameters=request.template_params
            )
        elif request.message_type in ["image", "video", "document"]:
            result = await client.send_media_message(
                to=request.to,
                media_type=request.message_type,
                media_url=request.media_url,
                caption=request.message
            )
        else:
            return {"success": False, "error": "Invalid message type"}
        
        if "error" in result:
            return {"success": False, "error": str(result["error"])}
        
        return {"success": True, "message_id": result.get("messages", [{}])[0].get("id")}
    except Exception as e:
        return {"success": False, "error": str(e)}


# =============================================================================
# THREADS ROUTES
# =============================================================================

@router.post("/threads-create")
async def create_threads_post(request: ThreadsPostRequest):
    """Create a Threads post via Late API."""
    try:
        client_id = getattr(request, 'client_id', 'default_client')
        client = ThreadsClient(client_id=client_id)
        
        post = await client.create_post(
            text=request.text,
            media_urls=request.media_urls,
            scheduled_time=request.scheduled_time
        )
        
        if post.status == "failed":
            return {"success": False, "error": "Failed to create post"}
        
        return {
            "success": True,
            "post_id": post.post_id,
            "status": post.status
        }
    except ValueError as e:
        return {"success": False, "error": str(e)}
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.get("/threads-posts")
async def get_threads_posts(client_id: str = "default_client", limit: int = 20):
    """Get recent Threads posts."""
    try:
        client = ThreadsClient(client_id=client_id)
        posts = await client.get_recent_posts(limit=limit)
        
        # Convert to dict format
        posts_data = []
        for post in posts:
            posts_data.append({
                "post_id": post.post_id,
                "text": post.text,
                "created_at": post.created_at.isoformat() if post.created_at else None,
                "like_count": post.like_count,
                "reply_count": post.reply_count,
                "quote_count": post.quote_count,
                "status": post.status
            })
        
        return {"posts": posts_data}
    except Exception as e:
        return {"posts": [], "error": str(e)}


@router.get("/threads-analytics")
async def get_threads_analytics():
    """Get Threads account analytics."""
    try:
        client = ThreadsClient(client_id="default_client")
        analytics = await client.get_account_analytics()
        return analytics
    except Exception as e:
        return {"error": str(e)}


@router.get("/threads-comments/{post_id}")
async def get_threads_comments(post_id: str, client_id: str = "default_client", limit: int = 50):
    """Get comments on a Threads post."""
    try:
        client = ThreadsClient(client_id=client_id)
        comments = await client.get_post_comments(post_id, limit=limit)
        return {"comments": comments}
    except Exception as e:
        return {"comments": [], "error": str(e)}


class ThreadsReplyRequest(BaseModel):
    comment_id: str
    text: str
    client_id: str = "default_client"


@router.post("/threads-reply")
async def reply_to_threads_comment(request: ThreadsReplyRequest):
    """Reply to a comment on Threads."""
    try:
        client = ThreadsClient(client_id=request.client_id)
        result = await client.reply_to_comment(request.comment_id, request.text)
        
        if "error" in result:
            return {"success": False, "error": result["error"]}
        
        return {"success": True, "reply_id": result.get("id")}
    except Exception as e:
        return {"success": False, "error": str(e)}
