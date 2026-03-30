# utils/guardrails.py
"""
Super-Duty Guardrails for Alita Chat
=====================================
Loads guardrails_config.json and enforces every rule:
  * message length / word-count limits
  * banned patterns  (regex - e.g. "count to 1 million")
  * profanity filter  (word-boundary exact match)
  * gibberish detection
  * spam indicators
  * repetition / consecutive-repeat checks
  * special-char ratio
  * jailbreak / prompt-injection detection
  * per-user sliding-window rate limiting (in-memory)

Always returns lightweight, static strings - NEVER calls an LLM to
generate a blocked response (that would itself burn tokens).
"""

from __future__ import annotations

import json, os, re, time, logging
from collections import defaultdict
from typing import Tuple, Dict, Any, Optional
from datetime import datetime

# --- Load config -----------------------------------------------------------

CONFIG_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "guardrails_config.json")
BLOCKED_LOG_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "blocked_requests.txt")

_config_cache: Optional[Dict[str, Any]] = None
_config_load_time: Optional[float] = None
CONFIG_CACHE_SECONDS = 60


def load_config(force_reload: bool = False) -> Dict[str, Any]:
    global _config_cache, _config_load_time
    current_time = datetime.now().timestamp()
    if not force_reload and _config_cache is not None and _config_load_time is not None:
        if current_time - _config_load_time < CONFIG_CACHE_SECONDS:
            return _config_cache
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            _config_cache = json.load(f)
            _config_load_time = current_time
            return _config_cache
    except (FileNotFoundError, json.JSONDecodeError):
        return _get_default_config()


def _get_default_config() -> Dict[str, Any]:
    return {
        "max_message_length": 2000,
        "max_word_count": 500,
        "min_message_length": 1,
        "max_repetition_ratio": 0.5,
        "max_consecutive_repeats": 3,
        "min_dictionary_word_ratio": 0.3,
        "max_special_char_ratio": 0.5,
        "blocked_response": "I can't process that request. Please send a clear, appropriate message and I'll be happy to help!",
        "log_blocked_requests": True,
        "banned_patterns": [],
        "profanity_list": [],
        "gibberish_patterns": [],
        "spam_indicators": [],
    }


# Pre-compile patterns from config on first load
_compiled: dict = {}


def _ensure_compiled():
    if _compiled:
        return
    cfg = load_config()
    _compiled["banned"] = []
    for pat in cfg.get("banned_patterns", []):
        try:
            _compiled["banned"].append(re.compile(pat, re.IGNORECASE))
        except re.error:
            pass
    prof_set = {w.lower() for w in cfg.get("profanity_list", [])}
    if prof_set:
        alts = "|".join(re.escape(w) for w in sorted(prof_set, key=len, reverse=True))
        _compiled["profanity_re"] = re.compile(rf"\b({alts})\b", re.IGNORECASE)
    else:
        _compiled["profanity_re"] = None
    _compiled["gibberish"] = []
    for pat in cfg.get("gibberish_patterns", []):
        try:
            _compiled["gibberish"].append(re.compile(pat, re.IGNORECASE))
        except re.error:
            pass
    _compiled["spam"] = [s.lower() for s in cfg.get("spam_indicators", [])]
    _compiled["ready"] = True


# --- Static response strings ------------------------------------------------

_BLOCKED_RESP = "I can't process that request. Please send a clear, appropriate message and I'll be happy to help!"
_PROFANITY_RESP = "Please keep the conversation respectful. I'm here to help with your marketing needs!"
_JAILBREAK_RESP = "I'm not able to process that kind of request. How can I help you with your marketing today?"
_RATE_LIMIT_MINUTE_RESP = "You're sending messages too quickly. Please wait a moment before trying again."
_RATE_LIMIT_HOUR_RESP = "You've reached the hourly message limit. Please try again shortly."

log = logging.getLogger("guardrails")

# --- Jailbreak / Prompt-Injection Patterns ----------------------------------

