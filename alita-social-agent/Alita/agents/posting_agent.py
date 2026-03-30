"""
Posting Agent - Multi-platform content distribution with intelligent routing
Implements three-tier platform routing strategy with retry logic and rate limiting:
- Tier 1: Direct API (Meta, YouTube) - Free
- Tier 2: Late API (TikTok, LinkedIn, Twitter/X) - $33/mo
- Tier 3: Manual Queue (Fallback) - Human posting
"""

import os
import asyncio
import time
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime
from dotenv import load_dotenv
import httpx

# Import API clients
import sys
sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from api.late_client import LateAPIClient, PostRequest, PostResponse
from agents.client_profile_manager import ClientProfileManager, ClientProfile

load_dotenv()


class PlatformTier(Enum):
    """Platform routing tiers."""
    DIRECT_API = "direct_api"  # Free direct integration
    LATE_API = "late_api"  # Via Late API
    MANUAL_QUEUE = "manual_queue"  # Human posting required


class PostingStatus(Enum):
    """Status of a posting attempt."""
    SUCCESS = "success"
    PENDING = "pending"
    FAILED = "failed"
    MANUAL_REQUIRED = "manual_required"
    SCHEDULED = "scheduled"


@dataclass
class ContentPost:
    """Content to be posted to platforms."""
    content: str  # Main text content
    platform: str  # Target platform (facebook, instagram, tiktok, etc.)
    content_type: str  # Type (post, reel, story, article, thread, etc.)
    client_id: str  # Client identifier
    media_urls: Optional[List[str]] = None
    scheduled_time: Optional[str] = None
    platform_specific_params: Optional[Dict[str, Any]] = None
    

@dataclass
class PostingResult:
    """Result of a posting attempt."""
    success: bool
    platform: str
    content_type: str
    post_id: Optional[str] = None
    status: str = "failed"
    tier_used: Optional[str] = None
    error: Optional[str] = None
    manual_queue_entry: Optional[Dict] = None
    timestamp: str = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now().isoformat()


