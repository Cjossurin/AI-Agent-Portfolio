# agents/alita_assistant.py
"""
Alita AI Assistant — Client-facing chat agent.

Loads knowledge from Agent RAGs/Alita Assistant RAG/ and uses Claude
to answer client questions about platform capabilities and NexarilyAI services.

When a client expresses project interest, it fires an admin notification.
"""

import os
import re
import json
from pathlib import Path
from typing import List, Dict, Optional
from datetime import datetime

from anthropic import Anthropic
from dotenv import load_dotenv
from prompt_templates import ALITA_ASSISTANT_SYSTEM_PROMPT

load_dotenv()

# ── Knowledge base location ───────────────────────────────────────────────────
RAG_DIR = Path(__file__).parent.parent / "Agent RAGs" / "Alita Assistant RAG"

# ── Per-client knowledge storage on disk ─────────────────────────────────────
CLIENT_KNOWLEDGE_DIR = Path(__file__).parent.parent / "storage" / "knowledge"

# ── Max conversation history rounds to keep ──────────────────────────────────
MAX_HISTORY_TURNS = 12   # 12 user+assistant pairs = 24 messages

# ── Per-user conversation store {user_id: [messages]} ────────────────────────
_conversations: Dict[str, List[Dict]] = {}

# ── Cached knowledge ──────────────────────────────────────────────────────────
_knowledge_cache: Optional[str] = None


# ─────────────────────────────────────────────────────────────────────────────
# Knowledge Loading
# ─────────────────────────────────────────────────────────────────────────────

def _load_knowledge() -> str:
    """Load and cache all knowledge files from the RAG directory."""
    global _knowledge_cache
    if _knowledge_cache is not None:
        return _knowledge_cache

    if not RAG_DIR.exists():
        _knowledge_cache = ""
        return _knowledge_cache

    parts = []
    for ext in ("*.md", "*.txt"):
        for fp in sorted(RAG_DIR.glob(ext)):
            if fp.name.lower() == "readme.md":
                continue  # skip meta file
            try:
                text = fp.read_text(encoding="utf-8").strip()
                if text:
                    parts.append(f"=== {fp.name} ===\n{text}")
            except Exception:
                pass

    _knowledge_cache = "\n\n".join(parts)
    return _knowledge_cache


def reload_knowledge():
    """Force-reload knowledge (call after adding new files)."""
    global _knowledge_cache
    _knowledge_cache = None
    return _load_knowledge()


# ─────────────────────────────────────────────────────────────────────────────
# Per-Client Knowledge (disk-persisted JSONL)
# ─────────────────────────────────────────────────────────────────────────────

def _score_relevance(text: str, query: str) -> int:
    """Simple keyword overlap score — no external deps."""
    query_words = set(re.sub(r"[^\w\s]", " ", query.lower()).split())
    text_words  = set(re.sub(r"[^\w\s]", " ", text.lower()).split())
    # Ignore very common stop words
    stop = {"the","a","an","is","in","on","at","to","of","and","or","for","with","what",
            "how","do","i","you","we","my","your","it","be","that","this","are","was","can"}
    query_words -= stop
    if not query_words:
        return 0
    return len(query_words & text_words)


def _load_client_knowledge(client_id: str, query: str, max_chunks: int = 6, max_chars: int = 2400) -> str:
    """
    Load the most relevant entries from the client's knowledge base.
    Returns a formatted string ready to embed in the system prompt.
    Priority: PostgreSQL → JSONL file fallback.
    """
    entries = []

    # 1. Try PostgreSQL first (survives Railway redeploys)
    try:
        from database.db import SessionLocal
        from database.models import ClientKnowledgeEntry
        db = SessionLocal()
        try:
            rows = (
                db.query(ClientKnowledgeEntry)
                .filter(ClientKnowledgeEntry.client_id == client_id)
                .all()
            )
            for row in rows:
                text = (row.text or "").strip()
                if text:
                    entries.append({
                        "text": text,
                        "source": row.source or "manual",
                        "category": row.category or "",
                    })
        finally:
            db.close()
    except Exception:
        pass

    # 2. Fall back to JSONL file if DB returned nothing
    if not entries:
        kb_path = CLIENT_KNOWLEDGE_DIR / client_id / "knowledge.jsonl"
        if kb_path.exists():
            try:
                for line in kb_path.read_text(encoding="utf-8").splitlines():
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        obj = json.loads(line)
                        text = obj.get("text", "").strip()
                        if text:
                            entries.append(obj)
                    except Exception:
                        pass
                # Back-fill DB from file
                if entries:
                    _backfill_knowledge_to_db(client_id, entries)
            except Exception:
                pass

    if not entries:
        return ""

    # Score and sort by relevance to the current query
    scored = sorted(
        entries,
        key=lambda e: _score_relevance(e.get("text", ""), query),
        reverse=True,
    )

    # Build context block, respecting char budget
    parts = []
    total = 0
    for entry in scored[:max_chunks]:
        text  = entry.get("text", "").strip()
        label = entry.get("category") or entry.get("source") or "general"
        chunk = f"[{label}] {text}"
        if total + len(chunk) > max_chars:
            break
        parts.append(chunk)
        total += len(chunk)

    return "\n\n".join(parts)


