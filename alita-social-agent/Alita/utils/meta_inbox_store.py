import json
import os
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


_STORAGE_DIR = Path("storage")
_STORAGE_DIR.mkdir(exist_ok=True)
_STORE_PATH = _STORAGE_DIR / "meta_inbox_store.json"

_LOCK = threading.Lock()


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_store() -> Dict[str, Any]:
    if not _STORE_PATH.exists():
        return {"conversations": {}, "last_event": {}}
    try:
        with open(_STORE_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return {"conversations": {}, "last_event": {}}
        data.setdefault("conversations", {})
        data.setdefault("last_event", {})
        return data
    except Exception:
        return {"conversations": {}, "last_event": {}}


def _write_store(data: Dict[str, Any]) -> None:
    tmp = str(_STORE_PATH) + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    os.replace(tmp, _STORE_PATH)


def _conv_key(platform: str, participant_id: str) -> str:
    return f"{(platform or '').strip().lower()}:{(participant_id or '').strip()}"


def record_message(
    *,
    platform: str,
    business_account_id: str,
    participant_id: str,
    direction: str,
    text: str,
    message_id: Optional[str] = None,
    timestamp_iso: Optional[str] = None,
) -> None:
    """Persist a DM event for Meta-backed inbox UI."""
    platform = (platform or "").strip().lower()
    if platform not in {"instagram", "facebook"}:
        return

    ts = timestamp_iso or _utc_now_iso()
    msg = {
        "id": message_id or f"{platform}:{participant_id}:{ts}",
        "direction": direction,
        "message": text or "",
        "createdAt": ts,
    }

    with _LOCK:
        store = _read_store()
        conversations: Dict[str, Any] = store.setdefault("conversations", {})
        key = _conv_key(platform, participant_id)

        conv = conversations.get(key) or {
            "id": key,
            "platform": platform,
            "accountId": str(business_account_id or ""),
            "participantId": str(participant_id or ""),
            "participantName": str(participant_id or ""),
            "updatedTime": ts,
            "lastMessage": text or "",
            "unreadCount": 0,
            "messages": [],
        }

        conv["accountId"] = str(business_account_id or conv.get("accountId") or "")
        conv["updatedTime"] = ts
        conv["lastMessage"] = text or conv.get("lastMessage") or ""

        # Count unread for incoming only
        if direction == "incoming":
            conv["unreadCount"] = int(conv.get("unreadCount") or 0) + 1

        messages: List[Dict[str, Any]] = conv.get("messages") or []
        messages.append(msg)
        # Bound message history per conversation
        conv["messages"] = messages[-200:]

        conversations[key] = conv
        store["conversations"] = conversations
        store.setdefault("last_event", {})[platform] = ts
        _write_store(store)


def list_conversations(platform: Optional[str] = None, limit: int = 50) -> List[Dict[str, Any]]:
    platform = (platform or "").strip().lower()
    with _LOCK:
        store = _read_store()
        convs = list((store.get("conversations") or {}).values())

    if platform in {"instagram", "facebook"}:
        convs = [c for c in convs if (c.get("platform") or "").lower() == platform]

    convs.sort(key=lambda c: c.get("updatedTime") or "", reverse=True)
    return convs[: max(1, min(200, int(limit or 50)))]


def get_messages(conversation_id: str) -> List[Dict[str, Any]]:
    with _LOCK:
        store = _read_store()
        conv = (store.get("conversations") or {}).get(conversation_id)
        if not conv:
            return []
        return list(conv.get("messages") or [])


def mark_read(conversation_id: str) -> None:
    with _LOCK:
        store = _read_store()
        convs = store.get("conversations") or {}
        conv = convs.get(conversation_id)
        if not conv:
            return
        conv["unreadCount"] = 0
        convs[conversation_id] = conv
        store["conversations"] = convs
        _write_store(store)


def get_status() -> Dict[str, Any]:
    with _LOCK:
        store = _read_store()
        last_event = store.get("last_event") or {}
        conversations = store.get("conversations") or {}

    counts = {"instagram": 0, "facebook": 0}
    for c in conversations.values():
        p = (c.get("platform") or "").lower()
        if p in counts:
            counts[p] += 1

    return {
        "last_event": last_event,
        "conversation_counts": counts,
        "store_path": str(_STORE_PATH),
    }
