# agents/alita_action_router.py
"""
Alita Action Router — Intent Detection, Optimization & Agent Delegation.

Uses Claude's tool-use API to detect when a client wants Alita to perform
an action (create content, generate image, schedule post, etc.), then:
  1. Checks plan limits / feature gates
  2. Optimizes parameters (silent enhancement)
  3. Stores a pending action for confirmation
  4. Executes the action via the appropriate agent
  5. Streams progress updates via SSE

8 Core Actions (v1):
  - create_content     → ContentCreationAgent.generate_content()
  - generate_image     → ImageGeneratorAgent.generate_image()
  - schedule_post      → DB insert to ScheduledPost
  - generate_calendar  → ContentCalendarOrchestrator.generate_calendar()
  - get_content_ideas  → MarketingIntelligenceAgent.generate_content_ideas()
  - get_growth_strategy→ GrowthHackingAgent.generate_strategy()
  - get_analytics      → AnalyticsAgent.generate_insights()
  - get_optimal_times  → CalendarAgent.get_optimal_posting_times()

9 Settings / Navigation Actions (v2):
  - navigate_to_page           → returns URL for frontend redirect
  - connect_social_account     → returns OAuth initiation URL
  - toggle_notification_email  → flips email pref in ClientProfile
  - toggle_auto_reply          → flips auto-reply in storage JSON
  - set_tone_preset            → updates tone_preferences_json
  - toggle_humor               → updates humor in tone prefs
  - toggle_casual_conversation → updates casual_conversation in tone prefs
  - add_knowledge_entry        → inserts into RAG / knowledge base
  - toggle_creative_prefs      → updates creative_preferences_json
"""

from __future__ import annotations
import os
import json
import time
import uuid
import asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Optional, AsyncGenerator, Any, Tuple

# ─────────────────────────────────────────────────────────────────────────────
# Claude Tool Definitions (tool-use schema)
# ─────────────────────────────────────────────────────────────────────────────

ALITA_TOOLS = [
    {
        "name": "create_content",
        "description": (
            "Create a social media post (caption/copy) for a specific platform. "
            "Use when the client asks to write, draft, or create a post."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "topic": {
                    "type": "string",
                    "description": "The topic or subject of the post",
                },
                "platform": {
                    "type": "string",
                    "enum": ["instagram", "facebook", "tiktok", "twitter", "linkedin", "threads"],
                    "description": "Target social media platform",
                },
                "content_type": {
                    "type": "string",
                    "enum": ["post", "reel_caption", "story", "carousel", "thread"],
                    "description": "Type of content to create",
                    "default": "post",
                },
                "tone": {
                    "type": "string",
                    "description": "Desired tone (e.g. professional, casual, funny, inspirational)",
                },
                "include_hashtags": {
                    "type": "boolean",
                    "description": "Whether to include hashtags",
                    "default": True,
                },
                "include_cta": {
                    "type": "boolean",
                    "description": "Whether to include a call-to-action",
                    "default": True,
                },
            },
            "required": ["topic", "platform"],
        },
    },
    {
        "name": "generate_image",
        "description": (
            "Generate an AI image for social media or marketing. "
            "Use when the client asks to create, generate, or make an image."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "prompt": {
                    "type": "string",
                    "description": "Description of the image to generate",
                },
                "platform": {
                    "type": "string",
                    "enum": ["instagram", "facebook", "tiktok", "twitter", "linkedin"],
                    "description": "Target platform (determines image size)",
                },
                "style": {
                    "type": "string",
                    "description": "Visual style (e.g. photorealistic, minimalist, vibrant, flat illustration)",
                },
                "size": {
                    "type": "string",
                    "description": "Image dimensions (e.g. 1080x1080, 1080x1920)",
                },
            },
            "required": ["prompt"],
        },
    },
    {
        "name": "schedule_post",
        "description": (
            "Schedule a post to be published at a specific date and time. "
            "Use when the client asks to schedule, queue, or plan a post for later."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "caption": {
                    "type": "string",
                    "description": "The post caption/text content",
                },
                "platform": {
                    "type": "string",
                    "enum": ["instagram", "facebook", "tiktok", "twitter", "linkedin", "threads"],
                    "description": "Platform to post on",
                },
                "scheduled_time": {
                    "type": "string",
                    "description": "When to publish (ISO format or natural language like 'next Monday at 10am')",
                },
                "content_type": {
                    "type": "string",
                    "enum": ["post", "reel", "story", "carousel"],
                    "description": "Type of post",
                    "default": "post",
                },
                "image_url": {
                    "type": "string",
                    "description": "URL of image to attach (if any)",
                },
                "topic": {
                    "type": "string",
                    "description": "Topic/subject of the post for tracking",
                },
            },
            "required": ["caption", "platform"],
        },
    },
    {
        "name": "generate_calendar",
        "description": (
            "Generate a full content calendar with multiple posts across platforms. "
            "Use when the client asks for a weekly/monthly content plan or calendar."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "duration_days": {
                    "type": "integer",
                    "description": "Number of days to plan for (default: 7)",
                    "default": 7,
                },
                "platforms": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Platforms to include (e.g. ['instagram', 'facebook'])",
                },
                "themes": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Content themes or topics to focus on",
                },
                "name": {
                    "type": "string",
                    "description": "Name for this calendar (e.g. 'March Week 1')",
                },
            },
            "required": [],
        },
    },
    {
        "name": "get_content_ideas",
        "description": (
            "Generate content ideas and topic suggestions for social media. "
            "Use when the client asks for ideas, inspiration, or what to post about."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "num_ideas": {
                    "type": "integer",
                    "description": "Number of ideas to generate (default: 5)",
                    "default": 5,
                },
                "platforms": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Platforms to target ideas for",
                },
                "themes": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Themes or topics to explore",
                },
                "goals": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Content goals (e.g. engagement, sales, brand awareness)",
                },
            },
            "required": [],
        },
    },
    {
        "name": "get_growth_strategy",
        "description": (
            "Generate a growth strategy with actionable tactics. "
            "Use when the client asks about growing their audience, getting followers, or growth advice."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "goal": {
                    "type": "string",
                    "description": "The growth goal (e.g. 'get 1000 followers', 'increase engagement')",
                },
                "budget": {
                    "type": "string",
                    "enum": ["low", "medium", "high"],
                    "description": "Budget level for tactics",
                    "default": "low",
                },
                "timeline": {
                    "type": "string",
                    "description": "Desired timeline (e.g. '30 days', '90 days')",
                    "default": "90 days",
                },
            },
            "required": ["goal"],
        },
    },
    {
        "name": "get_analytics",
        "description": (
            "Get analytics insights and performance summary. "
            "Use when the client asks about their performance, metrics, stats, or analytics."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "period": {
                    "type": "string",
                    "enum": ["7d", "30d", "90d"],
                    "description": "Time period to analyze",
                    "default": "30d",
                },
            },
            "required": [],
        },
    },
    {
        "name": "get_optimal_times",
        "description": (
            "Get the best times to post on a specific platform. "
            "Use when the client asks when to post or about the best posting schedule."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "platform": {
                    "type": "string",
                    "enum": ["instagram", "facebook", "tiktok", "twitter", "linkedin", "threads"],
                    "description": "Platform to get optimal times for",
                },
            },
            "required": ["platform"],
        },
    },
    # ── Navigation & Settings tools (v2) ──────────────────────────────────
    {
        "name": "navigate_to_page",
        "description": (
            "Navigate the user to a specific page in the Alita platform. "
            "Use when the client says 'take me to', 'go to', 'open', 'show me' a page."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "page_name": {
                    "type": "string",
                    "enum": [
                        "dashboard", "create-post", "calendar", "inbox", "comments",
                        "notifications", "analytics", "image-generator", "faceless-video",
                        "growth", "email-marketing", "intelligence", "settings",
                        "social-accounts", "notification-settings", "auto-reply",
                        "tone", "knowledge", "creative", "email-inbox", "security",
                        "billing", "alita-chat",
                    ],
                    "description": "The page to navigate to",
                },
            },
            "required": ["page_name"],
        },
    },
    {
        "name": "connect_social_account",
        "description": (
            "Start the process of connecting a social media account. "
            "Use when the client says 'connect my Facebook', 'link Instagram', etc."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "platform": {
                    "type": "string",
                    "enum": ["facebook", "instagram", "twitter", "tiktok", "linkedin", "threads", "youtube"],
                    "description": "Social platform to connect",
                },
            },
            "required": ["platform"],
        },
    },
    {
        "name": "toggle_notification_email",
        "description": (
            "Turn email notifications on or off for a specific type. "
            "Use when the client wants to enable/disable email alerts for sales, leads, complaints, etc."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "notification_type": {
                    "type": "string",
                    "enum": [
                        "sale", "lead", "complaint", "escalation", "support",
                        "follow_suggestion", "group_opportunity", "competitor_alert",
                        "content_idea", "growth_tip", "viral_alert", "milestone",
                        "budget_alert", "sentiment_alert", "post", "system",
                    ],
                    "description": "The notification category",
                },
                "enabled": {
                    "type": "boolean",
                    "description": "True to enable, False to disable",
                },
            },
            "required": ["notification_type", "enabled"],
        },
    },
    {
        "name": "toggle_auto_reply",
        "description": (
            "Turn auto-reply on or off for a specific social platform. "
            "Use when the client wants to enable/disable automatic replies on Instagram, Facebook, etc."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "platform": {
                    "type": "string",
                    "enum": ["instagram", "facebook", "tiktok", "linkedin", "twitter", "threads"],
                    "description": "Platform to toggle auto-reply for",
                },
                "enabled": {
                    "type": "boolean",
                    "description": "True to enable, False to disable",
                },
            },
            "required": ["platform", "enabled"],
        },
    },
    {
        "name": "set_tone_preset",
        "description": (
            "Change the writing tone/style preset for content generation. "
            "Use when the client says 'make my tone playful', 'switch to professional', etc."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "preset": {
                    "type": "string",
                    "enum": ["professional", "conversational", "playful", "educational", "bold", "empathetic"],
                    "description": "The tone preset to apply",
                },
            },
            "required": ["preset"],
        },
    },
    {
        "name": "toggle_humor",
        "description": (
            "Turn humor on or off in content generation, and optionally set intensity. "
            "Use when the client wants funny/witty content or wants to disable humor."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "enabled": {
                    "type": "boolean",
                    "description": "True to enable humor, False to disable",
                },
                "intensity": {
                    "type": "string",
                    "enum": ["subtle", "balanced", "bold"],
                    "description": "Humor intensity level",
                },
            },
            "required": ["enabled"],
        },
    },
    {
        "name": "toggle_casual_conversation",
        "description": (
            "Turn casual conversation mode on or off. "
            "When enabled, Alita responds in a more relaxed, informal style."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "enabled": {
                    "type": "boolean",
                    "description": "True to enable casual mode, False to disable",
                },
            },
            "required": ["enabled"],
        },
    },
    {
        "name": "add_knowledge_entry",
        "description": (
            "Add information to the client's knowledge base so Alita remembers it. "
            "Use when the client says 'remember that...', 'add to knowledge base', or shares business info."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "text": {
                    "type": "string",
                    "description": "The knowledge text to store",
                },
                "label": {
                    "type": "string",
                    "description": "A short label or category for this entry",
                },
            },
            "required": ["text"],
        },
    },
    {
        "name": "toggle_creative_prefs",
        "description": (
            "Toggle whether uploaded brand reference images are used for image or video generation. "
            "Use when the client wants their brand style to guide (or stop guiding) generated visuals."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "use_for_images": {
                    "type": "boolean",
                    "description": "Use brand references when generating images",
                },
                "use_for_videos": {
                    "type": "boolean",
                    "description": "Use brand references when generating videos",
                },
            },
            "required": [],
        },
    },
]

