"""
Post Creation Routes - Manually create posts across all platforms for demo/testing

Provides unified post creation interface:
    GET  /create-post/dashboard     -> Post creation UI
    POST /create-post/api/post      -> Create post on specified platform
    POST /create-post/api/generate  -> Generate post with AI (Claude)
"""

import os
import httpx
import json
from pathlib import Path
from typing import Optional, Literal, Dict, Any
from dataclasses import dataclass
from datetime import datetime, timedelta
from fastapi import APIRouter, Request, File, UploadFile, Cookie
from fastapi.responses import HTMLResponse, JSONResponse, Response
from dotenv import load_dotenv
import anthropic
from utils.file_reader import load_texts_from_folder
from utils.image_generator import generate_image
from utils.plan_limits import check_limit, increment_usage
import tempfile
import base64
import asyncio
import logging

logger = logging.getLogger(__name__)

# Lazy-initialized faceless generator
_faceless_generator = None

def _get_faceless_generator():
    """Get or create FacelessGenerator singleton."""
    global _faceless_generator
    if _faceless_generator is None:
        try:
            from agents.faceless_generator import FacelessGenerator
            _faceless_generator = FacelessGenerator()
            logger.info("FacelessGenerator initialized for post creation")
        except Exception as e:
            logger.warning(f"FacelessGenerator not available: {e}")
    return _faceless_generator

import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from api.token_manager import TokenManager

load_dotenv()

# Type aliases
Platform = Literal["threads", "instagram", "facebook", "twitter", "linkedin", "tiktok", "youtube"]
PostTone = Literal["professional", "casual", "enthusiastic", "witty", "educational", "humorous"]

@dataclass
class AIGenerationRequest:
    """Request for AI post generation."""
    platform: Platform
    topic: str
    tone: PostTone = "professional"
    include_hashtags: bool = True
    include_emojis: bool = True

@dataclass
class PostCreationRequest:
    """Request to create a post on a platform."""
    platform: Platform
    caption: str
    image_url: Optional[str] = None
    video_url: Optional[str] = None
    link_url: Optional[str] = None
    tiktok_video_id: Optional[str] = None

@dataclass
class PostCreationResponse:
    """Response after post creation."""
    success: bool
    platform: Platform
    post_id: Optional[str] = None
    message: Optional[str] = None
    error: Optional[str] = None

router = APIRouter(prefix="/create-post", tags=["Post Creation"])

_token_manager: Optional[TokenManager] = None


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


async def _resolve_facebook_page_access(
    *,
    user_id: Optional[str],
    page_id_hint: Optional[str] = None,
) -> tuple[Optional[str], Optional[str], Optional[str]]:
    """Return (page_id, page_access_token, error).

    Preference order:
    1) OAuth session -> user access token -> /me/accounts -> page access token
    2) Fallback to env FACEBOOK_PAGE_ID + FACEBOOK_PAGE_ACCESS_TOKEN
    """
    page_id_hint = (page_id_hint or "").strip()

    if user_id:
        tm = get_token_manager()
        user_access_token = tm.get_valid_token(user_id)

        if not user_access_token:
            return None, None, "Meta OAuth token missing/expired. Reconnect in /auth/dashboard."

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                r = await client.get(
                    "https://graph.facebook.com/v22.0/me/accounts",
                    params={
                        "fields": "id,name,access_token,instagram_business_account",
                        "access_token": user_access_token,
                    },
                )
                data = r.json() if r.content else {}
                if r.status_code != 200:
                    msg = _best_graph_error_message(data, "Failed to fetch Facebook Pages for this user")
                    return None, None, msg

                pages = (data.get("data") or []) if isinstance(data, dict) else []
                if not pages:
                    return None, None, "No Facebook Pages found for this Meta user. Ensure you granted Page permissions and have admin access to a Page."

                selected = None
                if page_id_hint:
                    for p in pages:
                        if (p.get("id") or "").strip() == page_id_hint:
                            selected = p
                            break

                if selected is None:
                    selected = pages[0]

                page_id = (selected.get("id") or "").strip()
                page_access_token = (selected.get("access_token") or "").strip()
                if not page_id or not page_access_token:
                    return None, None, "Could not resolve a Page access token from Meta OAuth."

                return page_id, page_access_token, None
        except Exception as e:
            return None, None, f"Failed to resolve Page access token: {str(e)}"

    # Fallback to env (still supported for local/demo use)
    page_id = (os.getenv("FACEBOOK_PAGE_ID", "") or "").strip()
    page_access_token = (os.getenv("FACEBOOK_PAGE_ACCESS_TOKEN", "") or "").strip()
    if not page_id or not page_access_token:
        return None, None, "Facebook not connected. Connect via /auth/dashboard (preferred) or set FACEBOOK_PAGE_ID + FACEBOOK_PAGE_ACCESS_TOKEN in .env."

    return page_id, page_access_token, None


def _load_style_references(client_id: str = "demo_client") -> str:
    """Load writing samples used to mimic brand voice/style.

    Uses the same folder convention as the EngagementAgent:
    - style_references/{client_id}/ (preferred)
    - style_references/ (fallback)
    """
    try:
        # Client-specific folder first
        client_folder = Path("style_references") / (client_id or "demo_client")
        if client_folder.exists():
            style_text = load_texts_from_folder(str(client_folder))
            if style_text:
                return style_text

        # Fallback to root style_references
        root_folder = Path("style_references")
        if root_folder.exists():
            style_text = load_texts_from_folder(str(root_folder))
            if style_text:
                return style_text

        return ""
    except Exception:
        # Never block post creation if style loading fails
        return ""


_STYLE_CACHE: Dict[str, str] = {}


def _get_style_context(client_id: str = "demo_client") -> str:
    key = (client_id or "demo_client").strip() or "demo_client"
    if key not in _STYLE_CACHE:
        text = _load_style_references(key)
        # Keep prompts bounded (large PDFs/exports can be huge)
        _STYLE_CACHE[key] = (text[:8000] if text else "")
    return _STYLE_CACHE[key]


def _select_claude_model(tier: str = "pro") -> tuple[str, str]:
    """Return (primary_model, fallback_model) based on plan tier.

    Content generation is always a "complex" task.
    """
    from utils.ai_config import get_text_model, CLAUDE_HAIKU
    primary = get_text_model(tier, complexity="complex")
    fallback = CLAUDE_HAIKU
    return primary, fallback


def _best_graph_error_message(payload: Dict[str, Any], default: str) -> str:
    """Extract the most actionable error message from a Meta Graph API response."""
    try:
        err = (payload or {}).get("error") or {}
        if isinstance(err, dict):
            # Prefer user-facing guidance when Meta provides it
            return (
                (err.get("error_user_msg") or "").strip()
                or (err.get("error_user_title") or "").strip()
                or (err.get("message") or "").strip()
                or default
            )
        return default
    except Exception:
        return default


def _is_http_url(value: str) -> bool:
    v = (value or "").strip().lower()
    return v.startswith("https://") or v.startswith("http://")


async def _upload_image_to_imgbb(image_path: str) -> Optional[str]:
    """Upload a local image to imgbb for temporary public hosting."""
    imgbb_api_key = (os.getenv("IMGBB_API_KEY") or "").strip()
    if not imgbb_api_key:
        return None

    try:
        with open(image_path, "rb") as image_file:
            image_data = base64.b64encode(image_file.read()).decode()

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                "https://api.imgbb.com/1/upload",
                data={
                    "key": imgbb_api_key,
                    "image": image_data,
                },
            )
            response.raise_for_status()
            result = response.json()

        if result.get("success") and (result.get("data") or {}).get("url"):
            return result["data"]["url"]
        return None
    except Exception:
        return None


async def _download_image_to_temp(url: str) -> Optional[str]:
    """Download an image URL to a temp file (so we can re-host it for Instagram)."""
    if not _is_http_url(url):
        return None

    try:
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            r = await client.get(url)

        if r.status_code != 200:
            return None

        content_type = (r.headers.get("content-type") or "").lower()
        if not content_type.startswith("image/"):
            return None

        ext = ".jpg"
        if "png" in content_type:
            ext = ".png"
        elif "webp" in content_type:
            ext = ".webp"

        fd, path = tempfile.mkstemp(prefix="alita_ig_", suffix=ext)
        os.close(fd)
        with open(path, "wb") as f:
            f.write(r.content)
        return path
    except Exception:
        return None


async def _ensure_instagram_public_image_url(caption: str, image_url: str) -> tuple[Optional[str], Optional[str]]:
    """Return (public_url, error).

    Instagram Graph API requires a public URL Meta can fetch.
    We make that reliable by re-hosting on imgbb when possible.
    """
    supplied = (image_url or "").strip()

    # 1) If no image provided, auto-generate one from the caption.
    if not supplied:
        imgbb_api_key = (os.getenv("IMGBB_API_KEY") or "").strip()
        if not imgbb_api_key:
            return None, "Instagram requires an image. Provide an Image URL, or set IMGBB_API_KEY so Alita can auto-generate + host an image."

        tmp_path = os.path.join("temp", f"instagram_auto_{int(datetime.utcnow().timestamp())}.jpg")
        try:
            generate_image(caption, tmp_path)
        except Exception as e:
            return None, f"Failed to generate Instagram image: {str(e)}"

        hosted = await _upload_image_to_imgbb(tmp_path)
        if not hosted:
            return None, "Failed to upload generated image to imgbb. Check IMGBB_API_KEY."
        return hosted, None

    # 2) Local path supplied (rare via API): upload to imgbb.
    if os.path.exists(supplied):
        hosted = await _upload_image_to_imgbb(supplied)
        if hosted:
            return hosted, None
        return None, "Image path provided but could not upload to imgbb. Set IMGBB_API_KEY or provide a public Image URL."

    # 3) Remote URL supplied: try to re-host to make it Meta-fetchable.
    if _is_http_url(supplied):
        hosted = None
        tmp = await _download_image_to_temp(supplied)
        if tmp:
            hosted = await _upload_image_to_imgbb(tmp)
            try:
                os.remove(tmp)
            except Exception:
                pass

        if hosted:
            return hosted, None

        # If we can't re-host, fall back to using the supplied URL (may still work)
        return supplied, None

    return None, "Invalid Image URL. Provide https://... image URL (jpg/png)"

# ═══════════════════════════════════════════════════════════════════════════
# AI Post Generation
# ═══════════════════════════════════════════════════════════════════════════

