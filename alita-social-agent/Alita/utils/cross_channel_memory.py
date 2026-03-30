"""
utils/cross_channel_memory.py

Persistent cross-channel conversation memory.

Tracks a user's full conversation history across ALL channels (comments,
DMs, mentions) for a given client.  This lets the AI pick up context
seamlessly when someone starts in a comment thread and moves to DMs —
or vice-versa.

Key design choices
──────────────────
• Indexed by (client_id, sender_id)  — both are stable platform IDs.
• Each entry records the channel ("comment" | "dm" | "mention") so the
  agent knows the conversation context.
• Persisted to  storage/conversations/{client_id}/{sender_id}.json
  so history survives server restarts.
• TTL of 7 days (configurable) — long enough to cover comment→DM journeys
  that take several days.
• Thread-safe file I/O with a simple per-user write-lock.
"""

from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

# ── Storage root ─────────────────────────────────────────────────────────────
_STORAGE_ROOT = Path("storage") / "conversations"

# ── Per-file write locks (avoids concurrent write corruption) ─────────────────
_file_locks: Dict[str, threading.Lock] = {}
_locks_meta = threading.Lock()


def _get_lock(path: str) -> threading.Lock:
    with _locks_meta:
        if path not in _file_locks:
            _file_locks[path] = threading.Lock()
        return _file_locks[path]


# ── Data model ────────────────────────────────────────────────────────────────

class ChannelEvent:
    """A single turn in a cross-channel conversation."""

    VALID_CHANNELS = {"comment", "dm", "mention", "facebook_dm", "facebook_comment"}
    VALID_DIRECTIONS = {"incoming", "outgoing"}

    def __init__(
        self,
        channel: str,
        direction: str,
        text: str,
        timestamp: Optional[str] = None,
        post_id: Optional[str] = None,   # for comments — the IG media object
        message_id: Optional[str] = None,
    ):
        self.channel = channel if channel in self.VALID_CHANNELS else "dm"
        self.direction = direction if direction in self.VALID_DIRECTIONS else "incoming"
        self.text = text
        self.timestamp = timestamp or datetime.utcnow().isoformat()
        self.post_id = post_id
        self.message_id = message_id

    def to_dict(self) -> dict:
        d = {
            "channel": self.channel,
            "direction": self.direction,
            "text": self.text,
            "timestamp": self.timestamp,
        }
        if self.post_id:
            d["post_id"] = self.post_id
        if self.message_id:
            d["message_id"] = self.message_id
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "ChannelEvent":
        return cls(
            channel=data.get("channel", "dm"),
            direction=data.get("direction", "incoming"),
            text=data.get("text", ""),
            timestamp=data.get("timestamp"),
            post_id=data.get("post_id"),
            message_id=data.get("message_id"),
        )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<ChannelEvent {self.channel}/{self.direction} @{self.timestamp[:16]}>"


# ── Core class ────────────────────────────────────────────────────────────────

