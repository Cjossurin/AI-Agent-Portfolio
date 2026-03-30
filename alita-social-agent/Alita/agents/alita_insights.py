# agents/alita_insights.py
"""
Alita Insight Engine — Proactive "Chief of Staff" briefings.

Gathers page-specific data for a client, calls Claude to generate
2-4 actionable insight cards, and caches the result for 15 minutes.

Each card is a dict:
    {
        "type":         "alert" | "suggestion" | "win" | "nudge",
        "icon":         emoji string,
        "title":        short headline  (≤60 chars ideally),
        "body":         1-2 sentence detail,
        "action_url":   optional link,
        "action_label": optional button text,
        "priority":     "high" | "medium" | "low",
    }
"""

import os
import json
import time
from typing import List, Dict, Optional
from datetime import datetime, timedelta

from anthropic import Anthropic
from dotenv import load_dotenv

load_dotenv()

# ── In-memory insight cache: { "client_id:page": (timestamp, cards) } ─────
_insight_cache: Dict[str, tuple] = {}
_CACHE_TTL = 900  # 15 minutes


# ─────────────────────────────────────────────────────────────────────────────
# Page-specific data gatherers
# ─────────────────────────────────────────────────────────────────────────────

def _gather_dashboard_data(client_id: str, profile) -> dict:
    """Gather data visible/relevant on the Dashboard page."""
    data: dict = {"page": "dashboard"}
    try:
        from database.db import SessionLocal
        from database.models import ScheduledPost, ClientNotification
        db = SessionLocal()
        try:
            today_str = datetime.utcnow().strftime("%Y-%m-%d")
            tomorrow_str = (datetime.utcnow() + timedelta(days=1)).strftime("%Y-%m-%d")

            # Posts scheduled today
            today_posts = (
                db.query(ScheduledPost)
                .filter(
                    ScheduledPost.client_id == client_id,
                    ScheduledPost.status == "scheduled",
                    ScheduledPost.scheduled_time.ilike(f"{today_str}%"),
                )
                .count()
            )
            data["posts_today"] = today_posts

            # Posts scheduled tomorrow
            tomorrow_posts = (
                db.query(ScheduledPost)
                .filter(
                    ScheduledPost.client_id == client_id,
                    ScheduledPost.status == "scheduled",
                    ScheduledPost.scheduled_time.ilike(f"{tomorrow_str}%"),
                )
                .count()
            )
            data["posts_tomorrow"] = tomorrow_posts

            # Unread notifications
            unread = (
                db.query(ClientNotification)
                .filter(
                    ClientNotification.client_id == client_id,
                    ClientNotification.read == False,
                )
                .count()
            )
            data["unread_notifications"] = unread

            # Setup completion checks
            data["tone_configured"] = bool(getattr(profile, "tone_configured", False))
            data["rag_ready"] = bool(getattr(profile, "rag_ready", False))
            data["has_knowledge"] = bool(getattr(profile, "tone_preferences_json", None))

            # Plan info
            data["plan_tier"] = getattr(profile, "plan_tier", "free") or "free"

            # Last posted date (most recent non-scheduled post)
            last_post = (
                db.query(ScheduledPost)
                .filter(
                    ScheduledPost.client_id == client_id,
                    ScheduledPost.status == "posted",
                )
                .order_by(ScheduledPost.updated_at.desc())
                .first()
            )
            if last_post and last_post.updated_at:
                days_since = (datetime.utcnow() - last_post.updated_at).days
                data["days_since_last_post"] = days_since
            else:
                data["days_since_last_post"] = None

        finally:
            db.close()
    except Exception as e:
        print(f"[AlitaInsights] Dashboard gather error: {e}")
    return data