@router.post("/api/generate")
async def generate_post_with_ai(request: Request) -> JSONResponse:
    """Generate a post caption using Claude AI.
    
    Request body:
        - platform (Platform): Target social platform
        - topic (str): Topic or theme for the post
        - tone (PostTone): Writing tone
        - include_hashtags (bool): Whether to include hashtags
        - include_emojis (bool): Whether to include emojis
    
    Returns:
        JSONResponse with generated_text and metadata
    """
    try:
        body = await request.json()
        platform: Platform = body.get("platform", "").lower()
        topic: str = body.get("topic", "")
        tone: PostTone = body.get("tone", "professional")
        goal: str = body.get("goal", "views_engagement")
        content_type: str = body.get("content_type", "post")
        include_hashtags: bool = body.get("include_hashtags", True)
        include_emojis: bool = body.get("include_emojis", True)
        client_id: str = (body.get("client_id") or "demo_client").strip() or "demo_client"

        # ── Plan gate: check posts_created quota (unified counter) ─────────
        _plan_tier = "pro"  # default; overridden if profile found
        try:
            from database.db import SessionLocal as _SL_gen
            from database.models import ClientProfile as _CP_gen
            from utils.plan_limits import check_post_schedule_limit as _cpsl
            _db_gen = _SL_gen()
            _prof = _db_gen.query(_CP_gen).filter(_CP_gen.client_id == client_id).first()
            if _prof:
                _ok, _used, _limit, _msg = _cpsl(_prof)
                if not _ok:
                    _db_gen.close()
                    return JSONResponse({"success": False, "error": _msg, "upgrade_url": "/billing"}, status_code=402)
            _plan_tier = getattr(_prof, "plan_tier", "pro") or "pro" if _prof else "pro"
            _db_gen.close()
        except Exception:
            pass

        api_key = (os.getenv("ANTHROPIC_API_KEY") or "").strip()
        if not api_key:
            return JSONResponse(
                {
                    "success": False,
                    "error": "ANTHROPIC_API_KEY is not configured. Set it in your .env and restart the server.",
                },
                status_code=400,
            )
        
        if not topic:
            return JSONResponse({"error": "Topic is required"}, status_code=400)
        
        # Goal descriptions
        goal_descriptions: Dict[str, str] = {
            "views_engagement": "Maximize views, likes, comments, and shares. Focus on engagement-driving content.",
            "follower_growth": "Attract new followers. Focus on shareable, discoverable content that builds audience.",
            "conversions_sales": "Drive conversions and sales. Focus on compelling CTAs and value propositions."
        }
        
        goal_desc: str = goal_descriptions.get(goal, goal_descriptions["views_engagement"])
        
        # Platform-specific character limits
        platform_limits: Dict[Platform, int] = {
            "threads": 500,
            "instagram": 2200,
            "facebook": 63206,
            "twitter": 280,
            "linkedin": 3000,
            "tiktok": 2200,
            "youtube": 5000
        }
        
        char_limit: int = platform_limits.get(platform, 300)
        
        # Platform-specific guidelines
        platform_tips: Dict[Platform, str] = {
            "threads": "Threads is a Twitter-like platform. Keep it punchy and engaging.",
            "instagram": "Instagram captions can be longer. Use line breaks for readability.",
            "facebook": "Facebook is great for storytelling. Be conversational and friendly.",
            "twitter": "Twitter has a 280 character limit. Be concise and punchy.",
            "linkedin": "LinkedIn is professional. Focus on insights and professional growth.",
            "tiktok": "TikTok captions are fun and trendy. Use popular phrases and trends.",
            "youtube": "YouTube community posts can be longer. Encourage engagement."
        }
        
        tip: str = platform_tips.get(platform, "Write an engaging social media post.")

        # Style/brand voice injection (optional but preferred)
        style_context = _get_style_context(client_id)
        style_section = ""
        if style_context:
            style_section = f"""
    ### BRAND VOICE / STYLE SAMPLES
    Mimic the tone, sentence length, and vocabulary from these examples.
    Do NOT mention the samples or that you used them.

    --- BEGIN STYLE SAMPLES ---
    {style_context}
    --- END STYLE SAMPLES ---
    """
        
        prompt: str = f"""You are an expert social media copywriter.
    {style_section}

    Write a {tone} {content_type} for {platform} about: {topic}

Content Goal: {goal.replace('_', ' ').title()}
Goal Strategy: {goal_desc}

Requirements:
- Content type: {content_type}
- Keep it under {char_limit} characters
- {tip}
- Tone: {tone}
- Include hashtags: {'Yes, use 5-10 relevant hashtags' if include_hashtags else 'No hashtags'}
- Include emojis: {'Yes, use 2-4 relevant emojis' if include_emojis else 'No emojis'}
- Make it optimized for {goal.replace('_', ' ')}

Return ONLY the post text, nothing else."""
        
        # Generate with Claude — offloaded to thread pool so we don't block the event loop
        import asyncio as _aio
        from utils.agent_executor import AGENT_POOL
        _loop = _aio.get_running_loop()

        client = anthropic.Anthropic(api_key=api_key)
        primary_model, fallback_model = _select_claude_model(tier=_plan_tier)

        def _call_claude():
            try:
                return client.messages.create(
                    model=primary_model,
                    max_tokens=1024,
                    messages=[{"role": "user", "content": prompt}],
                )
            except Exception as e:
                msg = str(e)
                should_fallback = (
                    "not_found_error" in msg.lower()
                    or "model:" in msg.lower()
                    or "404" in msg
                )
                if should_fallback and fallback_model and fallback_model != primary_model:
                    return client.messages.create(
                        model=fallback_model,
                        max_tokens=1024,
                        messages=[{"role": "user", "content": prompt}],
                    )
                else:
                    raise

        message = await _loop.run_in_executor(AGENT_POOL, _call_claude)
        
        generated_text = message.content[0].text.strip()

        # ── Auto-generate image for visual-first platforms ──────────────
        generated_image_url = None
        image_generation_note = ""
        # Always-visual platforms + any platform when content_type is image_post
        always_visual = ["instagram", "tiktok", "threads"]
        should_generate_image = (
            platform in always_visual
            or content_type in ["image_post", "carousel", "story", "reel", "video_post", "short"]
        )

        if should_generate_image:
            # Try AI image generation first (DALL-E / Flux / Midjourney)
            ai_image_generated = False
            fg = _get_faceless_generator()
            if fg:
                try:
                    from agents.faceless_generator import ImageType, ImageQuality, Platform as FGPlatform
                    # Map platform to faceless generator platform
                    fg_platform_map = {
                        "instagram": FGPlatform.INSTAGRAM_FEED,
                        "tiktok": FGPlatform.TIKTOK,
                        "facebook": FGPlatform.FACEBOOK_FEED,
                        "youtube": FGPlatform.YOUTUBE,
                        "threads": None,
                        "linkedin": None,
                        "twitter": None,
                    }
                    fg_platform = fg_platform_map.get(platform)
                    # Create an image prompt from the caption
                    image_prompt = f"Professional social media image for: {topic}. Style: {tone}, visually engaging, high quality"
                    result = await fg.generate_image(
                        prompt=image_prompt,
                        image_type=ImageType.GENERAL,
                        size="1080x1080",
                        platform=fg_platform,
                        quality=ImageQuality.BUDGET,
                    )
                    if result.success and result.url:
                        generated_image_url = result.url
                        image_generation_note = f" AI image generated ({result.api_used or 'AI'})."
                        ai_image_generated = True
                    elif result.success and result.local_path:
                        # Upload local image to imgbb
                        hosted = await _upload_image_to_imgbb(result.local_path)
                        if hosted:
                            generated_image_url = hosted
                            image_generation_note = f" AI image generated ({result.api_used or 'AI'})."
                            ai_image_generated = True
                except Exception as e:
                    logger.warning(f"AI image generation failed, falling back to text overlay: {e}")

            # Fallback: generate text-overlay image + upload to imgbb
            if not ai_image_generated:
                imgbb_api_key = (os.getenv("IMGBB_API_KEY") or "").strip()
                if imgbb_api_key:
                    try:
                        tmp_path = os.path.join(
                            "temp",
                            f"ai_gen_{platform}_{int(datetime.utcnow().timestamp())}.jpg",
                        )
                        generate_image(generated_text, tmp_path)
                        hosted_url = await _upload_image_to_imgbb(tmp_path)
                        if hosted_url:
                            generated_image_url = hosted_url
                            image_generation_note = " Image auto-generated."
                        else:
                            image_generation_note = " (Image upload failed. You can provide an Image URL manually.)"
                        try:
                            os.remove(tmp_path)
                        except Exception:
                            pass
                    except Exception as img_err:
                        image_generation_note = f" (Image generation failed: {img_err})"
                else:
                    image_generation_note = " (Set IMGBB_API_KEY or OPENAI_API_KEY to enable auto image generation.)"

        # ── Increment posts_created counter ──
        try:
            from database.db import SessionLocal as _SL_inc
            from database.models import ClientProfile as _CP_inc
            _db_inc = _SL_inc()
            _p = _db_inc.query(_CP_inc).filter(_CP_inc.client_id == client_id).first()
            if _p:
                increment_usage(_p, "posts_created", _db_inc)
            _db_inc.close()
        except Exception:
            pass

        return JSONResponse({
            "success": True,
            "platform": platform,
            "generated_text": generated_text,
            "char_count": len(generated_text),
            "char_limit": char_limit,
            "generated_image_url": generated_image_url,
            "message": f"✅ Post generated successfully!{image_generation_note}"
        }, status_code=200)
        
    except Exception as e:
        # Keep errors actionable (model misconfig is the most common failure here)
        return JSONResponse(
            {
                "success": False,
                "error": str(e),
                "hint": "If this is a model not found error, set CLAUDE_SONNET_MODEL (or ANTHROPIC_MODEL) in .env to a model enabled for your Anthropic key.",
            },
            status_code=500,
        )


# ═══════════════════════════════════════════════════════════════════════════
# Post Creation API Endpoints
# ═══════════════════════════════════════════════════════════════════════════

