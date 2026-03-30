"""
Late API Client - Multi-platform posting integration
Supports: TikTok, LinkedIn, Twitter/X, Threads, Reddit, Pinterest, Bluesky
Documentation: https://docs.getlate.dev
"""

import os
import logging
import httpx
import asyncio
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from enum import Enum
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

load_dotenv()


class Platform(Enum):
    """Supported platforms via Late API."""
    TIKTOK = "tiktok"
    LINKEDIN = "linkedin"
    TWITTER = "twitter"
    THREADS = "threads"
    REDDIT = "reddit"
    PINTEREST = "pinterest"
    BLUESKY = "bluesky"


class PostStatus(Enum):
    """Post status states."""
    PENDING = "pending"
    PROCESSING = "processing"
    PUBLISHED = "published"
    FAILED = "failed"
    SCHEDULED = "scheduled"


@dataclass
class PostRequest:
    """Request to post content to a platform."""
    platform: str  # Platform identifier (tiktok, linkedin, twitter, etc.)
    profile_id: str  # Late API profile ID for the specific account
    content: str  # Post content/caption
    media_urls: Optional[List[str]] = None  # URLs to media files
    scheduled_time: Optional[str] = None  # ISO 8601 format for scheduling
    additional_params: Optional[Dict[str, Any]] = None  # Platform-specific parameters


@dataclass
class PostResponse:
    """Response from posting content."""
    success: bool
    post_id: Optional[str] = None
    platform: Optional[str] = None
    status: Optional[str] = None
    error: Optional[str] = None
    raw_response: Optional[Dict] = None


