"""
Late API Webhook Handler
Receives notifications when clients connect their social media accounts
"""

from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import JSONResponse
import os
import json
import hmac
import hashlib
from datetime import datetime

router = APIRouter(prefix="/webhooks", tags=["Webhooks"])

# Late API webhook secret (for signature verification)
LATE_WEBHOOK_SECRET = os.getenv("LATE_WEBHOOK_SECRET", "")

# Import connection manager
import sys
sys.path.append(os.path.dirname(os.path.dirname(__file__)))


def verify_late_signature(payload: bytes, signature: str) -> bool:
    """
    Verify webhook signature from Late API
    """
    if not LATE_WEBHOOK_SECRET:
        return True
    
    expected_signature = hmac.new(
        LATE_WEBHOOK_SECRET.encode(),
        payload,
        hashlib.sha256
    ).hexdigest()
    
    return hmac.compare_digest(signature, expected_signature)


def add_connection_to_file(client_id: str, platform: str, profile_id: str, username: str):
    """Add connection to storage file"""
    from api.client_connections_routes import add_connection
    add_connection(client_id, platform, profile_id, username)


@router.post("/late-api/profile-connected")
async def late_profile_connected(request: Request):
    """
    Handle Late API webhook when a profile is connected
    
    Expected payload:
    {
        "event": "profile.connected",
        "profile_id": "697b123abc...",
        "platform": "twitter",
        "username": "johndoe",
        "user_id": "platform_user_id",
        "workspace_id": "ws_abc123",
        "timestamp": "2026-02-07T12:00:00Z"
    }
    """
    
    # Get raw body for signature verification
    body = await request.body()
    
    # Verify signature if provided
    signature = request.headers.get("X-Late-Signature", "")
    if signature and not verify_late_signature(body, signature):
        raise HTTPException(status_code=401, detail="Invalid webhook signature")
    
    # Parse JSON
    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")
    
    # Extract connection details
    event = data.get("event")
    profile_id = data.get("profile_id")
    platform = data.get("platform", "").lower()
    username = data.get("username", "")
    workspace_id = data.get("workspace_id")
    
    if event == "profile.connected":
        # Try to extract client_id from referrer or metadata
        # In production, you'd have this in the URL or webhook metadata
        client_id = data.get("metadata", {}).get("client_id", "pending_assignment")
        
        # Save connection
        add_connection_to_file(client_id, platform, profile_id, username)
        
        # Also save to .env format file for easy copying
        env_line = f"LATE_PROFILE_{platform.upper()}_{client_id}={profile_id}  # @{username} - {datetime.now().strftime('%Y-%m-%d %H:%M')}\n"
        
        env_file = "storage/new_connections_env.txt"
        os.makedirs(os.path.dirname(env_file), exist_ok=True)
        
        with open(env_file, "a", encoding="utf-8") as f:
            f.write(env_line)
        
        return JSONResponse({
            "status": "success",
            "message": "Profile connection received",
            "data": {
                "client_id": client_id,
                "platform": platform,
                "username": username,
                "profile_id": profile_id
            }
        })
    
    elif event == "profile.disconnected":
        # Handle disconnection (update status in database)
        return JSONResponse({
            "status": "success",
            "message": "Profile disconnection received"
        })
    
    else:
        return JSONResponse({
            "status": "success",
            "message": f"Event received: {event}"
        })


@router.post("/late-api/post-published")
async def late_post_published(request: Request):
    """
    Handle Late API webhook when a post is published
    
    Expected payload:
    {
        "event": "post.published",
        "post_id": "post_abc123",
        "profile_id": "697b123...",
        "platform": "twitter",
        "status": "published",
        "url": "https://twitter.com/user/status/123",
        "timestamp": "2026-02-07T12:00:00Z"
    }
    """
    
    body = await request.body()
    data = json.loads(body)
    
    # In production, update your database with post status
    
    return JSONResponse({
        "status": "success",
        "message": "Post status received"
    })


@router.post("/late-api/post-failed")
async def late_post_failed(request: Request):
    """
    Handle Late API webhook when a post fails
    """
    
    body = await request.body()
    data = json.loads(body)
    
    # In production, log error and notify user
    
    return JSONResponse({
        "status": "success",
        "message": "Post failure received"
    })


@router.get("/test")
async def test_webhook():
    """
    Test endpoint to verify webhooks are working
    """
    return JSONResponse({
        "status": "ok",
        "message": "Webhook endpoint is active",
        "endpoints": {
            "profile_connected": "/webhooks/late-api/profile-connected",
            "post_published": "/webhooks/late-api/post-published",
            "post_failed": "/webhooks/late-api/post-failed"
        }
    })
