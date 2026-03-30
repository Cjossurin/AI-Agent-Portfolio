"""
YouTube API Client - Full integration for video management and analytics
Documentation: https://developers.google.com/youtube/v3
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
    """YouTube video metrics."""
    video_id: str
    views: int
    likes: int
    comments: int
    shares: Optional[int] = None


@dataclass
class VideoResponse:
    """Response from video operation."""
    success: bool
    video_id: Optional[str] = None
    url: Optional[str] = None
    error: Optional[str] = None
    raw_response: Optional[Dict] = None


class YouTubeClient:
    """
    YouTube API Client - Native integration for video management.
    
    Features:
    - Upload videos (public or unlisted)
    - Get video analytics (views, likes, comments)
    - Manage playlists
    - Get channel information
    - Search YouTube
    - Get trending videos
    - Manage video metadata (title, description, tags)
    
    Requires:
    - YOUTUBE_API_KEY: YouTube Data API key
    - YOUTUBE_CHANNEL_ID: Channel ID
    
    Usage:
        client = YouTubeClient()
        channel = await client.get_channel_info()
        videos = await client.get_channel_videos()
    """
    
    def __init__(self):
        """Initialize YouTube API client with credentials."""
        self.api_key = os.getenv("YOUTUBE_API_KEY")
        self.channel_id = os.getenv("YOUTUBE_CHANNEL_ID")
        self.refresh_token = os.getenv("YOUTUBE_REFRESH_TOKEN")
        
        self.base_url = "https://www.googleapis.com/youtube/v3"
        self.timeout = 30.0
        
    def _get_headers(self) -> Dict[str, str]:
        """Get request headers."""
        return {
            "Content-Type": "application/json",
            "User-Agent": "Alita-AI-Agent/1.0"
        }
    
    async def get_channel_info(self) -> Dict[str, Any]:
        """
        Get channel information.
        
        Returns:
            Channel data (name, description, subscriber count, etc.)
        """
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(
                    f"{self.base_url}/channels",
                    params={
                        "key": self.api_key,
                        "part": "snippet,statistics,contentDetails",
                        "id": self.channel_id,
                        "fields": "items(id,snippet(title,description,thumbnails),statistics(viewCount,subscriberCount,videoCount),contentDetails)"
                    },
                    headers=self._get_headers()
                )
                
                if response.status_code == 200:
                    data = response.json()
                    if data.get("items"):
                        channel = data["items"][0]
                        return {
                            "channel_id": channel.get("id"),
                            "title": channel.get("snippet", {}).get("title"),
                            "description": channel.get("snippet", {}).get("description"),
                            "subscribers": channel.get("statistics", {}).get("subscriberCount"),
                            "views": channel.get("statistics", {}).get("viewCount"),
                            "video_count": channel.get("statistics", {}).get("videoCount")
                        }
                    return {"error": "Channel not found"}
                else:
                    return {"error": f"Failed to fetch channel: {response.status_code}"}
        except Exception as e:
            return {"error": f"Exception: {str(e)}"}
    
    async def get_channel_videos(self, max_results: int = 10) -> Dict[str, Any]:
        """
        Get videos from authenticated channel.
        
        Args:
            max_results: Number of videos to retrieve (max 50)
        
        Returns:
            List of videos with metadata
        """
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                # First get uploads playlist
                response = await client.get(
                    f"{self.base_url}/channels",
                    params={
                        "key": self.api_key,
                        "part": "contentDetails",
                        "id": self.channel_id
                    },
                    headers=self._get_headers()
                )
                
                if response.status_code != 200:
                    return {"error": "Failed to fetch channel details"}
                
                data = response.json()
                if not data.get("items"):
                    return {"error": "Channel not found"}
                
                uploads_id = data["items"][0].get("contentDetails", {}).get("relatedPlaylists", {}).get("uploads")
                
                # Now get videos from uploads playlist
                response = await client.get(
                    f"{self.base_url}/playlistItems",
                    params={
                        "key": self.api_key,
                        "part": "snippet,contentDetails",
                        "playlistId": uploads_id,
                        "maxResults": min(max_results, 50)
                    },
                    headers=self._get_headers()
                )
                
                if response.status_code == 200:
                    data = response.json()
                    videos = []
                    for item in data.get("items", []):
                        videos.append({
                            "video_id": item.get("contentDetails", {}).get("videoId"),
                            "title": item.get("snippet", {}).get("title"),
                            "description": item.get("snippet", {}).get("description"),
                            "published_at": item.get("snippet", {}).get("publishedAt"),
                            "thumbnail": item.get("snippet", {}).get("thumbnails", {}).get("default", {}).get("url")
                        })
                    return {"videos": videos}
                else:
                    return {"error": f"Failed to fetch videos: {response.status_code}"}
        except Exception as e:
            return {"error": f"Exception: {str(e)}"}
    
    async def get_video_analytics(self, video_id: str) -> Dict[str, Any]:
        """
        Get analytics for a specific YouTube video.
        
        Args:
            video_id: YouTube video ID
        
        Returns:
            Video metrics (views, likes, comments, etc.)
        """
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(
                    f"{self.base_url}/videos",
                    params={
                        "key": self.api_key,
                        "part": "snippet,statistics",
                        "id": video_id,
                        "fields": "items(id,snippet(title,publishedAt),statistics(viewCount,likeCount,commentCount))"
                    },
                    headers=self._get_headers()
                )
                
                if response.status_code == 200:
                    data = response.json()
                    if data.get("items"):
                        video = data["items"][0]
                        return {
                            "video_id": video_id,
                            "title": video.get("snippet", {}).get("title"),
                            "views": int(video.get("statistics", {}).get("viewCount", 0)),
                            "likes": int(video.get("statistics", {}).get("likeCount", 0)),
                            "comments": int(video.get("statistics", {}).get("commentCount", 0)),
                            "published_at": video.get("snippet", {}).get("publishedAt")
                        }
                    return {"error": "Video not found"}
                else:
                    return {"error": f"Failed to fetch analytics: {response.status_code}"}
        except Exception as e:
            return {"error": f"Exception: {str(e)}"}
    
    async def get_video_comments(self, video_id: str, max_results: int = 10) -> Dict[str, Any]:
        """
        Get comments on a YouTube video.
        
        Args:
            video_id: YouTube video ID
            max_results: Number of comments to retrieve
        
        Returns:
            List of comments with metadata
        """
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(
                    f"{self.base_url}/commentThreads",
                    params={
                        "key": self.api_key,
                        "part": "snippet",
                        "videoId": video_id,
                        "maxResults": min(max_results, 100),
                        "textFormat": "plainText"
                    },
                    headers=self._get_headers()
                )
                
                if response.status_code == 200:
                    data = response.json()
                    comments = []
                    for item in data.get("items", []):
                        comment = item.get("snippet", {}).get("topLevelComment", {}).get("snippet", {})
                        comments.append({
                            "author": comment.get("authorDisplayName"),
                            "text": comment.get("textDisplay"),
                            "likes": comment.get("likeCount"),
                            "published_at": comment.get("publishedAt")
                        })
                    return {"comments": comments}
                else:
                    return {"error": f"Failed to fetch comments: {response.status_code}"}
        except Exception as e:
            return {"error": f"Exception: {str(e)}"}
    
    async def search_videos(self, query: str, max_results: int = 10) -> Dict[str, Any]:
        """
        Search YouTube for videos.
        
        Args:
            query: Search query
            max_results: Number of results to retrieve
        
        Returns:
            Search results
        """
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(
                    f"{self.base_url}/search",
                    params={
                        "key": self.api_key,
                        "part": "snippet",
                        "q": query,
                        "type": "video",
                        "maxResults": min(max_results, 50)
                    },
                    headers=self._get_headers()
                )
                
                if response.status_code == 200:
                    data = response.json()
                    videos = []
                    for item in data.get("items", []):
                        video_id = item.get("id", {}).get("videoId")
                        if video_id:
                            videos.append({
                                "video_id": video_id,
                                "title": item.get("snippet", {}).get("title"),
                                "description": item.get("snippet", {}).get("description"),
                                "channel": item.get("snippet", {}).get("channelTitle"),
                                "published_at": item.get("snippet", {}).get("publishedAt")
                            })
                    return {"videos": videos}
                else:
                    return {"error": f"Search failed: {response.status_code}"}
        except Exception as e:
            return {"error": f"Exception: {str(e)}"}
    
    async def get_trending_videos(self, max_results: int = 10) -> Dict[str, Any]:
        """
        Get trending videos on YouTube.
        
        Args:
            max_results: Number of videos to retrieve
        
        Returns:
            List of trending videos
        """
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(
                    f"{self.base_url}/videos",
                    params={
                        "key": self.api_key,
                        "part": "snippet,statistics",
                        "chart": "mostPopular",
                        "maxResults": min(max_results, 50),
                        "regionCode": "US"
                    },
                    headers=self._get_headers()
                )
                
                if response.status_code == 200:
                    data = response.json()
                    videos = []
                    for item in data.get("items", []):
                        videos.append({
                            "video_id": item.get("id"),
                            "title": item.get("snippet", {}).get("title"),
                            "channel": item.get("snippet", {}).get("channelTitle"),
                            "views": item.get("statistics", {}).get("viewCount"),
                            "likes": item.get("statistics", {}).get("likeCount")
                        })
                    return {"videos": videos}
                else:
                    return {"error": f"Failed to fetch trending: {response.status_code}"}
        except Exception as e:
            return {"error": f"Exception: {str(e)}"}
