"""
Token Manager - Secure storage and lifecycle management for OAuth tokens.

Uses SQLite for persistence and Fernet symmetric encryption for token security.
Handles:
- Encrypted token storage (access + refresh tokens)
- Automatic token refresh before expiry
- User ↔ Instagram account mapping (for webhook routing)
- Token revocation / account disconnection
- Multi-user isolation

Database Schema:
    users          - Registered users (email, name, created)
    user_tokens    - Encrypted OAuth tokens per user
    account_map    - Maps Instagram Business Account IDs → user IDs (webhook routing)

Usage:
    tm = TokenManager()
    await tm.initialize()  # Creates tables if needed
    await tm.store_token(user_id="u1", token_data=token, ig_accounts=[...])
    token = await tm.get_valid_token(user_id="u1")  # Auto-refreshes if needed
"""

import os
import time
import json
import sqlite3
import secrets
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

# ─── Encryption ─────────────────────────────────────────────────────────

# Try cryptography library first, fall back to base64 obfuscation
try:
    from cryptography.fernet import Fernet
    ENCRYPTION_AVAILABLE = True
except ImportError:
    ENCRYPTION_AVAILABLE = False
    import base64
    print("⚠️  cryptography package not installed. Using base64 encoding (NOT secure for production).")
    print("   Install with: pip install cryptography")

# Cache the encryption key for the lifetime of this process
_CACHED_ENCRYPTION_KEY: Optional[bytes] = None


def _get_encryption_key() -> bytes:
    """
    Get or generate the encryption key for token storage.
    
    The key is cached in-memory so the same key is used for both
    encrypt and decrypt within a single process. In production,
    this should come from .env or a secret manager.
    """
    global _CACHED_ENCRYPTION_KEY
    
    if _CACHED_ENCRYPTION_KEY is not None:
        return _CACHED_ENCRYPTION_KEY
    
    key = os.getenv("TOKEN_ENCRYPTION_KEY")
    
    if key:
        _CACHED_ENCRYPTION_KEY = key.encode()
        return _CACHED_ENCRYPTION_KEY
    
    # Generate a new key and cache it for this process
    if ENCRYPTION_AVAILABLE:
        new_key = Fernet.generate_key()
    else:
        new_key = base64.urlsafe_b64encode(secrets.token_bytes(32))
    
    _CACHED_ENCRYPTION_KEY = new_key
    
    print(f"⚠️  No TOKEN_ENCRYPTION_KEY found in .env")
    print(f"   Generated new key. Add this to your .env file:")
    print(f"   TOKEN_ENCRYPTION_KEY={new_key.decode()}")
    
    return new_key


def encrypt_value(plaintext: str) -> str:
    """Encrypt a string value for storage."""
    key = _get_encryption_key()
    if ENCRYPTION_AVAILABLE:
        f = Fernet(key)
        return f.encrypt(plaintext.encode()).decode()
    else:
        # Base64 fallback (NOT secure — development only)
        import base64
        return base64.urlsafe_b64encode(plaintext.encode()).decode()


def decrypt_value(ciphertext: str) -> str:
    """Decrypt a stored value."""
    key = _get_encryption_key()
    if ENCRYPTION_AVAILABLE:
        f = Fernet(key)
        return f.decrypt(ciphertext.encode()).decode()
    else:
        import base64
        return base64.urlsafe_b64decode(ciphertext.encode()).decode()


# ─── Data Models ─────────────────────────────────────────────────────────

@dataclass
class StoredUser:
    """A registered user in the system."""
    user_id: str
    email: Optional[str] = None
    name: Optional[str] = None
    meta_user_id: Optional[str] = None  # Facebook/Meta user ID
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    is_active: bool = True


@dataclass
class StoredToken:
    """A stored OAuth token (decrypted view)."""
    user_id: str
    access_token: str
    token_type: str = "bearer"
    expires_at: Optional[float] = None
    scopes: Optional[str] = None  # Comma-separated scopes
    is_long_lived: bool = False
    instagram_account_id: Optional[str] = None
    facebook_page_id: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    
    @property
    def is_expired(self) -> bool:
        if not self.expires_at:
            return False
        return time.time() > (self.expires_at - 300)  # 5-min buffer
    
    @property
    def scope_list(self) -> List[str]:
        if not self.scopes:
            return []
        return [s.strip() for s in self.scopes.split(",")]