@router.post("/api/post")
async def create_post(
    request: Request,
    alita_session: Optional[str] = Cookie(None, alias="alita_session"),
) -> JSONResponse:
    """Create a post on the specified platform.
    
    Request body:
        - platform (Platform): Target social platform
        - caption (str): Post content/caption
        - image_url (Optional[str]): URL to image for media posts
    
    Returns:
        JSONResponse with post_id and status
    """
    try:
        body = await request.json()
        platform: Platform = body.get("platform", "").lower()
        caption: str = body.get("caption", "")
        image_url: str = (body.get("image_url") or "").strip()
        video_url: str = (body.get("video_url") or "").strip()
        link_url: str = (body.get("link_url") or "").strip()
        tiktok_video_id: str = (body.get("tiktok_video_id") or body.get("video_id") or "").strip()
        
        if not platform or not caption:
            return JSONResponse({"error": "Platform and caption required"}, status_code=400)

        # Basic platform capability validation (aligned to what this demo currently supports)
        if platform == "threads":
            if video_url:
                return JSONResponse({"error": "Threads video posting is not supported in this demo (text/image only)"}, status_code=400)
        
        # Route to appropriate platform handler
        if platform == "threads":
            media_urls = [image_url] if image_url else None
            result = await _post_via_late_api("threads", caption, media_urls)
        elif platform == "instagram":
            user_id = _get_session_user(alita_session)
            content_type_body = (body.get("content_type") or "").strip().lower()
            if content_type_body == "reel":
                result = await create_instagram_reel_post(caption, video_url, cover_url=image_url, user_id=user_id)
            else:
                result = await create_instagram_post(caption, image_url, user_id=user_id)
        elif platform == "facebook":
            user_id = _get_session_user(alita_session)
            result = await create_facebook_post(caption, image_url=image_url, link_url=link_url, user_id=user_id)
        elif platform == "twitter":
            result = await create_twitter_post(caption, image_url)
        elif platform == "linkedin":
            result = await create_linkedin_post(caption, link_url)
        elif platform == "tiktok":
            content_type_body = (body.get("content_type") or "").strip().lower()
            if content_type_body in ("video_post", "video", "short"):
                result = await _create_video_post("tiktok", caption)
            else:
                result = await create_tiktok_post(caption, image_url=image_url or None, video_id=tiktok_video_id or None)
        elif platform == "youtube":
            content_type_body = (body.get("content_type") or "").strip().lower()
            if content_type_body in ("short_video", "video", "short"):
                result = await _create_video_post("youtube", caption)
            else:
                result = await create_youtube_post(caption, image_url)
        else:
            return JSONResponse({"error": f"Platform '{platform}' not supported"}, status_code=400)
        
        return JSONResponse(result, status_code=200 if result.get("success") else 400)
    except Exception as e:
        return JSONResponse({"error": str(e), "success": False}, status_code=500)


async def create_threads_post(caption: str, image_url: Optional[str] = None) -> Dict[str, Any]:
    """Create a Threads post via Late API (Zernio)."""
    media_urls = [image_url] if image_url else None
    return await _post_via_late_api("threads", caption, media_urls)


async def create_instagram_post(caption: str, image_url: str = "", *, user_id: Optional[str] = None):
    """Create an Instagram post via Instagram Graph API (publishing requires IG Business/Creator)."""
    try:
        page_id_hint = (os.getenv("FACEBOOK_PAGE_ID", "") or "").strip()
        page_id, access_token, err = await _resolve_facebook_page_access(user_id=user_id, page_id_hint=page_id_hint)
        if err or not access_token or not page_id:
            return {"success": False, "error": err or "Facebook credentials not configured"}

        # Instagram publishing uses the Facebook Graph host, not graph.instagram.com (Basic Display API)
        graph_base = "https://graph.facebook.com/v18.0"

        # Prefer explicit config, otherwise auto-discover IG business account connected to the Page
        ig_user_id = (os.getenv("INSTAGRAM_BUSINESS_ACCOUNT_ID") or os.getenv("INSTAGRAM_USER_ID") or "").strip()

        async with httpx.AsyncClient(timeout=30.0) as client:
            if not ig_user_id:
                discover_url = f"{graph_base}/{page_id}"
                discover_r = await client.get(
                    discover_url,
                    params={
                        "fields": "instagram_business_account",
                        "access_token": access_token,
                    },
                )
                discover_data = discover_r.json() if discover_r.content else {}
                if discover_r.status_code != 200:
                    msg = (discover_data.get("error") or {}).get("message") or "Failed to discover instagram_business_account"
                    return {"success": False, "error": msg}

                ig_obj = discover_data.get("instagram_business_account") or {}
                ig_user_id = (ig_obj.get("id") or "").strip()
                if not ig_user_id:
                    return {
                        "success": False,
                        "error": "No Instagram business account is connected to this Facebook Page. Connect an IG Business/Creator account to the Page in Meta Business Suite, then reconnect in /auth/dashboard (or set INSTAGRAM_BUSINESS_ACCOUNT_ID in .env).",
                    }

            public_image_url, prep_error = await _ensure_instagram_public_image_url(caption=caption, image_url=image_url)
            if prep_error:
                return {"success": False, "error": prep_error}

            # Create a media container
            create_url = f"{graph_base}/{ig_user_id}/media"
            create_payload = {
                "image_url": public_image_url,
                "caption": caption,
                "access_token": access_token,
            }
            create_r = await client.post(create_url, data=create_payload)
            create_data = create_r.json() if create_r.content else {}

            if create_r.status_code != 200 or not create_data.get("id"):
                msg = _best_graph_error_message(create_data, "Failed to create Instagram media container")
                return {"success": False, "error": "Instagram create failed: " + msg}

            creation_id = create_data.get("id")

            # Publish the media container
            publish_url = f"{graph_base}/{ig_user_id}/media_publish"

            # Instagram often needs a short processing delay before the container can be published
            await asyncio.sleep(5)

            last_msg = ""
            for attempt in range(4):
                publish_r = await client.post(
                    publish_url,
                    data={
                        "creation_id": creation_id,
                        "access_token": access_token,
                    },
                )
                publish_data = publish_r.json() if publish_r.content else {}

                if publish_r.status_code == 200 and publish_data.get("id"):
                    return {
                        "success": True,
                        "platform": "instagram",
                        "post_id": publish_data.get("id"),
                        "message": f"✅ Instagram post created! ID: {publish_data.get('id')}",
                        "image_url_used": public_image_url,
                    }

                last_msg = _best_graph_error_message(publish_data, "Failed to publish Instagram media")
                if "not ready" in (last_msg or "").lower() and attempt < 3:
                    await asyncio.sleep(3 + attempt * 2)
                    continue
                break

            return {"success": False, "error": "Instagram publish failed: " + (last_msg or "Failed to publish Instagram media")}
    except Exception as e:
        return {"success": False, "error": str(e)}


async def create_instagram_reel_post(caption: str, video_url: str, cover_url: str = "", *, user_id: Optional[str] = None):
    """Publish an Instagram Reel via Graph API (media_type=REELS, 2-step: container → publish with polling)."""
    try:
        video_url = (video_url or "").strip()
        if not video_url or not _is_http_url(video_url):
            return {"success": False, "error": "A publicly accessible HTTPS video URL is required for Instagram Reels (MP4 format, 9:16 aspect ratio)."}

        page_id_hint = (os.getenv("FACEBOOK_PAGE_ID", "") or "").strip()
        page_id, access_token, err = await _resolve_facebook_page_access(user_id=user_id, page_id_hint=page_id_hint)
        if err or not access_token or not page_id:
            return {"success": False, "error": err or "Facebook/Instagram credentials not configured"}

        graph_base = "https://graph.facebook.com/v18.0"
        ig_user_id = (os.getenv("INSTAGRAM_BUSINESS_ACCOUNT_ID") or os.getenv("INSTAGRAM_USER_ID") or "").strip()

        async with httpx.AsyncClient(timeout=180.0) as client:
            if not ig_user_id:
                disc_r = await client.get(
                    f"{graph_base}/{page_id}",
                    params={"fields": "instagram_business_account", "access_token": access_token},
                )
                disc_data = disc_r.json() if disc_r.content else {}
                ig_user_id = ((disc_data.get("instagram_business_account") or {}).get("id") or "").strip()
                if not ig_user_id:
                    return {"success": False, "error": "No Instagram Business/Creator account connected to this Facebook Page. Connect one in Meta Business Suite then reconnect in /connect/dashboard."}

            # Step 1: Create REELS media container
            create_payload: Dict[str, str] = {
                "media_type": "REELS",
                "video_url": video_url,
                "caption": caption,
                "share_to_feed": "true",
                "access_token": access_token,
            }
            if cover_url and _is_http_url(cover_url):
                create_payload["cover_url"] = cover_url

            create_r = await client.post(f"{graph_base}/{ig_user_id}/media", data=create_payload)
            create_data = create_r.json() if create_r.content else {}
            if create_r.status_code != 200 or not create_data.get("id"):
                msg = _best_graph_error_message(create_data, "Failed to create Reel container")
                return {"success": False, "error": "Instagram Reels container creation failed: " + msg}

            container_id = create_data["id"]

            # Step 2: Poll until FINISHED or ERROR (Instagram processes the video asynchronously)
            for _ in range(24):  # up to ~2 minutes (24 x 5s)
                await asyncio.sleep(5)
                status_r = await client.get(
                    f"{graph_base}/{container_id}",
                    params={"fields": "status_code,status", "access_token": access_token},
                )
                status_data = status_r.json() if status_r.content else {}
                status_code = (status_data.get("status_code") or "").upper()
                if status_code == "FINISHED":
                    break
                if status_code in ("ERROR", "EXPIRED"):
                    detail = status_data.get("status") or status_code
                    return {"success": False, "error": f"Instagram Reels video processing failed ({detail}). Requirements: public HTTPS MP4, 9:16 aspect ratio, under 15 minutes, under 4 GB."}
            else:
                return {"success": False, "error": "Instagram Reels video processing timed out after 2 minutes. Try a shorter or smaller video."}

            # Step 3: Publish the container
            publish_r = await client.post(
                f"{graph_base}/{ig_user_id}/media_publish",
                data={"creation_id": container_id, "access_token": access_token},
            )
            publish_data = publish_r.json() if publish_r.content else {}
            if publish_r.status_code == 200 and publish_data.get("id"):
                return {
                    "success": True,
                    "platform": "instagram",
                    "post_type": "reel",
                    "post_id": publish_data["id"],
                    "message": f"✅ Instagram Reel published! ID: {publish_data['id']}",
                }
            last_msg = _best_graph_error_message(publish_data, "Failed to publish Reel")
            return {"success": False, "error": "Instagram Reels publish failed: " + last_msg}
    except Exception as e:
        return {"success": False, "error": str(e)}