# ─────────────────────────────────────────────────────────────────────────────
# Page Navigation Map — page_name → URL path
# ─────────────────────────────────────────────────────────────────────────────

PAGE_MAP: Dict[str, str] = {
    "dashboard":             "/dashboard",
    "create-post":           "/create-post/dashboard",
    "calendar":              "/calendar",
    "inbox":                 "/inbox/dashboard",
    "comments":              "/comments/dashboard",
    "notifications":         "/notifications",
    "analytics":             "/analytics/dashboard",
    "image-generator":       "/image-generator",
    "faceless-video":        "/faceless-video",
    "growth":                "/growth/dashboard",
    "email":                "/email",
    "email-marketing":       "/email?tab=campaigns",
    "intelligence":          "/intelligence/dashboard",
    "settings":              "/settings",
    "social-accounts":       "/connect/dashboard",
    "notification-settings": "/settings/notifications",
    "auto-reply":            "/settings/auto-reply",
    "tone":                  "/settings/tone",
    "knowledge":             "/settings/knowledge",
    "creative":              "/settings/creative",
    "email-inbox":           "/email?tab=inbox",
    "security":              "/settings/security",
    "billing":               "/billing",
    "alita-chat":            "/alita/chat",
}

# ─────────────────────────────────────────────────────────────────────────────
# Social Platform Connection Map — platform → OAuth initiation path
# ─────────────────────────────────────────────────────────────────────────────

PLATFORM_CONNECT_MAP: Dict[str, str] = {
    "facebook":  "/auth/start",          # Meta OAuth (covers FB + IG pages)
    "instagram": "/auth/start",          # Meta OAuth
    "twitter":   "/connect/late/twitter",
    "tiktok":    "/connect/late/tiktok",
    "linkedin":  "/connect/late/linkedin",
    "threads":   "/connect/late/threads",
    "youtube":   "/connect/late/youtube",
}

# ─────────────────────────────────────────────────────────────────────────────
# Tool Metadata — maps tool names to display, limit checks, descriptions
# ─────────────────────────────────────────────────────────────────────────────

