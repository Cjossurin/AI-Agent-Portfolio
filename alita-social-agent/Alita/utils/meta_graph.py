import os
import threading
from typing import Any, Dict, Optional

import httpx


_GRAPH_BASE = os.getenv("META_GRAPH_BASE", "https://graph.facebook.com")
_GRAPH_VERSION = os.getenv("META_GRAPH_VERSION", "v22.0")

_PAGE_TOKEN_CACHE: Dict[str, str] = {}
_FB_PAGE_TOKEN_CACHE: Dict[str, str] = {}
_CACHE_LOCK = threading.Lock()


_token_manager = None


def _get_token_manager():
    global _token_manager
    if _token_manager is not None:
        return _token_manager
    try:
        from api.token_manager import TokenManager

        tm = TokenManager()
        tm.initialize()
        _token_manager = tm
        print("✅ TokenManager loaded for Meta token routing")
    except Exception as e:
        print(f"⚠️  TokenManager not available in meta_graph: {e}")
        _token_manager = None
    return _token_manager


def get_user_token_for_instagram_business_account(instagram_business_account_id: str) -> Optional[str]:
    """Returns the stored OAuth user token for an IG business account, if available."""
    tm = _get_token_manager()
    if not tm:
        return None
    try:
        token = tm.get_token_by_instagram_id(str(instagram_business_account_id))
        return token or None
    except Exception:
        return None


def get_user_token_for_facebook_page(facebook_page_id: str) -> Optional[str]:
    """Returns the stored OAuth user token for a connected Facebook Page, if available."""
    tm = _get_token_manager()
    if not tm:
        return None
    try:
        token = tm.get_token_by_facebook_page_id(str(facebook_page_id))
        return token or None
    except Exception:
        return None


async def resolve_page_access_token_for_facebook_page(facebook_page_id: str) -> str:
    """Resolve a *Page access token* for a given Facebook Page ID."""
    page_id = str(facebook_page_id or "").strip()
    if not page_id:
        return os.getenv("FACEBOOK_PAGE_ACCESS_TOKEN", "") or os.getenv("INSTAGRAM_ACCESS_TOKEN", "")

    with _CACHE_LOCK:
        cached = _FB_PAGE_TOKEN_CACHE.get(page_id)
    if cached:
        return cached

    env_token = os.getenv("FACEBOOK_PAGE_ACCESS_TOKEN", "") or os.getenv("INSTAGRAM_ACCESS_TOKEN", "")

    # If the env token is already a Page token for this Page, we can use it directly.
    # If it's a *user* token, we'll try to exchange it for a Page token via /me/accounts.
    if env_token:
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                me_r = await client.get(
                    f"{_GRAPH_BASE}/{_GRAPH_VERSION}/me",
                    params={"fields": "id", "access_token": env_token},
                )
                me_id = str((me_r.json() or {}).get("id") or "").strip() if me_r.status_code == 200 else ""
                if me_id and me_id == page_id:
                    with _CACHE_LOCK:
                        _FB_PAGE_TOKEN_CACHE[page_id] = env_token
                    return env_token
        except Exception:
            pass

    user_token = get_user_token_for_facebook_page(page_id)

    # Try to resolve a Page token from either stored OAuth user token OR env token (if it was a user token).
    candidate_user_token = user_token or env_token
    if not candidate_user_token:
        return env_token

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            pages_r = await client.get(
                f"{_GRAPH_BASE}/{_GRAPH_VERSION}/me/accounts",
                params={"access_token": candidate_user_token, "limit": 200},
            )
            pages = (pages_r.json() or {}).get("data") or []
            for page in pages:
                if str((page or {}).get("id")) != page_id:
                    continue
                page_token = (page or {}).get("access_token")
                if page_token:
                    with _CACHE_LOCK:
                        _FB_PAGE_TOKEN_CACHE[page_id] = page_token
                    return page_token

    except Exception as e:
        print(f"⚠️  Failed resolving Page token for FB Page {page_id}: {e}")

    # Fallback: return whatever we have.
    return env_token or user_token or ""


async def resolve_page_access_token_for_instagram_business_account(
    instagram_business_account_id: str,
) -> str:
    """
    Resolve a *Page access token* that corresponds to the given IG Business Account.

    Falls back to:
    - `INSTAGRAM_ACCESS_TOKEN` env var
    - stored OAuth token (even if it's a user token)
    """
    ig_id = str(instagram_business_account_id or "").strip()
    if not ig_id:
        return os.getenv("INSTAGRAM_ACCESS_TOKEN", "")

    with _CACHE_LOCK:
        cached = _PAGE_TOKEN_CACHE.get(ig_id)
    if cached:
        return cached

    env_token = os.getenv("INSTAGRAM_ACCESS_TOKEN", "")

    user_token = get_user_token_for_instagram_business_account(ig_id)
    if not user_token:
        return env_token

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            pages_r = await client.get(
                f"{_GRAPH_BASE}/{_GRAPH_VERSION}/me/accounts",
                params={"access_token": user_token, "limit": 200},
            )
            pages = (pages_r.json() or {}).get("data") or []

            for page in pages:
                page_id = (page or {}).get("id")
                page_token = (page or {}).get("access_token")
                if not page_id or not page_token:
                    continue

                ig_r = await client.get(
                    f"{_GRAPH_BASE}/{_GRAPH_VERSION}/{page_id}",
                    params={
                        "fields": "instagram_business_account{id}",
                        "access_token": page_token,
                    },
                )
                ig_found = ((ig_r.json() or {}).get("instagram_business_account") or {}).get("id")
                if str(ig_found) == ig_id:
                    with _CACHE_LOCK:
                        _PAGE_TOKEN_CACHE[ig_id] = page_token
                    return page_token

    except Exception as e:
        print(f"⚠️  Failed resolving Page token for IG {ig_id}: {e}")

    # Fallback: return OAuth token even if it isn't a Page token.
    return user_token or env_token