def _backfill_knowledge_to_db(client_id: str, entries: list):
    """Back-fill knowledge entries from JSONL file into PostgreSQL."""
    try:
        import hashlib
        from database.db import SessionLocal
        from database.models import ClientKnowledgeEntry
        db = SessionLocal()
        try:
            for entry in entries:
                text = entry.get("text", "").strip()
                if not text:
                    continue
                entry_id = hashlib.sha256(f"{client_id}:{text[:200]}".encode()).hexdigest()[:32]
                existing = db.query(ClientKnowledgeEntry).filter(ClientKnowledgeEntry.id == entry_id).first()
                if not existing:
                    db.add(ClientKnowledgeEntry(
                        id=entry_id,
                        client_id=client_id,
                        text=text,
                        source=entry.get("source", "manual"),
                        category=entry.get("category", ""),
                    ))
            db.commit()
        finally:
            db.close()
    except Exception:
        pass


# ─────────────────────────────────────────────────────────────────────────────
# Client Tone / Style Loading
# ─────────────────────────────────────────────────────────────────────────────

def _load_client_tone(client_id: str) -> dict:
    """Load the client's saved tone/style preferences from PostgreSQL."""
    result: dict = {"tone_prefs": {}, "style_dna": "", "voice_profile": {}}
    try:
        from database.db import SessionLocal
        from database.models import ClientProfile
        db = SessionLocal()
        try:
            prof = db.query(ClientProfile).filter(ClientProfile.client_id == client_id).first()
            if prof:
                if getattr(prof, "tone_preferences_json", None):
                    result["tone_prefs"] = json.loads(prof.tone_preferences_json)
                if getattr(prof, "normalized_samples_text", None):
                    result["style_dna"] = prof.normalized_samples_text.strip()
                if getattr(prof, "voice_profile_json", None):
                    result["voice_profile"] = json.loads(prof.voice_profile_json)
        finally:
            db.close()
    except Exception:
        pass
    return result


def _build_tone_block(client_id: str) -> str:
    """Build a tone/style instruction block from the client's saved preferences."""
    if not client_id or client_id in ("default_client", ""):
        return ""

    tone_data = _load_client_tone(client_id)
    prefs      = tone_data.get("tone_prefs", {})
    style_dna  = tone_data.get("style_dna", "")
    voice      = tone_data.get("voice_profile", {})

    if not prefs and not style_dna and not voice:
        return ""

    lines = []

    # Tone preset label
    preset = prefs.get("preset") or prefs.get("label", "")
    if preset:
        lines.append(f"- Tone preset: {preset}")

    # Humor settings
    humor = prefs.get("humor", {})
    if humor.get("enabled"):
        intensity = humor.get("intensity", "balanced")
        comedians = humor.get("comedians", [])
        humor_line = f"- Humor: enabled ({intensity} intensity)"
        if comedians:
            humor_line += f", styled after: {', '.join(comedians[:3])}"
        lines.append(humor_line)
    else:
        lines.append("- Humor: keep minimal/professional")

    # Casual vs formal
    if prefs.get("casual_conversation"):
        lines.append("- Conversational style: casual and relaxed")

    # Pull style DNA from voice_profile if not already populated
    if not style_dna and voice:
        style_dna = (voice.get("style_dna") or voice.get("writing_style") or "").strip()

    block = "\n\n=== CLIENT COMMUNICATION STYLE ===\n"
    block += (
        "IMPORTANT: Mirror this client's preferred communication style in ALL your responses. "
        "Do not use a generic tone — adapt your voice to match theirs.\n"
    )
    if lines:
        block += "\n".join(lines) + "\n"
    if style_dna:
        # Trim to a reasonable length to stay within token budget
        trimmed = style_dna[:1500].strip()
        block += f"\nClient writing style reference (use this to match their voice):\n{trimmed}\n"
    block += "=== END COMMUNICATION STYLE ==="
    return block


