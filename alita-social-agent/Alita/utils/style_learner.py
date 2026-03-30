"""
utils/style_learner.py

Automatically learn a client's tone + writing style from their existing
Instagram posts/captions.  Does NOT require Late API — uses Meta Graph API
directly with the access token we already have.

Entry points
------------
    await learn_from_instagram(client_id, access_token, ig_account_id)
        – fetch up to 75 recent captions from the IG Business Account
        – feed to Claude Haiku for style extraction
        – persist to  style_references/{client_id}/normalized_samples.txt
        – update      style_references/{client_id}/tone_prefs.json

    get_learn_status(client_id) -> dict
        – read tone_prefs.json and return auto-learn metadata for UI display
"""

import os
import json
import asyncio
from datetime import datetime, timezone
from typing import Optional

import httpx

# ── paths ────────────────────────────────────────────────────────────────
STYLE_BASE = "style_references"


def _tone_path(client_id: str) -> str:
    return os.path.join(STYLE_BASE, client_id, "tone_prefs.json")


def _samples_path(client_id: str) -> str:
    return os.path.join(STYLE_BASE, client_id, "normalized_samples.txt")


def _ensure_dir(client_id: str):
    os.makedirs(os.path.join(STYLE_BASE, client_id), exist_ok=True)


def _load_prefs(client_id: str) -> dict:
    # 1. Try PostgreSQL first (survives Railway redeploys)
    try:
        from database.db import SessionLocal
        from database.models import ClientProfile
        _db = SessionLocal()
        try:
            _prof = _db.query(ClientProfile).filter(ClientProfile.client_id == client_id).first()
            if _prof and getattr(_prof, "tone_preferences_json", None):
                return json.loads(_prof.tone_preferences_json)
        finally:
            _db.close()
    except Exception:
        pass
    # 2. Fall back to filesystem cache
    p = _tone_path(client_id)
    if os.path.exists(p):
        try:
            with open(p) as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def _save_prefs(client_id: str, prefs: dict):
    # 1. Write to PostgreSQL (primary)
    try:
        from database.db import SessionLocal
        from database.models import ClientProfile
        _db = SessionLocal()
        try:
            _prof = _db.query(ClientProfile).filter(ClientProfile.client_id == client_id).first()
            if _prof:
                _prof.tone_preferences_json = json.dumps(prefs)
                _db.commit()
        finally:
            _db.close()
    except Exception:
        pass
    # 2. Filesystem cache
    _ensure_dir(client_id)
    with open(_tone_path(client_id), "w") as f:
        json.dump(prefs, f, indent=2)


def _save_samples(client_id: str, text: str):
    # 1. Write to PostgreSQL (primary)
    try:
        from database.db import SessionLocal
        from database.models import ClientProfile
        _db = SessionLocal()
        try:
            _prof = _db.query(ClientProfile).filter(ClientProfile.client_id == client_id).first()
            if _prof:
                _prof.normalized_samples_text = text
                _db.commit()
        finally:
            _db.close()
    except Exception:
        pass
    # 2. Filesystem cache
    _ensure_dir(client_id)
    with open(_samples_path(client_id), "w", encoding="utf-8") as f:
        f.write(text)


# ── Instagram Graph API helpers ──────────────────────────────────────────

GRAPH = "https://graph.instagram.com"


async def _fetch_captions(
    access_token: str,
    ig_account_id: str,
    limit: int = 75,
) -> tuple[list[str], str | None]:
    """
    Fetch recent post captions from an IG Business Account.

    Returns (captions_list, ig_handle_or_None).
    Uses the /{ig-user-id}/media endpoint with fields=caption,timestamp.
    Silently skips posts without captions (Reels thumbnails, etc.)
    """
    captions: list[str] = []
    handle: Optional[str] = None

    async with httpx.AsyncClient(timeout=30) as client:
        # 1. Resolve @handle
        try:
            me = await client.get(
                f"{GRAPH}/{ig_account_id}",
                params={"fields": "username", "access_token": access_token},
            )
            me.raise_for_status()
            handle = me.json().get("username")
        except Exception as e:
            print(f"[style_learner] Could not fetch IG handle: {e}")

        # 2. Fetch media with captions
        url = f"{GRAPH}/{ig_account_id}/media"
        params = {
            "fields": "caption,timestamp",
            "limit": min(limit, 100),
            "access_token": access_token,
        }

        pages_fetched = 0
        while url and len(captions) < limit:
            try:
                r = await client.get(url, params=params)
                r.raise_for_status()
                data = r.json()
            except Exception as e:
                print(f"[style_learner] Media fetch error: {e}")
                break

            for post in data.get("data", []):
                cap = (post.get("caption") or "").strip()
                if cap:
                    captions.append(cap)

            # Next page
            url = data.get("paging", {}).get("next")
            params = {}  # next URL already has params baked in
            pages_fetched += 1
            if pages_fetched >= 3:  # max 3 pages × 100 = 300 (we stop at limit)
                break

    return captions[:limit], handle