def _gather_calendar_data(client_id: str, profile) -> dict:
    """Gather data relevant to the Calendar page."""
    data: dict = {"page": "calendar"}
    try:
        from database.db import SessionLocal
        from database.models import ScheduledPost
        db = SessionLocal()
        try:
            now = datetime.utcnow()

            # Posts this week
            week_start = now - timedelta(days=now.weekday())
            week_end = week_start + timedelta(days=6)
            week_start_str = week_start.strftime("%Y-%m-%d")
            week_end_str = week_end.strftime("%Y-%m-%d")

            week_posts = (
                db.query(ScheduledPost)
                .filter(
                    ScheduledPost.client_id == client_id,
                    ScheduledPost.status == "scheduled",
                    ScheduledPost.scheduled_time >= week_start_str,
                    ScheduledPost.scheduled_time <= week_end_str + "T23:59:59",
                )
                .all()
            )
            data["posts_this_week"] = len(week_posts)

            # Figure out which days this week have posts
            days_with_posts = set()
            for p in week_posts:
                if p.scheduled_time:
                    try:
                        day = p.scheduled_time[:10]
                        days_with_posts.add(day)
                    except Exception:
                        pass
            total_days_this_week = 7
            data["empty_days_this_week"] = total_days_this_week - len(days_with_posts)

            # Platform distribution
            platforms = {}
            for p in week_posts:
                plat = (p.platform or "unknown").lower()
                platforms[plat] = platforms.get(plat, 0) + 1
            data["platform_distribution"] = platforms

            # Usage quota
            data["plan_tier"] = getattr(profile, "plan_tier", "free") or "free"
            data["posts_created"] = getattr(profile, "usage_posts_created", 0) or 0

        finally:
            db.close()
    except Exception as e:
        print(f"[AlitaInsights] Calendar gather error: {e}")
    return data


def _gather_analytics_data(client_id: str, profile) -> dict:
    """Gather data relevant to the Analytics page."""
    data: dict = {"page": "analytics"}
    try:
        from pathlib import Path
        analytics_dir = Path("storage") / "analytics" / client_id
        if analytics_dir.exists():
            # Find most recent weekly report
            reports = sorted(analytics_dir.glob("weekly_*.json"), reverse=True)
            if reports:
                try:
                    report = json.loads(reports[0].read_text(encoding="utf-8"))
                    agg = report.get("aggregates", {})
                    data["total_followers"] = agg.get("total_followers", 0)
                    data["total_engagement"] = agg.get("total_engagement", 0)
                    data["avg_engagement_rate"] = agg.get("avg_engagement_rate", 0)
                    data["top_platform"] = agg.get("top_platform", "")
                    insights = report.get("insights", [])
                    data["top_insight"] = insights[0] if insights else ""
                    recs = report.get("recommendations", [])
                    data["top_recommendation"] = recs[0] if recs else ""
                    data["report_date"] = reports[0].stem.replace("weekly_", "")
                except Exception:
                    pass
        # Check if connected
        data["has_meta_token"] = bool(getattr(profile, "meta_ig_account_id", None))
    except Exception as e:
        print(f"[AlitaInsights] Analytics gather error: {e}")
    return data


def _gather_growth_data(client_id: str, profile) -> dict:
    """Gather data relevant to the Growth page — reads from PostgreSQL."""
    data: dict = {"page": "growth"}
    try:
        from database.db import SessionLocal
        from database.models import GrowthReport
        _db = SessionLocal()
        try:
            rows = (
                _db.query(GrowthReport)
                .filter(GrowthReport.client_id == client_id)
                .order_by(GrowthReport.created_at.desc())
                .all()
            )
            data["total_reports"] = len(rows)
            if rows:
                try:
                    latest = json.loads(rows[0].report_json)
                    data["latest_report_date"] = latest.get("generated_at", rows[0].created_at.isoformat() if rows[0].created_at else "")
                    qw = latest.get("quick_wins", [])
                    data["quick_wins_count"] = len(qw)
                    data["sample_quick_win"] = qw[0].get("title", "") if qw else ""
                except Exception:
                    pass
        finally:
            _db.close()

        # Check for campaign activity (DB-backed)
        try:
            from database.models import GrowthCampaignRun
            _db2 = SessionLocal()
            try:
                latest_run = (
                    _db2.query(GrowthCampaignRun)
                    .filter(GrowthCampaignRun.client_id == client_id)
                    .order_by(GrowthCampaignRun.created_at.desc())
                    .first()
                )
                if latest_run and latest_run.created_at:
                    data["days_since_campaign"] = (datetime.utcnow() - latest_run.created_at).days
            finally:
                _db2.close()
        except Exception:
            pass
    except Exception as e:
        print(f"[AlitaInsights] Growth gather error: {e}")
    return data


