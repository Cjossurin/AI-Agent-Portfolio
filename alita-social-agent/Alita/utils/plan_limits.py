"""
utils/plan_limits.py — Single source of truth for plan feature limits.

Usage:
    from utils.plan_limits import PLANS, get_limits, check_limit, PLAN_ORDER

    limits = get_limits("growth")
    ok, msg = check_limit(profile, "images_created")
"""
from __future__ import annotations
import os
import json as _json
from typing import Any

# ── Plan ordering (used for "at least X" comparisons) ─────────────────────────
PLAN_ORDER = ["free", "starter", "growth", "pro"]

# ── Platforms actually built in this codebase ─────────────────────────────────
# Meta (direct API): Instagram, Facebook
# Late API: TikTok, Twitter/X, LinkedIn, Threads, YouTube
ALL_PLATFORMS = ["instagram", "facebook", "tiktok", "twitter", "linkedin", "threads", "youtube"]

PLAN_PLATFORMS = {
    "free":    ["instagram", "facebook"],
    "starter": ["instagram", "facebook", "tiktok", "twitter"],
    "growth":  ["instagram", "facebook", "tiktok", "twitter", "linkedin", "threads"],
    "pro":     ["instagram", "facebook", "tiktok", "twitter", "linkedin", "threads", "youtube"],
    # Pro also gets all FUTURE platforms added automatically
}

PLATFORM_DISPLAY = {
    "instagram": "Instagram",
    "facebook":  "Facebook",
    "tiktok":    "TikTok",
    "twitter":   "Twitter / X",
    "linkedin":  "LinkedIn",
    "threads":   "Threads",
    "youtube":   "YouTube",
}


def plan_rank(tier: str) -> int:
    try:
        return PLAN_ORDER.index(tier)
    except ValueError:
        return 0


def is_at_least(tier: str, minimum: str) -> bool:
    return plan_rank(tier) >= plan_rank(minimum)


# ── Feature limits per plan  (-1 = unlimited) ────────────────────────────────
# Key names must match the usage_* columns on ClientProfile (without "usage_" prefix)
# plus "social_accounts" (not usage-tracked, just a cap in the DB check).