async def create_facebook_post(caption: str, image_url: str = "", link_url: str = "", *, user_id: Optional[str] = None):
    """Create a Facebook post via Meta Graph API. Supports text, link, and photo posts."""
    try:
        page_id_hint = (os.getenv("FACEBOOK_PAGE_ID", "") or "").strip()
        page_id, access_token, err = await _resolve_facebook_page_access(user_id=user_id, page_id_hint=page_id_hint)
        if err or not access_token or not page_id:
            return {"success": False, "error": err or "Facebook credentials not configured"}
        
        image_url = (image_url or "").strip()
        link_url = (link_url or "").strip()

        # If an image URL is provided, create a photo post
        if image_url and _is_http_url(image_url):
            url = f"https://graph.facebook.com/v18.0/{page_id}/photos"
            payload = {
                "url": image_url,
                "caption": caption,
                "access_token": access_token,
            }
        else:
            # Text or link post
            url = f"https://graph.facebook.com/v18.0/{page_id}/feed"
            payload = {
                "message": caption,
                "access_token": access_token,
            }
            if link_url:
                payload["link"] = link_url
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.post(url, json=payload)
            data = r.json()
            
            if r.status_code == 200 and data.get("id"):
                return {
                    "success": True,
                    "platform": "facebook",
                    "post_id": data.get("id"),
                    "message": f"✅ Facebook post created! ID: {data.get('id')}"
                }
            else:
                return {
                    "success": False,
                    "error": data.get("error", {}).get("message", "Failed to create post")
                }
    except Exception as e:
        return {"success": False, "error": str(e)}


async def create_twitter_post(caption: str, image_url: str = ""):
    """Post to Twitter/X via Late API."""
    media_urls = [image_url] if image_url else None
    return await _post_via_late_api("twitter", caption, media_urls)


async def create_linkedin_post(caption: str, image_url: str = ""):
    """Post to LinkedIn via Late API."""
    media_urls = [image_url] if image_url else None
    return await _post_via_late_api("linkedin", caption, media_urls)


def _get_late_profile_id(platform: str, client_id: str = "default_client") -> Optional[str]:
    """Resolve Late API profile ID for a platform.

    Priority: PlatformConnection DB table → client_connections.json → env var.
    """
    canon = platform.lower().strip()

    # 1) Database
    try:
        from database.db import SessionLocal
        from database.models import PlatformConnection
        db = SessionLocal()
        try:
            row = (
                db.query(PlatformConnection)
                .filter(PlatformConnection.client_id == client_id,
                        PlatformConnection.platform == canon)
                .first()
            )
            if row and getattr(row, "account_id", ""):
                return row.account_id
        finally:
            db.close()
    except Exception:
        pass

    # 2) client_connections.json
    try:
        conn_file = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                                 "storage", "client_connections.json")
        if os.path.exists(conn_file):
            with open(conn_file, "r") as f:
                all_conns = json.load(f)
            info = all_conns.get(client_id, {}).get(canon, {})
            pid = info.get("profile_id", "")
            if pid:
                return pid
    except Exception:
        pass

    # 3) Environment variable
    env_val = (os.getenv(f"LATE_PROFILE_{canon.upper()}_{client_id}") or "").strip()
    return env_val or None


async def _post_via_late_api(
    platform: str,
    caption: str,
    media_urls: Optional[list] = None,
    client_id: str = "default_client",
) -> Dict[str, Any]:
    """Post to any Late-API platform (TikTok, YouTube, LinkedIn, Twitter, etc.)."""
    from api.late_client import LateAPIClient, PostRequest as LatePostRequest

    late_api_key = (os.getenv("LATE_API_KEY") or "").strip()
    if not late_api_key:
        return {"success": False,
                "error": f"Late API key not configured. Set LATE_API_KEY in .env to enable {platform} posting."}

    profile_id = _get_late_profile_id(platform, client_id)
    if not profile_id:
        return {"success": False,
                "error": f"No {platform} profile connected via Late API. "
                         f"Connect at /connections/dashboard."}

    try:
        client = LateAPIClient(api_key=late_api_key)
        req = LatePostRequest(
            platform=platform,
            profile_id=profile_id,
            content=caption,
            media_urls=media_urls if media_urls else None,
        )
        resp = await client.post_to_platform(req)

        if resp.success:
            return {"success": True, "platform": platform,
                    "post_id": resp.post_id,
                    "message": f"✅ {platform.title()} post created! ID: {resp.post_id}"}
        return {"success": False, "error": resp.error}
    except Exception as e:
        return {"success": False, "error": str(e)}


async def create_tiktok_post(
    caption: str,
    image_url: Optional[str] = None,
    video_id: Optional[str] = None
) -> Dict[str, Any]:
    """Post to TikTok via Late API."""
    media_urls = []
    if image_url:
        media_urls.append(image_url)
    return await _post_via_late_api("tiktok", caption, media_urls or None)


async def create_youtube_post(caption: str, image_url: Optional[str] = None) -> Dict[str, Any]:
    """Post to YouTube via Late API."""
    media_urls = []
    if image_url:
        media_urls.append(image_url)
    return await _post_via_late_api("youtube", caption, media_urls or None)


async def _create_video_post(platform: str, caption: str, client_id: str = "default_client") -> Dict[str, Any]:
    """Generate a faceless video, upload it, and post via Late API.

    Works for TikTok and YouTube Shorts.
    """
    try:
        from agents.faceless_generator import (
            FacelessGenerator, VideoTier, VideoStyle,
            Platform as FGPlatform,
        )
    except ImportError as e:
        return {"success": False, "error": f"Video generation not available: {e}"}

    fg_platform_map = {
        "tiktok": FGPlatform.TIKTOK,
        "youtube": FGPlatform.YOUTUBE_SHORT,
    }
    fg_platform = fg_platform_map.get(platform, FGPlatform.TIKTOK)

    try:
        fg = FacelessGenerator(client_id=client_id)
        script = (caption or "Trending content")[:1500]

        logger.info(f"[CreatePost] Generating video for {platform} …")
        vid = await fg.generate_video(
            script=script,
            tier=VideoTier.STOCK_VIDEO,
            style=VideoStyle.PROFESSIONAL,
            platform=fg_platform,
            include_captions=True,
            client_id=client_id,
        )

        if not vid.success:
            return {"success": False, "error": f"Video generation failed: {vid.error}"}

        # FFmpeg missing: success=True but no local_path or url
        if not vid.local_path and not vid.url:
            note = (vid.metadata or {}).get("note", "")
            if "FFmpeg" in note:
                return {"success": False,
                        "error": "Video visuals generated but FFmpeg is not installed on the server to assemble the final video. Please contact support."}
            return {"success": False,
                    "error": "Video generation succeeded but produced no output file."}

        # Get a public URL for the video
        video_url = vid.url  # Some tiers return a hosted URL directly
        local_path = vid.local_path

        if not video_url and local_path:
            if not os.path.isfile(local_path):
                logger.error(f"[CreatePost] Video local_path does not exist: {local_path}")
                return {"success": False,
                        "error": "Video generated but file not found on server."}

            file_size = os.path.getsize(local_path)
            logger.info(f"[CreatePost] Video file: {local_path} ({file_size} bytes)")

            # Try multiple upload services
            from utils.media_upload import upload_to_catbox, upload_to_fileio

            video_url = await upload_to_catbox(local_path)
            if video_url:
                logger.info(f"[CreatePost] Uploaded to catbox: {video_url}")
            else:
                logger.warning("[CreatePost] Catbox upload failed, trying file.io")
                video_url = await upload_to_fileio(local_path)
                if video_url:
                    logger.info(f"[CreatePost] Uploaded to file.io: {video_url}")

            # Fallback: try imgbb if file is small enough (< 32 MB) and is image-like
            # imgbb doesn't support video, skip it

            if not video_url:
                # Last resort: try 0x0.st (free, supports video, no auth)
                try:
                    async with httpx.AsyncClient(timeout=120.0) as client:
                        with open(local_path, "rb") as f:
                            r = await client.post(
                                "https://0x0.st",
                                files={"file": (os.path.basename(local_path), f)},
                            )
                        if r.status_code == 200 and r.text.strip().startswith("http"):
                            video_url = r.text.strip()
                            logger.info(f"[CreatePost] Uploaded to 0x0.st: {video_url}")
                        else:
                            logger.warning(f"[CreatePost] 0x0.st failed: {r.status_code} {r.text[:200]}")
                except Exception as e0x0:
                    logger.warning(f"[CreatePost] 0x0.st error: {e0x0}")

        if not video_url:
            return {"success": False,
                    "error": "Video generated but all upload services failed. Try again later."}

        logger.info(f"[CreatePost] Posting to {platform} via Late API with video_url={video_url}")
        # Post via Late API with the video URL
        result = await _post_via_late_api(platform, caption, [video_url], client_id)
        logger.info(f"[CreatePost] Late API result: {result}")
        return result

    except Exception as e:
        logger.exception(f"Video post creation failed for {platform}")
        return {"success": False, "error": str(e)}


# ═══════════════════════════════════════════════════════════════════════════
# Dashboard UI
# ═══════════════════════════════════════════════════════════════════════════

