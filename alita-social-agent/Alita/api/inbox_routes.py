"""
Inbox Routes - Unified Inbox for DMs, Comments & Reviews via Late API

Provides a unified inbox across all connected social platforms:
    GET  /inbox/dashboard                   -> Unified inbox UI
    GET  /inbox/api/conversations           -> List DM conversations
    GET  /inbox/api/conversations/:id       -> Get conversation messages
    POST /inbox/api/conversations/:id/send  -> Send a message
    PUT  /inbox/api/conversations/:id       -> Archive/activate conversation
    GET  /inbox/api/comments                -> List posts with comments
    GET  /inbox/api/comments/:postId        -> Get comments for a post
    POST /inbox/api/comments/:postId/reply  -> Reply to a post/comment
    DELETE /inbox/api/comments/:postId      -> Delete a comment
    POST /inbox/api/comments/:postId/:commentId/hide   -> Hide a comment
    DELETE /inbox/api/comments/:postId/:commentId/hide -> Unhide a comment
    GET  /inbox/api/reviews                 -> List reviews
    POST /inbox/api/reviews/:reviewId/reply -> Reply to a review
"""

import os
import httpx
from typing import Optional, Dict, Any
from fastapi import APIRouter, Request, Cookie, Query
from fastapi.responses import HTMLResponse, JSONResponse
from dotenv import load_dotenv

from utils.meta_inbox_store import (
    list_conversations as meta_list_conversations,
    get_messages as meta_get_messages,
    mark_read as meta_mark_read,
    get_status as meta_get_status,
    record_message as meta_record_message,
)
from utils.meta_graph import send_instagram_dm as meta_send_instagram_dm

load_dotenv()

router = APIRouter(prefix="/inbox", tags=["Inbox"])

LATE_BASE = "https://getlate.dev/api/v1"


def _is_meta_platform(platform: Optional[str]) -> bool:
    return (platform or "").strip().lower() in {"instagram", "facebook"}


def _block_meta_platform(kind: str) -> JSONResponse:
    return JSONResponse(
        {
            "success": False,
            "error": f"Instagram/Facebook {kind} are handled via Meta (OAuth + Webhooks) in this app, not via Late.",
        },
        status_code=400,
    )


def _filter_out_meta_items(payload: Any) -> Any:
    """Best-effort filter so IG/FB never appear in Late-powered inbox lists."""
    try:
        if not isinstance(payload, dict):
            return payload
        items = payload.get("data")
        if not isinstance(items, list):
            return payload
        payload["data"] = [
            item
            for item in items
            if not _is_meta_platform((item or {}).get("platform") if isinstance(item, dict) else None)
        ]
        return payload
    except Exception:
        return payload


def _late_headers() -> Dict[str, str]:
    return {
        "Authorization": f"Bearer {os.getenv('LATE_API_KEY', '')}",
        "Content-Type": "application/json",
    }


# ═══════════════════════════════════════════════════════════════════════════
# Meta-backed Inbox Endpoints (Instagram/Facebook via webhooks/store)
# ═══════════════════════════════════════════════════════════════════════════


@router.get("/api/meta/status")
async def meta_inbox_status():
    return JSONResponse({"success": True, "status": meta_get_status()})


@router.get("/api/meta/conversations")
async def meta_list(
    platform: Optional[str] = None,
    limit: int = Query(30, ge=1, le=100),
):
    data = meta_list_conversations(platform=platform, limit=limit)
    return JSONResponse({"data": data})


@router.get("/api/meta/conversations/{conversation_id}/messages")
async def meta_messages(conversation_id: str):
    meta_mark_read(conversation_id)
    msgs = meta_get_messages(conversation_id)
    return JSONResponse({"messages": msgs})


@router.post("/api/meta/conversations/{conversation_id}/send")
async def meta_send(conversation_id: str, request: Request):
    body = await request.json()
    platform = (body.get("platform") or "instagram").strip().lower()
    account_id = str(body.get("accountId") or "").strip()
    text = str(body.get("message") or "").strip()

    if platform not in {"instagram", "facebook"}:
        return JSONResponse({"success": False, "error": "Meta send only supports Instagram/Facebook."}, status_code=400)
    if not text:
        return JSONResponse({"success": False, "error": "Missing message"}, status_code=400)

    # conversation_id is `platform:participant_id`
    participant_id = conversation_id.split(":", 1)[1] if ":" in conversation_id else conversation_id

    if platform == "facebook":
        return JSONResponse(
            {"success": False, "error": "Facebook DM sending is not wired yet in this build."},
            status_code=400,
        )

    result = await meta_send_instagram_dm(
        ig_business_account_id=account_id,
        recipient_id=participant_id,
        text=text,
    )
    if "error" in result:
        return JSONResponse({"success": False, "error": result.get("error")}, status_code=400)

    # Mirror into store for UI
    meta_record_message(
        platform=platform,
        business_account_id=account_id,
        participant_id=participant_id,
        direction="outgoing",
        text=text,
        message_id=(result.get("message_id") if isinstance(result, dict) else None),
    )
    return JSONResponse({"success": True, "result": result})


# ═══════════════════════════════════════════════════════════════════════════
# API Proxy Endpoints (Late API passthrough)
# ═══════════════════════════════════════════════════════════════════════════

# ─── Conversations (DMs) ────────────────────────────────────────────────

@router.get("/api/conversations")
async def list_conversations(
    platform: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = Query(20, ge=1, le=50),
    cursor: Optional[str] = None,
    accountId: Optional[str] = None,
):
    if _is_meta_platform(platform):
        return _block_meta_platform("DMs")
    params = {"limit": limit}
    if platform:
        params["platform"] = platform
    if status:
        params["status"] = status
    if cursor:
        params["cursor"] = cursor
    if accountId:
        params["accountId"] = accountId

    async with httpx.AsyncClient(timeout=20.0) as client:
        r = await client.get(f"{LATE_BASE}/inbox/conversations", headers=_late_headers(), params=params)
        return JSONResponse(_filter_out_meta_items(r.json()), status_code=r.status_code)


@router.get("/api/conversations/{conversation_id}")
async def get_conversation(conversation_id: str, accountId: str, platform: Optional[str] = None):
    if _is_meta_platform(platform):
        return _block_meta_platform("DMs")
    async with httpx.AsyncClient(timeout=20.0) as client:
        r = await client.get(
            f"{LATE_BASE}/inbox/conversations/{conversation_id}",
            headers=_late_headers(),
            params={"accountId": accountId}
        )
        return JSONResponse(r.json(), status_code=r.status_code)


@router.get("/api/conversations/{conversation_id}/messages")
async def get_messages(conversation_id: str, accountId: str, platform: Optional[str] = None):
    if _is_meta_platform(platform):
        return _block_meta_platform("DMs")
    async with httpx.AsyncClient(timeout=20.0) as client:
        r = await client.get(
            f"{LATE_BASE}/inbox/conversations/{conversation_id}/messages",
            headers=_late_headers(),
            params={"accountId": accountId}
        )
        data = r.json()
        # Normalize response structure for consistent frontend handling
        if isinstance(data, dict) and "data" in data:
            return JSONResponse({"messages": data.get("data", [])}, status_code=r.status_code)
        return JSONResponse({"messages": data if isinstance(data, list) else []}, status_code=r.status_code)


@router.post("/api/conversations/{conversation_id}/send")
async def send_message(conversation_id: str, request: Request):
    body = await request.json()
    if _is_meta_platform(body.get("platform")):
        return _block_meta_platform("DMs")
    async with httpx.AsyncClient(timeout=20.0) as client:
        r = await client.post(
            f"{LATE_BASE}/inbox/conversations/{conversation_id}/messages",
            headers=_late_headers(),
            json=body
        )
        return JSONResponse(r.json(), status_code=r.status_code)