PLANS: dict[str, dict[str, Any]] = {
    "free": {
        # ── Hard limits ──────────────────────────────────────────
        "social_accounts":   2,     # Instagram + Facebook only
        "posts_created":     5,     # AI posts/mo
        "images_created":    3,     # AI images/mo (budget tier)
        "videos_created":    0,     # no faceless videos
        "replies_sent":      20,    # AI engagement replies/mo
        "campaigns_sent":    0,     # no email campaigns
        "research_run":      0,     # no deep research
        "competitive_research": 0,
        "growth_strategy":   0,
        # ── Feature flags ────────────────────────────────────────
        "calendar_agent":        False,
        "recommended_times":     False,
        "seo_keywords":          False,
        "platform_optimized":    False,
        "premium_images":        False,
        "ai_animation":          False,
        "voice_clone":           False,
        "auto_dm_reply":         False,
        "auto_comment_reply":    False,
        "email_support_agent":   False,
        "campaign_analytics":    False,
        "trend_intelligence":    False,
        "sms_notifications":     False,
        "advanced_analytics":    False,
        "youtube_access":        False,
        "support_level":         "community",
        "platforms":             ["instagram", "facebook"],
        "future_platforms":      False,
    },
    "starter": {
        # ── Hard limits ──────────────────────────────────────────
        "social_accounts":   4,     # Instagram, Facebook, TikTok, Twitter/X
        "posts_created":     30,
        "images_created":    15,
        "videos_created":    1,     # 1 faceless video/mo
        "replies_sent":      150,
        "campaigns_sent":    2,
        "research_run":      0,
        "competitive_research":  3,
        "growth_strategy":       1,
        # ── Feature flags ────────────────────────────────────────
        "calendar_agent":        True,
        "recommended_times":     True,
        "seo_keywords":          True,
        "platform_optimized":    True,
        "premium_images":        False,
        "ai_animation":          False,
        "voice_clone":           True,   # digital voice clone / AI voiceover
        "auto_dm_reply":         True,
        "auto_comment_reply":    True,
        "email_support_agent":   False,
        "campaign_analytics":    True,
        "trend_intelligence":    True,
        "sms_notifications":     False,
        "advanced_analytics":    False,
        "youtube_access":        False,
        "support_level":         "in_app_chat",
        "platforms":             ["instagram", "facebook", "tiktok", "twitter"],
        "future_platforms":      False,
    },
    "growth": {
        # ── Hard limits ──────────────────────────────────────────
        "social_accounts":   6,     # Instagram, Facebook, TikTok, Twitter/X, LinkedIn, Threads
        "posts_created":     90,
        "images_created":    40,
        "videos_created":    5,     # 5 faceless videos/mo
        "replies_sent":      500,
        "campaigns_sent":    8,
        "research_run":      2,     # deep research sessions
        "competitive_research":  10,
        "growth_strategy":       4,
        # ── Feature flags ────────────────────────────────────────
        "calendar_agent":        True,
        "recommended_times":     True,
        "seo_keywords":          True,
        "platform_optimized":    True,
        "premium_images":        True,   # Midjourney / GoAPI
        "ai_animation":          False,
        "voice_clone":           True,
        "auto_dm_reply":         True,
        "auto_comment_reply":    True,
        "email_support_agent":   True,
        "campaign_analytics":    True,
        "trend_intelligence":    True,
        "sms_notifications":     True,
        "advanced_analytics":    True,   # full dashboard
        "youtube_access":        False,
        "support_level":         "priority_email",
        "platforms":             ["instagram", "facebook", "tiktok", "twitter", "linkedin", "threads"],
        "future_platforms":      False,
    },
    "pro": {
        # ── Hard limits ──────────────────────────────────────────
        "social_accounts":   -1,    # all 7 platforms + future = unlimited slots
        "posts_created":     -1,    # unlimited
        "images_created":    100,
        "videos_created":    15,    # tier 3 — AI animation enabled
        "replies_sent":      -1,
        "campaigns_sent":    -1,
        "research_run":      10,
        "competitive_research":  -1,
        "growth_strategy":       -1,
        # ── Feature flags ────────────────────────────────────────
        "calendar_agent":        True,
        "recommended_times":     True,
        "seo_keywords":          True,
        "platform_optimized":    True,
        "premium_images":        True,
        "ai_animation":          True,   # cinematic Kling animation
        "voice_clone":           True,
        "auto_dm_reply":         True,
        "auto_comment_reply":    True,
        "email_support_agent":   True,
        "campaign_analytics":    True,
        "trend_intelligence":    True,
        "sms_notifications":     True,
        "advanced_analytics":    True,
        "youtube_access":        True,
        "support_level":         "priority_slack",
        "platforms":             ["instagram", "facebook", "tiktok", "twitter", "linkedin", "threads", "youtube"],
        "future_platforms":      True,   # Pro gets every new platform automatically
    },
}


# ── Add-On Catalog ────────────────────────────────────────────────────────────
# Each add-on stacks on top of the base plan.
# "adds"    — increments a numeric limit by that amount per active addon purchase
# "unlocks" — sets a feature flag to True (regardless of base plan)
# Available to ALL plans including Free.