TOOL_META: Dict[str, Dict[str, Any]] = {
    "create_content": {
        "display_name": "Create Content",
        "limit_metric": "posts_created",
        "feature_flag": None,
        "emoji": "\u270d\ufe0f",
        "description": "Generate a social media post",
        "action_type": "confirm",
    },
    "generate_image": {
        "display_name": "Generate Image",
        "limit_metric": "images_created",
        "feature_flag": None,
        "emoji": "\U0001f3a8",
        "description": "Create an AI-generated image",
        "action_type": "confirm",
    },
    "schedule_post": {
        "display_name": "Schedule Post",
        "limit_metric": "posts_created",
        "feature_flag": None,
        "emoji": "\U0001f4c5",
        "description": "Schedule a post for publishing",
        "action_type": "confirm",
    },
    "generate_calendar": {
        "display_name": "Generate Calendar",
        "limit_metric": "posts_created",
        "feature_flag": "calendar_agent",
        "emoji": "\U0001f5d3\ufe0f",
        "description": "Create a full content calendar",
        "action_type": "confirm",
    },
    "get_content_ideas": {
        "display_name": "Content Ideas",
        "limit_metric": None,
        "feature_flag": None,
        "emoji": "\U0001f4a1",
        "description": "Generate content ideas",
        "action_type": "confirm",
    },
    "get_growth_strategy": {
        "display_name": "Growth Strategy",
        "limit_metric": "growth_strategy",
        "feature_flag": None,
        "emoji": "\U0001f680",
        "description": "Generate a growth strategy",
        "action_type": "confirm",
    },
    "get_analytics": {
        "display_name": "Analytics Summary",
        "limit_metric": None,
        "feature_flag": "advanced_analytics",
        "emoji": "\U0001f4ca",
        "description": "Analyze your performance metrics",
        "action_type": "confirm",
    },
    "get_optimal_times": {
        "display_name": "Best Posting Times",
        "limit_metric": None,
        "feature_flag": "recommended_times",
        "emoji": "\u23f0",
        "description": "Find optimal posting times",
        "action_type": "confirm",
    },
    # ── Navigation / Connection / Settings tools ──
    "navigate_to_page": {
        "display_name": "Go to Page",
        "limit_metric": None,
        "feature_flag": None,
        "emoji": "\U0001f517",
        "description": "Navigate to a page",
        "action_type": "navigate",
    },
    "connect_social_account": {
        "display_name": "Connect Account",
        "limit_metric": None,
        "feature_flag": None,
        "emoji": "\U0001f310",
        "description": "Connect a social media account",
        "action_type": "navigate",
    },
    "toggle_notification_email": {
        "display_name": "Notification Toggle",
        "limit_metric": None,
        "feature_flag": None,
        "emoji": "\U0001f514",
        "description": "Toggle email notification",
        "action_type": "instant",
    },
    "toggle_auto_reply": {
        "display_name": "Auto-Reply Toggle",
        "limit_metric": None,
        "feature_flag": None,
        "emoji": "\U0001f916",
        "description": "Toggle auto-reply",
        "action_type": "instant",
    },
    "set_tone_preset": {
        "display_name": "Set Tone",
        "limit_metric": None,
        "feature_flag": None,
        "emoji": "\U0001f3a4",
        "description": "Change tone preset",
        "action_type": "confirm",
    },
    "toggle_humor": {
        "display_name": "Humor Toggle",
        "limit_metric": None,
        "feature_flag": None,
        "emoji": "\U0001f602",
        "description": "Toggle humor settings",
        "action_type": "instant",
    },
    "toggle_casual_conversation": {
        "display_name": "Casual Mode",
        "limit_metric": None,
        "feature_flag": None,
        "emoji": "\U0001f60e",
        "description": "Toggle casual conversation mode",
        "action_type": "instant",
    },
    "add_knowledge_entry": {
        "display_name": "Add Knowledge",
        "limit_metric": None,
        "feature_flag": None,
        "emoji": "\U0001f4da",
        "description": "Add to knowledge base",
        "action_type": "confirm",
    },
    "toggle_creative_prefs": {
        "display_name": "Creative Prefs",
        "limit_metric": None,
        "feature_flag": None,
        "emoji": "\U0001f3a8",
        "description": "Toggle creative style preferences",
        "action_type": "instant",
    },
}

# ─────────────────────────────────────────────────────────────────────────────
# Pending Actions Store (in-memory, per-user, 10-min TTL)
# ─────────────────────────────────────────────────────────────────────────────

_pending_actions: Dict[str, dict] = {}  # action_id -> {tool, params, client_id, user_id, created_at, optimizations}
_MAX_PENDING_AGE = 600  # 10 minutes


def store_pending(
    tool_name: str,
    params: dict,
    client_id: str,
    user_id: str,
    optimizations: List[str] = None,
    optimized_params: dict = None,
) -> str:
    """Store an action awaiting confirmation. Returns action_id."""
    # Expire any stale entries for this user
    _cleanup_user_pending(user_id)
    action_id = str(uuid.uuid4())[:12]
    _pending_actions[action_id] = {
        "tool": tool_name,
        "params": params,
        "optimized_params": optimized_params or params,
        "client_id": client_id,
        "user_id": user_id,
        "optimizations": optimizations or [],
        "created_at": time.time(),
    }
    return action_id


def pop_pending(action_id: str, user_id: str = "") -> Optional[dict]:
    """Pop a pending action. Returns None if expired, not found, or wrong owner."""
    entry = _pending_actions.get(action_id)
    if not entry:
        return None
    # Ownership check — must match the user who created the action
    if user_id and str(entry.get("user_id", "")) != str(user_id):
        return None
    # Actually pop it now that ownership is verified
    _pending_actions.pop(action_id, None)
    if time.time() - entry["created_at"] > _MAX_PENDING_AGE:
        return None
    return entry


def cancel_pending(action_id: str, user_id: str = "") -> bool:
    """Cancel a pending action. Returns True if it existed and belongs to user."""
    entry = _pending_actions.get(action_id)
    if not entry:
        return False
    # Ownership check
    if user_id and str(entry.get("user_id", "")) != str(user_id):
        return False
    _pending_actions.pop(action_id, None)
    return True


def _cleanup_user_pending(user_id: str):
    """Remove any stale or existing pending actions for this user."""
    now = time.time()
    to_remove = [
        k for k, v in _pending_actions.items()
        if v["user_id"] == user_id or now - v["created_at"] > _MAX_PENDING_AGE
    ]
    for k in to_remove:
        _pending_actions.pop(k, None)


# ─────────────────────────────────────────────────────────────────────────────
# Plan Limit Check
# ─────────────────────────────────────────────────────────────────────────────

