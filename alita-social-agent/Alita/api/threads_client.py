"""
Threads API Client
==================
Integration with Threads (Meta's Twitter competitor) via Late API.

FEATURES:
- Create text posts
- Create posts with media (images, videos)
- Schedule posts
- Get post analytics
- Reply to posts (when API available)
- Profile management

REQUIREMENTS:
- Late API account (https://getlate.dev)
- LATE_API_KEY in .env
- LATE_PROFILE_THREADS_{client_id} in .env
- OR Official Threads API credentials (when available)
"""

import os
import httpx
from typing import Optional, List, Dict, Any
from dataclasses import dataclass
from datetime import datetime
from dotenv import load_dotenv

# Import our existing Late API client
import sys
sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from api.late_client import LateAPIClient, PostRequest, PostResponse

load_dotenv()


@dataclass
class ThreadsPost:
    """Represents a Threads post."""
    post_id: Optional[str] = None
    text: str = ""
    media_urls: Optional[List[str]] = None
    scheduled_time: Optional[str] = None
    created_at: Optional[datetime] = None
    like_count: int = 0
    reply_count: int = 0
    quote_count: int = 0
    status: str = "draft"  # draft, scheduled, published, failed


@dataclass
class ThreadsProfile:
    """Threads user profile."""
    user_id: str
    username: str
    display_name: Optional[str] = None
    bio: Optional[str] = None
    profile_picture_url: Optional[str] = None
    follower_count: int = 0
    following_count: int = 0
    post_count: int = 0