def save_client_knowledge_entry(client_id: str, text: str, source: str = "manual", category: str = ""):
    """
    Save a knowledge entry to PostgreSQL (primary) and JSONL file (cache).
    Called from settings_routes.py on knowledge save.
    """
    import hashlib

    # 1. Write to PostgreSQL (survives Railway redeploys)
    try:
        from database.db import SessionLocal
        from database.models import ClientKnowledgeEntry
        db = SessionLocal()
        try:
            entry_id = hashlib.sha256(f"{client_id}:{text.strip()[:200]}".encode()).hexdigest()[:32]
            existing = db.query(ClientKnowledgeEntry).filter(ClientKnowledgeEntry.id == entry_id).first()
            if not existing:
                db.add(ClientKnowledgeEntry(
                    id=entry_id,
                    client_id=client_id,
                    text=text.strip(),
                    source=source,
                    category=category,
                ))
                db.commit()
        finally:
            db.close()
    except Exception as e:
        print(f"⚠️  Knowledge entry DB save failed: {e}")

    # 2. Also write to JSONL file (cache)
    try:
        kb_dir = CLIENT_KNOWLEDGE_DIR / client_id
        kb_dir.mkdir(parents=True, exist_ok=True)
        kb_path = kb_dir / "knowledge.jsonl"
        record = {
            "text":     text.strip(),
            "source":   source,
            "category": category,
            "added_at": datetime.utcnow().isoformat(),
        }
        with open(kb_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception:
        pass


# ─────────────────────────────────────────────────────────────────────────────
# Conversation Management
# ─────────────────────────────────────────────────────────────────────────────

def get_history(user_id: str) -> List[Dict]:
    return _conversations.get(user_id, [])


def clear_history(user_id: str):
    _conversations.pop(user_id, None)


def _add_to_history(user_id: str, role: str, content: str):
    if user_id not in _conversations:
        _conversations[user_id] = []
    _conversations[user_id].append({"role": role, "content": content})
    # Trim oldest turns if over limit (keep pairs)
    msgs = _conversations[user_id]
    if len(msgs) > MAX_HISTORY_TURNS * 2:
        _conversations[user_id] = msgs[-(MAX_HISTORY_TURNS * 2):]


# ─────────────────────────────────────────────────────────────────────────────
# Project Interest Detection
# ─────────────────────────────────────────────────────────────────────────────

_INTEREST_KEYWORDS = [
    "build", "create", "develop", "make", "want", "need",
    "interested", "cost", "price", "how much", "quote",
    "chatbot", "bot", "automation", "automate", "system",
    "app", "application", "website", "platform", "dashboard",
    "integration", "connect", "crm", "lead", "sales",
    "can you build", "can you create", "can you make",
    "would like", "i'd like", "id like", "i want", "i need",
    "hire", "project", "proposal", "custom",
]

def _detect_project_interest(message: str) -> bool:
    """Return True if the message suggests a project/service inquiry."""
    msg_lower = message.lower()
    matches = sum(1 for kw in _INTEREST_KEYWORDS if kw in msg_lower)
    return matches >= 2


def _create_project_notification(user_id: str, business_name: str, client_id: str, message: str):
    """Write a notification to the admin notifications file."""
    try:
        notif_dir = Path("storage") / "notifications"
        notif_dir.mkdir(parents=True, exist_ok=True)
        # Use a shared admin notifications file
        admin_file = notif_dir / "admin_project_requests.jsonl"
        record = {
            "id": f"proj_{int(datetime.utcnow().timestamp() * 1000)}",
            "type": "lead",
            "title": f"Project Interest: {business_name}",
            "message": f"{business_name} expressed interest via Alita chat: \"{message[:200]}\"",
            "priority": "high",
            "timestamp": datetime.utcnow().isoformat(),
            "read": False,
            "client_id": client_id,
            "user_id": user_id,
        }
        with open(admin_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")

        # Also write to the client's own notification feed
        client_notif_file = notif_dir / f"{client_id}_dashboard_alerts.jsonl"
        client_record = {
            "id": f"proj_ack_{int(datetime.utcnow().timestamp() * 1000)}",
            "type": "system",
            "title": "Request Sent to Account Manager",
            "message": "Your interest in a new AI project has been noted. "
                       "Your NexarilyAI account manager will reach out within 24 hours with details and pricing.",
            "priority": "medium",
            "timestamp": datetime.utcnow().isoformat(),
            "read": False,
        }
        with open(client_notif_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(client_record) + "\n")
    except Exception as e:
        print(f"[AlitaAssistant] Notification write error: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# System Prompt
# ─────────────────────────────────────────────────────────────────────────────

_SYSTEM_TEMPLATE = ALITA_ASSISTANT_SYSTEM_PROMPT


def _build_system(business_name: str, client_id: str = "", query: str = "") -> str:
    knowledge = _load_knowledge()
    client_knowledge = _load_client_knowledge(client_id, query) if client_id else ""
    if client_knowledge:
        client_knowledge_block = (
            "\n\n=== CLIENT BUSINESS KNOWLEDGE ===\n"
            f"{client_knowledge}\n"
            "=== END CLIENT KNOWLEDGE ===\n\n"
            "When answering questions about this client's products, services, pricing, "
            "or niche, always draw on the CLIENT BUSINESS KNOWLEDGE above first."
        )
    else:
        client_knowledge_block = ""
    tone_style_block = _build_tone_block(client_id) if client_id else ""
    # Connected platforms context
    from agents.alita_action_router import build_connected_platforms_block
    connected_platforms_block = build_connected_platforms_block(client_id) if client_id else ""
    return _SYSTEM_TEMPLATE.format(
        date=datetime.utcnow().strftime("%B %d, %Y"),
        business_name=business_name,
        knowledge=knowledge,
        client_knowledge_block=client_knowledge_block,
        tone_style_block=tone_style_block,
        connected_platforms_block=connected_platforms_block,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Main Chat Function (with tool-use support)
# ─────────────────────────────────────────────────────────────────────────────

def chat(
    user_id: str,
    message: str,
    business_name: str = "your business",
    client_id: str = "default_client",
    profile=None,
    tier: str = "pro",
) -> Dict:
    """
    Send a message to Alita and get a response.

    When Claude invokes a tool, we return an action dict for the frontend
    to render a confirmation card instead of executing immediately.

    Returns:
        {
          "reply": str,
          "project_interest_detected": bool,
          "history_length": int,
          "action": dict | None,
          "limit_error": str | None,
        }
    """
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        return {
            "reply": "I'm having trouble connecting right now. Please try again in a moment.",
            "project_interest_detected": False,
            "history_length": 0,
            "action": None,
            "limit_error": None,
        }

    # Detect project interest BEFORE generating reply
    interest = _detect_project_interest(message)
    if interest:
        _create_project_notification(user_id, business_name, client_id, message)

    # ── Defence-in-depth guardrail check (also enforced at route level) ──
    from utils.guardrails import validate_message_quick
    guard_ok, guard_msg = validate_message_quick(message)
    if not guard_ok:
        _add_to_history(user_id, "user", message)
        _add_to_history(user_id, "assistant", guard_msg)
        return {
            "reply": guard_msg,
            "project_interest_detected": False,
            "history_length": len(get_history(user_id)),
            "action": None,
            "limit_error": None,
            "navigate_url": None,
            "setting_result": None,
        }

    # Add user message to history
    _add_to_history(user_id, "user", message)

    # Build messages for Claude
    history = get_history(user_id)
    # Remove the message we just added — we'll send it as the last item
    messages = history[:-1] + [{"role": "user", "content": message}]

    # If history is just the current message, use it directly
    if not messages:
        messages = [{"role": "user", "content": message}]

    # Import tool definitions
    from agents.alita_action_router import (
        ALITA_TOOLS,
        check_action_allowed,
        optimize_params,
        store_pending,
        build_confirmation_summary,
        TOOL_META,
        PAGE_MAP,
        PLATFORM_CONNECT_MAP,
        execute_instant_setting,
    )

    try:
        from utils.ai_config import get_text_model
        client = Anthropic(api_key=api_key)
        response = client.messages.create(
            model=get_text_model(tier, complexity="simple"),
            max_tokens=1024,
            system=_build_system(business_name, client_id=client_id, query=message),
            messages=messages,
            tools=ALITA_TOOLS,
        )

        # ── Parse response blocks ──
        text_reply = ""
        tool_use_block = None

        for block in response.content:
            if block.type == "text":
                text_reply += block.text
            elif block.type == "tool_use":
                tool_use_block = block

        # ── Handle tool-use ──
        if response.stop_reason == "tool_use" and tool_use_block:
            tool_name = tool_use_block.name
            tool_params = tool_use_block.input or {}
            action_type = TOOL_META.get(tool_name, {}).get("action_type", "confirm")

            # Check plan limits
            if profile:
                allowed, limit_msg = check_action_allowed(profile, tool_name)
                if not allowed:
                    fallback_reply = text_reply.strip() if text_reply.strip() else ""
                    if fallback_reply:
                        fallback_reply += "\n\n"
                    fallback_reply += f"\u26a0\ufe0f {limit_msg}"
                    _add_to_history(user_id, "assistant", fallback_reply)
                    return {
                        "reply": fallback_reply,
                        "project_interest_detected": interest,
                        "history_length": len(get_history(user_id)),
                        "action": None,
                        "limit_error": limit_msg,
                        "navigate_url": None,
                        "setting_result": None,
                    }

            # ── NAVIGATE action — return URL for frontend redirect ──
            if action_type == "navigate":
                reply_text = text_reply.strip()

                if tool_name == "navigate_to_page":
                    page = tool_params.get("page_name", "dashboard")
                    url = PAGE_MAP.get(page, "/dashboard")
                    if not reply_text:
                        reply_text = f"Taking you to {page.replace('-', ' ').title()} now!"
                elif tool_name == "connect_social_account":
                    platform = tool_params.get("platform", "")
                    url = PLATFORM_CONNECT_MAP.get(platform, "/connect/dashboard")
                    # Append client_id for OAuth
                    if "?" in url:
                        url += f"&client_id={client_id}"
                    else:
                        url += f"?client_id={client_id}"
                    if not reply_text:
                        reply_text = f"Let's connect your {platform.title()} account! Redirecting you now..."
                else:
                    url = "/dashboard"
                    if not reply_text:
                        reply_text = "Taking you there now!"

                _add_to_history(user_id, "assistant", reply_text)
                return {
                    "reply": reply_text,
                    "project_interest_detected": interest,
                    "history_length": len(get_history(user_id)),
                    "action": None,
                    "limit_error": None,
                    "navigate_url": url,
                    "setting_result": None,
                }

            # ── INSTANT action — execute immediately, return result ──
            if action_type == "instant":
                reply_text = text_reply.strip()
                try:
                    from database.db import SessionLocal
                    _db = SessionLocal()
                    try:
                        # Re-fetch profile inside this session
                        from database.models import ClientProfile
                        _prof = _db.query(ClientProfile).filter(
                            ClientProfile.client_id == client_id
                        ).first()
                        setting_res = execute_instant_setting(
                            tool_name, tool_params, client_id, _prof or profile, _db,
                        )
                    finally:
                        _db.close()
                except Exception as e:
                    print(f"[AlitaAssistant] Instant setting error: {e}")
                    setting_res = {"message": "Sorry, I had trouble updating that setting."}

                result_msg = setting_res.get("message", "Done!")
                if not reply_text:
                    reply_text = f"\u2705 {result_msg}"
                else:
                    reply_text += f"\n\n\u2705 {result_msg}"

                _add_to_history(user_id, "assistant", reply_text)
                return {
                    "reply": reply_text,
                    "project_interest_detected": interest,
                    "history_length": len(get_history(user_id)),
                    "action": None,
                    "limit_error": None,
                    "navigate_url": None,
                    "setting_result": setting_res,
                }

            # ── CONFIRM action (default) — store pending, return confirmation card ──
            # Optimize parameters
            optimized_params, opt_notes = optimize_params(tool_name, tool_params, profile) if profile else (tool_params, [])

            # Store pending action for confirmation
            action_id = store_pending(
                tool_name=tool_name,
                params=tool_params,
                client_id=client_id,
                user_id=user_id,
                optimizations=opt_notes,
                optimized_params=optimized_params,
            )

            # Build confirmation summary
            summary = build_confirmation_summary(tool_name, optimized_params, opt_notes)
            summary["action_id"] = action_id

            # Use Claude's text as the reply, or generate a default
            reply_text = text_reply.strip()
            if not reply_text:
                meta = TOOL_META.get(tool_name, {})
                reply_text = f"I'll {meta.get('description', 'do that').lower()} for you! Here's what I have planned:"

            _add_to_history(user_id, "assistant", reply_text)

            return {
                "reply": reply_text,
                "project_interest_detected": interest,
                "history_length": len(get_history(user_id)),
                "action": summary,
                "limit_error": None,
                "navigate_url": None,
                "setting_result": None,
            }

        # ── Normal text reply (no tool use) ──
        reply = text_reply.strip()
        if not reply:
            reply = "I'm not sure how to help with that — could you rephrase?"

    except Exception as e:
        print(f"[AlitaAssistant] Claude error: {e}")
        import traceback
        traceback.print_exc()
        reply = (
            "I'm having a little trouble right now — please try again in a moment. "
            "If this persists, contact your NexarilyAI account manager."
        )

    # Add assistant reply to history
    _add_to_history(user_id, "assistant", reply)

    return {
        "reply": reply,
        "project_interest_detected": interest,
        "history_length": len(get_history(user_id)),
        "action": None,
        "limit_error": None,
        "navigate_url": None,
        "setting_result": None,
    }