_JAILBREAK_PATTERNS = [
    r"ignore\s+(all\s+)?(your\s+)?(previous|prior|above)?\s*(instructions|rules|guidelines|prompts?)",
    r"ignore\s+(all\s+)?(previous|prior|above|your)\s+(instructions|rules|guidelines|prompts?)",
    r"ignore\s+everything\s+(above|before|i\s+said)",
    r"disregard\s+(all\s+)?(your\s+)?(previous|prior)?\s*(instructions|rules|guidelines)",
    r"forget\s+(all\s+)?(your\s+)?(previous|prior)?\s*(instructions|rules)",
    r"you\s+are\s+now\s+(a|an|the|my)\b",
    r"pretend\s+(you\s+are|to\s+be|you're)\b",
    r"act\s+as\s+(if|though|a|an)\b",
    r"from\s+now\s+on\s+you\s+(are|will|must)\b",
    r"(show|reveal|print|output|display|tell\s+me)\s+(the|your)\s+system\s+prompt",
    r"what\s+(is|are)\s+your\s+(system\s+)?prompt",
    r"\bDAN\b",
    r"\bjailbreak\b",
    r"bypass\s+(your|the|my)\s+(rules|restrictions|limits|guardrails|filters|safety)",
    r"override\s+(your|the|my)\s+(rules|instructions|restrictions|safety)",
    r"new\s+rule\s*:",
    r"developer\s+mode",
    r"sudo\s+mode",
    r"admin\s+mode",
    r"god\s+mode",
    r"(enter|enable|activate)\s+(unrestricted|unfiltered|uncensored)\s+mode",
    r"respond\s+without\s+(any\s+)?(restrictions|filters|limits|censorship)",
    r"do\s+not\s+(follow|obey|use)\s+(your|the)\s+(rules|guidelines|instructions)",
    r"(give|write|provide)\s+me\s+(the|your)\s+(initial|original|full)\s+(prompt|instructions)",
]
_JAILBREAK_RES = [re.compile(p, re.IGNORECASE) for p in _JAILBREAK_PATTERNS]


# --- Per-user rate limiting (in-memory sliding window) ----------------------

_RATE_STORE: dict = defaultdict(list)
_RATE_PER_MINUTE = 20
_RATE_PER_HOUR = 120


def check_rate_limit(user_id: str) -> Tuple[bool, str]:
    now = time.time()
    timestamps = _RATE_STORE[user_id]
    cutoff_hour = now - 3600
    _RATE_STORE[user_id] = [t for t in timestamps if t > cutoff_hour]
    timestamps = _RATE_STORE[user_id]
    cutoff_min = now - 60
    recent_minute = sum(1 for t in timestamps if t > cutoff_min)
    if recent_minute >= _RATE_PER_MINUTE:
        log.warning("Rate limit (per-minute) hit for user %s", user_id)
        return False, _RATE_LIMIT_MINUTE_RESP
    if len(timestamps) >= _RATE_PER_HOUR:
        log.warning("Rate limit (per-hour) hit for user %s", user_id)
        return False, _RATE_LIMIT_HOUR_RESP
    timestamps.append(now)
    return True, ""


# --- Jailbreak detector ----------------------------------------------------

def detect_jailbreak(message: str) -> bool:
    for rx in _JAILBREAK_RES:
        if rx.search(message):
            log.warning("Jailbreak pattern detected: %s", rx.pattern[:60])
            return True
    return False


# --- Logging helper ---------------------------------------------------------