async def send_instagram_dm(*, ig_business_account_id: str, recipient_id: str, text: str) -> Dict[str, Any]:
    """Send an Instagram DM via Graph API using the best available token."""
    access_token = await resolve_page_access_token_for_instagram_business_account(ig_business_account_id)
    if not access_token:
        return {"error": "Missing access token"}

    url = f"{_GRAPH_BASE}/{_GRAPH_VERSION}/me/messages"
    payload = {"recipient": {"id": recipient_id}, "message": {"text": text or ""}}

    async with httpx.AsyncClient(timeout=20.0) as client:
        r = await client.post(url, json=payload, params={"access_token": access_token})
        try:
            data = r.json()
        except Exception:
            data = {"raw": r.text}
        if r.status_code == 200:
            return data
        return {"error": data}


async def reply_to_instagram_comment(*, ig_business_account_id: str, comment_id: str, text: str) -> Dict[str, Any]:
    """Reply to an Instagram comment via Graph API using the best available token."""
    access_token = await resolve_page_access_token_for_instagram_business_account(ig_business_account_id)
    if not access_token:
        return {"error": "Missing access token"}

    cleaned = (text or "").encode("utf-8", errors="ignore").decode("utf-8", errors="ignore")
    url = f"{_GRAPH_BASE}/{_GRAPH_VERSION}/{comment_id}/replies"

    async with httpx.AsyncClient(timeout=20.0) as client:
        r = await client.post(url, json={"message": cleaned}, params={"access_token": access_token})
        try:
            data = r.json()
        except Exception:
            data = {"raw": r.text}
        if r.status_code == 200:
            return data
        return {"error": data}


async def send_facebook_dm(*, page_id: str, recipient_id: str, text: str) -> Dict[str, Any]:
    """Send a Facebook Messenger message from a Page via Graph API."""
    access_token = await resolve_page_access_token_for_facebook_page(page_id)
    if not access_token:
        return {"error": "Missing access token"}

    # Log token info (masked for security)
    token_preview = f"{access_token[:10]}...{access_token[-4:]}" if len(access_token) > 14 else "[token too short]"
    print(f"🔑 Sending FB DM with token: {token_preview} (len={len(access_token)})")
    
    # Inspect token permissions for debugging
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            inspect_r = await client.get(
                f"{_GRAPH_BASE}/debug_token",
                params={"input_token": access_token, "access_token": access_token}
            )
            if inspect_r.status_code == 200:
                token_data = inspect_r.json().get("data", {})
                scopes = token_data.get("scopes", [])
                app_id = token_data.get("app_id", "?")
                is_valid = token_data.get("is_valid", False)
                print(f"🔍 Token valid: {is_valid}, App ID: {app_id}")
                print(f"🔍 Token scopes: {', '.join(scopes) if scopes else 'NONE'}")
                if "pages_messaging" not in scopes:
                    print("⚠️  WARNING: Token missing 'pages_messaging' scope!")
    except Exception as e:
        print(f"⚠️  Could not inspect token: {e}")
    
    # Messenger Send API uses /me/messages with a Page access token.
    url = f"{_GRAPH_BASE}/{_GRAPH_VERSION}/me/messages"
    payload = {
        "messaging_type": "RESPONSE",
        "recipient": {"id": recipient_id},
        "message": {"text": text or ""},
    }
    
    print(f"📡 Posting to: {url}")
    print(f"📦 Payload: {payload}")

    async with httpx.AsyncClient(timeout=20.0) as client:
        r = await client.post(url, json=payload, params={"access_token": access_token})
        try:
            data = r.json()
        except Exception:
            data = {"raw": r.text}
        if r.status_code == 200:
            return data
        print(f"❌ HTTP {r.status_code}: {data}")
        return {"error": data}


async def reply_to_facebook_comment(*, page_id: str, comment_id: str, text: str) -> Dict[str, Any]:
    """Reply to a Facebook comment via Graph API using the best available token."""
    access_token = await resolve_page_access_token_for_facebook_page(page_id)
    if not access_token:
        return {"error": "Missing access token"}

    # Log token info (masked for security)
    token_preview = f"{access_token[:10]}...{access_token[-4:]}" if len(access_token) > 14 else "[token too short]"
    print(f"🔑 Replying to FB comment with token: {token_preview} (len={len(access_token)})")
    
    cleaned = (text or "").encode("utf-8", errors="ignore").decode("utf-8", errors="ignore")
    url = f"{_GRAPH_BASE}/{_GRAPH_VERSION}/{comment_id}/comments"

    async with httpx.AsyncClient(timeout=20.0) as client:
        r = await client.post(url, data={"message": cleaned}, params={"access_token": access_token})
        try:
            data = r.json()
        except Exception:
            data = {"raw": r.text}
        if r.status_code == 200:
            return data
        return {"error": data}
