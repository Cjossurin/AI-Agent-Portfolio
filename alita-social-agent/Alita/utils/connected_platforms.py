"""
utils/connected_platforms.py
----------------------------
Single source of truth for which social platforms a client currently has
connected (authenticated).

Usage:
    from utils.connected_platforms import get_connected_platforms

    platforms = get_connected_platforms("acme_corp")
    # → ["facebook", "instagram", "linkedin", "twitter"]
"""

from __future__ import annotations

import json
import os
from typing import List, Optional

# Path to the Late-API flat-file connection store
CONNECTIONS_FILE = os.path.join("storage", "client_connections.json")


def get_connected_platforms(
    client_id: str,
    db=None,  # optional SQLAlchemy Session – avoids opening a new one if caller already has one
) -> List[str]:
    """
    Return a sorted list of platform name strings that ``client_id`` has
    successfully connected (OAuth-authorised).

    Sources checked (in order, results merged):
    1. ``ClientProfile`` DB row  →  ``meta_ig_account_id``  →  "instagram"
                                    ``meta_facebook_page_id`` →  "facebook"
    2. ``storage/client_connections.json``  →  all non-Meta platforms
       (Twitter, TikTok, LinkedIn, Threads, YouTube, etc.)

    Args:
        client_id:  The Alita client identifier (matches ``ClientProfile.client_id``).
        db:         Optional open SQLAlchemy session.  If *None* a short-lived
                    session is opened internally and closed before returning.

    Returns:
        Sorted, deduplicated list of lowercase platform strings, e.g.
        ``["facebook", "instagram", "linkedin", "twitter"]``.
        Returns an empty list if nothing is connected or an error occurs.
    """
    platforms: set[str] = set()

    # ── 1. Meta platforms from the PostgreSQL database ────────────────────────
    _close_db = False
    try:
        if db is None:
            try:
                from database.db import SessionLocal
                db = SessionLocal()
                _close_db = True
            except Exception:
                db = None

        if db is not None:
            try:
                from database.models import ClientProfile
                profile = (
                    db.query(ClientProfile)
                    .filter(ClientProfile.client_id == client_id)
                    .first()
                )
                if profile:
                    if getattr(profile, "meta_ig_account_id", None):
                        platforms.add("instagram")
                    if getattr(profile, "meta_facebook_page_id", None):
                        platforms.add("facebook")
            except Exception as exc:
                print(f"⚠️  connected_platforms: DB lookup failed for {client_id}: {exc}")
    finally:
        if _close_db and db is not None:
            try:
                db.close()
            except Exception:
                pass

    # ── 2. Late-API platforms from DB (PlatformConnection table) ────────────
    _close_db2 = False
    try:
        _db2 = db
        if _db2 is None:
            try:
                from database.db import SessionLocal
                _db2 = SessionLocal()
                _close_db2 = True
            except Exception:
                _db2 = None

        if _db2 is not None:
            try:
                from database.models import PlatformConnection
                rows = (
                    _db2.query(PlatformConnection)
                    .filter(PlatformConnection.client_id == client_id)
                    .all()
                )
                for row in rows:
                    platforms.add(row.platform.lower())
            except Exception:
                pass  # table may not exist yet on first boot
        if _close_db2 and _db2 is not None:
            try:
                _db2.close()
            except Exception:
                pass
    except Exception:
        pass

    # ── 3. Late-API platforms from client_connections.json (fallback) ─────────
    try:
        if os.path.exists(CONNECTIONS_FILE):
            with open(CONNECTIONS_FILE, "r") as fh:
                all_connections: dict = json.load(fh)
            client_connections = all_connections.get(client_id, {})
            for platform_key in client_connections.keys():
                platforms.add(platform_key.lower())
    except Exception as exc:
        print(f"  connected_platforms: JSON lookup failed for {client_id}: {exc}")

    # ── 4. Env-var fallback (LATE_PROFILE_{PLATFORM}_{client_id}) ────────────
    # These survive Railway redeploys because they are set as service variables.
    _LATE_PLATFORMS = ["twitter", "tiktok", "linkedin", "threads", "youtube"]
    for _p in _LATE_PLATFORMS:
        if os.getenv(f"LATE_PROFILE_{_p.upper()}_{client_id}"):
            platforms.add(_p)

    return sorted(platforms)


def get_connected_platforms_with_details(
    client_id: str,
    db=None,
) -> dict:
    """
    Extended version that also returns account identifiers.

    Returns a dict keyed by platform name:
        {
          "instagram": {"account_id": "...", "username": "..."},
          "twitter":   {"account_id": "...", "username": "..."},
          ...
        }
    """
    result: dict = {}

    # ── DB (Meta) ─────────────────────────────────────────────────────────────
    _close_db = False
    try:
        if db is None:
            try:
                from database.db import SessionLocal
                db = SessionLocal()
                _close_db = True
            except Exception:
                db = None

        if db is not None:
            try:
                from database.models import ClientProfile
                profile = (
                    db.query(ClientProfile)
                    .filter(ClientProfile.client_id == client_id)
                    .first()
                )
                if profile:
                    ig_id = getattr(profile, "meta_ig_account_id", None)
                    ig_user = getattr(profile, "meta_ig_username", None)
                    fb_id = getattr(profile, "meta_facebook_page_id", None)
                    if ig_id:
                        result["instagram"] = {"account_id": ig_id, "username": ig_user or ""}
                    if fb_id:
                        result["facebook"] = {"account_id": fb_id, "username": ""}
            except Exception as exc:
                print(f"⚠️  connected_platforms_details: DB lookup failed for {client_id}: {exc}")
    finally:
        if _close_db and db is not None:
            try:
                db.close()
            except Exception:
                pass

    # ── DB (Late-API — PlatformConnection table) ────────────────────────────
    _close_db2 = False
    try:
        _db2 = db
        if _db2 is None:
            try:
                from database.db import SessionLocal
                _db2 = SessionLocal()
                _close_db2 = True
            except Exception:
                _db2 = None
        if _db2 is not None:
            try:
                from database.models import PlatformConnection
                rows = (
                    _db2.query(PlatformConnection)
                    .filter(PlatformConnection.client_id == client_id)
                    .all()
                )
                for row in rows:
                    p = row.platform.lower()
                    if p not in result:
                        result[p] = {
                            "account_id": row.account_id or "",
                            "username": row.username or "",
                        }
            except Exception:
                pass
        if _close_db2 and _db2 is not None:
            try:
                _db2.close()
            except Exception:
                pass
    except Exception:
        pass

    # ── JSON (Late-API — fallback) ────────────────────────────────────────────
    try:
        if os.path.exists(CONNECTIONS_FILE):
            with open(CONNECTIONS_FILE, "r") as fh:
                all_connections: dict = json.load(fh)
            for platform_key, details in all_connections.get(client_id, {}).items():
                p = platform_key.lower()
                if p not in result:  # don't overwrite Meta entries
                    result[p] = {
                        "account_id": details.get("profile_id", ""),
                        "username": details.get("username", ""),
                    }
    except Exception as exc:
        print(f"⚠️  connected_platforms_details: JSON lookup failed for {client_id}: {exc}")

    # ── Env-var fallback (LATE_PROFILE_{PLATFORM}_{client_id}) ────────────────
    _LATE_PLATFORMS = ["twitter", "tiktok", "linkedin", "threads", "youtube"]
    for _p in _LATE_PLATFORMS:
        env_val = os.getenv(f"LATE_PROFILE_{_p.upper()}_{client_id}")
        if env_val and _p not in result:
            result[_p] = {"account_id": env_val, "username": ""}

    return result
