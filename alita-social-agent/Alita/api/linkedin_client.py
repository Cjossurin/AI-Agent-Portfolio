"""
LinkedIn API Client
==================
Post updates, articles, and manage connections on LinkedIn via Late API.

FEATURES:
- Post text updates
- Post articles with rich media
- Post images and videos
- Schedule posts
- Get profile info
- Get post analytics
- Connection management (when API allows)

REQUIREMENTS:
- Late API account (https://getlate.dev)
- LATE_API_KEY in .env
- LATE_PROFILE_LINKEDIN_{client_id} in .env
"""

import os
import httpx
from typing import Optional, List, Dict, Any
from dataclasses import dataclass
from datetime import datetime
from dotenv import load_dotenv

# Import Late API client
import sys
sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from api.late_client import LateAPIClient, PostRequest, PostResponse

load_dotenv()


@dataclass
class LinkedInPost:
    """Represents a LinkedIn post."""
    post_id: Optional[str] = None
    text: str = ""
    media_urls: Optional[List[str]] = None
    article_url: Optional[str] = None
    scheduled_time: Optional[str] = None
    created_at: Optional[datetime] = None
    like_count: int = 0
    comment_count: int = 0
    share_count: int = 0
    impression_count: int = 0
    status: str = "draft"  # draft, scheduled, published, failed


@dataclass
class LinkedInProfile:
    """LinkedIn user profile."""
    user_id: str
    name: str
    headline: Optional[str] = None
    summary: Optional[str] = None
    profile_picture_url: Optional[str] = None
    connection_count: int = 0
    follower_count: int = 0