@router.put("/api/conversations/{conversation_id}")
async def update_conversation(conversation_id: str, request: Request):
    body = await request.json()
    if _is_meta_platform(body.get("platform")):
        return _block_meta_platform("DMs")
    async with httpx.AsyncClient(timeout=20.0) as client:
        r = await client.put(
            f"{LATE_BASE}/inbox/conversations/{conversation_id}",
            headers=_late_headers(),
            json=body
        )
        return JSONResponse(r.json(), status_code=r.status_code)


# ─── Comments ────────────────────────────────────────────────────────────

@router.get("/api/comments")
async def list_comments(
    platform: Optional[str] = None,
    limit: int = Query(20, ge=1, le=50),
    cursor: Optional[str] = None,
    accountId: Optional[str] = None,
    minComments: Optional[int] = None,
    sortBy: Optional[str] = None,
    sortOrder: Optional[str] = None,
):
    if _is_meta_platform(platform):
        return _block_meta_platform("comments")
    params = {"limit": limit}
    if platform:
        params["platform"] = platform
    if cursor:
        params["cursor"] = cursor
    if accountId:
        params["accountId"] = accountId
    if minComments is not None:
        params["minComments"] = minComments
    if sortBy:
        params["sortBy"] = sortBy
    if sortOrder:
        params["sortOrder"] = sortOrder

    async with httpx.AsyncClient(timeout=20.0) as client:
        r = await client.get(f"{LATE_BASE}/inbox/comments", headers=_late_headers(), params=params)
        return JSONResponse(_filter_out_meta_items(r.json()), status_code=r.status_code)


@router.get("/api/comments/{post_id}")
async def get_post_comments(
    post_id: str,
    accountId: str,
    limit: int = Query(50, ge=1, le=100),
    platform: Optional[str] = None,
):
    if _is_meta_platform(platform):
        return _block_meta_platform("comments")
    async with httpx.AsyncClient(timeout=20.0) as client:
        r = await client.get(
            f"{LATE_BASE}/inbox/comments/{post_id}",
            headers=_late_headers(),
            params={"accountId": accountId, "limit": limit}
        )
        return JSONResponse(r.json(), status_code=r.status_code)


@router.post("/api/comments/{post_id}/reply")
async def reply_to_comment(post_id: str, request: Request):
    body = await request.json()
    if _is_meta_platform(body.get("platform")):
        return _block_meta_platform("comments")
    async with httpx.AsyncClient(timeout=20.0) as client:
        r = await client.post(
            f"{LATE_BASE}/inbox/comments/{post_id}",
            headers=_late_headers(),
            json=body
        )
        return JSONResponse(r.json(), status_code=r.status_code)


@router.delete("/api/comments/{post_id}")
async def delete_comment(post_id: str, accountId: str, commentId: str, platform: Optional[str] = None):
    if _is_meta_platform(platform):
        return _block_meta_platform("comments")
    async with httpx.AsyncClient(timeout=20.0) as client:
        r = await client.delete(
            f"{LATE_BASE}/inbox/comments/{post_id}",
            headers=_late_headers(),
            params={"accountId": accountId, "commentId": commentId}
        )
        return JSONResponse(r.json(), status_code=r.status_code)


@router.post("/api/comments/{post_id}/{comment_id}/hide")
async def hide_comment(post_id: str, comment_id: str, request: Request):
    body = await request.json()
    if _is_meta_platform(body.get("platform")):
        return _block_meta_platform("comments")
    async with httpx.AsyncClient(timeout=20.0) as client:
        r = await client.post(
            f"{LATE_BASE}/inbox/comments/{post_id}/{comment_id}/hide",
            headers=_late_headers(),
            json=body
        )
        return JSONResponse(r.json(), status_code=r.status_code)


@router.delete("/api/comments/{post_id}/{comment_id}/hide")
async def unhide_comment(post_id: str, comment_id: str, accountId: str, platform: Optional[str] = None):
    if _is_meta_platform(platform):
        return _block_meta_platform("comments")
    async with httpx.AsyncClient(timeout=20.0) as client:
        r = await client.delete(
            f"{LATE_BASE}/inbox/comments/{post_id}/{comment_id}/hide",
            headers=_late_headers(),
            params={"accountId": accountId}
        )
        return JSONResponse(r.json(), status_code=r.status_code)


@router.post("/api/comments/{post_id}/{comment_id}/like")
async def like_comment(post_id: str, comment_id: str, request: Request):
    body = await request.json()
    if _is_meta_platform(body.get("platform")):
        return _block_meta_platform("comments")
    async with httpx.AsyncClient(timeout=20.0) as client:
        r = await client.post(
            f"{LATE_BASE}/inbox/comments/{post_id}/{comment_id}/like",
            headers=_late_headers(),
            json=body
        )
        return JSONResponse(r.json(), status_code=r.status_code)


@router.delete("/api/comments/{post_id}/{comment_id}/like")
async def unlike_comment(
    post_id: str,
    comment_id: str,
    accountId: str,
    likeUri: Optional[str] = None,
    platform: Optional[str] = None,
):
    if _is_meta_platform(platform):
        return _block_meta_platform("comments")
    params = {"accountId": accountId}
    if likeUri:
        params["likeUri"] = likeUri
    async with httpx.AsyncClient(timeout=20.0) as client:
        r = await client.delete(
            f"{LATE_BASE}/inbox/comments/{post_id}/{comment_id}/like",
            headers=_late_headers(),
            params=params
        )
        return JSONResponse(r.json(), status_code=r.status_code)


# ─── Reviews ────────────────────────────────────────────────────────────

@router.get("/api/reviews")
async def list_reviews(
    platform: Optional[str] = None,
    limit: int = Query(20, ge=1, le=50),
    cursor: Optional[str] = None,
    accountId: Optional[str] = None,
    minRating: Optional[int] = None,
    maxRating: Optional[int] = None,
    hasReply: Optional[bool] = None,
):
    if _is_meta_platform(platform):
        return _block_meta_platform("reviews")
    params = {"limit": limit}
    if platform:
        params["platform"] = platform
    if cursor:
        params["cursor"] = cursor
    if accountId:
        params["accountId"] = accountId
    if minRating is not None:
        params["minRating"] = minRating
    if maxRating is not None:
        params["maxRating"] = maxRating
    if hasReply is not None:
        params["hasReply"] = str(hasReply).lower()

    async with httpx.AsyncClient(timeout=20.0) as client:
        r = await client.get(f"{LATE_BASE}/inbox/reviews", headers=_late_headers(), params=params)
        return JSONResponse(_filter_out_meta_items(r.json()), status_code=r.status_code)


@router.post("/api/reviews/{review_id}/reply")
async def reply_to_review(review_id: str, request: Request):
    body = await request.json()
    if _is_meta_platform(body.get("platform")):
        return _block_meta_platform("reviews")
    async with httpx.AsyncClient(timeout=20.0) as client:
        r = await client.post(
            f"{LATE_BASE}/inbox/reviews/{review_id}/reply",
            headers=_late_headers(),
            json=body
        )
        return JSONResponse(r.json(), status_code=r.status_code)


from utils.auto_reply_settings import get_all as _get_auto_reply_all
from utils.auto_reply_settings import set_enabled as _set_auto_reply_enabled


# ═══════════════════════════════════════════════════════════════════════════
# Auto-Reply Settings (persisted)
# ═══════════════════════════════════════════════════════════════════════════

@router.get("/api/auto-reply")
async def get_auto_reply_settings():
    """Get auto-reply status for all platforms"""
    return JSONResponse(_get_auto_reply_all("dm"))