# ─── Token Manager ──────────────────────────────────────────────────────

class TokenManager:
    """
    Manages OAuth token lifecycle with encrypted SQLite storage.
    
    Key operations:
    - store_token()         Store encrypted token for a user
    - get_valid_token()     Get token, auto-refresh if expired
    - get_user_by_ig_id()   Map Instagram account → user (webhook routing)
    - revoke_user_tokens()  Disconnect user's account
    - list_connected_users() Admin view of all connected accounts
    """
    
    def __init__(self, db_path: Optional[str] = None):
        """
        Initialize TokenManager.
        
        Args:
            db_path: Path to SQLite database file.
                     Defaults to database/alita_oauth.db
        """
        if db_path is None:
            db_dir = Path(__file__).parent.parent / "database"
            db_dir.mkdir(exist_ok=True)
            db_path = str(db_dir / "alita_oauth.db")
        
        self.db_path = db_path
        self._initialized = False
    
    def initialize(self):
        """Create database tables if they don't exist."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Users table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id TEXT PRIMARY KEY,
                email TEXT UNIQUE,
                name TEXT,
                meta_user_id TEXT UNIQUE,
                created_at TEXT DEFAULT (datetime('now')),
                updated_at TEXT DEFAULT (datetime('now')),
                is_active INTEGER DEFAULT 1
            )
        """)
        
        # Tokens table (encrypted storage)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_tokens (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                access_token_encrypted TEXT NOT NULL,
                token_type TEXT DEFAULT 'bearer',
                expires_at REAL,
                scopes TEXT,
                is_long_lived INTEGER DEFAULT 0,
                instagram_account_id TEXT,
                facebook_page_id TEXT,
                created_at TEXT DEFAULT (datetime('now')),
                updated_at TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
            )
        """)
        
        # Account mapping table (for webhook routing)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS account_map (
                instagram_account_id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                instagram_username TEXT,
                facebook_page_id TEXT,
                facebook_page_name TEXT,
                connected_at TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
            )
        """)
        
        # OAuth state tokens (CSRF protection, short-lived)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS oauth_states (
                state TEXT PRIMARY KEY,
                created_at REAL NOT NULL,
                user_id TEXT,
                redirect_after TEXT
            )
        """)
        
        # Session tokens (for web UI login)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                session_id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                created_at REAL NOT NULL,
                expires_at REAL NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
            )
        """)
        
        conn.commit()
        conn.close()
        self._initialized = True
        print(f"✅ Token database initialized at {self.db_path}")
    
    def _ensure_initialized(self):
        if not self._initialized:
            self.initialize()
    
    def _get_conn(self) -> sqlite3.Connection:
        self._ensure_initialized()
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn
    
    # ─── User Management ────────────────────────────────────────────────
    
    def create_user(
        self,
        user_id: str,
        email: Optional[str] = None,
        name: Optional[str] = None,
        meta_user_id: Optional[str] = None,
    ) -> StoredUser:
        """Create or update a user record."""
        conn = self._get_conn()
        now = datetime.now().isoformat()
        
        try:
            conn.execute(
                """INSERT INTO users (user_id, email, name, meta_user_id, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?)
                   ON CONFLICT(user_id) DO UPDATE SET
                       email = COALESCE(excluded.email, email),
                       name = COALESCE(excluded.name, name),
                       meta_user_id = COALESCE(excluded.meta_user_id, meta_user_id),
                       updated_at = excluded.updated_at
                """,
                (user_id, email, name, meta_user_id, now, now),
            )
            conn.commit()
            print(f"✅ User created/updated: {user_id}")
            return StoredUser(
                user_id=user_id,
                email=email,
                name=name,
                meta_user_id=meta_user_id,
                created_at=now,
                updated_at=now,
            )
        finally:
            conn.close()
    
    def get_user(self, user_id: str) -> Optional[StoredUser]:
        """Get a user by user_id."""
        conn = self._get_conn()
        try:
            row = conn.execute(
                "SELECT * FROM users WHERE user_id = ?", (user_id,)
            ).fetchone()
            if row:
                return StoredUser(
                    user_id=row["user_id"],
                    email=row["email"],
                    name=row["name"],
                    meta_user_id=row["meta_user_id"],
                    created_at=row["created_at"],
                    updated_at=row["updated_at"],
                    is_active=bool(row["is_active"]),
                )
            return None
        finally:
            conn.close()
    
    def get_user_by_meta_id(self, meta_user_id: str) -> Optional[StoredUser]:
        """Find a user by their Meta/Facebook user ID."""
        conn = self._get_conn()
        try:
            row = conn.execute(
                "SELECT * FROM users WHERE meta_user_id = ?", (meta_user_id,)
            ).fetchone()
            if row:
                return StoredUser(
                    user_id=row["user_id"],
                    email=row["email"],
                    name=row["name"],
                    meta_user_id=row["meta_user_id"],
                    created_at=row["created_at"],
                    updated_at=row["updated_at"],
                    is_active=bool(row["is_active"]),
                )
            return None
        finally:
            conn.close()
    
    # ─── Token Storage ──────────────────────────────────────────────────
    
    def store_token(
        self,
        user_id: str,
        access_token: str,
        expires_at: Optional[float] = None,
        scopes: Optional[List[str]] = None,
        is_long_lived: bool = False,
        instagram_account_id: Optional[str] = None,
        facebook_page_id: Optional[str] = None,
    ) -> bool:
        """
        Store an encrypted OAuth token for a user.
        
        Replaces any existing token for this user. Only one active token
        per user is supported (simplifies token management).
        
        Args:
            user_id: User identifier
            access_token: The OAuth access token (will be encrypted)
            expires_at: Unix timestamp of token expiry
            scopes: List of granted permission scopes
            is_long_lived: Whether this is a long-lived token
            instagram_account_id: Linked Instagram Business Account ID
            facebook_page_id: Linked Facebook Page ID
            
        Returns:
            True if stored successfully
        """
        conn = self._get_conn()
        now = datetime.now().isoformat()
        
        try:
            # Encrypt the access token
            encrypted_token = encrypt_value(access_token)
            scopes_str = ",".join(scopes) if scopes else None
            
            # Remove existing tokens for this user (one token per user)
            conn.execute("DELETE FROM user_tokens WHERE user_id = ?", (user_id,))
            
            # Insert new token
            conn.execute(
                """INSERT INTO user_tokens 
                   (user_id, access_token_encrypted, token_type, expires_at, 
                    scopes, is_long_lived, instagram_account_id, facebook_page_id,
                    created_at, updated_at)
                   VALUES (?, ?, 'bearer', ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    user_id, encrypted_token, expires_at, scopes_str,
                    1 if is_long_lived else 0,
                    instagram_account_id, facebook_page_id,
                    now, now,
                ),
            )
            conn.commit()
            print(f"✅ Token stored (encrypted) for user {user_id}")
            return True
        except Exception as e:
            print(f"❌ Failed to store token: {e}")
            return False
        finally:
            conn.close()
    
    def get_token(self, user_id: str) -> Optional[StoredToken]:
        """
        Get the decrypted token for a user.

        Checks alita_oauth.db first (fast, local), then falls back to the main
        PostgreSQL MetaOAuthToken table so tokens survive Railway redeploys.

        Args:
            user_id: User identifier (Meta numeric user ID)

        Returns:
            StoredToken with decrypted access_token, or None
        """
        conn = self._get_conn()
        try:
            row = conn.execute(
                "SELECT * FROM user_tokens WHERE user_id = ? ORDER BY created_at DESC LIMIT 1",
                (user_id,),
            ).fetchone()
        finally:
            conn.close()

        if row:
            # Decrypt the access token
            try:
                decrypted_token = decrypt_value(row["access_token_encrypted"])
            except Exception as e:
                print(f"❌ Token decryption failed for user {user_id}: {e}")
                return None

            return StoredToken(
                user_id=row["user_id"],
                access_token=decrypted_token,
                token_type=row["token_type"],
                expires_at=row["expires_at"],
                scopes=row["scopes"],
                is_long_lived=bool(row["is_long_lived"]),
                instagram_account_id=row["instagram_account_id"],
                facebook_page_id=row["facebook_page_id"],
                created_at=row["created_at"],
                updated_at=row["updated_at"],
            )

        # ── Fallback: main PostgreSQL MetaOAuthToken table ────────────────────
        # Needed on Railway after a redeploy wipes alita_oauth.db, but the
        # token was saved to PostgreSQL during the OAuth callback.
        try:
            from database.db import SessionLocal as _SL
            from database.models import MetaOAuthToken as _MOT
            _db = _SL()
            try:
                _tok = _db.query(_MOT).filter(_MOT.meta_user_id == user_id).first()
                if _tok and _tok.access_token_enc:
                    try:
                        _dec = decrypt_value(_tok.access_token_enc)
                    except Exception as _de:
                        print(f"❌ Main-DB token decryption failed for {user_id}: {_de}")
                        return None
                    _expires = float(_tok.expires_at) if _tok.expires_at else None
                    _scopes_str = _tok.scopes or ""
                    return StoredToken(
                        user_id=user_id,
                        access_token=_dec,
                        token_type=_tok.token_type or "bearer",
                        expires_at=_expires,
                        scopes=_scopes_str,
                        is_long_lived=bool(_tok.is_long_lived),
                        instagram_account_id=_tok.ig_account_id,
                        facebook_page_id=_tok.facebook_page_id,
                    )
            finally:
                _db.close()
        except Exception as _fbe:
            print(f"[token_manager] Main-DB fallback failed for {user_id}: {_fbe}")

        return None
    
    def get_valid_token(self, user_id: str) -> Optional[str]:
        """
        Get a valid access token for a user.
        
        Checks expiry and returns None if expired (caller should refresh).
        
        Args:
            user_id: User identifier
            
        Returns:
            Valid access token string, or None if missing/expired
        """
        stored = self.get_token(user_id)
        if not stored:
            return None
        
        if stored.is_expired:
            print(f"⚠️  Token for user {user_id} is expired")
            return None
        
        return stored.access_token
    
    def delete_tokens(self, user_id: str) -> bool:
        """Remove all tokens for a user (disconnect account)."""
        conn = self._get_conn()
        try:
            conn.execute("DELETE FROM user_tokens WHERE user_id = ?", (user_id,))
            conn.execute("DELETE FROM account_map WHERE user_id = ?", (user_id,))
            conn.commit()
            print(f"✅ All tokens removed for user {user_id}")
            return True
        except Exception as e:
            print(f"❌ Failed to delete tokens: {e}")
            return False
        finally:
            conn.close()
    
    # ─── Account Mapping (Webhook Routing) ──────────────────────────────
    
    def map_instagram_account(
        self,
        instagram_account_id: str,
        user_id: str,
        instagram_username: Optional[str] = None,
        facebook_page_id: Optional[str] = None,
        facebook_page_name: Optional[str] = None,
    ) -> bool:
        """
        Map an Instagram Business Account ID to a user.
        
        This mapping is critical for webhook routing: when a webhook arrives
        with an instagram_business_account_id, we use this table to find
        which user's token to use.
        
        Args:
            instagram_account_id: Instagram Business Account ID
            user_id: User who owns this account
            instagram_username: @handle
            facebook_page_id: Connected Facebook Page ID
            facebook_page_name: Connected Facebook Page name
            
        Returns:
            True if mapped successfully
        """
        conn = self._get_conn()
        now = datetime.now().isoformat()
        
        try:
            conn.execute(
                """INSERT INTO account_map 
                   (instagram_account_id, user_id, instagram_username, 
                    facebook_page_id, facebook_page_name, connected_at)
                   VALUES (?, ?, ?, ?, ?, ?)
                   ON CONFLICT(instagram_account_id) DO UPDATE SET
                       user_id = excluded.user_id,
                       instagram_username = COALESCE(excluded.instagram_username, instagram_username),
                       facebook_page_id = COALESCE(excluded.facebook_page_id, facebook_page_id),
                       facebook_page_name = COALESCE(excluded.facebook_page_name, facebook_page_name),
                       connected_at = excluded.connected_at
                """,
                (instagram_account_id, user_id, instagram_username,
                 facebook_page_id, facebook_page_name, now),
            )
            conn.commit()
            username_str = f" (@{instagram_username})" if instagram_username else ""
            print(f"✅ Mapped IG account {instagram_account_id}{username_str} → user {user_id}")
            return True
        except Exception as e:
            print(f"❌ Failed to map account: {e}")
            return False
        finally:
            conn.close()
    
    def get_user_by_instagram_id(self, instagram_account_id: str) -> Optional[str]:
        """
        Look up which user owns an Instagram Business Account.

        Checks alita_oauth.db first, then falls back to the main PostgreSQL
        MetaOAuthToken / ClientProfile tables.

        Args:
            instagram_account_id: Instagram Business Account ID from webhook

        Returns:
            user_id (Meta numeric ID) if found, None otherwise
        """
        conn = self._get_conn()
        try:
            row = conn.execute(
                "SELECT user_id FROM account_map WHERE instagram_account_id = ?",
                (instagram_account_id,),
            ).fetchone()
        finally:
            conn.close()

        if row:
            return row["user_id"]

        # Fallback: main PostgreSQL DB
        try:
            from database.db import SessionLocal as _SL
            from database.models import MetaOAuthToken as _MOT
            _db = _SL()
            try:
                _tok = _db.query(_MOT).filter(
                    _MOT.ig_account_id == instagram_account_id
                ).first()
                if _tok:
                    return _tok.meta_user_id
            finally:
                _db.close()
        except Exception:
            pass
        return None

    def get_user_by_facebook_page_id(self, facebook_page_id: str) -> Optional[str]:
        """Look up which user owns a connected Facebook Page ID."""
        conn = self._get_conn()
        try:
            row = conn.execute(
                "SELECT user_id FROM account_map WHERE facebook_page_id = ?",
                (str(facebook_page_id),),
            ).fetchone()
        finally:
            conn.close()

        if row:
            return row["user_id"]

        # Fallback: main PostgreSQL DB
        try:
            from database.db import SessionLocal as _SL
            from database.models import MetaOAuthToken as _MOT
            _db = _SL()
            try:
                _tok = _db.query(_MOT).filter(
                    _MOT.facebook_page_id == str(facebook_page_id)
                ).first()
                if _tok:
                    return _tok.meta_user_id
            finally:
                _db.close()
        except Exception:
            pass
        return None
    
    def get_token_by_instagram_id(self, instagram_account_id: str) -> Optional[str]:
        """
        Get the access token for a given Instagram Business Account ID.
        
        Shortcut for webhook routing: IG account → user → token, in one call.
        
        Args:
            instagram_account_id: Instagram Business Account ID from webhook
            
        Returns:
            Decrypted access token, or None
        """
        user_id = self.get_user_by_instagram_id(instagram_account_id)
        if not user_id:
            return None
        return self.get_valid_token(user_id)

    def get_token_by_facebook_page_id(self, facebook_page_id: str) -> Optional[str]:
        """Get the access token for the user that connected a given Facebook Page ID."""
        user_id = self.get_user_by_facebook_page_id(str(facebook_page_id))
        if not user_id:
            return None
        return self.get_valid_token(user_id)
    
    # ─── OAuth State Management ─────────────────────────────────────────
    
    def store_oauth_state(
        self, state: str, user_id: Optional[str] = None,
        redirect_after: Optional[str] = None
    ) -> bool:
        """Store an OAuth state token for CSRF verification."""
        conn = self._get_conn()
        try:
            conn.execute(
                "INSERT INTO oauth_states (state, created_at, user_id, redirect_after) VALUES (?, ?, ?, ?)",
                (state, time.time(), user_id, redirect_after),
            )
            conn.commit()
            return True
        finally:
            conn.close()
    
    def verify_and_consume_state(self, state: str) -> Optional[Dict[str, Any]]:
        """
        Verify an OAuth state token and remove it (one-time use).
        
        Returns:
            Dict with user_id and redirect_after if valid, None if invalid/expired
        """
        conn = self._get_conn()
        try:
            row = conn.execute(
                "SELECT * FROM oauth_states WHERE state = ?", (state,)
            ).fetchone()
            
            if not row:
                return None
            
            # Check expiry (15 minutes max)
            if time.time() - row["created_at"] > 900:
                conn.execute("DELETE FROM oauth_states WHERE state = ?", (state,))
                conn.commit()
                return None
            
            # Consume (delete) the state
            conn.execute("DELETE FROM oauth_states WHERE state = ?", (state,))
            conn.commit()
            
            return {
                "user_id": row["user_id"],
                "redirect_after": row["redirect_after"],
            }
        finally:
            conn.close()
    
    def cleanup_expired_states(self):
        """Remove expired OAuth state tokens (older than 15 minutes)."""
        conn = self._get_conn()
        try:
            cutoff = time.time() - 900
            conn.execute("DELETE FROM oauth_states WHERE created_at < ?", (cutoff,))
            conn.commit()
        finally:
            conn.close()
    
    # ─── Session Management ─────────────────────────────────────────────
    
    def create_session(self, user_id: str, duration_hours: int = 24) -> str:
        """
        Create a new session for a logged-in user.
        
        Args:
            user_id: User identifier
            duration_hours: Session duration in hours (default 24h)
            
        Returns:
            Session token string
        """
        session_id = secrets.token_urlsafe(32)
        now = time.time()
        expires = now + (duration_hours * 3600)
        
        conn = self._get_conn()
        try:
            conn.execute(
                "INSERT INTO sessions (session_id, user_id, created_at, expires_at) VALUES (?, ?, ?, ?)",
                (session_id, user_id, now, expires),
            )
            conn.commit()
            return session_id
        finally:
            conn.close()
    
    def get_session_user(self, session_id: str) -> Optional[str]:
        """
        Get the user_id for a valid session.
        
        Args:
            session_id: Session token from cookie
            
        Returns:
            user_id if session is valid and not expired, None otherwise
        """
        conn = self._get_conn()
        try:
            row = conn.execute(
                "SELECT user_id, expires_at FROM sessions WHERE session_id = ?",
                (session_id,),
            ).fetchone()
            
            if not row:
                return None
            
            if time.time() > row["expires_at"]:
                # Expired session
                conn.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))
                conn.commit()
                return None
            
            return row["user_id"]
        finally:
            conn.close()
    
    def delete_session(self, session_id: str):
        """Delete a session (logout)."""
        conn = self._get_conn()
        try:
            conn.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))
            conn.commit()
        finally:
            conn.close()
    
    def cleanup_expired_sessions(self):
        """Remove expired sessions."""
        conn = self._get_conn()
        try:
            conn.execute("DELETE FROM sessions WHERE expires_at < ?", (time.time(),))
            conn.commit()
        finally:
            conn.close()
    
    # ─── Admin / Listing ────────────────────────────────────────────────
    
    def list_connected_users(self) -> List[Dict[str, Any]]:
        """List all users with connected Instagram accounts."""
        conn = self._get_conn()
        try:
            rows = conn.execute(
                """SELECT u.user_id, u.email, u.name, u.meta_user_id, u.created_at,
                          am.instagram_account_id, am.instagram_username, 
                          am.facebook_page_name, am.connected_at,
                          ut.expires_at, ut.is_long_lived, ut.scopes
                   FROM users u
                   LEFT JOIN account_map am ON u.user_id = am.user_id
                   LEFT JOIN user_tokens ut ON u.user_id = ut.user_id
                   WHERE u.is_active = 1
                   ORDER BY u.created_at DESC
                """
            ).fetchall()
            
            return [
                {
                    "user_id": row["user_id"],
                    "email": row["email"],
                    "name": row["name"],
                    "meta_user_id": row["meta_user_id"],
                    "instagram_account_id": row["instagram_account_id"],
                    "instagram_username": row["instagram_username"],
                    "facebook_page_name": row["facebook_page_name"],
                    "connected_at": row["connected_at"],
                    "token_expires_at": row["expires_at"],
                    "token_is_expired": (
                        time.time() > row["expires_at"]
                        if row["expires_at"]
                        else None
                    ),
                    "is_long_lived": bool(row["is_long_lived"]) if row["is_long_lived"] is not None else None,
                    "scopes": row["scopes"],
                }
                for row in rows
            ]
        finally:
            conn.close()
    
    def get_stats(self) -> Dict[str, int]:
        """Get database statistics."""
        conn = self._get_conn()
        try:
            users = conn.execute("SELECT COUNT(*) as c FROM users").fetchone()["c"]
            tokens = conn.execute("SELECT COUNT(*) as c FROM user_tokens").fetchone()["c"]
            accounts = conn.execute("SELECT COUNT(*) as c FROM account_map").fetchone()["c"]
            sessions = conn.execute(
                "SELECT COUNT(*) as c FROM sessions WHERE expires_at > ?",
                (time.time(),),
            ).fetchone()["c"]
            
            return {
                "total_users": users,
                "active_tokens": tokens,
                "linked_accounts": accounts,
                "active_sessions": sessions,
            }
        finally:
            conn.close()
