"""
utils/report_watchdog.py
========================
Report-integrity watchdog — runs at app startup and on-demand.

Responsibilities
────────────────
1. **recover_orphaned_reports()**
   Scans filesystem dirs (storage/growth_reports, storage/strategies,
   storage/report_recovery) for JSON reports not yet in PostgreSQL
   and imports them.

2. **verify_report_integrity()**
   Counts DB reports per client and logs a summary.  Returns a dict
   usable by admin diagnostics endpoint.

3. **startup_watchdog()**
   Convenience wrapper called once from web_app.py on boot.
"""

import json
import logging
from datetime import datetime
from pathlib import Path

log = logging.getLogger("report_watchdog")


# ──────────────────────────────────────────────────────────────────────────────
# 1. Recover orphaned filesystem reports → PostgreSQL
# ──────────────────────────────────────────────────────────────────────────────

def recover_orphaned_reports() -> dict:
    """Scan well-known filesystem dirs and import any report not already in DB.

    Returns: {"scanned": int, "imported": int, "errors": int, "details": [...]}
    """
    from database.db import SessionLocal
    from database.models import GrowthReport

    scanned = imported = errors = 0
    details: list[str] = []

    # All directories that may contain report JSON files
    search_dirs = [
        Path("storage/growth_reports"),
        Path("storage/strategies"),
        Path("storage/report_recovery"),
    ]

    db = SessionLocal()
    try:
        for base_dir in search_dirs:
            if not base_dir.exists():
                continue
            for json_file in base_dir.rglob("*.json"):
                scanned += 1
                try:
                    raw = json.loads(json_file.read_text(encoding="utf-8"))

                    # Determine report_id and client_id from JSON or path
                    report_id = (
                        raw.get("report_id")
                        or raw.get("strategy", {}).get("report_id")
                        or json_file.stem
                    )
                    client_id = (
                        raw.get("client_id")
                        or raw.get("strategy", {}).get("client_id")
                        or json_file.parent.name  # parent folder = client_id
                    )

                    # The actual strategy payload
                    strategy = raw.get("strategy", raw)

                    if not report_id or not client_id:
                        continue

                    # Skip if already in DB
                    exists = (
                        db.query(GrowthReport.id)
                        .filter(GrowthReport.id == report_id)
                        .first()
                    )
                    if exists:
                        continue

                    # Import into PostgreSQL
                    goal = (
                        strategy.get("goal", "")
                        or raw.get("goal", "")
                        or "Imported from filesystem"
                    )
                    row = GrowthReport(
                        id=report_id,
                        client_id=client_id,
                        goal=goal,
                        report_json=json.dumps(strategy, default=str, ensure_ascii=False),
                        created_at=_parse_date(raw) or datetime.utcnow(),
                    )
                    db.add(row)
                    db.flush()
                    imported += 1
                    details.append(f"imported {report_id} from {json_file}")
                    log.info(f"[watchdog] Imported orphan report {report_id} from {json_file}")

                except Exception as exc:
                    errors += 1
                    details.append(f"error {json_file}: {exc}")
                    log.warning(f"[watchdog] Error importing {json_file}: {exc}")

        db.commit()
    except Exception as exc:
        db.rollback()
        log.error(f"[watchdog] recover_orphaned_reports failed: {exc}")
        errors += 1
        details.append(f"fatal: {exc}")
    finally:
        db.close()

    summary = {
        "scanned": scanned,
        "imported": imported,
        "errors": errors,
        "details": details,
    }
    log.info(f"[watchdog] Orphan recovery complete: {scanned} scanned, {imported} imported, {errors} errors")
    return summary


# ──────────────────────────────────────────────────────────────────────────────
# 2. Report integrity check
# ──────────────────────────────────────────────────────────────────────────────

def verify_report_integrity() -> dict:
    """Return a health-check dict with per-client report counts + notification cross-ref."""
    from database.db import SessionLocal
    from database.models import GrowthReport, ClientNotification

    db = SessionLocal()
    try:
        # Reports per client
        from sqlalchemy import func
        report_counts = (
            db.query(GrowthReport.client_id, func.count(GrowthReport.id))
            .group_by(GrowthReport.client_id)
            .all()
        )
        total_reports = sum(c for _, c in report_counts)

        # Notifications referencing reports — wrapped separately so a missing DB column
        # (e.g. cleared_at / read_at) doesn't swallow the report count above.
        report_notifs = 0
        orphan_notifs = 0
        try:
            report_notifs = (
                db.query(ClientNotification)
                .filter(
                    ClientNotification.notification_type.in_(["content_idea", "growth_tip"]),
                    ClientNotification.metadata_json.ilike('%report_id%'),
                )
                .count()
            )

            # Check for orphan notification report_ids (notification has report_id but report gone)
            notifs_with_report = (
                db.query(ClientNotification)
                .filter(ClientNotification.metadata_json.ilike('%report_id%'))
                .all()
            )
            known_ids = {r_id for r_id, in db.query(GrowthReport.id).all()}
            for n in notifs_with_report:
                try:
                    meta = json.loads(n.metadata_json) if n.metadata_json else {}
                    rid = meta.get("report_id", "")
                    if rid and rid not in known_ids:
                        orphan_notifs += 1
                except Exception:
                    pass
        except Exception as notif_exc:
            log.warning(
                f"[watchdog] Notification cross-ref skipped — likely a missing DB column "
                f"that will self-heal after migration on next startup. Error: {notif_exc}"
            )

        return {
            "total_reports_in_db": total_reports,
            "reports_per_client": {cid: cnt for cid, cnt in report_counts},
            "notifications_with_report_link": report_notifs,
            "orphan_notification_report_refs": orphan_notifs,
            "status": "healthy" if orphan_notifs == 0 else "has_orphan_refs",
        }
    except Exception as exc:
        log.error(f"[watchdog] verify_report_integrity failed: {exc}")
        return {"error": str(exc)}
    finally:
        db.close()


