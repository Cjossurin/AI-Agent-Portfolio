"""
Meta OAuth 2.0 Client - Handles Facebook/Instagram OAuth authorization flow.

This module implements the complete OAuth 2.0 flow required for Meta App Review:
1. Generate authorization URL → redirect user to Meta login
2. Exchange authorization code for access token
3. Refresh long-lived tokens before expiry
4. Revoke tokens on disconnect
5. Validate token permissions

Usage:
    oauth = MetaOAuthClient()
    url = oauth.get_authorization_url(state="random_state_123")
    # User visits url, grants permissions, redirected back with ?code=...
    token_data = await oauth.exchange_code_for_token(code="abc123")
    # Store token_data securely using TokenManager
"""

import os
import time
import secrets
import hashlib
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from dotenv import load_dotenv
import httpx

load_dotenv()


@dataclass
class AccessTokenData:
    """Structured access token response from Meta."""
    access_token: str
    token_type: str = "bearer"
    expires_in: Optional[int] = None  # Seconds until expiry
    expires_at: Optional[float] = None  # Unix timestamp of expiry
    scopes: List[str] = field(default_factory=list)
    user_id: Optional[str] = None  # Meta user ID
    is_long_lived: bool = False
    
    def __post_init__(self):
        if self.expires_in and not self.expires_at:
            self.expires_at = time.time() + self.expires_in
    
    @property
    def is_expired(self) -> bool:
        if not self.expires_at:
            return False
        # Consider expired 5 minutes before actual expiry for safety
        return time.time() > (self.expires_at - 300)
    
    @property
    def time_until_expiry(self) -> Optional[float]:
        if not self.expires_at:
            return None
        return max(0, self.expires_at - time.time())
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "access_token": self.access_token,
            "token_type": self.token_type,
            "expires_in": self.expires_in,
            "expires_at": self.expires_at,
            "scopes": self.scopes,
            "user_id": self.user_id,
            "is_long_lived": self.is_long_lived,
        }


@dataclass
class InstagramBusinessAccount:
    """Instagram Business Account linked to a Facebook Page."""
    id: str  # Instagram Business Account ID
    username: str
    name: str
    profile_picture_url: Optional[str] = None
    followers_count: Optional[int] = None
    media_count: Optional[int] = None
    facebook_page_id: Optional[str] = None
    facebook_page_name: Optional[str] = None


