"""
TikTok API Client - Full integration for video posting, analytics, and engagement
Documentation: https://developers.tiktok.com/doc/
Note: For public posting, use Late API integration. This client focuses on analytics and profile management.
"""

import os
import httpx
import asyncio
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()


@dataclass
class VideoMetrics:
    """TikTok video metrics."""
    video_id: str
    views: int
    likes: int
    comments: int
    shares: int
    watched_duration: Optional[int] = None


@dataclass
class VideoResponse:
    """Response from video operation."""
    success: bool
    video_id: Optional[str] = None
    upload_url: Optional[str] = None
    error: Optional[str] = None
    raw_response: Optional[Dict] = None


class TikTokClient:
    """
    TikTok API Client - Native integration for analytics and profile management.
    
    Features:
    - Get user profile information
    - Retrieve video analytics
    - Get video list for authenticated user
    - Access follower count and engagement metrics
    - Retrieve comments and engagement data
    - Get trending sounds and hashtags
    
    For public video posting, this client integrates with Late API (getlate.dev).
    
    Requires:
    - TIKTOK_ACCESS_TOKEN: OAuth access token
    - TIKTOK_CLIENT_ID: App ID
    - TIKTOK_CLIENT_SECRET: App secret
    - TIKTOK_USER_ID: User ID (from OAuth flow)
    
    Usage:
        client = TikTokClient()
        profile = await client.get_user_profile()
        videos = await client.get_user_videos()
    """
    
    def __init__(self):
        """Initialize TikTok API client with credentials."""
        self.access_token = os.getenv("TIKTOK_ACCESS_TOKEN")
        self.client_id = os.getenv("TIKTOK_CLIENT_ID")
        self.client_secret = os.getenv("TIKTOK_CLIENT_SECRET")
        self.user_id = os.getenv("TIKTOK_USER_ID")
        
        self.base_url = "https://open.tiktokapis.com/v1"
        self.timeout = 30.0
        
    def _get_headers(self) -> Dict[str, str]:
        """Get request headers with Bearer token authentication."""
        return {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
            "User-Agent": "Alita-AI-Agent/1.0"
        }
    
    async def get_user_profile(self) -> Dict[str, Any]:
        """
        Get authenticated user's TikTok profile information.
        
        Returns:
            User profile data (username, follower count, bio, etc.)
        """
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(
                    f"{self.base_url}/user/info",
                    params={
                        "fields": "open_id,username,display_name,bio,avatar_large,follower_count,following_count,video_count,heart_count,verified"
                    },
                    headers=self._get_headers()
                )
                
                if response.status_code == 200:
                    data = response.json()
                    if data.get("data"):
                        return data["data"]
                    return {"error": data.get("error", {}).get("message", "Unknown error")}
                else:
                    return {"error": f"Failed to fetch profile: {response.status_code}"}
        except Exception as e:
            return {"error": f"Exception: {str(e)}"}
    
    async def get_user_videos(self, max_results: int = 10) -> Dict[str, Any]:
        """
        Get list of authenticated user's TikTok videos.
        
        Args:
            max_results: Number of videos to retrieve (max 100)
        
        Returns:
            List of videos with IDs and metadata
        """
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(
                    f"{self.base_url}/user/videos",
                    params={
                        "max_count": min(max_results, 100),
                        "fields": "id,create_time,video_description,like_count,comment_count,share_count,view_count,play_duration"
                    },
                    headers=self._get_headers()
                )
                
                if response.status_code == 200:
                    data = response.json()
                    return {
                        "videos": data.get("data", []),
                        "cursor": data.get("cursor"),
                        "has_more": data.get("has_more", False)
                    }
                else:
                    return {"error": f"Failed to fetch videos: {response.status_code}"}
        except Exception as e:
            return {"error": f"Exception: {str(e)}"}
    
    async def get_video_analytics(self, video_id: str) -> Dict[str, Any]:
        """
        Get detailed analytics for a specific TikTok video.
        
        Args:
            video_id: TikTok video ID
        
        Returns:
            Video metrics and analytics
        """
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(
                    f"{self.base_url}/video/query",
                    params={
                        "filters": {"video_id": video_id},
                        "fields": "id,create_time,video_description,like_count,comment_count,share_count,view_count,play_duration"
                    },
                    headers=self._get_headers()
                )
                
                if response.status_code == 200:
                    data = response.json()
                    video = data.get("data", [{}])[0] if data.get("data") else {}
                    return {
                        "video_id": video_id,
                        "views": video.get("view_count", 0),
                        "likes": video.get("like_count", 0),
                        "comments": video.get("comment_count", 0),
                        "shares": video.get("share_count", 0),
                        "created_at": video.get("create_time"),
                        "duration": video.get("play_duration")
                    }
                else:
                    return {"error": f"Failed to fetch analytics: {response.status_code}"}
        except Exception as e:
            return {"error": f"Exception: {str(e)}"}
    
    async def get_video_comments(self, video_id: str, max_results: int = 10) -> Dict[str, Any]:
        """
        Get comments on a TikTok video.
        
        Args:
            video_id: TikTok video ID
            max_results: Number of comments to retrieve
        
        Returns:
            List of comments with metadata
        """
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(
                    f"{self.base_url}/video/{video_id}/comments",
                    params={
                        "max_count": min(max_results, 100),
                        "fields": "id,text,like_count,reply_count,create_time"
                    },
                    headers=self._get_headers()
                )
                
                if response.status_code == 200:
                    data = response.json()
                    return {
                        "comments": data.get("data", []),
                        "cursor": data.get("cursor"),
                        "has_more": data.get("has_more", False)
                    }
                else:
                    return {"error": f"Failed to fetch comments: {response.status_code}"}
        except Exception as e:
            return {"error": f"Exception: {str(e)}"}
    
    async def get_trending_sounds(self, max_results: int = 20) -> Dict[str, Any]:
        """
        Get trending sounds on TikTok.
        
        Args:
            max_results: Number of sounds to retrieve
        
        Returns:
            List of trending sounds
        """
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(
                    f"{self.base_url}/music/trending",
                    params={
                        "max_count": min(max_results, 100),
                        "fields": "id,name,artist,duration,create_time"
                    },
                    headers=self._get_headers()
                )
                
                if response.status_code == 200:
                    data = response.json()
                    return {
                        "sounds": data.get("data", []),
                        "cursor": data.get("cursor")
                    }
                else:
                    return {"error": f"Failed to fetch trending sounds: {response.status_code}"}
        except Exception as e:
            return {"error": f"Exception: {str(e)}"}
    
    async def get_trending_hashtags(self, max_results: int = 20) -> Dict[str, Any]:
        """
        Get trending hashtags on TikTok.
        
        Args:
            max_results: Number of hashtags to retrieve
        
        Returns:
            List of trending hashtags
        """
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(
                    f"{self.base_url}/search/trending",
                    params={
                        "search_type": "hashtag",
                        "max_count": min(max_results, 100),
                        "fields": "id,name,view_count"
                    },
                    headers=self._get_headers()
                )
                
                if response.status_code == 200:
                    data = response.json()
                    return {
                        "hashtags": data.get("data", []),
                        "cursor": data.get("cursor")
                    }
                else:
                    return {"error": f"Failed to fetch trending hashtags: {response.status_code}"}
        except Exception as e:
            return {"error": f"Exception: {str(e)}"}
    
    async def search_videos(self, query: str, max_results: int = 10) -> Dict[str, Any]:
        """
        Search for TikTok videos by keyword.
        
        Args:
            query: Search query
            max_results: Number of videos to retrieve
        
        Returns:
            Search results
        """
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(
                    f"{self.base_url}/search/videos",
                    params={
                        "query": query,
                        "max_count": min(max_results, 100),
                        "fields": "id,video_description,like_count,view_count,create_time"
                    },
                    headers=self._get_headers()
                )
                
                if response.status_code == 200:
                    data = response.json()
                    return {
                        "videos": data.get("data", []),
                        "cursor": data.get("cursor")
                    }
                else:
                    return {"error": f"Failed to search videos: {response.status_code}"}
        except Exception as e:
            return {"error": f"Exception: {str(e)}"}
    
    async def get_follower_insights(self) -> Dict[str, Any]:
        """
        Get follower insights for authenticated user.
        
        Returns:
            Follower demographics and engagement data
        """
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(
                    f"{self.base_url}/user/info",
                    params={
                        "fields": "follower_count,following_count,video_count,heart_count,engagement_rate"
                    },
                    headers=self._get_headers()
                )
                
                if response.status_code == 200:
                    data = response.json()
                    if data.get("data"):
                        return data["data"]
                    return {"error": data.get("error", {}).get("message", "Unknown error")}
                else:
                    return {"error": f"Failed to fetch insights: {response.status_code}"}
        except Exception as e:
            return {"error": f"Exception: {str(e)}"}