class LinkedInClient:
    """
    Client for LinkedIn API (via Late API).
    
    Usage:
        client = LinkedInClient(client_id="demo_client")
        result = await client.create_post(text="New article on AI trends! 🚀")
    """
    
    def __init__(
        self,
        client_id: str,
        late_api_key: Optional[str] = None,
        profile_id: Optional[str] = None
    ):
        """
        Initialize LinkedIn client.
        
        Args:
            client_id: Client identifier (e.g., "demo_client")
            late_api_key: Late API key (defaults to env LATE_API_KEY)
            profile_id: LinkedIn profile ID (defaults to env LATE_PROFILE_LINKEDIN_{client_id})
        """
        self.client_id = client_id
        self.late_api_key = late_api_key or os.getenv("LATE_API_KEY")
        self.profile_id = profile_id or os.getenv(f"LATE_PROFILE_LINKEDIN_{client_id}")
        
        if not self.late_api_key:
            raise ValueError("LATE_API_KEY not found in environment")
        if not self.profile_id:
            raise ValueError(f"LATE_PROFILE_LINKEDIN_{client_id} not found in environment")
        
        # Initialize Late API client
        self.late_client = LateAPIClient(api_key=self.late_api_key)
    
    # =========================================================================
    # POST MANAGEMENT
    # =========================================================================
    
    async def create_post(
        self,
        text: str,
        media_urls: Optional[List[str]] = None,
        article_url: Optional[str] = None,
        scheduled_time: Optional[str] = None
    ) -> LinkedInPost:
        """
        Create a LinkedIn post.
        
        Args:
            text: Post text (up to 3000 characters for LinkedIn)
            media_urls: Optional list of image/video URLs
            article_url: Optional article/link to share
            scheduled_time: ISO format datetime for scheduling (optional)
        
        Returns:
            LinkedInPost object with post ID and status
        """
        # Validate text length
        if len(text) > 3000:
            raise ValueError("LinkedIn posts must be 3000 characters or less")
        
        # Create post request
        post_request = PostRequest(
            platform="linkedin",
            profile_id=self.profile_id,
            content=text,
            media_urls=media_urls,
            scheduled_time=scheduled_time
        )
        
        # Send via Late API
        response = await self.late_client.post_to_platform(post_request)
        
        # Convert to LinkedInPost
        return LinkedInPost(
            post_id=response.post_id if response.success else None,
            text=text,
            media_urls=media_urls,
            article_url=article_url,
            scheduled_time=scheduled_time,
            created_at=datetime.now() if response.success else None,
            status="published" if response.success else "failed"
        )
    
    async def create_text_post(self, text: str) -> LinkedInPost:
        """
        Create a simple text post.
        
        Args:
            text: Post content
        
        Returns:
            LinkedInPost object
        """
        return await self.create_post(text=text)
    
    async def create_image_post(
        self,
        text: str,
        image_urls: List[str]
    ) -> LinkedInPost:
        """
        Create a post with images (up to 9).
        
        Args:
            text: Post caption
            image_urls: List of image URLs (max 9 for LinkedIn)
        
        Returns:
            LinkedInPost object
        """
        if len(image_urls) > 9:
            raise ValueError("LinkedIn allows maximum 9 images per post")
        
        return await self.create_post(text=text, media_urls=image_urls)
    
    async def create_video_post(
        self,
        text: str,
        video_url: str
    ) -> LinkedInPost:
        """
        Create a post with video.
        
        Args:
            text: Video caption
            video_url: Video URL
        
        Returns:
            LinkedInPost object
        """
        return await self.create_post(text=text, media_urls=[video_url])
    
    async def create_article_post(
        self,
        text: str,
        article_url: str
    ) -> LinkedInPost:
        """
        Share an article/link.
        
        Args:
            text: Commentary on the article
            article_url: Article URL
        
        Returns:
            LinkedInPost object
        """
        # Include article URL in text for Late API
        full_text = f"{text}\n\n{article_url}"
        return await self.create_post(text=full_text, article_url=article_url)
    
    async def schedule_post(
        self,
        text: str,
        scheduled_time: datetime,
        media_urls: Optional[List[str]] = None
    ) -> LinkedInPost:
        """
        Schedule a post for future publishing.
        
        Args:
            text: Post content
            scheduled_time: When to publish
            media_urls: Optional media
        
        Returns:
            LinkedInPost object
        """
        return await self.create_post(
            text=text,
            media_urls=media_urls,
            scheduled_time=scheduled_time.isoformat()
        )
    
    # =========================================================================
    # POST HISTORY
    # =========================================================================
    
    async def get_recent_posts(self, limit: int = 20) -> List[LinkedInPost]:
        """
        Get recent posts from LinkedIn account.
        
        Args:
            limit: Maximum number of posts to retrieve
        
        Returns:
            List of LinkedInPost objects
        """
        try:
            endpoint = f"{self.late_client.base_url}/posts"
            params = {
                "profile_id": self.profile_id,
                "limit": limit,
                "platform": "linkedin"
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
                for post_data in data.get("data", []):
                    posts.append(LinkedInPost(
                        post_id=post_data.get("id"),
                        text=post_data.get("text", ""),
                        created_at=datetime.fromisoformat(post_data["created_at"]) if "created_at" in post_data else None,
                        like_count=post_data.get("like_count", 0),
                        comment_count=post_data.get("comment_count", 0),
                        share_count=post_data.get("share_count", 0),
                        impression_count=post_data.get("impression_count", 0),
                        status="published"
                    ))
                
                return posts
        except Exception as e:
            print(f"Error getting posts: {e}")
            return []
    
    # =========================================================================
    # ANALYTICS & INSIGHTS
    # =========================================================================
    
    async def get_post_analytics(self, post_id: str) -> Dict[str, Any]:
        """
        Get analytics for a specific post.
        
        Args:
            post_id: Post ID
        
        Returns:
            Analytics data
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
    # PROFILE MANAGEMENT
    # =========================================================================
    
    async def get_profile(self) -> Optional[LinkedInProfile]:
        """
        Get LinkedIn profile information.
        
        Returns:
            LinkedInProfile object or None
        """
        try:
            profiles = await self.late_client.get_profiles(platform="linkedin")
            
            if profiles and "data" in profiles:
                for profile in profiles["data"]:
                    if profile.get("id") == self.profile_id:
                        return LinkedInProfile(
                            user_id=profile.get("id"),
                            name=profile.get("name", ""),
                            headline=profile.get("headline"),
                            summary=profile.get("summary"),
                            profile_picture_url=profile.get("profile_picture_url"),
                            connection_count=profile.get("connection_count", 0),
                            follower_count=profile.get("follower_count", 0)
                        )
            return None
        except Exception as e:
            print(f"Error getting profile: {e}")
            return None
    
    # =========================================================================
    # CONTENT FORMATTING
    # =========================================================================
    
    @staticmethod
    def format_for_linkedin(content: str, max_length: int = 3000) -> str:
        """
        Format content for LinkedIn (professional tone, truncate if needed).
        
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
    def add_hashtags(text: str, hashtags: List[str]) -> str:
        """Add hashtags to text (LinkedIn supports many hashtags)."""
        hashtag_str = " ".join(f"#{tag.strip('#')}" for tag in hashtags)
        combined = f"{text}\n\n{hashtag_str}"
        
        if len(combined) <= 3000:
            return combined
        else:
            return text  # Can't fit hashtags, return original


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

async def post_to_linkedin(
    client_id: str,
    text: str,
    media_urls: Optional[List[str]] = None
) -> LinkedInPost:
    """Quick function to post to LinkedIn."""
    client = LinkedInClient(client_id=client_id)
    return await client.create_post(text, media_urls)


async def schedule_linkedin_post(
    client_id: str,
    text: str,
    scheduled_time: datetime,
    media_urls: Optional[List[str]] = None
) -> LinkedInPost:
    """Quick function to schedule a LinkedIn post."""
    client = LinkedInClient(client_id=client_id)
    return await client.schedule_post(text, scheduled_time, media_urls)


# =============================================================================
# EXAMPLE USAGE
# =============================================================================

async def example_usage():
    """Example of how to use the LinkedIn client."""
    
    # Initialize client
    client = LinkedInClient(client_id="demo_client")
    
    # Create a text post
    text_post = await client.create_text_post(
        text="Excited to share insights on AI automation in B2B marketing! 🚀 #AI #Marketing #B2B"
    )
    print(f"Text post created: {text_post.post_id}")
    
    # Create a post with image
    image_post = await client.create_image_post(
        text="Check out our latest case study results! 📊",
        image_urls=["https://example.com/chart.jpg"]
    )
    print(f"Image post created: {image_post.post_id}")
    
    # Share an article
    article_post = await client.create_article_post(
        text="Great read on the future of AI in business:",
        article_url="https://example.com/article"
    )
    print(f"Article shared: {article_post.post_id}")
    
    # Schedule a post
    from datetime import timedelta
    future_time = datetime.now() + timedelta(days=1)
    scheduled = await client.schedule_post(
        text="Weekly tips coming your way! 💡",
        scheduled_time=future_time
    )
    print(f"Post scheduled: {scheduled.post_id}")
    
    # Get profile info
    profile = await client.get_profile()
    if profile:
        print(f"Profile: {profile.name} - {profile.connection_count} connections")
    
    # Get recent posts
    posts = await client.get_recent_posts(limit=10)
    print(f"Found {len(posts)} recent posts")
    
    # Get post analytics
    if text_post.post_id:
        analytics = await client.get_post_analytics(text_post.post_id)
        print(f"Post analytics: {analytics}")


if __name__ == "__main__":
    import asyncio
    asyncio.run(example_usage())
