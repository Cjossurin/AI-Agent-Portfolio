# OAuth Setup Guide for Twitter, TikTok, and YouTube

## Overview
This guide walks you through setting up OAuth 2.0 for Twitter/X, TikTok, and YouTube so your **clients** can connect their own accounts to your application.

## Prerequisites
- Your app running at `http://localhost:8000` (or your production URL)
- Developer accounts on Twitter, TikTok, and Google

---

## 1. Twitter/X OAuth Setup

### Step 1: Create Twitter Developer Account
1. Go to [Twitter Developer Portal](https://developer.twitter.com/)
2. Sign in with your Twitter account
3. Apply for developer access if you haven't already
4. Create a new **Project** and **App**

### Step 2: Configure OAuth 2.0 Settings
1. In your app dashboard, go to **App Settings** → **User authentication settings**
2. Click **Set up** under OAuth 2.0
3. Configure the following:
   - **App permissions**: Read and Write
   - **Type of App**: Web App
   - **Callback URL / Redirect URL**: `http://localhost:8000/connect/twitter/callback`
   - **Website URL**: `http://localhost:8000`
   
4. Save settings

### Step 3: Get Your Credentials
1. Go to **Keys and tokens** tab
2. Copy your:
   - **Client ID** (OAuth 2.0)
   - **Client Secret** (OAuth 2.0)
3. Add to your `.env` file:
```env
TWITTER_CLIENT_ID=your_client_id_here
TWITTER_CLIENT_SECRET=your_client_secret_here
TWITTER_REDIRECT_URI=http://localhost:8000/connect/twitter/callback
```

### Production Setup
For production, update:
- Callback URL: `https://yourdomain.com/connect/twitter/callback`
- Website URL: `https://yourdomain.com`
- Redirect URI in .env: `https://yourdomain.com/connect/twitter/callback`

---

## 2. TikTok OAuth Setup

### Step 1: Create TikTok Developer Account
1. Go to [TikTok for Developers](https://developers.tiktok.com/)
2. Sign up/login with your TikTok account
3. Complete developer registration

### Step 2: Create an App
1. In the developer dashboard, click **Manage Apps**
2. Click **Create an App** or **Connect an App**
3. Fill in app details:
   - **App name**: Your app name
   - **Category**: Social or appropriate category
   
### Step 3: Configure OAuth Settings
1. Go to **Login Kit** settings
2. Add **Redirect URI**: `http://localhost:8000/connect/tiktok/callback`
3. Select scopes you need:
   - `user.info.basic` (required)
   - `video.list`
   - `video.upload` (if posting videos)

### Step 4: Get Your Credentials
1. In app dashboard, find:
   - **Client Key**
   - **Client Secret**
2. Add to your `.env` file:
```env
TIKTOK_CLIENT_KEY=your_client_key_here
TIKTOK_CLIENT_SECRET=your_client_secret_here
TIKTOK_REDIRECT_URI=http://localhost:8000/connect/tiktok/callback
```

### Production Setup
Update redirect URI to: `https://yourdomain.com/connect/tiktok/callback`

---

## 3. YouTube (Google) OAuth Setup

### Step 1: Create Google Cloud Project
1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project or select existing one
3. Name it something like "My Social Media App"

### Step 2: Enable YouTube Data API
1. In the sidebar, go to **APIs & Services** → **Library**
2. Search for **YouTube Data API v3**
3. Click **Enable**

### Step 3: Create OAuth Credentials
1. Go to **APIs & Services** → **Credentials**
2. Click **Create Credentials** → **OAuth client ID**
3. If prompted, configure OAuth consent screen first:
   - User Type: **External**
   - App name: Your app name
   - Support email: Your email
   - Add scopes: `youtube.readonly`, `youtube.upload`
   
4. Back to creating OAuth client ID:
   - Application type: **Web application**
   - Name: Your app name
   - Authorized redirect URIs: `http://localhost:8000/connect/youtube/callback`

### Step 4: Get Your Credentials
1. After creating, you'll see:
   - **Client ID**
   - **Client Secret**
2. Add to your `.env` file:
```env
GOOGLE_CLIENT_ID=your_client_id_here
GOOGLE_CLIENT_SECRET=your_client_secret_here
GOOGLE_REDIRECT_URI=http://localhost:8000/connect/youtube/callback
```

### Production Setup
- Add production redirect URI: `https://yourdomain.com/connect/youtube/callback`
- Update consent screen with production details
- Submit for verification if using sensitive scopes

---

## Complete .env Example

Create/update your `.env` file with ALL OAuth credentials:

```env
# ─── Twitter OAuth ───────────────────────────────────────────
TWITTER_CLIENT_ID=your_twitter_client_id
TWITTER_CLIENT_SECRET=your_twitter_client_secret
TWITTER_REDIRECT_URI=http://localhost:8000/connect/twitter/callback

# ─── TikTok OAuth ────────────────────────────────────────────
TIKTOK_CLIENT_KEY=your_tiktok_client_key
TIKTOK_CLIENT_SECRET=your_tiktok_client_secret
TIKTOK_REDIRECT_URI=http://localhost:8000/connect/tiktok/callback

# ─── YouTube OAuth ───────────────────────────────────────────
GOOGLE_CLIENT_ID=your_google_client_id.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=your_google_client_secret
GOOGLE_REDIRECT_URI=http://localhost:8000/connect/youtube/callback

# ─── Existing API Keys (if you have them) ───────────────────
TWITTER_API_KEY=your_twitter_api_key
TWITTER_API_SECRET=your_twitter_api_secret
TIKTOK_ACCESS_TOKEN=your_tiktok_token
YOUTUBE_API_KEY=your_youtube_api_key
```

---

## Testing Your OAuth Setup

### Step 1: Start Your Server
```bash
uvicorn web_app:app --reload
```

### Step 2: Visit Connection Dashboard
Open your browser to: `http://localhost:8000/connect/dashboard`

### Step 3: Test Each Platform
1. **Twitter**: Click "Connect Twitter/X" → Popup opens → Authorize → Success message
2. **TikTok**: Click "Connect TikTok" → Popup opens → Authorize → Success message
3. **YouTube**: Click "Connect YouTube" → Popup opens → Select Google account → Authorize → Success message

### Step 4: Verify Storage
Check your browser console (F12) → Application → Local Storage:
- `twitter_connected`: true
- `tiktok_connected`: true
- `youtube_connected`: true

---

## How Client Connections Work

### Multi-Tenant Architecture Flow:
1. **Your client** logs into your app
2. They visit `/connect/dashboard`
3. They click "Connect Twitter" (or TikTok/YouTube)
4. OAuth popup opens → They authorize with **their own** account
5. Your app receives:
   - Access token
   - Refresh token
   - User info (username, user_id, etc.)
6. You store this in your database associated with **your client's user_id**
7. When your client wants to post, you use **their** tokens

### Database Schema (Recommended):
```sql
CREATE TABLE user_connections (
    id INT PRIMARY KEY AUTO_INCREMENT,
    app_user_id INT,  -- Your app's user ID
    platform VARCHAR(20),  -- 'twitter', 'tiktok', 'youtube'
    platform_user_id VARCHAR(100),
    username VARCHAR(100),
    access_token TEXT,
    refresh_token TEXT,
    expires_at TIMESTAMP,
    connected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(app_user_id, platform)
);
```

---

## Troubleshooting

### "Redirect URI mismatch"
- Ensure redirect URI in developer portal **exactly matches** the one in your .env
- Include `http://` or `https://`
- Match port numbers
- No trailing slashes

### "Invalid client credentials"
- Double-check you copied the correct Client ID/Secret
- Check for extra spaces or newlines in .env file
- Regenerate credentials if needed

### "Popup blocked"
- Allow popups in browser settings for localhost
- Use a modern browser (Chrome, Firefox, Edge)

### "Scope permission denied"
- Ensure you requested the correct scopes in developer portal
- Some scopes require app review/verification

---

## Next Steps After Setup

1. **Implement Database Storage**: Replace TODO comments in `api/platform_oauth_routes.py` with actual database inserts
2. **Add Token Refresh Logic**: Implement automatic token refresh when access tokens expire
3. **Build User Management**: Create UI for users to see/manage connected accounts
4. **Add Disconnection Flow**: Allow users to revoke/disconnect platforms
5. **Production Deployment**: Update all redirect URIs to production URLs

---

## Security Best Practices

✅ **DO:**
- Store tokens encrypted in database
- Use HTTPS in production
- Validate state parameters
- Implement CSRF protection
- Rotate refresh tokens
- Set appropriate token expiration

❌ **DON'T:**
- Commit .env files to Git
- Share client secrets publicly
- Store tokens in localStorage (use session/database)
- Mix development and production credentials

---

## Support Links

- **Twitter**: [Developer Docs](https://developer.twitter.com/en/docs/authentication/oauth-2-0)
- **TikTok**: [Developer Docs](https://developers.tiktok.com/doc/login-kit-web/)
- **YouTube**: [OAuth Guide](https://developers.google.com/youtube/v3/guides/authentication)

---

**Ready to connect?** Once you've added all credentials to your `.env` file and restarted your server, visit `/connect/dashboard` to test!
