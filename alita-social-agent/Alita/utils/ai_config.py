"""
utils/ai_config.py — Single source of truth for AI model selection per plan tier.

Every agent should import from here instead of calling os.getenv() for model
strings directly.  This keeps model upgrades, tier gating, and fallback logic
in one place.

Usage:
    from utils.ai_config import get_text_model, get_max_image_quality, get_gemini_model
    from utils.ai_config import CLAUDE_HAIKU, CLAUDE_SONNET

    model = get_text_model("starter", complexity="complex")   # -> Sonnet
    model = get_text_model("free",    complexity="complex")   # -> Haiku
    quality_cap = get_max_image_quality("free")                # -> ImageQuality.BUDGET
    gemini = get_gemini_model("pro")                           # -> gemini-2.5-pro-exp-03-25
"""
from __future__ import annotations

import os
from enum import IntEnum


# ══════════════════════════════════════════════════════════════════════════════
# Claude / Anthropic  (env-var with safe defaults)
# ══════════════════════════════════════════════════════════════════════════════
CLAUDE_HAIKU:  str = os.getenv("CLAUDE_HAIKU_MODEL",  "claude-haiku-4-5-20251001")
CLAUDE_SONNET: str = os.getenv("CLAUDE_SONNET_MODEL", "claude-sonnet-4-5-20250929")


# ══════════════════════════════════════════════════════════════════════════════
# OpenAI
# ══════════════════════════════════════════════════════════════════════════════
GPT4V_MODEL:  str = os.getenv("GPT4V_MODEL",  "gpt-4o-mini")
DALLE_MODEL:  str = os.getenv("DALLE_MODEL",  "dall-e-3")


# ══════════════════════════════════════════════════════════════════════════════
# Google Gemini
# ══════════════════════════════════════════════════════════════════════════════
GEMINI_FLASH: str = os.getenv("GEMINI_FLASH_MODEL", "models/gemini-2.0-flash-exp")
GEMINI_25:    str = os.getenv("GEMINI_25_MODEL",    "models/gemini-2.5-pro-exp-03-25")


# ══════════════════════════════════════════════════════════════════════════════
# Image quality ordering (IntEnum so we can compare with < / > / min / max)
# ══════════════════════════════════════════════════════════════════════════════
class _ImageQualityOrder(IntEnum):
    """Mirrors agents.image_generator.ImageQuality but as an orderable int."""
    BUDGET   = 0
    STANDARD = 1
    PREMIUM  = 2


# ══════════════════════════════════════════════════════════════════════════════
# Per-tier mappings
# ══════════════════════════════════════════════════════════════════════════════

# Claude text model per tier + task complexity
# "simple"  = chat replies, short captions, engagement replies
# "complex" = blog posts, emails, strategies, long-form content
TIER_TEXT_MODELS: dict[str, dict[str, str]] = {
    "free":    {"simple": CLAUDE_HAIKU,  "complex": CLAUDE_HAIKU},
    "starter": {"simple": CLAUDE_HAIKU,  "complex": CLAUDE_SONNET},
    "growth":  {"simple": CLAUDE_SONNET, "complex": CLAUDE_SONNET},
    "pro":     {"simple": CLAUDE_SONNET, "complex": CLAUDE_SONNET},
}

# Maximum image quality allowed per tier
# Free    -> DALL-E only (BUDGET)
# Starter -> DALL-E + Flux (STANDARD)
# Growth  -> DALL-E + Flux + Midjourney (PREMIUM)
# Pro     -> Everything (PREMIUM)
TIER_MAX_IMAGE_QUALITY: dict[str, str] = {
    "free":    "budget",
    "starter": "standard",
    "growth":  "premium",
    "pro":     "premium",
}

# Gemini model per tier
# Free / Starter  -> Flash 2.0  (fast, cost-effective)
# Growth / Pro    -> Gemini 2.5 Pro (advanced reasoning)
TIER_GEMINI_MODELS: dict[str, str] = {
    "free":    GEMINI_FLASH,
    "starter": GEMINI_FLASH,
    "growth":  GEMINI_25,
    "pro":     GEMINI_25,
}


# ══════════════════════════════════════════════════════════════════════════════
# Public helpers
# ══════════════════════════════════════════════════════════════════════════════

def get_text_model(tier: str = "pro", complexity: str = "complex") -> str:
    """Return the Claude model string for a given plan tier and task complexity.

    Args:
        tier:       "free" | "starter" | "growth" | "pro"
        complexity: "simple" | "complex"

    Unknown tiers default to **pro** (safest fallback — never down-grades
    a paying customer who lands on an unrecognised tier label).
    """
    tier_map = TIER_TEXT_MODELS.get(tier, TIER_TEXT_MODELS["pro"])
    return tier_map.get(complexity, tier_map["complex"])


def get_max_image_quality(tier: str = "pro") -> str:
    """Return the highest ImageQuality *value string* allowed for the tier.

    The returned string matches ``ImageQuality.value`` in
    ``agents.image_generator`` (e.g. ``"budget"``).  This avoids a circular
    import — the caller can compare against the actual enum.
    """
    return TIER_MAX_IMAGE_QUALITY.get(tier, "premium")


def cap_image_quality(requested_quality, tier: str = "pro"):
    """Clamp *requested_quality* to the tier's ceiling.

    Args:
        requested_quality: An ``ImageQuality`` enum member.
        tier: Plan tier string.

    Returns:
        The lower of *requested_quality* and the tier's maximum, as an
        ``ImageQuality`` enum member.

    This must be called **after** ``ImageQuality`` is importable (i.e. inside
    agent code, never at module top-level in this file to avoid circular deps).
    """
    from agents.image_generator import ImageQuality  # deferred to avoid circular

    _ORDER = {
        ImageQuality.BUDGET:   0,
        ImageQuality.STANDARD: 1,
        ImageQuality.PREMIUM:  2,
    }
    _REVERSE = {v: k for k, v in _ORDER.items()}

    max_val = TIER_MAX_IMAGE_QUALITY.get(tier, "premium")
    max_enum = ImageQuality(max_val)

    req_rank  = _ORDER.get(requested_quality, 0)
    max_rank  = _ORDER.get(max_enum, 2)
    capped    = _REVERSE[min(req_rank, max_rank)]
    return capped


def get_gemini_model(tier: str = "pro") -> str:
    """Return the Gemini model string for a given plan tier."""
    return TIER_GEMINI_MODELS.get(tier, GEMINI_25)
