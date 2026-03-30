"""
utils/platform_events.py
------------------------
Background event handlers that fire the instant a social platform is
connected or disconnected.

Key function:
    on_platform_connected(client_id, platform, db=None)

Called as a FastAPI BackgroundTask from:
  - api/client_connections_routes.py  (Late-API OAuth callback + manual-add)
  - api/oauth_routes.py               (Meta Instagram / Facebook OAuth callback)

What it does:
  1. Reads the full list of currently connected platforms (live from DB + JSON).
  2. Updates the agent-scheduler config so future weekly jobs use the new list.
  3. Immediately generates a new 7-day content calendar covering ALL connected
     platforms (not just the new one).
  4. Sends a dashboard notification to the client confirming the update.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

log = logging.getLogger("platform_events")


async def on_platform_connected(
    client_id: str,
    platform: str,
    db=None,  # optional open SQLAlchemy session (closed by caller)
) -> None:
    """
    Instantly react to a new platform being connected:

    1. Fetch the full current connected-platform list.
    2. Sync the scheduler config so future weekly jobs stay accurate.
    3. Generate a fresh 7-day content calendar for ALL connected platforms.
    4. Notify the client via the in-app dashboard.

    This function is safe to run as a FastAPI BackgroundTask — it never
    raises an unhandled exception so the HTTP response is never affected.
    """
    log.info(f"[{client_id}] 📣 on_platform_connected fired for platform={platform}")

    try:
        # ── 1. Get full connected-platform list ───────────────────────────────
        from utils.connected_platforms import get_connected_platforms
        current_platforms = get_connected_platforms(client_id, db=db)

        if not current_platforms:
            # Fallback: at minimum include the platform we just connected
            current_platforms = [platform]
        log.info(f"[{client_id}] Current connected platforms: {current_platforms}")

        # ── 2. Sync agent-scheduler config ────────────────────────────────────
        _sync_scheduler_config(client_id, current_platforms)

        # ── 3. Regenerate the content calendar immediately ────────────────────
        calendar = await _regenerate_calendar(client_id, current_platforms, platform)
        calendar_info = ""
        if calendar is not None:
            total = getattr(calendar, "total_posts", 0)
            calendar_info = f" ({total} posts scheduled)"

        # ── 4. Notify the client ──────────────────────────────────────────────
        await _notify_client(client_id, platform, current_platforms, calendar_info)

    except Exception as exc:
        log.error(f"[{client_id}] ❌ on_platform_connected error for {platform}: {exc}", exc_info=True)


async def on_platform_disconnected(
    client_id: str,
    platform: str,
    db=None,
) -> None:
    """
    React to a platform being disconnected — update the scheduler config
    and send a notification.  Does NOT regenerate the calendar automatically
    (existing scheduled posts are kept; the next weekly job will exclude the
    removed platform naturally because it reads live connections).
    """
    log.info(f"[{client_id}] 📣 on_platform_disconnected fired for platform={platform}")

    try:
        from utils.connected_platforms import get_connected_platforms
        remaining_platforms = get_connected_platforms(client_id, db=db)

        # Remove the disconnected platform from remaining list (belt-and-suspenders
        # in case the write hasn't propagated yet)
        remaining_platforms = [p for p in remaining_platforms if p != platform.lower()]

        _sync_scheduler_config(client_id, remaining_platforms)
        log.info(f"[{client_id}] Remaining platforms after disconnect: {remaining_platforms}")

        # Purge scheduled posts for the disconnected platform from the UI JSONL
        removed = _purge_platform_posts(client_id, platform)
        if removed:
            log.info(f"[{client_id}] Purged {removed} {platform} posts from calendar")

        await _notify_disconnect(client_id, platform, remaining_platforms)

    except Exception as exc:
        log.error(f"[{client_id}] ❌ on_platform_disconnected error for {platform}: {exc}", exc_info=True)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _sync_scheduler_config(client_id: str, platforms: list[str]) -> None:
    """Push the updated platform list into the scheduler's persisted config."""
    try:
        from agents.agent_scheduler import update_client_config_file
        update_client_config_file(client_id, {"platforms": platforms})
        log.info(f"[{client_id}] Scheduler config synced with platforms={platforms}")
    except ImportError:
        # Fallback: write the config JSON directly
        try:
            import json, os
            from pathlib import Path
            CONFIG_DIR = Path("storage/scheduler_config")
            CONFIG_DIR.mkdir(parents=True, exist_ok=True)
            cfg_path = CONFIG_DIR / f"{client_id}.json"
            cfg: dict = {}
            if cfg_path.exists():
                try:
                    cfg = json.loads(cfg_path.read_text())
                except Exception:
                    pass
            cfg["platforms"] = platforms
            cfg_path.write_text(json.dumps(cfg, indent=2))
            log.info(f"[{client_id}] Scheduler config (direct write) synced with platforms={platforms}")
        except Exception as exc2:
            log.warning(f"[{client_id}] Could not sync scheduler config: {exc2}")
    except Exception as exc:
        log.warning(f"[{client_id}] Could not sync scheduler config: {exc}")


# Directory used to store debounce timestamp files
_EVENT_DIR = Path("storage/connection_events")