# ── Claude Haiku style extraction ────────────────────────────────────────

def _build_extraction_prompt(captions: list[str]) -> str:
    sample_block = "\n\n---\n\n".join(captions[:50])
    return f"""You are a writing-style analyst. Analyze the following Instagram captions written by a business owner and extract a detailed style profile.

CAPTIONS (up to 50 samples):
---
{sample_block}
---

Write a concise style profile covering:
1. Vocabulary level (simple / conversational / elevated)
2. Sentence length tendency (short punchy / medium / long detailed)
3. Emoji usage pattern (none / rare / moderate / heavy, and which types)
4. Hashtag style (none / a few branded / many generic / hidden at end)
5. CTA patterns (what calls-to-action they typically use)
6. Energy/mood (calm, enthusiastic, educational, inspiring, humorous, etc.)
7. 3-5 signature phrases or sentence constructions they repeat
8. Overall brand voice summary in 2-3 sentences

Format your response as clear prose, not bullet points.  This will be used as a system-prompt context so the AI can imitate this person's voice faithfully.
"""


async def _extract_style_with_claude(captions: list[str]) -> Optional[str]:
    """
    Call Anthropic Claude (Haiku for cost efficiency) to extract a style profile.
    Falls back to a simple concatenation if the API is unavailable.
    """
    import anthropic

    try:
        aclient = anthropic.AsyncAnthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
        msg = await aclient.messages.create(
            model=os.getenv("CLAUDE_HAIKU_MODEL", "claude-haiku-4-5-20251001"),
            max_tokens=1024,
            messages=[
                {
                    "role": "user",
                    "content": _build_extraction_prompt(captions),
                }
            ],
        )
        return msg.content[0].text.strip()
    except Exception as e:
        print(f"[style_learner] Claude extraction failed: {e}")
        # Graceful fallback — return raw captions so the feature still works
        return "\n\n".join(captions[:30])


# ── Public entry point ───────────────────────────────────────────────────

async def learn_from_instagram(
    client_id: str,
    access_token: str,
    ig_account_id: str,
) -> dict:
    """
    Fetch captions → extract style → persist.
    Safe to call as a BackgroundTask — all errors are caught and logged.

    Returns a status dict:
        {success, post_count, ig_handle, learned_at, error}
    """
    print(f"[style_learner] Starting auto-learn for client={client_id}, ig={ig_account_id}")
    try:
        captions, handle = await _fetch_captions(access_token, ig_account_id)

        if not captions:
            print(f"[style_learner] No captions found for {client_id}")
            prefs = _load_prefs(client_id)
            prefs.update({
                "auto_learn_status": "no_content",
                "auto_learned": False,
            })
            _save_prefs(client_id, prefs)
            return {"success": False, "error": "no_captions"}

        print(f"[style_learner] Extracted {len(captions)} captions. Running style extraction…")
        style_profile = await _extract_style_with_claude(captions)

        _save_samples(client_id, style_profile or "")

        # Update tone_prefs
        prefs = _load_prefs(client_id)
        prefs.update({
            "auto_learned": True,
            "auto_learn_status": "complete",
            "post_count": len(captions),
            "ig_handle": f"@{handle}" if handle else None,
            "learned_at": datetime.now(timezone.utc).strftime("%b %d, %Y"),
        })
        _save_prefs(client_id, prefs)

        print(f"[style_learner] ✅ Style learned from {len(captions)} posts for {client_id}")
        return {
            "success": True,
            "post_count": len(captions),
            "ig_handle": handle,
            "learned_at": prefs["learned_at"],
        }

    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"[style_learner] ❌ Error during auto-learn for {client_id}: {e}")

        prefs = _load_prefs(client_id)
        prefs.update({"auto_learn_status": "error", "auto_learned": False})
        _save_prefs(client_id, prefs)

        return {"success": False, "error": str(e)}


# ── Status helper (for UI) ────────────────────────────────────────────────

def get_learn_status(client_id: str) -> dict:
    """
    Return auto-learn metadata for displaying in the tone settings page.

    Returned keys:
        enabled       – bool  (auto_learn pref is on)
        learned       – bool  (a learning pass has completed)
        status        – "complete" | "running" | "no_content" | "error" | "never"
        post_count    – int or None
        ig_handle     – "@handle" or None
        learned_at    – human date string or None
    """
    prefs = _load_prefs(client_id)
    return {
        "enabled": prefs.get("auto_learn", False),
        "learned": prefs.get("auto_learned", False),
        "status": prefs.get("auto_learn_status", "never"),
        "post_count": prefs.get("post_count"),
        "ig_handle": prefs.get("ig_handle"),
        "learned_at": prefs.get("learned_at"),
    }
