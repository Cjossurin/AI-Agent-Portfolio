"""
agents/agent_scheduler.py

Centralised APScheduler-based trigger system for every Alita agent.

══════════════════════════════════════════════════════════════════════════════
COMPLETE TRIGGER MAP
══════════════════════════════════════════════════════════════════════════════

REAL-TIME  (driven by webhook_receiver.py — no changes needed there):
  Incoming DM          → EngagementAgent.handle_dm
  Incoming comment     → EngagementAgent.handle_comment
                         ConversationCategorizer.categorize_message
  Story mention        → EngagementAgent.handle_story_mention
  Escalation keyword   → Human Escalation (webhook_receiver.py)
  OAuth callback       → Auto style-learn (api/oauth_routes.py BackgroundTask)

SCHEDULED  (this file — one job-set per onboarded client):
  ┌──────────────────────────────────────────────────────────────────────┐
  │ WHEN              │ JOB                  │ WHAT HAPPENS              │
  ├──────────────────────────────────────────────────────────────────────┤
  │ Monday  02:00     │ weekly_strategy      │ MarketingIntelligenceAgent│
  │                   │                      │ → Orchestrator plans      │
  │                   │                      │   topics + times → DB     │
  ├──────────────────────────────────────────────────────────────────────┤
  │ Every 15 min      │ post_due_now         │ For each due post:        │
  │                   │                      │   MI context → Content    │
  │                   │                      │   Agent → Posting Agent   │
  │                   │                      │   → mark 'posted'         │
  ├──────────────────────────────────────────────────────────────────────┤
  │ Mon/Wed/Fri 09:00 │ growth_campaign      │ GrowthAgent               │
  │  (tier-aware)     │                      │   run_growth_campaign     │
  │  Free: off        │                      │   Starter: Tue/Thu        │
  │  Growth/Pro: daily│                      │   Growth+Pro: daily       │
  ├──────────────────────────────────────────────────────────────────────┤
  │ 1st (or 1&15)     │ growth_hack_strategy │ GrowthHackingAgent        │
  │  03:00 (tier)     │                      │   generate_strategy       │
  │  Free: off        │                      │   Starter/Growth: monthly │
  │                   │                      │   Pro: bi-weekly          │
  ├──────────────────────────────────────────────────────────────────────┤
  │ Tier-based        │ email_campaign       │ EmailMarketingAgent       │
  │  10:00            │                      │   plan_campaign           │
  │  Free: off        │                      │   Starter: bi-weekly      │
  │  Growth: 2×/wk    │                      │   Pro: weekly             │
  ├──────────────────────────────────────────────────────────────────────┤
  │ Sunday  23:00     │ weekly_analytics     │ AnalyticsAgent            │
  │                   │                      │   generate_report         │
  └──────────────────────────────────────────────────────────────────────┘

ON-DEMAND  (admin panel — POST /admin/scheduler/run/<job>?client_id=...):
  Any job can be triggered immediately via run_now(job_type, client_id).

══════════════════════════════════════════════════════════════════════════════
AGENT DEPENDENCY / DATA-FLOW GRAPH
══════════════════════════════════════════════════════════════════════════════

  [MarketingIntelligenceAgent]
    │  generate_weekly_strategy(niche, platforms, themes)
    │  → ContentStrategy(ideas, themes, platform_focus, ...)
    ↓
  [ContentCalendarOrchestrator]
    │  generate_calendar(marketing_strategy=strategy)   ← SEEDED with ideas
    │  → CalendarAgent.get_optimal_posting_times()     ← timing from RAG
    │  → ScheduledContentPiece[] with pre-seeded idea per slot
    ↓
  [ContentCalendarOrchestrator.generate_all_content]
    │  per slot: ContentCreationAgent.generate_from_idea(seeded_idea)
    │  → GeneratedContent (text, hashtags, ...)
    ↓
  [ContentCalendarOrchestrator.post_all_approved]
    │  PostingAgent.post_content(ContentPost)
    │  → Tier 1 (Meta direct) / Tier 2 (Late API) / Tier 3 (manual queue)
    ↓
  [AnalyticsAgent.generate_report]   ← every Sunday, reads what was posted
    → CrossPlatformReport (followers, reach, insights, recommendations)

  [GrowthAgent]  ← Mon/Wed/Fri, independent pipeline
    find_competitor_followers / find_hashtag_users
    → score_target_quality → execute_follow_action / execute_engagement_action

══════════════════════════════════════════════════════════════════════════════
"""

import os
import json
import asyncio
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any

try:
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    from apscheduler.triggers.cron import CronTrigger
    from apscheduler.triggers.date import DateTrigger
    from apscheduler.triggers.interval import IntervalTrigger
    APSCHEDULER_AVAILABLE = True
except ImportError:
    APSCHEDULER_AVAILABLE = False
    print("⚠️  APScheduler not installed. Run: pip install apscheduler>=3.10.0")