CREATE_POST_CSS = """
* { margin: 0; padding: 0; box-sizing: border-box; }
body {
    font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
    background: linear-gradient(135deg, #f0f2f5 0%, #fff 100%);
    color: #1c1e21;
    min-height: 100vh;
}
.nav-bar {
    background: #fff; border-bottom: 1px solid #e4e6eb;
    padding: 16px 24px; display: flex; justify-content: space-between; align-items: center;
}
.brand { font-size: 20px; font-weight: 700; }
.nav-links a { color: #606770; text-decoration: none; margin-left: 24px; font-size: 14px; }
.nav-links a:hover { color: #1c1e21; }

.container { max-width: 1200px; margin: 0 auto; padding: 24px; }
.header { margin-bottom: 32px; }
.header h1 { font-size: 32px; margin-bottom: 8px; }
.header p { color: #606770; font-size: 14px; }

.create-post-grid {
    display: grid; grid-template-columns: 1fr 2fr; gap: 24px; margin-bottom: 32px;
}
.platform-selector {
    background: #fff; border: 1px solid #e4e6eb; border-radius: 12px;
    padding: 24px; display: flex; flex-direction: column; gap: 12px; height: fit-content;
}
.platform-btn {
    padding: 12px 16px; border: 1px solid #e4e6eb; background: transparent;
    color: #606770; border-radius: 8px; cursor: pointer; font-size: 14px; font-weight: 600;
    transition: all 0.2s; text-align: left;
}
.platform-btn:hover { border-color: #5c6ac4; color: #5c6ac4; }
.platform-btn.active { background: #5c6ac4; color: #fff; border-color: #5c6ac4; }

.post-form {
    background: #fff; border: 1px solid #e4e6eb; border-radius: 12px; padding: 24px;
}
.form-group {
    margin-bottom: 20px; display: flex; flex-direction: column;
}
.form-group label {
    font-weight: 600; margin-bottom: 8px; color: #1c1e21; font-size: 14px;
}
.form-group input,
.form-group textarea,
.form-group select {
    padding: 12px; border: 1px solid #e4e6eb; background: #f8f9fb;
    color: #1c1e21; border-radius: 8px; font-size: 14px; font-family: inherit;
    outline: none; transition: all 0.2s;
}
.form-group input:focus,
.form-group textarea:focus,
.form-group select:focus {
    border-color: #5c6ac4; box-shadow: 0 0 0 3px rgba(24, 119, 242, 0.1);
}
.form-group textarea { min-height: 120px; resize: vertical; }

.char-count {
    font-size: 12px; color: #606770; margin-top: 4px;
}
.char-count.warning { color: #f5c518; }
.char-count.error { color: #e74c3c; }

.form-actions {
    display: flex; gap: 12px; justify-content: flex-end; margin-top: 24px;
}
.btn {
    padding: 12px 24px; border-radius: 8px; border: none; cursor: pointer;
    font-weight: 600; font-size: 14px; transition: all 0.2s;
}
.btn-primary { background: #5c6ac4; color: #fff; }
.btn-primary:hover { background: #1665d8; }
.btn-primary:disabled { background: #606770; cursor: not-allowed; }
.btn-secondary { background: transparent; color: #5c6ac4; border: 1px solid #5c6ac4; }
.btn-secondary:hover { background: rgba(24, 119, 242, 0.1); }

.platform-info {
    background: #f8f9fb; border-left: 3px solid #5c6ac4; padding: 12px;
    border-radius: 4px; font-size: 13px; margin-bottom: 20px;
}
.platform-info.warning { border-left-color: #f5c518; background: rgba(245, 197, 24, 0.05); }
.platform-info.error { border-left-color: #e74c3c; background: rgba(231, 76, 60, 0.05); }

.response-box {
    margin-top: 24px; padding: 16px; border-radius: 8px;
    display: none; font-size: 14px;
}
.response-box.success {
    display: block; background: rgba(0, 186, 124, 0.1); border: 1px solid #2e7d32;
    color: #2e7d32;
}
.response-box.error {
    display: block; background: rgba(231, 76, 60, 0.1); border: 1px solid #e74c3c;
    color: #e74c3c;
}

.post-preview {
    background: #f8f9fb; border: 1px solid #e4e6eb; border-radius: 8px;
    padding: 16px; margin-top: 20px; display: none;
}
.post-preview.show { display: block; }
.post-preview-title { font-size: 12px; color: #606770; margin-bottom: 8px; }
.post-preview-content {
    background: #fff; padding: 12px; border-radius: 4px;
    white-space: pre-wrap; word-break: break-word; font-size: 14px;
}

.loading {
    display: inline-block; width: 4px; height: 4px; background: #5c6ac4;
    border-radius: 50%; animation: pulse 0.6s infinite;
}
.hidden { display: none !important; }
@keyframes pulse {
    0%, 100% { opacity: 0.3; }
    50% { opacity: 1; }
}
"""