class PostingAgent:
    """
    Multi-platform posting agent with intelligent routing.
    
    Routing Logic:
    1. Determine platform tier (Direct, Late API, or Manual)
    2. Attempt posting via appropriate method
    3. Fall back to manual queue on failure
    4. Track all posting attempts and results
    
    Usage:
        agent = PostingAgent(client_id="client_123")
        result = await agent.post_content(content_post)
    """
    
    # Canonical platform name mapping — collapse aliases that appear in
    # calendar posts, OAuth callbacks, and env vars into the single name
    # that Late API accepts.
    _PLATFORM_ALIASES: Dict[str, str] = {
        "x":          "twitter",
        "twitter_x":  "twitter",
        "twitter/x":  "twitter",
        "ig":         "instagram",
        "fb":         "facebook",
        "yt":         "youtube",
        "tt":         "tiktok",
        "li":         "linkedin",
    }

    @classmethod
    def _normalise_platform(cls, name: str) -> str:
        """Return the canonical Late-API platform name."""
        key = name.lower().strip()
        return cls._PLATFORM_ALIASES.get(key, key)

    # Platform tier mapping
    PLATFORM_TIERS = {
        # Tier 1: Direct API (Free)
        "facebook": PlatformTier.DIRECT_API,
        "instagram": PlatformTier.DIRECT_API,
        "wordpress": PlatformTier.DIRECT_API,
        "blog": PlatformTier.DIRECT_API,
        
        # Tier 2: Late API ($33/mo)
        "youtube": PlatformTier.LATE_API,  # YouTube Shorts via Late API
        "tiktok": PlatformTier.LATE_API,
        "linkedin": PlatformTier.LATE_API,
        "twitter": PlatformTier.LATE_API,
        "twitter_x": PlatformTier.LATE_API,  # Calendar-agent alias
        "x": PlatformTier.LATE_API,  # Alias for Twitter
        "threads": PlatformTier.LATE_API,
        "reddit": PlatformTier.LATE_API,
        "pinterest": PlatformTier.LATE_API,
        "bluesky": PlatformTier.LATE_API,
    }
    
    def __init__(self, client_id: str, late_api_key: Optional[str] = None, user_token: Optional[str] = None):
        """
        Initialize posting agent.
        
        Args:
            client_id: Client identifier for multi-client support
            late_api_key: Late API key (defaults to LATE_API_KEY env var)
            user_token: OAuth user token (overrides env var if provided)
        """
        self.client_id = client_id
        
        # Load client profile  (niche, preferred platforms)
        self.profile_manager = ClientProfileManager()
        self.client_profile: Optional[ClientProfile] = self.profile_manager.get_client_profile(client_id)
        
        # Retry configuration
        self.max_retries = 3
        self.retry_delay = 2  # Initial delay in seconds (exponential backoff)
        
        # Rate limiting (per platform)
        self.rate_limits = {
            "instagram": {"calls": 200, "period": 3600},  # 200 calls/hour
            "facebook": {"calls": 200, "period": 3600},
            "twitter": {"calls": 300, "period": 900},  # 300 calls/15 min
            "linkedin": {"calls": 100, "period": 86400},  # 100 calls/day
            "tiktok": {"calls": 50, "period": 3600}
        }
        self.last_call_times: Dict[str, List[float]] = {}
        
        # Initialize Late API client
        try:
            self.late_client = LateAPIClient(api_key=late_api_key)
            self.late_api_available = True
        except ValueError:
            print("⚠️  Late API key not configured. Tier 2 platforms will use manual queue.")
            self.late_client = None
            self.late_api_available = False
        
        # === USER AUTHENTICATION (OAuth or Server Token) ===
        # Priority: OAuth user_token > TokenManager lookup > env var fallback
        if user_token:
            # OAuth token provided directly (from orchestrator or dashboard)
            self.instagram_access_token = user_token
            self._token_source = "oauth_direct"
            print(f"🔑 Using OAuth user token for {client_id}")
        else:
            # Try TokenManager lookup by client_id
            token_from_db = self._lookup_oauth_token(client_id)
            if token_from_db:
                self.instagram_access_token = token_from_db
                self._token_source = "oauth_database"
                print(f"🔑 Using OAuth token from database for {client_id}")
            else:
                # Fallback to server token from env var
                self.instagram_access_token = os.getenv("INSTAGRAM_ACCESS_TOKEN")
                self._token_source = "env_var"
                if self.instagram_access_token:
                    print(f"🔑 Using server token from env var for {client_id}")
        
        self.instagram_business_id = os.getenv("INSTAGRAM_BUSINESS_ACCOUNT_ID")
        self.facebook_page_id = os.getenv("FACEBOOK_PAGE_ID")  # Optional, for Facebook posting
        # === END USER AUTHENTICATION ===

        # Per-client ID override — read from DB (populated during OAuth)
        self._load_per_client_ids(client_id)
        
        # Track posting history
        self.posting_history: List[PostingResult] = []
        self.manual_queue: List[Dict] = []
        
        # Platform profile mapping (loaded from config/database in production)
        self.platform_profiles = self._load_platform_profiles()
        
        print(f"✅ Posting Agent initialized for {client_id}")
        if self.client_profile:
            print(f"   Preferred platforms: {', '.join(self.client_profile.platforms)}")
    
    def _load_platform_profiles(self) -> Dict[str, str]:
        """
        Load platform profile IDs for this client.
        Priority: DB (PlatformConnection table) > connections JSON > env vars.
        All platform names are normalised through ``_normalise_platform``.
        """
        profiles: Dict[str, str] = {}

        # First: load from PostgreSQL PlatformConnection table (survives redeploys)
        try:
            from database.db import SessionLocal
            from database.models import PlatformConnection
            db = SessionLocal()
            try:
                rows = (
                    db.query(PlatformConnection)
                    .filter(PlatformConnection.client_id == self.client_id)
                    .all()
                )
                for row in rows:
                    pid = getattr(row, "account_id", "") or ""
                    if pid:
                        profiles[self._normalise_platform(row.platform)] = pid
            finally:
                db.close()
        except Exception as exc:
            print(f"⚠️  PostingAgent: DB profile lookup failed: {exc}")

        # Second: fill gaps from the per-client Late API connections file (cache)
        try:
            import json as _json
            conn_file = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                                     "storage", "client_connections.json")
            if os.path.exists(conn_file):
                with open(conn_file, "r") as f:
                    all_conns = _json.load(f)
                client_conns = all_conns.get(self.client_id, {})
                for plat, info in client_conns.items():
                    pid = info.get("profile_id", "")
                    canon = self._normalise_platform(plat)
                    if pid and canon not in profiles:
                        profiles[canon] = pid
        except Exception:
            pass

        # Fill remaining platforms from env vars (fallback)
        for plat in ("youtube", "tiktok", "linkedin", "twitter",
                     "threads", "reddit", "pinterest", "bluesky"):
            if plat not in profiles:
                env_val = os.getenv(f"LATE_PROFILE_{plat.upper()}_{self.client_id}", "")
                if env_val:
                    profiles[plat] = env_val

        print(f"   📋 Late API profiles for {self.client_id}: "
              f"{list(profiles.keys()) if profiles else '(none)'}")
        return profiles
    
    @staticmethod
    def _lookup_oauth_token(client_id: str) -> Optional[str]:
        """
        Look up OAuth token from TokenManager database.
        
        Tries to find a valid (non-expired) token for this client_id.
        Falls through silently if TokenManager is not available.
        """
        try:
            from api.token_manager import TokenManager
            tm = TokenManager()
            token = tm.get_valid_token(client_id)
            return token
        except Exception:
            return None

    def _load_per_client_ids(self, client_id: str) -> None:
        """Load instagram_business_id and facebook_page_id from the client's
        ClientProfile in the database.  Falls back to env vars."""
        try:
            from database.db import SessionLocal
            from database.models import ClientProfile as _CP
            db = SessionLocal()
            try:
                profile = db.query(_CP).filter(_CP.client_id == client_id).first()
                if profile:
                    if profile.meta_ig_account_id:
                        self.instagram_business_id = profile.meta_ig_account_id
                        print(f"   📋 IG Business ID from DB: {self.instagram_business_id}")
                    if profile.meta_facebook_page_id:
                        self.facebook_page_id = profile.meta_facebook_page_id
                        print(f"   📋 FB Page ID from DB: {self.facebook_page_id}")
            finally:
                db.close()
        except Exception as e:
            print(f"   ⚠️  Could not load per-client IDs from DB: {e}")
    
    def get_platform_tier(self, platform: str) -> PlatformTier:
        """Determine which tier a platform belongs to."""
        return self.PLATFORM_TIERS.get(platform.lower(), PlatformTier.MANUAL_QUEUE)
    
    def _check_rate_limit(self, platform: str) -> bool:
        """
        Check if we're within rate limits for this platform.
        
        Args:
            platform: Platform name
            
        Returns:
            True if we can make the call, False if rate limited
        """
        if platform not in self.rate_limits:
            return True  # No rate limit defined
        
        limit = self.rate_limits[platform]
        now = time.time()
        
        # Initialize if first call
        if platform not in self.last_call_times:
            self.last_call_times[platform] = []
        
        # Remove calls outside the time window
        self.last_call_times[platform] = [
            t for t in self.last_call_times[platform]
            if now - t < limit["period"]
        ]
        
        # Check if we're at the limit
        if len(self.last_call_times[platform]) >= limit["calls"]:
            return False
        
        # Record this call
        self.last_call_times[platform].append(now)
        return True
    
    async def _retry_with_backoff(self, func, *args, **kwargs):
        """
        Retry a function with exponential backoff.
        Handles both exceptions AND PostingResult(success=False) returns.
        """
        last_result = None
        
        for attempt in range(self.max_retries):
            try:
                result = await func(*args, **kwargs)
                # If the function returned a successful result, return immediately
                if hasattr(result, 'success') and result.success:
                    return result
                # Failed PostingResult — treat like a retriable error
                if hasattr(result, 'success') and not result.success:
                    last_result = result
                    if attempt < self.max_retries - 1:
                        delay = self.retry_delay * (2 ** attempt)
                        print(f"   ⚠️ Attempt {attempt + 1} failed: {getattr(result, 'error', 'unknown')}")
                        print(f"   ⏳ Retrying in {delay} seconds...")
                        await asyncio.sleep(delay)
                        continue
                    else:
                        print(f"   ❌ All {self.max_retries} retry attempts failed")
                        return result
                return result  # Non-PostingResult object, return as-is
            except Exception as e:
                last_result = e
                if attempt < self.max_retries - 1:
                    delay = self.retry_delay * (2 ** attempt)
                    print(f"   ⚠️ Attempt {attempt + 1} failed: {str(e)}")
                    print(f"   ⏳ Retrying in {delay} seconds...")
                    await asyncio.sleep(delay)
                else:
                    print(f"   ❌ All {self.max_retries} retry attempts failed")
        
        if isinstance(last_result, Exception):
            raise last_result
        return last_result
    
    # === SCENE 3 SCREENCAST: SINGLE POST FUNCTION START ===
    async def post_content(self, post: ContentPost) -> PostingResult:
        """
        Post content to the specified platform with retry logic and rate limiting.
        
        Routes to appropriate posting method based on platform tier.
        Falls back to manual queue on failure.
        
        Args:
            post: ContentPost with all posting details
            
        Returns:
            PostingResult with success status and details
        """
        platform = self._normalise_platform(post.platform)
        tier = self.get_platform_tier(platform)
        
        print(f"\n📤 Posting to {platform.upper()} (Tier: {tier.value})")
        print(f"   Content Type: {post.content_type}")
        print(f"   Content Preview: {post.content[:50]}...")
        
        # Check rate limits
        if not self._check_rate_limit(platform):
            print(f"   ⚠️ Rate limit reached for {platform}. Queueing for later...")
            return PostingResult(
                success=False,
                platform=platform,
                content_type=post.content_type,
                status="rate_limited",
                tier_used=tier.value,
                error=f"Rate limit reached for {platform}. Try again later."
            )
        
        try:
            # Route to appropriate posting method with retry logic
            if tier == PlatformTier.DIRECT_API:
                result = await self._retry_with_backoff(self._post_via_direct_api, post)
            elif tier == PlatformTier.LATE_API:
                result = await self._retry_with_backoff(self._post_via_late_api, post)
            else:
                result = self._queue_for_manual_posting(post)
        except Exception as e:
            print(f"   ❌ All retry attempts failed: {str(e)}")
            result = PostingResult(
                success=False,
                platform=platform,
                content_type=post.content_type,
                status="failed_after_retries",
                tier_used=tier.value,
                error=f"Failed after {self.max_retries} retries: {str(e)}"
            )
        
        # Fall back to manual queue only for DIRECT_API failures
        # Late API failures should surface as real failures, not get silently queued
        if (not result.success
                and result.status not in ["manual_required", "rate_limited"]
                and tier == PlatformTier.DIRECT_API):
            print(f"   ⚠️  Posting failed, adding to manual queue...")
            result = self._queue_for_manual_posting(post)
        
        # Track result
        self.posting_history.append(result)
        
        if result.success:
            print(f"   ✅ Posted successfully! Post ID: {result.post_id}")
        elif result.status == "manual_required":
            print(f"   📋 Added to manual posting queue")
        elif result.status == "rate_limited":
            print(f"   ⏸️  Rate limited - queue for later")
        else:
            print(f"   ❌ Failed: {result.error}")
        
        return result
    # === SCENE 3 SCREENCAST: SINGLE POST FUNCTION END ===
    
    async def _post_via_direct_api(self, post: ContentPost) -> PostingResult:
        """
        Post via direct platform API (Tier 1).
        Supports Instagram and Facebook via Meta Graph API.
        """
        platform = post.platform.lower()
        
        if platform == "instagram":
            return await self._post_to_instagram(post)
        elif platform == "facebook":
            return await self._post_to_facebook(post)
        elif platform == "youtube":
            return PostingResult(
                success=False,
                platform=platform,
                content_type=post.content_type,
                status="not_implemented",
                tier_used=PlatformTier.DIRECT_API.value,
                error="Direct YouTube API integration not yet implemented. Use manual queue."
            )
        else:
            return PostingResult(
                success=False,
                platform=platform,
                content_type=post.content_type,
                status="not_implemented",
                tier_used=PlatformTier.DIRECT_API.value,
                error=f"Direct API for {platform} not implemented."
            )
    
    # ── Helpers ─────────────────────────────────────────────────────

    @staticmethod
    def _is_video_url(url: str) -> bool:
        """Detect whether a URL points to a video (extension + common CDN patterns)."""
        lower = url.lower().split("?")[0]  # ignore query params
        if lower.endswith(('.mp4', '.mov', '.avi', '.mkv', '.webm')):
            return True
        # CDN patterns (fal.ai, replicate, etc.) that serve video without extension
        video_hints = ["/video/", "content-type=video", "media_type=video"]
        return any(h in url.lower() for h in video_hints)

    async def _resolve_media_url(self, path: str) -> str:
        """If path is a local file, upload it to imgbb; otherwise return as-is."""
        if os.path.exists(path):
            url = await self._upload_image_to_imgbb(path)
            if not url:
                raise Exception("Failed to upload local file to hosting service")
            return url
        return path

    async def _ig_wait_for_media(self, client: httpx.AsyncClient, container_id: str,
                                  max_wait: int = 60, interval: int = 5) -> None:
        """Poll the container status until FINISHED or timeout (for video / reels)."""
        for _ in range(max_wait // interval):
            status_resp = await client.get(
                f"https://graph.facebook.com/v21.0/{container_id}",
                params={"fields": "status_code", "access_token": self.instagram_access_token},
            )
            status_code = status_resp.json().get("status_code", "")
            if status_code == "FINISHED":
                return
            if status_code == "ERROR":
                raise Exception(f"Instagram media processing error: {status_resp.json()}")
            print(f"   ⏳  Media processing: {status_code}…")
            await asyncio.sleep(interval)
        raise Exception("Timeout waiting for Instagram to process media")

    async def _ig_publish_container(self, client: httpx.AsyncClient, container_id: str) -> str:
        """Publish a ready container and return the post ID."""
        resp = await client.post(
            f"https://graph.facebook.com/v21.0/{self.instagram_business_id}/media_publish",
            params={"access_token": self.instagram_access_token, "creation_id": container_id},
        )
        try:
            resp.raise_for_status()
        except Exception:
            raise Exception(f"Media publish failed: {resp.text}")
        post_id = resp.json().get("id")
        if not post_id:
            raise Exception(f"No post ID in publish response: {resp.json()}")
        return post_id

    # ── Main Instagram dispatcher ─────────────────────────────────

    async def _post_to_instagram(self, post: ContentPost) -> PostingResult:
        """
        Post to Instagram via Graph API.
        
        Supports:
          • Image posts (single image)
          • Video posts (uploaded video)
          • Reels  — media_type=REELS + video_url
          • Stories — media_type=STORIES + image_url or video_url
          • Carousels — child containers + media_type=CAROUSEL
        """
        if not self.instagram_access_token or not self.instagram_business_id:
            return PostingResult(
                success=False,
                platform="instagram",
                content_type=post.content_type,
                status="credentials_missing",
                tier_used=PlatformTier.DIRECT_API.value,
                error="Instagram credentials not configured. Set INSTAGRAM_ACCESS_TOKEN and INSTAGRAM_BUSINESS_ACCOUNT_ID"
            )
        
        # Instagram requires media (image or video)
        if not post.media_urls or len(post.media_urls) == 0:
            return PostingResult(
                success=False,
                platform="instagram",
                content_type=post.content_type,
                status="media_required",
                tier_used=PlatformTier.DIRECT_API.value,
                error="Instagram posts require at least one image or video. Provide media_urls."
            )
        
        content_type = (post.content_type or "post").lower()

        try:
            if content_type == "carousel" and len(post.media_urls) > 1:
                return await self._ig_post_carousel(post)
            elif content_type == "story":
                return await self._ig_post_story(post)
            elif content_type == "reel":
                return await self._ig_post_reel(post)
            else:
                return await self._ig_post_single(post)
        except Exception as e:
            error_msg = f"Instagram API error: {str(e)}"
            print(f"   ❌ {error_msg}")
            import traceback
            print(f"   📋 Traceback: {traceback.format_exc()}")
            return PostingResult(
                success=False,
                platform="instagram",
                content_type=post.content_type,
                status="api_error",
                tier_used=PlatformTier.DIRECT_API.value,
                error=error_msg
            )

    # ── Single image / video post ─────────────────────────────────

    async def _ig_post_single(self, post: ContentPost) -> PostingResult:
        """Standard single-image or single-video post."""
        media_url = await self._resolve_media_url(post.media_urls[0])
        is_video = self._is_video_url(media_url)

        container_params = {
            "access_token": self.instagram_access_token,
            "caption": post.content,
        }
        if is_video:
            container_params["media_type"] = "VIDEO"
            container_params["video_url"] = media_url
        else:
            container_params["image_url"] = media_url

        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                f"https://graph.facebook.com/v21.0/{self.instagram_business_id}/media",
                params=container_params,
            )
            resp.raise_for_status()
            container_id = resp.json().get("id")
            print(f"   📦 Container created: {container_id}")

            if is_video:
                await self._ig_wait_for_media(client, container_id)
            else:
                await asyncio.sleep(5)

            post_id = await self._ig_publish_container(client, container_id)

        return PostingResult(
            success=True, platform="instagram", content_type=post.content_type,
            post_id=post_id, status="published", tier_used=PlatformTier.DIRECT_API.value,
        )

    # ── Reels ─────────────────────────────────────────────────────

    async def _ig_post_reel(self, post: ContentPost) -> PostingResult:
        """Publish an Instagram Reel (short-form video)."""
        media_url = await self._resolve_media_url(post.media_urls[0])

        container_params = {
            "access_token": self.instagram_access_token,
            "caption": post.content,
            "media_type": "REELS",
            "video_url": media_url,
            "share_to_feed": "true",
        }

        async with httpx.AsyncClient(timeout=90.0) as client:
            resp = await client.post(
                f"https://graph.facebook.com/v21.0/{self.instagram_business_id}/media",
                params=container_params,
            )
            resp.raise_for_status()
            container_id = resp.json().get("id")
            print(f"   🎬 Reel container created: {container_id}")

            await self._ig_wait_for_media(client, container_id, max_wait=120)
            post_id = await self._ig_publish_container(client, container_id)

        return PostingResult(
            success=True, platform="instagram", content_type="reel",
            post_id=post_id, status="published", tier_used=PlatformTier.DIRECT_API.value,
        )

    # ── Stories ────────────────────────────────────────────────────

    async def _ig_post_story(self, post: ContentPost) -> PostingResult:
        """Publish an Instagram Story (image or video)."""
        media_url = await self._resolve_media_url(post.media_urls[0])
        is_video = self._is_video_url(media_url)

        container_params = {
            "access_token": self.instagram_access_token,
            "media_type": "STORIES",
        }
        if is_video:
            container_params["video_url"] = media_url
        else:
            container_params["image_url"] = media_url

        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                f"https://graph.facebook.com/v21.0/{self.instagram_business_id}/media",
                params=container_params,
            )
            resp.raise_for_status()
            container_id = resp.json().get("id")
            print(f"   📖 Story container created: {container_id}")

            if is_video:
                await self._ig_wait_for_media(client, container_id)
            else:
                await asyncio.sleep(5)

            post_id = await self._ig_publish_container(client, container_id)

        return PostingResult(
            success=True, platform="instagram", content_type="story",
            post_id=post_id, status="published", tier_used=PlatformTier.DIRECT_API.value,
        )

    # ── Carousels ──────────────────────────────────────────────────

    async def _ig_post_carousel(self, post: ContentPost) -> PostingResult:
        """Publish an Instagram Carousel (2–10 images/videos)."""
        media_urls = post.media_urls[:10]  # IG limit is 10 items
        child_ids: List[str] = []

        async with httpx.AsyncClient(timeout=90.0) as client:
            # Step 1: Create child containers
            for idx, raw_url in enumerate(media_urls):
                url = await self._resolve_media_url(raw_url)
                is_video = self._is_video_url(url)

                child_params = {
                    "access_token": self.instagram_access_token,
                    "is_carousel_item": "true",
                }
                if is_video:
                    child_params["media_type"] = "VIDEO"
                    child_params["video_url"] = url
                else:
                    child_params["image_url"] = url

                resp = await client.post(
                    f"https://graph.facebook.com/v21.0/{self.instagram_business_id}/media",
                    params=child_params,
                )
                resp.raise_for_status()
                child_id = resp.json().get("id")
                child_ids.append(child_id)
                print(f"   📎 Carousel child {idx+1}/{len(media_urls)}: {child_id}")

                # Wait for video children to finish processing
                if is_video:
                    await self._ig_wait_for_media(client, child_id)

            # Brief pause to let image children settle
            await asyncio.sleep(5)

            # Step 2: Create parent carousel container
            parent_params = {
                "access_token": self.instagram_access_token,
                "media_type": "CAROUSEL",
                "caption": post.content,
                "children": ",".join(child_ids),
            }
            resp = await client.post(
                f"https://graph.facebook.com/v21.0/{self.instagram_business_id}/media",
                params=parent_params,
            )
            resp.raise_for_status()
            carousel_id = resp.json().get("id")
            print(f"   🖼️  Carousel container created: {carousel_id}")

            await asyncio.sleep(5)

            # Step 3: Publish
            post_id = await self._ig_publish_container(client, carousel_id)

        return PostingResult(
            success=True, platform="instagram", content_type="carousel",
            post_id=post_id, status="published", tier_used=PlatformTier.DIRECT_API.value,
        )
    
    async def _post_to_facebook(self, post: ContentPost) -> PostingResult:
        """
        Post to Facebook Page via Graph API.
        Supports text posts with optional media.
        """
        if not self.instagram_access_token:  # Same token works for Facebook
            return PostingResult(
                success=False,
                platform="facebook",
                content_type=post.content_type,
                status="credentials_missing",
                tier_used=PlatformTier.DIRECT_API.value,
                error="Facebook access token not configured. Set INSTAGRAM_ACCESS_TOKEN (works for both)"
            )
        
        # Use configured page ID or fall back to getting it from token
        page_id = self.facebook_page_id
        
        if not page_id:
            # Try to get page ID from /me/accounts
            try:
                async with httpx.AsyncClient(timeout=30.0) as client:
                    accounts_response = await client.get(
                        f"https://graph.facebook.com/v21.0/me/accounts",
                        params={"access_token": self.instagram_access_token}
                    )
                    accounts_response.raise_for_status()
                    accounts = accounts_response.json().get("data", [])
                    
                    if accounts:
                        page_id = accounts[0]["id"]  # Use first page
                    else:
                        return PostingResult(
                            success=False,
                            platform="facebook",
                            content_type=post.content_type,
                            status="no_pages_found",
                            tier_used=PlatformTier.DIRECT_API.value,
                            error="No Facebook Pages found for this access token"
                        )
            except Exception as e:
                return PostingResult(
                    success=False,
                    platform="facebook",
                    content_type=post.content_type,
                    status="api_error",
                    tier_used=PlatformTier.DIRECT_API.value,
                    error=f"Failed to retrieve Facebook Pages: {str(e)}"
                )
        
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                # Build post params
                post_params = {
                    "access_token": self.instagram_access_token,
                    "message": post.content
                }
                
                has_media = post.media_urls and len(post.media_urls) > 0

                if has_media:
                    media_url = post.media_urls[0]
                    # Resolve local files
                    if os.path.exists(media_url):
                        media_url = await self._upload_image_to_imgbb(media_url) or media_url

                    is_video = self._is_video_url(media_url)

                    if is_video:
                        # Video: use /{page_id}/videos endpoint
                        video_params = {
                            "access_token": self.instagram_access_token,
                            "file_url": media_url,
                            "description": post.content,
                        }
                        response = await client.post(
                            f"https://graph.facebook.com/v21.0/{page_id}/videos",
                            params=video_params,
                        )
                    else:
                        # Photo: use /{page_id}/photos endpoint (proper image upload)
                        photo_params = {
                            "access_token": self.instagram_access_token,
                            "url": media_url,
                            "caption": post.content,
                        }
                        response = await client.post(
                            f"https://graph.facebook.com/v21.0/{page_id}/photos",
                            params=photo_params,
                        )
                else:
                    # Text-only post to feed
                    response = await client.post(
                        f"https://graph.facebook.com/v21.0/{page_id}/feed",
                        params=post_params,
                    )
                
                response.raise_for_status()
                post_id = response.json().get("id") or response.json().get("post_id")
                
                return PostingResult(
                    success=True,
                    platform="facebook",
                    content_type=post.content_type,
                    post_id=post_id,
                    status="published",
                    tier_used=PlatformTier.DIRECT_API.value
                )
                
        except Exception as e:
            return PostingResult(
                success=False,
                platform="facebook",
                content_type=post.content_type,
                status="api_error",
                tier_used=PlatformTier.DIRECT_API.value,
                error=f"Facebook API error: {str(e)}"
            )
    
    async def _post_via_late_api(self, post: ContentPost) -> PostingResult:
        """Post via Late API (Tier 2)."""
        platform = self._normalise_platform(post.platform)
        
        # Check if Late API is available
        if not self.late_api_available or not self.late_client:
            return PostingResult(
                success=False,
                platform=platform,
                content_type=post.content_type,
                status="late_api_unavailable",
                tier_used=PlatformTier.LATE_API.value,
                error="Late API client not configured. Set LATE_API_KEY environment variable."
            )
        
        # Get profile ID for this platform
        profile_id = self.platform_profiles.get(platform)
        if not profile_id:
            print(f"   ⚠️  No Late API profile for '{platform}' "
                  f"(client={self.client_id}, available={list(self.platform_profiles.keys())})")
            return PostingResult(
                success=False,
                platform=platform,
                content_type=post.content_type,
                status="profile_not_configured",
                tier_used=PlatformTier.LATE_API.value,
                error=f"No profile ID configured for {platform}. Set LATE_PROFILE_{platform.upper()}_{self.client_id}"
            )
        
        # Create Late API request
        late_request = PostRequest(
            platform=platform,
            profile_id=profile_id,
            content=post.content,
            media_urls=post.media_urls,
            scheduled_time=post.scheduled_time,
            additional_params=post.platform_specific_params
        )
        
        # Post via Late API
        response = await self.late_client.post_to_platform(late_request)
        
        # Convert to PostingResult
        if response.success:
            return PostingResult(
                success=True,
                platform=platform,
                content_type=post.content_type,
                post_id=response.post_id,
                status=response.status or "published",
                tier_used=PlatformTier.LATE_API.value
            )
        else:
            return PostingResult(
                success=False,
                platform=platform,
                content_type=post.content_type,
                status="failed",
                tier_used=PlatformTier.LATE_API.value,
                error=response.error
            )
    
    def _queue_for_manual_posting(self, post: ContentPost) -> PostingResult:
        """Add content to manual posting queue (Tier 3 / Fallback)."""
        
        manual_entry = {
            "id": f"manual_{len(self.manual_queue) + 1}",
            "platform": post.platform,
            "content_type": post.content_type,
            "content": post.content,
            "media_urls": post.media_urls,
            "scheduled_time": post.scheduled_time,
            "client_id": self.client_id,
            "queued_at": datetime.now().isoformat(),
            "status": "pending_manual_post"
        }
        
        self.manual_queue.append(manual_entry)
        
        return PostingResult(
            success=False,  # Not posted yet, requires manual action
            platform=post.platform,
            content_type=post.content_type,
            status="manual_required",
            tier_used=PlatformTier.MANUAL_QUEUE.value,
            manual_queue_entry=manual_entry
        )
    
    async def post_to_multiple_platforms(self, posts: List[ContentPost]) -> List[PostingResult]:
        """
        Post the same or different content to multiple platforms.
        
        Args:
            posts: List of ContentPost objects
            
        Returns:
            List of PostingResult objects
        """
        results = []
        
        print(f"\n🚀 Posting to {len(posts)} platform(s)...")
        
        for post in posts:
            result = await self.post_content(post)
            results.append(result)
            
            # Small delay between posts to avoid rate limits
            await asyncio.sleep(0.5)
        
        # Summary
        successes = sum(1 for r in results if r.success)
        manual = sum(1 for r in results if r.status == "manual_required")
        failures = len(results) - successes - manual
        
        print(f"\n📊 Posting Summary:")
        print(f"   ✅ Successful: {successes}")
        print(f"   📋 Manual Queue: {manual}")
        print(f"   ❌ Failed: {failures}")
        
        return results
    
    def get_manual_queue(self) -> List[Dict]:
        """Get all items in the manual posting queue."""
        return self.manual_queue
    
    def get_recommended_platforms(self) -> List[str]:
        """
        Get recommended platforms for this client based on niche.
        
        Returns:
            List of platform names from client profile, or defaults
        """
        if self.client_profile:
            return self.client_profile.platforms
        return ["instagram", "facebook", "tiktok", "linkedin"]  # fallback
    
    def get_posting_stats(self) -> Dict:
        """
        Get posting statistics for this client.
        
        Returns:
            Dictionary with success rates, platform breakdown, etc.
        """
        if not self.posting_history:
            return {
                "total_posts": 0,
                "successful": 0,
                "failed": 0,
                "manual_required": 0,
                "rate_limited": 0,
                "success_rate": 0.0
            }
        
        total = len(self.posting_history)
        successful = sum(1 for r in self.posting_history if r.success)
        manual = sum(1 for r in self.posting_history if r.status == "manual_required")
        rate_limited = sum(1 for r in self.posting_history if r.status == "rate_limited")
        failed = total - successful - manual - rate_limited
        
        # Platform breakdown
        platform_stats = {}
        for result in self.posting_history:
            platform = result.platform
            if platform not in platform_stats:
                platform_stats[platform] = {"total": 0, "successful": 0}
            platform_stats[platform]["total"] += 1
            if result.success:
                platform_stats[platform]["successful"] += 1
        
        return {
            "total_posts": total,
            "successful": successful,
            "failed": failed,
            "manual_required": manual,
            "rate_limited": rate_limited,
            "success_rate": (successful / total * 100) if total > 0 else 0.0,
            "platform_breakdown": platform_stats
        }
    
    def clear_manual_queue_item(self, item_id: str) -> bool:
        """Remove an item from manual queue after it's been posted."""
        original_length = len(self.manual_queue)
        self.manual_queue = [item for item in self.manual_queue if item["id"] != item_id]
        return len(self.manual_queue) < original_length
    
    async def _upload_image_to_imgbb(self, image_path: str) -> Optional[str]:
        """
        Upload a local image to imgbb for temporary hosting.
        Returns the public URL or None if upload fails.
        """
        imgbb_api_key = os.getenv("IMGBB_API_KEY")
        
        if not imgbb_api_key:
            print("⚠️  IMGBB_API_KEY not set. Cannot upload local images. Get one free at: https://api.imgbb.com/")
            return None
        
        try:
            import base64
            
            # Read and encode image
            with open(image_path, "rb") as image_file:
                image_data = base64.b64encode(image_file.read()).decode()
            
            # Upload to imgbb
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    "https://api.imgbb.com/1/upload",
                    data={
                        "key": imgbb_api_key,
                        "image": image_data
                    }
                )
                response.raise_for_status()
                result = response.json()
                
                if result.get("success"):
                    url = result["data"]["url"]
                    print(f"✅ Image uploaded to: {url}")
                    return url
                else:
                    print(f"❌ Image upload failed: {result}")
                    return None
                    
        except Exception as e:
            print(f"❌ Error uploading image: {e}")
            return None
    
    def get_posting_history(self, platform: Optional[str] = None) -> List[PostingResult]:
        """Get posting history, optionally filtered by platform."""
        if platform:
            return [r for r in self.posting_history if r.platform == platform.lower()]
        return self.posting_history


