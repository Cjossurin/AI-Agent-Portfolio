# Client Connection System - Setup Instructions

## ✅ What Was Just Created

You now have a **self-service client connection system** that allows clients to connect their own social media accounts without you having to log into Late API for them!

---

## 📁 New Files Created

1. **`api/client_connections_routes.py`**
   - Client dashboard at `/connect/dashboard`
   - Shows connection status
   - Provides Late API connection link
   - Stores connections in `storage/client_connections.json`

2. **`api/late_webhooks.py`**
   - Receives webhooks from Late API when profiles are connected
   - Automatically saves profile_ids to storage
   - Generates .env format for easy copying

3. **Updated `web_app.py`**
   - Mounted connection routes
   - Mounted webhook routes
   - Added "Connect Accounts" link to navigation

---

## 🚀 How to Set It Up (15 Minutes)

### Step 1: Get Your Late API Workspace Invite URL

1. Go to https://app.getlate.dev
2. Click on your workspace settings
3. Look for "Team" or "Invite Members" section
4. Copy the workspace invite link (looks like `https://app.getlate.dev/invite/ws_abc123...`)

### Step 2: Add Invite URL to .env

Open your `.env` file and add:

```env
# Late API Workspace Invite (for client self-service connections)
LATE_WORKSPACE_INVITE_URL=https://app.getlate.dev/invite/YOUR_WORKSPACE_ID_HERE
```

### Step 3: Start Your Server

```bash
python -m uvicorn web_app:app --reload --host 0.0.0.0 --port 8000
```

You should see:
```
✅ Client connection routes mounted: /connect/dashboard
✅ Webhook routes mounted: /webhooks/late-api/*
```

### Step 4: Test the Dashboard

Visit: http://localhost:8000/connect/dashboard?client_id=demo_client

You should see:
- Connection status for Twitter, TikTok, LinkedIn, YouTube
- "Connect via Late API" button
- Instructions for connecting

### Step 5: Set Up Late API Webhooks (For Production)

**For Local Testing:**
1. Install ngrok: https://ngrok.com/download
2. Run: `ngrok http 8000`
3. Copy the HTTPS URL (e.g., `https://abc123.ngrok.io`)

**Configure Late API:**
1. Go to https://app.getlate.dev/settings/webhooks
2. Add webhook URL: `https://abc123.ngrok.io/webhooks/late-api/profile-connected`
3. Select events:
   - `profile.connected`
   - `profile.disconnected`
   - `post.published` (optional)
   - `post.failed` (optional)
4. Save

**Add webhook secret to .env:**
```env
# Late API Webhook Secret (for signature verification)
LATE_WEBHOOK_SECRET=your_webhook_secret_from_late_api
```

---

## 📋 How Clients Connect Their Accounts

### Client Flow:

1. **You send client a link:**
   ```
   http://localhost:8000/connect/dashboard?client_id=client_johndoe
   ```

2. **Client visits the page**
   - Sees their connection status
   - Clicks "Connect via Late API"

3. **Client is redirected to Late API**
   - Late API prompts them to select platforms (Twitter, TikTok, LinkedIn)
   - They log in with THEIR social media accounts
   - They authorize access

4. **Late API sends webhook to your server**
   - Webhook contains `profile_id`, `platform`, `username`
   - Your webhook handler automatically saves it

5. **Connection is saved automatically!**
   - Saved to `storage/client_connections.json`
   - Also saved to `storage/new_connections_env.txt` in .env format

6. **Copy to .env (for now)**
   - Check `storage/new_connections_env.txt`
   - Copy new lines to your `.env` file
   - Restart server (or in production, read from database)

---

## 📂 Where Connections Are Stored

### Temporary Storage (Current):

**`storage/client_connections.json`:**
```json
{
  "client_johndoe": {
    "twitter": {
      "profile_id": "697b123abc...",
      "username": "johndoe",
      "connected_at": "2026-02-07T12:30:00",
      "status": "active"
    },
    "tiktok": {
      "profile_id": "697b456def...",
      "username": "johndoe_tiktok",
      "connected_at": "2026-02-07T12:31:00",
      "status": "active"
    }
  }
}
```

**`storage/new_connections_env.txt`:**
```env
LATE_PROFILE_TWITTER_client_johndoe=697b123abc...  # @johndoe - 2026-02-07
LATE_PROFILE_TIKTOK_client_johndoe=697b456def...  # @johndoe_tiktok - 2026-02-07
```

---

## 🧪 Testing It Manually