ADDONS: dict[str, dict[str, Any]] = {
    "post_boost": {
        "name":        "Post Boost Pack",
        "price":       39,
        "description": "+30 AI posts/mo",
        "adds":        {"posts_created": 30},
        "unlocks":     {},
        "stripe_price_env": "STRIPE_PRICE_ADDON_POST_BOOST",
        "stripe_prod_env":  "STRIPE_PROD_POST_BOOST",
    },
    "engagement_boost": {
        "name":        "Engagement Boost Pack",
        "price":       29,
        "description": "+250 AI engagement replies/mo",
        "adds":        {"replies_sent": 250},
        "unlocks":     {},
        "stripe_price_env": "STRIPE_PRICE_ADDON_ENGAGEMENT_BOOST",
        "stripe_prod_env":  "STRIPE_PROD_ENGAGEMENT_BOOST",
    },
    "video_boost": {
        "name":        "Video Boost Pack",
        "price":       39,
        "description": "+5 faceless videos/mo",
        "adds":        {"videos_created": 5},
        "unlocks":     {},
        "stripe_price_env": "STRIPE_PRICE_ADDON_VIDEO_BOOST",
        "stripe_prod_env":  "STRIPE_PROD_VIDEO_BOOST",
    },
    "ai_animation": {
        "name":        "AI Animation Pack",
        "price":       59,
        "description": "Unlocks cinematic AI animation (Kling) + 5 videos/mo",
        "adds":        {"videos_created": 5},
        "unlocks":     {"ai_animation": True, "voice_clone": True},
        "stripe_price_env": "STRIPE_PRICE_ADDON_AI_ANIMATION",
        "stripe_prod_env":  "STRIPE_PROD_AI_ANIMATION",
    },
    "premium_images": {
        "name":        "Premium Images Pack",
        "price":       29,
        "description": "+25 Midjourney/GoAPI images/mo",
        "adds":        {"images_created": 25},
        "unlocks":     {"premium_images": True},
        "stripe_price_env": "STRIPE_PRICE_ADDON_PREMIUM_IMAGES",
        "stripe_prod_env":  "STRIPE_PROD_PREMIUM_IMAGES",
    },
    "email_campaign": {
        "name":        "Email Campaign Boost",
        "price":       25,
        "description": "+5 email campaigns/mo",
        "adds":        {"campaigns_sent": 5},
        "unlocks":     {},
        "stripe_price_env": "STRIPE_PRICE_ADDON_EMAIL_CAMPAIGN",
        "stripe_prod_env":  "STRIPE_PROD_EMAIL_CAMPAIGN",
    },
    "growth_strategy": {
        "name":        "Growth Strategy Pack",
        "price":       49,
        "description": "+3 growth strategy sessions/mo",
        "adds":        {"growth_strategy": 3},
        "unlocks":     {},
        "stripe_price_env": "STRIPE_PRICE_ADDON_GROWTH_STRATEGY",
        "stripe_prod_env":  "STRIPE_PROD_GROWTH_STRATEGY",
    },
    "research_boost": {
        "name":        "Research Boost Pack",
        "price":       39,
        "description": "+5 deep research sessions/mo",
        "adds":        {"research_run": 5},
        "unlocks":     {},
        "stripe_price_env": "STRIPE_PRICE_ADDON_RESEARCH_BOOST",
        "stripe_prod_env":  "STRIPE_PROD_RESEARCH_BOOST",
    },
    "youtube_addon": {
        "name":        "YouTube Add-on",
        "price":       29,
        "description": "Unlocks YouTube posting",
        "adds":        {},
        "unlocks":     {"youtube_access": True},
        "stripe_price_env": "STRIPE_PRICE_ADDON_YOUTUBE",
        "stripe_prod_env":  "STRIPE_PROD_YOUTUBE_ADDON",
    },
    "account_expansion": {
        "name":        "Account Expansion Pack",
        "price":       25,
        "description": "+5 connected social accounts",
        "adds":        {"social_accounts": 5},
        "unlocks":     {},
        "stripe_price_env": "STRIPE_PRICE_ADDON_ACCOUNT_EXPANSION",
        "stripe_prod_env":  "STRIPE_PROD_ACCOUNT_EXPANSION",
    },
}

# Map Stripe product IDs → addon keys (used in webhook to identify which addon was purchased)
ADDON_PROD_TO_KEY: dict[str, str] = {}
for _key, _addon in ADDONS.items():
    _prod_id = os.getenv(_addon["stripe_prod_env"], "")
    if _prod_id:
        ADDON_PROD_TO_KEY[_prod_id] = _key

# ── Monthly pricing (base, in USD) ─────────────────────────────────────────
PLAN_PRICE_MONTHLY = {
    "free":    0,
    "starter": 97,
    "growth":  197,
    "pro":     397,
}

