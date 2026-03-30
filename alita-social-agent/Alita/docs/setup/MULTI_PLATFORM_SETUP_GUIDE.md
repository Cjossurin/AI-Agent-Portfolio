# Multi-Platform Setup Guide: Late API + YouTube

## Overview
Your architecture uses:
- **Late API** → Twitter/X + TikTok + LinkedIn posting (multi-platform service)
- **YouTube API** → Direct YouTube integration for analytics

**Current Setup:** Client accounts connect via Late API dashboard, profile IDs stored in .env
**See Also:** [CLIENT_CONNECTION_ARCHITECTURE.md](CLIENT_CONNECTION_ARCHITECTURE.md) for detailed multi-tenant explanation

---

## Architecture Flow

### How Clients Connect Their Accounts

```
Client → Your App → Late API Dashboard → Client Authorizes Twitter/TikTok/YouTube
                                       ↓
                            Late API Profile IDs Created
                                       ↓
                            You Use Profile IDs to Post
```

**Key Point:** Clients connect their accounts **directly in Late API dashboard**, not through your OAuth flow. You simply use their profile IDs when posting.

---

## 1. Late API Setup (Twitter + TikTok)

### Step 1: Create Late Account
1. Go to [getlate.dev](https://getlate.dev)
2. Sign up for an account
3. Choose **Accelerate tier** ($33/month) for API access

### Step 2: Connect Your Master Account (Optional)
1. In Late dashboard, click **Add Profile**
2. Select **Twitter/X**
3. Authorize Late to access your Twitter
4. Repeat for **TikTok**

### Step 3: Get API Credentials
1. Go to **Settings** → **API Keys**
2. Generate a new API key
3. Copy the key

### Step 4: Add to .env
```env
LATE_API_KEY=your_late_api_key_here
LATE_API_BASE_URL=https://api.getlate.dev/v1
```

### Step 5: How Clients Connect
**Your clients connect THEIR accounts directly in Late API dashboard:**

1. Give client access to your Late API workspace (invite them)
2. They click **Add Profile** in Late dashboard
3. They select Twitter or TikTok
4. They authorize with **their own account**
5. Late API creates a **profile_id** for that connection
6. You store `{client_user_id: profile_id}` in your database
7. When posting for that client, use their profile_id

### Late API Posting Example
```python
from api.late_client import LateClient

late = LateClient(api_key=os.getenv("LATE_API_KEY"))

# Post to client's Twitter
response = await late.post({
    "platform": "twitter",
    "profile_id": "client_twitter_profile_id",  # From your database
    "content": "Hello from my client's account!",
    "media_urls": ["https://example.com/image.jpg"]
})
```

---

## 2. YouTube API Setup (Direct Integration)

### Step 1: Create Google Cloud Project
1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project: "My Social Media App"

### Step 2: Enable YouTube Data API
1. Go to **APIs & Services** → **Library**
2. Search for **YouTube Data API v3**
3. Click **Enable**

### Step 3: Create API Key (For Read-Only)
1. Go to **APIs & Services** → **Credentials**
2. Click **Create Credentials** → **API key**
3. Copy the API key
4. (Optional) Restrict to YouTube Data API v3

### Step 4: Add to .env
```env
YOUTUBE_API_KEY=your_youtube_api_key_here
YOUTUBE_CHANNEL_ID=your_channel_id_here
```

### For Posting to YouTube (OAuth Required)
If you need to **upload videos** on behalf of clients:

1. Create **OAuth 2.0 Client ID**:
   - Application type: **Web application**
   - Authorized redirect URIs: `http://localhost:8000/auth/youtube/callback`
   
2. Add to .env:
```env
GOOGLE_CLIENT_ID=your_client_id.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=your_client_secret
```

3. Each client authorizes your app to access their YouTube channel
4. Store refresh_token per client in database
5. Use refresh_token to upload videos on their behalf

---

## Complete .env Configuration

```env
# ─── Late API (Twitter + TikTok) ────────────────────────────
LATE_API_KEY=your_late_api_key_from_getlate_dev
LATE_API_BASE_URL=https://api.getlate.dev/v1

# ─── YouTube API (Read-Only) ────────────────────────────────
YOUTUBE_API_KEY=your_youtube_api_key_from_google_cloud
YOUTUBE_CHANNEL_ID=your_youtube_channel_id

# ─── YouTube OAuth (For Uploading - Optional) ──────────────
GOOGLE_CLIENT_ID=your_client_id.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=your_client_secret

# ─── Facebook & Instagram (Already configured) ─────────────
META_APP_ID=your_existing_app_id
META_APP_SECRET=your_existing_app_secret
META_ACCESS_TOKEN=your_existing_access_token
```

---

## Multi-Tenant Database Schema

Store client connections in your database:

```sql
CREATE TABLE client_social_profiles (
    id INT PRIMARY KEY AUTO_INCREMENT,
    app_user_id INT,  -- Your app's internal user ID
    platform VARCHAR(20),  -- 'twitter', 'tiktok', 'youtube'
    late_profile_id VARCHAR(100),  -- For Twitter/TikTok via Late API
    youtube_refresh_token TEXT,  -- For YouTube OAuth
    platform_username VARCHAR(100),
    connected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(app_user_id, platform)
);
```

**Example data:**
```
| app_user_id | platform | late_profile_id | youtube_refresh_token | platform_username |
|-------------|----------|-----------------|----------------------|-------------------|
| 123         | twitter  | late_prof_abc123| NULL                 | @johndoe          |
| 123         | tiktok   | late_prof_xyz789| NULL                 | johndoetiktok     |
| 123         | youtube  | NULL            | ya29.refresh_token   | JohnDoeChannel    |
```

---

## Testing Your Setup

### Test Late API
```bash
# Check Late API status
curl http://localhost:8000/social/late-api/status

# Post to Twitter (replace profile_id)
python test_late_api.py
```

### Test YouTube API
```bash
# Get channel info
curl http://localhost:8000/social/youtube/channel

# Get trending videos
curl http://localhost:8000/social/youtube/trending?max_results=10
```

---

## How It All Works Together

### Posting Workflow:

1. **Client Request:** User clicks "Post to Twitter"
2. **Lookup Profile:** Query database for client's `late_profile_id`
3. **Call Late API:**
   ```python
   await late_client.post({
       "platform": "twitter",
       "profile_id": client_late_profile_id,
       "content": post_content
   })
   ```
4. **Late API handles:** Authentication, posting, error handling
5. **Return Status:** Success/failure to your app

### Reading Workflow (YouTube):

1. **Client Request:** "Show my YouTube analytics"
2. **Call YouTube API:**
   ```python
   await youtube_client.get_video_analytics(video_id)
   ```
3. **Return Data:** Views, likes, comments, etc.

---

## Supported Platforms Summary

| Platform | Method | What You Need | Client Setup |
|----------|--------|---------------|--------------|
| **Twitter** | Late API | Late API key | Connect in Late dashboard |
| **TikTok** | Late API | Late API key | Connect in Late dashboard |
| **YouTube** | Direct API | YouTube API key | N/A (read-only) |
| **YouTube Upload** | OAuth | Google OAuth credentials | Authorize your app |
| **Facebook** | Direct API | Meta app credentials | OAuth (already done) |
| **Instagram** | Direct API | Meta app credentials | OAuth (already done) |
| **Threads** | Late API | Late API key | Connect in Late dashboard |
| **LinkedIn** | Late API | Late API key | Connect in Late dashboard |
| **Reddit** | Late API | Late API key | Connect in Late dashboard |

---

## Cost Breakdown

| Service | Tier | Monthly Cost |
|---------|------|--------------|
| **Late API** | Accelerate | $33 |
| **YouTube API** | Free tier | $0 (up to 10k quota/day) |
| **Google Cloud** | Pay-as-you-go | ~$0-5 |
| **Total** | | **~$33-38/month** |

---

## Next Steps

1. **Immediate:**
   - Sign up for Late API ($33/month)
   - Create Google Cloud project (free)
   - Add API keys to .env
   - Restart server

2. **For Client Connections:**
   - Invite clients to Late API workspace
   - Have them connect Twitter/TikTok accounts
   - Store their profile_ids in your database
   - Test posting on their behalf

3. **For YouTube Uploads:**
   - Set up OAuth 2.0 credentials
   - Build authorization flow for clients
   - Store refresh_tokens per client
   - Implement upload functionality

---

## Resources

- **Late API Docs:** https://docs.getlate.dev
- **Late API Dashboard:** https://app.getlate.dev
- **YouTube API Docs:** https://developers.google.com/youtube/v3
- **Google Cloud Console:** https://console.cloud.google.com

---

## Security Best Practices

✅ **DO:**
- Store Late API key in .env (never commit)
- Encrypt database tokens
- Use HTTPS in production
- Rotate API keys periodically
- Validate all client inputs

❌ **DON'T:**
- Share API keys publicly
- Store credentials in code
- Mix dev and production keys
- Give clients direct API access

---

**You're using the right architecture!** Late API handles the OAuth complexity for Twitter/TikTok, and YouTube API gives you direct access for analytics. This is much simpler than building custom OAuth for every platform! 🚀