async def _regenerate_calendar(client_id: str, platforms: list[str], new_platform: str):
    """
    Generate a fresh content calendar for all connected platforms.

    Debounce: if multiple platforms are connected in quick succession, only
    the last event actually generates the calendar (earlier events are
    superseded and return None silently).
    """
    try:
        # -- Debounce -------------------------------------------------------
        _EVENT_DIR.mkdir(parents=True, exist_ok=True)
        event_file = _EVENT_DIR / f"{client_id}.json"
        ts_now = datetime.utcnow().isoformat()
        event_file.write_text(json.dumps({"ts": ts_now, "platform": new_platform}))

        delay = int(os.getenv("CALENDAR_AUTO_GEN_DELAY_SECONDS", "180"))
        log.info(f"[{client_id}] Debounce: waiting {delay}s before generating calendar")
        await asyncio.sleep(delay)

        # If a newer connect event fired while we slept, let that one win
        if event_file.exists():
            stored = json.loads(event_file.read_text())
            if stored.get("ts") != ts_now:
                log.info(f"[{client_id}] Debounce: newer event supersedes -- skipping calendar regen")
                return None

        # -- Build calendar slots -------------------------------------------
        from agents.content_calendar_orchestrator import ContentCalendarOrchestrator
        from agents.agent_scheduler import _load_config

        config = _load_config(client_id)
        orch = ContentCalendarOrchestrator(
            client_id=client_id,
            timezone=config.get("timezone", "UTC"),
            load_existing_calendars=False,
        )

        week_label = datetime.now().strftime("%b %d, %Y")
        base_freq = dict(config.get("posts_per_platform_per_day", {}))
        ppd = {p: base_freq.get(p, 1) for p in platforms}

        log.info(f"[{client_id}] Regenerating calendar: platforms={platforms}")
        calendar = await orch.generate_calendar(
            name=f"Updated Calendar ({new_platform.title()} added) - {week_label}",
            platforms=platforms,
            duration_days=7,
            posts_per_platform_per_day=ppd,
            auto_approve=config.get("auto_approve", False),
            auto_post=config.get("auto_post", True),
        )
        log.info(f"[{client_id}] Calendar slots created: {getattr(calendar, 'calendar_id', '?')} "
                 f"({getattr(calendar, 'total_posts', '?')} slots)")

        # -- Generate content for every slot --------------------------------
        calendar_id = getattr(calendar, "calendar_id", None)
        if calendar_id:
            log.info(f"[{client_id}] Generating content for all calendar slots...")
            await orch.generate_all_content(calendar_id)
            log.info(f"[{client_id}] Content generation complete")

        # -- Bridge to UI JSONL (storage/scheduled_posts/) ------------------
        pieces = getattr(calendar, "scheduled_content", None) or []
        if pieces:
            try:
                from api.calendar_routes import _bridge_pieces_to_jsonl
                bridged = _bridge_pieces_to_jsonl(client_id, pieces)
                log.info(f"[{client_id}] Bridged {bridged} posts to scheduled_posts JSONL")
            except Exception as bridge_exc:
                log.warning(f"[{client_id}] Bridge to JSONL failed: {bridge_exc}")

        return calendar
    except Exception as exc:
        log.error(f"[{client_id}] Calendar regeneration failed: {exc}", exc_info=True)
        return None


async def _notify_client(
    client_id: str,
    new_platform: str,
    all_platforms: list[str],
    calendar_info: str,
) -> None:
    """Send a dashboard notification confirming the calendar was updated."""
    try:
        from utils.notification_manager import NotificationManager
        nm = NotificationManager(client_id)

        platform_list = ", ".join(p.title() for p in all_platforms)
        count = len(all_platforms)

        await nm.send_notification(
            notification_type="platform_connected",
            title=f"📅 {new_platform.title()} Added — Calendar Updated",
            message=(
                f"Your content calendar has been updated to include {new_platform.title()}. "
                f"Posts will now be scheduled across all {count} connected platform{'s' if count != 1 else ''}: "
                f"{platform_list}.{calendar_info}"
            ),
            priority="high",
            channels=["dashboard"],
        )
        log.info(f"[{client_id}] Dashboard notification sent for {new_platform} connection")
    except Exception as exc:
        log.warning(f"[{client_id}] Could not send connection notification: {exc}")


def _purge_platform_posts(client_id: str, platform: str) -> int:
    """
    Remove scheduled posts for a disconnected platform directly from PostgreSQL.
    Only deletes pending auto-created posts — preserves posted/failed history.
    Returns the number of posts removed.
    """
    try:
        from database.db import SessionLocal
        from database.models import ScheduledPost
        db = SessionLocal()
        try:
            count = (
                db.query(ScheduledPost)
                .filter(
                    ScheduledPost.client_id == client_id,
                    ScheduledPost.platform == platform.lower(),
                    ScheduledPost.status.notin_(["posted", "failed"]),
                )
                .delete(synchronize_session=False)
            )
            db.commit()
            if count:
                log.info(f"[{client_id}] Purged {count} pending {platform} posts from DB")
            return count
        finally:
            db.close()
    except Exception as exc:
        log.warning(f"[{client_id}] Could not purge {platform} posts: {exc}")
        return 0


async def _notify_disconnect(
    client_id: str,
    removed_platform: str,
    remaining_platforms: list[str],
) -> None:
    """Send a dashboard notification when a platform is disconnected."""
    try:
        from utils.notification_manager import NotificationManager
        nm = NotificationManager(client_id)
        count = len(remaining_platforms)
        suffix = (
            f" Remaining: {', '.join(p.title() for p in remaining_platforms)}."
            if remaining_platforms
            else " No platforms are currently connected."
        )
        await nm.send_notification(
            notification_type="platform_disconnected",
            title=f"🔌 {removed_platform.title()} Disconnected",
            message=(
                f"{removed_platform.title()} has been disconnected. "
                f"Your next scheduled content update will cover {count} platform{'s' if count != 1 else ''}."
                f"{suffix}"
            ),
            priority="medium",
            channels=["dashboard"],
        )
    except Exception as exc:
        log.warning(f"[{client_id}] Could not send disconnect notification: {exc}")