def _gather_create_post_data(client_id: str, profile) -> dict:
    """Gather data relevant to the Create Post page."""
    data: dict = {"page": "create-post"}
    try:
        from database.db import SessionLocal
        from database.models import ScheduledPost
        db = SessionLocal()
        try:
            # Time since last post per platform
            platforms = ["instagram", "facebook", "twitter", "linkedin", "tiktok", "threads"]
            platform_gaps = {}
            for plat in platforms:
                last = (
                    db.query(ScheduledPost)
                    .filter(
                        ScheduledPost.client_id == client_id,
                        ScheduledPost.platform == plat,
                        ScheduledPost.status.in_(["posted", "scheduled"]),
                    )
                    .order_by(ScheduledPost.scheduled_time.desc())
                    .first()
                )
                if last and last.scheduled_time:
                    try:
                        dt = datetime.fromisoformat(last.scheduled_time.replace("Z", "+00:00"))
                        gap = (datetime.utcnow() - dt.replace(tzinfo=None)).days
                        if gap > 0:
                            platform_gaps[plat] = gap
                    except Exception:
                        pass
            data["platform_gaps"] = platform_gaps
            data["niche"] = getattr(profile, "niche", "") or ""
        finally:
            db.close()
    except Exception as e:
        print(f"[AlitaInsights] Create-post gather error: {e}")
    return data


def _gather_inbox_data(client_id: str, profile) -> dict:
    """Gather data relevant to the Inbox page."""
    data: dict = {"page": "inbox"}
    # Inbox data is primarily fetched via external APIs at runtime,
    # so we provide general prompts
    data["has_meta_token"] = bool(getattr(profile, "meta_ig_account_id", None))
    return data


def _gather_settings_data(client_id: str, profile) -> dict:
    """Gather data relevant to Settings pages."""
    data: dict = {"page": "settings"}
    data["tone_configured"] = bool(getattr(profile, "tone_configured", False))
    data["has_knowledge"] = bool(getattr(profile, "rag_ready", False))
    data["has_samples"] = bool(getattr(profile, "normalized_samples_text", None))
    data["plan_tier"] = getattr(profile, "plan_tier", "free") or "free"
    data["has_meta_token"] = bool(getattr(profile, "meta_ig_account_id", None))
    return data


def _gather_generic_data(client_id: str, profile, page: str) -> dict:
    """Fallback for pages without a specific gatherer."""
    data: dict = {"page": page}
    data["plan_tier"] = getattr(profile, "plan_tier", "free") or "free"
    data["tone_configured"] = bool(getattr(profile, "tone_configured", False))
    return data


# ── Page → gatherer mapping ──────────────────────────────────────────────────
_PAGE_GATHERERS = {
    "dashboard":       _gather_dashboard_data,
    "calendar":        _gather_calendar_data,
    "analytics":       _gather_analytics_data,
    "social":          _gather_growth_data,        # growth page nav_id
    "growth":          _gather_growth_data,
    "create-post":     _gather_create_post_data,
    "inbox":           _gather_inbox_data,
    "comments":        _gather_inbox_data,          # similar context
    "settings":        _gather_settings_data,
    "tone":            _gather_settings_data,
    "knowledge":       _gather_settings_data,
    "connect":         _gather_settings_data,
    "creative":        _gather_settings_data,
    "notifications":   _gather_settings_data,
}


