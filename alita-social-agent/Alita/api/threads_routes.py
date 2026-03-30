"""
Threads Dashboard Routes - Dedicated Threads management interface
Separate from WhatsApp Business for better UX
"""

from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from typing import Optional
from pydantic import BaseModel
import sys
import os

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from agents.content_agent import ContentCreationAgent, ContentRequest

router = APIRouter(prefix="/threads", tags=["Threads"])


class ThreadsPostRequest(BaseModel):
    text: str
    media_urls: Optional[list] = None
    scheduled_time: Optional[str] = None


class AIContentRequest(BaseModel):
    topic: str
    tone: Optional[str] = "casual"
    client_id: str = "default_client"


@router.post("/generate-content")
async def generate_ai_content(request: AIContentRequest):
    """Generate AI content for Threads with RAG and style."""
    try:
        agent = ContentCreationAgent(client_id=request.client_id)
        
        content_request = ContentRequest(
            platform="instagram",  # Use instagram as threads uses similar format
            content_type="social_post",
            topic=request.topic,
            tone=request.tone,
            max_length=500,  # Threads limit
            include_hashtags=True,
            include_cta=False
        )
        
        result = await agent.generate_content(content_request, use_rag=True)
        
        return {
            "success": True,
            "content": result.content,
            "word_count": result.word_count,
            "hashtags": result.hashtags
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }


@router.get("/dashboard", response_class=HTMLResponse)
async def threads_dashboard():
    """Dedicated Threads management dashboard."""
    
    return """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Threads Dashboard | Alita AI</title>
        <style>
            * { margin: 0; padding: 0; box-sizing: border-box; }
            
            body {
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
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
            
            .header h1 {
                background: linear-gradient(135deg, #833ab4, #fd1d1d, #fcb045);
                -webkit-background-clip: text;
                -webkit-text-fill-color: transparent;
                font-size: 2.5em;
                margin-bottom: 10px;
                text-shadow: 0 0 20px rgba(255,255,255,0.1);
            }
            
            .header p { color: #b0b0b0; font-size: 1.1em; }
            
            .back-btn, .home-btn {
                position: fixed;
                top: 20px;
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
            .home-btn { left: 20px; }
            .back-btn { left: 120px; }
            .back-btn:hover, .home-btn:hover {
                background: rgba(255,255,255,0.2);
                transform: scale(1.02);
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
                color: #fd1d1d;
                margin-bottom: 20px;
                font-size: 1.5em;
            }
            
            .form-group { margin-bottom: 20px; }
            
            .form-group label {
                display: block;
                margin-bottom: 8px;
                color: #b0b0b0;
                font-weight: 500;
            }
            
            textarea {
                width: 100%;
                padding: 12px 15px;
                background: rgba(0,0,0,0.3);
                border: 1px solid rgba(255,255,255,0.2);
                border-radius: 8px;
                color: #e0e0e0;
                font-size: 1em;
                min-height: 120px;
                resize: vertical;
                font-family: inherit;
                transition: all 0.3s ease;
            }
            
            textarea:focus {
                outline: none;
                border-color: #fd1d1d;
                box-shadow: 0 0 10px rgba(253, 29, 29, 0.3);
            }
            
            input[type="text"], input[type="datetime-local"] {
                width: 100%;
                padding: 12px 15px;
                background: rgba(0,0,0,0.3);
                border: 1px solid rgba(255,255,255,0.2);
                border-radius: 8px;
                color: #e0e0e0;
                font-size: 1em;
            }
            
            input:focus {
                outline: none;
                border-color: #fd1d1d;
                box-shadow: 0 0 10px rgba(253, 29, 29, 0.3);
            }
            
            button {
                padding: 12px 30px;
                background: linear-gradient(135deg, #833ab4 0%, #fd1d1d 100%);
                border: none;
                border-radius: 8px;
                color: white;
                font-size: 1em;
                font-weight: bold;
                cursor: pointer;
                transition: all 0.3s ease;
            }
            
            button:hover {
                transform: translateY(-2px);
                box-shadow: 0 5px 20px rgba(253, 29, 29, 0.4);
            }
            
            .char-count {
                text-align: right;
                color: #b0b0b0;
                font-size: 0.9em;
                margin-top: 5px;
            }
            
            .char-count.warning { color: #ffc107; }
            .char-count.error { color: #f44336; }
            
            .alert {
                padding: 15px 20px;
                border-radius: 8px;
                margin-bottom: 20px;
                animation: fadeIn 0.3s ease;
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
            
            @keyframes fadeIn {
                from { opacity: 0; transform: translateY(-10px); }
                to { opacity: 1; transform: translateY(0); }
            }
            
            .post-item {
                background: rgba(0,0,0,0.3);
                padding: 15px;
                margin-bottom: 15px;
                border-radius: 8px;
                border: 1px solid rgba(255,255,255,0.1);
            }
            
            .post-stats {
                display: flex;
                gap: 20px;
                margin-top: 10px;
                color: #b0b0b0;
                font-size: 0.9em;
            }
        </style>
    </head>
    <body>
        <a href="/" class="home-btn">🏠 Home</a>
        <a href="/social/dashboard" class="back-btn">← Back</a>
        
        <div class="header">
            <h1>🧵 Threads Management</h1>
            <p>Create and manage your Threads posts</p>
        </div>
        
        <div class="section">
            <h2>✍️ Create Threads Post</h2>
            <div id="threads-alert"></div>
            
            <!-- AI Content Generation -->
            <div class="form-group" style="background: rgba(131, 58, 180, 0.1); padding: 15px; border-radius: 8px; margin-bottom: 20px; border: 1px solid rgba(131, 58, 180, 0.3);">
                <label style="display: flex; align-items: center; gap: 8px; margin-bottom: 10px;">
                    <span style="font-size: 20px;">🤖</span>
                    <strong>AI Content Generator</strong>
                    <span style="font-size: 0.85em; color: #b0b0b0;">(Uses your style & knowledge base)</span>
                </label>
                <div style="display: grid; grid-template-columns: 1fr auto; gap: 10px; align-items: end;">
                    <div>
                        <input type="text" id="ai-topic" placeholder="Topic or idea (e.g., 'AI automation tools')" style="margin-bottom: 8px;">
                        <select id="ai-tone" style="width: 100%; padding: 10px; background: rgba(0,0,0,0.3); border: 1px solid rgba(255,255,255,0.2); border-radius: 8px; color: #e0e0e0;">
                            <option value="casual">Casual & Friendly</option>
                            <option value="professional">Professional</option>
                            <option value="humorous">Humorous & Fun</option>
                            <option value="inspiring">Inspiring</option>
                            <option value="educational">Educational</option>
                        </select>
                    </div>
                    <button type="button" onclick="generateAIContent()" style="padding: 12px 20px; white-space: nowrap;">
                        ✨ Generate
                    </button>
                </div>
                <div id="ai-loading" style="display: none; color: #fcb045; margin-top: 10px; text-align: center;">
                    <span>🎨 Crafting content in your style...</span>
                </div>
            </div>
            
            <form onsubmit="createThreadsPost(event)">
                <div class="form-group">
                    <label for="threads-text">Post Text (max 500 characters)</label>
                    <textarea id="threads-text" maxlength="500" placeholder="What's on your mind? (or generate AI content above)" required oninput="updateCharCount()"></textarea>
                    <div id="char-count" class="char-count">0 / 500 characters</div>
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
                <p style="color: #b0b0b0; padding: 20px;">Loading posts...</p>
            </div>
        </div>
        
        <div class="section">
            <h2>📈 Account Analytics</h2>
            <div id="threads-analytics">
                <p style="color: #b0b0b0; padding: 20px;">Analytics will appear here after posting.</p>
            </div>
        </div>
        
        <script>
            function toggleSchedule() {
                const scheduleField = document.getElementById('schedule-field');
                scheduleField.style.display = document.getElementById('schedule-post').checked ? 'block' : 'none';
            }
            
            function updateCharCount() {
                const text = document.getElementById('threads-text').value;
                const counter = document.getElementById('char-count');
                counter.textContent = `${text.length} / 500 characters`;
                
                if (text.length > 450) {
                    counter.classList.add('warning');
                } else {
                    counter.classList.remove('warning');
                }
                
                if (text.length >= 500) {
                    counter.classList.add('error');
                } else {
                    counter.classList.remove('error');
                }
            }
            
            async function generateAIContent() {
                const topic = document.getElementById('ai-topic').value.trim();
                if (!topic) {
                    alert('Please enter a topic or idea');
                    return;
                }
                
                const tone = document.getElementById('ai-tone').value;
                const loadingDiv = document.getElementById('ai-loading');
                const alertDiv = document.getElementById('threads-alert');
                
                loadingDiv.style.display = 'block';
                alertDiv.innerHTML = '';
                
                try {
                    const response = await fetch('/threads/generate-content', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            topic: topic,
                            tone: tone,
                            client_id: 'default_client'
                        })
                    });
                    
                    const result = await response.json();
                    loadingDiv.style.display = 'none';
                    
                    if (result.success) {
                        document.getElementById('threads-text').value = result.content;
                        updateCharCount();
                        alertDiv.innerHTML = '<div class=\"alert success\">✅ AI content generated! Edit as needed.</div>';
                        setTimeout(() => { alertDiv.innerHTML = ''; }, 3000);
                    } else {
                        alertDiv.innerHTML = `<div class=\"alert error\">❌ ${result.error}</div>`;
                    }
                } catch (error) {
                    loadingDiv.style.display = 'none';
                    alertDiv.innerHTML = `<div class=\"alert error\">❌ Error: ${error.message}</div>`;
                }
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
                alertDiv.innerHTML = '<div class="alert" style="background: rgba(255,255,255,0.1); color: white;">Creating post...</div>';
                
                try {
                    const response = await fetch('/messaging/threads-create', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify(payload)
                    });
                    
                    const result = await response.json();
                    
                    if (result.success) {
                        alertDiv.innerHTML = '<div class=\"alert success\">✅ Post created successfully!</div>';
                        event.target.reset();
                        updateCharCount();
                        loadThreadsPosts();
                    } else {
                        alertDiv.innerHTML = `<div class=\"alert error\">❌ Failed: ${result.error}</div>`;
                    }
                } catch (error) {
                    alertDiv.innerHTML = `<div class=\"alert error\">❌ Error: ${error.message}</div>`;
                }
                
                setTimeout(() => { alertDiv.innerHTML = ''; }, 5000);
            }
            
            async function loadThreadsPosts() {
                const listDiv = document.getElementById('threads-posts-list');
                listDiv.innerHTML = '<p style=\"color: #b0b0b0; padding: 20px;\">Loading posts...</p>';
                
                try {
                    const response = await fetch('/messaging/threads-posts?client_id=default_client&limit=10');
                    const data = await response.json();
                    
                    if (data.posts && data.posts.length > 0) {
                        listDiv.innerHTML = data.posts.map(post => `
                            <div class=\"post-item\">
                                <p>${post.text}</p>
                                <div class=\"post-stats\">
                                    <span>❤️ ${post.like_count || 0} likes</span>
                                    <span>💬 ${post.reply_count || 0} replies</span>
                                    <span>🔁 ${post.quote_count || 0} quotes</span>
                                </div>
                            </div>
                        `).join('');
                    } else {
                        listDiv.innerHTML = '<p style=\"color: #b0b0b0; padding: 20px;\">No posts yet. Create your first post above!</p>';
                    }
                } catch (error) {
                    console.error('Failed to load posts:', error);
                    listDiv.innerHTML = '<p style=\"color: #f44336; padding: 20px;\">Failed to load posts</p>';
                }
            }
            
            // Initial load
            loadThreadsPosts();
        </script>
    </body>
    </html>
    """


@router.post("/create")
async def create_threads_post(request: ThreadsPostRequest):
    """Create a Threads post (proxies to messaging routes)."""
    from api.messaging_routes import create_threads_post as create_post
    return await create_post(request)