# Example usage and testing
async def example_usage():
    """Example of how to use the Posting Agent."""
    
    # Initialize agent for a specific client
    agent = PostingAgent(client_id="demo_client")
    
    # Example 1: Post to Twitter
    twitter_post = ContentPost(
        content="Just launched our new AI automation platform! 🚀 Check it out at example.com #AI #Automation",
        platform="twitter",
        content_type="post",
        client_id="demo_client",
        media_urls=["https://example.com/launch-banner.jpg"]
    )
    
    result = await agent.post_content(twitter_post)
    
    # Example 2: Post to multiple platforms at once
    multi_platform_posts = [
        ContentPost(
            content="Exciting news! Our new feature is live 🎉",
            platform="linkedin",
            content_type="post",
            client_id="demo_client"
        ),
        ContentPost(
            content="New feature alert! Check out what we've built 👀",
            platform="twitter",
            content_type="post",
            client_id="demo_client"
        ),
        ContentPost(
            content="Watch our latest tutorial on automating your workflow",
            platform="tiktok",
            content_type="video",
            client_id="demo_client",
            media_urls=["https://example.com/tutorial-video.mp4"]
        )
    ]
    
    results = await agent.post_to_multiple_platforms(multi_platform_posts)
    
    # Check manual queue
    manual_queue = agent.get_manual_queue()
    if manual_queue:
        print(f"\n📋 Manual Queue ({len(manual_queue)} items):")
        for item in manual_queue:
            print(f"   • {item['platform']}: {item['content'][:50]}...")
    
    # Get posting history
    history = agent.get_posting_history()
    print(f"\n📜 Total posts attempted: {len(history)}")


if __name__ == "__main__":
    asyncio.run(example_usage())
