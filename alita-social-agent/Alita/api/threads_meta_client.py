"""
Threads API Client (Meta Graph API)
====================================
Post to Threads using Meta Graph API via Instagram Business Account.

This uses your existing Instagram access token to post to Threads.
Requires: Instagram Business Account linked to Threads account.

SETUP:
1. Link your Threads account to your Instagram Business Account
2. Use your existing INSTAGRAM_ACCESS_TOKEN
3. Posts will appear on both Instagram and Threads (if configured)
"""

import os
import httpx
from typing import Optional, List, Dict, Any
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()


class ThreadsMetaClient:
    """
    Client for Threads API using Meta Graph API.
    Uses existing Instagram Business Account credentials.
    """
    
    def __init__(self, access_token: Optional[str] = None):
        """
        Initialize Threads Meta client.
        
        Args:
            access_token: Meta access token (defaults to INSTAGRAM_ACCESS_TOKEN from .env)
        """
        self.access_token = access_token or os.getenv("INSTAGRAM_ACCESS_TOKEN")
        self.ig_user_id = os.getenv("INSTAGRAM_BUSINESS_ACCOUNT_ID")
        self.base_url = "https://graph.facebook.com/v21.0"
        
        if not self.access_token:
            raise ValueError("INSTAGRAM_ACCESS_TOKEN not found in environment")
        if not self.ig_user_id:
            raise ValueError("INSTAGRAM_BUSINESS_ACCOUNT_ID not found in environment")
    
    async def create_text_post(self, text: str) -> Dict[str, Any]:
        """
        Create a text-only Threads post.
        
        Args:
            text: Post text (max 500 characters)
            
        Returns:
            Dict with post_id and status
        """
        try:
            async with httpx.AsyncClient() as client:
                # Step 1: Create container
                container_response = await client.post(
                    f"{self.base_url}/{self.ig_user_id}/threads",
                    params={
                        "media_type": "TEXT",
                        "text": text[:500],  # Threads has 500 char limit
                        "access_token": self.access_token
                    }
                )
                container_data = container_response.json()
                
                if "error" in container_data:
                    return {
                        "success": False,
                        "error": container_data["error"].get("message", "Failed to create container")
                    }
                
                container_id = container_data.get("id")
                
                # Step 2: Publish container
                publish_response = await client.post(
                    f"{self.base_url}/{self.ig_user_id}/threads_publish",
                    params={
                        "creation_id": container_id,
                        "access_token": self.access_token
                    }
                )
                publish_data = publish_response.json()
                
                if "error" in publish_data:
                    return {
                        "success": False,
                        "error": publish_data["error"].get("message", "Failed to publish")
                    }
                
                return {
                    "success": True,
                    "post_id": publish_data.get("id"),
                    "status": "published"
                }
                
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }
    
    async def create_media_post(
        self,
        text: str,
        image_url: Optional[str] = None,
        video_url: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Create a Threads post with media (image or video).
        
        Args:
            text: Post text
            image_url: URL to image (must be publicly accessible)
            video_url: URL to video (must be publicly accessible)
            
        Returns:
            Dict with post_id and status
        """
        try:
            async with httpx.AsyncClient() as client:
                # Determine media type
                if video_url:
                    media_type = "VIDEO"
                    media_url = video_url
                elif image_url:
                    media_type = "IMAGE"
                    media_url = image_url
                else:
                    # No media, just text
                    return await self.create_text_post(text)
                
                # Step 1: Create container with media
                params = {
                    "media_type": media_type,
                    "text": text[:500],
                    "access_token": self.access_token
                }
                
                if media_type == "IMAGE":
                    params["image_url"] = media_url
                elif media_type == "VIDEO":
                    params["video_url"] = media_url
                
                container_response = await client.post(
                    f"{self.base_url}/{self.ig_user_id}/threads",
                    params=params
                )
                container_data = container_response.json()
                
                if "error" in container_data:
                    return {
                        "success": False,
                        "error": container_data["error"].get("message", "Failed to create container")
                    }
                
                container_id = container_data.get("id")
                
                # Step 2: Wait for video processing if needed
                if media_type == "VIDEO":
                    # Check container status
                    import asyncio
                    for _ in range(30):  # Wait up to 30 seconds
                        status_response = await client.get(
                            f"{self.base_url}/{container_id}",
                            params={
                                "fields": "status_code",
                                "access_token": self.access_token
                            }
                        )
                        status_data = status_response.json()
                        status_code = status_data.get("status_code")
                        
                        if status_code == "FINISHED":
                            break
                        elif status_code == "ERROR":
                            return {
                                "success": False,
                                "error": "Video processing failed"
                            }
                        
                        await asyncio.sleep(1)
                
                # Step 3: Publish container
                publish_response = await client.post(
                    f"{self.base_url}/{self.ig_user_id}/threads_publish",
                    params={
                        "creation_id": container_id,
                        "access_token": self.access_token
                    }
                )
                publish_data = publish_response.json()
                
                if "error" in publish_data:
                    return {
                        "success": False,
                        "error": publish_data["error"].get("message", "Failed to publish")
                    }
                
                return {
                    "success": True,
                    "post_id": publish_data.get("id"),
                    "status": "published"
                }
                
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }
    
    async def get_threads_profile(self) -> Dict[str, Any]:
        """
        Get Threads profile information.
        
        Returns:
            Dict with profile data (username, bio, follower_count, etc.)
        """
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.base_url}/{self.ig_user_id}/threads_profile",
                    params={
                        "fields": "id,username,threads_profile_picture_url,threads_biography",
                        "access_token": self.access_token
                    }
                )
                data = response.json()
                
                if "error" in data:
                    return {
                        "success": False,
                        "error": data["error"].get("message", "Failed to get profile")
                    }
                
                return {
                    "success": True,
                    "profile": data
                }
                
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }
    
    async def get_threads_insights(self, post_id: str) -> Dict[str, Any]:
        """
        Get insights/analytics for a Threads post.
        
        Args:
            post_id: ID of the Threads post
            
        Returns:
            Dict with insights data (views, likes, replies, etc.)
        """
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.base_url}/{post_id}/insights",
                    params={
                        "metric": "views,likes,replies,reposts,quotes",
                        "access_token": self.access_token
                    }
                )
                data = response.json()
                
                if "error" in data:
                    return {
                        "success": False,
                        "error": data["error"].get("message", "Failed to get insights")
                    }
                
                return {
                    "success": True,
                    "insights": data.get("data", [])
                }
                
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }
    
    async def check_threads_enabled(self) -> bool:
        """
        Check if Threads posting is enabled for this Instagram account.
        
        Returns:
            True if Threads is linked and accessible, False otherwise
        """
        try:
            result = await self.get_threads_profile()
            return result.get("success", False)
        except:
            return False