@router.post("/api/auto-reply/{platform}")
async def toggle_auto_reply(platform: str, request: Request):
    """Enable/disable auto-reply for a platform"""
    body = await request.json()
    enabled = body.get("enabled", False)
    _set_auto_reply_enabled("dm", platform, enabled)
    return JSONResponse({"success": True, "platform": platform, "enabled": enabled})


@router.get("/api/comment-auto-reply")
async def get_comment_auto_reply_settings():
    """Get comment auto-reply status for all platforms"""
    return JSONResponse(_get_auto_reply_all("comment"))


@router.post("/api/comment-auto-reply/{platform}")
async def toggle_comment_auto_reply(platform: str, request: Request):
    """Enable/disable comment auto-reply for a platform"""
    body = await request.json()
    enabled = body.get("enabled", False)
    _set_auto_reply_enabled("comment", platform, enabled)
    return JSONResponse({"success": True, "platform": platform, "enabled": enabled})


# ═══════════════════════════════════════════════════════════════════════════
# Dashboard UI
# ═══════════════════════════════════════════════════════════════════════════

INBOX_CSS = """
/* Inbox-specific styles (light theme, inherits shell from shared_layout) */

/* Tabs */
.inbox-tabs { display: flex; gap: 4px; margin-bottom: 24px; border-bottom: 2px solid #e4e6eb; }
.inbox-tab {
    padding: 12px 20px; background: transparent; border: none;
    color: #606770; cursor: pointer; font-size: 14px; font-weight: 600;
    border-bottom: 3px solid transparent; transition: all 0.2s;
}
.inbox-tab.active { color: #5c6ac4; border-bottom-color: #5c6ac4; }
.inbox-tab:hover { color: #1c1e21; }
.inbox-tab .badge {
    background: #5c6ac4; color: #fff; border-radius: 10px;
    padding: 1px 7px; font-size: 11px; margin-left: 6px;
}

/* Panels */
.tab-panel { display: none; }
.tab-panel.active { display: block; }

/* Platform filter bar */
.filter-bar { display: flex; gap: 8px; margin-bottom: 16px; flex-wrap: wrap; }
.filter-btn {
    padding: 6px 14px; border-radius: 20px; border: 1px solid #dde0e4;
    background: #fff; color: #606770; cursor: pointer; font-size: 13px;
    transition: all 0.15s;
}
.filter-btn.active { background: #5c6ac4; color: #fff; border-color: #5c6ac4; }
.filter-btn:hover { border-color: #5c6ac4; color: #5c6ac4; }

/* Conversation list */
.conv-list { display: flex; flex-direction: column; gap: 2px; }
.conv-item {
    display: flex; align-items: center; gap: 14px; padding: 14px 16px;
    background: #fff; border: 1px solid #e4e6eb; border-radius: 10px;
    cursor: pointer; transition: all 0.15s;
}
.conv-item:hover { border-color: #5c6ac4; background: #f8f9fb; }
.conv-item .avatar {
    width: 44px; height: 44px; border-radius: 50%; background: #ede8f5;
    display: flex; align-items: center; justify-content: center; font-size: 18px;
    flex-shrink: 0; overflow: hidden; color: #5c6ac4;
}
.conv-item .avatar img { width: 100%; height: 100%; object-fit: cover; }
.conv-item .conv-info { flex: 1; min-width: 0; }
.conv-item .conv-name { font-weight: 600; font-size: 14px; color: #1c1e21; }
.conv-item .conv-preview { color: #606770; font-size: 13px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.conv-item .conv-meta { text-align: right; flex-shrink: 0; }
.conv-item .conv-time { color: #90949c; font-size: 12px; }
.conv-item .conv-platform {
    font-size: 11px; padding: 2px 8px; border-radius: 10px;
    background: #f0f2f5; color: #606770; margin-top: 4px; display: inline-block;
}
.conv-item .unread-dot { width: 8px; height: 8px; border-radius: 50%; background: #5c6ac4; }

/* Message thread */
.msg-panel {
    background: #fff; border: 1px solid #e4e6eb; border-radius: 12px;
    max-height: 500px; overflow-y: auto; padding: 16px; display: none;
    margin-bottom: 16px; box-shadow: 0 1px 4px rgba(0,0,0,.06);
}
.msg-panel.open { display: block; }
.msg-header {
    display: flex; justify-content: space-between; align-items: center;
    padding-bottom: 12px; border-bottom: 1px solid #e4e6eb; margin-bottom: 12px;
}
.msg-header .back-btn { background: none; border: none; color: #5c6ac4; cursor: pointer; font-size: 14px; font-weight: 600; }
.msg-bubble {
    max-width: 75%; padding: 10px 14px; border-radius: 16px;
    margin-bottom: 8px; font-size: 14px; line-height: 1.4;
}
.msg-bubble.incoming { background: #f0f2f5; color: #1c1e21; align-self: flex-start; border-bottom-left-radius: 4px; }
.msg-bubble.outgoing { background: linear-gradient(135deg,#5c6ac4,#764ba2); color: #fff; margin-left: auto; border-bottom-right-radius: 4px; }
.msg-list { display: flex; flex-direction: column; }
.msg-time { font-size: 11px; color: #90949c; margin-bottom: 12px; }
.msg-input-row { display: flex; flex-direction: column; gap: 8px; margin-top: 12px; padding-top: 12px; border-top: 1px solid #e4e6eb; }
.msg-input-row textarea {
    width: 100%; padding: 10px 14px; border-radius: 12px; border: 1px solid #dde0e4;
    background: #f8f9fb; color: #1c1e21; font-size: 14px; outline: none;
    resize: vertical; min-height: 60px; font-family: inherit; line-height: 1.4; box-sizing: border-box;
}
.msg-input-row textarea:focus { border-color: #5c6ac4; box-shadow: 0 0 0 3px rgba(92,106,196,.12); }
.msg-input-actions { display: flex; gap: 8px; justify-content: flex-end; }
.msg-input-actions button {
    padding: 9px 20px; border-radius: 20px; border: none;
    background: linear-gradient(135deg,#5c6ac4,#764ba2); color: #fff; cursor: pointer; font-weight: 600;
}

/* Comment cards */
.comment-post {
    background: #fff; border: 1px solid #e4e6eb; border-radius: 12px;
    padding: 18px; margin-bottom: 12px; box-shadow: 0 1px 4px rgba(0,0,0,.06);
}
.comment-post-header {
    display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px;
}
.comment-post-platform {
    font-size: 12px; padding: 3px 10px; border-radius: 10px;
    background: #f0f2f5; color: #606770;
}
.comment-post-content { font-size: 14px; color: #1c1e21; margin-bottom: 10px; line-height: 1.4; }
.comment-post-stats { display: flex; gap: 16px; font-size: 13px; color: #606770; margin-bottom: 10px; }
.comments-container { margin-top: 10px; }
.comment-item {
    display: flex; gap: 10px; padding: 10px 14px;
    border-left: 2px solid #e4e6eb; margin-left: 12px; margin-bottom: 6px;
}
.comment-item .c-avatar {
    width: 32px; height: 32px; border-radius: 50%; background: #ede8f5;
    flex-shrink: 0; overflow: hidden; display: flex; align-items: center; justify-content: center;
    font-size: 12px; color: #5c6ac4;
}
.comment-item .c-avatar img { width: 100%; height: 100%; object-fit: cover; }
.comment-item .c-body { flex: 1; }
.comment-item .c-author { font-size: 13px; font-weight: 600; color: #1c1e21; }
.comment-item .c-text { font-size: 13px; color: #444; margin-top: 2px; }
.comment-item .c-meta { font-size: 11px; color: #90949c; margin-top: 4px; }
.comment-actions { display: flex; gap: 10px; margin-top: 6px; }
.comment-actions button {
    background: none; border: 1px solid #dde0e4; color: #606770;
    padding: 3px 10px; border-radius: 14px; cursor: pointer; font-size: 12px;
}
.comment-actions button:hover { border-color: #5c6ac4; color: #5c6ac4; }

/* Reply form */
.reply-form { display: flex; flex-direction: column; gap: 8px; margin-top: 10px; margin-left: 12px; }
.reply-form textarea {
    width: 100%; padding: 8px 12px; border-radius: 12px; border: 1px solid #dde0e4;
    background: #f8f9fb; color: #1c1e21; font-size: 13px; outline: none;
    resize: vertical; min-height: 52px; font-family: inherit; line-height: 1.4; box-sizing: border-box;
}
.reply-form textarea:focus { border-color: #5c6ac4; }
.reply-form-actions { display: flex; gap: 8px; justify-content: flex-end; align-items: center; }
.reply-form-actions button {
    padding: 7px 16px; border-radius: 14px; border: none;
    background: linear-gradient(135deg,#5c6ac4,#764ba2); color: #fff; cursor: pointer; font-size: 13px;
}
/* AI button */
.ai-btn {
    padding: 7px 14px; border-radius: 14px; border: 1.5px solid #5c6ac4;
    background: transparent; color: #5c6ac4; cursor: pointer; font-size: 13px;
    font-weight: 600; transition: all 0.15s; white-space: nowrap;
}
.ai-btn:hover { background: #ede8f5; }
.ai-btn:disabled { opacity: 0.55; cursor: wait; }

/* Review cards */
.review-card {
    background: #fff; border: 1px solid #e4e6eb; border-radius: 12px;
    padding: 18px; margin-bottom: 12px; box-shadow: 0 1px 4px rgba(0,0,0,.06);
}
.review-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
.review-stars { color: #f5c518; font-size: 16px; }
.review-author { font-weight: 600; font-size: 14px; color: #1c1e21; }
.review-text { font-size: 14px; color: #444; line-height: 1.4; margin-bottom: 8px; }
.review-reply { background: #f8f9fb; border-radius: 8px; padding: 10px; margin-top: 8px; border: 1px solid #e4e6eb; }
.review-reply-label { font-size: 12px; color: #90949c; margin-bottom: 4px; }
.review-reply-text { font-size: 13px; color: #1c1e21; }

/* Settings */
.settings-panel { display: none; padding: 20px; background: #fff; border: 1px solid #e4e6eb; border-radius: 12px; margin-top: 16px; box-shadow: 0 1px 4px rgba(0,0,0,.06); }
.settings-panel.open { display: block; }
.settings-title { font-size: 16px; font-weight: 700; margin-bottom: 16px; color: #1c1e21; }
.setting-row {
    display: flex; justify-content: space-between; align-items: center;
    padding: 12px; background: #f8f9fb; border-radius: 8px; margin-bottom: 8px;
    border: 1px solid #e4e6eb;
}
.setting-row label { font-size: 14px; color: #1c1e21; }
.toggle {
    position: relative; display: inline-block; width: 40px; height: 24px;
    background: #dde0e4; border-radius: 12px; cursor: pointer; transition: all 0.3s;
}
.toggle input { display: none; }
.toggle span {
    position: absolute; top: 2px; left: 2px; width: 20px; height: 20px;
    background: #fff; border-radius: 50%; transition: all 0.3s;
}
.toggle input:checked + span { left: 18px; }
.toggle input:checked ~ * { background: #5c6ac4; }
#settings-list { display: flex; flex-direction: column; gap: 8px; }

/* Comment Auto-Reply Bar */
.comment-auto-reply-bar { padding: 12px 16px; background: #f8f9fb; border: 1px solid #e4e6eb; border-radius: 8px; }
.inline-toggle {
    position: relative; display: inline-flex; align-items: center;
    gap: 6px; margin-right: 14px; cursor: pointer;
}
.inline-toggle input { display: none; }
.inline-toggle span {
    width: 28px; height: 16px; background: #dde0e4; border-radius: 8px;
    position: relative; transition: all 0.3s;
    display: inline-block;
}
.inline-toggle span::after {
    content: ''; position: absolute; width: 14px; height: 14px;
    background: #fff; border-radius: 50%; top: 1px; left: 1px;
    transition: all 0.3s;
}
.inline-toggle input:checked + span {
    background: #5c6ac4;
}
.inline-toggle input:checked + span::after {
    left: 13px;
}

.loading { text-align: center; padding: 40px; color: #90949c; }
.error-box {
    background: #fce4ec; border: 1px solid #f8bbd0;
    color: #c62828; padding: 14px 18px; border-radius: 8px; font-size: 14px;
}

/* Toast */
.toast {
    position: fixed; bottom: 24px; right: 24px; padding: 12px 20px;
    border-radius: 8px; font-size: 14px; z-index: 9999;
    animation: fadeIn 0.3s ease;
}
.toast.success { background: #2e7d32; color: #fff; }
.toast.error { background: #c62828; color: #fff; }
@keyframes fadeIn { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: translateY(0); } }
"""