PLAN_PRICE_ANNUAL_MONTHLY = {        # effective monthly when billed annually
    "free":    0,
    "starter": 78,    # 97 * 0.8 = 77.60 → $78
    "growth":  158,   # 197 * 0.8 = 157.60 → $158
    "pro":     318,   # 397 * 0.8 = 317.60 → $318
}

PLAN_PRICE_ANNUAL_TOTAL = {          # total charged once per year
    "free":    0,
    "starter": 936,    # 78 * 12
    "growth":  1896,   # 158 * 12
    "pro":     3816,   # 318 * 12
}

PLAN_DISPLAY_NAMES = {
    "free":    "Free",
    "starter": "Starter",
    "growth":  "Growth",
    "pro":     "Pro",
}

# Human-readable names for usage metrics (used in limit-hit messaging)
METRIC_DISPLAY_NAMES: dict[str, str] = {
    "posts_created":        "AI Posts",
    "images_created":       "AI Images",
    "videos_created":       "Faceless Videos",
    "replies_sent":         "AI Engagement Replies (social + email)",
    "campaigns_sent":       "Email Campaigns",
    "research_run":         "Deep Research Sessions",
    "competitive_research": "Competitive Research Reports",
    "growth_strategy":      "Growth Strategy Sessions",
    "social_accounts":      "Connected Social Accounts",
}

# Which add-on to suggest when a metric is exhausted
METRIC_ADDON_SUGGESTION: dict[str, str] = {
    "posts_created":        "Post Boost Pack (+30 posts, $39/mo)",
    "images_created":       "Premium Images Pack (+25 images, $29/mo)",
    "videos_created":       "Video Boost Pack (+5 videos, $39/mo)",
    "replies_sent":         "Engagement Boost Pack (+250 replies, $29/mo)",
    "campaigns_sent":       "Email Campaign Boost (+5 campaigns, $25/mo)",
    "research_run":         "Research Boost Pack (+5 sessions, $39/mo)",
    "competitive_research": "Research Boost Pack (+5 sessions, $39/mo)",
    "growth_strategy":      "Growth Strategy Pack (+3 sessions, $49/mo)",
}

PLAN_TAGLINES = {
    "free":    "Get started — no credit card needed",
    "starter": "Your first AI marketing hire",
    "growth":  "A full marketing department in your pocket",
    "pro":     "Replace your $3K/mo marketing agency",
}

# ── Stripe Price IDs (env var override, with hardcoded defaults so Railway works) ──
STRIPE_PRICE_IDS = {
    ("starter", "monthly"): os.getenv("STRIPE_PRICE_STARTER_MONTHLY", "price_1T3Z12F9oATlcOnlKXAIuQCy"),
    ("starter", "annual"):  os.getenv("STRIPE_PRICE_STARTER_ANNUAL",  "price_1T3Z12F9oATlcOnlmE7PpRKY"),
    ("growth",  "monthly"): os.getenv("STRIPE_PRICE_GROWTH_MONTHLY",  "price_1T3Z1cF9oATlcOnl8pCtDy0Q"),
    ("growth",  "annual"):  os.getenv("STRIPE_PRICE_GROWTH_ANNUAL",   "price_1T3Z1cF9oATlcOnlYHYx1Asz"),
    ("pro",     "monthly"): os.getenv("STRIPE_PRICE_PRO_MONTHLY",     "price_1T3Z2eF9oATlcOnlNswaSgiw"),
    ("pro",     "annual"):  os.getenv("STRIPE_PRICE_PRO_ANNUAL",      "price_1T3Z2eF9oATlcOnlo7HhKcdL"),
}

# Add-on price IDs — filled after creating prices in Stripe Dashboard
ADDON_STRIPE_PRICE_IDS: dict[str, str] = {
    key: os.getenv(addon["stripe_price_env"], "")
    for key, addon in ADDONS.items()
}

# Reverse map: Stripe price ID → addon key
ADDON_PRICE_TO_KEY: dict[str, str] = {
    pid: key for key, pid in ADDON_STRIPE_PRICE_IDS.items() if pid
}


