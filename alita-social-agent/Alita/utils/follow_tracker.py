"""
utils/follow_tracker.py
=======================
Per-client deduplication tracker for the growth agent.

Prevents the growth agent from suggesting the same Instagram account,
Facebook group, competitor, or any other growth target more than once
per client — unless the client acts on the suggestion (then it can be
re-surfaced after a cooldown).

Storage
-------
JSON file: storage/follow_tracker/{client_id}_follow_tracker.json

Schema
------
{
    "suggested": {
        "instagram":       ["@fitnessbyjamila", "@coachwealthmindset"],
        "facebook_groups": ["Online Coaches & Consultants"],
        "twitter":         ["@coachpro"],
        "tiktok":          [],
        "competitor":      ["@fitcoachpro"]
    },
    "acted_on": {
        "instagram":       ["@fitnessbyjamila"]   // client clicked action button
    },
    "dismissed": {
        "instagram":       []                     // client explicitly dismissed (future)
    },
    "last_updated": "2025-01-15T10:30:00"
}

Usage
-----
    tracker = FollowTracker(client_id="26031243413178154")

    # Before suggesting an account:
    if not tracker.already_suggested("instagram", "@fitnessbyjamila"):
        tracker.mark_suggested("instagram", "@fitnessbyjamila")
        await notifier.send_growth_notification(...)

    # When client clicks action button (called from notification action-click endpoint):
    tracker.mark_acted_on("instagram", "@fitnessbyjamila")

    # Batch check — filter a list down to only unseen handles:
    new_handles = tracker.filter_unseen("instagram", ["@handle1", "@handle2", "@handle3"])
"""

import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

# Windows UTF-8 fix
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# Supported platform keys
VALID_PLATFORMS = {
    "instagram",
    "facebook_groups",
    "facebook",
    "twitter",
    "tiktok",
    "linkedin",
    "threads",
    "youtube",
    "competitor",
}

_STORAGE_DIR = Path("storage") / "follow_tracker"


class FollowTracker:
    """
    Tracks which growth targets (accounts, groups, competitors) have
    already been suggested, acted on, or dismissed for a given client.
    """

    def __init__(self, client_id: str):
        self.client_id = client_id
        _STORAGE_DIR.mkdir(parents=True, exist_ok=True)
        self._filepath = _STORAGE_DIR / f"{client_id}_follow_tracker.json"
        self._data: Dict = self._load()

    # ──────────────────────────────────────────────────────────────────
    # Public API
    # ──────────────────────────────────────────────────────────────────

    def already_suggested(self, platform: str, handle: str) -> bool:
        """Return True if this handle has already been suggested on this platform."""
        handle = _normalize(handle)
        return handle in self._bucket("suggested", platform)

    def mark_suggested(self, platform: str, handle: str) -> None:
        """Record that a suggestion was sent to the client."""
        self._add_to_bucket("suggested", platform, handle)

    def mark_acted_on(self, platform: str, handle: str) -> None:
        """Record that the client clicked the action button for this handle."""
        self._add_to_bucket("acted_on", platform, handle)

    def mark_dismissed(self, platform: str, handle: str) -> None:
        """Record that the client explicitly dismissed this suggestion."""
        self._add_to_bucket("dismissed", platform, handle)

    def filter_unseen(self, platform: str, handles: List[str]) -> List[str]:
        """
        Return only the handles from `handles` that have NOT been suggested yet.
        Useful when the growth agent produces a batch of candidates.
        """
        seen = set(self._bucket("suggested", platform))
        return [h for h in handles if _normalize(h) not in seen]

    def get_suggested(self, platform: Optional[str] = None) -> Dict[str, List[str]]:
        """
        Return all suggested handles.
        Pass `platform` to get only that platform's list.
        """
        if platform:
            return {platform: list(self._bucket("suggested", platform))}
        return {p: list(v) for p, v in self._data.get("suggested", {}).items()}

    def get_acted_on(self, platform: Optional[str] = None) -> Dict[str, List[str]]:
        """Return handles the client has acted on (clicked action button)."""
        if platform:
            return {platform: list(self._bucket("acted_on", platform))}
        return {p: list(v) for p, v in self._data.get("acted_on", {}).items()}

    def is_acted_on(self, platform: str, handle: str) -> bool:
        """Return True if client already clicked the action for this handle."""
        return _normalize(handle) in self._bucket("acted_on", platform)

    def clear_platform(self, platform: str) -> None:
        """
        Wipe all tracking data for a specific platform.
        Useful when starting a new growth cycle or for testing.
        """
        for bucket in ("suggested", "acted_on", "dismissed"):
            self._data.setdefault(bucket, {})[platform] = []
        self._save()

    def clear_all(self) -> None:
        """Wipe ALL tracking data for this client (use with caution)."""
        self._data = _empty_data()
        self._save()

    def summary(self) -> Dict:
        """Return a summary dict suitable for admin dashboards or logging."""
        result = {"client_id": self.client_id, "last_updated": self._data.get("last_updated")}
        for bucket in ("suggested", "acted_on", "dismissed"):
            total = sum(len(v) for v in self._data.get(bucket, {}).values())
            result[f"{bucket}_count"] = total
        return result

    # ──────────────────────────────────────────────────────────────────
    # Internal helpers
    # ──────────────────────────────────────────────────────────────────

    def _bucket(self, bucket_name: str, platform: str) -> List[str]:
        """Return the list for bucket+platform (read-only convenience)."""
        return self._data.setdefault(bucket_name, {}).setdefault(platform, [])

    def _add_to_bucket(self, bucket_name: str, platform: str, handle: str) -> None:
        handle = _normalize(handle)
        bucket = self._bucket(bucket_name, platform)
        if handle not in bucket:
            bucket.append(handle)
            self._data["last_updated"] = datetime.now().isoformat()
            self._save()

    def _load(self) -> Dict:
        if self._filepath.exists():
            try:
                with open(self._filepath, "r", encoding="utf-8") as f:
                    return json.load(f)
            except (json.JSONDecodeError, OSError):
                pass
        return _empty_data()

    def _save(self) -> None:
        with open(self._filepath, "w", encoding="utf-8") as f:
            json.dump(self._data, f, indent=2, ensure_ascii=False)


# ──────────────────────────────────────────────────────────────────────
# Module-level helpers
# ──────────────────────────────────────────────────────────────────────

def _normalize(handle: str) -> str:
    """Lowercase and strip whitespace for consistent comparisons."""
    return handle.strip().lower()


def _empty_data() -> Dict:
    return {
        "suggested":    {},
        "acted_on":     {},
        "dismissed":    {},
        "last_updated": None,
    }


# ──────────────────────────────────────────────────────────────────────
# Convenience factory — one per client, cached in memory during a request
# ──────────────────────────────────────────────────────────────────────

_cache: Dict[str, FollowTracker] = {}


def get_tracker(client_id: str) -> FollowTracker:
    """
    Return a cached FollowTracker for the given client_id.
    Creates a new one if it doesn't exist yet.

    Use this inside agent code to avoid creating multiple instances
    for the same client within a single run:

        from utils.follow_tracker import get_tracker

        tracker = get_tracker(client_id)
        if not tracker.already_suggested("instagram", "@fitnessbyjamila"):
            tracker.mark_suggested("instagram", "@fitnessbyjamila")
            await notifier.send_growth_notification(...)
    """
    if client_id not in _cache:
        _cache[client_id] = FollowTracker(client_id)
    return _cache[client_id]