INBOX_JS = """
console.log('INBOX_JS_BUILD', '2026-02-15-1');
var activeTab = 'conversations';
var platformFilter = '';
var openConvId = null;
var openConvAccountId = null;
var openConvPlatform = null;
var openConvName = null;

// ─── Tab switching ──────────────────────────────────────
function switchTab(tab) {
    activeTab = tab;
    document.querySelectorAll('.inbox-tab').forEach(function(t){ t.classList.remove('active'); });
    event.target.classList.add('active');
    document.querySelectorAll('.tab-panel').forEach(function(p){ p.classList.remove('active'); });
    document.getElementById('panel-' + tab).classList.add('active');
}

function filterPlatform(btn, plat) {
    platformFilter = (platformFilter === plat) ? '' : plat;
    document.querySelectorAll('.filter-btn').forEach(function(b){ b.classList.remove('active'); });
    if (platformFilter) btn.classList.add('active');
    if (activeTab === 'conversations') loadConversations();
    else if (activeTab === 'comments') loadComments();
    else loadReviews();
}

function toast(msg, type) {
    var el = document.createElement('div');
    el.className = 'toast ' + (type || 'success');
    el.textContent = msg;
    document.body.appendChild(el);
    setTimeout(function(){ el.remove(); }, 3000);
}

function timeAgo(dt) {
    if (!dt) return '';
    var diff = (Date.now() - new Date(dt).getTime()) / 1000;
    if (diff < 60) return 'just now';
    if (diff < 3600) return Math.floor(diff/60) + 'm';
    if (diff < 86400) return Math.floor(diff/3600) + 'h';
    return Math.floor(diff/86400) + 'd';
}

function platformIcon(p) {
    var icons = {
        twitter: '𝕏', instagram: '📷', facebook: 'f', linkedin: 'in',
        tiktok: '♪', youtube: '▶', threads: '🧵', reddit: '🤖', telegram: '✈'
    };
    return icons[p] || p;
}

function trunc(s, n) { return s && s.length > n ? s.substring(0, n) + '...' : (s || ''); }

function isDebugInbox() {
    try {
        return new URLSearchParams(window.location.search).get('debug') === '1';
    } catch (e) {
        return false;
    }
}

// ─── AI Reply Generator ────────────────────────────────
async function generateAIReply(textareaId) {
    var btn = event && event.currentTarget;
    var contextText = '';
    if (btn) {
        var commentEl = btn.closest ? btn.closest('.comment-item') : null;
        if (commentEl) {
            var ctEl = commentEl.querySelector('.c-text');
            if (ctEl) contextText = ctEl.textContent.trim();
        }
        if (!contextText) {
            var reviewEl = btn.closest ? btn.closest('.review-card') : null;
            if (reviewEl) {
                var rvEl = reviewEl.querySelector('.review-text');
                if (rvEl) contextText = rvEl.textContent.trim();
            }
        }
    }
    if (!contextText && openConvId) {
        var bubbles = document.querySelectorAll('#msg-list .msg-bubble.incoming');
        if (bubbles && bubbles.length > 0) contextText = bubbles[bubbles.length - 1].textContent.trim();
    }
    if (btn) { btn.disabled = true; btn.textContent = '\u23f3 Generating\u2026'; }
    try {
        var r = await fetch('/inbox/api/ai-reply', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ text: contextText })
        });
        var d = await r.json();
        if (d.reply) {
            var ta = document.getElementById(textareaId);
            if (ta) { ta.value = d.reply; ta.focus(); }
            toast('AI reply ready \u2014 edit if needed \u270f\ufe0f');
        } else {
            toast('Could not generate reply', 'error');
        }
    } catch(e) { toast('AI reply failed', 'error'); }
    if (btn) { btn.disabled = false; btn.textContent = '\u2728 AI Reply'; }
}

// ─── Conversations ──────────────────────────────────────
async function loadConversations() {
    var debug = isDebugInbox();
    console.log('🔍 loadConversations() called with platformFilter:', platformFilter);
    var el = document.getElementById('conv-list');
    el.innerHTML = '<div class="loading">Loading conversations...</div>';
    try {
        var convs = [];
        var metaInfo = { url: null, status: null, count: 0, error: null };
        var lateInfo = { url: null, status: null, count: 0, error: null };
        // Meta platforms: load from local webhook-backed store
        if (!platformFilter || platformFilter === 'instagram' || platformFilter === 'facebook') {
            var metaUrl = '/inbox/api/meta/conversations?limit=50';
            if (platformFilter) metaUrl += '&platform=' + platformFilter;
            metaInfo.url = metaUrl;
            console.log('📱 Fetching Meta conversations from:', metaUrl);
            try {
                var mr = await fetch(metaUrl);
                console.log('📱 Meta response status:', mr.status);
                metaInfo.status = mr.status;
                var metaText = await mr.text();
                var md = null;
                try { md = JSON.parse(metaText); } catch(parseErr) { metaInfo.error = 'Meta returned non-JSON: ' + metaText.slice(0, 200); }
                console.log('📱 Meta data:', md);
                if (md && md.data && Array.isArray(md.data)) {
                    metaInfo.count = md.data.length;
                    convs = convs.concat(md.data);
                    console.log('📱 Added', md.data.length, 'Meta conversations');
                } else if (!metaInfo.error && md && md.error) {
                    metaInfo.error = (md.error.message || JSON.stringify(md.error));
                }
            } catch(metaErr) { 
                metaInfo.error = metaErr && metaErr.message ? metaErr.message : String(metaErr);
                console.error('📱 Meta inbox fetch failed', metaErr); 
            }
        }

        // Late platforms: load from Late proxy
        if (!platformFilter || (platformFilter !== 'instagram' && platformFilter !== 'facebook')) {
            var url = '/inbox/api/conversations?limit=30';
            if (platformFilter) url += '&platform=' + platformFilter;
            lateInfo.url = url;
            console.log('⏰ Fetching Late conversations from:', url);
            try {
                var r = await fetch(url);
                console.log('⏰ Late response status:', r.status);
                lateInfo.status = r.status;
                var lateText = await r.text();
                var d = null;
                try { d = JSON.parse(lateText); } catch(parseErr) { lateInfo.error = 'Late returned non-JSON: ' + lateText.slice(0, 200); }
                console.log('⏰ Late data:', d);
                if (d && d.data && Array.isArray(d.data)) {
                    lateInfo.count = d.data.length;
                    convs = convs.concat(d.data);
                    console.log('⏰ Added', d.data.length, 'Late conversations');
                } else if (!lateInfo.error && d && d.error) {
                    lateInfo.error = (d.error.message || JSON.stringify(d.error));
                }
            } catch(lateErr) { 
                lateInfo.error = lateErr && lateErr.message ? lateErr.message : String(lateErr);
                console.error('⏰ Late inbox fetch failed', lateErr); 
            }
        }

        console.log('🔍 Total conversations found:', convs.length, convs);

        if (!convs || convs.length === 0) {
            console.log('❌ No conversations found, showing empty state');
            var dbg = '';
            if (debug) {
                var lines = [];
                lines.push('Meta: url=' + (metaInfo.url||'n/a'));
                lines.push('Meta: status=' + (metaInfo.status===null?'n/a':metaInfo.status) + ', count=' + (metaInfo.count||0));
                lines.push('Meta: error=' + (metaInfo.error||'none'));
                lines.push('');
                lines.push('Late: url=' + (lateInfo.url||'n/a'));
                lines.push('Late: status=' + (lateInfo.status===null?'n/a':lateInfo.status) + ', count=' + (lateInfo.count||0));
                lines.push('Late: error=' + (lateInfo.error||'none'));
                dbg = '<div style="margin-top:12px;padding:12px;background:#1a1a2e;border:1px solid #444;border-radius:6px;max-width:720px;color:#ccc;font-size:12px;">'
                    + '<b>Debug</b><br><br>' + lines.join('<br>') + '</div>';
            }
            el.innerHTML = '<div class="empty-state"><div class="icon">💬</div><p>No conversations yet</p><p style="margin-top:8px;font-size:13px;">Instagram/Facebook conversations appear after webhooks receive DMs. Other platforms load via Late.</p>' + dbg + '</div>';
            return;
        }

        // Sort by updated time
        convs.sort(function(a,b){
            return (new Date(b.updatedTime||0)).getTime() - (new Date(a.updatedTime||0)).getTime();
        });

        var html = '<div class="conv-list">';
        convs.forEach(function(c) {
            var pic = c.participantPicture ? '<img src="' + c.participantPicture + '">' : platformIcon(c.platform);
            html += '<div class="conv-item" onclick="openConversation(\\'' + c.id + '\\', \\'' + c.accountId + '\\', \\'' + (c.participantName||'').replace(/'/g,"\\\\'") + '\\', \\'' + c.platform + '\\')">';
            html += '<div class="avatar">' + pic + '</div>';
            html += '<div class="conv-info"><div class="conv-name">' + (c.participantName || 'Unknown') + '</div>';
            html += '<div class="conv-preview">' + trunc(c.lastMessage, 60) + '</div></div>';
            html += '<div class="conv-meta"><div class="conv-time">' + timeAgo(c.updatedTime) + '</div>';
            html += '<div class="conv-platform">' + c.platform + '</div>';
            if (c.unreadCount > 0) html += '<div class="unread-dot" style="margin-top:4px;"></div>';
            html += '</div></div>';
        });
        html += '</div>';
        el.innerHTML = html;
    } catch(e) { el.innerHTML = '<div class="error-box">Failed to load conversations</div>'; }
}

async function openConversation(convId, accountId, name, platform) {
    openConvId = convId; openConvAccountId = accountId;
    openConvPlatform = platform;
    openConvName = name;
    var panel = document.getElementById('msg-panel');
    panel.classList.add('open');
    document.getElementById('msg-header-name').textContent = name + ' (' + platform + ')';
    document.getElementById('msg-list').innerHTML = '<div class="loading">Loading messages...</div>';

    try {
        var isMeta = (platform === 'instagram' || platform === 'facebook');
        var url = isMeta
            ? ('/inbox/api/meta/conversations/' + convId + '/messages')
            : ('/inbox/api/conversations/' + convId + '/messages?accountId=' + accountId + '&platform=' + encodeURIComponent(platform || ''));
        var r = await fetch(url);
        var d = await r.json();
        var msgs = d.messages || [];
        if (msgs.length === 0) {
            document.getElementById('msg-list').innerHTML = '<div class="empty-state"><p>No messages in this conversation</p></div>';
            return;
        }
        var html = '<div class="msg-list">';
        msgs.forEach(function(m) {
            var cls = m.direction === 'outgoing' ? 'outgoing' : 'incoming';
            html += '<div class="msg-bubble ' + cls + '">' + (m.message || m.text || '') + '</div>';
            html += '<div class="msg-time" style="text-align:' + (cls==='outgoing'?'right':'left') + ';">' + timeAgo(m.createdAt || m.timestamp) + ' · ' + (m.senderName || m.from || '') + '</div>';
        });
        html += '</div>';
        document.getElementById('msg-list').innerHTML = html;
        var ml = document.getElementById('msg-list').parentElement;
        if (ml) ml.scrollTop = ml.scrollHeight;
    } catch(e) { console.error(e); document.getElementById('msg-list').innerHTML = '<div class="error-box">Failed to load messages: ' + e.message + '</div>'; }
}

function closeConversation() {
    document.getElementById('msg-panel').classList.remove('open');
    openConvId = null;
    openConvPlatform = null;
    openConvName = null;
}

async function sendReply() {
    if (!openConvId) return;
    var input = document.getElementById('msg-input');
    var text = input.value.trim();
    if (!text) return;
    input.value = '';
    input.style.height = '';
    try {
        var isMeta = (openConvPlatform === 'instagram' || openConvPlatform === 'facebook');
        var url = isMeta
            ? ('/inbox/api/meta/conversations/' + openConvId + '/send')
            : ('/inbox/api/conversations/' + openConvId + '/send');
        await fetch(url, {
            method: 'POST', headers: {'Content-Type':'application/json'},
            body: JSON.stringify({accountId: openConvAccountId, message: text, platform: openConvPlatform})
        });
        toast('Message sent');
        openConversation(openConvId, openConvAccountId, openConvName || '', openConvPlatform);
    } catch(e) { toast('Failed to send', 'error'); }
}

// ─── Comments ───────────────────────────────────────────
async function loadComments() {
    var el = document.getElementById('comments-list');
    el.innerHTML = '<div class="loading">Loading comments...</div>';
    try {
        var url = '/inbox/api/comments?limit=20&sortBy=date&sortOrder=desc';
        if (platformFilter) url += '&platform=' + platformFilter;
        var r = await fetch(url);
        var d = await r.json();
        if (!d.data || d.data.length === 0) {
            el.innerHTML = '<div class="empty-state"><div class="icon">💬</div><p>No comments yet</p><p style="margin-top:8px;font-size:13px;">This panel is Late-powered (non-Meta). Use /comments/dashboard for Instagram/Facebook.</p></div>';
            return;
        }
        
        var html = '';
        
        // Try to load comment auto-reply settings
        try {
            var settingsR = await fetch('/inbox/api/comment-auto-reply');
            var settings = await settingsR.json();
            
            // Build platforms from data
            var platforms = {};
            d.data.forEach(function(post) {
                platforms[post.platform] = true;
            });
            
            if (Object.keys(platforms).length > 0) {
                html += '<div class="comment-auto-reply-bar">';
                html += '<div style="font-size:13px;color:#8b98a5;margin-bottom:8px;">Auto-reply to comments:</div>';
                Object.keys(platforms).forEach(function(platform) {
                    var checked = settings[platform] ? ' checked' : '';
                    html += '<label class="inline-toggle"><input type="checkbox" onchange="toggleCommentAutoReply(\\'' + platform + '\\', this.checked)"' + checked + '><span></span> ' + platform.charAt(0).toUpperCase() + platform.slice(1) + '</label>';
                });
                html += '</div><div style="margin-bottom:16px;"></div>';
            }
        } catch(settingsErr) { 
            console.error('Could not load comment auto-reply settings:', settingsErr);
        }
        
        d.data.forEach(function(post) {
            html += '<div class="comment-post">';
            html += '<div class="comment-post-header"><div>';
            html += '<span class="comment-post-platform">' + post.platform + '</span>';
            html += ' <span style="color:#8b98a5;font-size:12px;">@' + (post.accountUsername||'') + '</span>';
            html += '</div><div style="color:#8b98a5;font-size:12px;">' + timeAgo(post.createdTime) + '</div></div>';
            html += '<div class="comment-post-content">' + trunc(post.content, 200) + '</div>';
            html += '<div class="comment-post-stats">';
            html += '<span>💬 ' + (post.commentCount||0) + ' comments</span>';
            html += '<span>❤ ' + (post.likeCount||0) + ' likes</span>';
            if (post.permalink) html += '<span><a href="' + post.permalink + '" target="_blank" style="color:#1877f2;text-decoration:none;">View ↗</a></span>';
            html += '</div>';
            html += '<button onclick="loadPostComments(\\'' + post.id + '\\', \\'' + post.accountId + '\\', \\'' + post.platform + '\\', this)" style="background:none;border:1px solid #2f3336;color:#1877f2;padding:6px 14px;border-radius:14px;cursor:pointer;font-size:13px;">Load Comments</button>';
            html += '<div class="comments-container" id="comments-' + post.id + '"></div>';
            html += '<div class="reply-form" id="reply-' + post.id + '" style="display:none;">';
            html += '<textarea id="reply-input-' + post.id + '" placeholder="Write a reply\u2026" rows="2"></textarea>';
            html += '<div class="reply-form-actions">';
            html += '<button class="ai-btn" onclick="generateAIReply(\\'reply-input-' + post.id + '\\')">\u2728 AI Reply</button>';
            html += '<button onclick="replyToPost(\\'' + post.id + '\\', \\'' + post.accountId + '\\', \\'' + post.platform + '\\')">Reply</button>';
            html += '</div></div>';
            html += '</div>';
        });
        el.innerHTML = html;
    } catch(e) { el.innerHTML = '<div class="error-box">Failed to load comments</div>'; }
}

async function loadPostComments(postId, accountId, platform, btn) {
    var container = document.getElementById('comments-' + postId);
    container.innerHTML = '<div class="loading" style="padding:10px;">Loading...</div>';
    if (btn) btn.style.display = 'none';
    document.getElementById('reply-' + postId).style.display = 'flex';
    try {
        var r = await fetch('/inbox/api/comments/' + postId + '?accountId=' + accountId + '&platform=' + encodeURIComponent(platform || ''));
        var d = await r.json();
        var comments = d.comments || [];
        if (comments.length === 0) {
            container.innerHTML = '<p style="color:#8b98a5;padding:10px;font-size:13px;">No comments on this post.</p>';
            return;
        }
        var html = '';
        comments.forEach(function(c) {
            var pic = (c.from && c.from.picture) ? '<img src="' + c.from.picture + '">' : '👤';
            var name = (c.from && c.from.name) ? c.from.name : 'Unknown';
            var isOwner = (c.from && c.from.isOwner) ? ' <span style="color:#00ba7c;font-size:11px;">(You)</span>' : '';
            html += '<div class="comment-item">';
            html += '<div class="c-avatar">' + pic + '</div>';
            html += '<div class="c-body">';
            html += '<div class="c-author">' + name + isOwner + '</div>';
            html += '<div class="c-text">' + (c.message || '') + '</div>';
            html += '<div class="c-meta">' + timeAgo(c.createdTime);
            if (c.likeCount > 0) html += ' · ❤ ' + c.likeCount;
            if (c.replyCount > 0) html += ' · ' + c.replyCount + ' replies';
            html += '</div>';
            html += '<div class="comment-actions">';
            if (c.canReply) html += '<button onclick="showReplyToComment(\\'' + postId + '\\', \\'' + c.id + '\\', \\'' + accountId + '\\', \\'' + (platform || '') + '\\', this)">Reply</button>';
            if (c.canDelete) html += '<button onclick="deleteComment(\\'' + postId + '\\', \\'' + c.id + '\\', \\'' + accountId + '\\', \\'' + (platform || '') + '\\')">Delete</button>';
            if (c.canHide && !c.isHidden) html += '<button onclick="hideComment(\\'' + postId + '\\', \\'' + c.id + '\\', \\'' + accountId + '\\', \\'' + (platform || '') + '\\')">Hide</button>';
            if (c.canHide && c.isHidden) html += '<button onclick="unhideComment(\\'' + postId + '\\', \\'' + c.id + '\\', \\'' + accountId + '\\', \\'' + (platform || '') + '\\')">Unhide</button>';
            if (c.url) html += '<a href="' + c.url + '" target="_blank" style="color:#1877f2;font-size:12px;text-decoration:none;">View ↗</a>';
            html += '</div>';
            // Nested replies
            if (c.replies && c.replies.length > 0) {
                c.replies.forEach(function(r) {
                    var rName = (r.from && r.from.name) ? r.from.name : 'Unknown';
                    html += '<div class="comment-item" style="margin-left:20px;border-color:#1a1f25;">';
                    html += '<div class="c-body"><div class="c-author">' + rName + '</div>';
                    html += '<div class="c-text">' + (r.message||'') + '</div>';
                    html += '<div class="c-meta">' + timeAgo(r.createdTime) + '</div></div></div>';
                });
            }
            html += '</div></div>';
        });
        container.innerHTML = html;
    } catch(e) { container.innerHTML = '<div class="error-box">Failed to load comments</div>'; }
}

function showReplyToComment(postId, commentId, accountId, platform, btn) {
    var parent = btn.closest('.comment-item');
    var existing = parent.querySelector('.reply-form');
    if (existing) { existing.remove(); return; }
    var form = document.createElement('div');
    form.className = 'reply-form';
    form.innerHTML =
        '<textarea id="creply-' + commentId + '" placeholder="Write a reply\u2026" rows="2"></textarea>' +
        '<div class="reply-form-actions">' +
        '<button class="ai-btn" onclick="generateAIReply(\\'creply-' + commentId + '\\')">\u2728 AI Reply</button>' +
        '<button onclick="replyToComment(\\'' + postId + '\\', \\'' + commentId + '\\', \\'' + accountId + '\\', \\'' + (platform || '') + '\\')">Send</button>' +
        '</div>';
    parent.querySelector('.c-body').appendChild(form);
}

async function replyToPost(postId, accountId, platform) {
    var input = document.getElementById('reply-input-' + postId);
    var text = input.value.trim();
    if (!text) return;
    input.value = '';
    try {
        await fetch('/inbox/api/comments/' + postId + '/reply', {
            method: 'POST', headers: {'Content-Type':'application/json'},
            body: JSON.stringify({accountId: accountId, message: text, platform: platform})
        });
        toast('Reply posted');
        loadPostComments(postId, accountId, platform);
    } catch(e) { toast('Failed to reply', 'error'); }
}

async function replyToComment(postId, commentId, accountId, platform) {
    var input = document.getElementById('creply-' + commentId);
    if (!input) return;
    var text = input.value.trim();
    if (!text) return;
    input.value = '';
    try {
        await fetch('/inbox/api/comments/' + postId + '/reply', {
            method: 'POST', headers: {'Content-Type':'application/json'},
            body: JSON.stringify({accountId: accountId, message: text, commentId: commentId, platform: platform})
        });
        toast('Reply posted');
        loadPostComments(postId, accountId, platform);
    } catch(e) { toast('Failed to reply', 'error'); }
}

async function deleteComment(postId, commentId, accountId, platform) {
    if (!confirm('Delete this comment?')) return;
    try {
        await fetch('/inbox/api/comments/' + postId + '?accountId=' + accountId + '&commentId=' + commentId + '&platform=' + encodeURIComponent(platform || ''), {method:'DELETE'});
        toast('Comment deleted');
        loadPostComments(postId, accountId, platform);
    } catch(e) { toast('Failed to delete', 'error'); }
}

async function hideComment(postId, commentId, accountId, platform) {
    try {
        await fetch('/inbox/api/comments/' + postId + '/' + commentId + '/hide', {
            method: 'POST', headers: {'Content-Type':'application/json'},
            body: JSON.stringify({accountId: accountId, platform: platform})
        });
        toast('Comment hidden');
        loadPostComments(postId, accountId, platform);
    } catch(e) { toast('Failed to hide', 'error'); }
}

async function unhideComment(postId, commentId, accountId, platform) {
    try {
        await fetch('/inbox/api/comments/' + postId + '/' + commentId + '/hide?accountId=' + accountId + '&platform=' + encodeURIComponent(platform || ''), {method:'DELETE'});
        toast('Comment unhidden');
        loadPostComments(postId, accountId, platform);
    } catch(e) { toast('Failed to unhide', 'error'); }
}

// ─── Reviews ────────────────────────────────────────────
async function loadReviews() {
    var el = document.getElementById('reviews-list');
    el.innerHTML = '<div class="loading">Loading reviews...</div>';
    try {
        var url = '/inbox/api/reviews?limit=20';
        if (platformFilter) url += '&platform=' + platformFilter;
        var r = await fetch(url);
        var d = await r.json();
        if (!d.data || d.data.length === 0) {
            el.innerHTML = '<div class="empty-state"><div class="icon">⭐</div><p>No reviews yet</p><p style="margin-top:8px;font-size:13px;">Reviews from Facebook Pages and Google Business will show here.</p></div>';
            return;
        }
        var html = '';
        d.data.forEach(function(rv) {
            html += '<div class="review-card">';
            html += '<div class="review-header">';
            html += '<div><span class="review-author">' + (rv.reviewer && rv.reviewer.name ? rv.reviewer.name : 'Anonymous') + '</span>';
            html += ' <span class="comment-post-platform">' + rv.platform + '</span></div>';
            html += '<div class="review-stars">' + '★'.repeat(rv.rating || 0) + '☆'.repeat(5-(rv.rating||0)) + '</div>';
            html += '</div>';
            if (rv.text) html += '<div class="review-text">' + rv.text + '</div>';
            html += '<div style="color:#8b98a5;font-size:12px;">' + timeAgo(rv.created) + '</div>';
            if (rv.hasReply && rv.reply) {
                html += '<div class="review-reply"><div class="review-reply-label">Your Reply</div>';
                html += '<div class="review-reply-text">' + rv.reply.text + '</div></div>';
            } else {
                html += '<div class="reply-form" style="margin-left:0;margin-top:10px;">';
                html += '<textarea id="rv-input-' + rv.id + '" placeholder="Reply to review\u2026" rows="2"></textarea>';
                html += '<div class="reply-form-actions">';
                html += '<button class="ai-btn" onclick="generateAIReply(\\'rv-input-' + rv.id + '\\')">\u2728 AI Reply</button>';
                html += '<button onclick="replyToReview(\\'' + rv.id + '\\', \\'' + rv.accountId + '\\', \\'' + rv.platform + '\\')">Reply</button>';
                html += '</div></div>';
            }
            html += '</div>';
        });
        el.innerHTML = html;
    } catch(e) { el.innerHTML = '<div class="error-box">Failed to load reviews</div>'; }
}

async function replyToReview(reviewId, accountId, platform) {
    var input = document.getElementById('rv-input-' + reviewId);
    var text = input.value.trim();
    if (!text) return;
    input.value = '';
    try {
        await fetch('/inbox/api/reviews/' + reviewId + '/reply', {
            method: 'POST', headers: {'Content-Type':'application/json'},
            body: JSON.stringify({accountId: accountId, message: text, platform: platform})
        });
        toast('Reply posted');
        loadReviews();
    } catch(e) { toast('Failed to reply', 'error'); }
}

// ─── Auto-Reply Settings ────────────────────────────────
async function loadAutoReplySettings() {
    try {
        var r = await fetch('/inbox/api/auto-reply');
        var settings = await r.json();
        document.getElementById('settings-list').innerHTML = '';
        Object.keys(settings).forEach(function(platform) {
            var enabled = settings[platform];
            var html = '<div class="setting-row">';
            html += '<label>' + platform.charAt(0).toUpperCase() + platform.slice(1) + '</label>';
            html += '<label class="toggle"><input type="checkbox" onchange="toggleAutoReply(\\'' + platform + '\\', this.checked)"' + (enabled ? ' checked' : '') + '><span></span></label>';
            html += '</div>';
            document.getElementById('settings-list').innerHTML += html;
        });
    } catch(e) { console.error('Failed to load auto-reply settings:', e); }
}

async function toggleAutoReply(platform, enabled) {
    try {
        var r = await fetch('/inbox/api/auto-reply/' + platform, {
            method: 'POST', headers: {'Content-Type':'application/json'},
            body: JSON.stringify({enabled: enabled})
        });
        var result = await r.json();
        if (result.success) {
            toast('Auto-reply ' + (enabled ? 'enabled' : 'disabled') + ' for ' + platform);
        }
    } catch(e) { toast('Failed to update auto-reply setting', 'error'); }
}

async function toggleCommentAutoReply(platform, enabled) {
    try {
        var r = await fetch('/inbox/api/comment-auto-reply/' + platform, {
            method: 'POST', headers: {'Content-Type':'application/json'},
            body: JSON.stringify({enabled: enabled})
        });
        var result = await r.json();
        if (result.success) {
            toast('Comment auto-reply ' + (enabled ? 'enabled' : 'disabled') + ' for ' + platform);
        }
    } catch(e) { toast('Failed to update comment auto-reply', 'error'); }
}

// ─── Init ───────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', function() {
    loadConversations();
    loadComments();
    loadReviews();
    loadAutoReplySettings();
});

document.addEventListener('keydown', function(e) {
    if (e.key === 'Enter' && (e.ctrlKey || e.metaKey) && document.activeElement && document.activeElement.id === 'msg-input') {
        e.preventDefault();
        sendReply();
    }
});
"""