class LateAPIClient:
    """
    Client for Late API - Multi-platform posting service.
    
    Features:
    - Post to TikTok, LinkedIn, Twitter/X, Threads, Reddit, Pinterest, Bluesky
    - Schedule posts for future publishing
    - Check post status and retrieve analytics
    - Manage multiple profiles per platform
    
    Usage:
        client = LateAPIClient(api_key="your_key")
        response = await client.post_to_platform(post_request)
    """
    
    def __init__(self, api_key: Optional[str] = None, base_url: str = "https://getlate.dev/api/v1"):
        """
        Initialize Late API client.
        
        Args:
            api_key: Late API key (defaults to LATE_API_KEY env var)
            base_url: Late API base URL
        """
        self.api_key = api_key or os.getenv("LATE_API_KEY")
        if not self.api_key:
            raise ValueError("Late API key is required. Set LATE_API_KEY env var or pass api_key parameter.")
        
        self.base_url = base_url.rstrip('/')
        self.timeout = 120.0  # Videos can take time to upload from URL
        
    def _get_headers(self) -> Dict[str, str]:
        """Get request headers with authentication."""
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "User-Agent": "Alita-AI-Agent/1.0"
        }
    
    VIDEO_EXTENSIONS = {'.mp4', '.mov', '.avi', '.wmv', '.flv', '.3gp', '.webm', '.mkv'}

    @staticmethod
    def _detect_media_type(url: str) -> str:
        """Detect if a media URL is video or image based on extension."""
        from pathlib import PurePosixPath
        try:
            path = PurePosixPath(url.split('?')[0])
            if path.suffix.lower() in LateAPIClient.VIDEO_EXTENSIONS:
                return "video"
        except Exception:
            pass
        return "image"

    async def post_to_platform(self, request: PostRequest) -> PostResponse:
        """
        Post content to a platform via Late API (Zernio).
        
        Builds the correct payload per https://docs.zernio.com/posts/create-post:
        - mediaItems (not mediaUrls) with {type, url} objects
        - YouTube: platformSpecificData with title + visibility
        - TikTok: tiktokSettings with consent flags at root level
        """
        endpoint = f"{self.base_url}/posts"

        # --- Platform entry -----------------------------------------------
        platform_entry: Dict[str, Any] = {
            "platform": request.platform,
            "accountId": request.profile_id,
        }

        # YouTube requires title + visibility inside platformSpecificData
        if request.platform == "youtube":
            title = (request.content or "")[:100].split('\n')[0] or "Untitled Video"
            platform_entry["platformSpecificData"] = {
                "title": title,
                "visibility": "public",
            }

        # --- Core payload --------------------------------------------------
        payload: Dict[str, Any] = {
            "content": request.content or "",
            "platforms": [platform_entry],
            "publishNow": True,
        }

        # --- Media items ---------------------------------------------------
        if request.media_urls:
            payload["mediaItems"] = [
                {"type": self._detect_media_type(url), "url": url}
                for url in request.media_urls
            ]

        # --- TikTok consent flags (required, goes at root level) -----------
        if request.platform == "tiktok":
            payload["tiktokSettings"] = {
                "privacy_level": "PUBLIC_TO_EVERYONE",
                "allow_comment": True,
                "allow_duet": True,
                "allow_stitch": True,
                "content_preview_confirmed": True,
                "express_consent_given": True,
                "video_made_with_ai": True,
            }

        # --- Scheduling ----------------------------------------------------
        if request.scheduled_time:
            payload["scheduledFor"] = request.scheduled_time
            payload["publishNow"] = False

        # --- Merge caller-provided overrides (PostingAgent, etc.) ----------
        if request.additional_params:
            payload.update(request.additional_params)

        logger.info(f"[LateAPI] POST {endpoint} platform={request.platform} "
                     f"profile={request.profile_id} mediaItems={payload.get('mediaItems')}")

        # --- TikTok privacy-level fallback list ---
        _tiktok_privacy_levels = ["PUBLIC_TO_EVERYONE", "FOLLOWER_OF_CREATOR", "SELF_ONLY"]

        async def _do_post(p: Dict[str, Any]) -> PostResponse:
            """Execute a single POST attempt and return a PostResponse."""
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    endpoint,
                    headers=self._get_headers(),
                    json=p
                )
                response.raise_for_status()
                data = response.json()
                logger.info(f"[LateAPI] Success: {data}")
                return PostResponse(
                    success=True,
                    post_id=data.get("id") or data.get("post_id"),
                    platform=request.platform,
                    status=data.get("status", "published"),
                    raw_response=data
                )

        try:
            return await _do_post(payload)
        except httpx.HTTPStatusError as e:
            error_detail = "Unknown error"
            raw_body = ""
            try:
                raw_body = e.response.text[:500]
                error_data = e.response.json()
                error_detail = error_data.get("error", error_data.get("message", str(e)))
            except Exception:
                error_detail = raw_body or str(e)
            logger.error(f"[LateAPI] {e.response.status_code} error for {request.platform}: {error_detail}")
            logger.error(f"[LateAPI] Full response body: {raw_body}")
            logger.error(f"[LateAPI] Payload sent: {payload}")

            # --- TikTok: retry with alternative privacy levels on 400 ---
            if (request.platform == "tiktok"
                    and e.response.status_code == 400
                    and "privacy" in error_detail.lower()):
                current_level = payload.get("tiktokSettings", {}).get("privacy_level", "")
                for alt_level in _tiktok_privacy_levels:
                    if alt_level == current_level:
                        continue
                    logger.info(f"[LateAPI] TikTok privacy retry: {current_level} → {alt_level}")
                    payload["tiktokSettings"]["privacy_level"] = alt_level
                    try:
                        return await _do_post(payload)
                    except httpx.HTTPStatusError as retry_err:
                        logger.warning(f"[LateAPI] TikTok privacy retry {alt_level} also failed: "
                                       f"{retry_err.response.status_code}")
                        continue
                    except Exception as retry_err:
                        logger.warning(f"[LateAPI] TikTok privacy retry {alt_level} error: {retry_err}")
                        continue

            return PostResponse(
                success=False,
                platform=request.platform,
                error=f"HTTP {e.response.status_code}: {error_detail}"
            )
        except Exception as e:
            logger.error(f"[LateAPI] Request failed for {request.platform}: {e}")
            return PostResponse(
                success=False,
                platform=request.platform,
                error=f"Request failed: {str(e)}"
            )
    
    async def get_post_status(self, post_id: str) -> PostResponse:
        """
        Get the status of a posted or scheduled post.
        
        Args:
            post_id: The Late API post ID
            
        Returns:
            PostResponse with current status
        """
        endpoint = f"{self.base_url}/posts/{post_id}"
        
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(
                    endpoint,
                    headers=self._get_headers()
                )
                response.raise_for_status()
                
                data = response.json()
                
                return PostResponse(
                    success=True,
                    post_id=post_id,
                    platform=data.get("platform"),
                    status=data.get("status"),
                    raw_response=data
                )
                
        except httpx.HTTPStatusError as e:
            return PostResponse(
                success=False,
                post_id=post_id,
                error=f"HTTP {e.response.status_code}: {str(e)}"
            )
            
        except Exception as e:
            return PostResponse(
                success=False,
                post_id=post_id,
                error=f"Request failed: {str(e)}"
            )
    
    async def get_profiles(self, platform: Optional[str] = None) -> Dict[str, Any]:
        """
        Get all connected profiles for the account.
        
        Args:
            platform: Optional filter by platform (tiktok, linkedin, twitter, etc.)
            
        Returns:
            Dict with profiles list
        """
        endpoint = f"{self.base_url}/profiles"
        
        params = {}
        if platform:
            params["platform"] = platform
        
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(
                    endpoint,
                    headers=self._get_headers(),
                    params=params
                )
                response.raise_for_status()
                
                return response.json()
                
        except Exception as e:
            return {"error": str(e), "profiles": []}
    
    async def delete_scheduled_post(self, post_id: str) -> bool:
        """
        Delete a scheduled post before it's published.
        
        Args:
            post_id: The Late API post ID
            
        Returns:
            True if deleted successfully
        """
        endpoint = f"{self.base_url}/posts/{post_id}"
        
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.delete(
                    endpoint,
                    headers=self._get_headers()
                )
                response.raise_for_status()
                return True
                
        except Exception as e:
            return False
    
    async def get_analytics(self, post_id: str) -> Dict[str, Any]:
        """
        Get analytics/performance data for a published post.
        
        Args:
            post_id: The Late API post ID
            
        Returns:
            Dict with analytics data (views, likes, comments, etc.)
        """
        endpoint = f"{self.base_url}/posts/{post_id}/analytics"
        
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(
                    endpoint,
                    headers=self._get_headers()
                )
                response.raise_for_status()
                
                return response.json()
                
        except Exception as e:
            return {"error": str(e)}