def _log_blocked(message: str, reason: str, sender_id: str = "unknown"):
    cfg = load_config()
    if not cfg.get("log_blocked_requests", True):
        return
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        with open(BLOCKED_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(f"\n{'='*60}\n")
            f.write(f"BLOCKED REQUEST\n")
            f.write(f"Time: {ts}\n")
            f.write(f"Sender: {sender_id}\n")
            f.write(f"Reason: {reason}\n")
            f.write(f"Message: {message[:500]}{'...' if len(message) > 500 else ''}\n")
            f.write(f"{'='*60}\n")
    except Exception:
        pass


# --- Lightweight English word set for dictionary-ratio check ----------------

_ENGLISH_WORDS = None


def _load_english_words():
    global _ENGLISH_WORDS
    if _ENGLISH_WORDS is not None:
        return _ENGLISH_WORDS
    try:
        from nltk.corpus import words as nltk_words
        _ENGLISH_WORDS = {w.lower() for w in nltk_words.words()}
        return _ENGLISH_WORDS
    except Exception:
        pass
    _ENGLISH_WORDS = {
        "the", "be", "to", "of", "and", "a", "in", "that", "have", "i",
        "it", "for", "not", "on", "with", "he", "as", "you", "do", "at",
        "this", "but", "his", "by", "from", "they", "we", "say", "her",
        "she", "or", "an", "will", "my", "one", "all", "would", "there",
        "their", "what", "so", "up", "out", "if", "about", "who", "get",
        "which", "go", "me", "when", "make", "can", "like", "time", "no",
        "just", "him", "know", "take", "people", "into", "year", "your",
        "good", "some", "could", "them", "see", "other", "than", "then",
        "now", "look", "only", "come", "its", "over", "think", "also",
        "back", "after", "use", "two", "how", "our", "work", "first",
        "well", "way", "even", "new", "want", "because", "any", "these",
        "give", "day", "most", "us", "is", "was", "are", "been", "has",
        "had", "did", "said", "each", "tell", "does", "set", "three",
        "home", "read", "hand", "large", "add", "here", "must", "big",
        "high", "such", "follow", "act", "why", "ask", "men", "change",
        "light", "kind", "off", "need", "house", "try", "again", "point",
        "world", "near", "build", "self", "own", "should", "found",
        "answer", "grow", "study", "still", "learn", "food", "between",
        "keep", "never", "last", "let", "thought", "city", "start",
        "might", "far", "run", "while", "close", "night", "real",
        "life", "few", "open", "seem", "together", "next", "white",
        "children", "begin", "got", "walk", "example", "paper", "group",
        "always", "those", "both", "often", "until", "car", "care",
        "second", "book", "room", "friend", "idea", "stop", "once",
        "sure", "watch", "face", "main", "enough", "girl", "young",
        "ready", "above", "ever", "feel", "talk", "soon", "body",
        "dog", "family", "leave", "song", "door", "product", "short",
        "class", "question", "happen", "complete", "ship", "area",
        "half", "rock", "order", "fire", "south", "problem", "piece",
        "told", "knew", "pass", "since", "top", "whole", "space",
        "heard", "best", "hour", "better", "true", "during", "hundred",
        "five", "remember", "step", "early", "hold", "ground", "interest",
        "fast", "listen", "table", "travel", "less", "morning", "simple",
        "several", "toward", "against", "slow", "center", "love",
        "person", "money", "serve", "appear", "road", "map", "rain",
        "rule", "pull", "cold", "notice", "voice", "power", "town",
        "fine", "certain", "fly", "fall", "lead", "cry", "dark",
        "machine", "note", "wait", "plan", "figure", "star", "box",
        "field", "rest", "able", "done", "drive", "stood", "front",
        "teach", "week", "final", "gave", "green", "quick", "develop",
        "warm", "free", "minute", "strong", "special", "mind", "behind",
        "clear", "produce", "fact", "street", "lot", "nothing", "stay",
        "full", "force", "blue", "object", "decide", "surface", "deep",
        "moon", "island", "foot", "ten", "six",
        "post", "content", "image", "social", "media", "instagram",
        "facebook", "twitter", "tiktok", "linkedin", "youtube", "threads",
        "schedule", "calendar", "analytics", "growth", "strategy",
        "campaign", "audience", "engagement", "marketing", "brand",
        "create", "generate", "write", "caption", "hashtag", "platform",
        "business", "client", "dashboard", "settings", "billing",
        "notification", "email", "connect", "account", "tone", "style",
        "humor", "casual", "professional", "knowledge", "video",
        "subscribe", "followers", "likes", "comments", "shares",
        "impressions", "reach", "conversion", "funnel", "leads",
        "website", "blog", "newsletter", "design", "template", "help",
        "please", "thanks", "thank", "hello", "hi", "hey", "alita",
        "okay", "ok", "yes", "no", "sure", "maybe", "great", "cool",
        "awesome", "nice", "amazing", "perfect",
    }
    return _ENGLISH_WORDS


# --- Core check functions ---------------------------------------------------

def check_length(message: str, config: Dict[str, Any]) -> Tuple[bool, str]:
    if len(message) < config.get("min_message_length", 1):
        return False, "Message too short"
    if len(message) > config.get("max_message_length", 2000):
        return False, f"Message too long (max {config['max_message_length']} characters)."
    if len(message.split()) > config.get("max_word_count", 500):
        return False, f"Message too long (max {config['max_word_count']} words)."
    return True, ""


def check_repetition(message: str, config: Dict[str, Any]) -> Tuple[bool, str]:
    words = message.lower().split()
    if not words:
        return True, ""
    max_consec = config.get("max_consecutive_repeats", 3)
    run = 1
    for i in range(1, len(words)):
        if words[i] == words[i - 1]:
            run += 1
            if run > max_consec:
                return False, "Excessive consecutive repetition"
        else:
            run = 1
    if len(words) > 5:
        unique = set(words)
        ratio = 1 - (len(unique) / len(words))
        if ratio > config.get("max_repetition_ratio", 0.5):
            return False, "High repetition ratio"
    if re.search(r"(.)\1{10,}", message):
        return False, "Excessive character repetition"
    return True, ""


def check_profanity(message: str, _config: Dict[str, Any]) -> Tuple[bool, str]:
    _ensure_compiled()
    rx = _compiled.get("profanity_re")
    if rx and rx.search(message):
        return False, "Profanity detected"
    return True, ""


def check_gibberish(message: str, config: Dict[str, Any]) -> Tuple[bool, str]:
    _ensure_compiled()
    for rx in _compiled.get("gibberish", []):
        if rx.search(message.strip()):
            return False, "Gibberish pattern detected"
    if len(message) > 10:
        special = sum(1 for c in message if not c.isalnum() and not c.isspace())
        if special / len(message) > config.get("max_special_char_ratio", 0.5):
            return False, "Too many special characters"
    alpha_words = re.findall(r"[a-zA-Z]+", message.lower())
    if len(alpha_words) >= 6:
        eng = _load_english_words()
        known = sum(1 for w in alpha_words if w in eng)
        if known / len(alpha_words) < config.get("min_dictionary_word_ratio", 0.3):
            return False, "Message appears to be gibberish"
    return True, ""


def check_banned_patterns(message: str, _config: Dict[str, Any]) -> Tuple[bool, str]:
    _ensure_compiled()
    for rx in _compiled.get("banned", []):
        if rx.search(message):
            return False, "Banned pattern detected"
    return True, ""


def check_spam(message: str, _config: Dict[str, Any]) -> Tuple[bool, str]:
    _ensure_compiled()
    phrases = _compiled.get("spam", [])
    lower = message.lower()
    hits = sum(1 for p in phrases if p in lower)
    if hits >= 2:
        return False, "Spam detected"
    return True, ""


# --- Main validation (backwards-compatible 3-tuple for engagement_agent) -----

def validate_message(message: str, sender_id: str = "unknown") -> Tuple[bool, str, str]:
    """
    Run every guardrail check on *message*.
    Returns (is_valid, reason, blocked_response).
    When is_valid is False, blocked_response is a safe static string
    (NO LLM call - that would itself burn tokens).
    """
    cfg = load_config()
    if not message or not message.strip():
        return False, "Empty message", _BLOCKED_RESP
    checks = [
        ("length", check_length),
        ("repetition", check_repetition),
        ("profanity", check_profanity),
        ("gibberish", check_gibberish),
        ("banned_patterns", check_banned_patterns),
        ("spam", check_spam),
    ]
    for name, fn in checks:
        ok, reason = fn(message, cfg)
        if not ok:
            full = f"{name}: {reason}"
            print(f"Guardrail triggered - {full}")
            _log_blocked(message, full, sender_id)
            if name == "profanity":
                return False, full, _PROFANITY_RESP
            return False, full, _BLOCKED_RESP
    if detect_jailbreak(message):
        full = "jailbreak: Prompt injection attempt"
        print(f"Guardrail triggered - {full}")
        _log_blocked(message, full, sender_id)
        return False, full, _JAILBREAK_RESP
    return True, "", ""


# --- Lightweight 2-tuple API for Alita route --------------------------------

def validate_message_quick(message: str) -> Tuple[bool, str]:
    """Same checks as validate_message but returns (ok, user_facing_reason)."""
    ok, _reason, blocked = validate_message(message)
    if not ok:
        return False, blocked
    return True, ""


# --- Error sanitization -----------------------------------------------------

def sanitize_error(exc: Exception) -> str:
    """Return a safe generic message - never leak exception internals to users."""
    return "Sorry, something went wrong. Please try again."


# --- Helpers kept for backwards compat / COPILOT_INSTRUCTIONS references -----

def reload_config():
    return load_config(force_reload=True)


def test_guardrails(message: str) -> Dict[str, Any]:
    cfg = load_config()
    results: Dict[str, Any] = {
        "message": message[:100] + ("..." if len(message) > 100 else ""),
        "checks": {},
    }
    checks = [
        ("length", check_length),
        ("repetition", check_repetition),
        ("profanity", check_profanity),
        ("gibberish", check_gibberish),
        ("banned_patterns", check_banned_patterns),
        ("spam", check_spam),
    ]
    for name, fn in checks:
        ok, reason = fn(message, cfg)
        results["checks"][name] = {"passed": ok, "reason": reason if not ok else "OK"}
    results["jailbreak"] = detect_jailbreak(message)
    results["overall_valid"] = all(c["passed"] for c in results["checks"].values()) and not results["jailbreak"]
    return results