def get_limits(tier: str) -> dict[str, Any]:
    """Return the limits dict for the given plan tier. Defaults to 'free'."""
    return PLANS.get(tier, PLANS["free"])


def get_usage_limit(tier: str, metric: str) -> int:
    """Return the numeric limit for a specific metric. -1 = unlimited."""
    return get_limits(tier).get(metric, 0)


def _parse_active_addons(profile) -> dict:
    """Parse the active_addons JSON field from a ClientProfile."""
    raw = getattr(profile, "active_addons", None)
    if not raw:
        return {}
    try:
        return _json.loads(raw) if isinstance(raw, str) else (raw or {})
    except Exception:
        return {}


def get_effective_limit(tier: str, metric: str, active_addons: dict) -> int:
    """
    Return the effective numeric limit for a metric, after applying add-on bonuses.
    -1 = unlimited. Returns base limit if no relevant addons.
    """
    base = get_usage_limit(tier, metric)
    if base == -1:
        return -1  # already unlimited — addons don't change this

    bonus = 0
    for addon_key, is_active in (active_addons or {}).items():
        if not is_active:
            continue
        addon = ADDONS.get(addon_key)
        if not addon:
            continue
        bonus += addon.get("adds", {}).get(metric, 0)

    if bonus == 0:
        return base
    # If base was 0 (blocked) but an addon adds, the addon grants the feature
    return max(base, 0) + bonus


def has_feature(tier: str, feature: str) -> bool:
    """Return True if the plan tier includes the given boolean feature."""
    val = get_limits(tier).get(feature, False)
    if isinstance(val, bool):
        return val
    if isinstance(val, int):
        return val != 0
    return False


def has_feature_with_addons(tier: str, feature: str, active_addons: dict) -> bool:
    """Return True if the plan OR any active add-on unlocks the feature."""
    if has_feature(tier, feature):
        return True
    for addon_key, is_active in (active_addons or {}).items():
        if not is_active:
            continue
        addon = ADDONS.get(addon_key)
        if addon and addon.get("unlocks", {}).get(feature):
            return True
    return False


def check_limit(profile, metric: str) -> tuple[bool, str]:
    """
    Check if a ClientProfile has remaining quota for the given metric,
    including any active add-on bonuses.

    Returns:
        (True, "")          — within limits, proceed
        (False, message)    — limit reached, block the action
    """
    tier          = getattr(profile, "plan_tier", "free")
    active_addons = _parse_active_addons(profile)
    limit         = get_effective_limit(tier, metric, active_addons)
    tier_name     = PLAN_DISPLAY_NAMES.get(tier, tier.title())
    metric_name   = METRIC_DISPLAY_NAMES.get(metric, metric.replace("_", " ").title())

    if limit == -1:
        return True, ""   # unlimited

    if limit == 0:
        addon_hint = METRIC_ADDON_SUGGESTION.get(metric, "")
        addon_line = f" Or add the {addon_hint}." if addon_hint else ""
        return False, (
            f"Your {tier_name} plan does not include {metric_name}."
            f" Upgrade your plan to unlock this feature.{addon_line}"
            f" Visit /billing to upgrade →"
        )

    current = getattr(profile, f"usage_{metric}", 0) or 0
    if current >= limit:
        addon_hint = METRIC_ADDON_SUGGESTION.get(metric, "")
        addon_line = f" Or add the {addon_hint} to get more without upgrading." if addon_hint else ""
        return False, (
            f"You've hit your monthly {metric_name} limit ({current}/{limit} used) on the {tier_name} plan."
            f" Upgrade your plan for a higher limit.{addon_line}"
            f" Visit /billing to upgrade →"
        )

    return True, ""


def increment_usage(profile, metric: str, db) -> None:
    """
    Atomically increment a usage counter and save to DB.
    Uses SQL-level increment to prevent race conditions with concurrent requests.
    """
    col = f"usage_{metric}"
    try:
        from database.models import ClientProfile
        from sqlalchemy import text
        # Atomic SQL increment — avoids read-modify-write race
        db.execute(
            text(f"UPDATE client_profiles SET {col} = COALESCE({col}, 0) + 1 WHERE id = :pid"),
            {"pid": profile.id},
        )
        db.commit()
        # Refresh the in-memory object so callers see the new value
        db.refresh(profile)
    except Exception:
        # Fallback to non-atomic if the SQL approach fails (e.g. column doesn't exist)
        db.rollback()
        current = getattr(profile, col, 0) or 0
        setattr(profile, col, current + 1)
        db.add(profile)
        db.commit()