@router.post("/api/ai-reply")
async def generate_inbox_ai_reply(request: Request, alita_session: Optional[str] = Cookie(None)):
    from database.db import get_db
    from utils.shared_layout import require_auth_and_profile, _Redirect
    data = {}
    try:
        data = await request.json()
    except Exception:
        pass
    message_text = (data.get("text") or "").strip()
    db = next(get_db())
    try:
        try:
            user, profile = require_auth_and_profile(request, db)
        except _Redirect:
            return JSONResponse({"error": "Not authenticated"}, status_code=401)
        client_id = getattr(profile, "client_id", None) or "default_client"
        try:
            from agents.engagement_agent import EngagementAgent
            agent = EngagementAgent(client_id=client_id, use_voice_matching=False)
            prompt = message_text if message_text else "Someone reached out to us. Write a short, friendly reply."
            reply = agent.respond_to_message(
                message=prompt, client_id=client_id,
                sender_id="inbox_ai_request", use_memory=False,
            )
            if len(reply) > 350:
                reply = reply[:347] + "..."
            return JSONResponse({"reply": reply})
        except Exception as e:
            print(f"❌ Inbox AI reply failed: {e}")
            return JSONResponse({"reply": "Thanks for reaching out! Happy to help — let us know what you need. 👋"})
    finally:
        db.close()


