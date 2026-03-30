"""
Calendar Agent Routes
=====================
Provides the client-facing content calendar UI and scheduling API.

Routes:
  GET  /calendar                          – Calendar view (month grid + list)
  GET  /api/calendar/posts                – List all scheduled posts (JSON)
  POST /api/calendar/schedule-post        – Create / save a scheduled post
  PUT  /api/calendar/posts/{post_id}      – Edit a scheduled post
  DELETE /api/calendar/posts/{post_id}    – Delete a scheduled post
  POST /api/calendar/recommended-slots    – AI-powered recommended time slots
  POST /api/calendar/auto-create          – Auto-generate post topic + content
"""

import json
import uuid
import os
import re
import asyncio
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Request
from fastapi.responses import HTMLResponse, JSONResponse

from utils.shared_layout import build_page

logger = logging.getLogger(__name__)
router = APIRouter()

# ─── Storage (PostgreSQL-backed — survives Railway redeploys) ─────────────────

# Legacy JSONL path — used only for one-time migration on first read
_LEGACY_SCHED_DIR = Path("storage") / "scheduled_posts"


def _post_row_to_dict(row) -> dict:
    """Convert a ScheduledPost ORM row to the dict format the UI expects."""
    return {
        "id":             row.id,
        "platform":       row.platform or "",
        "caption":        row.caption or "",
        "image_url":      row.image_url or "",
        "content_type":   row.content_type or "post",
        "scheduled_time": row.scheduled_time or "",
        "topic":          row.topic or "",
        "seo_keywords":   row.seo_keywords or "",
        "auto_created":   bool(row.auto_created),
        "status":         row.status or "scheduled",
        "created_at":     row.created_at.isoformat() if row.created_at else "",
        "updated_at":     row.updated_at.isoformat() if row.updated_at else "",
        "client_id":      row.client_id or "",
    }