# ──────────────────────────────────────────────────────────────────────────────
# 3. Startup hook
# ──────────────────────────────────────────────────────────────────────────────

def startup_watchdog():
    """Call once at app boot (from web_app.py startup event).

    - Imports any filesystem-only reports into PostgreSQL
    - Recovers any emergency notification files into PostgreSQL
    - Logs report integrity status
    """
    log.info("[watchdog] === Integrity Watchdog Starting ===")

    recovery = recover_orphaned_reports()
    if recovery["imported"] > 0:
        log.warning(
            f"[watchdog] Recovered {recovery['imported']} orphaned reports into DB!"
        )

    notif_recovered = recover_orphaned_notifications()
    if notif_recovered > 0:
        log.warning(
            f"[watchdog] Recovered {notif_recovered} orphaned notifications into DB!"
        )

    health = verify_report_integrity()
    log.info(f"[watchdog] DB has {health.get('total_reports_in_db', '?')} reports — status: {health.get('status', '?')}")

    if health.get("orphan_notification_report_refs", 0) > 0:
        log.warning(
            f"[watchdog] {health['orphan_notification_report_refs']} notification(s) reference missing reports!"
        )

    log.info("[watchdog] === Integrity Watchdog Complete ===")
    return health


# ──────────────────────────────────────────────────────────────────────────────
# 4. Recover orphaned notification recovery files → PostgreSQL
# ──────────────────────────────────────────────────────────────────────────────

def recover_orphaned_notifications() -> int:
    """Import emergency notification recovery JSON files into PostgreSQL.

    When ``NotificationManager._send_dashboard_notification`` fails to write to
    the DB (cold-boot race, connection pool exhaustion, etc.) it drops a JSON
    file into ``storage/notification_recovery/``.  This function picks those
    files up and inserts them, then deletes the file.  Safe to call repeatedly.
    """
    recovery_dir = Path("storage") / "notification_recovery"
    if not recovery_dir.exists():
        return 0

    files = sorted(recovery_dir.glob("*.json"))
    if not files:
        return 0

    log.warning(f"[watchdog] Found {len(files)} orphan notification files to recover")

    try:
        from database.db import SessionLocal
        from database.models import ClientNotification
    except Exception as exc:
        log.error(f"[watchdog] Cannot import DB modules for notification recovery: {exc}")
        return 0

    db = SessionLocal()
    recovered = 0
    try:
        for fpath in files:
            try:
                data = json.loads(fpath.read_text(encoding="utf-8"))

                # Dedup — skip if a notification with same id already exists
                nid = data.get("id", "")
                if nid:
                    existing = (
                        db.query(ClientNotification.id)
                        .filter(ClientNotification.id == nid)
                        .first()
                    )
                    if existing:
                        log.info(f"[watchdog] Notification {nid} already in DB, removing file")
                        fpath.unlink(missing_ok=True)
                        continue

                row = ClientNotification(
                    id=nid or f"recovered_{fpath.stem}",
                    client_id=str(data["client_id"]),
                    notification_type=data.get("notification_type", "system"),
                    title=data.get("title", ""),
                    message=data.get("message", ""),
                    priority=data.get("priority", "medium"),
                    read=False,
                    metadata_json=json.dumps(data.get("metadata", {})),
                )

                # Restore original timestamp if present
                created = data.get("created_at")
                if created:
                    try:
                        row.created_at = datetime.fromisoformat(
                            str(created).replace("Z", "+00:00").replace("+00:00", "")
                        )
                    except (ValueError, TypeError):
                        pass

                db.add(row)
                db.commit()
                fpath.unlink(missing_ok=True)
                recovered += 1
                log.info(f"[watchdog] ✅ Recovered notification from {fpath.name}")

            except Exception as exc:
                db.rollback()
                log.error(f"[watchdog] Failed to recover {fpath.name}: {exc}")

    finally:
        db.close()

    log.info(f"[watchdog] Notification recovery complete: {recovered}/{len(files)}")
    return recovered


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def _parse_date(raw: dict) -> datetime | None:
    """Best-effort parse of a date from report JSON."""
    for key in ("created_at", "generated_at", "saved_at", "timestamp"):
        val = raw.get(key) or raw.get("strategy", {}).get(key)
        if val:
            try:
                return datetime.fromisoformat(str(val).replace("Z", "+00:00").replace("+00:00", ""))
            except Exception:
                pass
    return None