class MetaOAuthClient:
    """
    Complete Meta OAuth 2.0 implementation for Facebook/Instagram.
    
    Handles the full authorization flow:
    - Authorization URL generation with proper scopes
    - Code-to-token exchange
    - Short-lived → long-lived token exchange
    - Token refresh
    - Token validation and debug
    - Token revocation
    - Instagram Business Account discovery
    """
    
    # Meta OAuth endpoints
    AUTHORIZATION_URL = "https://www.facebook.com/v22.0/dialog/oauth"
    TOKEN_URL = "https://graph.facebook.com/v22.0/oauth/access_token"
    DEBUG_TOKEN_URL = "https://graph.facebook.com/debug_token"
    GRAPH_API_BASE = "https://graph.facebook.com/v22.0"
    
    # Default scopes needed for Alita
    #
    # IMPORTANT: Only request scopes that have passed Meta App Review.
    # Requesting rejected/unapproved scopes causes "feature unavailable"
    # errors on the consent screen.
    #
    # Approved (per META_APP_REVIEW_PLAN.md + UNIFIED_APP_RELEASE_GUIDE.md):
    #   instagram_basic, instagram_business_basic,
    #   instagram_business_manage_messages, instagram_manage_messages,
    #   instagram_content_publish, instagram_manage_insights,
    #   pages_show_list, pages_manage_metadata, pages_read_engagement,
    #   pages_manage_posts, pages_manage_engagement, email
    #
    # REJECTED: instagram_manage_comments ("Screencast Not Aligned")
    DEFAULT_SCOPES = [
        # Instagram permissions (approved)
        "instagram_basic",
        "instagram_content_publish",
        "instagram_manage_insights",
        "instagram_manage_messages",
        # Facebook Page permissions (approved)
        "pages_show_list",
        "pages_read_engagement",
        "pages_manage_metadata",
        "pages_manage_posts",
        "pages_manage_engagement",
        # User profile
        "public_profile",
        "email",
    ]
    
    def __init__(
        self,
        app_id: Optional[str] = None,
        app_secret: Optional[str] = None,
        redirect_uri: Optional[str] = None,
    ):
        """
        Initialize Meta OAuth client.
        
        Args:
            app_id: Facebook App ID (defaults to META_APP_ID env var)
            app_secret: Facebook App Secret (defaults to META_APP_SECRET env var)
            redirect_uri: OAuth callback URL (defaults to META_REDIRECT_URI env var)
        """
        self.app_id = app_id or os.getenv("META_APP_ID")
        self.app_secret = app_secret or os.getenv("META_APP_SECRET")
        self.redirect_uri = redirect_uri or os.getenv("META_REDIRECT_URI") or self._build_redirect_uri()

        if not self.app_id:
            raise ValueError(
                "META_APP_ID not configured. Set it in .env or pass app_id parameter."
            )
        if not self.app_secret:
            raise ValueError(
                "META_APP_SECRET not configured. Set it in .env or pass app_secret parameter."
            )

    @staticmethod
    def _build_redirect_uri() -> str:
        """Build the callback URL, auto-detecting Railway domain if env vars not set."""
        for key in ("RAILWAY_PUBLIC_DOMAIN", "RAILWAY_STATIC_URL"):
            domain = os.getenv(key, "").strip()
            if domain:
                domain = domain.removeprefix("https://").removeprefix("http://")
                return f"https://{domain}/auth/callback"
        return "http://localhost:8000/auth/callback"
    
    # ─── Authorization URL ──────────────────────────────────────────────
    
    def get_authorization_url(
        self,
        scopes: Optional[List[str]] = None,
        state: Optional[str] = None,
        extras: Optional[Dict[str, str]] = None,
    ) -> Dict[str, str]:
        """
        Generate the Meta OAuth authorization URL.
        
        The user should be redirected to this URL to start the login flow.
        Meta will show a consent screen, and after approval, redirect the user
        back to redirect_uri with an authorization code.
        
        Args:
            scopes: List of permission scopes (defaults to DEFAULT_SCOPES)
            state: CSRF protection token (auto-generated if not provided)
            extras: Additional query parameters
            
        Returns:
            Dict with 'url' and 'state' (save state to verify callback)
        """
        if state is None:
            state = secrets.token_urlsafe(32)
        
        if scopes is None:
            scopes = self.DEFAULT_SCOPES
        
        params = {
            "client_id": self.app_id,
            "redirect_uri": self.redirect_uri,
            "scope": ",".join(scopes),
            "response_type": "code",
            "state": state,
        }
        
        if extras:
            params.update(extras)
        
        # Build URL
        query_string = "&".join(f"{k}={v}" for k, v in params.items())
        url = f"{self.AUTHORIZATION_URL}?{query_string}"
        
        return {"url": url, "state": state}
    
    # ─── Token Exchange ─────────────────────────────────────────────────
    
    async def exchange_code_for_token(self, code: str) -> AccessTokenData:
        """
        Exchange authorization code for a short-lived access token.
        
        This is Step 2 of the OAuth flow. After the user approves permissions
        on Meta's consent screen, they are redirected back with a ?code= parameter.
        We exchange this code for an access token.
        
        Args:
            code: Authorization code from Meta callback
            
        Returns:
            AccessTokenData with the short-lived token
            
        Raises:
            httpx.HTTPStatusError: If Meta API returns an error
            ValueError: If response is missing expected fields
        """
        params = {
            "client_id": self.app_id,
            "client_secret": self.app_secret,
            "redirect_uri": self.redirect_uri,
            "code": code,
        }
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(self.TOKEN_URL, params=params)
            
            if response.status_code != 200:
                error_data = response.json()
                error_msg = error_data.get("error", {}).get("message", str(error_data))
                raise ValueError(f"Token exchange failed: {error_msg}")
            
            data = response.json()
        
        access_token = data.get("access_token")
        if not access_token:
            raise ValueError(f"No access_token in response: {data}")
        
        # Get user ID from token
        user_id = await self._get_user_id(access_token)
        
        token_data = AccessTokenData(
            access_token=access_token,
            token_type=data.get("token_type", "bearer"),
            expires_in=data.get("expires_in"),
            user_id=user_id,
            is_long_lived=False,
        )
        
        # Get granted scopes
        token_data.scopes = await self._get_token_scopes(access_token)
        
        print(f"✅ Short-lived token obtained for user {user_id}")
        print(f"   Expires in: {token_data.expires_in}s")
        print(f"   Scopes: {', '.join(token_data.scopes[:5])}...")
        
        return token_data
    
    async def exchange_for_long_lived_token(
        self, short_lived_token: str
    ) -> AccessTokenData:
        """
        Exchange a short-lived token (~1 hour) for a long-lived token (~60 days).
        
        CRITICAL: Always do this after initial code exchange. Short-lived tokens
        are useless for production — they expire in ~1 hour.
        
        Args:
            short_lived_token: The short-lived access token
            
        Returns:
            AccessTokenData with the long-lived token (60-day expiry)
        """
        params = {
            "grant_type": "fb_exchange_token",
            "client_id": self.app_id,
            "client_secret": self.app_secret,
            "fb_exchange_token": short_lived_token,
        }
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(self.TOKEN_URL, params=params)
            
            if response.status_code != 200:
                error_data = response.json()
                error_msg = error_data.get("error", {}).get("message", str(error_data))
                raise ValueError(f"Long-lived token exchange failed: {error_msg}")
            
            data = response.json()
        
        access_token = data.get("access_token")
        if not access_token:
            raise ValueError(f"No access_token in long-lived response: {data}")
        
        user_id = await self._get_user_id(access_token)
        scopes = await self._get_token_scopes(access_token)
        
        token_data = AccessTokenData(
            access_token=access_token,
            token_type=data.get("token_type", "bearer"),
            expires_in=data.get("expires_in", 5184000),  # Default 60 days
            user_id=user_id,
            scopes=scopes,
            is_long_lived=True,
        )
        
        print(f"✅ Long-lived token obtained for user {user_id}")
        print(f"   Expires in: {token_data.expires_in // 86400} days")
        
        return token_data
    
    async def refresh_long_lived_token(
        self, current_token: str
    ) -> AccessTokenData:
        """
        Refresh a long-lived token before it expires.
        
        Long-lived tokens can be refreshed once per day, and only if
        the token has NOT yet expired. Once expired, user must re-authenticate.
        
        Args:
            current_token: The current long-lived access token
            
        Returns:
            AccessTokenData with the refreshed token
        """
        # Same endpoint as long-lived exchange
        return await self.exchange_for_long_lived_token(current_token)
    
    # ─── Token Validation ───────────────────────────────────────────────
    
    async def debug_token(self, token: str) -> Dict[str, Any]:
        """
        Inspect a token's metadata using Meta's debug endpoint.
        
        Returns details like: app_id, user_id, scopes, expiry, validity.
        Useful for verifying tokens are working and have correct permissions.
        
        Args:
            token: Access token to inspect
            
        Returns:
            Dict with token debug info
        """
        # Use app token for debugging
        app_token = f"{self.app_id}|{self.app_secret}"
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                self.DEBUG_TOKEN_URL,
                params={
                    "input_token": token,
                    "access_token": app_token,
                },
            )
            
            if response.status_code != 200:
                error_data = response.json()
                raise ValueError(f"Token debug failed: {error_data}")
            
            data = response.json().get("data", {})
        
        return {
            "app_id": data.get("app_id"),
            "user_id": data.get("user_id"),
            "is_valid": data.get("is_valid", False),
            "scopes": data.get("scopes", []),
            "expires_at": data.get("expires_at"),
            "issued_at": data.get("issued_at"),
            "type": data.get("type"),
            "error": data.get("error"),
        }
    
    async def validate_token(self, token: str) -> bool:
        """
        Quick check if a token is still valid.
        
        Args:
            token: Access token to validate
            
        Returns:
            True if token is valid, False otherwise
        """
        try:
            debug_info = await self.debug_token(token)
            return debug_info.get("is_valid", False)
        except Exception:
            return False
    
    # ─── Token Revocation ───────────────────────────────────────────────
    
    async def revoke_token(self, token: str) -> bool:
        """
        Revoke an access token (user disconnects their account).
        
        This permanently invalidates the token. The user will need to
        re-authorize to get a new one.
        
        Args:
            token: Access token to revoke
            
        Returns:
            True if revocation was successful
        """
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.delete(
                f"{self.GRAPH_API_BASE}/me/permissions",
                params={"access_token": token},
            )
            
            if response.status_code == 200:
                result = response.json()
                success = result.get("success", False)
                if success:
                    print("✅ Token successfully revoked")
                return success
            else:
                print(f"❌ Token revocation failed: {response.text}")
                return False
    
    # ─── Account Discovery ──────────────────────────────────────────────
    
    async def get_instagram_business_accounts(
        self, token: str
    ) -> List[InstagramBusinessAccount]:
        """
        Discover all Instagram Business Accounts linked to the user's Facebook Pages.
        
        Flow: User Token → Facebook Pages → Instagram Business Accounts
        
        Args:
            token: Valid user access token
            
        Returns:
            List of InstagramBusinessAccount objects
        """
        accounts = []
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            # Step 1: Get user's Facebook Pages
            pages_response = await client.get(
                f"{self.GRAPH_API_BASE}/me/accounts",
                params={
                    "access_token": token,
                    "fields": "id,name,access_token,instagram_business_account",
                },
            )
            
            if pages_response.status_code != 200:
                print(f"❌ Failed to get Facebook Pages: {pages_response.text}")
                return accounts
            
            pages = pages_response.json().get("data", [])
            
            for page in pages:
                ig_account = page.get("instagram_business_account")
                if not ig_account:
                    continue
                
                ig_id = ig_account.get("id")
                
                # Step 2: Get Instagram account details
                ig_response = await client.get(
                    f"{self.GRAPH_API_BASE}/{ig_id}",
                    params={
                        "access_token": token,
                        "fields": "id,username,name,profile_picture_url,followers_count,media_count",
                    },
                )
                
                if ig_response.status_code == 200:
                    ig_data = ig_response.json()
                    accounts.append(
                        InstagramBusinessAccount(
                            id=ig_data.get("id", ig_id),
                            username=ig_data.get("username", "unknown"),
                            name=ig_data.get("name", ""),
                            profile_picture_url=ig_data.get("profile_picture_url"),
                            followers_count=ig_data.get("followers_count"),
                            media_count=ig_data.get("media_count"),
                            facebook_page_id=page.get("id"),
                            facebook_page_name=page.get("name"),
                        )
                    )
                    print(f"   📸 Found IG account: @{ig_data.get('username')}")
        
        print(f"✅ Found {len(accounts)} Instagram Business Account(s)")
        return accounts
    
    async def get_facebook_pages(self, token: str) -> List[Dict[str, Any]]:
        """
        Get all Facebook Pages the user manages.
        
        Args:
            token: Valid user access token
            
        Returns:
            List of page dicts with id, name, access_token
        """
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"{self.GRAPH_API_BASE}/me/accounts",
                params={
                    "access_token": token,
                    "fields": "id,name,access_token,category",
                },
            )
            
            if response.status_code != 200:
                print(f"❌ Failed to get Facebook Pages: {response.text}")
                return []
            
            pages = response.json().get("data", [])
            print(f"✅ Found {len(pages)} Facebook Page(s)")
            return pages
    
    # ─── Comment Management (for Meta App Review demo) ──────────────────
    
    async def get_post_comments(
        self, token: str, post_id: str, limit: int = 25
    ) -> List[Dict[str, Any]]:
        """
        Get comments on an Instagram post.
        
        Args:
            token: Valid user access token
            post_id: Instagram media ID
            limit: Max comments to return
            
        Returns:
            List of comment dicts
        """
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"{self.GRAPH_API_BASE}/{post_id}/comments",
                params={
                    "access_token": token,
                    "fields": "id,text,timestamp,username,from",
                    "limit": limit,
                },
            )
            
            if response.status_code != 200:
                print(f"❌ Failed to get comments: {response.text}")
                return []
            
            return response.json().get("data", [])
    
    async def reply_to_comment(
        self, token: str, comment_id: str, message: str
    ) -> Optional[str]:
        """
        Reply to an Instagram comment.
        
        Args:
            token: Valid user access token
            comment_id: Comment ID to reply to
            message: Reply text
            
        Returns:
            Reply comment ID if successful, None otherwise
        """
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{self.GRAPH_API_BASE}/{comment_id}/replies",
                json={"message": message},
                params={"access_token": token},
            )
            
            if response.status_code == 200:
                reply_id = response.json().get("id")
                print(f"✅ Replied to comment {comment_id}: {reply_id}")
                return reply_id
            else:
                print(f"❌ Failed to reply: {response.text}")
                return None
    
    # ─── Facebook Comment Management ────────────────────────────────────
    
    async def get_facebook_post_comments(
        self, token: str, post_id: str, limit: int = 25
    ) -> List[Dict[str, Any]]:
        """
        Get comments on a Facebook post.
        
        Args:
            token: Valid page or user access token
            post_id: Facebook post ID
            limit: Max comments to return
            
        Returns:
            List of comment dicts with id, message, from, created_time
        """
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"{self.GRAPH_API_BASE}/{post_id}/comments",
                params={
                    "access_token": token,
                    "fields": "id,message,from,created_time,like_count,comment_count",
                    "limit": limit,
                },
            )
            
            if response.status_code != 200:
                print(f"❌ Failed to get Facebook comments: {response.text}")
                return []
            
            return response.json().get("data", [])
    
    async def reply_to_facebook_comment(
        self, token: str, comment_id: str, message: str
    ) -> Optional[str]:
        """
        Reply to a Facebook comment.
        
        Args:
            token: Valid page access token
            comment_id: Comment ID to reply to
            message: Reply text
            
        Returns:
            Reply comment ID if successful, None otherwise
        """
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{self.GRAPH_API_BASE}/{comment_id}/comments",
                data={"message": message},
                params={"access_token": token},
            )
            
            if response.status_code == 200:
                reply_id = response.json().get("id")
                print(f"✅ Replied to Facebook comment {comment_id}: {reply_id}")
                return reply_id
            else:
                print(f"❌ Failed to reply to Facebook comment: {response.text}")
                return None
    
    async def delete_facebook_comment(
        self, token: str, comment_id: str
    ) -> bool:
        """
        Delete a Facebook comment (moderation).
        
        Args:
            token: Valid page access token
            comment_id: Comment ID to delete
            
        Returns:
            True if successful
        """
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.delete(
                f"{self.GRAPH_API_BASE}/{comment_id}",
                params={"access_token": token},
            )
            
            if response.status_code == 200:
                print(f"✅ Deleted Facebook comment {comment_id}")
                return True
            else:
                print(f"❌ Failed to delete comment: {response.text}")
                return False
    
    async def hide_facebook_comment(
        self, token: str, comment_id: str, is_hidden: bool = True
    ) -> bool:
        """
        Hide/unhide a Facebook comment.
        
        Args:
            token: Valid page access token
            comment_id: Comment ID to hide
            is_hidden: True to hide, False to unhide
            
        Returns:
            True if successful
        """
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{self.GRAPH_API_BASE}/{comment_id}",
                data={"is_hidden": str(is_hidden).lower()},
                params={"access_token": token},
            )
            
            if response.status_code == 200:
                action = "hidden" if is_hidden else "unhidden"
                print(f"✅ {action.capitalize()} Facebook comment {comment_id}")
                return True
            else:
                print(f"❌ Failed to hide/unhide comment: {response.text}")
                return False
    
    # ─── Facebook Messenger (Page Inbox) ───────────────────────────────
    
    async def get_page_conversations(
        self, page_id: str, page_token: str, limit: int = 25
    ) -> List[Dict[str, Any]]:
        """
        Get conversations in Page inbox (Messenger).
        
        Args:
            page_id: Facebook Page ID
            page_token: Page access token
            limit: Max conversations to return
            
        Returns:
            List of conversation dicts
        """
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"{self.GRAPH_API_BASE}/{page_id}/conversations",
                params={
                    "access_token": page_token,
                    "fields": "id,participants,updated_time,message_count",
                    "limit": limit,
                },
            )
            
            if response.status_code != 200:
                print(f"❌ Failed to get conversations: {response.text}")
                return []
            
            return response.json().get("data", [])
    
    async def get_conversation_messages(
        self, conversation_id: str, page_token: str, limit: int = 25
    ) -> List[Dict[str, Any]]:
        """
        Get messages in a Facebook Page conversation.
        
        Args:
            conversation_id: Conversation ID
            page_token: Page access token
            limit: Max messages to return
            
        Returns:
            List of message dicts
        """
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"{self.GRAPH_API_BASE}/{conversation_id}/messages",
                params={
                    "access_token": page_token,
                    "fields": "id,message,from,created_time",
                    "limit": limit,
                },
            )
            
            if response.status_code != 200:
                print(f"❌ Failed to get messages: {response.text}")
                return []
            
            return response.json().get("data", [])
    
    async def send_facebook_message(
        self, page_id: str, page_token: str, recipient_id: str, message: str
    ) -> Optional[str]:
        """
        Send a Facebook Messenger message from a Page.
        
        Args:
            page_id: Facebook Page ID
            page_token: Page access token
            recipient_id: PSID (Page-scoped ID) of the recipient
            message: Message text
            
        Returns:
            Message ID if successful
        """
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{self.GRAPH_API_BASE}/{page_id}/messages",
                json={
                    "recipient": {"id": recipient_id},
                    "message": {"text": message},
                },
                params={"access_token": page_token},
            )
            
            if response.status_code == 200:
                message_id = response.json().get("message_id")
                print(f"✅ Sent Facebook message: {message_id}")
                return message_id
            else:
                print(f"❌ Failed to send Facebook message: {response.text}")
                return None
    
    # ─── Instagram Posting ──────────────────────────────────────────────
    
    async def create_instagram_image_post(
        self, ig_account_id: str, token: str, image_url: str, caption: str = ""
    ) -> Optional[str]:
        """
        Post an image to Instagram (2-step process: create container → publish).
        
        Args:
            ig_account_id: Instagram Business Account ID
            token: Valid user access token
            image_url: Publicly accessible URL of the image
            caption: Post caption (optional)
            
        Returns:
            Published post ID if successful
        """
        async with httpx.AsyncClient(timeout=60.0) as client:
            # Step 1: Create media container
            container_response = await client.post(
                f"{self.GRAPH_API_BASE}/{ig_account_id}/media",
                data={
                    "image_url": image_url,
                    "caption": caption,
                },
                params={"access_token": token},
            )
            
            if container_response.status_code != 200:
                print(f"❌ Failed to create container: {container_response.text}")
                return None
            
            container_id = container_response.json().get("id")
            print(f"📦 Container created: {container_id}")
            
            # Step 2: Publish container
            publish_response = await client.post(
                f"{self.GRAPH_API_BASE}/{ig_account_id}/media_publish",
                data={"creation_id": container_id},
                params={"access_token": token},
            )
            
            if publish_response.status_code == 200:
                post_id = publish_response.json().get("id")
                print(f"✅ Instagram post published: {post_id}")
                return post_id
            else:
                print(f"❌ Failed to publish: {publish_response.text}")
                return None
    
    async def create_instagram_video_post(
        self, ig_account_id: str, token: str, video_url: str, caption: str = "",
        cover_url: Optional[str] = None, is_reel: bool = True
    ) -> Optional[str]:
        """
        Post a Reel or video to Instagram (2-step: create container → publish).

        Args:
            ig_account_id: Instagram Business Account ID
            token: Valid user access token
            video_url: Publicly accessible URL of the video
            caption: Post caption (optional)
            cover_url: Optional thumbnail URL
            is_reel: True (default) to publish as REELS; False for in-feed VIDEO

        Returns:
            Published post ID if successful
        """
        async with httpx.AsyncClient(timeout=120.0) as client:
            # Step 1: Create media container — use REELS for proper Reel publishing
            data = {
                "media_type": "REELS" if is_reel else "VIDEO",
                "video_url": video_url,
                "caption": caption,
            }
            if is_reel:
                data["share_to_feed"] = "true"
            if cover_url:
                data["cover_url"] = cover_url
            
            container_response = await client.post(
                f"{self.GRAPH_API_BASE}/{ig_account_id}/media",
                data=data,
                params={"access_token": token},
            )
            
            if container_response.status_code != 200:
                print(f"❌ Failed to create video container: {container_response.text}")
                return None
            
            container_id = container_response.json().get("id")
            print(f"📦 Video container created: {container_id}")
            
            # Wait for video processing (poll status)
            import asyncio
            max_wait = 60  # seconds
            waited = 0
            while waited < max_wait:
                status_response = await client.get(
                    f"{self.GRAPH_API_BASE}/{container_id}",
                    params={"access_token": token, "fields": "status_code"},
                )
                
                if status_response.status_code == 200:
                    status = status_response.json().get("status_code")
                    if status == "FINISHED":
                        break
                    elif status == "ERROR":
                        print("❌ Video processing failed")
                        return None
                
                await asyncio.sleep(5)
                waited += 5
            
            # Step 2: Publish
            publish_response = await client.post(
                f"{self.GRAPH_API_BASE}/{ig_account_id}/media_publish",
                data={"creation_id": container_id},
                params={"access_token": token},
            )
            
            if publish_response.status_code == 200:
                post_id = publish_response.json().get("id")
                print(f"✅ Instagram video published: {post_id}")
                return post_id
            else:
                print(f"❌ Failed to publish video: {publish_response.text}")
                return None
    
    async def get_instagram_media(
        self, ig_account_id: str, token: str, limit: int = 25
    ) -> List[Dict[str, Any]]:
        """
        Get recent Instagram posts for an account.
        
        Args:
            ig_account_id: Instagram Business Account ID
            token: Valid user access token
            limit: Max posts to return
            
        Returns:
            List of media dicts
        """
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"{self.GRAPH_API_BASE}/{ig_account_id}/media",
                params={
                    "access_token": token,
                    "fields": "id,media_type,media_url,permalink,caption,timestamp,like_count,comments_count",
                    "limit": limit,
                },
            )
            
            if response.status_code != 200:
                print(f"❌ Failed to get Instagram media: {response.text}")
                return []
            
            return response.json().get("data", [])
    
    # ─── Instagram Engagement ───────────────────────────────────────────
    
    async def like_instagram_media(
        self, media_id: str, token: str
    ) -> bool:
        """
        Like an Instagram post.
        
        Args:
            media_id: Instagram media ID
            token: Valid user access token
            
        Returns:
            True if successful
        """
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{self.GRAPH_API_BASE}/{media_id}/likes",
                params={"access_token": token},
            )
            
            if response.status_code == 200:
                print(f"✅ Liked Instagram post {media_id}")
                return True
            else:
                print(f"❌ Failed to like: {response.text}")
                return False
    
    async def unlike_instagram_media(
        self, media_id: str, token: str
    ) -> bool:
        """
        Unlike an Instagram post.
        
        Args:
            media_id: Instagram media ID
            token: Valid user access token
            
        Returns:
            True if successful
        """
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.delete(
                f"{self.GRAPH_API_BASE}/{media_id}/likes",
                params={"access_token": token},
            )
            
            if response.status_code == 200:
                print(f"✅ Unliked Instagram post {media_id}")
                return True
            else:
                print(f"❌ Failed to unlike: {response.text}")
                return False
    
    async def comment_on_instagram_media(
        self, media_id: str, token: str, message: str
    ) -> Optional[str]:
        """
        Comment on an Instagram post.
        
        Args:
            media_id: Instagram media ID
            token: Valid user access token
            message: Comment text
            
        Returns:
            Comment ID if successful
        """
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{self.GRAPH_API_BASE}/{media_id}/comments",
                data={"message": message},
                params={"access_token": token},
            )
            
            if response.status_code == 200:
                comment_id = response.json().get("id")
                print(f"✅ Commented on Instagram post {media_id}: {comment_id}")
                return comment_id
            else:
                print(f"❌ Failed to comment: {response.text}")
                return None
    
    async def delete_instagram_comment(
        self, comment_id: str, token: str
    ) -> bool:
        """
        Delete an Instagram comment.
        
        Args:
            comment_id: Comment ID to delete
            token: Valid user access token
            
        Returns:
            True if successful
        """
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.delete(
                f"{self.GRAPH_API_BASE}/{comment_id}",
                params={"access_token": token},
            )
            
            if response.status_code == 200:
                print(f"✅ Deleted Instagram comment {comment_id}")
                return True
            else:
                print(f"❌ Failed to delete comment: {response.text}")
                return False
    
    async def hide_instagram_comment(
        self, comment_id: str, token: str, hide: bool = True
    ) -> bool:
        """
        Hide/unhide an Instagram comment.
        
        Args:
            comment_id: Comment ID to hide
            token: Valid user access token
            hide: True to hide, False to unhide
            
        Returns:
            True if successful
        """
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{self.GRAPH_API_BASE}/{comment_id}",
                data={"hide": str(hide).lower()},
                params={"access_token": token},
            )
            
            if response.status_code == 200:
                action = "hidden" if hide else "unhidden"
                print(f"✅ {action.capitalize()} Instagram comment {comment_id}")
                return True
            else:
                print(f"❌ Failed to hide/unhide comment: {response.text}")
                return False
    
    # ─── Instagram Direct Messages ──────────────────────────────────────
    
    async def send_instagram_dm(
        self, ig_account_id: str, token: str, recipient_id: str, message: str
    ) -> Optional[str]:
        """
        Send an Instagram Direct Message.
        
        Args:
            ig_account_id: Instagram Business Account ID
            token: Valid user access token
            recipient_id: Instagram user ID (IGSID)
            message: Message text
            
        Returns:
            Message ID if successful
        """
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{self.GRAPH_API_BASE}/{ig_account_id}/messages",
                json={
                    "recipient": {"id": recipient_id},
                    "message": {"text": message},
                },
                params={"access_token": token},
            )
            
            if response.status_code == 200:
                message_id = response.json().get("message_id")
                print(f"✅ Sent Instagram DM: {message_id}")
                return message_id
            else:
                print(f"❌ Failed to send Instagram DM: {response.text}")
                return None
    
    # ─── Facebook Page Posting ──────────────────────────────────────────
    
    async def create_facebook_post(
        self, page_id: str, page_token: str, message: str,
        link: Optional[str] = None, published: bool = True
    ) -> Optional[str]:
        """
        Create a Facebook Page post.
        
        Args:
            page_id: Facebook Page ID
            page_token: Page access token
            message: Post text
            link: Optional URL to share
            published: If False, creates as draft
            
        Returns:
            Post ID if successful
        """
        async with httpx.AsyncClient(timeout=30.0) as client:
            data = {
                "message": message,
                "published": str(published).lower(),
            }
            if link:
                data["link"] = link
            
            response = await client.post(
                f"{self.GRAPH_API_BASE}/{page_id}/feed",
                data=data,
                params={"access_token": page_token},
            )
            
            if response.status_code == 200:
                post_id = response.json().get("id")
                print(f"✅ Facebook post created: {post_id}")
                return post_id
            else:
                print(f"❌ Failed to create Facebook post: {response.text}")
                return None
    
    async def create_facebook_photo_post(
        self, page_id: str, page_token: str, photo_url: str, message: str = ""
    ) -> Optional[str]:
        """
        Post a photo to a Facebook Page.
        
        Args:
            page_id: Facebook Page ID
            page_token: Page access token
            photo_url: URL of the photo
            message: Caption
            
        Returns:
            Post ID if successful
        """
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"{self.GRAPH_API_BASE}/{page_id}/photos",
                data={
                    "url": photo_url,
                    "caption": message,
                },
                params={"access_token": page_token},
            )
            
            if response.status_code == 200:
                post_id = response.json().get("post_id")
                print(f"✅ Facebook photo posted: {post_id}")
                return post_id
            else:
                print(f"❌ Failed to post photo: {response.text}")
                return None
    
    # ─── Private Helpers ────────────────────────────────────────────────
    
    async def _get_user_id(self, token: str) -> Optional[str]:
        """Get the Meta user ID from a token."""
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.get(
                    f"{self.GRAPH_API_BASE}/me",
                    params={"access_token": token, "fields": "id"},
                )
                if response.status_code == 200:
                    return response.json().get("id")
        except Exception:
            pass
        return None
    
    async def _get_token_scopes(self, token: str) -> List[str]:
        """Get the scopes/permissions granted for a token."""
        try:
            debug_info = await self.debug_token(token)
            return debug_info.get("scopes", [])
        except Exception:
            return []
    
    @staticmethod
    def generate_state_token() -> str:
        """Generate a cryptographically secure state token for CSRF protection."""
        return secrets.token_urlsafe(32)
    
    @staticmethod
    def verify_state_token(expected: str, received: str) -> bool:
        """Verify state token matches (constant-time comparison)."""
        return secrets.compare_digest(expected, received)
