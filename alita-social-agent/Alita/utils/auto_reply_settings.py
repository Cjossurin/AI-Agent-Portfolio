import json
import os
from dataclasses import dataclass
from threading import RLock
from typing import Dict, Literal

AutoReplyKind = Literal["dm", "comment"]


_STORAGE_PATH = os.path.join("storage", "auto_reply_settings.json")
_LOCK = RLock()


def _default_platforms() -> Dict[str, bool]:
    return {
        "twitter": False,
        "instagram": False,
        "facebook": False,
        "linkedin": False,
        "threads": False,
        "tiktok": False,
        "youtube": False,
        "reddit": False,
        "telegram": False,
    }


def _default_state() -> Dict[str, Dict[str, bool]]:
    return {
        "dm": _default_platforms(),
        "comment": _default_platforms(),
    }


def _ensure_dir_exists() -> None:
    os.makedirs(os.path.dirname(_STORAGE_PATH), exist_ok=True)


def _load_state_unlocked() -> Dict[str, Dict[str, bool]]:
    if not os.path.exists(_STORAGE_PATH):
        return _default_state()

    try:
        with open(_STORAGE_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return _default_state()

    state = _default_state()
    for kind in ("dm", "comment"):
        if isinstance(data.get(kind), dict):
            for platform, enabled in data[kind].items():
                if platform in state[kind]:
                    state[kind][platform] = bool(enabled)
    return state


def _save_state_unlocked(state: Dict[str, Dict[str, bool]]) -> None:
    _ensure_dir_exists()
    tmp_path = _STORAGE_PATH + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, sort_keys=True)
    os.replace(tmp_path, _STORAGE_PATH)


def get_all(kind: AutoReplyKind) -> Dict[str, bool]:
    with _LOCK:
        state = _load_state_unlocked()
        return dict(state.get(kind, _default_platforms()))


def is_enabled(kind: AutoReplyKind, platform: str) -> bool:
    platform_key = (platform or "").lower()
    with _LOCK:
        state = _load_state_unlocked()
        return bool(state.get(kind, {}).get(platform_key, False))


def set_enabled(kind: AutoReplyKind, platform: str, enabled: bool) -> None:
    platform_key = (platform or "").lower()
    with _LOCK:
        state = _load_state_unlocked()
        if kind not in state:
            state[kind] = _default_platforms()
        if platform_key not in state[kind]:
            # Ignore unknown platforms to avoid storing junk keys
            return
        state[kind][platform_key] = bool(enabled)
        _save_state_unlocked(state)