class CrossChannelMemory:
    """
    Persistent, cross-channel conversation memory.

    Usage
    ─────
        from utils.cross_channel_memory import cross_channel_memory

        # Record an incoming comment
        cross_channel_memory.add_event(
            client_id="acme",
            sender_id="12345678",
            channel="comment",
            direction="incoming",
            text="Do you ship internationally?",
            post_id="17846368219941196",
        )

        # Get unified context string ready to inject into a Claude prompt
        context = cross_channel_memory.get_context_for_prompt("acme", "12345678")
    """

    def __init__(self, ttl_days: int = 7, max_events: int = 40):
        self.ttl_days = ttl_days
        self.max_events = max_events

    # ── Internal file helpers ─────────────────────────────────────────────────

    def _path(self, client_id: str, sender_id: str) -> Path:
        # Sanitise to avoid directory traversal
        safe_client = "".join(c for c in client_id if c.isalnum() or c in "_-")
        safe_sender = "".join(c for c in sender_id if c.isalnum() or c in "_-")
        return _STORAGE_ROOT / safe_client / f"{safe_sender}.json"

    def _load(self, client_id: str, sender_id: str) -> dict:
        """Load user record from disk.  Returns empty scaffold on miss."""
        path = self._path(client_id, sender_id)
        if not path.exists():
            return {"events": [], "first_seen": datetime.utcnow().isoformat()}
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {"events": [], "first_seen": datetime.utcnow().isoformat()}

    def _save(self, client_id: str, sender_id: str, record: dict) -> None:
        """Persist user record to disk (with file lock)."""
        path = self._path(client_id, sender_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        lock = _get_lock(str(path))
        with lock:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(record, f, indent=2, ensure_ascii=False)

    # ── Public API ────────────────────────────────────────────────────────────

    def add_event(
        self,
        client_id: str,
        sender_id: str,
        channel: str,
        direction: str,
        text: str,
        post_id: Optional[str] = None,
        message_id: Optional[str] = None,
    ) -> None:
        """
        Record one turn of a conversation.

        Parameters
        ──────────
        client_id   : Your internal client slug (e.g. "acme")
        sender_id   : Platform user/participant ID (stable across channels)
        channel     : "comment" | "dm" | "mention" | "facebook_dm" | …
        direction   : "incoming" (user→bot) | "outgoing" (bot→user)
        text        : Message/comment body
        post_id     : IG media object ID (for comments only)
        message_id  : Platform message ID (for deduplication)
        """
        if not text or not text.strip():
            return

        record = self._load(client_id, sender_id)
        events: List[dict] = record.get("events", [])

        # Deduplicate by message_id
        if message_id and any(e.get("message_id") == message_id for e in events):
            return

        event = ChannelEvent(
            channel=channel,
            direction=direction,
            text=text.strip(),
            post_id=post_id,
            message_id=message_id,
        )
        events.append(event.to_dict())

        # Prune old events (TTL)
        cutoff = (datetime.utcnow() - timedelta(days=self.ttl_days)).isoformat()
        events = [e for e in events if e.get("timestamp", "") >= cutoff]

        # Cap total events
        if len(events) > self.max_events:
            events = events[-self.max_events:]

        record["events"] = events
        record["last_activity"] = datetime.utcnow().isoformat()
        self._save(client_id, sender_id, record)

    def get_events(
        self,
        client_id: str,
        sender_id: str,
        max_events: Optional[int] = None,
    ) -> List[ChannelEvent]:
        """Return recent events (most recent last).

        Expired events are automatically filtered out.
        """
        record = self._load(client_id, sender_id)
        cutoff = (datetime.utcnow() - timedelta(days=self.ttl_days)).isoformat()
        raw = [
            e for e in record.get("events", [])
            if e.get("timestamp", "") >= cutoff
        ]
        limit = max_events or self.max_events
        raw = raw[-limit:]
        return [ChannelEvent.from_dict(e) for e in raw]

    def get_context_for_prompt(
        self,
        client_id: str,
        sender_id: str,
        max_events: int = 12,
    ) -> str:
        """
        Return a formatted string suitable for injection into a Claude system
        prompt.  Includes channel labels so the model can reason about the
        conversation journey.

        Example output
        ──────────────
        CROSS-CHANNEL CONVERSATION HISTORY (last 12 interactions):
        [comment • incoming • 2026-02-19 14:02] USER: Do you ship internationally?
        [comment • outgoing • 2026-02-19 14:02] BOT: Yes! We ship worldwide …
        [dm • incoming • 2026-02-20 09:18] USER: Hey, following up on the shipping question
        [dm • outgoing • 2026-02-20 09:18] BOT: Of course! …

        Returns empty string if no history exists.
        """
        events = self.get_events(client_id, sender_id, max_events=max_events)
        if not events:
            return ""

        # Check if multiple channels are present
        channels_seen = {e.channel for e in events}
        multi_channel = len(channels_seen) > 1

        lines = []
        header_note = " (moved across channels)" if multi_channel else ""
        lines.append(
            f"CROSS-CHANNEL CONVERSATION HISTORY{header_note} — last {len(events)} interactions:"
        )

        for ev in events:
            ts = ev.timestamp[:16].replace("T", " ")
            speaker = "USER" if ev.direction == "incoming" else "BOT"
            post_note = f" [post:{ev.post_id[:8]}…]" if ev.post_id else ""
            channel_label = ev.channel.upper().replace("_", " ")
            lines.append(f"[{channel_label}{post_note} • {ts}] {speaker}: {ev.text}")

        return "\n".join(lines)

    def get_channel_journey(self, client_id: str, sender_id: str) -> dict:
        """
        Summary of which channels this user has interacted through.
        Useful for admin panels / dashboards.
        """
        events = self.get_events(client_id, sender_id)
        if not events:
            return {"channels": [], "total_interactions": 0, "first_seen": None, "last_seen": None}

        channels = sorted({e.channel for e in events})
        return {
            "channels": channels,
            "total_interactions": len(events),
            "first_seen": events[0].timestamp[:16],
            "last_seen": events[-1].timestamp[:16],
            "channel_counts": {
                ch: sum(1 for e in events if e.channel == ch) for ch in channels
            },
        }

    def delete_user(self, client_id: str, sender_id: str) -> bool:
        """Hard-delete all data for a user (GDPR right-to-erasure)."""
        path = self._path(client_id, sender_id)
        if path.exists():
            path.unlink()
            return True
        return False


# ── Module-level singleton ────────────────────────────────────────────────────
cross_channel_memory = CrossChannelMemory(ttl_days=7, max_events=40)
