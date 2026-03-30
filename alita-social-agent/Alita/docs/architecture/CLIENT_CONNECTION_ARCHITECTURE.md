# How Your Multi-Tenant Client Connections Work

## What You Currently Have ✅

You have a **multi-tenant architecture** where each client can connect their own Twitter, TikTok, and YouTube accounts. Here's how it works:

---

## Current Architecture

### 1. Late API Profile IDs (Twitter & TikTok)

Your `.env` file stores profile IDs per client:

```env
# Late API Profile IDs for default_client
LATE_PROFILE_TIKTOK_default_client=697b090c77637c5c857cbbc8
LATE_PROFILE_LINKEDIN_default_client=697b0a7877637c5c857cbbd2
LATE_PROFILE_TWITTER_default_client=697b093a77637c5c857cbbc9
```

**How it works:**
- Each client has a unique `client_id` (e.g., `default_client`, `client_123`, `client_456`)
- For each client, you store their Late API profile IDs in environment variables
- Pattern: `LATE_PROFILE_{PLATFORM}_{client_id}`

### 2. Posting Agent Loads Profile IDs

In `agents/posting_agent.py` (lines 159-175):

```python
def _load_platform_profiles(self) -> Dict[str, str]:
    """Load platform profile IDs for this client."""
    return {
        "tiktok": os.getenv(f"LATE_PROFILE_TIKTOK_{self.client_id}", ""),
        "linkedin": os.getenv(f"LATE_PROFILE_LINKEDIN_{self.client_id}", ""),
        "twitter": os.getenv(f"LATE_PROFILE_TWITTER_{self.client_id}", ""),
        "threads": os.getenv(f"LATE_PROFILE_THREADS_{self.client_id}", ""),
        "reddit": os.getenv(f"LATE_PROFILE_REDDIT_{self.client_id}", ""),
        "pinterest": os.getenv(f"LATE_PROFILE_PINTEREST_{self.client_id}", ""),
        "bluesky": os.getenv(f"LATE_PROFILE_BLUESKY_{self.client_id}", ""),
    }
```

**What this means:**
- When you create a PostingAgent for a client: `PostingAgent(client_id="client_123")`
- It automatically loads THEIR profile IDs from `.env`
- When posting to Twitter/TikTok, it uses THEIR Late API profile ID

---

## How Clients Connect Their Accounts

### Current Method (Environment Variables):

**For each new client:**

1. **Client connects in Late API dashboard:**
   - Client logs into https://app.getlate.dev (or you do it for them)
   - Clicks "Add Profile"
   - Selects Twitter, TikTok, LinkedIn, etc.
   - Authorizes with THEIR account
   - Late API generates a `profile_id`

2. **You add to .env file:**
   ```env
   # Client: John Doe (client_johndoe)
   LATE_PROFILE_TWITTER_client_johndoe=late_prof_abc123
   LATE_PROFILE_TIKTOK_client_johndoe=late_prof_xyz789
   
   # Client: Jane Smith (client_janesmith)
   LATE_PROFILE_TWITTER_client_janesmith=late_prof_def456
   LATE_PROFILE_TIKTOK_client_janesmith=late_prof_uvw012
   ```

3. **Your app posts on their behalf:**
   ```python
   # Post for John Doe
   agent = PostingAgent(client_id="client_johndoe")
   await agent.post_content(ContentPost(
       content="Check out my new product!",
       platform="twitter",
       client_id="client_johndoe"
   ))
   # This automatically uses john's Twitter profile ID
   ```

---

## The Problem You're Worried About

**Issue:** Storing profile IDs in `.env` doesn't scale for many clients.

**Why it's a problem:**
- .env file gets massive with 100+ clients
- Manually adding profile IDs for each client is tedious
- No self-service for clients to connect accounts
- Security: all credentials in one file

---

## The Solution: Database + OAuth Dashboard

### What You Need to Build

**1. Database Table for Client Connections:**

```sql
CREATE TABLE client_platform_connections (
    id INT PRIMARY KEY AUTO_INCREMENT,
    app_user_id INT NOT NULL,              -- Your app's user ID (e.g., 123)
    client_id VARCHAR(100) NOT NULL,       -- Your client identifier (e.g., "client_johndoe")
    platform VARCHAR(50) NOT NULL,         -- 'twitter', 'tiktok', 'linkedin', 'youtube'
    late_profile_id VARCHAR(200),          -- For Late API platforms
    youtube_refresh_token TEXT,            -- For YouTube OAuth
    platform_username VARCHAR(100),        -- Their @handle
    platform_user_id VARCHAR(100),         -- Platform's user ID
    connected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    status VARCHAR(20) DEFAULT 'active',   -- 'active', 'expired', 'revoked'
    UNIQUE(client_id, platform)
);
```

**Example data:**
| app_user_id | client_id | platform | late_profile_id | platform_username |
|-------------|-----------|----------|-----------------|-------------------|
| 123 | client_johndoe | twitter | late_prof_abc123 | @johndoe |
| 123 | client_johndoe | tiktok | late_prof_xyz789 | johndoe_tiktok |
| 456 | client_janesmith | twitter | late_prof_def456 | @janesmith |

**2. Late API OAuth Flow (For Twitter/TikTok):**

You don't need to build OAuth yourself! Late API has a **Share Link** feature:

```python
# In your web dashboard
@router.get("/connect/late-api")
async def connect_late_api(client_id: str):
    """Generate Late API connection link for client."""
    
    # Late API provides a share link that clients click
    # They authorize their accounts directly with Late
    # Late sends webhook with profile_id
    
    late_share_link = f"https://app.getlate.dev/share?workspace={YOUR_WORKSPACE_ID}"
    
    return HTMLResponse(f"""
        <h1>Connect Your Social Accounts</h1>
        <p>Click below to connect Twitter, TikTok, LinkedIn:</p>
        <a href="{late_share_link}" target="_blank">
            <button>Connect via Late API</button>
        </a>
        <p>After connecting, we'll automatically sync your accounts.</p>
    """)
```

**Late API Webhook** (when client connects):
```python
@router.post("/webhooks/late-api/profile-connected")
async def late_profile_connected(webhook_data: dict):
    """Late API sends this when client connects account."""
    
    profile_id = webhook_data["profile_id"]
    platform = webhook_data["platform"]  # 'twitter', 'tiktok', etc.
    username = webhook_data["username"]
    
    # Store in database
    db.execute("""
        INSERT INTO client_platform_connections 
        (client_id, platform, late_profile_id, platform_username)
        VALUES (?, ?, ?, ?)
    """, (current_client_id, platform, profile_id, username))
    
    return {"status": "success"}
```

**3. Update PostingAgent to Use Database:**

```python
def _load_platform_profiles(self) -> Dict[str, str]:
    """Load platform profile IDs from database."""
    
    # Query database instead of env vars
    profiles = db.query("""
        SELECT platform, late_profile_id
        FROM client_platform_connections
        WHERE client_id = ? AND status = 'active'
    """, (self.client_id,))
    
    return {row['platform']: row['late_profile_id'] for row in profiles}
```

---

## YouTube is Different (Direct OAuth)

For YouTube, you need actual OAuth because it's not via Late API:

**1. Client Dashboard with OAuth Button:**

```python
@router.get("/connect/youtube")
async def connect_youtube(client_id: str):
    """Initiate YouTube OAuth for client."""
    
    google_oauth_url = (
        "https://accounts.google.com/o/oauth2/v2/auth?"
        f"client_id={GOOGLE_CLIENT_ID}&"
        f"redirect_uri={YOUTUBE_CALLBACK_URL}&"
        f"response_type=code&"
        f"scope=https://www.googleapis.com/auth/youtube.readonly&"
        f"access_type=offline&"
        f"state={client_id}"  # Pass client_id in state
    )
    
    return RedirectResponse(google_oauth_url)

@router.get("/connect/youtube/callback")
async def youtube_callback(code: str, state: str):
    """Handle YouTube OAuth callback."""
    
    client_id = state  # Extract client_id from state
    
    # Exchange code for tokens
    token_response = httpx.post("https://oauth2.googleapis.com/token", data={
        "code": code,
        "client_id": GOOGLE_CLIENT_ID,
        "client_secret": GOOGLE_CLIENT_SECRET,
        "redirect_uri": YOUTUBE_CALLBACK_URL,
        "grant_type": "authorization_code"
    })
    
    tokens = token_response.json()
    refresh_token = tokens["refresh_token"]
    
    # Get channel info
    channel_info = get_youtube_channel_info(tokens["access_token"])
    
    # Store in database
    db.execute("""
        INSERT INTO client_platform_connections
        (client_id, platform, youtube_refresh_token, platform_username)
        VALUES (?, 'youtube', ?, ?)
    """, (client_id, refresh_token, channel_info["channel_title"]))
    
    return HTMLResponse("<h1>✅ YouTube Connected!</h1>")
```

---

## What You Need to Do

### Phase 1: Keep Using .env (Current - Works Fine for Now)
✅ You're already doing this
✅ Works perfectly for 1-10 clients
✅ No code changes needed

### Phase 2: Build Database Storage (When You Have 10+ Clients)
1. Create `client_platform_connections` table
2. Build admin page to manually add profile IDs
3. Update `PostingAgent._load_platform_profiles()` to read from database
4. Migrate existing .env entries to database

### Phase 3: Self-Service OAuth (When You Have 50+ Clients)
1. Build client dashboard with "Connect Account" buttons
2. Implement Late API webhook for profile connections
3. Build YouTube OAuth flow (for YouTube uploads)
4. Let clients connect their own accounts

---

## Quick Answer to Your Question

**"How will my clients connect their Twitter, TikTok, and YouTube?"**

**Currently (what you have):**
- You connect client accounts FOR them via Late API dashboard
- You manually add profile IDs to .env file
- Works great for 1-10 clients

**Future (what you'll build):**
- Clients click "Connect Twitter" in YOUR dashboard
- For Twitter/TikTok: Redirects to Late API → They authorize → Webhook sends you profile_id
- For YouTube: Standard OAuth flow → They authorize → You store refresh_token
- Everything saved in database automatically

---

## Files You'd Create

**1. `api/client_connections_routes.py`**
- Dashboard showing connected accounts
- "Connect Twitter/TikTok" button → Late API share link
- "Connect YouTube" button → OAuth flow
- Display connected accounts with status

**2. `api/late_webhooks.py`**
- Handle Late API profile connection webhooks
- Store profile_ids in database

**3. `database/migrations/add_client_connections.sql`**
- Create client_platform_connections table

**4. Update `agents/posting_agent.py`**
- Change `_load_platform_profiles()` to query database instead of .env

---

## You're Already 90% There!

Your current `.env` approach IS the multi-tenant architecture - it just stores data in .env instead of database.

**What you have:** ✅ Working multi-tenant system
**What you're missing:** Self-service client connection UI

For now, keep using .env. When you have 10+ clients, migrate to database. When you have 50+ clients, build self-service dashboard.

**You don't need to change anything right now - your system already works!** 🎉