CREATE_POST_JS = """
let selectedPlatform = 'threads';
const platformLimits = {
    threads: 500,
    instagram: 2200,
    facebook: 63206,
    twitter: 280,
    linkedin: 3000,
    tiktok: 2200,
    youtube: 5000
};

const platformConfig = {
    threads: {
        captionLabel: 'Post Text',
        captionPlaceholder: "What's on your mind?",
        aiContentTypes: [
            { value: 'post', label: 'Post' },
            { value: 'thread', label: 'Thread' }
        ],
        showImage: true,
        imageLabel: 'Image URL (optional)',
        showLink: false,
        linkLabel: 'Link URL (optional)',
        showTikTokVideoId: false,
        requiresImage: false,
        requiresTikTokVideoId: false,
        note: 'Supports text and optional image in this demo.'
    },
    instagram: {
        captionLabel: 'Caption',
        captionPlaceholder: 'Write a caption for your image...',
        aiContentTypes: [
            { value: 'post', label: '📸 Photo Post' },
            { value: 'reel', label: '🎬 Reel (Video)' },
            { value: 'story', label: '📖 Story' }
        ],
        showImage: true,
        imageLabel: 'Image URL (optional — leave blank to auto-generate)',
        showLink: false,
        linkLabel: 'Link URL (optional)',
        showTikTokVideoId: false,
        showVideoUrl: false,
        requiresImage: false,
        requiresTikTokVideoId: false,
        requiresVideoUrl: false,
        note: 'Visual-first. AI auto-generates images for photo posts. Reels require a video URL.'
    },
    facebook: {
        captionLabel: 'Post Text',
        captionPlaceholder: 'Write a Facebook post...',
        aiContentTypes: [
            { value: 'image_post', label: '🖼️ Image Post' },
            { value: 'text_post', label: '📝 Text Post' },
            { value: 'link_post', label: '🔗 Link Post' },
            { value: 'ad', label: '💰 Ad Copy' }
        ],
        showImage: true,
        imageLabel: 'Image URL (leave blank to auto-generate)',
        showLink: true,
        linkLabel: 'Link URL (optional)',
        showTikTokVideoId: false,
        requiresImage: false,
        requiresTikTokVideoId: false,
        note: 'Supports text, images, and links. AI generates image for image posts.'
    },
    twitter: {
        captionLabel: 'Tweet Text',
        captionPlaceholder: 'Write a tweet...',
        aiContentTypes: [
            { value: 'post', label: 'Tweet' },
            { value: 'thread', label: 'Thread' }
        ],
        showImage: false,
        imageLabel: 'Image URL (not supported)',
        showLink: false,
        linkLabel: 'Link URL (not supported)',
        showTikTokVideoId: false,
        requiresImage: false,
        requiresTikTokVideoId: false,
        note: 'Text-only in this demo (media upload not implemented).'
    },
    linkedin: {
        captionLabel: 'Post Text',
        captionPlaceholder: 'Share a professional update...',
        aiContentTypes: [
            { value: 'image_post', label: '🖼️ Image Post' },
            { value: 'text_post', label: '📝 Text Post' },
            { value: 'article', label: '📰 Article' },
            { value: 'ad', label: '💰 Ad Copy' }
        ],
        showImage: true,
        imageLabel: 'Image URL (leave blank to auto-generate)',
        showLink: true,
        linkLabel: 'Link URL (optional)',
        showTikTokVideoId: false,
        requiresImage: false,
        requiresTikTokVideoId: false,
        note: 'Supports text, images, and links. AI generates image for image posts.'
    },
    tiktok: {
        captionLabel: 'Caption',
        captionPlaceholder: 'Write a TikTok caption...',
        aiContentTypes: [
            { value: 'video_post', label: '🎬 Video Post (AI generates video)' },
            { value: 'image_post', label: '🖼️ Photo Post' }
        ],
        showImage: true,
        imageLabel: 'Image/Thumbnail URL (leave blank to auto-generate)',
        showLink: false,
        linkLabel: 'Link URL (not supported)',
        showTikTokVideoId: false,
        requiresImage: false,
        requiresTikTokVideoId: false,
        note: '🎬 Video Post: AI generates a faceless video and posts it. Photo Post: image via Late API. Connect TikTok at /connections/dashboard.'
    },
    youtube: {
        captionLabel: 'Post Text',
        captionPlaceholder: 'Write a YouTube post...',
        aiContentTypes: [
            { value: 'short_video', label: '🎬 YouTube Short (AI generates video)' },
            { value: 'image_post', label: '🖼️ Community Image Post' },
            { value: 'community_post', label: '📝 Community Text Post' },
            { value: 'video_description', label: '📝 Video Description (text only)' }
        ],
        showImage: true,
        imageLabel: 'Image URL (leave blank to auto-generate)',
        showLink: false,
        linkLabel: 'Link URL (not supported)',
        showTikTokVideoId: false,
        requiresImage: false,
        requiresTikTokVideoId: false,
        note: '🎬 YouTube Short: AI generates a faceless short video and posts it. Connect YouTube at /connections/dashboard.'
    }
};

let selectedGoal = 'views_engagement';

function selectPlatform(platform) {
    try {
        selectedPlatform = platform;
        console.log('✓ Platform changed to:', platform);
        
        // Step 1: Remove active from all buttons
        const buttons = document.querySelectorAll('.platform-btn');
        buttons.forEach(btn => btn.classList.remove('active'));
        
        // Step 2: Add active to the clicked button
        const target = document.querySelector('[data-platform="' + platform + '"]');
        if (target) {
            target.classList.add('active');
            console.log('✓ Button highlighted');
        } else {
            console.log('✗ Button not found for platform:', platform);
        }
        
        // Step 3: Update info
        updatePlatformInfo();
        updatePlatformForm();
        validateForm();
        
        // Step 4: Update char count
        try {
            updateCharCount();
        } catch (e) {
            console.log('⚠ Char count update failed (textarea may not exist yet):', e.message);
        }
    } catch (e) {
        console.error('✗ Error in selectPlatform:', e);
    }
}

function selectGoal(goal) {
    try {
        selectedGoal = goal;
        console.log('✓ Goal changed to:', goal);
        
        // Update button styling
        const goalBtns = document.querySelectorAll('.goal-btn');
        goalBtns.forEach(btn => {
            btn.style.background = '#fff';
            btn.style.color = '#1c1e21';
        });
        
        const target = document.querySelector('[data-goal="' + goal + '"]');
        if (target) {
            target.style.background = '#5c6ac4';
            target.style.color = '#fff';
            console.log('✓ Goal button highlighted');
        }
    } catch (e) {
        console.error('✗ Error in selectGoal:', e);
    }
}

function updatePlatformInfo() {
    try {
        const infoBox = document.getElementById('platform-info');
        if (!infoBox) {
            console.log('⚠ platform-info element not found');
            return;
        }
        
        const platformNotes = {
            threads: '✅ Threads: AI generates text + image post.',
            instagram: '✅ Instagram: Photo posts auto-generate images. For Reels, select "🎬 Reel (Video)" and provide a public HTTPS MP4 URL (9:16, max 15 min).',
            facebook: '✅ Facebook: AI generates text + image. Supports links too.',
            twitter: '✅ Twitter/X: AI generates text tweets.',
            linkedin: '✅ LinkedIn: AI generates text + image. Supports links too.',
            tiktok: '✅ TikTok: AI generates caption + image/thumbnail.',
            youtube: '✅ YouTube: AI generates text + image for community posts.'
        };

        const cfg = platformConfig[selectedPlatform] || null;
        const base = platformNotes[selectedPlatform] || '❓ Platform info unavailable';
        const extra = cfg && cfg.note ? ('\\n' + cfg.note) : '';
        infoBox.textContent = base + extra;
        infoBox.className = 'platform-info';
        console.log('✓ Platform info updated');
    } catch (e) {
        console.error('✗ Error in updatePlatformInfo:', e);
    }
}

function updatePlatformForm() {
    try {
        const cfg = platformConfig[selectedPlatform];
        if (!cfg) return;

        const captionLabel = document.getElementById('caption-label');
        const caption = document.getElementById('caption');
        if (captionLabel) captionLabel.textContent = cfg.captionLabel;
        if (caption) caption.placeholder = cfg.captionPlaceholder;

        const imageGroup = document.getElementById('image-group');
        const imageLabel = document.getElementById('image-label');
        const imageInput = document.getElementById('image_url');
        if (imageGroup) imageGroup.classList.toggle('hidden', !cfg.showImage);
        if (imageLabel) imageLabel.textContent = cfg.imageLabel;
        if (imageInput) imageInput.disabled = !cfg.showImage;

        const linkGroup = document.getElementById('link-group');
        const linkLabel = document.getElementById('link-label');
        const linkInput = document.getElementById('link_url');
        if (linkGroup) linkGroup.classList.toggle('hidden', !cfg.showLink);
        if (linkLabel) linkLabel.textContent = cfg.linkLabel;
        if (linkInput) linkInput.disabled = !cfg.showLink;

        const tiktokGroup = document.getElementById('tiktok-videoid-group');
        const tiktokInput = document.getElementById('tiktok_video_id');
        if (tiktokGroup) tiktokGroup.classList.toggle('hidden', !cfg.showTikTokVideoId);
        if (tiktokInput) tiktokInput.disabled = !cfg.showTikTokVideoId;

        // Show video URL field only when Instagram + Reel is selected
        const isReel = selectedPlatform === 'instagram' && document.getElementById('ai-content-type') && document.getElementById('ai-content-type').value === 'reel';
        const videoGroup = document.getElementById('video-group');
        const videoInput = document.getElementById('video_url');
        if (videoGroup) videoGroup.classList.toggle('hidden', !isReel);
        if (videoInput) videoInput.disabled = !isReel;
        // For Instagram Reels: hide image field; for Instagram photos: show image field
        if (selectedPlatform === 'instagram') {
            if (imageGroup) imageGroup.classList.toggle('hidden', isReel);
            if (imageInput) { imageInput.disabled = isReel; }
        }

        const reqHint = document.getElementById('requirements-hint');
        if (reqHint) {
            const parts = [];
            if (cfg.requiresImage) parts.push('Image URL required');
            if (cfg.requiresTikTokVideoId) parts.push('TikTok video id required');
            reqHint.textContent = parts.length ? ('Requirements: ' + parts.join(' • ')) : '';
            reqHint.classList.toggle('hidden', parts.length === 0);
        }

        updateAIContentTypes();
    } catch (e) {
        console.error('✗ Error in updatePlatformForm:', e);
    }
}

function updateAIContentTypes() {
    try {
        const select = document.getElementById('ai-content-type');
        if (!select) return;

        const cfg = platformConfig[selectedPlatform];
        const options = (cfg && cfg.aiContentTypes) ? cfg.aiContentTypes : [
            { value: 'post', label: 'Post' }
        ];

        const current = select.value;
        select.innerHTML = '';
        options.forEach(opt => {
            const o = document.createElement('option');
            o.value = opt.value;
            o.textContent = opt.label;
            select.appendChild(o);
        });

        // Preserve previous value if still available
        const stillExists = options.some(o => o.value === current);
        select.value = stillExists ? current : (options[0] ? options[0].value : 'post');
    } catch (e) {
        console.error('✗ Error in updateAIContentTypes:', e);
    }
}

function updateCharCount() {
    try {
        const textarea = document.getElementById('caption');
        const countEl = document.getElementById('char-count');
        
        if (!textarea || !countEl) {
            console.log('⚠ Textarea or char-count element not found');
            return;
        }
        
        const limit = platformLimits[selectedPlatform] || 300;
        const count = textarea.value.length;
        
        countEl.textContent = count + ' / ' + limit + ' characters';
        countEl.classList.remove('warning', 'error');
        
        if (count > limit) {
            countEl.classList.add('error');
        } else if (count > limit * 0.9) {
            countEl.classList.add('warning');
        }
        console.log('✓ Char count updated:', count, '/', limit);
    } catch (e) {
        console.error('✗ Error in updateCharCount:', e);
    }
}

function updatePreview() {
    const caption = document.getElementById('caption').value;
    const imageUrlEl = document.getElementById('image_url');
    const linkUrlEl = document.getElementById('link_url');
    const tiktokVideoIdEl = document.getElementById('tiktok_video_id');
    const imageUrl = imageUrlEl ? imageUrlEl.value.trim() : '';
    const linkUrl = linkUrlEl ? linkUrlEl.value.trim() : '';
    const tiktokVideoId = tiktokVideoIdEl ? tiktokVideoIdEl.value.trim() : '';
    const preview = document.getElementById('post-preview');
    const content = document.getElementById('preview-content');

    const videoUrlElPrev = document.getElementById('video_url');
    const videoUrlPreview = videoUrlElPrev ? videoUrlElPrev.value.trim() : '';
    const lines = [];
    if (caption.trim()) lines.push(caption);
    if (imageUrl) lines.push('[Image] ' + imageUrl);
    if (videoUrlPreview) lines.push('[🎬 Reel Video] ' + videoUrlPreview);
    if (linkUrl) lines.push('[Link] ' + linkUrl);
    if (tiktokVideoId) lines.push('[TikTok Video ID] ' + tiktokVideoId);

    if (lines.length) {
        content.textContent = lines.join('\\n');
        preview.classList.add('show');
    } else {
        preview.classList.remove('show');
    }
}

function validateForm() {
    const responseBox = document.getElementById('response');
    const submitBtn = document.getElementById('submit-btn');

    if (!submitBtn) return true;

    const cfg = platformConfig[selectedPlatform] || {};
    const captionEl = document.getElementById('caption');
    const imageEl = document.getElementById('image_url');
    const linkEl = document.getElementById('link_url');
    const tiktokVideoIdEl = document.getElementById('tiktok_video_id');

    const caption = captionEl ? captionEl.value.trim() : '';
    const imageUrl = imageEl ? imageEl.value.trim() : '';
    const linkUrl = linkEl ? linkEl.value.trim() : '';
    const tiktokVideoId = tiktokVideoIdEl ? tiktokVideoIdEl.value.trim() : '';

    // Clear prior inline error when user changes fields
    if (responseBox && responseBox.className.indexOf('error') !== -1) {
        responseBox.className = 'response-box';
        responseBox.textContent = '';
    }

    if (!caption) {
        submitBtn.disabled = true;
        return false;
    }

    const limit = platformLimits[selectedPlatform] || 300;
    if (caption.length > limit) {
        submitBtn.disabled = true;
        return false;
    }

    if (cfg.requiresImage && !imageUrl) {
        submitBtn.disabled = true;
        return false;
    }

    if (cfg.requiresTikTokVideoId && !tiktokVideoId) {
        submitBtn.disabled = true;
        return false;
    }

    const videoUrlEl = document.getElementById('video_url');
    const videoUrl = videoUrlEl ? videoUrlEl.value.trim() : '';
    const isReelSelected = selectedPlatform === 'instagram' && document.getElementById('ai-content-type') && document.getElementById('ai-content-type').value === 'reel';
    if (isReelSelected && !videoUrl) {
        submitBtn.disabled = true;
        return false;
    }

    // Twitter demo is text-only; prevent media/link submission from UI
    if (selectedPlatform === 'twitter' && (imageUrl || linkUrl || tiktokVideoId)) {
        submitBtn.disabled = true;
        return false;
    }

    submitBtn.disabled = false;
    return true;
}

async function submitPost(e) {
    const caption = document.getElementById('caption').value.trim();
    const imageUrlEl = document.getElementById('image_url');
    const linkUrlEl = document.getElementById('link_url');
    const tiktokVideoIdEl = document.getElementById('tiktok_video_id');
    const videoUrlEl = document.getElementById('video_url');
    const contentTypeEl = document.getElementById('ai-content-type');
    const imageUrl = imageUrlEl ? imageUrlEl.value.trim() : '';
    const linkUrl = linkUrlEl ? linkUrlEl.value.trim() : '';
    const tiktokVideoId = tiktokVideoIdEl ? tiktokVideoIdEl.value.trim() : '';
    const videoUrl = videoUrlEl ? videoUrlEl.value.trim() : '';
    const contentType = contentTypeEl ? contentTypeEl.value : 'post';
    const responseBox = document.getElementById('response');

    const ok = validateForm();
    if (!ok) {
        const cfg = platformConfig[selectedPlatform] || {};
        responseBox.className = 'response-box error';
        if (!caption) {
            responseBox.textContent = '❌ Text is required';
        } else if ((cfg.requiresImage || false) && !imageUrl) {
            responseBox.textContent = '❌ Image URL is required for ' + selectedPlatform;
        } else if ((cfg.requiresTikTokVideoId || false) && !tiktokVideoId) {
            responseBox.textContent = '❌ TikTok video id is required for TikTok posting';
        } else {
            const limit = platformLimits[selectedPlatform] || 300;
            responseBox.textContent = '❌ Please fix the form (limit: ' + limit + ' characters)';
        }
        return;
    }
    
    if (!caption) {
        responseBox.className = 'response-box error';
        responseBox.textContent = '❌ Caption is required';
        return;
    }
    
    const limit = platformLimits[selectedPlatform] || 300;
    if (caption.length > limit) {
        responseBox.className = 'response-box error';
        responseBox.textContent = '❌ Caption exceeds ' + limit + ' character limit for ' + selectedPlatform;
        return;
    }
    
    const btn = (e && e.target) ? e.target : document.getElementById('submit-btn');
    btn.disabled = true;
    btn.innerHTML = '<span class="loading"></span> Posting...';
    
    try {
        const res = await fetch('/create-post/api/post', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                platform: selectedPlatform,
                caption: caption,
                image_url: imageUrl,
                video_url: videoUrl,
                link_url: linkUrl,
                tiktok_video_id: tiktokVideoId,
                content_type: contentType
            })
        });
        
        const data = await res.json();
        
        if (data.success) {
            responseBox.className = 'response-box success';
            responseBox.innerHTML = '✅ ' + data.message + '<br><small>Post ID: ' + data.post_id + '</small>';
            document.getElementById('caption').value = '';
            if (document.getElementById('image_url')) document.getElementById('image_url').value = '';
            if (document.getElementById('video_url')) document.getElementById('video_url').value = '';
            if (document.getElementById('link_url')) document.getElementById('link_url').value = '';
            if (document.getElementById('tiktok_video_id')) document.getElementById('tiktok_video_id').value = '';
            updatePreview();
            updateCharCount();
            validateForm();
        } else {
            responseBox.className = 'response-box error';
            responseBox.textContent = '❌ Error: ' + data.error;
        }
    } catch (e) {
        responseBox.className = 'response-box error';
        responseBox.textContent = '❌ Failed to create post: ' + e.message;
    }
    
    btn.disabled = false;
    btn.innerHTML = '📤 Publish';
    validateForm();
}

function clearForm() {
    document.getElementById('caption').value = '';
    if (document.getElementById('image_url')) document.getElementById('image_url').value = '';
    if (document.getElementById('video_url')) document.getElementById('video_url').value = '';
    if (document.getElementById('link_url')) document.getElementById('link_url').value = '';
    if (document.getElementById('tiktok_video_id')) document.getElementById('tiktok_video_id').value = '';
    document.getElementById('response').className = 'response-box';
    document.getElementById('response').textContent = '';
    updatePreview();
    updateCharCount();
    validateForm();
}

async function generateWithAI(e) {
    const topic = document.getElementById('ai-topic').value.trim();
    const tone = document.getElementById('ai-tone').value;
    const includeHashtags = document.getElementById('ai-hashtags').checked;
    const includeEmojis = document.getElementById('ai-emojis').checked;
    const responseBox = document.getElementById('response');
    
    if (!topic) {
        responseBox.className = 'response-box error';
        responseBox.textContent = '❌ Please enter a topic for AI generation';
        return;
    }
    
    const btn = (e && e.target) ? e.target : document.getElementById('generate-btn');
    btn.disabled = true;
    btn.innerHTML = '<span class="loading"></span> Generating with AI...';
    
    try {
        const contentType = document.getElementById('ai-content-type').value;
        const res = await fetch('/create-post/api/generate', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                platform: selectedPlatform,
                topic: topic,
                tone: tone,
                goal: selectedGoal,
                content_type: contentType,
                include_hashtags: includeHashtags,
                include_emojis: includeEmojis
            })
        });
        
        const data = await res.json();
        
        if (data.success) {
            document.getElementById('caption').value = data.generated_text;

            // Auto-fill image URL for visual platforms if an image was generated
            if (data.generated_image_url) {
                const imageUrlEl = document.getElementById('image_url');
                if (imageUrlEl) {
                    imageUrlEl.value = data.generated_image_url;
                }
            }

            responseBox.className = 'response-box success';
            let statusHtml = '✅ ' + data.message + '<br><small>' + data.char_count + ' / ' + data.char_limit + ' characters</small>';
            if (data.generated_image_url) {
                statusHtml += '<br><small>🖼️ Auto-generated image ready</small>';
                statusHtml += '<br><img src="' + data.generated_image_url + '" style="max-width:200px;border-radius:8px;margin-top:8px;" />';
            }
            responseBox.innerHTML = statusHtml;
            updatePreview();
            updateCharCount();
            validateForm();
            
            // Scroll to caption
            document.getElementById('caption').scrollIntoView({ behavior: 'smooth' });
        } else {
            responseBox.className = 'response-box error';
            responseBox.textContent = '❌ Error: ' + data.error;
        }
    } catch (e) {
        responseBox.className = 'response-box error';
        responseBox.textContent = '❌ Failed to generate: ' + e.message;
    }
    
    btn.disabled = false;
    btn.innerHTML = '✨ Generate with AI';
}

document.addEventListener('DOMContentLoaded', function() {
    updatePlatformInfo();
    updatePlatformForm();

    // Platform selection
    document.querySelectorAll('.platform-btn').forEach(btn => {
        btn.addEventListener('click', function() {
            const platform = btn.getAttribute('data-platform');
            if (platform) selectPlatform(platform);
        });
    });

    // Goal selection
    document.querySelectorAll('.goal-btn').forEach(btn => {
        btn.addEventListener('click', function() {
            const goal = btn.getAttribute('data-goal');
            if (goal) selectGoal(goal);
        });
    });

    // Action buttons
    const generateBtn = document.getElementById('generate-btn');
    if (generateBtn) generateBtn.addEventListener('click', function(ev) { generateWithAI(ev); });
    const submitBtn = document.getElementById('submit-btn');
    if (submitBtn) submitBtn.addEventListener('click', function(ev) { submitPost(ev); });

    // Refresh form fields when content type changes (e.g., switching to Reel shows video URL field)
    const ctypeSelect = document.getElementById('ai-content-type');
    if (ctypeSelect) ctypeSelect.addEventListener('change', function() { updatePlatformForm(); validateForm(); });
    const clearBtn = document.getElementById('clear-btn');
    if (clearBtn) clearBtn.addEventListener('click', function() { clearForm(); });

    const captionEl = document.getElementById('caption');
    if (captionEl) {
        captionEl.addEventListener('input', function() {
            updateCharCount();
            updatePreview();
            validateForm();
        });
    }
    if (document.getElementById('image_url')) {
        document.getElementById('image_url').addEventListener('input', function() {
            updatePreview();
            validateForm();
        });
    }
    if (document.getElementById('link_url')) {
        document.getElementById('link_url').addEventListener('input', function() {
            updatePreview();
            validateForm();
        });
    }
    if (document.getElementById('tiktok_video_id')) {
        document.getElementById('tiktok_video_id').addEventListener('input', function() {
            updatePreview();
            validateForm();
        });
    }
    validateForm();
});

// ═══════════════════════════════════════════════════════════
// SCHEDULE FOR LATER
// ═══════════════════════════════════════════════════════════
function toggleScheduleDrawer() {
    const drawer = document.getElementById('schedule-drawer');
    const isOpen = drawer.style.display !== 'none';
    drawer.style.display = isOpen ? 'none' : '';
    const btn = document.getElementById('schedule-toggle-btn');
    if (btn) btn.textContent = isOpen ? '\\u{1F4C5} Schedule' : '\\u2715 Cancel Schedule';
}

async function loadScheduleSlots() {
    const btn      = document.getElementById('sched-slots-btn');
    const grid     = document.getElementById('sched-slots-grid');
    const insights = document.getElementById('sched-insights');

    btn.disabled    = true;
    btn.textContent = '⟳ Loading…';
    grid.innerHTML  = '<span style="font-size:.78rem;color:#90949c">Asking AI for best times…</span>';
    insights.style.display = 'none';

    try {
        const r = await fetch('/api/calendar/recommended-slots', {
            method: 'POST',
            headers: {'Content-Type':'application/json'},
            body: JSON.stringify({
                platform: selectedPlatform,
                timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
                content_type: document.getElementById('ai-content-type') ? document.getElementById('ai-content-type').value : 'post'
            })
        });
        const d = await r.json();
        const slots = d.concrete_slots || [];

        if (slots.length === 0) {
            grid.innerHTML = '<span style="font-size:.78rem;color:#90949c">No slots available.</span>';
        } else {
            grid.innerHTML = '';
            slots.forEach(s => {
                const b = document.createElement('button');
                b.type      = 'button';
                b.style.cssText = 'padding:8px 6px;border-radius:8px;border:1px solid #dde0e4;background:#fff;font-size:.74rem;font-weight:600;cursor:pointer;text-align:center;line-height:1.3;transition:all .15s;border-left:3px solid ' + (s.priority === 'high' ? '#2e7d32' : '#1565c0');
                b.innerHTML = '<strong>' + (s.day || '') + '</strong><br>' + (s.label || s.datetime_local || '').replace(/.*at /,'');
                b.onclick   = () => {
                    document.querySelectorAll('#sched-slots-grid button').forEach(x => x.style.background = '#fff');
                    b.style.background = '#5c6ac4';
                    b.style.color      = '#fff';
                    document.getElementById('sched-datetime').value = s.datetime_local || '';
                };
                grid.appendChild(b);
            });
        }

        const ins = d.insights || [];
        if (ins.length > 0) {
            insights.innerHTML = '<strong>&#128161; AI Insights:</strong><ul style="margin:5px 0 0 16px">' + ins.map(i => '<li>' + i + '</li>').join('') + '</ul>';
            insights.style.display = '';
        }
    } catch(e) {
        grid.innerHTML = '<span style="color:#c62828;font-size:.78rem">Failed to load slots.</span>';
    }

    btn.disabled    = false;
    btn.textContent = '\\u2728 Get Recommended Times';
}

async function schedulePost() {
    const caption      = (document.getElementById('caption') || {}).value || '';
    const imageUrl     = (document.getElementById('image_url') || {}).value || '';
    const scheduledTime= document.getElementById('sched-datetime').value;
    const responseEl   = document.getElementById('sched-response');
    const contentType  = document.getElementById('ai-content-type') ? document.getElementById('ai-content-type').value : 'post';

    if (!scheduledTime) { responseEl.style.color = '#c62828'; responseEl.textContent = '❌ Please select a scheduled time.'; return; }
    if (!caption.trim()) { responseEl.style.color = '#c62828'; responseEl.textContent = '❌ Please write a caption first (or use Generate with AI).'; return; }

    const btn = document.getElementById('schedule-post-btn');
    btn.disabled    = true;
    btn.textContent = '⟳ Scheduling…';

    try {
        const r = await fetch('/api/calendar/schedule-post', {
            method: 'POST',
            headers: {'Content-Type':'application/json'},
            body: JSON.stringify({
                platform:       selectedPlatform,
                caption,
                image_url:      imageUrl,
                content_type:   contentType,
                scheduled_time: scheduledTime,
            })
        });
        const d = await r.json();
        if (d.ok) {
            responseEl.style.color = '#2e7d32';
            responseEl.textContent = '\\u2705 Post scheduled! View it on your Calendar.';
            setTimeout(() => {
                document.getElementById('schedule-drawer').style.display = 'none';
                document.getElementById('schedule-toggle-btn').textContent = '\\u{1F4C5} Schedule';
                responseEl.textContent = '';
                clearForm();
            }, 2000);
        } else {
            responseEl.style.color  = '#c62828';
            responseEl.textContent = '\\u274C ' + (d.error || 'Schedule failed');
        }
    } catch(e) {
        responseEl.style.color = '#c62828';
        responseEl.textContent = '\\u274C Network error';
    }

    btn.disabled    = false;
    btn.textContent = '\\u{1F4C5} Schedule Post';
}
"""

