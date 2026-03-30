"""
Content Calendar Orchestrator — Lightweight Calendar Planning Layer

Generates AI-optimised calendar *plans* (topics, platforms, times) that are
stored in PostgreSQL via ``_bridge_pieces_to_jsonl``.  Actual content
generation + posting happens JIT at each post's scheduled time
(``job_post_due_now`` in ``agent_scheduler.py``).

Used by:
  - ``api/calendar_routes.py``  → "Generate AI Calendar" button
  - ``agents/agent_scheduler.py`` → weekly_strategy job
  - ``utils/platform_events.py``  → auto-regen on new platform connect
"""

import os
import json
import random
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field, asdict
from enum import Enum
from pathlib import Path
import pytz
import sys

# Parent dir for sibling imports
_parent = str(Path(__file__).parent.parent)
if _parent not in sys.path:
    sys.path.insert(0, _parent)

from agents.calendar_agent import CalendarAgent, CalendarAgentRAG
from agents.content_agent import ContentCreationAgent, ContentIdea, GeneratedContent
from agents.client_profile_manager import ClientProfileManager

# ── Logging ────────────────────────────────────────────────────────────────
Path("logs").mkdir(exist_ok=True)
logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════
# Data classes — kept because _bridge_pieces_to_jsonl reads them
# ═══════════════════════════════════════════════════════════════════════════

class ContentStatus(Enum):
    PENDING = "pending"
    GENERATING = "generating"
    READY = "ready"
    APPROVED = "approved"
    SCHEDULED = "scheduled"
    POSTED = "posted"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class ScheduledContentPiece:
    """Individual slot in the calendar plan."""
    content_id: str
    calendar_id: str
    platform: str
    content_type: str
    scheduled_time: datetime
    timezone: str

    topic: Optional[str] = None
    theme: Optional[str] = None
    campaign_id: Optional[str] = None

    generated_content: Optional[GeneratedContent] = None

    status: str = ContentStatus.PENDING.value
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    generated_at: Optional[str] = None
    posted_at: Optional[str] = None

    priority: int = 2
    requires_approval: bool = True
    metadata: Dict[str, Any] = field(default_factory=dict)
    error_message: Optional[str] = None


@dataclass
class ContentCalendar:
    """Complete calendar plan."""
    calendar_id: str
    client_id: str
    name: str
    description: Optional[str] = None

    start_date: datetime = field(default_factory=datetime.now)
    end_date: Optional[datetime] = None
    timezone: str = "UTC"

    platforms: List[str] = field(default_factory=list)
    posts_per_platform_per_day: Dict[str, int] = field(default_factory=dict)
    themes: List[str] = field(default_factory=list)

    scheduled_content: List[ScheduledContentPiece] = field(default_factory=list)

    total_posts: int = 0
    pending_posts: int = 0
    ready_posts: int = 0
    approved_posts: int = 0
    posted_posts: int = 0
    failed_posts: int = 0

    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    last_modified: str = field(default_factory=lambda: datetime.now().isoformat())

    auto_approve: bool = False
    auto_post: bool = False

    def update_stats(self):
        self.total_posts = len(self.scheduled_content)
        self.pending_posts  = sum(1 for p in self.scheduled_content if p.status == ContentStatus.PENDING.value)
        self.ready_posts    = sum(1 for p in self.scheduled_content if p.status == ContentStatus.READY.value)
        self.approved_posts = sum(1 for p in self.scheduled_content if p.status == ContentStatus.APPROVED.value)
        self.posted_posts   = sum(1 for p in self.scheduled_content if p.status == ContentStatus.POSTED.value)
        self.failed_posts   = sum(1 for p in self.scheduled_content if p.status == ContentStatus.FAILED.value)
        self.last_modified  = datetime.now().isoformat()


# ═══════════════════════════════════════════════════════════════════════════
# Orchestrator
# ═══════════════════════════════════════════════════════════════════════════