# Convenience functions for common use cases

async def post_to_tiktok(client: LateAPIClient, profile_id: str, caption: str, 
                        video_url: str, **kwargs) -> PostResponse:
    """Post a video to TikTok."""
    request = PostRequest(
        platform="tiktok",
        profile_id=profile_id,
        content=caption,
        media_urls=[video_url],
        additional_params=kwargs
    )
    return await client.post_to_platform(request)


async def post_to_linkedin(client: LateAPIClient, profile_id: str, content: str,
                          media_urls: Optional[List[str]] = None, **kwargs) -> PostResponse:
    """Post to LinkedIn (personal profile or company page)."""
    request = PostRequest(
        platform="linkedin",
        profile_id=profile_id,
        content=content,
        media_urls=media_urls,
        additional_params=kwargs
    )
    return await client.post_to_platform(request)


async def post_to_twitter(client: LateAPIClient, profile_id: str, tweet: str,
                         media_urls: Optional[List[str]] = None, **kwargs) -> PostResponse:
    """Post a tweet to Twitter/X."""
    request = PostRequest(
        platform="twitter",
        profile_id=profile_id,
        content=tweet,
        media_urls=media_urls,
        additional_params=kwargs
    )
    return await client.post_to_platform(request)


async def post_to_threads(client: LateAPIClient, profile_id: str, content: str,
                         media_urls: Optional[List[str]] = None, **kwargs) -> PostResponse:
    """Post to Threads (Meta's Twitter alternative)."""
    request = PostRequest(
        platform="threads",
        profile_id=profile_id,
        content=content,
        media_urls=media_urls,
        additional_params=kwargs
    )
    return await client.post_to_platform(request)


# Example usage
async def example_usage():
    """Example of how to use the Late API client."""
    
    # Initialize client (reads from LATE_API_KEY env var)
    client = LateAPIClient()
    
    # Get connected profiles
    profiles = await client.get_profiles()
    
    # Post to Twitter
    twitter_response = await post_to_twitter(
        client=client,
        profile_id="twitter_profile_123",
        tweet="Just shipped a new feature! 🚀 #AI #Automation",
        media_urls=["https://example.com/image.jpg"]
    )
    
    if twitter_response.success:
        # Check status later
        status = await client.get_post_status(twitter_response.post_id)
    
    # Schedule a LinkedIn post for later
    linkedin_response = await post_to_linkedin(
        client=client,
        profile_id="linkedin_profile_456",
        content="Excited to share our latest insights on AI automation...",
        media_urls=["https://example.com/article-banner.jpg"],
        scheduled_at="2026-01-30T10:00:00Z"
    )


if __name__ == "__main__":
    # Run example
    asyncio.run(example_usage())