def check_action_allowed(profile, tool_name: str) -> Tuple[bool, str]:
    """
    Check if the user's plan allows performing this action.
    Returns (allowed, error_message).
    """
    from utils.plan_limits import check_limit, has_feature_with_addons

    meta = TOOL_META.get(tool_name, {})
    tier = getattr(profile, "plan_tier", "free")

    # Feature flag check
    feature = meta.get("feature_flag")
    if feature:
        import json as _json
        addons_raw = getattr(profile, "active_addons", None) or "{}"
        try:
            active_addons = _json.loads(addons_raw) if isinstance(addons_raw, str) else (addons_raw or {})
        except Exception:
            active_addons = {}
        if not has_feature_with_addons(tier, feature, active_addons):
            from utils.plan_limits import PLAN_DISPLAY_NAMES
            tier_name = PLAN_DISPLAY_NAMES.get(tier, tier.title())
            return False, (
                f"Your {tier_name} plan doesn't include {meta.get('display_name', tool_name)}. "
                f"Upgrade your plan at /billing to unlock this feature."
            )

    # Usage limit check
    limit_metric = meta.get("limit_metric")
    if limit_metric:
        ok, msg = check_limit(profile, limit_metric)
        if not ok:
            return False, msg

    return True, ""


# ─────────────────────────────────────────────────────────────────────────────
# Smart Optimization Layer
# ─────────────────────────────────────────────────────────────────────────────

def optimize_params(
    tool_name: str,
    raw_params: dict,
    profile,
) -> Tuple[dict, List[str]]:
    """
    Enhance raw parameters before execution.
    Returns (optimized_params, optimization_notes).
    """
    params = dict(raw_params)  # copy
    notes: List[str] = []
    niche = getattr(profile, "niche", None) or getattr(profile, "business_type", None) or ""
    business_name = getattr(profile, "business_name", None) or ""

    if tool_name == "create_content":
        # Inject niche context into topic if not already present
        if niche and niche.lower() not in (params.get("topic") or "").lower():
            params["context"] = f"The client's business niche is: {niche}. Business: {business_name}."
            notes.append(f"Added business context ({niche})")
        # Default tone from client profile if not specified
        if not params.get("tone"):
            params["tone"] = "professional yet engaging"
            notes.append("Set professional tone as default")

    elif tool_name == "generate_image":
        prompt = params.get("prompt", "")
        # Enrich with composition/lighting details
        enhancements = []
        if "lighting" not in prompt.lower():
            enhancements.append("professional lighting")
        if "composition" not in prompt.lower() and "layout" not in prompt.lower():
            enhancements.append("clean composition")
        if "quality" not in prompt.lower() and "resolution" not in prompt.lower():
            enhancements.append("high quality")
        if enhancements:
            params["prompt"] = f"{prompt}, {', '.join(enhancements)}"
            notes.append(f"Enhanced prompt with {', '.join(enhancements)}")
        # Auto-size for platform
        platform = params.get("platform")
        if platform and not params.get("size"):
            sizes = {
                "instagram": "1080x1080",
                "facebook": "1200x630",
                "tiktok": "1080x1920",
                "twitter": "1200x675",
                "linkedin": "1200x627",
            }
            params["size"] = sizes.get(platform, "1080x1080")
            notes.append(f"Auto-sized to {params['size']} for {platform}")

    elif tool_name == "schedule_post":
        # If no scheduled_time, note that we'll suggest optimal time
        if not params.get("scheduled_time"):
            notes.append("Will suggest optimal posting time")
        # Inject topic from caption if not set
        if not params.get("topic") and params.get("caption"):
            params["topic"] = params["caption"][:80]

    elif tool_name == "generate_calendar":
        # Default name if not set
        if not params.get("name"):
            week = datetime.utcnow().strftime("%B Week %W")
            params["name"] = f"{business_name} \u2014 {week}" if business_name else week
            notes.append(f"Named calendar '{params['name']}'")
        # Default platforms from connected accounts
        if not params.get("platforms"):
            try:
                from database.db import SessionLocal
                from database.models import SocialAccount
                _db = SessionLocal()
                try:
                    cid = getattr(profile, "client_id", "")
                    accs = _db.query(SocialAccount.platform).filter(
                        SocialAccount.client_id == cid
                    ).distinct().all()
                    if accs:
                        params["platforms"] = [a[0] for a in accs]
                        notes.append(f"Using {len(params['platforms'])} connected platforms")
                finally:
                    _db.close()
            except Exception:
                params["platforms"] = ["instagram"]
                notes.append("Defaulted to Instagram")

    elif tool_name == "get_content_ideas":
        # Inject niche
        if niche:
            params["_niche"] = niche
            notes.append(f"Targeting {niche} niche")

    elif tool_name == "get_growth_strategy":
        # Inject business type from profile
        if niche:
            params["business_type"] = niche
            notes.append(f"Applied business context ({niche})")
        if not params.get("current_situation"):
            params["current_situation"] = f"Using Alita AI platform for social media management"

    return params, notes


# ─────────────────────────────────────────────────────────────────────────────
# Confirmation Summary Builder
# ─────────────────────────────────────────────────────────────────────────────