# ─────────────────────────────────────────────────────────────────────────────
# Insight prompt + generation
# ─────────────────────────────────────────────────────────────────────────────

_INSIGHT_SYSTEM = """You are Alita, an AI marketing strategist embedded in the Alita AI platform.
You generate proactive briefing cards for the client — short, actionable insights
that help them make better decisions RIGHT NOW.

You are NOT a chatbot. You are a strategist who watches the data and speaks first.
Think like a sharp executive assistant who walks in and says "Before you start —
here are the 3 things you need to know."

Rules:
1. Return ONLY valid JSON — an array of 2-4 objects.
2. Each object has exactly these keys:
   "type": one of "alert", "suggestion", "win", "nudge"
   "icon": a single relevant emoji
   "title": short headline, ≤60 chars (no period)
   "body": 1-2 sentences of context or advice. Be specific with numbers when available.
   "action_url": a URL path on the platform (e.g. "/calendar") or "" if none
   "action_label": short button label (e.g. "View Calendar") or "" if none
   "priority": "high", "medium", or "low"
3. Cards should be diverse — don't repeat the same theme.
4. Prioritize by urgency: alerts > suggestions > nudges > wins.
5. Be specific and data-driven when numbers are available. No vague platitudes.
6. Keep it punchy — this is NOT a conversation, it's a dashboard briefing.
7. Never fabricate numbers. If you don't have data, give a strategic tip instead.
8. Match the page context — only give insights relevant to what the user is looking at.
{tone_block}
Current date: {date}
Client business: {business_name}
Client niche: {niche}
Client plan: {plan_tier}
Page the client is viewing: {page}

=== PAGE DATA ===
{page_data_json}
=== END PAGE DATA ===

Return ONLY the JSON array. No markdown, no explanation, no code fence."""


def generate_insights(
    client_id: str,
    page: str,
    profile,
    business_name: str = "",
    force: bool = False,
) -> List[Dict]:
    """
    Generate (or return cached) insight cards for a given page.

    Parameters
    ----------
    client_id    : Client identifier
    page         : The nav-id of the page (e.g. "dashboard", "calendar")
    profile      : The ClientProfile ORM object (or None)
    business_name: Client business name
    force        : Bypass cache if True
    """
    cache_key = f"{client_id}:{page}"

    # Check cache
    if not force and cache_key in _insight_cache:
        ts, cards = _insight_cache[cache_key]
        if time.time() - ts < _CACHE_TTL:
            return cards

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        return _fallback_insights(page)

    # Gather page-specific data
    gatherer = _PAGE_GATHERERS.get(page, lambda cid, prof: _gather_generic_data(cid, prof, page))
    try:
        page_data = gatherer(client_id, profile)
    except Exception:
        page_data = {"page": page}

    # Build tone block (reuse from alita_assistant)
    tone_block = ""
    try:
        from agents.alita_assistant import _build_tone_block
        tone_block = _build_tone_block(client_id)
        if tone_block:
            tone_block = (
                "\n\nIMPORTANT — write ALL card titles and bodies in this client's "
                "communication style:\n" + tone_block
            )
    except Exception:
        pass

    niche = getattr(profile, "niche", "") or "" if profile else ""
    plan_tier = getattr(profile, "plan_tier", "free") or "free" if profile else "free"

    system_prompt = _INSIGHT_SYSTEM.format(
        date=datetime.utcnow().strftime("%B %d, %Y"),
        business_name=business_name or "the client's business",
        niche=niche or "general",
        plan_tier=plan_tier,
        page=page,
        page_data_json=json.dumps(page_data, default=str),
        tone_block=tone_block,
    )

    try:
        client = Anthropic(api_key=api_key)
        response = client.messages.create(
            model=os.getenv("CLAUDE_HAIKU_MODEL", "claude-haiku-4-5-20251001"),
            max_tokens=800,
            system=system_prompt,
            messages=[{"role": "user", "content": f"Generate briefing cards for the {page} page."}],
        )
        raw = response.content[0].text.strip()

        # Parse JSON — handle potential markdown fence
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[-1].rsplit("```", 1)[0]
        cards = json.loads(raw)
        if not isinstance(cards, list):
            cards = [cards]

        # Validate card schema
        valid_cards = []
        for card in cards[:4]:
            if isinstance(card, dict) and "title" in card and "body" in card:
                valid_cards.append({
                    "type": card.get("type", "suggestion"),
                    "icon": card.get("icon", "💡"),
                    "title": str(card.get("title", ""))[:80],
                    "body": str(card.get("body", ""))[:300],
                    "action_url": str(card.get("action_url", "")),
                    "action_label": str(card.get("action_label", "")),
                    "priority": card.get("priority", "medium"),
                })
        if not valid_cards:
            valid_cards = _fallback_insights(page)

        # Cache
        _insight_cache[cache_key] = (time.time(), valid_cards)
        return valid_cards

    except Exception as e:
        print(f"[AlitaInsights] Generation error: {e}")
        fb = _fallback_insights(page)
        _insight_cache[cache_key] = (time.time(), fb)
        return fb