### Test the Dashboard:
```bash
# Visit in browser
http://localhost:8000/connect/dashboard?client_id=test_client
```

### Test Webhook Manually:
```bash
# Simulate a webhook from Late API
curl -X POST http://localhost:8000/webhooks/late-api/profile-connected \
  -H "Content-Type: application/json" \
  -d '{
    "event": "profile.connected",
    "profile_id": "697bTEST123",
    "platform": "twitter",
    "username": "testuser",
    "workspace_id": "ws_test"
  }'
```

Check console - you should see:
```
📨 WEBHOOK RECEIVED: profile.connected
Platform: twitter
Username: @testuser
Profile ID: 697bTEST123
✅ Connection saved!
```

Check `storage/new_connections_env.txt` - you should see new line added.

### Test Connection Status API:
```bash
curl http://localhost:8000/connect/status?client_id=test_client
```

Should return:
```json
{
  "client_id": "test_client",
  "connections": [...],
  "total_connected": 1
}
```

---

## 🔄 Workflow Example

**Scenario:** New client "Sarah" wants to connect her Twitter and TikTok

1. **You:**
   - Send Sarah: `http://localhost:8000/connect/dashboard?client_id=client_sarah`

2. **Sarah:**
   - Opens link in browser
   - Sees clean dashboard with instructions
   - Clicks "Connect via Late API"
   - Redirected to Late API
   - Logs in with her Twitter → Authorizes
   - Logs in with her TikTok → Authorizes

3. **Late API:**
   - Sends webhook #1: Twitter connection
   - Sends webhook #2: TikTok connection

4. **Your Server:**
   - Receives webhook #1, saves Twitter profile_id
   - Receives webhook #2, saves TikTok profile_id
   - Both saved to `storage/client_connections.json`
   - Both appended to `storage/new_connections_env.txt`

5. **You:**
   - Open `storage/new_connections_env.txt`
   - Copy new lines:
     ```env
     LATE_PROFILE_TWITTER_client_sarah=697bSARAH_TWITTER
     LATE_PROFILE_TIKTOK_client_sarah=697bSARAH_TIKTOK
     ```
   - Paste into `.env` file
   - (Optional) Restart server or use hot-reload

6. **Done!**
   - Sarah's accounts are connected
   - You can now post to HER Twitter/TikTok using PostingAgent:
     ```python
     agent = PostingAgent(client_id="client_sarah")
     await agent.post_content(ContentPost(
         content="Hello from Sarah's account!",
         platform="twitter"
     ))
     ```

---

## 🎯 Next Steps

### Immediate (Works Right Now):
1. ✅ Add `LATE_WORKSPACE_INVITE_URL` to .env
2. ✅ Restart server
3. ✅ Test dashboard at `/connect/dashboard?client_id=demo_client`
4. ✅ Click "Connect via Late API" to test flow

### For Production (When You Deploy):
1. Set up ngrok or deploy to Railway/Heroku
2. Configure Late API webhooks with your public URL
3. Add `LATE_WEBHOOK_SECRET` to .env
4. Webhook will automatically capture profile_ids

### Future Enhancement (Optional):
1. **Auto-sync to .env:** Script to automatically update .env from JSON
2. **Database migration:** Move from JSON file to PostgreSQL/SQLite
3. **Real-time updates:** WebSocket to refresh dashboard automatically
4. **Connection management:** Allow clients to disconnect accounts
5. **YouTube OAuth:** Add Google OAuth for YouTube uploads

---

## 📚 API Endpoints Available Now

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/connect/dashboard` | GET | Client connection dashboard (with ?client_id=) |
| `/connect/status` | GET | Get connection status for client |
| `/connect/manual-add` | POST | Manually add a connection (admin) |
| `/webhooks/late-api/profile-connected` | POST | Late API webhook for new connections |
| `/webhooks/late-api/post-published` | POST | Late API webhook for published posts |
| `/webhooks/test` | GET | Test webhook endpoint |

---

## 🎉 You're Done!

Your clients can now connect their own social media accounts without you having to manually log into Late API for them!

**To onboard a new client:**
1. Send them: `/connect/dashboard?client_id=client_name`
2. They click "Connect via Late API"
3. They authorize their accounts
4. Webhook automatically captures profile_ids
5. You copy from `storage/new_connections_env.txt` to `.env`
6. Start posting to their accounts!

---

**Need help?** Check the webhook logs in your server console or look at `storage/client_connections.json` to see all connections.