@router.get("/dashboard")
async def dashboard(request: Request):
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

    body_content = """
            <div class="header">
                <h1>✍️ Create a Post</h1>
                <p>Manually create posts across all your connected platforms for testing and demos</p>
            </div>

            <div class="create-post-grid">
                <div class="platform-selector">
                    <div style="font-weight: 600; margin-bottom: 12px; color: #1c1e21;">Select Platform</div>
                    <button class="platform-btn active" data-platform="threads" onclick="selectPlatform('threads')">Threads</button>
                    <button class="platform-btn" data-platform="instagram" onclick="selectPlatform('instagram')">Instagram</button>
                    <button class="platform-btn" data-platform="facebook" onclick="selectPlatform('facebook')">Facebook</button>
                    <button class="platform-btn" data-platform="twitter" onclick="selectPlatform('twitter')">Twitter/X</button>
                    <button class="platform-btn" data-platform="linkedin" onclick="selectPlatform('linkedin')">LinkedIn</button>
                    <button class="platform-btn" data-platform="tiktok" onclick="selectPlatform('tiktok')">TikTok</button>
                    <button class="platform-btn" data-platform="youtube" onclick="selectPlatform('youtube')">YouTube</button>
                </div>

                <div class="post-form">
                    <div id="platform-info" class="platform-info"></div>

                    <!-- AI Generation Section -->
                    <div style="background: #f8f9fb; padding: 16px; border-radius: 8px; margin-bottom: 20px; border: 1px solid #5c6ac4;">
                        <div style="font-weight: 600; margin-bottom: 16px; color: #5c6ac4; font-size: 16px;">✨ Generate with AI</div>

                        <!-- Content Goal Selection -->
                        <div class="form-group">
                            <label style="margin-bottom: 8px; display: block;">Content Goal</label>
                            <div style="display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 8px;">
                                <button type="button" class="goal-btn active" data-goal="views_engagement" onclick="selectGoal('views_engagement')" style="padding: 10px; border-radius: 8px; border: 1px solid #e4e6eb; background: #5c6ac4; color: #fff; cursor: pointer; font-weight: 600; font-size: 13px;">📢 Engagement</button>
                                <button type="button" class="goal-btn" data-goal="follower_growth" onclick="selectGoal('follower_growth')" style="padding: 10px; border-radius: 8px; border: 1px solid #e4e6eb; background: #fff; color: #1c1e21; cursor: pointer; font-weight: 600; font-size: 13px;">📈 Growth</button>
                                <button type="button" class="goal-btn" data-goal="conversions_sales" onclick="selectGoal('conversions_sales')" style="padding: 10px; border-radius: 8px; border: 1px solid #e4e6eb; background: #fff; color: #1c1e21; cursor: pointer; font-weight: 600; font-size: 13px;">💰 Sales</button>
                            </div>
                        </div>

                        <!-- Content Type Selection -->
                        <div class="form-group">
                            <label for="ai-content-type">Content Type</label>
                            <select id="ai-content-type" style="width: 100%;">
                                <option value="post">Post</option>
                                <option value="caption">Caption</option>
                                <option value="reel">Reel / Short</option>
                                <option value="story">Story</option>
                                <option value="thread">Thread</option>
                                <option value="article">Article</option>
                                <option value="ad">Ad Copy</option>
                            </select>
                        </div>

                        <div class="form-group">
                            <label for="ai-topic">Topic</label>
                            <input type="text" id="ai-topic" placeholder="e.g., New product launch, marketing tips, company culture...">
                        </div>

                        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-bottom: 12px;">
                            <div class="form-group" style="margin-bottom: 0;">
                                <label for="ai-tone">Tone</label>
                                <select id="ai-tone" style="width: 100%;">
                                    <option value="professional">Professional</option>
                                    <option value="casual">Casual</option>
                                    <option value="enthusiastic">Enthusiastic</option>
                                    <option value="witty">Witty</option>
                                    <option value="educational">Educational</option>
                                    <option value="humorous">Humorous</option>
                                </select>
                            </div>
                            <div style="display: flex; flex-direction: column; gap: 8px; justify-content: flex-end;">
                                <label style="display: flex; align-items: center; gap: 8px; cursor: pointer; font-size: 13px;">
                                    <input type="checkbox" id="ai-hashtags" checked style="width: 16px; height: 16px; cursor: pointer;">
                                    Include hashtags
                                </label>
                                <label style="display: flex; align-items: center; gap: 8px; cursor: pointer; font-size: 13px;">
                                    <input type="checkbox" id="ai-emojis" checked style="width: 16px; height: 16px; cursor: pointer;">
                                    Include emojis
                                </label>
                            </div>
                        </div>
                        <button id="generate-btn" type="button" class="btn btn-primary" style="width: 100%;" onclick="generateWithAI(event)">✨ Generate with AI</button>
                    </div>

                    <!-- Manual Post Section -->
                    <form onsubmit="return false;">
                        <div style="color: #606770; font-size: 13px; margin-bottom: 16px; padding-bottom: 12px; border-bottom: 1px solid #e4e6eb;">
                            Or enter your caption manually:
                        </div>

                        <div id="requirements-hint" class="platform-info warning hidden" style="margin-bottom: 16px;"></div>

                        <div class="form-group">
                            <label id="caption-label" for="caption">Post Caption</label>
                            <textarea id="caption" placeholder="What's on your mind?"></textarea>
                            <div id="char-count" class="char-count">0 / 500 characters</div>
                        </div>

                        <div class="form-group" id="image-group">
                            <label id="image-label" for="image_url">Image URL (optional)</label>
                            <input type="url" id="image_url" placeholder="https://example.com/image.jpg">
                        </div>

                        <div class="form-group hidden" id="video-group">
                            <label id="video-label" for="video_url">📹 Reel Video URL (required for Reels)</label>
                            <input type="url" id="video_url" placeholder="https://example.com/reel.mp4">
                            <small style="color:#606770;font-size:12px;margin-top:6px;display:block">Must be a publicly accessible HTTPS MP4, 9:16 aspect ratio, max 15 min, max 4 GB. Processing takes up to 2 minutes.</small>
                        </div>

                        <div class="form-group hidden" id="link-group">
                            <label id="link-label" for="link_url">Link URL (optional)</label>
                            <input type="url" id="link_url" placeholder="https://example.com">
                        </div>

                        <div class="form-group hidden" id="tiktok-videoid-group">
                            <label for="tiktok_video_id">TikTok Video ID (required)</label>
                            <input type="text" id="tiktok_video_id" placeholder="e.g., 1234567890 (or set TIKTOK_VIDEO_ID in .env)">
                            <small style="color:#606770; font-size:12px; margin-top:8px;">This demo uses a pre-uploaded video id (no upload in this form).</small>
                        </div>

                        <div id="post-preview" class="post-preview">
                            <div class="post-preview-title">📱 Preview</div>
                            <div class="post-preview-content" id="preview-content"></div>
                        </div>

                        <!-- Schedule for Later drawer -->
                        <div id="schedule-drawer" style="display:none;background:#f8f9fb;border:1px solid #dde0e4;border-radius:10px;padding:16px;margin-top:16px">
                            <div style="font-weight:700;font-size:.88rem;color:#1c1e21;margin-bottom:12px">&#128197; Schedule for Later</div>
                            <div style="margin-bottom:10px">
                                <label style="font-size:.82rem;font-weight:600;color:#444;display:block;margin-bottom:5px">&#127775; Recommended Time Slots</label>
                                <p style="font-size:.78rem;color:#606770;margin-bottom:8px">AI picks optimal times based on platform algorithm research.</p>
                                <button id="sched-slots-btn" type="button" class="btn btn-secondary" style="font-size:.82rem;padding:8px 14px;margin-bottom:10px" onclick="loadScheduleSlots()">
                                    &#127775; Get Recommended Times
                                </button>
                                <div id="sched-slots-grid" style="display:grid;grid-template-columns:repeat(3,1fr);gap:7px"></div>
                                <div id="sched-insights" style="background:#e8f0fe;border-radius:8px;padding:10px 12px;font-size:.78rem;color:#1565c0;margin-top:8px;display:none"></div>
                            </div>
                            <div style="margin-bottom:10px">
                                <label style="font-size:.82rem;font-weight:600;color:#444;display:block;margin-bottom:5px">Or pick a custom time:</label>
                                <input type="datetime-local" id="sched-datetime" style="width:100%;padding:9px;border:1px solid #dde0e4;border-radius:7px;font-size:.85rem">
                            </div>
                            <button id="schedule-post-btn" type="button" class="btn btn-primary" style="width:100%" onclick="schedulePost()">
                                &#128197; Schedule Post
                            </button>
                            <div id="sched-response" style="margin-top:8px;font-size:.83rem"></div>
                        </div>

                        <div class="form-actions">
                            <button id="clear-btn" type="button" class="btn btn-secondary" onclick="clearForm()">Clear</button>
                            <button id="schedule-toggle-btn" type="button" class="btn btn-secondary" onclick="toggleScheduleDrawer()">&#128197; Schedule</button>
                            <button id="submit-btn" type="button" class="btn btn-primary">📤 Publish Now</button>
                        </div>

                        <div id="response" class="response-box"></div>
                    </form>
                </div>
            </div>
    """

    return HTMLResponse(build_page(
        title="Create Post",
        active_nav="create-post",
        body_content=body_content,
        extra_css=CREATE_POST_CSS,
        extra_js=CREATE_POST_JS,
        user_name=_uname,
        business_name=_bname,
    ), headers={"Cache-Control": "no-cache, no-store, must-revalidate", "Pragma": "no-cache", "Expires": "0"})

@router.get("/assets/dashboard.css")
async def dashboard_css() -> Response:
    return Response(
        content=CREATE_POST_CSS,
        media_type="text/css",
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0",
        },
    )


@router.get("/assets/dashboard.js")
async def dashboard_js() -> Response:
    return Response(
        content=CREATE_POST_JS,
        media_type="application/javascript",
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0",
        },
    )