def invalidate_cache(client_id: str, page: str = ""):
    """Clear cached insights. If page is empty, clear all for client."""
    keys_to_remove = []
    for key in _insight_cache:
        if key.startswith(f"{client_id}:"):
            if not page or key == f"{client_id}:{page}":
                keys_to_remove.append(key)
    for k in keys_to_remove:
        _insight_cache.pop(k, None)


# ─────────────────────────────────────────────────────────────────────────────
# Fallback insights (no Claude needed — always available)
# ─────────────────────────────────────────────────────────────────────────────

_FALLBACK_CARDS = {
    "dashboard": [
        {
            "type": "suggestion", "icon": "📅", "priority": "medium",
            "title": "Plan your week ahead",
            "body": "Consistent posting drives growth. Head to the Calendar to schedule your next batch of content.",
            "action_url": "/calendar", "action_label": "Open Calendar",
        },
        {
            "type": "nudge", "icon": "🎯", "priority": "low",
            "title": "Explore Growth tools",
            "body": "Generate a growth strategy tailored to your niche — it takes under a minute.",
            "action_url": "/growth/dashboard", "action_label": "Try Growth",
        },
    ],
    "calendar": [
        {
            "type": "suggestion", "icon": "🕐", "priority": "medium",
            "title": "Fill empty days",
            "body": "Gaps in your calendar mean missed opportunities. Use auto-generate to fill them in seconds.",
            "action_url": "", "action_label": "",
        },
    ],
    "analytics": [
        {
            "type": "nudge", "icon": "📊", "priority": "medium",
            "title": "Run your weekly AI analysis",
            "body": "Get AI-powered insights on what's working and what needs attention across all your platforms.",
            "action_url": "", "action_label": "",
        },
    ],
    "create-post": [
        {
            "type": "suggestion", "icon": "✍️", "priority": "medium",
            "title": "Try multi-platform posting",
            "body": "Create once, publish everywhere. Select multiple platforms to maximize your reach.",
            "action_url": "", "action_label": "",
        },
    ],
}


def _fallback_insights(page: str) -> List[Dict]:
    """Return static cards when Claude is unavailable."""
    return _FALLBACK_CARDS.get(page, [
        {
            "type": "nudge", "icon": "💡", "priority": "low",
            "title": "Alita is here to help",
            "body": "Ask me anything about growing your business or using the platform more effectively.",
            "action_url": "/alita/chat", "action_label": "Open Chat",
        },
    ])