class ThreadsClient:
    """
    Client for Threads API (via Late API).
    
    Usage:
        client = ThreadsClient(client_id="demo_client")
        result = await client.create_post(text="Hello Threads! 🧵")
    """
    
    def __init__(
        self,
        client_id: str,
        late_api_key: Optional[str] = None,
        profile_id: Optional[str] = None
    ):
        """
        Initialize Threads client.
        
        Args:
            client_id: Client identifier (e.g., "demo_client")
            late_api_key: Late API key (defaults to env LATE_API_KEY)
            profile_id: Threads profile ID (defaults to env LATE_PROFILE_THREADS_{client_id})
        """
        self.client_id = client_id
        self.late_api_key = late_api_key or os.getenv("LATE_API_KEY")
        self.profile_id = profile_id or os.getenv(f"LATE_PROFILE_THREADS_{client_id}")
        
        if not self.late_api_key:
            raise ValueError("LATE_API_KEY not found in environment")
        if not self.profile_id:
            raise ValueError(
                f"LATE_PROFILE_THREADS_{client_id} not found in environment. "
                f"Please add your Threads profile ID to .env file. "
                f"Go to https://late.so/workspace and connect your Threads account to get your profile ID."
            )
        
        # Initialize Late API client
        self.late_client = LateAPIClient(api_key=self.late_api_key)
    
    # =========================================================================
    # POST MANAGEMENT
    # =========================================================================
    
    async def create_post(
        self,
        text: str,
        media_urls: Optional[List[str]] = None,
        scheduled_time: Optional[str] = None
    ) -> ThreadsPost:
        """
        Create a Threads post (publish immediately or schedule).
        
        Args:
            text: Post text (up to 500 characters)
            media_urls: Optional list of media URLs (images/videos)
            scheduled_time: ISO format datetime for scheduling (optional)
        
        Returns:
            ThreadsPost object with post ID and status
        """
        # Validate text length
        if len(text) > 500:
            raise ValueError("Threads posts must be 500 characters or less")
        
        # Create post request
        post_request = PostRequest(
            platform="threads",
            profile_id=self.profile_id,
            content=text,
            media_urls=media_urls,
            scheduled_time=scheduled_time
        )
        
        # Send via Late API
        response = await self.late_client.post_to_platform(post_request)
        
        # Convert to ThreadsPost
        return ThreadsPost(
            post_id=response.post_id if response.success else None,
            text=text,
            media_urls=media_urls,
            scheduled_time=scheduled_time,
            created_at=datetime.now() if response.success else None,
            status="published" if response.success else "failed"
        )
    
    async def create_text_post(self, text: str) -> ThreadsPost:
        """
        Create a simple text post.
        
        Args:
            text: Post content
        
        Returns:
            ThreadsPost object
        """
        return await self.create_post(text=text)
    
    async def create_media_post(
        self,
        text: str,
        media_urls: List[str]
    ) -> ThreadsPost:
        """
        Create a post with media (images/videos).
        
        Args:
            text: Post caption
            media_urls: List of media URLs
        
        Returns:
            ThreadsPost object
        """
        return await self.create_post(text=text, media_urls=media_urls)
    
    async def schedule_post(
        self,
        text: str,
        scheduled_time: datetime,
        media_urls: Optional[List[str]] = None
    ) -> ThreadsPost:
        """
        Schedule a post for future publishing.
        
        Args:
            text: Post content
            scheduled_time: When to publish
            media_urls: Optional media
        
        Returns:
            ThreadsPost object
        """
        return await self.create_post(
            text=text,
            media_urls=media_urls,
            scheduled_time=scheduled_time.isoformat()
        )
    
    # =========================================================================
    # THREADING (REPLY TO OWN POST)
    # =========================================================================
    
    async def create_thread(
        self,
        posts: List[str],
        delay_seconds: int = 2
    ) -> List[ThreadsPost]:
        """
        Create a thread (series of connected posts).
        
        Args:
            posts: List of post texts
            delay_seconds: Delay between posts
        
        Returns:
            List of ThreadsPost objects
        """
        import asyncio
        
        results = []
        for i, text in enumerate(posts):
            post = await self.create_post(text=text)
            results.append(post)
            
            # Add delay between posts (except last one)
            if i < len(posts) - 1:
                await asyncio.sleep(delay_seconds)
        
        return results
    
    # =========================================================================
    # POST HISTORY
    # =========================================================================
    
    async def get_recent_posts(self, limit: int = 20) -> List[ThreadsPost]:
        """
        Get recent posts from Threads account via Late API.
        
        Args:
            limit: Maximum number of posts to retrieve
        
        Returns:
            List of ThreadsPost objects
        """
        try:
            # Late API: GET /v1/posts?platform=threads&status=published
            endpoint = f"{self.late_client.base_url}/posts"
            params = {
                "platform": "threads",
                "status": "published",
                "limit": limit
            }
            
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    endpoint,
                    headers=self.late_client._get_headers(),
                    params=params
                )
                response.raise_for_status()
                data = response.json()
                
                posts = []
                for post_data in data.get("posts", []):
                    # Parse timestamps
                    created_at = None
                    for time_field in ["createdAt", "created_at", "scheduledFor"]:
                        if time_field in post_data and post_data[time_field]:
                            try:
                                ts = post_data[time_field]
                                if ts.endswith("Z"):
                                    ts = ts[:-1] + "+00:00"
                                created_at = datetime.fromisoformat(ts)
                            except:
                                pass
                            break
                    
                    # Extract engagement from platforms array or analytics
                    like_count = 0
                    reply_count = 0
                    quote_count = 0
                    
                    # Get platform-specific post URL
                    platforms = post_data.get("platforms", [])
                    platform_url = None
                    for p in platforms:
                        if p.get("platform") == "threads":
                            platform_url = p.get("platformPostUrl")
                    
                    posts.append(ThreadsPost(
                        post_id=post_data.get("_id"),
                        text=post_data.get("content", ""),
                        created_at=created_at,
                        like_count=like_count,
                        reply_count=reply_count,
                        quote_count=quote_count,
                        status="published"
                    ))
                
                return posts
        except Exception as e:
            print(f"❌ Error getting Threads posts: {e}")
            return []
    
    # =========================================================================
    # ANALYTICS & INSIGHTS
    # =========================================================================
    
    async def get_post_insights(self, post_id: str) -> Dict[str, Any]:
        """
        Get analytics for a specific post.
        
        Args:
            post_id: Post ID
        
        Returns:
            Analytics data (likes, replies, quotes, views)
        
        Note: This uses Late API's analytics endpoint.
        """
        try:
            return await self.late_client.get_analytics(post_id)
        except Exception as e:
            return {"error": str(e)}
    
    async def get_account_analytics(
        self,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Get account-level analytics.
        
        Args:
            start_date: Start date (ISO format)
            end_date: End date (ISO format)
        
        Returns:
            Account analytics
        """
        try:
            endpoint = f"{self.late_client.base_url}/analytics/account/{self.profile_id}"
            params = {}
            if start_date:
                params["start_date"] = start_date
            if end_date:
                params["end_date"] = end_date
            
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    endpoint,
                    headers=self.late_client._get_headers(),
                    params=params
                )
                response.raise_for_status()
                return response.json()
        except Exception as e:
            return {"error": str(e)}
    
    # =========================================================================
    # COMMENT MANAGEMENT
    # =========================================================================
    
    async def get_post_comments(self, post_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        """
        Get comments on a Threads post via Late API inbox.
        
        Args:
            post_id: Post ID
            limit: Maximum comments to retrieve
        
        Returns:
            List of comment dictionaries
        """
        try:
            # Late API: GET /v1/inbox/comments/{postId}?accountId={accountId}
            endpoint = f"{self.late_client.base_url}/inbox/comments/{post_id}"
            params = {
                "accountId": self.profile_id,
                "limit": limit
            }
            
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    endpoint,
                    headers=self.late_client._get_headers(),
                    params=params
                )
                
                if response.status_code == 403:
                    # Inbox addon not available
                    print("⚠️ Late API Inbox addon required for comments")
                    return []
                
                response.raise_for_status()
                data = response.json()
                return data.get("comments", [])
        except Exception as e:
            print(f"⚠️ Comments not available: {e}")
            return []
    
    async def reply_to_comment(self, comment_id: str, text: str, post_id: str = "") -> Dict[str, Any]:
        """
        Reply to a comment on a Threads post via Late API.
        
        Args:
            comment_id: Comment ID to reply to
            text: Reply text
            post_id: Post ID the comment belongs to
        
        Returns:
            Response data
        """
        try:
            # Late API: POST /v1/inbox/comments/{postId}
            endpoint = f"{self.late_client.base_url}/inbox/comments/{post_id}"
            payload = {
                "accountId": self.profile_id,
                "message": text,
                "parentCommentId": comment_id
            }
            
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    endpoint,
                    headers=self.late_client._get_headers(),
                    json=payload
                )
                
                if response.status_code == 403:
                    return {"error": "Late API Inbox addon required for replying to comments"}
                
                response.raise_for_status()
                return response.json()
        except Exception as e:
            return {"error": str(e)}
    
    async def delete_comment(self, comment_id: str) -> Dict[str, Any]:
        """
        Delete a comment (only your own comments).
        
        Args:
            comment_id: Comment ID to delete
        
        Returns:
            Response data
        """
        try:
            endpoint = f"{self.late_client.base_url}/comments/{comment_id}"
            
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.delete(
                    endpoint,
                    headers=self.late_client._get_headers()
                )
                response.raise_for_status()
                return {"success": True}
        except Exception as e:
            return {"error": str(e)}
    
    # =========================================================================
    # PROFILE MANAGEMENT
    # =========================================================================
    
    async def get_profile(self) -> Optional[ThreadsProfile]:
        """
        Get Threads profile information.
        
        Returns:
            ThreadsProfile object or None
        """
        # Via Late API profiles endpoint
        try:
            profiles = await self.late_client.get_profiles(platform="threads")
            
            if profiles and "data" in profiles:
                for profile in profiles["data"]:
                    if profile.get("id") == self.profile_id:
                        return ThreadsProfile(
                            user_id=profile.get("id"),
                            username=profile.get("username", ""),
                            display_name=profile.get("name"),
                            bio=profile.get("bio"),
                            profile_picture_url=profile.get("profile_picture_url"),
                            follower_count=profile.get("followers_count", 0),
                            following_count=profile.get("following_count", 0),
                            post_count=profile.get("media_count", 0)
                        )
            return None
        except Exception as e:
            print(f"Error getting profile: {e}")
            return None
    
    # =========================================================================
    # CONTENT FORMATTING
    # =========================================================================
    
    @staticmethod
    def format_for_threads(content: str, max_length: int = 500) -> str:
        """
        Format content for Threads (truncate if needed, add hashtags).
        
        Args:
            content: Original content
            max_length: Maximum character length
        
        Returns:
            Formatted content
        """
        if len(content) <= max_length:
            return content
        
        # Truncate and add ellipsis
        truncated = content[:max_length-4] + "..."
        return truncated
    
    @staticmethod
    def extract_hashtags(text: str) -> List[str]:
        """Extract hashtags from text."""
        import re
        return re.findall(r'#\w+', text)
    
    @staticmethod
    def add_hashtags(text: str, hashtags: List[str]) -> str:
        """Add hashtags to text (if room available)."""
        hashtag_str = " ".join(hashtags)
        combined = f"{text}\n\n{hashtag_str}"
        
        if len(combined) <= 500:
            return combined
        else:
            return text  # Can't fit hashtags, return original


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

async def post_to_threads(
    client_id: str,
    text: str,
    media_urls: Optional[List[str]] = None
) -> ThreadsPost:
    """Quick function to post to Threads."""
    client = ThreadsClient(client_id=client_id)
    return await client.create_post(text, media_urls)


async def schedule_threads_post(
    client_id: str,
    text: str,
    scheduled_time: datetime,
    media_urls: Optional[List[str]] = None
) -> ThreadsPost:
    """Quick function to schedule a Threads post."""
    client = ThreadsClient(client_id=client_id)
    return await client.schedule_post(text, scheduled_time, media_urls)


# =============================================================================
# EXAMPLE USAGE
# =============================================================================

async def example_usage():
    """Example of how to use the Threads client."""
    
    # Initialize client
    client = ThreadsClient(client_id="demo_client")
    
    # Create a simple text post
    text_post = await client.create_text_post(
        text="Just launched Alita AI's Threads integration! 🧵🚀 #AI #Automation"
    )
    print(f"Text post created: {text_post.post_id}")
    
    # Create a post with media
    media_post = await client.create_media_post(
        text="Check out our new dashboard! 📊",
        media_urls=["https://example.com/dashboard.jpg"]
    )
    print(f"Media post created: {media_post.post_id}")
    
    # Schedule a post for later
    from datetime import timedelta
    future_time = datetime.now() + timedelta(hours=2)
    scheduled = await client.schedule_post(
        text="Scheduled post test ⏰",
        scheduled_time=future_time
    )
    print(f"Post scheduled: {scheduled.post_id}")
    
    # Create a thread (multiple connected posts)
    thread_posts = [
        "1/ Here's why AI automation is changing social media marketing...",
        "2/ Traditional social media management requires hours of manual work daily.",
        "3/ With AI agents, you can automate 80% of repetitive tasks while maintaining authenticity.",
        "4/ That's why we built Alita AI. Learn more at alita.ai 🚀"
    ]
    thread = await client.create_thread(thread_posts)
    print(f"Thread created with {len(thread)} posts")
    
    # Get profile info
    profile = await client.get_profile()
    if profile:
        print(f"Profile: @{profile.username} - {profile.follower_count} followers")
    
    # Get post insights
    if text_post.post_id:
        insights = await client.get_post_insights(text_post.post_id)
        print(f"Post insights: {insights}")


if __name__ == "__main__":
    import asyncio
    asyncio.run(example_usage())