class ContentCalendarOrchestrator:
    """
    Plans calendar slots (topics + optimal times) for each connected platform.
    Content is generated later — JIT at each post's scheduled time.
    """

    def __init__(
        self,
        client_id: str,
        timezone: str = None,
        load_existing_calendars: bool = False,   # no-op, kept for caller compat
    ):
        self.client_id = client_id
        self.timezone = timezone or os.getenv("DEFAULT_TIMEZONE", "America/New_York")

        # Client profile
        self.profile_manager = ClientProfileManager()
        self.client_profile = self.profile_manager.get_client_profile(client_id)

        if self.client_profile:
            _niche = getattr(self.client_profile, "niche", "(none)")
            _biz = (getattr(self.client_profile, "business_name", None)
                    or getattr(self.client_profile, "client_name", "(none)"))
            print(f"✅ [{client_id}] profile loaded — biz='{_biz}', niche='{_niche}'")
        else:
            print(f"⚠️ [{client_id}] profile NOT found — RAG will use niche fallback only")

        # Calendar agent (RAG-powered optimal times)
        self.calendar_agent = CalendarAgent(
            client_id=client_id,
            rag_system=CalendarAgentRAG(),
            profile=self.client_profile,
        )
        # Content agent kept for type references only (JIT gen uses its own instance)
        self.content_agent = ContentCreationAgent(client_id=client_id)

        # In-memory calendar store (only lives for the duration of this run)
        self.calendars: Dict[str, ContentCalendar] = {}
        self._calendar_counter = 0

        # Seeded ideas from Marketing Intelligence
        self._seeded_ideas: Dict[str, List[Dict]] = {}

        logger.info(f"ContentCalendarOrchestrator initialised for {client_id} (tz={self.timezone})")

    # ── ID helpers ─────────────────────────────────────────────────────────

    def _generate_calendar_id(self) -> str:
        self._calendar_counter += 1
        return f"calendar_{self.client_id}_{self._calendar_counter}_{datetime.now().strftime('%Y%m%d')}"

    def _generate_content_id(self) -> str:
        import uuid as _uuid
        return str(_uuid.uuid4())

    # ── Main entry point ──────────────────────────────────────────────────

    async def generate_calendar(
        self,
        name: str,
        platforms: Optional[List[str]] = None,
        duration_days: int = 7,
        posts_per_platform_per_day: Optional[Dict[str, int]] = None,
        themes: Optional[List[str]] = None,
        start_date: Optional[datetime] = None,
        auto_schedule: bool = True,
        auto_approve: bool = False,
        auto_post: bool = False,
        include_email_campaigns: bool = False,   # ignored, kept for compat
        description: Optional[str] = None,
        marketing_strategy: Optional[Any] = None,
        use_marketing_agent: bool = True,
    ) -> ContentCalendar:
        """
        Generate a calendar *plan* — topics + optimal posting times per platform.

        Content is NOT generated here.  It will be created JIT at each post's
        scheduled time by ``job_post_due_now`` (or the daily 05:00 safety net).
        """
        # ── Resolve platforms ──────────────────────────────────────────
        if not platforms:
            try:
                from utils.connected_platforms import get_connected_platforms
                platforms = get_connected_platforms(self.client_id)
                if platforms:
                    logger.info(f"[{self.client_id}] Auto-detected platforms: {platforms}")
            except Exception as _e:
                logger.warning(f"[{self.client_id}] Platform detection failed: {_e}")
        if not platforms:
            platforms = ["instagram", "facebook"]
            logger.warning(f"[{self.client_id}] Falling back to: {platforms}")

        logger.info(f"Generating calendar: {name} ({duration_days}d, {len(platforms)} platforms)")

        # Default start (tomorrow 8 AM)
        if start_date is None:
            tz = pytz.timezone(self.timezone)
            start_date = (datetime.now(tz).replace(hour=8, minute=0, second=0, microsecond=0)
                          + timedelta(days=1))

        end_date = start_date + timedelta(days=duration_days)

        # Themes from profile pillars
        if not themes and self.client_profile and self.client_profile.content_pillars:
            pillars = self.client_profile.content_pillars
            themes = pillars if isinstance(pillars, list) else [pillars]

        # Posting frequency
        if not posts_per_platform_per_day:
            posts_per_platform_per_day = self._get_default_posting_frequency(platforms)

        # ── Topics are NOT planned here ─────────────────────────────
        # Calendar generation only assigns platform + content_type + time.
        # Topics, research, captions, and media are all determined JIT when
        # each post is due (job_post_due_now in agent_scheduler.py).
        self._seeded_ideas = {}

        # ── Create calendar object ─────────────────────────────────────
        calendar = ContentCalendar(
            calendar_id=self._generate_calendar_id(),
            client_id=self.client_id,
            name=name,
            description=description,
            start_date=start_date,
            end_date=end_date,
            timezone=self.timezone,
            platforms=platforms,
            posts_per_platform_per_day=posts_per_platform_per_day,
            themes=themes or [],
            auto_approve=auto_approve,
            auto_post=auto_post,
        )
        self.calendars[calendar.calendar_id] = calendar

        logger.info(f"Calendar {calendar.calendar_id}: {start_date.date()} → {end_date.date()}, "
                     f"platforms={platforms}")

        # ── Fill schedule slots ────────────────────────────────────────
        if auto_schedule:
            await self._generate_optimal_schedule(calendar, duration_days)
        else:
            self._generate_simple_schedule(calendar, duration_days)

        calendar.update_stats()

        print(f"✅ Calendar planned: {calendar.total_posts} slots "
              f"({', '.join(platforms)}, {duration_days}d)")
        logger.info(f"Calendar {calendar.calendar_id}: {calendar.total_posts} slots planned")
        return calendar

    # ── Seed extraction ────────────────────────────────────────────────

    def _extract_seeded_ideas(self, strategy: Any, platforms: List[str]):
        self._seeded_ideas = {}
        try:
            ideas = getattr(strategy, "content_ideas", []) or []
            for idea in ideas:
                idea_platforms = (
                    getattr(idea, "platforms", None)
                    or [getattr(idea, "platform", None)]
                )
                idea_platforms = [p.lower() for p in idea_platforms if p]
                if not idea_platforms:
                    idea_platforms = [p.lower() for p in platforms]

                idea_dict = (
                    idea.to_dict() if hasattr(idea, "to_dict")
                    else {k: v for k, v in vars(idea).items()}
                )
                for k, v in list(idea_dict.items()):
                    if hasattr(v, "value"):
                        idea_dict[k] = v.value
                    elif hasattr(v, "name"):
                        idea_dict[k] = v.name

                for p in idea_platforms:
                    if p in [pl.lower() for pl in platforms] or p == "all":
                        targets = [pl.lower() for pl in platforms] if p == "all" else [p]
                        for tp in targets:
                            self._seeded_ideas.setdefault(tp, []).append(idea_dict)
        except Exception as e:
            logger.warning(f"Could not extract seeded ideas: {e}")

    # ── Posting frequency defaults ─────────────────────────────────────

    def _get_default_posting_frequency(self, platforms: List[str]) -> Dict[str, int]:
        defaults = {
            "instagram": 1,
            "tiktok": 2,
            "linkedin": 1,
            "facebook": 1,
            "twitter": 3,
            "threads": 1,
            "youtube": 1,
        }
        return {p: defaults.get(p.lower(), 1) for p in platforms}

    # ── AI-optimised schedule ──────────────────────────────────────────

    async def _generate_optimal_schedule(self, calendar: ContentCalendar, duration_days: int):
        logger.info(f"Generating optimal schedule for {len(calendar.platforms)} platforms")

        for platform in calendar.platforms:
            try:
                optimal = await self.calendar_agent.get_optimal_posting_times(
                    platform=platform,
                    timezone=self.timezone,
                    niche=(self.client_profile.niche.value
                           if self.client_profile and hasattr(self.client_profile.niche, "value")
                           else None),
                    content_type="post",
                    account_goal="growth",
                )

                recommended = optimal.get("recommended_times", [])
                ppd = calendar.posts_per_platform_per_day.get(platform, 1)
                current = calendar.start_date
                theme_idx = 0

                for day in range(duration_days):
                    dow = current.strftime("%A")
                    day_times = [t for t in recommended if t.get("day") == dow]
                    if not day_times:
                        day_times = [{"time": "10:00", "priority": "medium"}] * ppd

                    # Track times already used for this platform on this day
                    used_hours_today = []

                    for post_num in range(ppd):
                        ti = day_times[post_num % len(day_times)]
                        h, m = map(int, ti.get("time", "10:00").split(":"))
                        sched = current.replace(hour=h, minute=m, second=0, microsecond=0)

                        # ── Enforce minimum 1-hour gap between same-platform posts ──
                        _MIN_GAP_HOURS = 1
                        while any(abs((sched - u).total_seconds()) < _MIN_GAP_HOURS * 3600
                                  for u in used_hours_today):
                            sched += timedelta(hours=_MIN_GAP_HOURS)
                            if sched.hour >= 22:  # clamp to avoid scheduling past 10 PM
                                sched = sched.replace(hour=22, minute=0)
                                break
                        used_hours_today.append(sched)

                        theme = None
                        if calendar.themes:
                            theme = calendar.themes[theme_idx % len(calendar.themes)]
                            theme_idx += 1

                        slot_idx = day * ppd + post_num
                        ideas = self._seeded_ideas.get(platform.lower(), [])
                        seeded = ideas[slot_idx % len(ideas)] if ideas else None

                        calendar.scheduled_content.append(ScheduledContentPiece(
                            content_id=self._generate_content_id(),
                            calendar_id=calendar.calendar_id,
                            platform=platform,
                            content_type=self._infer_content_type(platform),
                            scheduled_time=sched,
                            timezone=self.timezone,
                            topic=(seeded.get("title") or seeded.get("topic")) if seeded else None,
                            theme=(seeded.get("theme") or theme) if seeded else theme,
                            priority=1 if ti.get("priority") == "high" else 2,
                            requires_approval=not calendar.auto_approve,
                            metadata={"seeded_idea": seeded} if seeded else {},
                        ))

                    current += timedelta(days=1)

                count = sum(1 for c in calendar.scheduled_content if c.platform == platform)
                logger.info(f"  {platform}: {count} slots")

            except Exception as e:
                logger.error(f"Optimal schedule failed for {platform}: {e}")
                self._generate_simple_schedule_for_platform(calendar, platform, duration_days)

    # ── Fallback simple schedule ───────────────────────────────────────

    def _generate_simple_schedule(self, calendar: ContentCalendar, duration_days: int):
        for platform in calendar.platforms:
            self._generate_simple_schedule_for_platform(calendar, platform, duration_days)

    def _generate_simple_schedule_for_platform(
        self, calendar: ContentCalendar, platform: str, duration_days: int
    ):
        ppd = calendar.posts_per_platform_per_day.get(platform, 1)
        times = {
            "instagram": ["10:00", "14:00", "19:00"],
            "tiktok":    ["07:00", "12:00", "17:00", "20:00"],
            "linkedin":  ["08:00", "12:00", "17:00"],
            "facebook":  ["10:00", "13:00", "18:00"],
            "twitter":   ["09:00", "13:00", "17:00", "20:00"],
            "threads":   ["10:00", "15:00", "20:00"],
            "youtube":   ["15:00"],
        }.get(platform.lower(), ["10:00", "14:00", "18:00"])

        current = calendar.start_date
        theme_idx = 0

        for day in range(duration_days):
            used_hours_today = []

            for post_num in range(ppd):
                t = times[post_num % len(times)]
                h, m = map(int, t.split(":"))
                sched = current.replace(hour=h, minute=m, second=0, microsecond=0)

                # ── Enforce minimum 1-hour gap between same-platform posts ──
                _MIN_GAP_HOURS = 1
                while any(abs((sched - u).total_seconds()) < _MIN_GAP_HOURS * 3600
                          for u in used_hours_today):
                    sched += timedelta(hours=_MIN_GAP_HOURS)
                    if sched.hour >= 22:
                        sched = sched.replace(hour=22, minute=0)
                        break
                used_hours_today.append(sched)

                theme = None
                if calendar.themes:
                    theme = calendar.themes[theme_idx % len(calendar.themes)]
                    theme_idx += 1

                slot_idx = day * ppd + post_num
                ideas = self._seeded_ideas.get(platform.lower(), [])
                seeded = ideas[slot_idx % len(ideas)] if ideas else None

                calendar.scheduled_content.append(ScheduledContentPiece(
                    content_id=self._generate_content_id(),
                    calendar_id=calendar.calendar_id,
                    platform=platform,
                    content_type=self._infer_content_type(platform),
                    scheduled_time=sched,
                    timezone=self.timezone,
                    topic=(seeded.get("title") or seeded.get("topic")) if seeded else None,
                    theme=(seeded.get("theme") or theme) if seeded else theme,
                    requires_approval=not calendar.auto_approve,
                    metadata={"seeded_idea": seeded} if seeded else {},
                ))

            current += timedelta(days=1)

    # ── Content-type mix per platform ──────────────────────────────────

    def _infer_content_type(self, platform: str) -> str:
        _mix = {
            "instagram": (["post", "reel", "carousel", "story"],  [40, 35, 15, 10]),
            "tiktok":    (["video"],                               [100]),
            "linkedin":  (["post", "article", "thread"],           [70, 20, 10]),
            "facebook":  (["post", "reel", "story"],               [50, 30, 20]),
            "twitter":   (["tweet", "thread"],                     [80, 20]),
            "threads":   (["post", "thread"],                      [90, 10]),
            "youtube":   (["video", "shorts"],                     [60, 40]),
        }
        p = platform.lower()
        if p in _mix:
            types, weights = _mix[p]
            return random.choices(types, weights=weights, k=1)[0]
        return "post"