# ── paths ─────────────────────────────────────────────────────────────────────
CONFIG_DIR = Path("storage/scheduler_config")
LOG_DIR = Path("logs")
CONFIG_DIR.mkdir(parents=True, exist_ok=True)
LOG_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [scheduler] %(levelname)s %(message)s",
    handlers=[
        logging.FileHandler("logs/scheduler.log"),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger("agent_scheduler")


# ── default per-client config ─────────────────────────────────────────────────

DEFAULT_CONFIG: Dict[str, Any] = {
    # Platforms to include in weekly calendar
    "platforms": ["instagram", "tiktok", "linkedin"],
    # Posting frequency per platform per day (best-practice defaults for all platforms)
    "posts_per_platform_per_day": {
        "instagram": 1,
        "tiktok":    2,
        "linkedin":  1,
        "facebook":  1,
        "twitter":   3,
        "threads":   1,
        "youtube":   1,
    },
    # Client timezone (pytz string)
    "timezone": os.getenv("DEFAULT_TIMEZONE", "America/New_York"),
    # Calendar duration in days (generated each Monday)
    "calendar_duration_days": 7,
    # Whether to auto-approve generated content (bypasses manual review)
    "auto_approve": True,
    # Whether to auto-post approved content immediately
    "auto_post": True,
    # Growth agent enabled
    "growth_enabled": True,
    # Platforms for growth campaigns
    "growth_platforms": ["instagram"],
    # Analytics: Instagram & Facebook creds (set per-client if available)
    "instagram_credentials": None,    # {"ig_user_id": "...", "access_token": "..."}
    "facebook_credentials": None,     # {"page_id": "...", "page_token": "..."}
    # Schedule overrides (24h format, local time in client timezone)
    "weekly_strategy_dow": "mon",     # day-of-week for strategy generation
    "weekly_strategy_hour": 2,
    "daily_generate_hour": 5,
    "daily_approve_hour": 7,
    "daily_approve_minute": 30,
    "daily_post_hour": 8,
    "growth_hour": 9,
    "analytics_dow": "sun",
    "analytics_hour": 23,
    # Email support agent
    "email_support_enabled": False,   # enable after Gmail OAuth is set up
    "email_inbox_check_hours": 3,     # how often to check the inbox
}


# ── Tier-based schedule mappings ──────────────────────────────────────────────
# None = agent disabled for that tier.  Values are APScheduler CronTrigger kwargs.

GROWTH_CAMPAIGN_SCHEDULE: Dict[str, Optional[Dict[str, Any]]] = {
    "free":    None,                                          # disabled
    "starter": {"day_of_week": "tue,thu"},                    # 2×/wk
    "growth":  {"day_of_week": "mon,tue,wed,thu,fri,sat,sun"},# daily
    "pro":     {"day_of_week": "mon,tue,wed,thu,fri,sat,sun"},# daily
}

GROWTH_HACK_SCHEDULE: Dict[str, Optional[Dict[str, Any]]] = {
    "free":    None,                                          # disabled
    "starter": {"day": "1"},                                  # 1st of month
    "growth":  {"day": "1"},                                  # 1st of month
    "pro":     {"day": "1,15"},                               # bi-weekly
}

EMAIL_CAMPAIGN_SCHEDULE: Dict[str, Optional[Dict[str, Any]]] = {
    "free":    None,                                          # disabled
    "starter": {"day": "1,15"},                               # bi-weekly  (2 campaigns/mo)
    "growth":  {"day_of_week": "tue,fri"},                    # 2×/wk     (8 campaigns/mo)
    "pro":     {"day_of_week": "wed"},                        # weekly    (unlimited)
}

# hours between inbox polls — None = disabled
EMAIL_INBOX_POLL_HOURS: Dict[str, Optional[int]] = {
    "free":    None,     # disabled
    "starter": 2,        # every 2 h
    "growth":  1,        # every hour
    "pro":     1,        # every hour (same, but bigger batch)
}


def _get_client_tier(client_id: str) -> str:
    """Look up plan_tier from the DB for a client.  Returns 'free' on error."""
    try:
        from database.db import SessionLocal
        from database.models import ClientProfile
        _db = SessionLocal()
        try:
            _prof = _db.query(ClientProfile).filter(ClientProfile.client_id == client_id).first()
            if not _prof:
                log.warning(f"[{client_id}] _get_client_tier: no profile found — defaulting to 'free'")
                return "free"
            tier = getattr(_prof, "plan_tier", "free") or "free"
            return tier
        finally:
            _db.close()
    except Exception as e:
        log.warning(f"[{client_id}] _get_client_tier DB error — defaulting to 'free': {e}")
        return "free"


def _check_quota(client_id: str, metric: str) -> bool:
    """Return True if the client still has quota for the given metric."""
    try:
        from database.db import SessionLocal
        from database.models import ClientProfile
        from utils.plan_limits import check_limit
        _db = SessionLocal()
        try:
            _prof = _db.query(ClientProfile).filter(ClientProfile.client_id == client_id).first()
            if not _prof:
                return False
            ok, msg = check_limit(_prof, metric)
            if not ok:
                log.info(f"[{client_id}] Quota exhausted for '{metric}': {msg}")
            return ok
        finally:
            _db.close()
    except Exception as e:
        log.warning(f"[{client_id}] Quota check failed for '{metric}': {e}")
        return False


def _load_config(client_id: str) -> Dict[str, Any]:
    # 1. Try PostgreSQL first (survives Railway redeploys)
    try:
        from database.db import SessionLocal
        from database.models import ClientProfile
        _db = SessionLocal()
        try:
            _prof = _db.query(ClientProfile).filter(ClientProfile.client_id == client_id).first()
            if _prof and getattr(_prof, "scheduler_config_json", None):
                saved = json.loads(_prof.scheduler_config_json)
                return {**DEFAULT_CONFIG, **saved}
        finally:
            _db.close()
    except Exception:
        pass
    # 2. Fall back to filesystem
    path = CONFIG_DIR / f"{client_id}.json"
    if path.exists():
        try:
            with open(path) as f:
                saved = json.load(f)
            # Back-fill DB
            _backfill_scheduler_config(client_id, saved)
            return {**DEFAULT_CONFIG, **saved}
        except Exception as e:
            log.warning(f"Could not load config for {client_id}: {e}")
    return dict(DEFAULT_CONFIG)


def _backfill_scheduler_config(client_id: str, config: Dict[str, Any]):
    """Back-fill scheduler config from file into PostgreSQL."""
    try:
        from database.db import SessionLocal
        from database.models import ClientProfile
        _db = SessionLocal()
        try:
            _prof = _db.query(ClientProfile).filter(ClientProfile.client_id == client_id).first()
            if _prof:
                _prof.scheduler_config_json = json.dumps(config)
                _db.commit()
        finally:
            _db.close()
    except Exception:
        pass


def save_config(client_id: str, config: Dict[str, Any]):
    """Persist a client's scheduler config (DB primary, file cache)."""
    # 1. Write to PostgreSQL (primary — survives Railway redeploys)
    try:
        from database.db import SessionLocal
        from database.models import ClientProfile
        _db = SessionLocal()
        try:
            _prof = _db.query(ClientProfile).filter(ClientProfile.client_id == client_id).first()
            if _prof:
                _prof.scheduler_config_json = json.dumps(config)
                _db.commit()
        finally:
            _db.close()
    except Exception:
        pass
    # 2. Filesystem cache
    path = CONFIG_DIR / f"{client_id}.json"
    with open(path, "w") as f:
        json.dump(config, f, indent=2)
    log.info(f"Scheduler config saved for {client_id}")


def update_client_config_file(client_id: str, updates: Dict[str, Any]) -> None:
    """
    Module-level convenience: patch a client's persisted scheduler config
    without requiring a running AgentScheduler instance.

    Called by ``utils.platform_events`` when a platform is connected /
    disconnected so future weekly jobs pick up the correct platform list.
    """
    cfg = _load_config(client_id)
    cfg.update(updates)
    save_config(client_id, cfg)
    log.info(f"[{client_id}] Scheduler config updated (module-level): {updates}")


# ── job implementations ───────────────────────────────────────────────────────

def _load_latest_analytics_report(client_id: str) -> str:
    """
    Load the most recent weekly analytics report for a client and return a
    formatted performance-context string that can be injected into the
    weekly strategy prompt so Claude is aware of what worked last week.
    Returns an empty string when no report exists (first run, etc.).
    """
    try:
        report_dir = Path("storage/analytics") / client_id
        if not report_dir.exists():
            return ""
        report_files = sorted(report_dir.glob("report_*.json"), reverse=True)
        if not report_files:
            return ""
        import json as _j
        report = _j.loads(report_files[0].read_text())

        lines = ["\n### LAST WEEK'S SOCIAL MEDIA PERFORMANCE\n"]

        best = report.get("best_platform", "")
        worst = report.get("worst_platform", "")
        if best:
            lines.append(f"Best performing platform: {best}")
        if worst:
            lines.append(f"Lowest performing platform: {worst}")

        platforms_data = report.get("platforms", [])
        if platforms_data:
            lines.append("\nPer-platform metrics:")
            for p in platforms_data:
                name = p.get("platform", "unknown")
                er   = p.get("engagement_rate", 0)
                al   = p.get("avg_likes", 0)
                ac   = p.get("avg_comments", 0)
                top  = p.get("top_post_id", "")
                line = (f"  {name}: engagement_rate={er:.2f}%, "
                        f"avg_likes={al:.0f}, avg_comments={ac:.0f}")
                if top:
                    line += f", best_post_id={top}"
                lines.append(line)

        insights = report.get("insights", [])
        if insights:
            lines.append("\nKey insights from last week:")
            for ins in insights[:3]:
                lines.append(f"  - {ins}")

        recommendations = report.get("recommendations", [])
        if recommendations:
            lines.append("\nRecommended adjustments for this week:")
            for rec in recommendations[:3]:
                lines.append(f"  - {rec}")

        context = "\n".join(lines)
        log.info(f"[{client_id}] Loaded analytics report '{report_files[0].name}' for strategy seeding")
        return context
    except Exception as _e:
        log.warning(f"[{client_id}] Could not load analytics report for strategy seeding: {_e}")
        return ""


async def job_weekly_strategy(client_id: str):
    """
    Monday 02:00 — MarketingIntelligenceAgent → ContentCalendarOrchestrator

    Data flow:
      1. Load client niche from ClientProfileManager
      2. MarketingIntelligenceAgent.generate_weekly_strategy(niche, platforms)
         → ContentStrategy with ideas, themes, platform_focus
      3. Save strategy JSON to storage/strategies/{client_id}/latest.json
      4. ContentCalendarOrchestrator.generate_calendar(marketing_strategy=strategy)
         → calendar slots seeded with real marketing ideas (not blank)
         → CalendarAgent provides RAG-backed optimal posting times per platform
      5. ContentCalendarOrchestrator.generate_all_content(calendar_id)
         → each slot: ContentCreationAgent.generate_from_idea(seeded_idea)
         → sets status to READY
    """
    # Quick lock check stays on the event loop (lightweight, no I/O)
    try:
        from api.calendar_routes import _is_generation_running
        if _is_generation_running(client_id):
            log.warning(f"[{client_id}] Skipping weekly_strategy: another generation is already running")
            return
    except ImportError:
        pass
    # Offload the heavy work to the agent thread pool
    from utils.agent_executor import submit_agent_task
    await submit_agent_task(_job_weekly_strategy_work, client_id, timeout=1200)


async def _job_weekly_strategy_work(client_id: str):
    """Heavy work for weekly_strategy — runs in agent thread pool."""
    log.info(f"[{client_id}] ▶ weekly_strategy starting (thread pool)")
    config = _load_config(client_id)
    try:
        from api.calendar_routes import _acquire_gen_lock, _release_gen_lock
        _acquire_gen_lock(client_id, f"scheduler_{client_id}")
    except ImportError:
        pass
    try:
        # Load client profile
        from agents.client_profile_manager import ClientProfileManager
        pm = ClientProfileManager()
        profile = pm.get_client_profile(client_id)
        niche = None
        if profile:
            niche = getattr(profile.niche, "value", None) or getattr(profile, "description", None) or "business"

        niche = niche or "general business"

        # ── Use live connected platforms rather than stale config ─────
        try:
            from utils.connected_platforms import get_connected_platforms
            live_platforms = get_connected_platforms(client_id)
            if live_platforms:
                platforms = live_platforms
                log.info(f"[{client_id}] Live connected platforms: {platforms}")
            else:
                platforms = config["platforms"]
                log.warning(f"[{client_id}] No connected platforms detected — using config: {platforms}")
        except Exception as _cp_err:
            platforms = config["platforms"]
            log.warning(f"[{client_id}] Could not fetch connected platforms: {_cp_err} — using config: {platforms}")

        # Merge per-day frequency: config defaults + best-practice fallback for any new platform
        from agents.rag_system import PLATFORM_DEFAULT_FREQUENCY
        base_freq = dict(config["posts_per_platform_per_day"])
        posts_per_platform_per_day = {
            p: base_freq.get(p, PLATFORM_DEFAULT_FREQUENCY.get(p, 1))
            for p in platforms
        }

        # ── INCREMENTAL MODE: only generate for platforms with no scheduled posts ─
        # The manual "Generate AI Calendar" button always does a full overwrite.
        # The scheduler only fills gaps — platforms that already have content are skipped.
        duration_days = config["calendar_duration_days"]
        try:
            from api.calendar_routes import _get_platforms_needing_generation
            platforms_needed = _get_platforms_needing_generation(
                client_id, platforms, duration_days, config["timezone"]
            )
            if not platforms_needed:
                log.info(f"[{client_id}] ✅ All platforms already have scheduled content "
                         f"for the next {duration_days} days — skipping generation")
                return
            skipped = [p for p in platforms if p not in platforms_needed]
            if skipped:
                log.info(f"[{client_id}] Platforms already scheduled: {skipped}. "
                         f"Generating only for: {platforms_needed}")
            platforms = platforms_needed
            # Trim frequency map to only the platforms we're generating for
            posts_per_platform_per_day = {
                p: posts_per_platform_per_day[p]
                for p in platforms if p in posts_per_platform_per_day
            }
        except ImportError:
            log.warning(f"[{client_id}] Could not import gap-fill check — generating for all platforms")
        except Exception as _gap_err:
            log.warning(f"[{client_id}] Gap-fill check failed: {_gap_err} — generating for all platforms")

        log.info(f"[{client_id}] Generating calendar plan (platforms={platforms})")

        # ── Calendar Orchestration (plan-only: platform + type + time) ─
        from agents.content_calendar_orchestrator import ContentCalendarOrchestrator
        orch = ContentCalendarOrchestrator(
            client_id=client_id,
            timezone=config["timezone"],
            load_existing_calendars=False,
        )

        week_label = datetime.now().strftime("Week of %b %d, %Y")
        calendar = await orch.generate_calendar(
            name=f"{client_id} — {week_label}",
            platforms=platforms,
            duration_days=duration_days,
            posts_per_platform_per_day=posts_per_platform_per_day,
            auto_approve=config["auto_approve"],
            auto_post=config["auto_post"],
            use_marketing_agent=False,         # topics determined JIT at post time
        )
        log.info(f"[{client_id}] Calendar created: {calendar.calendar_id} ({calendar.total_posts} slots)")

        # ── Step 3: Bridge plan-only slots to DB (skip content gen) ──
        # Content will be generated JIT at post time or by daily 05:00 safety net
        log.info(f"[{client_id}] Bridging {calendar.total_posts} planned slots to DB…")
        try:
            from api.calendar_routes import _bridge_pieces_to_jsonl
            if calendar.scheduled_content:
                bridged = _bridge_pieces_to_jsonl(client_id, calendar.scheduled_content)
                log.info(f"[{client_id}] Bridged {bridged} planned posts to scheduled_posts DB")
        except Exception as _bridge_err:
            log.warning(f"[{client_id}] Bridge to JSONL failed: {_bridge_err}")
        log.info(f"[{client_id}] ✅ weekly_strategy complete — {calendar.total_posts} planned posts")

        # ── Send notification about the new weekly calendar ────────────
        try:
            import importlib as _imp_strat
            _nm_mod_strat = _imp_strat.import_module("utils.notification_manager")
            _NM_strat = getattr(_nm_mod_strat, "NotificationManager", None)
            if _NM_strat:
                _nm_strat = _NM_strat(client_id)
                _plat_list = ", ".join(platforms) if platforms else "your connected platforms"
                await _nm_strat.send_growth_notification(
                    notification_type="system",
                    title="📅 Weekly Content Calendar Generated",
                    message=(
                        f"Your content calendar for {week_label} has been created.\n\n"
                        f"Total posts scheduled: {calendar.total_posts}\n"
                        f"Platforms: {_plat_list}\n"
                        f"Posts per platform per day: {posts_per_platform_per_day}\n"
                        f"Duration: {duration_days} days\n"
                        f"Auto-approve: {'Yes' if config.get('auto_approve') else 'No'}\n"
                        f"Auto-post: {'Yes' if config.get('auto_post') else 'No'}\n\n"
                        f"Content will be generated automatically at each post's scheduled time. "
                        f"Review and edit posts before they go live."
                    ),
                    priority="medium",
                    action_url="/calendar",
                    action_label="View Calendar",
                    action_type="internal_link",
                    extra_meta={
                        "job_name": "weekly_strategy",
                        "event_time": datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S'),
                    },
                )
        except Exception as _notif_strat_err:
            log.warning(f"[{client_id}] Strategy notification failed: {_notif_strat_err}")

    except Exception as e:
        log.error(f"[{client_id}] ❌ weekly_strategy failed: {e}", exc_info=True)
    finally:
        try:
            _release_gen_lock(client_id)
        except Exception:
            pass

async def job_daily_generate(client_id: str):
    """Legacy stub — kept so run_now('daily_generate', …) doesn't error.

    Content generation now happens JIT inside job_post_due_now at each
    post's scheduled time.  Nothing to do here.
    """
    log.info(f"[{client_id}] daily_generate is a no-op — content generates JIT at post time")


async def job_daily_approve(client_id: str):
    """Legacy stub — kept so run_now('daily_approve', …) doesn't error.

    There is no separate approval step; posts go planned → posted in one
    shot inside job_post_due_now.
    """
    log.info(f"[{client_id}] daily_approve is a no-op — posts go planned → posted directly")


async def job_post_due_now(client_id: str):
    """
    Every 15 minutes — the SINGLE execution point for all calendar posts.
    Offloads heavy AI work to the agent thread pool.
    """
    from utils.agent_executor import submit_agent_task
    await submit_agent_task(_job_post_due_now_work, client_id, timeout=900)


async def _job_post_due_now_work(client_id: str):
    """Heavy work for post_due_now — runs in agent thread pool.

    IMPORTANT: Railway containers run in UTC.  Posts are stored with
    timezone-aware ISO strings (e.g. "2026-03-06T08:30:00-05:00" for
    Eastern).  We must do ALL comparisons in the same timezone.
    """
    config = _load_config(client_id)

    # ── Timezone-aware "now" in the client's configured timezone ──────
    import pytz
    client_tz = pytz.timezone(config.get("timezone", "America/New_York"))
    now = datetime.now(pytz.utc).astimezone(client_tz)
    window_start = now
    window_end = now + timedelta(minutes=15)

    log.info(f"[{client_id}] ▶ post_due_now check: "
             f"{window_start:%Y-%m-%d %H:%M %Z} – {window_end:%H:%M %Z}")

    try:
        from database.db import SessionLocal
        from database.models import ScheduledPost

        db = SessionLocal()
        try:
            # Grab all posts that haven't been posted yet
            candidates = db.query(ScheduledPost).filter(
                ScheduledPost.client_id == client_id,
                ScheduledPost.status.in_(["planned", "scheduled", "approved"]),
            ).all()

            due_posts = []
            for p in candidates:
                try:
                    raw = (p.scheduled_time or "").strip()
                    if not raw:
                        continue
                    st = datetime.fromisoformat(raw)
                    # If stored without tzinfo, assume client timezone
                    if st.tzinfo is None:
                        st = client_tz.localize(st)
                    else:
                        # Convert to client tz so comparison is apples-to-apples
                        st = st.astimezone(client_tz)
                    if window_start <= st < window_end:
                        due_posts.append(p)
                    elif st < window_start:
                        # ── Catch-up: post was scheduled in the past but
                        #    never fired (server downtime, bug, etc.) ──
                        due_posts.append(p)
                        log.warning(f"[{client_id}] Catch-up: post {p.id} was "
                                    f"due at {st:%Y-%m-%d %H:%M %Z}, adding now")
                except (ValueError, TypeError, AttributeError) as _pe:
                    log.warning(f"[{client_id}] Cannot parse scheduled_time "
                                f"'{getattr(p, 'scheduled_time', '?')}' for "
                                f"post {getattr(p, 'id', '?')}: {_pe}")
                    continue

            log.info(f"[{client_id}] post_due_now: {len(candidates)} candidates, "
                     f"{len(due_posts)} due in window (incl. catch-up)")

            if not due_posts:
                return

            log.info(f"[{client_id}] {len(due_posts)} post(s) due — executing pipeline")

            # ── Load MI + Content + Posting agents once for the batch ──
            from agents.marketing_intelligence_agent import MarketingIntelligenceAgent
            from agents.content_agent import ContentCreationAgent, ContentRequest
            from agents.posting_agent import PostingAgent, ContentPost
            from agents.client_profile_manager import ClientProfileManager

            profile_mgr = ClientProfileManager()
            profile = profile_mgr.get_client_profile(client_id)

            mi = MarketingIntelligenceAgent(client_id=client_id)
            content_agent = ContentCreationAgent(client_id=client_id)
            poster = PostingAgent(client_id=client_id)

            # Resolve niche once
            niche = "business"
            if profile:
                _raw = getattr(profile, "niche", None)
                niche = (
                    getattr(_raw, "value", None)
                    or (str(_raw) if _raw else None)
                    or getattr(profile, "business_description", None)
                    or "business"
                )
                niche = niche.replace("_", " ")

            # Build business context string once
            biz_ctx = ""
            if profile:
                parts = []
                for attr, label in [
                    ("business_description", "Business"),
                    ("business_name", "Name"),
                    ("tone", "Tone"),
                ]:
                    v = getattr(profile, attr, None)
                    if v:
                        parts.append(f"{label}: {v}")
                _kw = getattr(profile, "keywords", None)
                if _kw and isinstance(_kw, list) and _kw:
                    parts.append(f"Keywords: {', '.join(_kw)}")
                _pil = getattr(profile, "content_pillars", None)
                if _pil and isinstance(_pil, list) and _pil:
                    parts.append(f"Pillars: {', '.join(_pil)}")
                biz_ctx = "\n".join(parts)

            #  Gather real-time intelligence ONCE for the whole batch (same niche)
            mi_intelligence = ""
            try:
                keywords = [niche]
                if profile:
                    _kw = getattr(profile, "keywords", None)
                    if _kw and isinstance(_kw, list):
                        keywords = _kw[:3]
                intel = await mi.gather_all_intelligence(niche, keywords)
                pieces = []
                for item in (intel.get("news") or [])[:3]:
                    pieces.append(f"- {item.get('title', '')} ({item.get('source', '')})")
                for item in (intel.get("youtube_trends") or [])[:2]:
                    pieces.append(f"- YouTube trend: {item.get('title', '')}")
                if pieces:
                    mi_intelligence = "Recent industry intelligence:\n" + "\n".join(pieces)
            except Exception as _mi_err:
                log.warning(f"[{client_id}] MI intelligence gathering skipped: {_mi_err}")

            posted = 0
            failed = 0
            manual = 0
            _fail_errors = []  # collect per-platform error messages
            _fail_details = []  # structured: [{"item", "error", "time"}]

            # Sort by platform so same-platform posts are grouped
            # (allows targeted inter-post delay to avoid API rate limits)
            due_posts.sort(key=lambda x: (x.platform or "").lower())
            _prev_platform = None

            for p in due_posts:
                # ── Inter-post delay: 60s between same-platform posts ────
                _cur_plat = (p.platform or "").lower()
                if _prev_platform and _cur_plat == _prev_platform:
                    log.info(f"[{client_id}] ⏳ 60s delay before next {_cur_plat} post")
                    await asyncio.sleep(60)
                _prev_platform = _cur_plat
                try:
                    # ── Step 1: Build rich context for content generation ───
                    context_parts = []
                    if biz_ctx:
                        context_parts.append(biz_ctx)
                    if mi_intelligence:
                        context_parts.append(mi_intelligence)
                    if p.topic:
                        context_parts.append(f"Post topic/hook: {p.topic}")
                    context_str = "\n\n".join(context_parts)

                    # ── Step 2: Generate content via Content Creation Agent ─
                    # Only generate if caption is empty (manual edits preserved)
                    _ctype = (p.content_type or "post").lower()
                    _plat  = (p.platform or "instagram").lower()
                    if not (p.caption or "").strip():
                        # Build a content-type-aware topic so AI writes the
                        # right format (reel hook vs tweet vs article etc.)
                        _type_hints = {
                            "reel":     "short-form vertical video hook/script",
                            "story":    "casual ephemeral story caption",
                            "carousel": "multi-slide educational carousel",
                            "tweet":    "concise punchy tweet",
                            "thread":   "multi-tweet thread narrative",
                            "short":    "YouTube Short hook",
                            "shorts":   "YouTube Short hook",
                            "video":    "engaging video caption",
                            "article":  "professional long-form article",
                        }
                        _hint = _type_hints.get(_ctype, "")
                        _base_topic = p.topic or "General brand content"
                        _effective_topic = (
                            f"{_base_topic} (Format: {_hint} for {_plat})"
                            if _hint else _base_topic
                        )

                        log.info(f"[{client_id}] Generating {_ctype} content for {_plat} "
                                 f"'{_effective_topic[:80]}' ({p.id})")
                        req = ContentRequest(
                            content_type=_ctype,
                            platform=_plat,
                            topic=_effective_topic,
                            context=context_str,
                            include_hashtags=True,
                            include_cta=True,
                        )
                        result = await content_agent.generate_content(req)
                        p.caption = result.content or ""
                        db.commit()
                    else:
                        log.info(f"[{client_id}] Using existing caption for {p.platform} post {p.id}")

                    # ── Step 3: Ensure media exists ──────────────────────────
                    # Support JSON array in image_url for carousels
                    media = None
                    if p.image_url:
                        try:
                            _parsed = json.loads(p.image_url)
                            if isinstance(_parsed, list):
                                media = _parsed
                            else:
                                media = [p.image_url]
                        except (json.JSONDecodeError, TypeError):
                            media = [p.image_url]

                    # JIT media generation for platforms that require media
                    _MEDIA_REQUIRED = {"instagram", "tiktok", "youtube"}
                    _VIDEO_PLATFORMS = {"tiktok", "youtube", "instagram"}
                    _is_video = _ctype in ("video", "short", "shorts", "reel")

                    # ── Clear stale image URL on video posts ──────────────────
                    # If a previous failed attempt saved an image URL on a post
                    # that requires video (TikTok/YouTube/Instagram Reels), clear
                    # it so video generation re-runs now that FFmpeg is available.
                    _VIDEO_EXTS = (".mp4", ".mov", ".avi", ".mkv", ".webm")
                    if (media and _plat in _VIDEO_PLATFORMS and _is_video):
                        _is_actual_video = any(
                            u.lower().split("?")[0].endswith(_VIDEO_EXTS)
                            for u in (media if isinstance(media, list) else [media])
                        )
                        if not _is_actual_video:
                            log.info(f"[{client_id}] Clearing stale image URL from "
                                     f"video post {p.id} ({_plat}/{_ctype}) — will regenerate as video")
                            p.image_url = ""
                            media = None
                            db.commit()

                    if _plat in _MEDIA_REQUIRED and not media:
                        # ── Video generation path (TikTok / YouTube) ─────────
                        if _plat in _VIDEO_PLATFORMS and _is_video:
                            log.info(f"[{client_id}] No media for {_plat} {_ctype} "
                                     f"post {p.id} — generating video via FacelessGenerator")
                            try:
                                from agents.faceless_generator import (
                                    FacelessGenerator, VideoTier, Platform as FGPlatform,
                                    VideoStyle,
                                )
                                from utils.media_upload import upload_media_file

                                fg = FacelessGenerator(client_id=client_id)
                                # Use caption as script; fall back to topic
                                _script = (p.caption or p.topic or "Trending content")[:1500]

                                # Map platform+content_type to FacelessGenerator Platform enum
                                _fg_plat_map = {
                                    ("tiktok", "video"): FGPlatform.TIKTOK,
                                    ("tiktok", "short"): FGPlatform.TIKTOK,
                                    ("tiktok", "shorts"): FGPlatform.TIKTOK,
                                    ("youtube", "video"): FGPlatform.YOUTUBE,
                                    ("youtube", "short"): FGPlatform.YOUTUBE_SHORT,
                                    ("youtube", "shorts"): FGPlatform.YOUTUBE_SHORT,
                                    ("instagram", "reel"): FGPlatform.INSTAGRAM_REEL,
                                    ("instagram", "video"): FGPlatform.INSTAGRAM_REEL,
                                }
                                _fg_platform = _fg_plat_map.get(
                                    (_plat, _ctype), FGPlatform.TIKTOK
                                )

                                # Use Tier 1 (stock video) — FREE and fastest
                                vid_result = await fg.generate_video(
                                    script=_script,
                                    tier=VideoTier.STOCK_VIDEO,
                                    style=VideoStyle.PROFESSIONAL,
                                    platform=_fg_platform,
                                    include_captions=True,
                                    client_id=client_id,
                                )

                                if vid_result.success and vid_result.local_path:
                                    # Upload local video to get a public URL
                                    _pub_url = await upload_media_file(vid_result.local_path)
                                    if _pub_url:
                                        p.image_url = _pub_url
                                        media = [_pub_url]
                                        db.commit()
                                        log.info(f"[{client_id}] ✅ Generated & uploaded video "
                                                 f"for post {p.id}: {_pub_url[:80]}")
                                    else:
                                        log.warning(f"[{client_id}] Video generated but upload "
                                                    f"failed for post {p.id}")
                                elif vid_result.success and vid_result.url:
                                    # Some tiers may return a URL directly
                                    p.image_url = vid_result.url
                                    media = [vid_result.url]
                                    db.commit()
                                    log.info(f"[{client_id}] ✅ Video URL for post {p.id}: "
                                             f"{vid_result.url[:80]}")
                                elif vid_result.success:
                                    # FFmpeg missing — video visuals generated but not assembled
                                    log.warning(f"[{client_id}] Video generation returned success "
                                                f"but no file (FFmpeg likely missing on server). "
                                                f"Post {p.id} will fall back to image.")
                                else:
                                    log.warning(f"[{client_id}] Video generation failed for "
                                                f"post {p.id}: {vid_result.error}")
                            except Exception as vid_err:
                                log.warning(f"[{client_id}] Video generation error for "
                                            f"post {p.id}: {vid_err}")

                        # ── Image generation fallback (or primary for non-video) ──
                        if not media:
                            log.info(f"[{client_id}] No media for {_plat} {_ctype} "
                                     f"post {p.id} — generating image")
                            try:
                                from agents.image_generator import (
                                    ImageGeneratorAgent, ImageType, ImageQuality,
                                )
                                from utils.ai_config import cap_image_quality as _cap_q
                                img_agent = ImageGeneratorAgent(client_id=client_id)

                                # Use tier-appropriate quality (pro=PREMIUM, starter=STANDARD, etc.)
                                _client_tier = getattr(
                                    db.query(ClientProfile).filter(ClientProfile.client_id == client_id).first(),
                                    "plan_tier", "pro"
                                ) or "pro"
                                _img_quality = _cap_q(ImageQuality.PREMIUM, _client_tier)

                                # Pick size based on content type / platform
                                _size_map = {
                                    "reel": "1080x1920", "story": "1080x1920",
                                    "short": "1080x1920", "shorts": "1080x1920",
                                    "post": "1080x1080", "carousel": "1080x1080",
                                }
                                _img_size = _size_map.get(_ctype, "1080x1080")

                                # Carousel: generate multiple images (3-5 slides)
                                if _ctype == "carousel":
                                    _num_slides = 4  # cover image + 3 content slides
                                    _carousel_urls = []
                                    _base_topic = p.topic or "Brand visual"
                                    _caption_text = (p.caption or "")[:400]

                                    for _slide_i in range(_num_slides):
                                        if _slide_i == 0:
                                            _slide_prompt = (
                                                f"Eye-catching cover slide visual for: {_base_topic}. "
                                                f"Bold, attention-grabbing composition. No text or words in image."
                                            )
                                        else:
                                            _slide_prompt = (
                                                f"Slide {_slide_i + 1} of educational carousel about: {_base_topic}. "
                                                f"Visual metaphor for key point #{_slide_i}. "
                                                f"Clean, informative visual. No text or words in image."
                                            )

                                        _s_result = await img_agent.generate_image(
                                            prompt=_slide_prompt,
                                            image_type=ImageType.GENERAL,
                                            size=_img_size,
                                            platform=_plat,
                                            quality=_img_quality,
                                        )
                                        if _s_result.success and _s_result.url:
                                            _carousel_urls.append(_s_result.url)
                                            log.info(f"[{client_id}] Carousel slide {_slide_i+1}/{_num_slides} ✅")
                                        else:
                                            log.warning(f"[{client_id}] Carousel slide {_slide_i+1} failed: {_s_result.error}")

                                    if _carousel_urls:
                                        import json as _json_carousel
                                        p.image_url = _json_carousel.dumps(_carousel_urls)
                                        media = _carousel_urls
                                        db.commit()
                                        log.info(f"[{client_id}] ✅ Generated {len(_carousel_urls)} carousel images for post {p.id}")
                                    else:
                                        log.warning(f"[{client_id}] All carousel slides failed for post {p.id}")
                                else:
                                    # Single image for non-carousel posts
                                    _vis_prompt = (p.caption or p.topic or "Brand visual")[:300]

                                    img_result = await img_agent.generate_image(
                                        prompt=_vis_prompt,
                                        image_type=ImageType.GENERAL,
                                        size=_img_size,
                                        platform=_plat,
                                        quality=_img_quality,
                                    )
                                    if img_result.success and img_result.url:
                                        p.image_url = img_result.url
                                        media = [img_result.url]
                                        db.commit()
                                        log.info(f"[{client_id}] ✅ Generated image for post {p.id} "
                                                 f"(api={img_result.api_used}): {img_result.url[:80]}")
                                    else:
                                        log.warning(f"[{client_id}] Image generation failed for "
                                                    f"post {p.id}: {img_result.error}")
                            except Exception as img_err:
                                log.warning(f"[{client_id}] Image generation error for "
                                            f"post {p.id}: {img_err}")

                    # Final check — skip if media-required platform still has none
                    if _plat in _MEDIA_REQUIRED and not media:
                        log.warning(f"[{client_id}] {_plat} post {p.id} skipped — no media")
                        p.status = "failed"
                        failed += 1
                        db.commit()
                        continue

                    content_post = ContentPost(
                        content=p.caption or "",
                        platform=p.platform or "instagram",
                        content_type=p.content_type or "post",
                        client_id=client_id,
                        media_urls=media,
                        scheduled_time=p.scheduled_time,
                    )
                    log.info(f"[{client_id}] Posting {_plat}/{_ctype} id={p.id} "
                             f"media={[u[:60] for u in (media or [])]}")
                    post_result = await poster.post_content(content_post)

                    if post_result.success:
                        p.status = "posted"
                        posted += 1
                    elif post_result.status in ("scheduled", "manual_required"):
                        # Not truly posted — queued for manual action or
                        # scheduled via Late API.  Keep as scheduled so user
                        # can see it, or mark a distinct status.
                        p.status = "manual_required"
                        manual += 1
                        log.info(f"[{client_id}] Post {p.id} queued: "
                                 f"{post_result.status} — {post_result.error or 'n/a'}")
                    else:
                        p.status = "failed"
                        failed += 1
                        _err_msg = post_result.error or 'unknown error'
                        _fail_errors.append(f"{_plat}: {_err_msg}")
                        _fail_details.append({
                            "item": f"{_plat} post {p.id} ({(p.content_type or 'post')})",
                            "error": _err_msg,
                            "time": datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC'),
                        })
                        log.warning(f"[{client_id}] Post {p.id} failed: {post_result.error}")

                    db.commit()

                except Exception as post_err:
                    p.status = "failed"
                    failed += 1
                    _fail_errors.append(f"{_plat}: {post_err}")
                    _fail_details.append({
                        "item": f"{_plat} post {p.id} ({(p.content_type or 'post')})",
                        "error": str(post_err),
                        "time": datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC'),
                    })
                    db.commit()
                    log.warning(f"[{client_id}] Post {p.id} error: {post_err}")

            log.info(f"[{client_id}] ✅ post_due_now — posted={posted}, manual={manual}, failed={failed}")

            # ── Send notification about posted content ──────────────────
            if posted > 0 or manual > 0 or failed > 0:
                try:
                    import importlib as _imp_post
                    _nm_mod_post = _imp_post.import_module("utils.notification_manager")
                    _NM_post = getattr(_nm_mod_post, "NotificationManager", None)
                    if _NM_post:
                        _nm_post = _NM_post(client_id)
                        _parts = []
                        if posted:
                            _parts.append(f"{posted} published")
                        if manual:
                            _parts.append(f"{manual} queued for review")
                        if failed:
                            _parts.append(f"{failed} failed")
                        _summary = ", ".join(_parts)
                        _msg = f"Your scheduled content has been processed: {_summary}."
                        if failed:
                            _msg += (
                                f"\n\n{failed} post(s) failed to publish. "
                                f"See the failure details below for each platform, "
                                f"the specific error returned, and when it occurred."
                            )
                        if _fail_errors:
                            _msg += "\n\nError summary: " + "; ".join(_fail_errors[:10])
                        await _nm_post.send_growth_notification(
                            notification_type="post",
                            title=f"Content Posted: {_summary}",
                            message=_msg,
                            priority="high" if failed else "medium",
                            action_url="/calendar",
                            action_label="View Calendar",
                            action_type="internal_link",
                            extra_meta={
                                "job_name": "post_due_now",
                                "event_time": datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S'),
                                "failed_items": _fail_details[:20] if _fail_details else [],
                            },
                        )
                except Exception as _notif_post_err:
                    log.warning(f"[{client_id}] Post notification failed: {_notif_post_err}")

        finally:
            db.close()

    except Exception as e:
        log.error(f"[{client_id}] ❌ post_due_now failed: {e}", exc_info=True)


# Keep the old name as an alias so any existing run_now("daily_post", …) calls still work
job_daily_post = job_post_due_now


async def job_growth_campaign(client_id: str):
    """
    Tier-scheduled growth campaign.  Frequency is set per-tier in add_client().
    Offloads heavy work to agent thread pool.

    NOTE: Even on free tier, the recommendation block (people-to-follow /
    groups-to-join) still runs — those are just AI suggestions displayed in
    notifications and cost nothing.  Only the actual follow/engagement
    campaigns are gated by tier.
    """
    config = _load_config(client_id)
    if not config.get("growth_enabled"):
        return
    from utils.agent_executor import submit_agent_task
    await submit_agent_task(_job_growth_campaign_work, client_id, timeout=600)


async def _job_growth_campaign_work(client_id: str):
    """Heavy work for growth_campaign — runs in agent thread pool.

    Mirrors the API-triggered version in growth_routes.py:
    saves each run to ``GrowthCampaignRun`` and sends a notification.
    """
    config = _load_config(client_id)
    import uuid as _uuid_gc
    import json as _json_gc
    from datetime import datetime as _dt_gc

    log.info(f"[{client_id}] ▶ growth_campaign starting")
    try:
        from agents.growth_agent import GrowthAgent
        from utils.connected_platforms import get_connected_platforms
        agent = GrowthAgent(client_id=client_id)

        # Only run actual follow/engagement campaigns on paid tiers
        tier = _get_client_tier(client_id)
        _has_campaign_schedule = GROWTH_CAMPAIGN_SCHEDULE.get(tier) is not None

        # Only run campaigns on platforms the client has actually connected
        connected = get_connected_platforms(client_id)
        configured = config.get("growth_platforms", ["instagram"])
        platforms = [p for p in configured if p in connected] if connected else configured

        # NOTE: even if `platforms` is empty the recommendation block below
        # must still run — recommendations cover ALL major platforms and are
        # not gated by Late API connections.

        if _has_campaign_schedule:
            for platform in (platforms or []):
                run_id = str(_uuid_gc.uuid4())
                log.info(f"[{client_id}] Running growth campaign on {platform} (run {run_id})")
                # Isolated try/except: a campaign failure must NOT block the
                # follow/group recommendation block that runs after the loop.
                try:
                    result = await agent.run_growth_campaign(
                        platform=platform,
                        max_follows=20,
                        max_engagements=30,
                        dry_run=True,  # no real API connections — dry_run=False blocks 30-90s per target and kills the timeout before recommendations run
                    )
                    log.info(
                        f"[{client_id}] {platform} growth: "
                        f"follows={result.get('follows', 0)}, "
                        f"engagements={result.get('engagements', 0)}, "
                        f"skipped={result.get('skipped', 0)}"
                    )
                except Exception as _camp_err:
                    result = {}
                    log.warning(
                        f"[{client_id}] {platform} run_growth_campaign failed "
                        f"(recommendations will still run): {_camp_err}"
                    )

                # ── Save campaign run to DB (matches growth_routes._save_campaign_to_db) ──
                try:
                    from database.db import SessionLocal as _SL_gc
                    from database.models import GrowthCampaignRun
                    _db_gc = _SL_gc()
                    try:
                        output = {
                            "run_id":     run_id,
                            "client_id":  client_id,
                            "created_at": _dt_gc.utcnow().isoformat(),
                            "platform":   platform,
                            "dry_run":    False,
                            "source":     "scheduler",
                            "result":     result if isinstance(result, dict) else {"raw": str(result)},
                        }
                        _db_gc.add(GrowthCampaignRun(
                            id=run_id,
                            client_id=client_id,
                            platform=platform,
                            dry_run=False,
                            result_json=_json_gc.dumps(output, default=str, ensure_ascii=False),
                            created_at=_dt_gc.utcnow(),
                        ))
                        _db_gc.commit()
                        log.info(f"[{client_id}] Saved growth campaign run {run_id} to DB")
                    except Exception as _db_err:
                        _db_gc.rollback()
                        log.warning(f"[{client_id}] Failed to save growth campaign to DB: {_db_err}")
                    finally:
                        _db_gc.close()
                except Exception as _imp_err:
                    log.warning(f"[{client_id}] DB import error for growth save: {_imp_err}")

                # ── Send notification to user ──
                try:
                    import importlib as _imp_gc
                    _nm_mod = _imp_gc.import_module("utils.notification_manager")
                    _NM = getattr(_nm_mod, "NotificationManager", None)
                    if _NM:
                        _nm = _NM(client_id)
                        _follows = result.get('follows', 0) if isinstance(result, dict) else 0
                        _engagements = result.get('engagements', 0) if isinstance(result, dict) else 0
                        _errors_list = result.get('errors', []) if isinstance(result, dict) else []
                        _campaign_msg = (
                            f"Daily {platform} growth run finished: "
                            f"{_follows} follow(s), {_engagements} engagement(s)."
                        )
                        if _errors_list:
                            _campaign_msg += (
                                f"\n\n{len(_errors_list)} error(s) occurred during this run:\n"
                                + "\n".join(f"• {e}" for e in _errors_list[:10])
                            )
                        else:
                            _campaign_msg += "\n\nNo errors were encountered during this run."
                        _campaign_msg += "\n\nCheck your growth recommendations for new people to follow."
                        await _nm.send_growth_notification(
                            notification_type="growth_tip",
                            title="Growth Campaign Complete ✅",
                            message=_campaign_msg,
                            priority="high" if _errors_list else "medium",
                            action_url="/notifications",
                            action_label="View Recommendations",
                            platform=platform,
                            extra_meta={
                                "job_name": f"growth_campaign ({platform})",
                                "event_time": datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S'),
                                "error_details": "; ".join(str(e) for e in _errors_list[:5]) if _errors_list else "",
                            },
                        )
                except Exception as _notif_err:
                    log.warning(f"[{client_id}] Growth notification failed: {_notif_err}")
        else:
            log.info(f"[{client_id}] Skipping campaigns (tier={tier}) — recommendations will still run")

        # ── Claude-powered follow / group recommendations (daily) ──────
        log.info(f"[{client_id}] >>> Entering recommendation block")
        try:
            from database.db import SessionLocal as _SL_rec
            from database.models import ClientNotification as _CN_rec, RecommendationAction as _RA_rec
            from datetime import timedelta as _td_rec

            _db_rec = _SL_rec()
            try:
                # Only skip if the consolidated DAILY report was already sent
                # today (calendar day, Eastern time).  Using calendar day instead
                # of a rolling window prevents yesterday-evening admin tests from
                # blocking the 9 AM scheduled run.
                from zoneinfo import ZoneInfo as _ZI_rec
                _now_et = _dt_gc.now(_ZI_rec("America/New_York"))
                _today_start_et = _now_et.replace(hour=0, minute=0, second=0, microsecond=0)
                _cutoff = _today_start_et.astimezone(_ZI_rec("UTC")).replace(tzinfo=None)
                recent_recs = (
                    _db_rec.query(_CN_rec.id)
                    .filter(
                        _CN_rec.client_id == client_id,
                        _CN_rec.notification_type == "growth_report",
                        _CN_rec.created_at >= _cutoff,
                    )
                    .first()
                )
                _should_recommend = recent_recs is None
            finally:
                _db_rec.close()

            log.info(f"[{client_id}] >>> Dedup check: _should_recommend={_should_recommend}")
            if _should_recommend:
                # Build per-platform follow quotas from RAG-based safe limits.
                # Recommendations are just notification cards the user acts on
                # manually, so include ALL major platforms — not just API-connected ones.
                from agents.growth_agent import GrowthAgent as _GA_limits
                _ALL_REC_PLATFORMS = ["instagram", "facebook", "tiktok", "twitter_x", "linkedin"]
                _rec_platforms = list(dict.fromkeys(
                    (platforms or []) + [p for p in _ALL_REC_PLATFORMS if p not in (platforms or [])]
                ))
                # Up to 10 per platform — closer to the SAFE_DAILY_FOLLOW_LIMITS.
                # Results are sent as a single consolidated report, not individual notifications.
                _ppl = {
                    p: min(10, _GA_limits.SAFE_DAILY_FOLLOW_LIMITS.get(p, 10))
                    for p in _rec_platforms
                }
                _total = sum(_ppl.values())
                # Groups: up to 2 per group-capable platform, max 8
                _group_plats = [p for p in _rec_platforms if p in _GA_limits.GROUP_CAPABLE_PLATFORMS]
                _num_groups = min(8, max(2, len(_group_plats)))

                # Load previously acted-on names to exclude from Claude prompt
                _db_excl = _SL_rec()
                try:
                    _excluded = [
                        r[0]
                        for r in _db_excl.query(_RA_rec.name)
                        .filter(_RA_rec.client_id == client_id)
                        .all()
                    ]
                finally:
                    _db_excl.close()

                log.info(
                    f"[{client_id}] Generating daily follow/group recommendations via Claude "
                    f"({_total} people across {len(_rec_platforms)} platforms, {_num_groups} groups, "
                    f"{len(_excluded)} exclusions)"
                )
                log.info(f"[{client_id}] >>> Step 1: Calling generate_follow_recommendations...")
                recs = await agent.generate_follow_recommendations(
                    platforms=_rec_platforms,
                    per_platform_limits=_ppl,
                    num_groups=_num_groups,
                    excluded_names=_excluded,
                )
                people = recs.get("people", [])
                groups = recs.get("groups", [])
                log.info(f"[{client_id}] >>> Step 2: Got {len(people)} people, {len(groups)} groups from Claude")

                # Retry once if the first call came back empty
                if not people and not groups:
                    log.warning(
                        f"[{client_id}] ⚠️ First recommendation call returned 0 results — "
                        f"retrying once after 5 s pause…"
                    )
                    import asyncio as _aio_rec
                    await _aio_rec.sleep(5)
                    recs = await agent.generate_follow_recommendations(
                        platforms=_rec_platforms,
                        per_platform_limits=_ppl,
                        num_groups=_num_groups,
                        excluded_names=_excluded,
                    )
                    people = recs.get("people", [])
                    groups = recs.get("groups", [])

                if not people and not groups:
                    log.warning(
                        f"[{client_id}] ⚠️ Recommendations still empty after retry — "
                        f"check ANTHROPIC_API_KEY, TAVILY_API_KEY, and client profile"
                    )
                    try:
                        import importlib as _imp_empty
                        _NM_empty = getattr(
                            _imp_empty.import_module("utils.notification_manager"),
                            "NotificationManager", None
                        )
                        if _NM_empty:
                            await _NM_empty(client_id).send_growth_notification(
                                notification_type="growth_tip",
                                title="Growth Recommendations Delayed ⚠️",
                                message=(
                                    "Today's people-to-follow recommendations couldn't be generated — "
                                    "Claude returned no usable accounts after two attempts. "
                                    "This usually means the AI service is temporarily unavailable or "
                                    "API keys need to be verified.\n\n"
                                    "What to check:\n"
                                    "• ANTHROPIC_API_KEY is set and has remaining credits\n"
                                    "• TAVILY_API_KEY is set and active\n"
                                    "• Your client profile has a valid niche and business description\n\n"
                                    "Recommendations will automatically retry at the next scheduled run."
                                ),
                                priority="medium",
                                action_url="/growth/dashboard",
                                action_label="View Dashboard",
                                extra_meta={
                                    "job_name": "growth_campaign → recommendations",
                                    "event_time": datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S'),
                                    "error_code": "EMPTY_RECOMMENDATIONS",
                                    "error_details": (
                                        "generate_follow_recommendations() returned 0 people and 0 groups "
                                        f"across {len(_rec_platforms)} platforms after 2 attempts (with 5s pause between)."
                                    ),
                                },
                            )
                    except Exception:
                        pass

                # ── Dedup helper: skip if same title was sent in last 30 days ──
                log.info(f"[{client_id}] >>> Step 3: Running 30-day title dedup...")
                _db_dedup = _SL_rec()
                try:
                    _dedup_cutoff = _dt_gc.utcnow() - _td_rec(days=30)
                    _existing = set(
                        r[0]
                        for r in _db_dedup.query(_CN_rec.title)
                        .filter(
                            _CN_rec.client_id == client_id,
                            _CN_rec.notification_type.in_(
                                ["follow_suggestion", "group_opportunity", "growth_report"]
                            ),
                            _CN_rec.created_at >= _dedup_cutoff,
                        )
                        .all()
                    )

                    # Also load permanently acted-on names (followed / dismissed)
                    _acted_on_names = set(
                        r[0].lower()
                        for r in _db_dedup.query(_RA_rec.name)
                        .filter(_RA_rec.client_id == client_id)
                        .all()
                    )
                    _acted_on_urls = set(
                        r[0].lower()
                        for r in _db_dedup.query(_RA_rec.url)
                        .filter(_RA_rec.client_id == client_id, _RA_rec.url.isnot(None))
                        .all()
                        if r[0]
                    )
                finally:
                    _db_dedup.close()
                log.info(f"[{client_id}] >>> Step 3: {len(_existing)} existing titles, {len(_acted_on_names)} acted-on names in dedup set")

                # URL validation already done inside generate_follow_recommendations

                # ── Filter out 30-day duplicates AND permanently acted-on ──
                def _is_new_person(p):
                    title_key = f"Follow: {p.get('name', 'Unknown')}"
                    if title_key in _existing:
                        return False
                    if p.get("name", "").lower() in _acted_on_names:
                        return False
                    if p.get("url", "").lower() in _acted_on_urls:
                        return False
                    return True

                def _is_new_group(g):
                    title_key = f"Join: {g.get('name', 'Unknown')}"
                    if title_key in _existing:
                        return False
                    if g.get("name", "").lower() in _acted_on_names:
                        return False
                    if g.get("url", "").lower() in _acted_on_urls:
                        return False
                    return True

                _new_people = [p for p in people if _is_new_person(p)]
                _new_groups = [g for g in groups if _is_new_group(g)]
                log.info(f"[{client_id}] >>> Step 4: After dedup: {len(_new_people)} people, {len(_new_groups)} groups")

                # ── Build consolidated report ──
                import importlib as _imp_rec
                _nm_mod_rec = _imp_rec.import_module("utils.notification_manager")
                _NM_rec = getattr(_nm_mod_rec, "NotificationManager", None)

                _PLAT_DISPLAY = {
                    "twitter_x": "Twitter/X", "tiktok": "TikTok",
                    "linkedin": "LinkedIn", "instagram": "Instagram",
                    "facebook": "Facebook", "youtube": "YouTube",
                    "threads": "Threads",
                }
                _PLAT_ICON = {
                    "instagram": "\ud83d\udcf7", "facebook": "\ud83d\udc4d",
                    "tiktok": "\ud83c\udfb5", "twitter_x": "\ud83d\udc26",
                    "linkedin": "\ud83d\udcbc", "youtube": "\u25b6\ufe0f",
                    "threads": "\ud83e\uddf5",
                }

                # Group people and groups by platform
                from collections import defaultdict as _dd_rep
                _ppl_by_plat = _dd_rep(list)
                for p in _new_people:
                    _ppl_by_plat[p.get("platform", "other")].append(p)
                _grp_by_plat = _dd_rep(list)
                for g in _new_groups:
                    _grp_by_plat[g.get("platform", "other")].append(g)

                _all_plats = list(dict.fromkeys(
                    list(_ppl_by_plat.keys()) + list(_grp_by_plat.keys())
                ))

                # Build HTML report body
                _html_parts = []
                for plat in _all_plats:
                    _disp = _PLAT_DISPLAY.get(plat, plat.title())
                    _icon = _PLAT_ICON.get(plat, "\ud83c\udf10")
                    _html_parts.append(
                        f"<div style='margin-bottom:16px'>"
                        f"<h3 style='margin:0 0 8px;font-size:15px;color:#1f2937'>"
                        f"{_icon} {_disp}</h3>"
                    )
                    plat_people = _ppl_by_plat.get(plat, [])
                    plat_groups = _grp_by_plat.get(plat, [])

                    if plat_people:
                        _html_parts.append(
                            "<div style='margin-left:8px;margin-bottom:8px'>"
                            "<strong style='font-size:13px;color:#374151'>"
                            "People to Follow</strong>"
                        )
                        for pp in plat_people:
                            _name = pp.get("name", "Unknown")
                            _url = pp.get("url", "")
                            _plat_tag = pp.get("platform", plat)
                            _reason = pp.get("reason", "")[:120]
                            _link = (
                                f"<a href='{_url}' target='_blank' "
                                f"rel='noopener noreferrer' "
                                f"style='color:#2563eb;text-decoration:none;font-weight:600'>"
                                f"{_name}</a>"
                            ) if _url else f"<strong>{_name}</strong>"
                            # Escape quotes for data attributes
                            _esc_name = _name.replace("'", "&#39;").replace('"', '&quot;')
                            _esc_url = _url.replace("'", "&#39;").replace('"', '&quot;')
                            _html_parts.append(
                                f"<div style='padding:6px 0;border-bottom:1px solid #f3f4f6' "
                                f"id='rec-{hash(_name + _url) & 0xFFFFFFFF:08x}'>"
                                f"{_link}"
                                f"<br><span style='font-size:12px;color:#6b7280'>{_reason}</span>"
                                f"<div style='margin-top:4px'>"
                                f"<button onclick=\"recAction(this,'followed')\" "
                                f"data-name=\"{_esc_name}\" data-url=\"{_esc_url}\" data-platform=\"{_plat_tag}\" "
                                f"style='font-size:11px;padding:2px 8px;margin-right:6px;"
                                f"background:#10b981;color:#fff;border:none;border-radius:4px;cursor:pointer'>"
                                f"&#10003; I Followed</button>"
                                f"<button onclick=\"recAction(this,'dismissed')\" "
                                f"data-name=\"{_esc_name}\" data-url=\"{_esc_url}\" data-platform=\"{_plat_tag}\" "
                                f"style='font-size:11px;padding:2px 8px;"
                                f"background:#6b7280;color:#fff;border:none;border-radius:4px;cursor:pointer'>"
                                f"&#10007; Not Interested</button>"
                                f"</div>"
                                f"</div>"
                            )
                        _html_parts.append("</div>")

                    if plat_groups:
                        _html_parts.append(
                            "<div style='margin-left:8px;margin-bottom:8px'>"
                            "<strong style='font-size:13px;color:#374151'>"
                            "Groups &amp; Communities</strong>"
                        )
                        for gg in plat_groups:
                            _gname = gg.get("name", "Unknown")
                            _gurl = gg.get("url", "")
                            _gplat = gg.get("platform", plat)
                            _greason = gg.get("reason", "")[:120]
                            _glink = (
                                f"<a href='{_gurl}' target='_blank' "
                                f"rel='noopener noreferrer' "
                                f"style='color:#2563eb;text-decoration:none;font-weight:600'>"
                                f"{_gname}</a>"
                            ) if _gurl else f"<strong>{_gname}</strong>"
                            _esc_gname = _gname.replace("'", "&#39;").replace('"', '&quot;')
                            _esc_gurl = _gurl.replace("'", "&#39;").replace('"', '&quot;')
                            _html_parts.append(
                                f"<div style='padding:6px 0;border-bottom:1px solid #f3f4f6' "
                                f"id='rec-{hash(_gname + _gurl) & 0xFFFFFFFF:08x}'>"
                                f"{_glink}"
                                f"<br><span style='font-size:12px;color:#6b7280'>{_greason}</span>"
                                f"<div style='margin-top:4px'>"
                                f"<button onclick=\"recAction(this,'followed')\" "
                                f"data-name=\"{_esc_gname}\" data-url=\"{_esc_gurl}\" data-platform=\"{_gplat}\" "
                                f"style='font-size:11px;padding:2px 8px;margin-right:6px;"
                                f"background:#10b981;color:#fff;border:none;border-radius:4px;cursor:pointer'>"
                                f"&#10003; I Joined</button>"
                                f"<button onclick=\"recAction(this,'dismissed')\" "
                                f"data-name=\"{_esc_gname}\" data-url=\"{_esc_gurl}\" data-platform=\"{_gplat}\" "
                                f"style='font-size:11px;padding:2px 8px;"
                                f"background:#6b7280;color:#fff;border:none;border-radius:4px;cursor:pointer'>"
                                f"&#10007; Not Interested</button>"
                                f"</div>"
                                f"</div>"
                            )
                        _html_parts.append("</div>")

                    _html_parts.append("</div>")

                _total_ppl = len(_new_people)
                _total_grp = len(_new_groups)
                log.info(f"[{client_id}] >>> Step 5: Building report - {_total_ppl} people, {_total_grp} groups")

                if _total_ppl == 0 and _total_grp == 0:
                    log.info(f"[{client_id}] No new recommendations after dedup + validation")
                elif _NM_rec:
                    log.info(f"[{client_id}] >>> Step 6: Building HTML report ({_total_ppl} ppl, {_total_grp} grp, {len(_all_plats)} plats)")
                    _report_html = (
                        f"<div style='font-size:14px;color:#374151;margin-bottom:12px'>"
                        f"We found <strong>{_total_ppl} people</strong> to follow and "
                        f"<strong>{_total_grp} groups</strong> to join across "
                        f"{len(_all_plats)} platform{'s' if len(_all_plats) != 1 else ''}."
                        f"</div>"
                        + "\n".join(_html_parts)
                    )
                    log.info(f"[{client_id}] >>> Step 7: HTML built ({len(_report_html)} chars), sending notification...")

                    # Sanitize surrogates that crash PostgreSQL UTF-8 encoding
                    _report_html = _report_html.encode('utf-8', errors='replace').decode('utf-8')

                    _nm_rec = _NM_rec(client_id)
                    _report_title = f"Daily Growth Report \ud83d\udcc8 \u2014 {_total_ppl} people, {_total_grp} groups"
                    _report_title = _report_title.encode('utf-8', errors='replace').decode('utf-8')
                    try:
                        _notif_result = await _nm_rec.send_growth_notification(
                            notification_type="growth_report",
                            title=_report_title,
                            message=_report_html,
                            priority="medium",
                        )
                        if _notif_result and getattr(_notif_result, 'status', None) == 'sent':
                            log.info(f"[{client_id}] >>> Step 8: growth_report notification SENT and SAVED (id={getattr(_notif_result, 'notification_id', '?')})")
                        else:
                            log.error(f"[{client_id}] >>> Step 8: growth_report notification BLOCKED or FAILED — result={_notif_result}")
                    except Exception as _rep_err:
                        log.error(f"[{client_id}] >>> Step 8: growth_report notification FAILED: {_rep_err}", exc_info=True)
                else:
                    log.warning(f"[{client_id}] >>> Step 6: _NM_rec is None — cannot send notification!")

                log.info(
                    f"[{client_id}] \u2705 Sent consolidated growth report: "
                    f"{_total_ppl} people, {_total_grp} groups"
                )
            else:
                log.info(f"[{client_id}] Skipping recommendations — already sent today")
        except Exception as _rec_err:
            log.error(f"[{client_id}] ❌ Recommendation generation failed: {_rec_err}", exc_info=True)
            # Notify the user so they know something went wrong instead of
            # silently failing with no recommendations.
            try:
                import importlib as _imp_fail
                _nm_mod_fail = _imp_fail.import_module("utils.notification_manager")
                _NM_fail = getattr(_nm_mod_fail, "NotificationManager", None)
                if _NM_fail:
                    _nm_fail = _NM_fail(client_id)
                    _err_type = type(_rec_err).__name__
                    _err_str = str(_rec_err)
                    await _nm_fail.send_growth_notification(
                        notification_type="growth_tip",
                        title="Growth Recommendations Failed ⚠️",
                        message=(
                            "Today's people-to-follow and groups-to-join recommendations "
                            "could not be generated due to an error during processing.\n\n"
                            f"Error type: {_err_type}\n"
                            f"Error message: {_err_str[:500]}\n\n"
                            "The system will automatically retry at the next scheduled run. "
                            "If this error persists, check the application logs for a full stack trace."
                        ),
                        priority="high",
                        action_url="/growth/dashboard",
                        action_label="View Dashboard",
                        extra_meta={
                            "job_name": "growth_campaign → recommendations",
                            "event_time": datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S'),
                            "error_code": _err_type,
                            "error_details": _err_str[:1000],
                        },
                    )
            except Exception:
                pass

        log.info(f"[{client_id}] ✅ growth_campaign complete")

    except Exception as e:
        log.error(f"[{client_id}] ❌ growth_campaign failed: {e}", exc_info=True)


async def job_weekly_analytics(client_id: str):
    """
    Sunday 23:00 — Generate analytics report for the week.
    Offloads heavy work to agent thread pool.
    """
    from utils.agent_executor import submit_agent_task
    await submit_agent_task(_job_weekly_analytics_work, client_id, timeout=600)


async def _job_weekly_analytics_work(client_id: str):
    """Heavy work for weekly_analytics — runs in agent thread pool."""
    log.info(f"[{client_id}] ▶ weekly_analytics starting")
    config = _load_config(client_id)

    try:
        from agents.analytics_agent import AnalyticsAgent
        agent = AnalyticsAgent(client_id=client_id)

        ig_creds = config.get("instagram_credentials")
        fb_creds = config.get("facebook_credentials")

        # If creds not in config, try reading from token manager
        if not ig_creds:
            try:
                from api.token_manager import TokenManager
                tm = TokenManager()
                # Look up by client's connections file
                import json as _j
                conn_path = Path("storage/connections") / f"{client_id}.json"
                if conn_path.exists():
                    conn = _j.loads(conn_path.read_text())
                    meta_user_id = conn.get("meta_user_id")
                    ig_account_id = conn.get("ig_account_id")
                    if meta_user_id and ig_account_id:
                        token_data = tm.get_valid_token(meta_user_id)
                        if token_data:
                            ig_creds = {
                                "ig_user_id": ig_account_id,
                                "access_token": token_data.access_token,
                            }
                            log.info(f"[{client_id}] Analytics: resolved IG creds from token manager")
            except Exception as te:
                log.warning(f"[{client_id}] Could not resolve token for analytics: {te}")

        end_date = datetime.now()
        start_date = end_date - timedelta(days=7)

        report = await agent.generate_report(
            start_date=start_date,
            end_date=end_date,
            instagram_credentials=ig_creds,
            facebook_credentials=fb_creds,
        )

        # Save report
        report_dir = Path("storage/analytics") / client_id
        report_dir.mkdir(parents=True, exist_ok=True)
        report_file = report_dir / f"report_{end_date.strftime('%Y_%m_%d')}.json"
        agent.export_report_json(report, str(report_file))
        log.info(f"[{client_id}] ✅ weekly_analytics complete → {report_file}")

        # ── Send notification about the new analytics report ──────────
        try:
            import importlib as _imp_analytics
            _nm_mod_analytics = _imp_analytics.import_module("utils.notification_manager")
            _NM_analytics = getattr(_nm_mod_analytics, "NotificationManager", None)
            if _NM_analytics:
                _nm_analytics = _NM_analytics(client_id)
                # Build a detailed summary from the report
                _best_plat = ""
                _summary_parts = []
                _summary_parts.append(
                    f"Your weekly social media analytics report for "
                    f"{start_date.strftime('%b %d')} – {end_date.strftime('%b %d, %Y')} is ready."
                )
                if hasattr(report, "best_platform"):
                    _best_plat = getattr(report, "best_platform", "")
                elif isinstance(report, dict):
                    _best_plat = report.get("best_platform", "")
                if _best_plat:
                    _summary_parts.append(f"Best performing platform: {_best_plat}.")
                # Pull additional stats if available
                if isinstance(report, dict):
                    _total_reach = report.get("total_reach") or report.get("reach")
                    _total_engagement = report.get("total_engagement") or report.get("engagement")
                    _total_followers = report.get("follower_change") or report.get("followers_gained")
                    if _total_reach:
                        _summary_parts.append(f"Total reach: {_total_reach:,}." if isinstance(_total_reach, (int, float)) else f"Total reach: {_total_reach}.")
                    if _total_engagement:
                        _summary_parts.append(f"Total engagement: {_total_engagement:,}." if isinstance(_total_engagement, (int, float)) else f"Total engagement: {_total_engagement}.")
                    if _total_followers:
                        _summary_parts.append(f"Follower change: {_total_followers:+,}." if isinstance(_total_followers, (int, float)) else f"Follower change: {_total_followers}.")
                _summary_msg = " ".join(_summary_parts)
                await _nm_analytics.send_growth_notification(
                    notification_type="system",
                    title="📊 Weekly Analytics Report Ready",
                    message=_summary_msg,
                    priority="medium",
                    action_url="/analytics",
                    action_label="View Report",
                    action_type="internal_link",
                    extra_meta={
                        "job_name": "weekly_analytics",
                        "event_time": datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S'),
                        "report_id": str(report_file),
                    },
                )
        except Exception as _notif_analytics_err:
            log.warning(f"[{client_id}] Analytics notification failed: {_notif_analytics_err}")

    except Exception as e:
        log.error(f"[{client_id}] ❌ weekly_analytics failed: {e}", exc_info=True)


async def job_email_inbox_check(client_id: str):
    """
    Tier-based polling — fetch inbox via unified email service, store in DB,
    run AI categorization + draft.  Auto-skips if no email is connected.
    """
    # Auto-detect connection (no manual flag needed)
    try:
        from utils.email_service import get_connection
        conn = await get_connection(client_id)
        if not conn:
            return  # no email connected — skip silently
    except Exception:
        return

    from utils.agent_executor import submit_agent_task
    await submit_agent_task(_job_email_inbox_check_work, client_id, timeout=600)


async def _job_email_inbox_check_work(client_id: str):
    """Heavy work for email_inbox_check — runs in agent thread pool.
    Uses unified email_service + stores results in EmailThread / EmailMessageRecord.
    """
    log.info(f"[{client_id}] ▶ email_inbox_check starting")
    try:
        from utils.email_service import fetch_inbox as _fetch
        from database.db import SessionLocal
        from database.models import (
            ClientProfile, EmailThread, EmailMessageRecord,
            EmailCategory, DraftStatus,
        )
        from datetime import datetime as _dt
        import uuid as _uuid

        # Resolve profile_id
        _db = SessionLocal()
        try:
            _prof = _db.query(ClientProfile).filter(
                ClientProfile.client_id == client_id
            ).first()
            if not _prof:
                log.warning(f"[{client_id}] email_inbox_check — no profile found")
                return
            profile_id = _prof.id
        finally:
            _db.close()

        # Fetch unread emails via unified service
        raw_emails = await _fetch(client_id, max_results=20, unread_only=True)
        if not raw_emails:
            log.info(f"[{client_id}] email_inbox_check — 0 new emails")
            return

        db = SessionLocal()
        new_count = 0
        escalated = 0
        try:
            for raw in raw_emails:
                ext_msg_id = raw.get("message_id", "")
                if ext_msg_id:
                    existing = db.query(EmailMessageRecord).filter(
                        EmailMessageRecord.external_message_id == ext_msg_id,
                        EmailMessageRecord.client_profile_id == profile_id,
                    ).first()
                    if existing:
                        continue

                ext_thread_id = raw.get("thread_id", ext_msg_id)
                thread = db.query(EmailThread).filter(
                    EmailThread.external_thread_id == ext_thread_id,
                    EmailThread.client_profile_id == profile_id,
                ).first()

                if not thread:
                    thread = EmailThread(
                        id=_uuid.uuid4().hex,
                        client_profile_id=profile_id,
                        external_thread_id=ext_thread_id,
                        subject=raw.get("subject", "(no subject)"),
                        sender_email=raw.get("sender_email", ""),
                        sender_name=raw.get("sender_name", ""),
                        category=EmailCategory.general,
                        message_count=0,
                        last_message_at=_dt.utcnow(),
                    )
                    db.add(thread)
                    db.flush()

                # AI categorize
                category_str = "general"
                ai_draft = ""
                try:
                    from agents.email_support_agent import EmailSupportAgent
                    agent = EmailSupportAgent(client_id=client_id)
                    cat_result = await agent.categorize_email_text(
                        subject=raw.get("subject", ""),
                        body=raw.get("body", "")[:2000],
                        sender=raw.get("sender_email", ""),
                    )
                    category_str = cat_result.get("category", "general")
                    ai_draft = cat_result.get("draft_reply", "")
                    if category_str in ("support", "complaint", "urgent"):
                        escalated += 1
                except Exception as cat_err:
                    log.warning(f"[{client_id}] categorize failed: {cat_err}")

                try:
                    thread.category = EmailCategory(category_str)
                except Exception:
                    thread.category = EmailCategory.general

                msg_record = EmailMessageRecord(
                    id=_uuid.uuid4().hex,
                    thread_id=thread.id,
                    client_profile_id=profile_id,
                    external_message_id=ext_msg_id,
                    direction="inbound",
                    sender_email=raw.get("sender_email", ""),
                    sender_name=raw.get("sender_name", ""),
                    subject=raw.get("subject", ""),
                    body_text=raw.get("body", ""),
                    ai_category=category_str,
                    ai_draft_reply=ai_draft if ai_draft else None,
                    draft_status=DraftStatus.pending if ai_draft else DraftStatus.none,
                    received_at=_dt.utcnow(),
                )
                db.add(msg_record)
                thread.message_count = (thread.message_count or 0) + 1
                thread.last_message_at = _dt.utcnow()
                new_count += 1

            db.commit()

        except Exception as db_err:
            db.rollback()
            log.error(f"[{client_id}] email DB store error: {db_err}", exc_info=True)
        finally:
            db.close()

        log.info(f"[{client_id}] ✅ email_inbox_check complete — {new_count} new, {escalated} escalated")

        # Notification for escalated emails
        if escalated:
            try:
                import importlib
                nm_mod = importlib.import_module("utils.notification_manager")
                NotificationManager = getattr(nm_mod, "NotificationManager", None)
                if NotificationManager:
                    nm = NotificationManager(client_id)
                    await nm.send_growth_notification(
                        notification_type="message_received",
                        title=f"{escalated} Email(s) Need Attention",
                        message=(
                            f"{escalated} customer email(s) were categorized as requiring immediate attention "
                            f"(support, complaint, or urgent) during the latest inbox check.\n\n"
                            f"Total new emails processed: {new_count}\n"
                            f"Escalated for review: {escalated}\n\n"
                            f"AI draft replies have been generated where possible. "
                            f"Please review and approve or edit them before sending."
                        ),
                        priority="high",
                        action_url="/email?tab=inbox",
                        action_label="Review Emails",
                        extra_meta={
                            "job_name": "email_inbox_check",
                            "event_time": datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S'),
                        },
                    )
            except Exception as ne:
                log.warning(f"[{client_id}] notification send failed: {ne}")

    except Exception as e:
        log.error(f"[{client_id}] ❌ email_inbox_check failed: {e}", exc_info=True)


# ── Growth hacking strategy job ───────────────────────────────────────────────

async def job_growth_hack_strategy(client_id: str):
    """
    Tier-scheduled: generate a growth hacking strategy report.
    Free: off, Starter/Growth: 1st of month, Pro: 1st & 15th.
    Respects growth_strategy quota from plan_limits.
    """
    tier = _get_client_tier(client_id)
    if GROWTH_HACK_SCHEDULE.get(tier) is None:
        log.info(f"[{client_id}] growth_hack skipped — tier '{tier}' disabled")
        return
    if not _check_quota(client_id, "growth_strategy"):
        return
    from utils.agent_executor import submit_agent_task
    await submit_agent_task(_job_growth_hack_work, client_id, timeout=900)


async def _job_growth_hack_work(client_id: str):
    """Heavy work for growth_hack_strategy — runs in agent thread pool."""
    log.info(f"[{client_id}] ▶ growth_hack_strategy starting")
    try:
        from database.db import SessionLocal
        from database.models import ClientProfile
        from agents.growth_hacking_agent import GrowthHackingAgent
        from utils.plan_limits import increment_usage

        _db = SessionLocal()
        try:
            profile = _db.query(ClientProfile).filter(ClientProfile.client_id == client_id).first()
            if not profile:
                log.warning(f"[{client_id}] growth_hack — profile not found")
                return

            tier = getattr(profile, "plan_tier", "pro") or "pro"
            agent = GrowthHackingAgent(client_id=client_id, tier=tier)

            # Only recommend tactics for platforms the client actually uses
            from utils.connected_platforms import get_connected_platforms
            _platforms = get_connected_platforms(client_id)

            _strat_kwargs = dict(
                business_type=profile.niche or "Coaching / Consulting",
                current_situation="Building & growing online presence",
                goal="Grow audience and generate qualified leads",
                budget="low",
                timeline="90 days",
                niche=profile.niche,
                target_audience=getattr(profile, "target_market_description", None),
                current_online_presence=getattr(profile, "website_url", None),
                connected_platforms=_platforms,
            )
            strategy = await agent.generate_strategy(**_strat_kwargs)

            # If Claude failed, the agent returns an error dict with
            # fallback tactics.  Retry once before accepting the fallback.
            if strategy.get("error") and not strategy.get("quick_wins"):
                log.warning(
                    f"[{client_id}] Strategy first attempt failed "
                    f"({strategy['error'][:120]}), retrying once…"
                )
                import asyncio as _aio_strat
                await _aio_strat.sleep(5)
                strategy = await agent.generate_strategy(**_strat_kwargs)
                if strategy.get("error"):
                    log.warning(
                        f"[{client_id}] Strategy retry also failed — "
                        f"saving fallback report ({strategy['error'][:120]})"
                    )

            # ── Persist strategy to PostgreSQL (survives redeploys) ─────
            import uuid as _uuid
            report_id = _uuid.uuid4().hex[:12]
            strategy["report_id"]  = report_id
            strategy["client_id"]  = client_id
            strategy["created_at"] = datetime.utcnow().isoformat()

            from api.growth_routes import _save_report_to_db
            _save_report_to_db(report_id, client_id,
                               "Grow audience and generate qualified leads",
                               strategy)

            # Also write filesystem copy as backup
            try:
                strat_dir = Path("storage/strategies") / client_id
                strat_dir.mkdir(parents=True, exist_ok=True)
                strat_file = strat_dir / f"growth_hack_{datetime.utcnow().strftime('%Y_%m_%d')}.json"
                with open(strat_file, "w") as f:
                    json.dump(strategy, f, indent=2, default=str)
            except Exception as fe:
                log.warning(f"[{client_id}] filesystem backup failed (non-fatal): {fe}")

            # Increment usage counter
            increment_usage(profile, "growth_strategy", _db)
            _db.commit()

            log.info(f"[{client_id}] ✅ growth_hack_strategy complete → DB report {report_id}")

            # ── Send notifications with report link ───────────────────────
            try:
                import importlib
                nm_mod = importlib.import_module("utils.notification_manager")
                NotificationManager = getattr(nm_mod, "NotificationManager", None)
                if NotificationManager:
                    nm = NotificationManager(client_id)
                    # Main notification with link to the saved report
                    await nm.send_growth_notification(
                        notification_type="growth_tip",
                        title="New Growth Strategy Ready",
                        message="Alita generated a fresh growth hacking strategy for your business. Review the tactics and start implementing!",
                        priority="medium",
                        action_url=f"/growth/report/{report_id}",
                        action_label="View Strategy",
                        extra_meta={"report_id": report_id},
                    )
                    # Additional notifications for top quick wins
                    quick_wins = strategy.get("quick_wins") or []
                    for i, tactic in enumerate(quick_wins[:2]):
                        notif_type = "content_idea" if i == 0 else "growth_tip"
                        impact = tactic.get("expected_impact", "medium")
                        prio = "high" if impact in ("high", "massive") else "medium"
                        await nm.send_growth_notification(
                            notification_type=notif_type,
                            title=f"Growth Hack: {tactic.get('title', 'New Tactic')}",
                            message=tactic.get("description", tactic.get("why_it_works", "")),
                            priority=prio,
                            action_url=f"/growth/report/{report_id}",
                            action_label="View Full Report",
                            action_type="internal_link",
                            extra_meta={"report_id": report_id},
                        )
            except Exception as ne:
                log.warning(f"[{client_id}] growth_hack notification failed: {ne}")

        finally:
            _db.close()

    except Exception as e:
        log.error(f"[{client_id}] ❌ growth_hack_strategy failed: {e}", exc_info=True)


# ── Email campaign suggestion job ─────────────────────────────────────────────

async def job_email_campaign_suggestion(client_id: str):
    """
    Tier-scheduled: auto-generate an email campaign plan/suggestion.
    Free: off, Starter: bi-weekly, Growth: 2×/wk, Pro: weekly.
    Respects campaigns_sent quota from plan_limits.
    """
    tier = _get_client_tier(client_id)
    if EMAIL_CAMPAIGN_SCHEDULE.get(tier) is None:
        log.info(f"[{client_id}] email_campaign skipped — tier '{tier}' disabled")
        return
    if not _check_quota(client_id, "campaigns_sent"):
        return
    from utils.agent_executor import submit_agent_task
    await submit_agent_task(_job_email_campaign_work, client_id, timeout=600)


async def _job_email_campaign_work(client_id: str):
    """Heavy work for email_campaign_suggestion — runs in agent thread pool."""
    log.info(f"[{client_id}] ▶ email_campaign_suggestion starting")
    try:
        from database.db import SessionLocal
        from database.models import ClientProfile
        from agents.email_marketing_agent import EmailMarketingAgent
        from utils.plan_limits import increment_usage

        _db = SessionLocal()
        try:
            profile = _db.query(ClientProfile).filter(ClientProfile.client_id == client_id).first()
            if not profile:
                log.warning(f"[{client_id}] email_campaign — profile not found")
                return

            tier = getattr(profile, "plan_tier", "pro") or "pro"
            agent = EmailMarketingAgent(client_id=client_id)
            agent.set_tier(tier)

            # Build a contextual brief from the client profile
            biz_name  = profile.business_name or "your business"
            niche     = profile.niche or "general"
            brief     = (
                f"Generate a high-performing email campaign idea for {biz_name} "
                f"in the {niche} niche. Focus on audience engagement and conversions."
            )

            # Run synchronously (agent is sync)
            import asyncio
            loop = asyncio.get_event_loop()
            from concurrent.futures import ThreadPoolExecutor
            _pool = ThreadPoolExecutor(max_workers=1)

            rec = await loop.run_in_executor(
                _pool,
                lambda: agent.plan_campaign(
                    campaign_type="newsletter",
                    campaign_goal="engagement",
                    target_segment="all_subscribers",
                    content_brief=brief,
                    client_knowledge="",
                    industry=niche,
                ),
            )

            # Persist suggestion
            camp_dir = Path("storage/email_campaigns") / client_id
            camp_dir.mkdir(parents=True, exist_ok=True)
            camp_file = camp_dir / f"suggestion_{datetime.utcnow().strftime('%Y_%m_%d_%H%M')}.json"
            # CampaignRecommendation may be a dataclass — convert if possible
            rec_data = rec.__dict__ if hasattr(rec, "__dict__") else str(rec)
            with open(camp_file, "w") as f:
                json.dump(rec_data, f, indent=2, default=str)

            # Increment usage
            increment_usage(profile, "campaigns_sent", _db)
            _db.commit()

            log.info(f"[{client_id}] ✅ email_campaign_suggestion complete → {camp_file}")

            # Send notification
            try:
                import importlib
                nm_mod = importlib.import_module("utils.notification_manager")
                NotificationManager = getattr(nm_mod, "NotificationManager", None)
                if NotificationManager:
                    nm = NotificationManager(client_id)
                    await nm.send_growth_notification(
                        notification_type="content_idea",
                        title="New Email Campaign Suggestion",
                        message=f"Alita has a new email campaign idea for {biz_name}. Review the plan and launch when ready!",
                        priority="medium",
                        action_url="/email",
                        action_label="View Campaign",
                    )
            except Exception as ne:
                log.warning(f"[{client_id}] email_campaign notification failed: {ne}")

        finally:
            _db.close()

    except Exception as e:
        log.error(f"[{client_id}] ❌ email_campaign_suggestion failed: {e}", exc_info=True)


# ── Monthly usage-counter reset ───────────────────────────────────────────────
# Stripe's invoice.payment_succeeded webhook already resets paid subscribers,
# but free-tier (and edge-case) users never trigger that event.  This daily
# check runs at 00:05 UTC; if today is the 1st of the month it resets every
# profile whose usage_reset_at is still in a prior month.

async def job_monthly_usage_reset():
    """Reset all usage counters for profiles that haven't been reset this month."""
    try:
        from database.db import SessionLocal
        from database.models import ClientProfile
        from datetime import datetime as _dt

        db = SessionLocal()
        now = _dt.utcnow()
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

        profiles = db.query(ClientProfile).all()
        reset_count = 0
        for p in profiles:
            last_reset = p.usage_reset_at
            if last_reset and last_reset >= month_start:
                continue  # already reset this month (e.g. by Stripe webhook)
            p.usage_posts_created = 0
            p.usage_images_created = 0
            p.usage_videos_created = 0
            p.usage_replies_sent = 0
            p.usage_campaigns_sent = 0
            p.usage_research_run = 0
            p.usage_competitive_research = 0
            p.usage_growth_strategy = 0
            p.usage_reset_at = now
            db.add(p)
            reset_count += 1
        if reset_count:
            db.commit()
            log.info(f"✅ Monthly usage reset: {reset_count} profile(s) zeroed")
        else:
            log.info("Monthly usage reset: all profiles already current")
        db.close()
    except Exception as e:
        log.error(f"❌ Monthly usage reset failed: {e}", exc_info=True)


# ── Scheduler class ───────────────────────────────────────────────────────────

class AgentScheduler:
    """
    Central scheduler that owns one AsyncIOScheduler and manages
    per-client job sets.

    Usage
    -----
        scheduler = AgentScheduler()
        await scheduler.start()            # call from app startup event
        scheduler.add_client("acme_corp")  # called after client onboards
        await scheduler.shutdown()         # call from app shutdown event
    """

    def __init__(self):
        if not APSCHEDULER_AVAILABLE:
            self._scheduler = None
            log.warning("APScheduler not available — scheduled jobs disabled")
            return
        self._scheduler = AsyncIOScheduler(timezone=os.getenv("DEFAULT_TIMEZONE", "America/New_York"))
        self._client_ids: List[str] = []

    # ── lifecycle ──────────────────────────────────────────────────────

    async def start(self):
        """Start the scheduler and register jobs for all onboarded clients."""
        if not self._scheduler:
            log.error("CRITICAL: APScheduler not available — no jobs will fire")
            return

        log.info("=" * 60)
        log.info("AgentScheduler starting up …")
        log.info(f"  Server time (UTC)  : {datetime.utcnow():%Y-%m-%d %H:%M:%S}")
        log.info(f"  Scheduler timezone : {self._scheduler.timezone}")
        log.info("=" * 60)

        self._load_all_clients()

        # ── Global job: monthly usage-counter reset (1st of month, 00:05) ──
        self._scheduler.add_job(
            job_monthly_usage_reset,
            CronTrigger(day=1, hour=0, minute=5, timezone=os.getenv("DEFAULT_TIMEZONE", "America/New_York")),
            id="global_monthly_usage_reset",
            replace_existing=True,
            misfire_grace_time=7200,
        )

        # ── Heartbeat: log scheduler health every 6 hours ──────────────
        self._scheduler.add_job(
            self._heartbeat,
            IntervalTrigger(hours=6),
            id="global_heartbeat",
            replace_existing=True,
            misfire_grace_time=3600,
        )

        self._scheduler.start()

        # Log every registered job so we can see exactly what will fire
        all_jobs = self._scheduler.get_jobs()
        log.info(f"✅ AgentScheduler started — {len(self._client_ids)} client(s), "
                 f"{len(all_jobs)} job(s) registered:")
        for j in all_jobs:
            log.info(f"  • {j.id}  next_run={j.next_run_time}")

        # ── Startup sanity check ──────────────────────────────────────
        client_jobs = [j for j in all_jobs if j.id not in ("global_monthly_usage_reset", "global_heartbeat")]
        if not client_jobs and self._client_ids:
            log.error(
                f"🚨 SCHEDULER ALERT: {len(self._client_ids)} client(s) loaded but "
                f"ZERO client jobs registered! Jobs may have silently failed to register."
            )
        elif not self._client_ids:
            log.warning("⚠️ SCHEDULER: No onboarded clients found — no jobs will fire.")

    async def shutdown(self):
        """Gracefully shut down the scheduler."""
        if self._scheduler and self._scheduler.running:
            self._scheduler.shutdown(wait=False)
            log.info("AgentScheduler stopped")

    async def _heartbeat(self):
        """Log scheduler health every 6 hours so we can detect silent failures."""
        if not self._scheduler:
            return
        all_jobs = self._scheduler.get_jobs()
        client_jobs = [j for j in all_jobs if j.id not in ("global_monthly_usage_reset", "global_heartbeat")]
        log.info(
            f"💓 HEARTBEAT: scheduler alive — {len(self._client_ids)} client(s), "
            f"{len(client_jobs)} client job(s), {len(all_jobs)} total job(s)"
        )
        if not client_jobs and self._client_ids:
            log.error(
                f"🚨 HEARTBEAT ALERT: {len(self._client_ids)} client(s) registered "
                f"but ZERO jobs active! Attempting re-registration…"
            )
            for cid in list(self._client_ids):
                try:
                    self.add_client(cid)
                except Exception as e:
                    log.error(f"  Re-registration failed for {cid}: {e}")

    # ── client management ──────────────────────────────────────────────

    def _load_all_clients(self):
        """Load all fully-onboarded clients from database and add their jobs.

        NOTE: We no longer require ``rag_ready == True`` here.  The RAG check
        was silently preventing ALL job registration whenever Qdrant was
        unreachable on Railway, meaning zero posts would ever fire.  Content
        generation still works without RAG (it uses profile + MI intelligence).
        """
        try:
            from database.db import get_db
            from database.models import ClientProfile, OnboardingStatus
            db = next(get_db())
            profiles = db.query(ClientProfile).filter(
                ClientProfile.onboarding_status == OnboardingStatus.complete,
            ).all()
            db.close()
            log.info(f"Found {len(profiles)} onboarded client(s) in DB — registering jobs")
            for profile in profiles:
                self.add_client(profile.client_id)
            log.info(f"Finished loading {len(profiles)} client(s)")
        except Exception as e:
            log.error(f"CRITICAL: Could not load clients from DB: {e}", exc_info=True)

    def add_client(self, client_id: str, config: Optional[Dict[str, Any]] = None):
        """
        Register all scheduled jobs for a new client.
        Safe to call multiple times — existing jobs are replaced.

        RAG status is logged but NEVER blocks job registration.
        Jobs run with profile + MI intelligence even without RAG content.
        """
        if not self._scheduler:
            return
        if config:
            save_config(client_id, config)
        cfg = _load_config(client_id)

        # ── RAG soft-check: log whether KB has content, but NEVER block jobs ──
        try:
            from agents.rag_system import RAGSystem
            rag = RAGSystem()
            rag_docs = rag.list_documents(client_id, limit=1)
            if not rag_docs:
                log.info(
                    f"[{client_id}] RAG knowledge base is empty — jobs will still run. "
                    "Content generation will use profile + MI intelligence only."
                )
            else:
                log.info(f"[{client_id}] RAG KB has content ✓")
        except Exception as rag_err:
            log.warning(
                f"[{client_id}] Could not reach RAG/Qdrant ({rag_err}) — "
                "jobs will still be registered (content gen works without RAG)."
            )

        self._remove_client_jobs(client_id)

        tz = cfg.get("timezone", "UTC")

        # ── Monday 02:00: weekly strategy + calendar generation ──────
        self._scheduler.add_job(
            job_weekly_strategy,
            CronTrigger(
                day_of_week=cfg.get("weekly_strategy_dow", "mon"),
                hour=cfg.get("weekly_strategy_hour", 2),
                minute=0,
                timezone=tz,
            ),
            id=f"weekly_strategy_{client_id}",
            args=[client_id],
            replace_existing=True,
            misfire_grace_time=3600,      # allow up to 1h late if server was down
        )

        # ── Daily 05:00: legacy stub (content generates JIT now) ────
        # Kept so _remove_client_jobs / run_now don't break
        self._scheduler.add_job(
            job_daily_generate,
            CronTrigger(hour=5, minute=0, timezone=tz),
            id=f"daily_generate_{client_id}",
            args=[client_id],
            replace_existing=True,
            misfire_grace_time=3600,
        )

        # ── Daily 07:30: legacy stub (no separate approval step) ───
        self._scheduler.add_job(
            job_daily_approve,
            CronTrigger(hour=7, minute=30, timezone=tz),
            id=f"daily_approve_{client_id}",
            args=[client_id],
            replace_existing=True,
            misfire_grace_time=1800,
        )

        # ── Every 15 min: post content whose scheduled_time has arrived ──
        # The marketing agent sets per-post times; we fire them at the right moment
        # instead of dumping everything at a fixed 08:00 cron.
        self._scheduler.add_job(
            job_post_due_now,
            IntervalTrigger(minutes=15, timezone=tz),
            id=f"daily_post_{client_id}",
            args=[client_id],
            replace_existing=True,
            misfire_grace_time=900,   # 15-min grace
        )

        # ── Growth campaigns + daily recommendations ─────────────────
        # Always register — recommendations run on ALL tiers (free included).
        # The actual follow/engagement campaigns are tier-gated inside the job.
        _tier = _get_client_tier(client_id)
        _growth_sched = GROWTH_CAMPAIGN_SCHEDULE.get(_tier)
        _growth_days = _growth_sched.get("day_of_week", "mon,wed,fri") if _growth_sched else "mon,tue,wed,thu,fri,sat,sun"
        self._scheduler.add_job(
            job_growth_campaign,
            CronTrigger(
                day_of_week=_growth_days,
                hour=cfg.get("growth_hour", 9),
                minute=0,
                timezone=tz,
            ),
            id=f"growth_campaign_{client_id}",
            args=[client_id],
            replace_existing=True,
            misfire_grace_time=7200,
        )

        # ── Growth hacking strategy (tier-aware) ───────────────────
        _hack_sched = GROWTH_HACK_SCHEDULE.get(_tier)
        if _hack_sched is not None:
            cron_kwargs = {"hour": 3, "minute": 0, "timezone": tz}
            if "day" in _hack_sched:
                cron_kwargs["day"] = _hack_sched["day"]
            if "day_of_week" in _hack_sched:
                cron_kwargs["day_of_week"] = _hack_sched["day_of_week"]
            self._scheduler.add_job(
                job_growth_hack_strategy,
                CronTrigger(**cron_kwargs),
                id=f"growth_hack_{client_id}",
                args=[client_id],
                replace_existing=True,
                misfire_grace_time=7200,
            )
        else:
            log.info(f"[{client_id}] Growth hack NOT registered (tier={_tier})")

        # ── Email campaign suggestion (tier-aware) ─────────────────
        _email_sched = EMAIL_CAMPAIGN_SCHEDULE.get(_tier)
        if _email_sched is not None:
            ecron_kwargs = {"hour": 10, "minute": 0, "timezone": tz}
            if "day" in _email_sched:
                ecron_kwargs["day"] = _email_sched["day"]
            if "day_of_week" in _email_sched:
                ecron_kwargs["day_of_week"] = _email_sched["day_of_week"]
            self._scheduler.add_job(
                job_email_campaign_suggestion,
                CronTrigger(**ecron_kwargs),
                id=f"email_campaign_{client_id}",
                args=[client_id],
                replace_existing=True,
                misfire_grace_time=3600,
            )
        else:
            log.info(f"[{client_id}] Email campaign NOT registered (tier={_tier})")

        # ── Sunday 23:00: analytics report ─────────────────────────
        self._scheduler.add_job(
            job_weekly_analytics,
            CronTrigger(
                day_of_week=cfg.get("analytics_dow", "sun"),
                hour=cfg.get("analytics_hour", 23),
                minute=0,
                timezone=tz,
            ),
            id=f"weekly_analytics_{client_id}",
            args=[client_id],
            replace_existing=True,
            misfire_grace_time=3600,
        )

        # ── Tier-based email inbox polling (auto-enabled when email connected) ─
        poll_hours = EMAIL_INBOX_POLL_HOURS.get(_tier)
        if poll_hours:
            self._scheduler.add_job(
                job_email_inbox_check,
                IntervalTrigger(
                    hours=poll_hours,
                    timezone=tz,
                ),
                id=f"email_inbox_{client_id}",
                args=[client_id],
                replace_existing=True,
                misfire_grace_time=1800,
            )

        if client_id not in self._client_ids:
            self._client_ids.append(client_id)

        log.info(f"Jobs registered for client: {client_id} (tz={tz})")

    def remove_client(self, client_id: str):
        """Remove all scheduled jobs for a client (e.g. account deactivated)."""
        self._remove_client_jobs(client_id)
        if client_id in self._client_ids:
            self._client_ids.remove(client_id)
        log.info(f"Jobs removed for client: {client_id}")

    def _remove_client_jobs(self, client_id: str):
        if not self._scheduler:
            return
        job_ids = [
            f"weekly_strategy_{client_id}",
            f"daily_generate_{client_id}",
            f"daily_approve_{client_id}",
            f"daily_post_{client_id}",
            f"growth_campaign_{client_id}",
            f"growth_hack_{client_id}",
            f"email_campaign_{client_id}",
            f"weekly_analytics_{client_id}",
            f"email_inbox_{client_id}",
        ]
        for job_id in job_ids:
            try:
                self._scheduler.remove_job(job_id)
            except Exception:
                pass

    # ── on-demand triggers ─────────────────────────────────────────────

    _job_map = {
        "weekly_strategy": job_weekly_strategy,
        "daily_generate": job_daily_generate,
        "daily_approve": job_daily_approve,
        "daily_post": job_daily_post,
        "growth_campaign": job_growth_campaign,
        "growth_hack": job_growth_hack_strategy,
        "email_campaign": job_email_campaign_suggestion,
        "weekly_analytics": job_weekly_analytics,
        "email_inbox_check": job_email_inbox_check,
    }

    async def run_now(self, job_type: str, client_id: str) -> Dict[str, Any]:
        """
        Trigger a specific job immediately (used by admin panel).

        Returns {"success": bool, "job": job_type, "client_id": client_id}
        """
        fn = self._job_map.get(job_type)
        if not fn:
            return {"success": False, "error": f"Unknown job type: {job_type}"}
        try:
            log.info(f"Manual trigger: {job_type} for {client_id}")
            await fn(client_id)
            return {"success": True, "job": job_type, "client_id": client_id}
        except Exception as e:
            log.error(f"Manual trigger failed: {job_type}/{client_id}: {e}", exc_info=True)
            return {"success": False, "error": str(e)}

    # ── status ─────────────────────────────────────────────────────────

    def get_status(self) -> Dict[str, Any]:
        """
        Return a snapshot of all scheduled jobs — used by admin panel dashboard.

        Returns dict with:
            running     – bool
            client_ids  – list of registered clients
            jobs        – list of {id, next_run, trigger}
        """
        if not self._scheduler:
            return {"running": False, "client_ids": [], "jobs": []}

        jobs_info = []
        for job in self._scheduler.get_jobs():
            jobs_info.append({
                "id": job.id,
                "next_run": job.next_run_time.isoformat() if job.next_run_time else None,
                "trigger": str(job.trigger),
            })

        return {
            "running": self._scheduler.running,
            "client_ids": list(self._client_ids),
            "jobs": jobs_info,
        }

    def update_client_config(self, client_id: str, updates: Dict[str, Any]):
        """
        Update a client's scheduler config and re-register their jobs.
        Call this from the admin panel when a client changes their settings.
        """
        cfg = _load_config(client_id)
        cfg.update(updates)
        save_config(client_id, cfg)
        self.add_client(client_id, cfg)
        log.info(f"Scheduler config updated and jobs re-registered for {client_id}")


# ── module-level singleton ─────────────────────────────────────────────────────
# Import this instance everywhere: `from agents.agent_scheduler import scheduler`
scheduler = AgentScheduler()