def _migrate_jsonl_to_db(client_id: str):
    """One-time migration: import any existing JSONL posts into PostgreSQL.

    Called transparently on the first _load_posts() after the DB migration.
    Safe to call repeatedly — skips if JSONL file doesn't exist or is empty,
    and deduplicates by post id.
    """
    legacy_file = _LEGACY_SCHED_DIR / f"{client_id}_posts.jsonl"
    if not legacy_file.exists():
        return

    items = []
    try:
        with open(legacy_file, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    try:
                        items.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass
    except Exception:
        return

    if not items:
        return

    from database.db import SessionLocal
    from database.models import ScheduledPost
    db = SessionLocal()
    try:
        # Check which IDs already exist in DB
        existing_ids = {
            r[0] for r in db.query(ScheduledPost.id).filter(
                ScheduledPost.client_id == client_id
            ).all()
        }
        new_rows = []
        for item in items:
            pid = item.get("id", "")
            if not pid or pid in existing_ids:
                continue
            new_rows.append(ScheduledPost(
                id=pid,
                client_id=client_id,
                platform=item.get("platform", ""),
                caption=item.get("caption", ""),
                image_url=item.get("image_url", ""),
                content_type=item.get("content_type", "post"),
                scheduled_time=item.get("scheduled_time", ""),
                topic=item.get("topic", ""),
                seo_keywords=item.get("seo_keywords", ""),
                auto_created=bool(item.get("auto_created", False)),
                status=item.get("status", "scheduled"),
            ))
        if new_rows:
            db.bulk_save_objects(new_rows)
            db.commit()
            logger.info(f"[{client_id}] Migrated {len(new_rows)} posts from JSONL to DB")
        # Rename the legacy file so we don't re-import
        try:
            legacy_file.rename(legacy_file.with_suffix(".jsonl.migrated"))
        except Exception:
            pass
    except Exception as e:
        db.rollback()
        logger.warning(f"[{client_id}] JSONL→DB migration failed: {e}")
    finally:
        db.close()


def _load_posts(client_id: str) -> list:
    """Load all scheduled posts for a client from PostgreSQL."""
    # One-time: migrate any legacy JSONL data into the DB
    _migrate_jsonl_to_db(client_id)

    from database.db import SessionLocal
    from database.models import ScheduledPost
    db = SessionLocal()
    try:
        rows = (
            db.query(ScheduledPost)
            .filter(ScheduledPost.client_id == client_id)
            .order_by(ScheduledPost.scheduled_time)
            .all()
        )
        return [_post_row_to_dict(r) for r in rows]
    finally:
        db.close()


def _save_posts(client_id: str, items: list):
    """Upsert posts for a client in PostgreSQL.

    SAFE: merges by post ID — never deletes posts that aren't in the incoming list.
    Only used by _purge_platform_posts (platform disconnect) which pre-filters.
    For individual CRUD, the endpoints write directly to DB.
    """
    from database.db import SessionLocal
    from database.models import ScheduledPost
    db = SessionLocal()
    try:
        existing_ids = {
            r[0] for r in db.query(ScheduledPost.id).filter(
                ScheduledPost.client_id == client_id
            ).all()
        }
        for item in items:
            pid = item.get("id", str(uuid.uuid4()))
            if pid in existing_ids:
                continue  # already in DB, don't duplicate
            db.add(ScheduledPost(
                id=pid,
                client_id=client_id,
                platform=item.get("platform", ""),
                caption=item.get("caption", ""),
                image_url=item.get("image_url", ""),
                content_type=item.get("content_type", "post"),
                scheduled_time=item.get("scheduled_time", ""),
                topic=item.get("topic", ""),
                seo_keywords=item.get("seo_keywords", ""),
                auto_created=bool(item.get("auto_created", False)),
                status=item.get("status", "scheduled"),
            ))
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error(f"[{client_id}] _save_posts DB write failed: {e}")
    finally:
        db.close()


def _get_platforms_needing_generation(
    client_id: str,
    all_platforms: list,
    duration_days: int = 7,
    timezone_str: str | None = None,
) -> list:
    """Return only the platforms that have NO scheduled posts in the upcoming date range.

    Used by the automated scheduler to avoid regenerating content for platforms
    that already have a full calendar.  The manual "Generate AI Calendar" button
    bypasses this entirely and always generates for all platforms.
    """
    from database.db import SessionLocal
    from database.models import ScheduledPost
    import pytz
    from datetime import datetime as _dt, timedelta

    tz_name = timezone_str or os.getenv("DEFAULT_TIMEZONE", "America/New_York")
    try:
        tz = pytz.timezone(tz_name)
    except Exception:
        tz = pytz.timezone("America/New_York")

    now = _dt.now(tz)
    start_date = now.date()
    end_date = start_date + timedelta(days=duration_days)

    db = SessionLocal()
    try:
        # Find platforms that already have at least one scheduled (non-cancelled) post
        rows = (
            db.query(ScheduledPost.platform)
            .filter(
                ScheduledPost.client_id == client_id,
                ScheduledPost.status.in_(("scheduled", "posted", "approved")),
                ScheduledPost.scheduled_time >= start_date.isoformat(),
                ScheduledPost.scheduled_time < end_date.isoformat(),
            )
            .distinct()
            .all()
        )
        already_scheduled = {r[0].lower() for r in rows if r[0]}
        needed = [p for p in all_platforms if p.lower() not in already_scheduled]
        return needed
    except Exception as e:
        logger.warning(f"[{client_id}] _get_platforms_needing_generation error: {e}")
        return all_platforms  # Fall back to generating for all platforms
    finally:
        db.close()


def _clear_date_range_posts(
    client_id: str,
    duration_days: int = 7,
    timezone_str: str | None = None,
) -> int:
    """Delete auto-created pending posts in the upcoming date range only.

    Called before the manual "Generate AI Calendar" button runs so it gives
    a clean slate for the fresh AI plan.  Only deletes posts within the
    generation window (tomorrow \u2192 tomorrow+duration_days).  Manually-scheduled
    posts, already-posted posts, and posts outside the range are preserved.
    Returns the number of rows deleted.
    """
    from database.db import SessionLocal
    from database.models import ScheduledPost
    import pytz as _pytz

    tz = _pytz.timezone(timezone_str or os.getenv("DEFAULT_TIMEZONE", "America/New_York"))
    start = (datetime.now(tz).replace(hour=0, minute=0, second=0, microsecond=0)
             + timedelta(days=1))
    end = start + timedelta(days=duration_days)
    start_str = start.strftime("%Y-%m-%d")
    end_str = end.strftime("%Y-%m-%d")

    db = SessionLocal()
    try:
        count = (
            db.query(ScheduledPost)
            .filter(
                ScheduledPost.client_id == client_id,
                ScheduledPost.auto_created == True,
                ScheduledPost.status.notin_(["posted", "failed"]),
                ScheduledPost.scheduled_time >= start_str,
                ScheduledPost.scheduled_time < end_str,
            )
            .delete(synchronize_session=False)
        )
        db.commit()
        logger.info(f"[{client_id}] Cleared {count} auto-created pending posts "
                     f"in range {start_str} to {end_str}")
        return count
    except Exception as e:
        db.rollback()
        logger.error(f"[{client_id}] _clear_date_range_posts error: {e}")
        return 0
    finally:
        db.close()


def _bridge_pieces_to_jsonl(client_id: str, pieces: list) -> int:
    """Convert ScheduledContentPiece objects into the scheduled_posts DB.

    Called after ContentCalendarOrchestrator.generate_all_content() completes so
    that the calendar UI sees the AI-generated posts.
    Deduplicates by content_id so re-running generation is safe.
    Skips pieces that failed generation (no content).

    NOTE: Name kept as _bridge_pieces_to_jsonl for backward compatibility with
    callers in agent_scheduler.py and platform_events.py.
    """
    from database.db import SessionLocal
    from database.models import ScheduledPost
    from datetime import datetime as _dt

    db = SessionLocal()
    try:
        # Get existing post IDs for this client
        existing_ids = {
            r[0] for r in db.query(ScheduledPost.id).filter(
                ScheduledPost.client_id == client_id
            ).all()
        }

        new_rows = []
        seen_ids = set(existing_ids)  # track within this batch to avoid PK collisions
        for piece in pieces:
            pid = getattr(piece, "content_id", None) or str(uuid.uuid4())
            if pid in seen_ids:
                pid = str(uuid.uuid4())  # generate fresh UUID on collision
            seen_ids.add(pid)

            # Skip failed pieces
            piece_status = getattr(piece, "status", "")
            if piece_status in ("failed", "error"):
                continue

            gc = getattr(piece, "generated_content", None)
            caption = ""
            image_url = ""
            if gc:
                caption = (
                    getattr(gc, "caption", "") or
                    getattr(gc, "content", "") or
                    ""
                )
                image_url = getattr(gc, "image_url", "") or ""

            topic = getattr(piece, "topic", "") or ""
            # Topic is intentionally empty at calendar-planning time.
            # It will be determined JIT when the post is due.

            st = getattr(piece, "scheduled_time", None)
            scheduled_time = st.isoformat() if hasattr(st, "isoformat") else str(st or "")

            new_rows.append(ScheduledPost(
                id=pid,
                client_id=client_id,
                platform=getattr(piece, "platform", ""),
                caption=caption,
                image_url=image_url,
                content_type=getattr(piece, "content_type", "post"),
                scheduled_time=scheduled_time,
                topic=topic,
                seo_keywords="",
                auto_created=True,
                status="planned",  # content generated JIT at scheduled time
            ))

        if new_rows:
            db.bulk_save_objects(new_rows)
            db.commit()
            logger.info(f"[{client_id}] Bridged {len(new_rows)} AI posts to DB "
                         f"(first scheduled: {new_rows[0].scheduled_time})")
        else:
            logger.warning(f"[{client_id}] Bridge created 0 new rows from {len(pieces)} pieces "
                            f"(all deduped or skipped)")

        return len(new_rows)
    except Exception as e:
        db.rollback()
        logger.error(f"[{client_id}] Bridge to DB failed: {e}", exc_info=True)
        raise  # propagate so the caller's try/except captures it
    finally:
        db.close()


# ─── Helper: resolve user + profile ──────────────────────────────────────────

def _get_user_profile(request: Request):
    from database.db import get_db
    from database.models import ClientProfile
    from api.auth_routes import get_current_user

    db = next(get_db())
    try:
        user = get_current_user(request, db)
        if not user:
            return None, None
        profile = db.query(ClientProfile).filter(
            ClientProfile.user_id == user.id
        ).first()
        return user, profile
    finally:
        db.close()


# ─── JSON API ─────────────────────────────────────────────────────────────────

@router.get("/api/calendar/posts")
async def api_list_posts(request: Request, platform: str = "", status: str = ""):
    user, profile = _get_user_profile(request)
    if not user or not profile:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    posts = _load_posts(profile.client_id)

    if platform:
        posts = [p for p in posts if p.get("platform", "").lower() == platform.lower()]
    if status:
        posts = [p for p in posts if p.get("status", "scheduled") == status]

    return JSONResponse({"posts": posts, "count": len(posts)})


@router.post("/api/calendar/schedule-post")
async def api_schedule_post(request: Request):
    user, profile = _get_user_profile(request)
    if not user or not profile:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON"}, status_code=400)

    platform       = (body.get("platform") or "").strip()
    caption        = (body.get("caption") or "").strip()
    scheduled_time = (body.get("scheduled_time") or "").strip()
    image_url      = (body.get("image_url") or "").strip()
    content_type   = (body.get("content_type") or "post").strip()
    topic          = (body.get("topic") or "").strip()
    seo_keywords   = (body.get("seo_keywords") or "").strip()
    auto_created   = bool(body.get("auto_created", False))

    if not platform or not scheduled_time:
        return JSONResponse(
            {"error": "platform and scheduled_time are required"},
            status_code=400,
        )

    # ── Plan quota check ─────────────────────────────────────────────────
    from utils.plan_limits import check_post_schedule_limit
    allowed, used, limit, quota_msg = check_post_schedule_limit(profile)
    if not allowed:
        return JSONResponse({"error": quota_msg, "quota_exceeded": True}, status_code=403)

    from database.db import SessionLocal
    from database.models import ScheduledPost

    # ── Time-conflict check: warn if a post on the same platform is within 1 hour ──
    conflict_warning = None
    try:
        _cdb = SessionLocal()
        try:
            _sched_dt = datetime.fromisoformat(scheduled_time)
            _one_hour = timedelta(hours=1)
            _nearby = _cdb.query(ScheduledPost).filter(
                ScheduledPost.client_id == profile.client_id,
                ScheduledPost.platform == platform,
                ScheduledPost.status.in_(["planned", "scheduled", "approved"]),
            ).all()
            for _nb in _nearby:
                try:
                    _nb_dt = datetime.fromisoformat((_nb.scheduled_time or "").strip())
                    if abs((_sched_dt - _nb_dt).total_seconds()) < _one_hour.total_seconds():
                        conflict_warning = (
                            f"Another {platform} post is scheduled within 1 hour "
                            f"({_nb.scheduled_time}). Posts too close together may "
                            f"fail due to platform rate limits."
                        )
                        break
                except (ValueError, TypeError):
                    continue
        finally:
            _cdb.close()
    except Exception:
        pass  # non-blocking — conflict check is advisory
    post_id = str(uuid.uuid4())
    post_dict = {
        "id":             post_id,
        "platform":       platform,
        "caption":        caption,
        "image_url":      image_url,
        "content_type":   content_type,
        "scheduled_time": scheduled_time,
        "topic":          topic,
        "seo_keywords":   seo_keywords,
        "auto_created":   auto_created,
        "status":         "scheduled",
        "created_at":     datetime.utcnow().isoformat(),
        "client_id":      profile.client_id,
    }

    db = SessionLocal()
    try:
        db.add(ScheduledPost(
            id=post_id,
            client_id=profile.client_id,
            platform=platform,
            caption=caption,
            image_url=image_url,
            content_type=content_type,
            scheduled_time=scheduled_time,
            topic=topic,
            seo_keywords=seo_keywords,
            auto_created=auto_created,
            status="scheduled",
        ))
        # Keep usage_posts_created in sync so both counters agree
        try:
            from database.models import ClientProfile as _CP_sync
            _prof = db.query(_CP_sync).filter(_CP_sync.client_id == profile.client_id).first()
            if _prof:
                _prof.usage_posts_created = (_prof.usage_posts_created or 0) + 1
                db.add(_prof)
        except Exception:
            pass
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error(f"schedule-post DB error: {e}")
        return JSONResponse({"error": "Failed to save post"}, status_code=500)
    finally:
        db.close()

    resp = {"ok": True, "post": post_dict}
    if conflict_warning:
        resp["warning"] = conflict_warning
    return JSONResponse(resp)


@router.put("/api/calendar/posts/{post_id}")
async def api_update_post(request: Request, post_id: str):
    user, profile = _get_user_profile(request)
    if not user or not profile:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON"}, status_code=400)

    from database.db import SessionLocal
    from database.models import ScheduledPost
    db = SessionLocal()
    try:
        row = db.query(ScheduledPost).filter(
            ScheduledPost.id == post_id,
            ScheduledPost.client_id == profile.client_id,
        ).first()
        if not row:
            return JSONResponse({"error": "Post not found"}, status_code=404)

        for key in (
            "platform", "caption", "image_url", "content_type",
            "scheduled_time", "topic", "seo_keywords", "status",
        ):
            if key in body:
                setattr(row, key, body[key])
        row.updated_at = datetime.utcnow()
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error(f"update-post DB error: {e}")
        return JSONResponse({"error": "Failed to update post"}, status_code=500)
    finally:
        db.close()

    return JSONResponse({"ok": True})


@router.delete("/api/calendar/posts/{post_id}")
async def api_delete_post(request: Request, post_id: str):
    user, profile = _get_user_profile(request)
    if not user or not profile:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    from database.db import SessionLocal
    from database.models import ScheduledPost
    db = SessionLocal()
    try:
        deleted = db.query(ScheduledPost).filter(
            ScheduledPost.id == post_id,
            ScheduledPost.client_id == profile.client_id,
        ).delete()
        db.commit()
        if not deleted:
            return JSONResponse({"error": "Post not found"}, status_code=404)
    except Exception as e:
        db.rollback()
        logger.error(f"delete-post DB error: {e}")
        return JSONResponse({"error": "Failed to delete post"}, status_code=500)
    finally:
        db.close()

    return JSONResponse({"ok": True})


@router.post("/api/calendar/recommended-slots")
async def api_recommended_slots(request: Request):
    """Return AI-powered recommended posting times for a platform."""
    user, profile = _get_user_profile(request)
    if not user or not profile:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON"}, status_code=400)

    platform     = (body.get("platform") or "instagram").strip()
    timezone     = (body.get("timezone") or "America/New_York").strip()
    content_type = (body.get("content_type") or "post").strip()
    niche        = (body.get("niche") or "").strip() or None
    account_goal = (body.get("account_goal") or "growth").strip()

    try:
        from agents.calendar_agent import CalendarAgent
        agent = CalendarAgent(client_id=profile.client_id, profile=profile)
        recs = await agent.get_optimal_posting_times(
            platform=platform,
            timezone=timezone,
            niche=niche,
            content_type=content_type,
            account_goal=account_goal,
        )

        # Build concrete datetime slot suggestions for the next 7 days
        from datetime import date
        import pytz

        try:
            tz = pytz.timezone(timezone)
        except Exception:
            tz = pytz.UTC

        now = datetime.now(tz)
        day_names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

        concrete_slots = []
        for rec in recs.get("recommended_times", [])[:6]:
            day_name = rec.get("day", "Monday")
            time_str = rec.get("time", "10:00")
            priority = rec.get("priority", "medium")

            try:
                target_weekday = day_names.index(day_name)
                today_weekday  = now.weekday()
                days_ahead     = (target_weekday - today_weekday) % 7
                if days_ahead == 0:
                    days_ahead = 7   # always future
                target_date = now.date() + timedelta(days=days_ahead)

                hour, minute = map(int, time_str.split(":"))
                slot_dt = tz.localize(
                    datetime(target_date.year, target_date.month, target_date.day, hour, minute)
                )
                concrete_slots.append({
                    "label": f"{day_name} {slot_dt.strftime('%b %d')} at {slot_dt.strftime('%-I:%M %p')}",
                    "datetime_local": slot_dt.strftime("%Y-%m-%dT%H:%M"),
                    "datetime_utc":   slot_dt.astimezone(pytz.UTC).isoformat(),
                    "day":            day_name,
                    "time":           time_str,
                    "priority":       priority,
                })
            except Exception:
                pass

        recs["concrete_slots"] = concrete_slots
        return JSONResponse(recs)

    except Exception as e:
        logger.warning(f"CalendarAgent error: {e}")
        # Fallback static slots
        now       = datetime.utcnow()
        fallbacks = []
        for i in range(1, 6):
            slot = now + timedelta(days=i)
            hr   = 10 if i % 2 == 0 else 18
            slot = slot.replace(hour=hr, minute=0, second=0, microsecond=0)
            fallbacks.append({
                "label":          slot.strftime("%A %b %d at %-I:%M %p"),
                "datetime_local": slot.strftime("%Y-%m-%dT%H:%M"),
                "datetime_utc":   slot.isoformat(),
                "priority":       "medium",
            })
        return JSONResponse({
            "recommended_times": [],
            "concrete_slots":    fallbacks,
            "insights":          ["Could not load AI recommendations. Showing default slots."],
            "_fallback":         True,
        })


@router.post("/api/calendar/generate-orchestrated")
async def api_generate_orchestrated(request: Request, background_tasks: BackgroundTasks):
    """Full orchestrated calendar: MarketingIntelligenceAgent -> ContentCalendarOrchestrator -> content generation."""
    user, profile = _get_user_profile(request)
    if not user or not profile:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    body: dict = {}
    try:
        body = await request.json()
    except Exception:
        pass

    cal_id = f"cal_{uuid.uuid4().hex[:10]}"
    background_tasks.add_task(_bg_orchestrate_in_thread, profile.client_id, cal_id, body)
    return JSONResponse({
        "ok": True,
        "calendar_id": cal_id,
        "message": "Generating calendar. This usually takes 1\u20133 minutes depending on how many platforms are connected.",
    })


# ── Status file helper for background generation tracking ──────────────────

_GEN_STATUS_DIR = Path("storage") / "generation_status"


def _write_gen_status(cal_id: str, status: str, detail: str = "", posts: int = 0):
    """Write a JSON status file that the JS frontend can poll."""
    _GEN_STATUS_DIR.mkdir(parents=True, exist_ok=True)
    (_GEN_STATUS_DIR / f"{cal_id}.json").write_text(json.dumps({
        "status": status,    # "working" | "done" | "error"
        "detail": detail,
        "posts": posts,
        "ts": datetime.utcnow().isoformat(),
    }))


@router.get("/api/calendar/generation-status/{cal_id}")
async def api_generation_status(cal_id: str, request: Request):
    """Poll endpoint — returns the current progress of a background calendar generation."""
    status_file = _GEN_STATUS_DIR / f"{cal_id}.json"
    if not status_file.exists():
        return JSONResponse({"status": "working", "detail": "Starting up..."})
    try:
        data = json.loads(status_file.read_text())
        return JSONResponse(data)
    except Exception:
        return JSONResponse({"status": "working", "detail": "Reading status..."})


# ── Generation lock: prevent duplicate concurrent runs ─────────────────────
_GEN_LOCK_DIR = Path("storage") / "generation_status"


def _is_generation_running(client_id: str) -> bool:
    """Check if another generation is already in progress for this client."""
    lock_file = _GEN_LOCK_DIR / f"_active_{client_id}.json"
    if not lock_file.exists():
        return False
    try:
        data = json.loads(lock_file.read_text())
        from datetime import datetime as _dt
        started = _dt.fromisoformat(data.get("started", ""))
        if (_dt.utcnow() - started).total_seconds() > 1200:
            lock_file.unlink(missing_ok=True)
            return False
        return True
    except Exception:
        lock_file.unlink(missing_ok=True)
        return False


def _acquire_gen_lock(client_id: str, cal_id: str) -> bool:
    _GEN_LOCK_DIR.mkdir(parents=True, exist_ok=True)
    lock_file = _GEN_LOCK_DIR / f"_active_{client_id}.json"
    if _is_generation_running(client_id):
        return False
    lock_file.write_text(json.dumps({"cal_id": cal_id, "started": datetime.utcnow().isoformat()}))
    return True


def _release_gen_lock(client_id: str):
    lock_file = _GEN_LOCK_DIR / f"_active_{client_id}.json"
    lock_file.unlink(missing_ok=True)


def _bg_orchestrate_in_thread(client_id: str, cal_id: str, params: dict):
    """Sync wrapper — runs in a thread pool so the FastAPI event loop stays free.

    FastAPI's BackgroundTasks runs sync functions in a thread pool executor,
    preventing synchronous API calls (NewsAPI, YouTube) from blocking the
    main event loop and freezing all other requests.
    """
    if not _acquire_gen_lock(client_id, cal_id):
        _write_gen_status(cal_id, "error",
                          "Another calendar generation is already running. Please wait for it to finish.")
        return
    try:
        asyncio.run(
            asyncio.wait_for(
                _bg_orchestrate_calendar(client_id, cal_id, params),
                timeout=900,  # 15 minute hard timeout (70 posts ~ 12 min)
            )
        )
    except asyncio.TimeoutError:
        logger.error(f"[{client_id}] Calendar generation timed out after 15 minutes")
        _write_gen_status(cal_id, "error",
                          "Generation timed out after 15 minutes. Try again with fewer days.")
    except Exception as exc:
        logger.error(f"[{client_id}] Calendar generation thread error: {exc}", exc_info=True)
        _write_gen_status(cal_id, "error", f"Generation failed: {str(exc)[:200]}")
    finally:
        _release_gen_lock(client_id)


async def _bg_orchestrate_calendar(client_id: str, cal_id: str, params: dict):
    """Background task — runs ContentCalendarOrchestrator end-to-end with status tracking.

    This is the MANUAL "Generate AI Calendar" button handler.
    It clears stale auto-created pending posts, then generates fresh content for
    ALL connected platforms.  Manually-scheduled posts and already-posted posts
    are always preserved.
    """
    try:
        from agents.content_calendar_orchestrator import ContentCalendarOrchestrator
        from utils.connected_platforms import get_connected_platforms
        from datetime import datetime as _dt

        _write_gen_status(cal_id, "working", "Detecting connected platforms...")

        tz = params.get("timezone") or os.getenv("DEFAULT_TIMEZONE", "America/New_York")
        orch = ContentCalendarOrchestrator(client_id=client_id, timezone=tz)

        # Auto-detect platforms from connected accounts (don't hardcode!)
        platforms = params.get("platforms") or None
        if not platforms:
            platforms = get_connected_platforms(client_id)
            logger.info(f"[{client_id}] Auto-detected platforms for calendar: {platforms}")
        if not platforms:
            platforms = ["instagram", "twitter", "linkedin"]
            logger.warning(f"[{client_id}] No connected platforms found, using defaults: {platforms}")

        # Use best-practice frequencies from the orchestrator (twitter=3, tiktok=2, etc.)
        posts_per_platform_per_day = orch._get_default_posting_frequency(platforms)
        duration_days = min(int(params.get("duration_days") or 7), 7)
        themes        = params.get("themes") or None
        auto_approve  = bool(params.get("auto_approve", False))
        name          = params.get("name") or f"AI Calendar {_dt.now().strftime('%b %d')}"

        # ── Clear stale auto-created posts (preserves manual + posted history) ──
        cleared = _clear_date_range_posts(client_id, duration_days, tz)
        logger.info(f"[{client_id}] ▶ Calendar generation "
                     f"for: {platforms} — cleared {cleared} auto-created pending posts")

        total_est = len(platforms) * duration_days
        _write_gen_status(cal_id, "working",
                          f"Building calendar for {', '.join(p.title() for p in platforms)} "
                          f"(~{total_est} posts over {duration_days} days)...")

        cal = await orch.generate_calendar(
            name=name,
            platforms=platforms,
            duration_days=duration_days,
            themes=themes,
            auto_approve=auto_approve,
            posts_per_platform_per_day=posts_per_platform_per_day,
            use_marketing_agent=False,         # topics determined JIT at post time
        )

        total_slots = len(getattr(cal, "scheduled_content", []))

        # ── Plan-only: skip content generation here ────────────────
        # Content will be generated JIT at posting time (job_post_due_now)
        # or pre-generated by the daily 05:00 safety-net job.
        _write_gen_status(cal_id, "working",
                          f"Saving {total_slots} planned slots to calendar...")

        # Bridge AI-generated pieces to the calendar UI (PostgreSQL DB)
        bridged = 0
        total_pieces = len(getattr(cal, "scheduled_content", []))
        try:
            if cal.scheduled_content:
                bridged = _bridge_pieces_to_jsonl(client_id, cal.scheduled_content)
                logger.info(f"[{client_id}] Bridged {bridged}/{total_pieces} AI posts to scheduled_posts DB")
        except Exception as _bridge_err:
            logger.error(f"[{client_id}] Bridge to DB failed: {_bridge_err}", exc_info=True)

        if bridged == 0 and total_pieces > 0:
            # Bridge failed silently — report error so user knows something went wrong
            logger.error(f"[{client_id}] Bridge returned 0 but orchestrator created {total_pieces} slots")
            _write_gen_status(cal_id, "error",
                              f"Calendar planned {total_pieces} posts but failed to save them to the database. Please try again.",
                              posts=0)
            return

        _write_gen_status(cal_id, "done",
                          f"Planned {bridged} posts across {', '.join(p.title() for p in platforms)} — content will be generated before posting.",
                          posts=bridged)

        # Fire notification
        try:
            import importlib
            nm_mod = importlib.import_module("utils.notification_manager")
            NotificationManager = getattr(nm_mod, "NotificationManager", None)
            if NotificationManager:
                nm = NotificationManager(client_id)
                await nm.send_notification(
                    notification_type="content_idea",
                    title="Calendar Ready",
                    message=f"Your calendar '{name}' is planned with {bridged} posts. Content generates automatically before posting.",
                    priority="medium",
                    channels=["dashboard"],
                    metadata={
                        "action_url": "/calendar",
                        "action_label": "View Calendar",
                        "action_type": "internal_link",
                    },
                )
        except Exception as _notif_err:
            logger.warning(f"[{client_id}] Calendar notification failed: {_notif_err}")
    except Exception as exc:
        logger.error(f"[{client_id}] orchestrate_calendar failed: {exc}", exc_info=True)
        _write_gen_status(cal_id, "error", f"Generation failed: {str(exc)[:200]}")


@router.get("/api/calendar/quota")
async def api_calendar_quota(request: Request):
    """Return the client's current post schedule quota for the month."""
    user, profile = _get_user_profile(request)
    if not user or not profile:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    from utils.plan_limits import check_post_schedule_limit, PLAN_DISPLAY_NAMES, ADDONS
    allowed, used, limit, msg = check_post_schedule_limit(profile)
    tier      = getattr(profile, "plan_tier", "free") or "free"
    tier_name = PLAN_DISPLAY_NAMES.get(tier, tier.title())
    remaining = (limit - used) if limit != -1 else None   # None = unlimited

    return JSONResponse({
        "tier":      tier,
        "tier_name": tier_name,
        "used":      used,
        "limit":     limit,         # -1 = unlimited
        "remaining": remaining,     # None = unlimited
        "allowed":   allowed,
        "pct":       round(used / limit * 100) if (limit and limit != -1) else 0,
        "message":   msg,
        "boost_available": bool(ADDONS.get("post_boost")),
    })


@router.post("/api/calendar/auto-create")
async def api_auto_create(request: Request):
    """Auto-generate post topic, keywords, and caption using marketing intelligence."""
    user, profile = _get_user_profile(request)
    if not user or not profile:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    # ── Plan quota check ─────────────────────────────────────────────────
    from utils.plan_limits import check_post_schedule_limit
    allowed, _used, _limit, quota_msg = check_post_schedule_limit(profile)
    if not allowed:
        return JSONResponse({"error": quota_msg, "quota_exceeded": True}, status_code=403)

    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON"}, status_code=400)

    platform     = (body.get("platform") or "instagram").strip()
    content_type = (body.get("content_type") or "post").strip()
    niche        = (body.get("niche") or "").strip()
    goal         = (body.get("goal") or "engagement").strip()

    # Try to derive niche from client profile
    if not niche and profile:
        niche = getattr(profile, "niche", "") or getattr(profile, "business_name", "") or "general"

    try:
        import anthropic as _anthropic
        import asyncio as _aio
        from utils.agent_executor import AGENT_POOL

        _client = _anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
        model   = os.getenv("CLAUDE_HAIKU_MODEL", "claude-haiku-4-5-20251001")

        system = (
            "You are a social media content strategist. "
            "Generate a trending post idea with SEO keywords. "
            "Always respond with valid JSON only, no markdown."
        )
        user_msg = (
            f"Platform: {platform}\n"
            f"Content type: {content_type}\n"
            f"Niche/industry: {niche}\n"
            f"Goal: {goal}\n\n"
            "Generate a post idea. Return JSON:\n"
            '{"topic": "...", "caption": "...", "seo_keywords": "...", "hashtags": "...", "content_notes": "..."}'
        )

        # Offload sync SDK call to thread pool
        _loop = _aio.get_running_loop()
        resp = await _loop.run_in_executor(
            AGENT_POOL,
            lambda: _client.messages.create(
                model=model,
                max_tokens=600,
                system=system,
                messages=[{"role": "user", "content": user_msg}],
            ),
        )
        text = resp.content[0].text.strip()

        # Extract JSON
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            data = json.loads(match.group(0))
        else:
            data = {
                "topic":         text[:80],
                "caption":       text,
                "seo_keywords":  "",
                "hashtags":      "",
                "content_notes": "",
            }

        return JSONResponse({"ok": True, **data})

    except Exception as e:
        logger.warning(f"auto-create error: {e}")
        return JSONResponse(
            {"error": f"Auto-create failed: {str(e)}", "ok": False},
            status_code=500,
        )


# ─── HTML Page ────────────────────────────────────────────────────────────────

_CALENDAR_CSS = """
/* ── Calendar page layout ──────────────────────────────── */
.cal-header{display:flex;align-items:center;justify-content:space-between;margin-bottom:20px;flex-wrap:wrap;gap:12px}
.cal-header h1{font-size:1.3rem;font-weight:800}
.cal-tabs{display:flex;gap:6px}
.cal-tab{padding:6px 16px;border-radius:8px;font-size:.83rem;font-weight:600;color:#606770;background:#fff;border:1px solid #dde0e4;cursor:pointer;transition:all .12s}
.cal-tab.active{background:#5c6ac4;color:#fff;border-color:#5c6ac4}

/* ── Month grid ────────────────────────────────────────── */
.month-grid{background:#fff;border-radius:12px;box-shadow:0 1px 4px rgba(0,0,0,.06);overflow:hidden;margin-bottom:20px;position:relative;min-height:420px}
.month-nav{display:flex;align-items:center;justify-content:space-between;padding:16px 20px;border-bottom:1px solid #f0f2f5}
.month-nav h2{font-size:1rem;font-weight:700}
.month-nav button{background:#f0f2f5;border:none;border-radius:8px;padding:6px 12px;cursor:pointer;font-size:.85rem;font-weight:600}
.month-nav button:hover{background:#e4e6eb}
.cal-grid{display:grid;grid-template-columns:repeat(7,1fr)}
.cal-day-label{text-align:center;font-size:.72rem;font-weight:700;color:#90949c;text-transform:uppercase;padding:10px 4px;background:#fafbff;border-bottom:1px solid #f0f2f5}
.cal-cell{min-height:90px;padding:6px;border-right:1px solid #f0f2f5;border-bottom:1px solid #f0f2f5;cursor:pointer;transition:background .1s;position:relative}
.cal-cell:nth-child(7n){border-right:none}
.cal-cell:hover{background:#fafbff}
.cal-cell.today .day-num{background:#5c6ac4;color:#fff;border-radius:50%;width:24px;height:24px;display:flex;align-items:center;justify-content:center}
.cal-cell.selected{background:#f0eeff;outline:2px solid #5c6ac4;outline-offset:-2px;border-radius:4px}
.cal-cell.other-month .day-num{color:#c0c4cc}
.day-num{font-size:.82rem;font-weight:600;color:#1c1e21;margin-bottom:4px;width:24px;height:24px;display:flex;align-items:center;justify-content:center}
.cal-post-pill{font-size:.68rem;font-weight:600;padding:2px 5px;border-radius:4px;margin-bottom:2px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;cursor:pointer}
.cal-post-pill.instagram{background:#ede8f5;color:#764ba2}
.cal-post-pill.facebook{background:#e8f0fe;color:#1565c0}
.cal-post-pill.twitter{background:#e0f7fa;color:#00838f}
.cal-post-pill.tiktok{background:#fce4ec;color:#c62828}
.cal-post-pill.linkedin{background:#e3f2fd;color:#1565c0}
.cal-post-pill.threads{background:#f3e5f5;color:#6a1b9a}
.cal-post-pill.youtube{background:#ffebee;color:#b71c1c}
.cal-post-pill.other{background:#f0f2f5;color:#555}

/* ── List view ─────────────────────────────────────────── */
.post-list{background:#fff;border-radius:12px;box-shadow:0 1px 4px rgba(0,0,0,.06);overflow:hidden}
.post-list-header{padding:16px 20px;border-bottom:1px solid #f0f2f5;font-weight:700;font-size:.92rem}
.post-row{display:flex;align-items:flex-start;gap:14px;padding:14px 20px;border-bottom:1px solid #f0f2f5;transition:background .12s}
.post-row:last-child{border-bottom:none}
.post-row:hover{background:#fafbff}
.post-platform-badge{font-size:.72rem;font-weight:700;padding:3px 9px;border-radius:99px;white-space:nowrap}
.post-row .post-time{font-size:.78rem;color:#90949c;white-space:nowrap;min-width:130px}
.post-caption-preview{font-size:.85rem;flex:1;color:#1c1e21;line-height:1.45;overflow:hidden;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical}
.post-actions{display:flex;gap:6px;flex-shrink:0}
.act-btn{padding:5px 10px;border-radius:6px;font-size:.75rem;font-weight:600;cursor:pointer}
.act-edit{background:#e8f0fe;color:#1565c0}
.act-del{background:#fce4ec;color:#c62828}
.act-btn:hover{opacity:.8}

/* ── Add-post panel ────────────────────────────────────── */
.add-post-panel{background:#fff;border-radius:12px;box-shadow:0 1px 4px rgba(0,0,0,.06);padding:24px;margin-bottom:20px;display:none}
.add-post-panel.open{display:block}
.panel-header{display:flex;align-items:center;justify-content:space-between;margin-bottom:20px}
.panel-header h2{font-size:1rem;font-weight:700}
.panel-close{background:#f0f2f5;border-radius:8px;padding:5px 10px;font-size:.82rem;font-weight:600}
.form-row{display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-bottom:14px}
.form-row-3{display:grid;grid-template-columns:1fr 1fr 1fr;gap:14px;margin-bottom:14px}
.slot-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin:10px 0}
.slot-btn{padding:9px 8px;border-radius:8px;border:1px solid #dde0e4;background:#fff;font-size:.78rem;font-weight:600;cursor:pointer;text-align:center;transition:all .15s;line-height:1.3}
.slot-btn:hover{border-color:#5c6ac4;color:#5c6ac4}
.slot-btn.selected{background:#5c6ac4;color:#fff;border-color:#5c6ac4}
.slot-btn.high{border-left:3px solid #2e7d32}
.slot-btn.medium{border-left:3px solid #1565c0}

/* ── Auto-create section ───────────────────────────────── */
.auto-create-box{background:#f8f5fb;border:1px solid #d8d0ec;border-radius:10px;padding:16px;margin-bottom:16px}
.auto-create-box h3{font-size:.9rem;font-weight:700;color:#5c6ac4;margin-bottom:10px}

/* ── Modal overlay ────────────────────────────────── */
.modal-overlay{position:fixed;inset:0;background:rgba(0,0,0,.45);z-index:200;display:none;align-items:center;justify-content:center}
.modal-overlay.open{display:flex}
.modal-box{background:#fff;border-radius:14px;padding:28px;max-width:560px;width:90%;max-height:90vh;overflow-y:auto;box-shadow:0 8px 32px rgba(0,0,0,.18)}
.modal-box h2{font-size:1.05rem;font-weight:700;margin-bottom:18px}
.modal-footer{display:flex;gap:10px;justify-content:flex-end;margin-top:20px}

/* ── Day Detail Modal ─────────────────────────────── */
.day-detail-box{background:#fff;border-radius:14px;padding:24px;max-width:520px;width:93%;max-height:85vh;overflow-y:auto;box-shadow:0 8px 32px rgba(0,0,0,.22)}
.day-detail-header{display:flex;align-items:center;justify-content:space-between;margin-bottom:16px}
.day-detail-header h2{font-size:1.05rem;font-weight:700;margin:0}
.day-detail-close{background:none;border:none;font-size:1.1rem;cursor:pointer;color:#606770;padding:4px 8px}
.day-detail-close:hover{color:#1c1e21}
.day-detail-list{list-style:none;padding:0;margin:0}
.day-detail-item{display:flex;align-items:center;gap:10px;padding:10px 12px;border-radius:10px;cursor:pointer;transition:background .15s}
.day-detail-item:hover{background:#f5f6f8}
.day-detail-time{font-size:.82rem;font-weight:700;color:#374151;min-width:48px}
.day-detail-badge{font-size:.7rem;font-weight:600;color:#fff;padding:2px 8px;border-radius:6px;text-transform:capitalize}
.day-detail-badge.instagram{background:#e1306c}.day-detail-badge.facebook{background:#1877f2}
.day-detail-badge.twitter{background:#1da1f2}.day-detail-badge.tiktok{background:#010101}
.day-detail-badge.linkedin{background:#0077b5}.day-detail-badge.threads{background:#333}
.day-detail-badge.youtube{background:#ff0000}.day-detail-badge.other{background:#90949c}
.day-detail-type{font-size:.7rem;color:#90949c;font-weight:500}
.day-detail-topic{font-size:.82rem;color:#374151;flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.day-detail-status{font-size:.68rem;font-weight:600;padding:2px 7px;border-radius:5px}
.day-detail-status.planned{background:#fef3c7;color:#92400e}
.day-detail-status.scheduled{background:#dbeafe;color:#1e40af}
.day-detail-status.approved{background:#d1fae5;color:#065f46}
.day-detail-status.posted{background:#e0e7ff;color:#3730a3}
.day-detail-status.failed{background:#fee2e2;color:#991b1b}
.day-detail-warn{color:#f59e0b;font-size:.75rem;margin-left:2px}
.day-detail-add{display:block;width:100%;margin-top:12px;padding:10px;background:#f5f6f8;border:1.5px dashed #d1d5db;border-radius:10px;cursor:pointer;font-size:.84rem;font-weight:600;color:#5c6ac4;text-align:center;transition:background .15s}
.day-detail-add:hover{background:#eef0fd}
.day-detail-empty{text-align:center;padding:32px 16px;color:#90949c;font-size:.88rem}

/* ── Quick-add floating button ─────────────────────────── */
.fab{
  position:fixed;bottom:28px;right:28px;
  width:52px;height:52px;border-radius:50%;
  background:linear-gradient(135deg,#5c6ac4,#764ba2);
  color:#fff;font-size:1.5rem;display:flex;align-items:center;justify-content:center;
  box-shadow:0 4px 16px rgba(92,106,196,.4);cursor:pointer;z-index:150;
  transition:transform .15s;
}
.fab:hover{transform:scale(1.07)}

/* ── Insights bar ─────────────────────────────────────── */
.insights-bar{background:#e8f0fe;border-radius:10px;padding:12px 16px;margin-bottom:18px;font-size:.83rem;color:#1565c0;display:none}
.insights-bar.show{display:block}
.insights-bar ul{margin:6px 0 0 16px}
.insights-bar li{margin-bottom:2px}

/* ── Post quota bar ───────────────────────────────────── */
.quota-bar-wrap{background:#fff;border-radius:10px;padding:12px 18px;margin-bottom:18px;
  box-shadow:0 1px 4px rgba(0,0,0,.06);display:flex;align-items:center;gap:16px;flex-wrap:wrap}
.quota-label{font-size:.82rem;font-weight:700;color:#374151;white-space:nowrap}
.quota-track{flex:1;min-width:120px;height:8px;background:#f0f2f5;border-radius:4px;overflow:hidden}
.quota-fill{height:100%;border-radius:4px;transition:width .4s}
.quota-fill.ok{background:#16a34a}
.quota-fill.warn{background:#f59e0b}
.quota-fill.danger{background:#dc2626}
.quota-text{font-size:.8rem;color:#6b7280;white-space:nowrap}
.quota-upgrade{padding:5px 12px;background:transparent;border:1.5px solid #7c3aed;color:#7c3aed;
  border-radius:7px;font-size:.78rem;font-weight:700;cursor:pointer;text-decoration:none;
  white-space:nowrap;transition:all .15s}
.quota-upgrade:hover{background:#7c3aed;color:#fff}

/* ── Empty state ──────────────────────────────────────── */
.empty-cal{text-align:center;padding:48px 20px;color:#90949c}
.cal-empty-overlay{
  display:none;align-items:center;justify-content:center;
  position:absolute;inset:0;z-index:10;
  background:rgba(255,255,255,.85);
  border-radius:12px;
}
.empty-cal-card{
  text-align:center;padding:48px 36px;max-width:420px;
  background:#fff;border-radius:16px;
  box-shadow:0 4px 24px rgba(0,0,0,.08);
}
.empty-cal-icon{font-size:3rem;margin-bottom:12px}
.empty-cal-card h3{font-size:1.15rem;font-weight:800;color:#1c1e21;margin-bottom:10px}
.empty-cal-card p{font-size:.88rem;color:#606770;line-height:1.6;margin-bottom:16px}
.empty-cal-gen-btn{
  font-size:.95rem;padding:12px 28px;
  background:linear-gradient(135deg,#5c6ac4,#764ba2);color:#fff;
  border:none;border-radius:10px;font-weight:700;cursor:pointer;
  transition:opacity .15s;
}
.empty-cal-gen-btn:hover{opacity:.88}
.empty-cal-hint{font-size:.78rem;color:#90949c;margin-top:14px;margin-bottom:0}
.empty-cal .icon{font-size:2.4rem;margin-bottom:12px}

/* ── AI Generation overlay ────────────────────────────── */
.ai-gen-overlay{
  position:fixed;inset:0;background:rgba(0,0,0,.55);
  z-index:500;display:none;flex-direction:column;
  align-items:center;justify-content:center;gap:16px;
}
.ai-gen-spinner{
  width:56px;height:56px;border-radius:50%;
  border:5px solid rgba(255,255,255,.25);
  border-top-color:#fff;
  animation:ai-spin 0.9s linear infinite;
}
@keyframes ai-spin{to{transform:rotate(360deg)}}
.ai-gen-card{
  background:#fff;border-radius:14px;padding:28px 36px;
  text-align:center;max-width:340px;
  box-shadow:0 8px 30px rgba(0,0,0,.25);
}
.ai-gen-card h3{font-size:1rem;font-weight:700;margin-bottom:8px;color:#1c1e21}
.ai-gen-card p{font-size:.85rem;color:#606770;line-height:1.5}
"""

_CALENDAR_JS = """
// ── State ──────────────────────────────────────────────────────────────
let allPosts      = [];
let currentYear   = new Date().getFullYear();
let currentMonth  = new Date().getMonth();    // 0-indexed
let viewMode      = 'month';  // 'month' | 'list'
let editingPostId = null;

const PLATFORMS = ['instagram','facebook','twitter','tiktok','linkedin','threads','youtube'];
const MONTH_NAMES = ['January','February','March','April','May','June',
                     'July','August','September','October','November','December'];
const PLATFORM_NAMES = {instagram:'Instagram',facebook:'Facebook',twitter:'Twitter/X',linkedin:'LinkedIn',tiktok:'TikTok',threads:'Threads',youtube:'YouTube'};

// Convert 24h HH:MM to 12h format (e.g. "14:30" → "2:30 PM")
function to12h(hhmm) {
  if (!hhmm || hhmm.length < 5) return hhmm || '';
  var parts = hhmm.split(':');
  var h = parseInt(parts[0], 10);
  var m = parts[1];
  if (isNaN(h)) return hhmm;
  var ampm = h >= 12 ? 'PM' : 'AM';
  h = h % 12 || 12;
  return h + ':' + m + ' ' + ampm;
}

// Proper display name for a platform
function platName(p) { return PLATFORM_NAMES[(p||'').toLowerCase()] || p || 'Other'; }

// ── Boot ───────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', async () => {
  try {
    await loadPosts();
    loadQuota();
    var _pp = document.getElementById('panel-platform');
    var _pc = document.getElementById('panel-content-type');
    if (_pp) _pp.addEventListener('change', () => clearSlots());
    if (_pc) _pc.addEventListener('change', () => clearSlots());
  } catch(e) { console.error('Calendar boot error:', e); }
});

// ── Post quota bar ─────────────────────────────────────────────────────
async function loadQuota() {
  try {
    const r = await fetch('/api/calendar/quota');
    const q = await r.json();
    const bar   = document.getElementById('quota-bar');
    const fill  = document.getElementById('quota-fill');
    const text  = document.getElementById('quota-text');
    const upBtn = document.getElementById('quota-upgrade');
    if (!bar) return;
    bar.style.display = '';

    if (q.limit === -1) {
      // Unlimited plan
      fill.style.width = '0%';
      fill.className   = 'quota-fill ok';
      text.textContent = `${q.used} scheduled \u2022 Unlimited (${q.tier_name})`;
      return;
    }

    const pct = Math.min(100, q.pct);
    fill.style.width = pct + '%';
    fill.className   = 'quota-fill ' + (pct >= 90 ? 'danger' : pct >= 70 ? 'warn' : 'ok');
    text.textContent = `${q.used} / ${q.limit} posts used \u2022 ${q.remaining ?? 0} remaining (${q.tier_name})`;

    if (!q.allowed || q.remaining === 0) {
      upBtn.style.display = '';
      upBtn.textContent   = '\u2191 Upgrade or Add Posts';
    } else if (q.remaining !== null && q.remaining <= 5) {
      upBtn.style.display = '';
      upBtn.textContent   = `\u26A0\uFE0F Only ${q.remaining} left — Add More`;
    }
  } catch(e) { console.warn('loadQuota error', e); }
}

// ── Load all posts from API ────────────────────────────────────────────
async function loadPosts() {
  try {
    const r = await fetch('/api/calendar/posts');
    const d = await r.json();
    allPosts = d.posts || [];
    renderCalendar();
    renderList();
  } catch(e) { console.warn('loadPosts error', e); }
}

// ── View mode toggle ───────────────────────────────────────────────────
function setView(mode) {
  viewMode = mode;
  document.getElementById('view-month').classList.toggle('active', mode === 'month');
  document.getElementById('view-list').classList.toggle('active',  mode === 'list');
  document.getElementById('month-section').style.display = mode === 'month' ? '' : 'none';
  document.getElementById('list-section').style.display  = mode === 'list'  ? '' : 'none';
}

// ══════════════════════════════════════════════════════════════════════
// MONTH GRID
// ══════════════════════════════════════════════════════════════════════
function renderCalendar() {
  const titleEl = document.getElementById('month-title');
  if (titleEl) titleEl.textContent = MONTH_NAMES[currentMonth] + ' ' + currentYear;

  const grid = document.getElementById('cal-cells');
  if (!grid) return;
  grid.innerHTML = '';

  const firstDay = new Date(currentYear, currentMonth, 1).getDay(); // 0=Sun
  const daysInMonth = new Date(currentYear, currentMonth + 1, 0).getDate();
  const today = new Date();

  // Leading blanks from previous month
  const prevDays = new Date(currentYear, currentMonth, 0).getDate();
  for (let i = firstDay; i > 0; i--) {
    const cell = makeCell(prevDays - i + 1, true);
    grid.appendChild(cell);
  }

  // Current month days
  for (let d = 1; d <= daysInMonth; d++) {
    const isToday = (
      today.getFullYear() === currentYear &&
      today.getMonth()    === currentMonth &&
      today.getDate()     === d
    );
    const cell = makeCell(d, false, isToday);
    const dateStr = formatDateStr(currentYear, currentMonth + 1, d);

    // Attach posts
    const dayPosts = allPosts.filter(p => (p.scheduled_time || '').startsWith(dateStr));
    dayPosts.slice(0, 3).forEach(p => {
      const pill = document.createElement('div');
      pill.className = 'cal-post-pill ' + (p.platform || 'other');
      const t = to12h((p.scheduled_time || '').slice(11, 16));
      const pn = platName(p.platform);
      const ct = p.content_type || 'post';
      const ctLabel = ct.charAt(0).toUpperCase() + ct.slice(1);
      pill.textContent = t + ' ' + pn + ' \u00b7 ' + ctLabel;
      pill.title = pn + ' ' + ctLabel + ' at ' + t + (p.topic ? ' \u2014 ' + p.topic : '');
      pill.onclick = (ev) => { ev.stopPropagation(); openEditModal(p); };
      cell.appendChild(pill);
    });
    if (dayPosts.length > 3) {
      const more = document.createElement('div');
      more.style.cssText = 'font-size:.66rem;color:#90949c;padding:1px 4px;cursor:pointer';
      more.textContent = '+' + (dayPosts.length - 3) + ' more';
      more.onclick = (ev) => { ev.stopPropagation(); openDayDetail(dateStr, dayPosts); };
      cell.appendChild(more);
    }

    // Click date cell -> open day detail view (shows all posts)
    cell.addEventListener('click', () => {
      grid.querySelectorAll('.cal-cell.selected').forEach(c => c.classList.remove('selected'));
      cell.classList.add('selected');
      openDayDetail(dateStr, dayPosts);
    });
    grid.appendChild(cell);
  }

  // Trailing blanks
  const totalCells = firstDay + daysInMonth;
  const trailing   = (7 - (totalCells % 7)) % 7;
  for (let i = 1; i <= trailing; i++) {
    grid.appendChild(makeCell(i, true));
  }

  // Empty-state overlay — shown when no posts exist at all
  var calWrap = grid.parentElement;
  var emptyOverlay = calWrap ? calWrap.querySelector('.cal-empty-overlay') : null;
  if (!emptyOverlay && calWrap) {
    emptyOverlay = document.createElement('div');
    emptyOverlay.className = 'cal-empty-overlay';
    emptyOverlay.innerHTML =
      '<div class="empty-cal-card">' +
        '<div class="empty-cal-icon">&#128197;</div>' +
        '<h3>Your calendar is empty</h3>' +
        '<p>No posts are scheduled yet. Let the AI build your content calendar ' +
          'based on your brand, niche, and connected platforms.</p>' +
        '<button class="btn-primary empty-cal-gen-btn" onclick="generateAICalendar()">' +
          '&#10024; Generate AI Calendar' +
        '</button>' +
        '<p class="empty-cal-hint">Or click <b>+ Schedule Post</b> above to add one manually.</p>' +
      '</div>';
    calWrap.appendChild(emptyOverlay);
  }
  if (emptyOverlay) {
    emptyOverlay.style.display = allPosts.length === 0 ? 'flex' : 'none';
  }
}

function makeCell(day, otherMonth, isToday = false) {
  const cell = document.createElement('div');
  cell.className = 'cal-cell' + (otherMonth ? ' other-month' : '') + (isToday ? ' today' : '');
  const num = document.createElement('div');
  num.className = 'day-num';
  num.textContent = day;
  cell.appendChild(num);
  return cell;
}

function formatDateStr(y, m, d) {
  return y + '-' + String(m).padStart(2, '0') + '-' + String(d).padStart(2, '0');
}

function prevMonth() {
  currentMonth--;
  if (currentMonth < 0) { currentMonth = 11; currentYear--; }
  renderCalendar();
}
function nextMonth() {
  currentMonth++;
  if (currentMonth > 11) { currentMonth = 0; currentYear++; }
  renderCalendar();
}

// ══════════════════════════════════════════════════════════════════════
// LIST VIEW
// ══════════════════════════════════════════════════════════════════════
function renderList() {
  const container = document.getElementById('post-list-body');
  if (!container) return;

  const platformFilter = (document.getElementById('filter-platform') || {}).value || '';
  const filtered = platformFilter
    ? allPosts.filter(p => p.platform === platformFilter)
    : allPosts;

  if (filtered.length === 0) {
    container.innerHTML = (
      "<div class='empty-cal' style='padding:48px 20px;text-align:center'>" +
      "<div style='font-size:2.4rem;margin-bottom:12px'>&#128197;</div>" +
      "<p style='font-weight:700;font-size:1rem;color:#374151;margin-bottom:8px'>No scheduled posts yet</p>" +
      "<p style='font-size:.85rem;color:#606770;margin-bottom:16px'>Let the AI build your content calendar or add a post manually.</p>" +
      "<button class='btn-primary' style='background:linear-gradient(135deg,#5c6ac4,#764ba2);border:none;padding:10px 24px;border-radius:10px;font-weight:700;cursor:pointer;color:#fff;font-size:.9rem' onclick='generateAICalendar()'>&#10024; Generate AI Calendar</button>" +
      "<p style='margin-top:12px'><a href='#' onclick='openAddPanel(); return false;' style='color:#5c6ac4;font-weight:600;font-size:.85rem'>or + Schedule a post manually</a></p>" +
      "</div>"
    );
    return;
  }

  container.innerHTML = filtered.map(p => {
    const dt  = p.scheduled_time ? new Date(p.scheduled_time) : null;
    const dtStr = dt ? dt.toLocaleString('en-US', {month:'short',day:'numeric',year:'numeric',hour:'numeric',minute:'2-digit'}) : '-';
    const cap = (p.caption || p.topic || '(auto-generated)').slice(0, 120);
    const plat = p.platform || 'other';
    return (
      '<div class="post-row">' +
      '  <div class="post-time">' + dtStr + '</div>' +
      '  <span class="post-platform-badge cal-post-pill ' + plat + '">' + plat + (p.content_type && p.content_type !== 'post' ? ' &bull; ' + escHtml(p.content_type) : '') + '</span>' +
      (['instagram','tiktok','youtube'].includes(plat) && !p.image_url ? '  <span style="color:#f59e0b;font-size:.75rem;font-weight:600;margin-left:4px" title="No image/video URL — post will be skipped at publish time">⚠️ no media</span>' : '') +
      '  <div class="post-caption-preview">' + escHtml(cap) + '</div>' +
      '  <div class="post-actions">' +
      '    <button class="act-btn act-edit" data-pid="' + escHtml(p.id || '') + '" onclick="openEditModalById(this.dataset.pid)">Edit</button>' +
      '    <button class="act-btn act-del"  data-pid="' + escHtml(p.id || '') + '" onclick="deletePost(this.dataset.pid)">Delete</button>' +
      '  </div>' +
      '</div>'
    );
  }).join('');
}

function escHtml(s) {
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}

// ══════════════════════════════════════════════════════════════════════
// ADD / EDIT PANEL
// ══════════════════════════════════════════════════════════════════════
function openAddPanel(prefillDate) {
  editingPostId = null;
  document.getElementById('add-post-panel').classList.add('open');
  document.getElementById('panel-post-id').value = '';
  document.getElementById('panel-caption').value = '';
  document.getElementById('panel-image-url').value = '';
  document.getElementById('panel-topic').value = '';
  document.getElementById('panel-seo').value = '';
  document.getElementById('panel-scheduled-time').value =
    prefillDate ? (prefillDate + 'T10:00') : '';
  document.getElementById('panel-platform').value = 'instagram';
  clearSlots();
  document.getElementById('add-post-panel').scrollIntoView({behavior:'smooth'});
}

function closeAddPanel() {
  document.getElementById('add-post-panel').classList.remove('open');
}

async function getRecommendedSlots() {
  const platform    = document.getElementById('panel-platform').value;
  const contentType = document.getElementById('panel-content-type').value;
  const slotsDiv    = document.getElementById('slots-container');
  const insightsBar = document.getElementById('insights-bar');
  const slotBtn     = document.getElementById('get-slots-btn');

  slotBtn.disabled    = true;
  slotBtn.textContent = '⟳ Loading…';
  slotsDiv.innerHTML  = '<span style="font-size:.8rem;color:#90949c">Asking AI for best times…</span>';
  insightsBar.classList.remove('show');

  try {
    const r = await fetch('/api/calendar/recommended-slots', {
      method: 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify({platform, content_type: contentType, timezone: Intl.DateTimeFormat().resolvedOptions().timeZone})
    });
    const d = await r.json();

    const slots = d.concrete_slots || [];
    if (slots.length === 0) {
      slotsDiv.innerHTML = '<span style="font-size:.8rem;color:#90949c">No slots available.</span>';
    } else {
      slotsDiv.innerHTML = '';
      slots.forEach(s => {
        const btn = document.createElement('button');
        btn.type      = 'button';
        btn.className = 'slot-btn ' + (s.priority || 'medium');
        btn.innerHTML = '<strong>' + escHtml(s.day || '') + '</strong><br>' + escHtml((s.label || s.datetime_local || '').replace(/.*at /,''));
        btn.onclick   = () => selectSlot(btn, s.datetime_local);
        slotsDiv.appendChild(btn);
      });
    }

    const insights = d.insights || [];
    if (insights.length > 0) {
      insightsBar.innerHTML = '<strong>&#128161; AI Insights:</strong><ul>' +
        insights.map(i => '<li>' + escHtml(i) + '</li>').join('') + '</ul>';
      insightsBar.classList.add('show');
    }
  } catch(e) {
    slotsDiv.innerHTML = '<span style="color:#c62828;font-size:.8rem">Failed to load slots.</span>';
  }

  slotBtn.disabled    = false;
  slotBtn.textContent = '&#127775; Get Recommended Times';
}

function selectSlot(btn, datetimeLocal) {
  document.querySelectorAll('.slot-btn').forEach(b => b.classList.remove('selected'));
  btn.classList.add('selected');
  document.getElementById('panel-scheduled-time').value = datetimeLocal;
}

function clearSlots() {
  const d = document.getElementById('slots-container');
  if (d) d.innerHTML = '';
}

// ── Auto-create topic ────────────────────────────────────────────────
async function autoCreateTopic() {
  const platform    = document.getElementById('panel-platform').value;
  const contentType = document.getElementById('panel-content-type').value;
  const btn         = document.getElementById('auto-create-btn');

  btn.disabled    = true;
  btn.textContent = '⟳ Generating…';

  try {
    const r = await fetch('/api/calendar/auto-create', {
      method: 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify({platform, content_type: contentType})
    });
    const d = await r.json();
    if (d.ok) {
      if (d.topic)        document.getElementById('panel-topic').value   = d.topic;
      if (d.caption)      document.getElementById('panel-caption').value = d.caption;
      if (d.seo_keywords) document.getElementById('panel-seo').value     = d.seo_keywords;
      showToast('✅ Topic generated by AI!');
    } else {
      showToast('❌ ' + (d.error || 'Auto-create failed'));
    }
  } catch(e) {
    showToast('❌ Network error');
  }

  btn.disabled    = false;
  btn.textContent = '&#9889; Auto-Generate Topic';
}

// ── Save / submit post ────────────────────────────────────────────────
async function saveScheduledPost() {
  const postId       = document.getElementById('panel-post-id').value.trim();
  const platform     = document.getElementById('panel-platform').value;
  const contentType  = document.getElementById('panel-content-type').value;
  const caption      = document.getElementById('panel-caption').value.trim();
  const imageUrl     = document.getElementById('panel-image-url').value.trim();
  const topic        = document.getElementById('panel-topic').value.trim();
  const seo          = document.getElementById('panel-seo').value.trim();
  const scheduledTime= document.getElementById('panel-scheduled-time').value.trim();

  if (!platform || !scheduledTime) {
    showToast('❌ Platform and scheduled time are required');
    return;
  }

  // Warn if media-required platform has no image URL
  const _mReq = ['instagram', 'tiktok', 'youtube'];
  if (_mReq.includes(platform) && !imageUrl) {
    document.getElementById('panel-image-url').style.borderColor = '#ef4444';
    showToast('⚠️ ' + platform.charAt(0).toUpperCase() + platform.slice(1) + ' requires an image or video URL — this post will be skipped at publish time without one.');
  } else {
    document.getElementById('panel-image-url').style.borderColor = '';
  }

  const saveBtn = document.getElementById('save-post-btn');
  saveBtn.disabled = true;
  saveBtn.textContent = '⟳ Saving…';

  try {
    let url = '/api/calendar/schedule-post';
    let method = 'POST';
    if (postId) { url = '/api/calendar/posts/' + postId; method = 'PUT'; }

    const r = await fetch(url, {
      method,
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify({
        platform, content_type: contentType,
        caption, image_url: imageUrl,
        topic, seo_keywords: seo,
        scheduled_time: scheduledTime,
      })
    });
    const d = await r.json();
    if (d.ok) {
      showToast(postId ? '✅ Post updated!' : '✅ Post scheduled!');
      closeAddPanel();
      await loadPosts();
      loadQuota();  // refresh quota bar after scheduling
    } else if (d.quota_exceeded) {
      // Show a blocking message with upgrade link
      showToast('⛔ ' + (d.error || 'Monthly post limit reached.'));
      document.getElementById('quota-upgrade').style.display = '';
      document.getElementById('quota-upgrade').textContent   = '⬆️ Upgrade or Add Posts';
    } else {
      showToast('❌ ' + (d.error || 'Save failed'));
    }
  } catch(e) {
    showToast('❌ Network error');
  }

  saveBtn.disabled    = false;
  saveBtn.textContent = '&#128197; Save to Calendar';
}

// ── Edit modal ────────────────────────────────────────────────────────
function openEditModal(post) {
  editingPostId = post.id;
  document.getElementById('modal-post-id').value         = post.id;
  document.getElementById('modal-platform').value        = post.platform || 'instagram';
  document.getElementById('modal-content-type').value    = post.content_type || 'post';
  document.getElementById('modal-caption').value         = post.caption || '';
  document.getElementById('modal-image-url').value       = post.image_url || '';
  document.getElementById('modal-topic').value           = post.topic || '';
  document.getElementById('modal-seo').value             = post.seo_keywords || '';
  document.getElementById('modal-scheduled-time').value  = (post.scheduled_time || '').slice(0,16);
  document.getElementById('edit-modal').classList.add('open');
}

function closeEditModal() {
  document.getElementById('edit-modal').classList.remove('open');
  editingPostId = null;
}

async function saveEditModal() {
  const postId      = document.getElementById('modal-post-id').value.trim();
  const platform    = document.getElementById('modal-platform').value;
  const contentType = document.getElementById('modal-content-type').value;
  const caption     = document.getElementById('modal-caption').value.trim();
  const imageUrl    = document.getElementById('modal-image-url').value.trim();
  const topic       = document.getElementById('modal-topic').value.trim();
  const seo         = document.getElementById('modal-seo').value.trim();
  const scheduledTime = document.getElementById('modal-scheduled-time').value.trim();

  if (!postId || !scheduledTime) {
    showToast('❌ Scheduled time is required');
    return;
  }

  // Warn if media-required platform has no image URL
  const _mReqM = ['instagram', 'tiktok', 'youtube'];
  if (_mReqM.includes(platform) && !imageUrl) {
    document.getElementById('modal-image-url').style.borderColor = '#ef4444';
    showToast('⚠️ ' + platform.charAt(0).toUpperCase() + platform.slice(1) + ' requires an image or video URL — this post will be skipped at publish time without one.');
  } else {
    document.getElementById('modal-image-url').style.borderColor = '';
  }

  const btn = document.getElementById('modal-save-btn');
  btn.disabled    = true;
  btn.textContent = '⟳ Saving…';

  try {
    const r = await fetch('/api/calendar/posts/' + postId, {
      method: 'PUT',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify({platform, content_type: contentType, caption, image_url: imageUrl, topic, seo_keywords: seo, scheduled_time: scheduledTime})
    });
    const d = await r.json();
    if (d.ok) {
      showToast('✅ Changes saved!');
      closeEditModal();
      await loadPosts();
    } else {
      showToast('❌ ' + (d.error || 'Save failed'));
    }
  } catch(e) {
    showToast('❌ Network error');
  }

  btn.disabled    = false;
  btn.textContent = '&#128197; Save Changes';
}

// ── Delete ────────────────────────────────────────────────────────────
async function deletePost(postId) {
  if (!confirm('Delete this scheduled post?')) return;
  try {
    const r = await fetch('/api/calendar/posts/' + postId, {method:'DELETE'});
    const d = await r.json();
    if (d.ok) { showToast('Post deleted'); await loadPosts(); }
    else showToast('❌ ' + (d.error || 'Delete failed'));
  } catch(e) { showToast('❌ Network error'); }
}

// ── Day Detail Modal ──────────────────────────────────────────────────
function openDayDetail(dateStr, dayPosts) {
  var modal = document.getElementById('day-detail-modal');
  var title = document.getElementById('day-detail-title');
  var list  = document.getElementById('day-detail-list');
  var addBtn = document.getElementById('day-detail-add-btn');
  if (!modal || !list) return;

  // Format the date nicely
  var parts = dateStr.split('-');
  var dateObj = new Date(parseInt(parts[0]), parseInt(parts[1]) - 1, parseInt(parts[2]));
  var dateLabel = dateObj.toLocaleDateString('en-US', {weekday: 'long', month: 'long', day: 'numeric', year: 'numeric'});
  title.textContent = '📅 ' + dateLabel;

  // Sort posts by time
  var sorted = (dayPosts || []).slice().sort(function(a, b) {
    return (a.scheduled_time || '').localeCompare(b.scheduled_time || '');
  });

  if (sorted.length === 0) {
    list.innerHTML = '<li class="day-detail-empty">No posts scheduled for this day.</li>';
  } else {
    list.innerHTML = sorted.map(function(p) {
      var t = to12h((p.scheduled_time || '').slice(11, 16));
      var plat = (p.platform || 'other').toLowerCase();
      var pn = platName(plat);
      var ct = p.content_type || 'post';
      var ctLabel = ct.charAt(0).toUpperCase() + ct.slice(1);
      var status = (p.status || 'scheduled').toLowerCase();
      return (
        '<li class="day-detail-item" data-pid="' + escHtml(p.id || '') + '" onclick="closeDayDetail(); openEditModalById(this.dataset.pid)">' +
        '<span class="day-detail-time">' + escHtml(t) + '</span>' +
        '<span class="day-detail-badge ' + plat + '">' + escHtml(pn) + '</span>' +
        '<span class="day-detail-type">' + escHtml(ctLabel) + '</span>' +
        (p.topic ? '<span class="day-detail-topic">' + escHtml(p.topic) + '</span>' : '') +
        '<span class="day-detail-status ' + status + '">' + escHtml(status) + '</span>' +
        '</li>'
      );
    }).join('');
  }

  addBtn.onclick = function() { closeDayDetail(); openAddPanel(dateStr); };
  modal.classList.add('open');
}
function closeDayDetail() {
  var modal = document.getElementById('day-detail-modal');
  if (modal) modal.classList.remove('open');
}

// ── Generate AI Calendar ────────────────────────────────────────────
// ── Lookup post by id then open edit modal ──────────────────────────────
function openEditModalById(pid) {
  var post = allPosts.find(function(p){ return p.id === pid; });
  if (post) openEditModal(post);
  else showToast('Post not found');
}

// ── Generate AI Calendar ───────────────────────────────────────────────
async function generateAICalendar() {
  var btn = document.getElementById('gen-ai-cal-btn');
  if (!btn || btn.dataset.running) return;
  btn.dataset.running = '1';
  btn.disabled = true;
  var origText = btn.innerHTML;

  var overlay = document.getElementById('ai-gen-overlay');
  var msg     = document.getElementById('ai-gen-msg');
  if (overlay) overlay.style.display = 'flex';
  btn.innerHTML = '&#9203; Generating...';
  if (msg) msg.textContent = 'Starting AI calendar generation...';
  showToast('Generating your AI calendar... this usually takes 1\u20133 minutes.');

  function reset() {
    if (overlay) overlay.style.display = 'none';
    btn.disabled = false;
    btn.innerHTML = origText;
    delete btn.dataset.running;
  }

  try {
    var r = await fetch('/api/calendar/generate-orchestrated', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({})
    });
    var d = await r.json();
    if (r.ok && d.calendar_id) {
      var calId = d.calendar_id;
      var polls = 0;
      var maxPolls = 120;
      var poll = setInterval(async function() {
        polls++;
        try {
          var sr = await fetch('/api/calendar/generation-status/' + calId);
          var sd = await sr.json();
          var elapsed = Math.floor(polls * 5 / 60);
          var secs = (polls * 5) % 60;
          var timeStr = elapsed > 0 ? (elapsed + 'm ' + secs + 's') : (secs + 's');
          if (msg) msg.textContent = sd.detail || ('Working... (' + timeStr + ')');

          if (sd.status === 'done') {
            clearInterval(poll);
            var postCount = sd.posts || 0;
            if (postCount > 0) {
              // Hard reload to guarantee fresh calendar display
              showToast(postCount + ' AI posts planned! Reloading calendar...');
              setTimeout(function() { window.location.reload(); }, 1200);
              return;
            }
            await loadPosts();
            reset();
            showToast('Calendar generated but no posts were created. Try again or check connected platforms.');
          } else if (sd.status === 'error') {
            clearInterval(poll);
            reset();
            showToast('Generation failed: ' + (sd.detail || 'Unknown error. Check logs.'));
          } else if (polls >= maxPolls) {
            clearInterval(poll);
            await loadPosts();
            reset();
            showToast('Generation timed out. Check logs. Any completed posts should appear above.');
          }
        } catch(pe) {
          if (polls >= maxPolls) {
            clearInterval(poll);
            await loadPosts();
            reset();
            showToast('Could not check status. Any completed posts should appear above.');
          }
        }
      }, 5000);
    } else {
      reset();
      showToast('Error: ' + (d.error || d.detail || 'Generation failed. Try again.'));
    }
  } catch(e) {
    reset();
    showToast('Network error - please try again.');
  }
}
// ── Toast ─────────────────────────────────────────────────────────────
function showToast(msg) {
  const t = document.getElementById('cal-toast');
  if (!t) return;
  t.textContent = msg;
  t.style.opacity = '1';
  setTimeout(() => { t.style.opacity = '0'; }, 4000);
}

// ── Dismiss generation overlay (user can continue browsing) ───────────
function dismissGenOverlay() {
  var overlay = document.getElementById('ai-gen-overlay');
  if (overlay) overlay.style.display = 'none';
  showToast('Generation continues in the background. Posts will appear when ready.');
}

// Expose real generateAICalendar to fallback stub
window._realGenerateAICalendar = generateAICalendar;
"""


@router.get("/calendar", response_class=HTMLResponse)
async def calendar_page(request: Request):
    from database.db import get_db
    from utils.shared_layout import build_page, get_user_context
    from fastapi.responses import RedirectResponse

    db = next(get_db())
    try:
        user_obj, profile = get_user_context(request, db)
    except Exception:
        user_obj, profile = None, None
    finally:
        db.close()

    if not user_obj:
        return RedirectResponse("/account/login", status_code=303)

    _uname = user_obj.full_name if user_obj else "User"
    _bname = profile.business_name if profile else "My Business"

    body = """
<div class="cal-header">
  <h1>&#128197; Content Calendar</h1>
  <div style="display:flex;gap:10px;align-items:center;flex-wrap:wrap">
    <div class="cal-tabs">
      <button id="view-month" class="cal-tab active" onclick="setView('month')">&#128197; Month</button>
      <button id="view-list"  class="cal-tab"        onclick="setView('list')">&#9776; List</button>
    </div>
    <button class="btn-primary" onclick="openAddPanel()">&#43; Schedule Post</button>
    <button class="btn-secondary" id="gen-ai-cal-btn" onclick="generateAICalendar()" style="background:linear-gradient(135deg,#5c6ac4,#764ba2);color:#fff;border:none">&#10024; Generate AI Calendar</button>
  </div>
</div>

<!-- Inline fallback: ensures generateAICalendar is always defined -->
<script>
if (typeof generateAICalendar === 'undefined') {
  window.generateAICalendar = function() {
    var btn = document.getElementById('gen-ai-cal-btn');
    if (btn) { btn.disabled = true; btn.textContent = 'Loading...'; }
    setTimeout(function() {
      if (typeof window._realGenerateAICalendar === 'function') {
        window._realGenerateAICalendar();
      } else {
        alert('Calendar script is still loading. Please wait a moment and try again.');
        if (btn) { btn.disabled = false; btn.innerHTML = '&#10024; Generate AI Calendar'; }
      }
    }, 500);
  };
}
</script>

<!-- Monthly post quota bar -->
<div id="quota-bar" class="quota-bar-wrap" style="display:none">
  <span class="quota-label">&#128202; Posts This Month</span>
  <div class="quota-track"><div id="quota-fill" class="quota-fill ok" style="width:0%"></div></div>
  <span id="quota-text" class="quota-text">Loading&hellip;</span>
  <a href="/billing" id="quota-upgrade" class="quota-upgrade" style="display:none">&#8679; Add More Posts</a>
</div>

<!-- Add / Edit panel -->
<div id="add-post-panel" class="add-post-panel">
  <input type="hidden" id="panel-post-id">
  <div class="panel-header">
    <h2>&#128197; Schedule a Post</h2>
    <button class="panel-close" onclick="closeAddPanel()">&#10005; Close</button>
  </div>

  <!-- Auto-create section -->
  <div class="auto-create-box">
    <h3>&#9889; Auto-Generate with AI</h3>
    <p style="font-size:.82rem;color:#444;margin-bottom:12px">
      Let the marketing AI suggest a trending topic, caption, and SEO keywords for this slot.
    </p>
    <div class="form-row">
      <div>
        <label class="form-label">Platform</label>
        <select id="panel-platform" class="form-input">
          <option value="instagram">Instagram</option>
          <option value="facebook">Facebook</option>
          <option value="twitter">Twitter/X</option>
          <option value="tiktok">TikTok</option>
          <option value="linkedin">LinkedIn</option>
          <option value="threads">Threads</option>
          <option value="youtube">YouTube</option>
        </select>
      </div>
      <div>
        <label class="form-label">Content Type</label>
        <select id="panel-content-type" class="form-input">
          <option value="post">Post</option>
          <option value="reel">Reel / Short</option>
          <option value="story">Story</option>
          <option value="carousel">Carousel</option>
          <option value="thread">Thread</option>
          <option value="video">Video</option>
        </select>
      </div>
    </div>
    <button id="auto-create-btn" type="button" class="btn-secondary" style="width:100%" onclick="autoCreateTopic()">
      &#9889; Auto-Generate Topic
    </button>
  </div>

  <!-- Recommended time slots -->
  <div style="margin-bottom:16px">
    <label class="form-label">&#127775; Recommended Time Slots</label>
    <p style="font-size:.8rem;color:#606770;margin-bottom:8px">
      AI picks the best times based on platform algorithm research for your audience.
    </p>
    <button id="get-slots-btn" type="button" class="btn-secondary" style="margin-bottom:10px" onclick="getRecommendedSlots()">
      &#127775; Get Recommended Times
    </button>
    <div id="slots-container" class="slot-grid"></div>
    <div id="insights-bar" class="insights-bar"></div>
  </div>

  <!-- Post details -->
  <div class="form-row">
    <div>
      <label class="form-label">Scheduled Date &amp; Time *</label>
      <input type="datetime-local" id="panel-scheduled-time" class="form-input">
    </div>
    <div>
      <label class="form-label">Image / Video URL <span style="font-size:.73rem;color:#f59e0b;font-weight:600">— required for Instagram, TikTok &amp; YouTube</span></label>
      <input type="url" id="panel-image-url" class="form-input" placeholder="https://...">
    </div>
  </div>

  <div style="margin-bottom:14px">
    <label class="form-label">Topic / Hook</label>
    <input type="text" id="panel-topic" class="form-input" placeholder="e.g., 5 ways to grow on Instagram in 2026">
  </div>

  <div style="margin-bottom:14px">
    <label class="form-label">Caption (leave blank to auto-generate at post time)</label>
    <textarea id="panel-caption" class="form-input" rows="3" placeholder="Write your caption here, or leave blank for AI to generate…"></textarea>
  </div>

  <div style="margin-bottom:16px">
    <label class="form-label">SEO Keywords</label>
    <input type="text" id="panel-seo" class="form-input" placeholder="e.g., social media marketing, Instagram growth, content strategy">
  </div>

  <div style="display:flex;gap:10px;justify-content:flex-end">
    <button type="button" class="btn-secondary" onclick="closeAddPanel()">Cancel</button>
    <button id="save-post-btn" type="button" class="btn-primary" onclick="saveScheduledPost()">
      &#128197; Save to Calendar
    </button>
  </div>
</div>

<!-- Month view section -->
<div id="month-section">
  <div class="month-grid">
    <div class="month-nav">
      <button onclick="prevMonth()">&#8592; Prev</button>
      <h2 id="month-title"></h2>
      <button onclick="nextMonth()">Next &#8594;</button>
    </div>
    <div class="cal-grid">
      <div class="cal-day-label">Sun</div>
      <div class="cal-day-label">Mon</div>
      <div class="cal-day-label">Tue</div>
      <div class="cal-day-label">Wed</div>
      <div class="cal-day-label">Thu</div>
      <div class="cal-day-label">Fri</div>
      <div class="cal-day-label">Sat</div>
      <div id="cal-cells" style="display:contents"></div>
    </div>
  </div>
</div>

<!-- List view section -->
<div id="list-section" style="display:none">
  <div class="post-list">
    <div class="post-list-header" style="display:flex;align-items:center;gap:12px">
      <span>Scheduled Posts</span>
      <select id="filter-platform" class="form-input" style="width:auto;font-size:.8rem;padding:5px 10px" onchange="renderList()">
        <option value="">All Platforms</option>
        <option value="instagram">Instagram</option>
        <option value="facebook">Facebook</option>
        <option value="twitter">Twitter/X</option>
        <option value="tiktok">TikTok</option>
        <option value="linkedin">LinkedIn</option>
        <option value="threads">Threads</option>
        <option value="youtube">YouTube</option>
      </select>
    </div>
    <div id="post-list-body"></div>
  </div>
</div>

<!-- Floating action button -->
<div class="fab" onclick="openAddPanel()" title="Schedule a post">&#43;</div>

<!-- Day Detail Modal -->
<div id="day-detail-modal" class="modal-overlay">
  <div class="day-detail-box">
    <div class="day-detail-header">
      <h2 id="day-detail-title">&#128197; Posts for ...</h2>
      <button class="day-detail-close" onclick="closeDayDetail()">&#10005;</button>
    </div>
    <ul id="day-detail-list" class="day-detail-list"></ul>
    <button class="day-detail-add" id="day-detail-add-btn">&#43; Schedule a Post</button>
  </div>
</div>

<!-- Edit Modal -->
<div id="edit-modal" class="modal-overlay">
  <div class="modal-box">
    <h2>&#9998; Edit Scheduled Post</h2>
    <input type="hidden" id="modal-post-id">
    <div class="form-row">
      <div>
        <label class="form-label">Platform</label>
        <select id="modal-platform" class="form-input">
          <option value="instagram">Instagram</option>
          <option value="facebook">Facebook</option>
          <option value="twitter">Twitter/X</option>
          <option value="tiktok">TikTok</option>
          <option value="linkedin">LinkedIn</option>
          <option value="threads">Threads</option>
          <option value="youtube">YouTube</option>
        </select>
      </div>
      <div>
        <label class="form-label">Content Type</label>
        <select id="modal-content-type" class="form-input">
          <option value="post">Post</option>
          <option value="reel">Reel / Short</option>
          <option value="story">Story</option>
          <option value="carousel">Carousel</option>
          <option value="thread">Thread</option>
          <option value="video">Video</option>
        </select>
      </div>
    </div>
    <div style="margin-bottom:12px">
      <label class="form-label">Scheduled Date &amp; Time *</label>
      <input type="datetime-local" id="modal-scheduled-time" class="form-input">
    </div>
    <div style="margin-bottom:12px">
      <label class="form-label">Topic / Hook</label>
      <input type="text" id="modal-topic" class="form-input">
    </div>
    <div style="margin-bottom:12px">
      <label class="form-label">Caption</label>
      <textarea id="modal-caption" class="form-input" rows="4"></textarea>
    </div>
    <div style="margin-bottom:12px">
      <label class="form-label">Image / Video URL <span style="font-size:.73rem;color:#f59e0b;font-weight:600">— required for Instagram, TikTok &amp; YouTube</span></label>
      <input type="url" id="modal-image-url" class="form-input" placeholder="https://...">
    </div>
    <div style="margin-bottom:12px">
      <label class="form-label">SEO Keywords</label>
      <input type="text" id="modal-seo" class="form-input">
    </div>
    <div class="modal-footer">
      <button type="button" class="btn-secondary" onclick="closeEditModal()">Cancel</button>
      <button id="modal-save-btn" type="button" class="btn-primary" onclick="saveEditModal()">&#128197; Save Changes</button>
    </div>
  </div>
</div>

<!-- AI Generation Loading Overlay -->
<div id="ai-gen-overlay" class="ai-gen-overlay">
  <div class="ai-gen-spinner"></div>
  <div class="ai-gen-card">
    <h3>&#10024; Generating Your AI Calendar</h3>
    <p id="ai-gen-msg">Building your content calendar...</p>
    <p style="margin-top:12px;font-size:.78rem;color:#90949c">This usually takes 1\u20133 minutes depending on how many platforms are connected.<br>Please keep this tab open.</p>
    <button onclick="dismissGenOverlay()" style="margin-top:14px;padding:8px 20px;background:#f0f2f5;border:1px solid #d1d5db;border-radius:8px;cursor:pointer;font-size:.82rem;font-weight:600;color:#374151">&#10005; Dismiss &amp; Continue Browsing</button>
    <p style="margin-top:6px;font-size:.72rem;color:#aaa">Generation continues in the background.</p>
  </div>
</div>

<!-- Toast -->
<div id="cal-toast" style="position:fixed;bottom:24px;right:24px;background:#1c1e21;color:#fff;padding:10px 20px;border-radius:10px;font-size:.84rem;font-weight:500;opacity:0;transition:opacity .3s;pointer-events:none;z-index:9999"></div>
"""

    return HTMLResponse(
        build_page(
            title="Content Calendar",
            active_nav="calendar",
            body_content=body,
            extra_css=_CALENDAR_CSS,
            extra_js=_CALENDAR_JS,
            user_name=_uname,
            business_name=_bname,
        ),
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0",
        },
    )
