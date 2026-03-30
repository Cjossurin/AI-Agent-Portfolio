"""
Twitter/X API Client - Full integration for tweeting, analytics, and engagement
Documentation: https://developer.twitter.com/en/docs/twitter-api
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
class Tweet:
    """Tweet data model."""
    id: str
    text: str
    created_at: str
    author_id: str
    public_metrics: Dict[str, int]
    impression_count: Optional[int] = None


@dataclass
class TweetResponse:
    """Response from tweet operation."""
    success: bool
    tweet_id: Optional[str] = None
    text: Optional[str] = None
    created_at: Optional[str] = None
    error: Optional[str] = None
    raw_response: Optional[Dict] = None


class TwitterClient:
    """
    Twitter/X API Client - Native integration.
    
    Features:
    - Post tweets (v2 API)
    - Get tweet analytics (impressions, engagement)
    - Retrieve user timeline
    - Like, retweet, reply to tweets
    - Get user profile information
    - Search tweets
    
    Requires:
    - TWITTER_API_KEY: API Key (Bearer Token)
    - TWITTER_API_SECRET: API Secret
    - TWITTER_ACCESS_TOKEN: User access token
    - TWITTER_ACCESS_TOKEN_SECRET: User access token secret
    - TWITTER_USER_ID: User ID for the authenticated account
    
    Usage:
        client = TwitterClient()
        response = await client.post_tweet("Hello Twitter!")
    """
    
    def __init__(self):
        """Initialize Twitter API client with credentials."""
        self.api_key = os.getenv("TWITTER_API_KEY")
        self.api_secret = os.getenv("TWITTER_API_SECRET")
        self.access_token = os.getenv("TWITTER_ACCESS_TOKEN")
        self.access_token_secret = os.getenv("TWITTER_ACCESS_TOKEN_SECRET")
        self.user_id = os.getenv("TWITTER_USER_ID")
        
        self.base_url = "https://api.twitter.com/2"
        self.timeout = 30.0
        
    def _get_headers(self) -> Dict[str, str]:
        """Get request headers with Bearer token authentication."""
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "User-Agent": "Alita-AI-Agent/1.0"
        }
    
    async def post_tweet(self, text: str, reply_settings: str = "everyone") -> TweetResponse:
        """
        Post a tweet.
        
        Args:
            text: Tweet content (max 280 characters)
            reply_settings: "everyone", "following", or "mentioned_users"
        
        Returns:
            TweetResponse with tweet ID and status
        """
        if len(text) > 280:
            return TweetResponse(
                success=False,
                error=f"Tweet exceeds 280 character limit ({len(text)} characters)"
            )
        
        payload = {
            "text": text,
            "reply_settings": reply_settings
        }
        
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.base_url}/tweets",
                    json=payload,
                    headers=self._get_headers()
                )
                
                if response.status_code == 201:
                    data = response.json()
                    return TweetResponse(
                        success=True,
                        tweet_id=data.get("data", {}).get("id"),
                        text=text,
                        created_at=datetime.utcnow().isoformat(),
                        raw_response=data
                    )
                else:
                    error_detail = response.json() if response.text else response.text
                    return TweetResponse(
                        success=False,
                        error=f"Twitter API error: {response.status_code} - {error_detail}"
                    )
        except Exception as e:
            return TweetResponse(success=False, error=f"Exception: {str(e)}")
    
    async def post_tweet_with_media(
        self,
        text: str,
        media_ids: List[str],
        reply_settings: str = "everyone"
    ) -> TweetResponse:
        """
        Post a tweet with media attachments.
        
        Args:
            text: Tweet content
            media_ids: List of media IDs (uploaded via upload_media)
            reply_settings: Reply settings
        
        Returns:
            TweetResponse
        """
        payload = {
            "text": text,
            "reply_settings": reply_settings,
            "media": {
                "media_ids": media_ids
            }
        }
        
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.base_url}/tweets",
                    json=payload,
                    headers=self._get_headers()
                )
                
                if response.status_code == 201:
                    data = response.json()
                    return TweetResponse(
                        success=True,
                        tweet_id=data.get("data", {}).get("id"),
                        text=text,
                        created_at=datetime.utcnow().isoformat(),
                        raw_response=data
                    )
                else:
                    return TweetResponse(
                        success=False,
                        error=f"Twitter API error: {response.status_code}"
                    )
        except Exception as e:
            return TweetResponse(success=False, error=f"Exception: {str(e)}")
    
    async def get_tweet_analytics(self, tweet_id: str) -> Dict[str, Any]:
        """
        Get analytics for a specific tweet.
        
        Args:
            tweet_id: Twitter tweet ID
        
        Returns:
            Dictionary with tweet metrics (impressions, engagement, etc.)
        """
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(
                    f"{self.base_url}/tweets/{tweet_id}",
                    params={"tweet.fields": "public_metrics,impression_count"},
                    headers=self._get_headers()
                )
                
                if response.status_code == 200:
                    data = response.json()
                    tweet = data.get("data", {})
                    return {
                        "tweet_id": tweet_id,
                        "text": tweet.get("text"),
                        "impressions": tweet.get("impression_count", 0),
                        "metrics": tweet.get("public_metrics", {}),
                        "created_at": tweet.get("created_at")
                    }
                else:
                    return {"error": f"Failed to fetch tweet: {response.status_code}"}
        except Exception as e:
            return {"error": f"Exception: {str(e)}"}
    
    async def get_user_timeline(
        self,
        user_id: Optional[str] = None,
        max_results: int = 10
    ) -> Dict[str, Any]:
        """
        Get user's recent tweets.
        
        Args:
            user_id: User ID (defaults to authenticated user)
            max_results: Number of tweets to retrieve (max 100)
        
        Returns:
            Dictionary with tweet list and pagination
        """
        user_id = user_id or self.user_id
        if not user_id:
            return {"error": "User ID not configured"}
        
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(
                    f"{self.base_url}/users/{user_id}/tweets",
                    params={
                        "max_results": min(max_results, 100),
                        "tweet.fields": "created_at,public_metrics,impression_count"
                    },
                    headers=self._get_headers()
                )
                
                if response.status_code == 200:
                    data = response.json()
                    return {
                        "tweets": data.get("data", []),
                        "meta": data.get("meta", {})
                    }
                else:
                    return {"error": f"Failed to fetch timeline: {response.status_code}"}
        except Exception as e:
            return {"error": f"Exception: {str(e)}"}
    
    async def like_tweet(self, tweet_id: str) -> Dict[str, Any]:
        """
        Like a tweet.
        
        Args:
            tweet_id: Tweet ID to like
        
        Returns:
            Success/failure response
        """
        payload = {"tweet_id": tweet_id}
        
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.base_url}/users/{self.user_id}/likes",
                    json=payload,
                    headers=self._get_headers()
                )
                
                if response.status_code == 200:
                    return {"success": True, "message": "Tweet liked"}
                else:
                    return {"success": False, "error": f"Error: {response.status_code}"}
        except Exception as e:
            return {"success": False, "error": f"Exception: {str(e)}"}
    
    async def retweet(self, tweet_id: str) -> Dict[str, Any]:
        """
        Retweet a tweet.
        
        Args:
            tweet_id: Tweet ID to retweet
        
        Returns:
            Success/failure response
        """
        payload = {"tweet_id": tweet_id}
        
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.base_url}/users/{self.user_id}/retweets",
                    json=payload,
                    headers=self._get_headers()
                )
                
                if response.status_code == 200:
                    return {"success": True, "message": "Tweet retweeted"}
                else:
                    return {"success": False, "error": f"Error: {response.status_code}"}
        except Exception as e:
            return {"success": False, "error": f"Exception: {str(e)}"}
    
    async def reply_to_tweet(self, tweet_id: str, text: str) -> TweetResponse:
        """
        Reply to a tweet.
        
        Args:
            tweet_id: Tweet ID to reply to
            text: Reply content
        
        Returns:
            TweetResponse
        """
        payload = {
            "text": text,
            "reply": {
                "in_reply_to_tweet_id": tweet_id
            }
        }
        
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.base_url}/tweets",
                    json=payload,
                    headers=self._get_headers()
                )
                
                if response.status_code == 201:
                    data = response.json()
                    return TweetResponse(
                        success=True,
                        tweet_id=data.get("data", {}).get("id"),
                        text=text,
                        created_at=datetime.utcnow().isoformat(),
                        raw_response=data
                    )
                else:
                    return TweetResponse(success=False, error=f"Error: {response.status_code}")
        except Exception as e:
            return TweetResponse(success=False, error=f"Exception: {str(e)}")
    
    async def get_user_profile(self, user_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Get user profile information.
        
        Args:
            user_id: User ID (defaults to authenticated user)
        
        Returns:
            User profile data
        """
        user_id = user_id or self.user_id
        if not user_id:
            return {"error": "User ID not configured"}
        
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(
                    f"{self.base_url}/users/{user_id}",
                    params={"user.fields": "public_metrics,created_at,description,verified"},
                    headers=self._get_headers()
                )
                
                if response.status_code == 200:
                    data = response.json()
                    return data.get("data", {})
                else:
                    return {"error": f"Failed to fetch profile: {response.status_code}"}
        except Exception as e:
            return {"error": f"Exception: {str(e)}"}
    
    async def search_tweets(self, query: str, max_results: int = 10) -> Dict[str, Any]:
        """
        Search for tweets.
        
        Args:
            query: Search query
            max_results: Number of tweets to retrieve
        
        Returns:
            Search results
        """
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(
                    f"{self.base_url}/tweets/search/recent",
                    params={
                        "query": query,
                        "max_results": min(max_results, 100),
                        "tweet.fields": "created_at,public_metrics"
                    },
                    headers=self._get_headers()
                )
                
                if response.status_code == 200:
                    data = response.json()
                    return {
                        "tweets": data.get("data", []),
                        "meta": data.get("meta", {})
                    }
                else:
                    return {"error": f"Search failed: {response.status_code}"}
        except Exception as e:
            return {"error": f"Exception: {str(e)}"}