def build_confirmation_summary(tool_name: str, params: dict, optimizations: List[str]) -> dict:
    """
    Build a structured confirmation summary for the frontend.
    Returns a dict with keys: tool, display_name, emoji, summary_lines, optimizations.
    """
    meta = TOOL_META.get(tool_name, {})
    lines: List[dict] = []  # [{label, value}]

    if tool_name == "create_content":
        lines.append({"label": "Topic", "value": params.get("topic", "\u2014")})
        lines.append({"label": "Platform", "value": (params.get("platform") or "\u2014").title()})
        if params.get("content_type"):
            lines.append({"label": "Type", "value": params["content_type"].replace("_", " ").title()})
        if params.get("tone"):
            lines.append({"label": "Tone", "value": params["tone"].title()})

    elif tool_name == "generate_image":
        prompt = params.get("prompt", "\u2014")
        lines.append({"label": "Description", "value": prompt[:120] + ("..." if len(prompt) > 120 else "")})
        if params.get("platform"):
            lines.append({"label": "Platform", "value": params["platform"].title()})
        if params.get("size"):
            lines.append({"label": "Size", "value": params["size"]})
        if params.get("style"):
            lines.append({"label": "Style", "value": params["style"].title()})

    elif tool_name == "schedule_post":
        caption = params.get("caption", "\u2014")
        lines.append({"label": "Caption", "value": caption[:100] + ("..." if len(caption) > 100 else "")})
        lines.append({"label": "Platform", "value": (params.get("platform") or "\u2014").title()})
        if params.get("scheduled_time"):
            lines.append({"label": "Time", "value": params["scheduled_time"]})
        else:
            lines.append({"label": "Time", "value": "Will suggest optimal time"})

    elif tool_name == "generate_calendar":
        lines.append({"label": "Duration", "value": f"{params.get('duration_days', 7)} days"})
        if params.get("platforms"):
            lines.append({"label": "Platforms", "value": ", ".join(p.title() for p in params["platforms"])})
        if params.get("themes"):
            lines.append({"label": "Themes", "value": ", ".join(params["themes"][:3])})

    elif tool_name == "get_content_ideas":
        lines.append({"label": "Ideas", "value": f"{params.get('num_ideas', 5)} ideas"})
        if params.get("platforms"):
            lines.append({"label": "Platforms", "value": ", ".join(p.title() for p in params["platforms"])})
        if params.get("themes"):
            lines.append({"label": "Themes", "value": ", ".join(params["themes"][:3])})

    elif tool_name == "get_growth_strategy":
        lines.append({"label": "Goal", "value": params.get("goal", "\u2014")})
        lines.append({"label": "Budget", "value": (params.get("budget") or "low").title()})
        lines.append({"label": "Timeline", "value": params.get("timeline", "90 days")})

    elif tool_name == "get_analytics":
        period_labels = {"7d": "Last 7 days", "30d": "Last 30 days", "90d": "Last 90 days"}
        lines.append({"label": "Period", "value": period_labels.get(params.get("period", "30d"), "Last 30 days")})

    elif tool_name == "get_optimal_times":
        lines.append({"label": "Platform", "value": (params.get("platform") or "\u2014").title()})

    return {
        "tool": tool_name,
        "display_name": meta.get("display_name", tool_name),
        "emoji": meta.get("emoji", "\u2728"),
        "summary_lines": lines,
        "optimizations": optimizations,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Action Execution Engine (async generator yielding SSE events)
# ─────────────────────────────────────────────────────────────────────────────

async def execute_action(
    tool_name: str,
    params: dict,
    client_id: str,
    profile,
    db,
) -> AsyncGenerator[dict, None]:
    """
    Execute an agent action. Yields dicts for SSE events:
      {"status": "progress", "message": "..."}
      {"status": "complete", "result": {...}, "result_type": "..."}
      {"status": "error", "message": "..."}
    """
    meta = TOOL_META.get(tool_name, {})

    try:
        if tool_name == "create_content":
            yield {"status": "progress", "message": "Generating your content..."}
            result = await _exec_create_content(params, client_id, profile, db)
            yield {"status": "complete", "result": result, "result_type": "content"}

        elif tool_name == "generate_image":
            yield {"status": "progress", "message": "Creating your image with AI..."}
            result = await _exec_generate_image(params, client_id, profile, db)
            yield {"status": "complete", "result": result, "result_type": "image"}

        elif tool_name == "schedule_post":
            yield {"status": "progress", "message": "Scheduling your post..."}
            result = await _exec_schedule_post(params, client_id, profile, db)
            yield {"status": "complete", "result": result, "result_type": "schedule"}

        elif tool_name == "generate_calendar":
            yield {"status": "progress", "message": "Building your content calendar..."}
            yield {"status": "progress", "message": "Generating topics and captions..."}
            result = await _exec_generate_calendar(params, client_id, profile, db)
            yield {"status": "complete", "result": result, "result_type": "calendar"}

        elif tool_name == "get_content_ideas":
            yield {"status": "progress", "message": "Researching trending content ideas..."}
            result = await _exec_get_content_ideas(params, client_id, profile)
            yield {"status": "complete", "result": result, "result_type": "ideas"}

        elif tool_name == "get_growth_strategy":
            yield {"status": "progress", "message": "Analyzing growth opportunities..."}
            result = await _exec_get_growth_strategy(params, client_id, profile)
            yield {"status": "complete", "result": result, "result_type": "strategy"}

        elif tool_name == "get_analytics":
            yield {"status": "progress", "message": "Gathering your analytics data..."}
            result = await _exec_get_analytics(params, client_id, profile)
            yield {"status": "complete", "result": result, "result_type": "analytics"}

        elif tool_name == "get_optimal_times":
            yield {"status": "progress", "message": "Calculating best posting times..."}
            result = await _exec_get_optimal_times(params, client_id, profile)
            yield {"status": "complete", "result": result, "result_type": "times"}

        # ── Settings tools (executed inline but also callable via execute_action) ──
        elif tool_name == "toggle_notification_email":
            result = await _exec_toggle_notification_email(params, client_id, profile, db)
            yield {"status": "complete", "result": result, "result_type": "setting"}

        elif tool_name == "toggle_auto_reply":
            result = await _exec_toggle_auto_reply(params, client_id, profile, db)
            yield {"status": "complete", "result": result, "result_type": "setting"}

        elif tool_name == "set_tone_preset":
            yield {"status": "progress", "message": "Updating your tone preset..."}
            result = await _exec_set_tone_preset(params, client_id, profile, db)
            yield {"status": "complete", "result": result, "result_type": "setting"}

        elif tool_name == "toggle_humor":
            result = await _exec_toggle_humor(params, client_id, profile, db)
            yield {"status": "complete", "result": result, "result_type": "setting"}

        elif tool_name == "toggle_casual_conversation":
            result = await _exec_toggle_casual_conversation(params, client_id, profile, db)
            yield {"status": "complete", "result": result, "result_type": "setting"}

        elif tool_name == "add_knowledge_entry":
            yield {"status": "progress", "message": "Adding to your knowledge base..."}
            result = await _exec_add_knowledge_entry(params, client_id, profile, db)
            yield {"status": "complete", "result": result, "result_type": "setting"}

        elif tool_name == "toggle_creative_prefs":
            result = await _exec_toggle_creative_prefs(params, client_id, profile, db)
            yield {"status": "complete", "result": result, "result_type": "setting"}

        else:
            yield {"status": "error", "message": f"Unknown action: {tool_name}"}

    except Exception as e:
        print(f"[AlitaRouter] Action {tool_name} failed: {e}")
        import traceback
        traceback.print_exc()
        yield {"status": "error", "message": f"Something went wrong: {str(e)[:200]}"}


# ─────────────────────────────────────────────────────────────────────────────
# Individual Action Executors
# ─────────────────────────────────────────────────────────────────────────────

async def _exec_create_content(params: dict, client_id: str, profile, db) -> dict:
    from agents.content_agent import ContentCreationAgent, ContentRequest

    agent = ContentCreationAgent(client_id=client_id)
    request = ContentRequest(
        content_type=params.get("content_type", "post"),
        platform=params.get("platform", "instagram"),
        topic=params.get("topic", ""),
        context=params.get("context", ""),
        tone=params.get("tone", ""),
        include_hashtags=params.get("include_hashtags", True),
        include_cta=params.get("include_cta", True),
    )
    result = await agent.generate_content(request)

    # Increment usage
    from utils.plan_limits import increment_usage
    increment_usage(profile, "posts_created", db)

    return {
        "caption": result.content,
        "hashtags": result.hashtags or [],
        "platform": result.platform,
        "content_type": result.content_type,
        "word_count": result.word_count,
    }


async def _exec_generate_image(params: dict, client_id: str, profile, db) -> dict:
    from agents.image_generator import ImageGeneratorAgent

    agent = ImageGeneratorAgent(client_id=client_id)
    result = await agent.generate_image(
        prompt=params.get("prompt", ""),
        platform=params.get("platform"),
        style=params.get("style"),
        size=params.get("size", "1080x1080"),
    )

    if not result.success:
        raise Exception(result.error or "Image generation failed")

    # Usage increment is handled inside ImageGeneratorAgent.generate_image()

    return {
        "url": result.url,
        "api_used": result.api_used,
        "cost_estimate": result.cost_estimate,
    }


async def _exec_schedule_post(params: dict, client_id: str, profile, db) -> dict:
    from database.models import ScheduledPost

    # Parse scheduled time
    scheduled_time = None
    time_str = params.get("scheduled_time")
    if time_str:
        # Try ISO format first
        try:
            scheduled_time = datetime.fromisoformat(time_str.replace("Z", "+00:00"))
        except Exception:
            pass
        if not scheduled_time:
            # Try natural language parsing
            scheduled_time = _parse_natural_time(time_str)

    if not scheduled_time:
        # Default to next day at 10am UTC
        scheduled_time = datetime.utcnow().replace(
            hour=10, minute=0, second=0, microsecond=0
        ) + timedelta(days=1)

    post = ScheduledPost(
        client_id=client_id,
        platform=params.get("platform", "instagram"),
        caption=params.get("caption", ""),
        image_url=params.get("image_url"),
        content_type=params.get("content_type", "post"),
        scheduled_time=scheduled_time,
        topic=params.get("topic", ""),
        status="scheduled",
    )
    db.add(post)
    db.commit()
    db.refresh(post)

    from utils.plan_limits import increment_usage
    increment_usage(profile, "posts_created", db)

    return {
        "post_id": post.id,
        "platform": post.platform,
        "scheduled_time": scheduled_time.strftime("%B %d, %Y at %I:%M %p UTC"),
        "caption_preview": (post.caption or "")[:120],
    }


async def _exec_generate_calendar(params: dict, client_id: str, profile, db) -> dict:
    from agents.content_calendar_orchestrator import ContentCalendarOrchestrator

    tz = getattr(profile, "timezone", None) or "America/New_York"
    orch = ContentCalendarOrchestrator(client_id=client_id, timezone=tz)

    calendar = await orch.generate_calendar(
        name=params.get("name", "AI Calendar"),
        platforms=params.get("platforms"),
        duration_days=params.get("duration_days", 7),
        themes=params.get("themes"),
        auto_schedule=True,
    )

    # Count pieces
    pieces = getattr(calendar, "scheduled_content", []) or []
    platforms = set()
    for p in pieces:
        plat = getattr(p, "platform", None) or (p.get("platform") if isinstance(p, dict) else None)
        if plat:
            platforms.add(plat)

    return {
        "calendar_name": getattr(calendar, "name", "Calendar"),
        "total_posts": len(pieces),
        "platforms": list(platforms),
        "duration_days": params.get("duration_days", 7),
        "link": "/calendar",
    }


async def _exec_get_content_ideas(params: dict, client_id: str, profile) -> dict:
    from agents.marketing_intelligence_agent import MarketingIntelligenceAgent

    agent = MarketingIntelligenceAgent(client_id=client_id)
    niche = params.pop("_niche", None) or getattr(profile, "niche", None) or ""

    ideas = await agent.generate_content_ideas(
        niche=niche,
        num_ideas=params.get("num_ideas", 5),
        platforms=params.get("platforms"),
        goals=params.get("goals"),
        themes=params.get("themes"),
    )

    return {
        "ideas": [
            {
                "title": getattr(idea, "title", str(idea)),
                "description": getattr(idea, "description", ""),
                "platform": getattr(idea, "platform", ""),
                "content_type": getattr(idea, "content_type", ""),
            }
            for idea in (ideas or [])
        ],
    }


async def _exec_get_growth_strategy(params: dict, client_id: str, profile) -> dict:
    from agents.growth_hacking_agent import GrowthHackingAgent
    import uuid as _uuid

    agent = GrowthHackingAgent(client_id=client_id)
    niche = getattr(profile, "niche", None) or ""

    strategy = await agent.generate_strategy(
        business_type=params.get("business_type", niche or "small business"),
        current_situation=params.get("current_situation", "Growing social media presence"),
        goal=params.get("goal", "Increase followers and engagement"),
        budget=params.get("budget", "low"),
        timeline=params.get("timeline", "90 days"),
        niche=niche,
    )

    # ── Persist to PostgreSQL so reports survive redeploys ─────────────────
    try:
        from api.growth_routes import _save_report_to_db
        from datetime import datetime
        report_id = _uuid.uuid4().hex[:12]
        strategy["report_id"]  = report_id
        strategy["client_id"]  = client_id
        strategy["created_at"] = datetime.utcnow().isoformat()
        _save_report_to_db(
            report_id, client_id,
            params.get("goal", "Increase followers and engagement"),
            strategy,
        )
    except Exception as exc:
        import logging
        logging.getLogger(__name__).warning(
            f"[{client_id}] chat growth strategy DB save failed: {exc}"
        )

    return {
        "positioning": strategy.get("positioning_angle", ""),
        "quick_wins": strategy.get("quick_wins", [])[:5],
        "medium_term": strategy.get("medium_term", [])[:3],
        "contrarian_insight": strategy.get("contrarian_insight", ""),
        "roi_estimate": strategy.get("roi_estimate", ""),
    }


async def _exec_get_analytics(params: dict, client_id: str, profile) -> dict:
    from agents.analytics_agent import AnalyticsAgent

    agent = AnalyticsAgent(client_id=client_id)

    # Try to collect real metrics
    ig_creds = None
    fb_creds = None
    try:
        from database.db import SessionLocal
        from database.models import SocialAccount
        _db = SessionLocal()
        try:
            accounts = _db.query(SocialAccount).filter(
                SocialAccount.client_id == client_id
            ).all()
            for acc in accounts:
                if acc.platform == "instagram" and acc.access_token:
                    ig_creds = {"ig_user_id": acc.platform_user_id, "access_token": acc.access_token}
                elif acc.platform == "facebook" and acc.access_token:
                    fb_creds = {"page_id": acc.platform_user_id, "page_token": acc.access_token}
        finally:
            _db.close()
    except Exception:
        pass

    try:
        report = await agent.generate_report(
            instagram_credentials=ig_creds,
            facebook_credentials=fb_creds,
        )
        aggregates = report.aggregates if hasattr(report, "aggregates") else {}
        insights = report.insights if hasattr(report, "insights") else []
        recommendations = report.recommendations if hasattr(report, "recommendations") else []
    except Exception:
        aggregates = {}
        insights = ["Connect your social accounts for detailed analytics."]
        recommendations = ["Go to Social Accounts settings to connect platforms."]

    return {
        "aggregates": aggregates if isinstance(aggregates, dict) else {},
        "insights": insights[:5] if isinstance(insights, list) else [],
        "recommendations": recommendations[:3] if isinstance(recommendations, list) else [],
        "link": "/analytics/dashboard",
    }


async def _exec_get_optimal_times(params: dict, client_id: str, profile) -> dict:
    from agents.calendar_agent import CalendarAgent

    tz = getattr(profile, "timezone", None) or "America/New_York"
    niche = getattr(profile, "niche", None) or ""
    agent = CalendarAgent(client_id=client_id, profile=profile)

    result = await agent.get_optimal_posting_times(
        platform=params.get("platform", "instagram"),
        timezone=tz,
        niche=niche,
    )

    return {
        "platform": params.get("platform", "instagram"),
        "recommended_times": result.get("recommended_times", []),
        "best_days": result.get("best_days", []),
        "posting_frequency": result.get("posting_frequency", ""),
        "insights": result.get("insights", ""),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Utility: parse natural language time
# ─────────────────────────────────────────────────────────────────────────────

def _parse_natural_time(text: str) -> Optional[datetime]:
    """Attempt to parse natural language time references."""
    text_lower = text.lower().strip()
    now = datetime.utcnow()

    # "tomorrow at Xam/pm"
    if "tomorrow" in text_lower:
        base = now + timedelta(days=1)
        return _extract_hour(text_lower, base)

    # "next monday/tuesday/etc at X"
    days = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
    for i, day in enumerate(days):
        if day in text_lower:
            days_ahead = (i - now.weekday()) % 7
            if days_ahead == 0:
                days_ahead = 7
            base = now + timedelta(days=days_ahead)
            return _extract_hour(text_lower, base)

    return None


def _extract_hour(text: str, base: datetime) -> datetime:
    """Extract hour from text like '10am', '2pm', '3:30 pm'."""
    import re
    match = re.search(r'(\d{1,2})(?::(\d{2}))?\s*(am|pm)', text)
    if match:
        hour = int(match.group(1))
        minute = int(match.group(2) or 0)
        period = match.group(3)
        if period == "pm" and hour != 12:
            hour += 12
        elif period == "am" and hour == 12:
            hour = 0
        return base.replace(hour=hour, minute=minute, second=0, microsecond=0)
    return base.replace(hour=10, minute=0, second=0, microsecond=0)


# ─────────────────────────────────────────────────────────────────────────────
# Settings Executor Functions
# ─────────────────────────────────────────────────────────────────────────────

async def _exec_toggle_notification_email(params: dict, client_id: str, profile, db) -> dict:
    """Toggle a single email notification type on/off."""
    notif_type = params.get("notification_type", "")
    enabled = params.get("enabled", True)

    prefs_raw = getattr(profile, "notification_email_prefs_json", None) or "{}"
    try:
        prefs = json.loads(prefs_raw) if isinstance(prefs_raw, str) else (prefs_raw or {})
    except Exception:
        prefs = {}

    prefs[notif_type] = enabled
    profile.notification_email_prefs_json = json.dumps(prefs)
    db.commit()

    state = "enabled" if enabled else "disabled"
    label = notif_type.replace("_", " ").title()
    return {"message": f"{label} email notifications {state}.", "type": notif_type, "enabled": enabled}


async def _exec_toggle_auto_reply(params: dict, client_id: str, profile, db) -> dict:
    """Toggle auto-reply on/off for a platform."""
    platform = params.get("platform", "instagram")
    enabled = params.get("enabled", True)

    ar_dir = "storage/auto_reply"
    ar_path = os.path.join(ar_dir, f"{client_id}.json")
    try:
        if os.path.exists(ar_path):
            with open(ar_path) as f:
                ar_prefs = json.load(f)
        else:
            ar_prefs = {"platforms": {}}
    except Exception:
        ar_prefs = {"platforms": {}}

    if platform not in ar_prefs.get("platforms", {}):
        ar_prefs.setdefault("platforms", {})[platform] = {
            "enabled": False, "comments": True, "dms": True,
            "delay_minutes": 1, "fallback_message": "",
        }
    ar_prefs["platforms"][platform]["enabled"] = enabled

    os.makedirs(ar_dir, exist_ok=True)
    with open(ar_path, "w") as f:
        json.dump(ar_prefs, f, indent=2)

    state = "enabled" if enabled else "disabled"
    return {"message": f"Auto-reply for {platform.title()} {state}.", "platform": platform, "enabled": enabled}


async def _exec_set_tone_preset(params: dict, client_id: str, profile, db) -> dict:
    """Change the tone preset."""
    preset = params.get("preset", "professional")

    PRESET_TONES = {
        "professional": {"system": "Write in a professional, polished tone.", "label": "Professional"},
        "conversational": {"system": "Write in a warm, conversational tone.", "label": "Conversational"},
        "playful": {"system": "Write in a playful, fun tone.", "label": "Playful"},
        "educational": {"system": "Write in an educational, informative tone.", "label": "Educational"},
        "bold": {"system": "Write in a bold, confident tone.", "label": "Bold"},
        "empathetic": {"system": "Write in an empathetic, understanding tone.", "label": "Empathetic"},
    }

    if preset not in PRESET_TONES:
        return {"message": f"Unknown preset: {preset}. Choose from: {', '.join(PRESET_TONES.keys())}"}

    prefs_raw = getattr(profile, "tone_preferences_json", None) or "{}"
    try:
        prefs = json.loads(prefs_raw) if isinstance(prefs_raw, str) else (prefs_raw or {})
    except Exception:
        prefs = {}

    prefs["preset"] = preset
    prefs["system_prompt"] = PRESET_TONES[preset]["system"]
    prefs["label"] = PRESET_TONES[preset]["label"]
    prefs["updated_at"] = datetime.utcnow().isoformat()

    profile.tone_preferences_json = json.dumps(prefs)
    if not getattr(profile, "tone_configured", False):
        profile.tone_configured = True
    db.commit()

    # Also write filesystem cache
    try:
        style_dir = f"style_references/{client_id}"
        os.makedirs(style_dir, exist_ok=True)
        with open(os.path.join(style_dir, "tone_prefs.json"), "w") as f:
            json.dump(prefs, f, indent=2)
    except Exception:
        pass

    return {"message": f"Tone preset changed to **{PRESET_TONES[preset]['label']}**.", "preset": preset}


async def _exec_toggle_humor(params: dict, client_id: str, profile, db) -> dict:
    """Toggle humor on/off and optionally set intensity."""
    enabled = params.get("enabled", True)
    intensity = params.get("intensity", "balanced")

    prefs_raw = getattr(profile, "tone_preferences_json", None) or "{}"
    try:
        prefs = json.loads(prefs_raw) if isinstance(prefs_raw, str) else (prefs_raw or {})
    except Exception:
        prefs = {}

    prefs.setdefault("humor", {})
    prefs["humor"]["enabled"] = enabled
    if enabled:
        prefs["humor"]["intensity"] = intensity
    prefs["updated_at"] = datetime.utcnow().isoformat()

    profile.tone_preferences_json = json.dumps(prefs)
    db.commit()

    if enabled:
        return {"message": f"Humor **enabled** at **{intensity}** intensity.", "enabled": True, "intensity": intensity}
    return {"message": "Humor **disabled**.", "enabled": False}


async def _exec_toggle_casual_conversation(params: dict, client_id: str, profile, db) -> dict:
    """Toggle casual conversation mode."""
    enabled = params.get("enabled", True)

    prefs_raw = getattr(profile, "tone_preferences_json", None) or "{}"
    try:
        prefs = json.loads(prefs_raw) if isinstance(prefs_raw, str) else (prefs_raw or {})
    except Exception:
        prefs = {}

    prefs["casual_conversation"] = {"enabled": enabled}
    prefs["updated_at"] = datetime.utcnow().isoformat()

    profile.tone_preferences_json = json.dumps(prefs)
    db.commit()

    state = "enabled" if enabled else "disabled"
    return {"message": f"Casual conversation mode **{state}**.", "enabled": enabled}


async def _exec_add_knowledge_entry(params: dict, client_id: str, profile, db) -> dict:
    """Add an entry to the client's knowledge base."""
    text = params.get("text", "").strip()
    label = params.get("label", "Alita Chat").strip()

    if not text:
        return {"message": "No text provided to add."}

    try:
        from database.models import ClientKnowledgeEntry
        entry = ClientKnowledgeEntry(
            client_id=client_id,
            text=text,
            source="alita_chat",
            category=label,
        )
        db.add(entry)
        db.commit()
    except Exception as e:
        print(f"[AlitaRouter] Knowledge add DB error: {e}")

    # Also try RAG ingest
    try:
        from agents.knowledge_base import add_client_knowledge
        add_client_knowledge(client_id, text, source="alita_chat", label=label)
    except Exception:
        pass

    preview = text[:80] + ("..." if len(text) > 80 else "")
    return {"message": f"Added to knowledge base: \"{preview}\"", "label": label}


async def _exec_toggle_creative_prefs(params: dict, client_id: str, profile, db) -> dict:
    """Toggle creative reference preferences."""
    prefs_raw = getattr(profile, "creative_preferences_json", None) or "{}"
    try:
        prefs = json.loads(prefs_raw) if isinstance(prefs_raw, str) else (prefs_raw or {})
    except Exception:
        prefs = {}

    if "use_for_images" in params:
        prefs["use_for_images"] = params["use_for_images"]
    if "use_for_videos" in params:
        prefs["use_for_videos"] = params["use_for_videos"]

    profile.creative_preferences_json = json.dumps(prefs)
    db.commit()

    parts = []
    if "use_for_images" in params:
        parts.append(f"images: {'ON' if params['use_for_images'] else 'OFF'}")
    if "use_for_videos" in params:
        parts.append(f"videos: {'ON' if params['use_for_videos'] else 'OFF'}")
    return {"message": f"Brand reference usage updated — {', '.join(parts)}.", "prefs": prefs}


# ─────────────────────────────────────────────────────────────────────────────
# Connected Platforms Context (injected into Alita system prompt)
# ─────────────────────────────────────────────────────────────────────────────

def build_connected_platforms_block(client_id: str) -> str:
    """
    Build a context string listing the client's connected social platforms
    and their connection timestamps for Alita's system prompt.
    """
    if not client_id:
        return ""

    platforms = []

    # 1. Meta (Facebook / Instagram) via MetaOAuthToken
    try:
        from database.db import SessionLocal
        from database.models import ClientProfile as _CP
        _db = SessionLocal()
        try:
            _prof = _db.query(_CP).filter(_CP.client_id == client_id).first()
            if _prof:
                ig_user = getattr(_prof, "meta_ig_username", None)
                meta_at = getattr(_prof, "meta_connected_at", None)
                if ig_user:
                    age = _format_time_ago(meta_at) if meta_at else "unknown time ago"
                    platforms.append(f"Instagram (@{ig_user}, connected {age})")
                fb_page = getattr(_prof, "meta_facebook_page_id", None)
                if fb_page:
                    age = _format_time_ago(meta_at) if meta_at else "unknown time ago"
                    platforms.append(f"Facebook (Page ID {fb_page}, connected {age})")
        finally:
            _db.close()
    except Exception:
        pass

    # 2. Late API platforms (PlatformConnection table)
    try:
        from database.db import SessionLocal
        from database.models import PlatformConnection
        _db = SessionLocal()
        try:
            conns = _db.query(PlatformConnection).filter(
                PlatformConnection.client_id == client_id
            ).all()
            for conn in conns:
                name = (conn.platform or "").title()
                user = conn.username or ""
                age = _format_time_ago(conn.connected_at) if conn.connected_at else "unknown time ago"
                label = f"{name}"
                if user:
                    label += f" (@{user})"
                label += f", connected {age}"
                platforms.append(label)
        finally:
            _db.close()
    except Exception:
        pass

    if not platforms:
        return (
            "\n\n=== CONNECTED PLATFORMS ===\n"
            "No social accounts connected yet. If the client wants to connect one, "
            "use the connect_social_account tool.\n"
            "=== END CONNECTED PLATFORMS ===\n"
        )

    listing = "\n".join(f"  - {p}" for p in platforms)
    return (
        "\n\n=== CONNECTED PLATFORMS ===\n"
        f"The client has these social accounts connected:\n{listing}\n\n"
        "If a platform was connected very recently (within the last few minutes), "
        "congratulate the client on connecting it! Say something like "
        "'Welcome back!' or 'Congratulations on connecting [platform]!'\n"
        "=== END CONNECTED PLATFORMS ===\n"
    )


def _format_time_ago(dt_val) -> str:
    """Format a datetime as a human-readable time-ago string."""
    if not dt_val:
        return "unknown time ago"
    try:
        now = datetime.utcnow()
        if hasattr(dt_val, "replace") and dt_val.tzinfo:
            dt_val = dt_val.replace(tzinfo=None)
        diff = now - dt_val
        seconds = diff.total_seconds()
        if seconds < 60:
            return "just now"
        if seconds < 3600:
            mins = int(seconds / 60)
            return f"{mins} minute{'s' if mins != 1 else ''} ago"
        if seconds < 86400:
            hrs = int(seconds / 3600)
            return f"{hrs} hour{'s' if hrs != 1 else ''} ago"
        if seconds < 604800:
            days = int(seconds / 86400)
            return f"{days} day{'s' if days != 1 else ''} ago"
        weeks = int(seconds / 604800)
        if weeks < 5:
            return f"{weeks} week{'s' if weeks != 1 else ''} ago"
        months = int(seconds / 2592000)
        return f"{months} month{'s' if months != 1 else ''} ago"
    except Exception:
        return "some time ago"


# ─────────────────────────────────────────────────────────────────────────────
# Instant Settings Executor (called from chat() for action_type=instant)
# ─────────────────────────────────────────────────────────────────────────────

def execute_instant_setting(tool_name: str, params: dict, client_id: str, profile, db) -> dict:
    """
    Synchronously execute an instant settings action.
    Returns a result dict with a 'message' key.
    """
    import asyncio

    _executors = {
        "toggle_notification_email": _exec_toggle_notification_email,
        "toggle_auto_reply": _exec_toggle_auto_reply,
        "toggle_humor": _exec_toggle_humor,
        "toggle_casual_conversation": _exec_toggle_casual_conversation,
        "toggle_creative_prefs": _exec_toggle_creative_prefs,
    }

    executor = _executors.get(tool_name)
    if not executor:
        return {"message": f"Unknown instant action: {tool_name}"}

    # Run the async executor synchronously
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # We're inside an async context — use a new thread
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                result = pool.submit(
                    asyncio.run, executor(params, client_id, profile, db)
                ).result(timeout=10)
        else:
            result = asyncio.run(executor(params, client_id, profile, db))
    except Exception as e:
        print(f"[AlitaRouter] Instant setting {tool_name} error: {e}")
        result = {"message": "Sorry, I had trouble updating that setting. Please try again."}

    return result