# ── Calendar / post scheduling quota helpers ──────────────────────────────────

def count_scheduled_posts_this_month(client_id: str) -> int:
    """
    Unified post counter:  returns the total number of posts the client has
    created *or* scheduled in the current calendar month.

    Sources (takes the MAX so neither can undercount):
      1. ``scheduled_posts`` PostgreSQL table  — rows created this month
         (covers AI calendar generation + manual Schedule Post + Create Post
         → Schedule flow).
      2. ``ClientProfile.usage_posts_created`` column — incremented by the
         Create Post "Generate with AI" endpoint.  This catches AI
         generations even if the user never pressed "Schedule".

    Why ``max``:  The Schedule Post endpoint increments ``usage_posts_created``
    *and* inserts a ``scheduled_posts`` row, so both counters count the same
    event.  We take the higher of the two to avoid double-counting while
    ensuring neither can be bypassed.
    """
    from datetime import datetime as _dt

    now = _dt.utcnow()
    period_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    db_count = 0
    usage_count = 0

    # ── Source 1: PostgreSQL scheduled_posts table ─────────────────────────
    try:
        from database.db import SessionLocal as _SL
        from database.models import ScheduledPost as _SP, ClientProfile as _CP
        _db = _SL()
        try:
            db_count = (
                _db.query(_SP)
                .filter(
                    _SP.client_id == client_id,
                    _SP.created_at >= period_start,
                    _SP.status.notin_(["deleted", "cancelled"]),
                )
                .count()
            )
            # ── Source 2: usage_posts_created column ───────────────────────
            _prof = _db.query(_CP).filter(_CP.client_id == client_id).first()
            if _prof:
                usage_count = getattr(_prof, "usage_posts_created", 0) or 0
        finally:
            _db.close()
    except Exception as _e:
        print(f"[plan_limits] DB post count failed: {_e}")

    return max(db_count, usage_count)


def check_post_schedule_limit(profile) -> tuple[bool, int, int, str]:
    """
    Determine if the client can schedule another post this month, accounting for
    the base plan limit plus any active Post Boost add-ons.

    Returns:
        (allowed: bool, used: int, limit: int, message: str)

    Mid-month upgrades are handled automatically: when a client upgrades their
    plan_tier, the effective limit increases immediately, so remaining quota grows.
    """
    tier          = getattr(profile, "plan_tier", "free") or "free"
    active_addons = _parse_active_addons(profile)
    limit         = get_effective_limit(tier, "posts_created", active_addons)
    tier_name     = PLAN_DISPLAY_NAMES.get(tier, tier.title())

    used = count_scheduled_posts_this_month(getattr(profile, "client_id", ""))

    if limit == -1:
        # Unlimited plan (Pro)
        return True, used, -1, ""

    if limit == 0:
        addon_hint = METRIC_ADDON_SUGGESTION.get("posts_created", "")
        addon_line = f" Or add the {addon_hint}." if addon_hint else ""
        msg = (
            f"Your {tier_name} plan does not include AI post scheduling."
            f" Upgrade to unlock it.{addon_line}"
            f" Visit /billing →"
        )
        return False, used, 0, msg

    if used >= limit:
        addon_hint = METRIC_ADDON_SUGGESTION.get("posts_created", "")
        addon_line = (
            f" Or add the {addon_hint} to get more posts this month without upgrading."
            if addon_hint else ""
        )
        msg = (
            f"You've scheduled {used}/{limit} posts this month on your {tier_name} plan."
            f" Upgrade for a higher limit.{addon_line}"
            f" Visit /billing to upgrade →"
        )
        return False, used, limit, msg

    return True, used, limit, ""