@router.get("/dashboard", response_class=HTMLResponse)
async def inbox_dashboard(request: Request):
    from utils.shared_layout import build_page, require_auth_and_profile, _Redirect
    from database.db import get_db

    db = next(get_db())
    try:
        try:
            user, profile = require_auth_and_profile(request, db)
        except _Redirect as r:
            return r.response()

        body = """
            <div style="margin-bottom:22px">
                <h1 style="font-size:1.35rem;font-weight:800">&#128236; Inbox</h1>
                <p style="font-size:.85rem;color:#606770;margin-top:4px">Manage DMs, comments, and reviews across all platforms</p>
            </div>

            <div class="inbox-tabs">
                <button class="inbox-tab active" onclick="switchTab('conversations')">&#128172; Messages</button>
                <button class="inbox-tab" onclick="switchTab('comments')">&#128173; Comments</button>
                <button class="inbox-tab" onclick="switchTab('reviews')">&#11088; Reviews</button>
            </div>

            <div class="filter-bar">
                <button class="filter-btn" onclick="filterPlatform(this,'instagram')">&#128247; Instagram</button>
                <button class="filter-btn" onclick="filterPlatform(this,'facebook')">f Facebook</button>
                <button class="filter-btn" onclick="filterPlatform(this,'twitter')">&#120143; Twitter</button>
                <button class="filter-btn" onclick="filterPlatform(this,'linkedin')">in LinkedIn</button>
                <button class="filter-btn" onclick="filterPlatform(this,'threads')">&#129529; Threads</button>
                <button class="filter-btn" onclick="filterPlatform(this,'tiktok')">&#9834; TikTok</button>
                <button class="filter-btn" onclick="filterPlatform(this,'youtube')">&#9654; YouTube</button>
                <button class="filter-btn" onclick="filterPlatform(this,'reddit')">&#129302; Reddit</button>
                <button class="filter-btn" onclick="filterPlatform(this,'telegram')">&#9992; Telegram</button>
                <button class="filter-btn" style="margin-left:auto;" onclick="document.getElementById('settings-panel').classList.toggle('open')">&#9881;&#65039; Auto-Reply</button>
            </div>

            <div id="panel-conversations" class="tab-panel active">
                <div id="msg-panel" class="msg-panel">
                    <div class="msg-header">
                        <button class="back-btn" onclick="closeConversation()">&#8592; Back</button>
                        <strong id="msg-header-name"></strong>
                        <span></span>
                    </div>
                    <div id="msg-list" class="msg-list"></div>
                    <div class="msg-input-row">
                        <textarea id="msg-input" placeholder="Type a message\u2026 (Ctrl+Enter to send)" rows="2"></textarea>
                        <div class="msg-input-actions">
                            <button class="ai-btn" onclick="generateAIReply('msg-input')">&#10024; AI Reply</button>
                            <button onclick="sendReply()">Send</button>
                        </div>
                    </div>
                </div>
                <div id="conv-list"></div>
            </div>

            <div id="panel-comments" class="tab-panel">
                <div id="comments-list"></div>
            </div>

            <div id="panel-reviews" class="tab-panel">
                <div id="reviews-list"></div>
            </div>

            <div id="settings-panel" class="settings-panel">
                <div class="settings-title">&#129302; Auto-Reply Settings</div>
                <div id="settings-list"></div>
            </div>
        """

        html = build_page(
            title="Inbox",
            active_nav="inbox",
            body_content=body,
            user_name=user.full_name,
            business_name=profile.business_name,
            extra_css=INBOX_CSS,
            extra_js=INBOX_JS,
        )
        return HTMLResponse(html)
    finally:
        db.close()
