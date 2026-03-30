# How to Connect a New Client's Accounts (Step-by-Step)

## Your Current Setup Works Perfectly!

You already have everything you need. Here's exactly how to connect a new client's Twitter, TikTok, and YouTube accounts.

---

## Step-by-Step: Adding a New Client

### Example: New client "Sarah Johnson"

**1. Choose a client_id:** `client_sarah`

**2. Connect Client's Accounts in Late API Dashboard:**

#### Twitter:
1. Go to https://app.getlate.dev
2. Click "Add Profile"
3. Select "Twitter/X"
4. **Important:** Have Sarah authorize with HER Twitter account
   - Option A: She logs in and authorizes
   - Option B: You log in with her credentials temporarily
5. Late API generates a profile_id (e.g., `697b123abc456def789`)
6. Copy this profile_id

#### TikTok:
1. Still in Late API dashboard, click "Add Profile" again
2. Select "TikTok"
3. Have Sarah authorize with HER TikTok account
4. Late API generates another profile_id (e.g., `697b456xyz789abc123`)
5. Copy this profile_id

#### LinkedIn (Optional):
1. Same process - "Add Profile" → "LinkedIn"
2. Get her LinkedIn profile_id

**3. Add Profile IDs to Your `.env` File:**

Open `C:\Users\Prince\Documents\Alita\.env` and add:

```env
# Client: Sarah Johnson (client_sarah)
LATE_PROFILE_TWITTER_client_sarah=697b123abc456def789
LATE_PROFILE_TIKTOK_client_sarah=697b456xyz789abc123
LATE_PROFILE_LINKEDIN_client_sarah=697b789def123abc456
```

**4. Connect YouTube (If Needed):**

YouTube is different - it's not via Late API. For read-only access (analytics), you just need the YouTube API key you already have.

For uploading videos on Sarah's behalf, you'd need to:
1. Have her authorize your app via OAuth
2. Store her refresh_token in .env or database

For now, if you just want to read YouTube data, you're all set with your existing `YOUTUBE_API_KEY`.

**5. Test the Connection:**

```python
# Test posting to Sarah's Twitter
from agents.posting_agent import PostingAgent, ContentPost

agent = PostingAgent(client_id="client_sarah")

result = await agent.post_content(ContentPost(
    content="Hello from Sarah's account! 🎉",
    platform="twitter",
    client_id="client_sarah"
))

print(f"Success: {result.success}")
print(f"Post ID: {result.post_id}")
```

**6. Verify It Worked:**

- Check Sarah's Twitter - the post should appear
- Check Late API dashboard - you'll see the post in activity

---

## Quick Reference: .env Pattern

```env
# Pattern: LATE_PROFILE_{PLATFORM}_{client_id}

# Client 1 (default_client) - ALREADY IN YOUR .env ✅
LATE_PROFILE_TIKTOK_default_client=697b090c77637c5c857cbbc8
LATE_PROFILE_LINKEDIN_default_client=697b0a7877637c5c857cbbd2
LATE_PROFILE_TWITTER_default_client=697b093a77637c5c857cbbc9

# Client 2 (client_sarah) - NEW CLIENT
LATE_PROFILE_TWITTER_client_sarah=697b123abc456def789
LATE_PROFILE_TIKTOK_client_sarah=697b456xyz789abc123
LATE_PROFILE_LINKEDIN_client_sarah=697b789def123abc456

# Client 3 (client_john) - ANOTHER NEW CLIENT
LATE_PROFILE_TWITTER_client_john=697bAAAbbbCCCddd111
LATE_PROFILE_TIKTOK_client_john=697bDDDeeeFFfggg222
```

---

## How Your Code Automatically Uses It

When you create a PostingAgent:

```python
agent = PostingAgent(client_id="client_sarah")
```

The agent **automatically**:
1. Reads `LATE_PROFILE_TWITTER_client_sarah` from .env
2. Reads `LATE_PROFILE_TIKTOK_client_sarah` from .env
3. Stores them in `self.platform_profiles`

When you post:

```python
await agent.post_content(ContentPost(
    content="My post",
    platform="twitter",
    client_id="client_sarah"
))
```

The agent **automatically**:
1. Looks up profile_id from `self.platform_profiles["twitter"]`
2. Calls Late API with Sarah's profile_id
3. Post appears on **Sarah's Twitter**, not yours!

---

## Example: Posting to Multiple Clients

```python
from agents.posting_agent import PostingAgent, ContentPost

# Post to default_client's Twitter
default_agent = PostingAgent(client_id="default_client")
await default_agent.post_content(ContentPost(
    content="Announcement from default client",
    platform="twitter",
    client_id="default_client"
))

# Post to Sarah's Twitter (different account!)
sarah_agent = PostingAgent(client_id="client_sarah")
await sarah_agent.post_content(ContentPost(
    content="Announcement from Sarah's account",
    platform="twitter",
    client_id="client_sarah"
))

# Post to John's TikTok
john_agent = PostingAgent(client_id="client_john")
await john_agent.post_content(ContentPost(
    content="TikTok video from John",
    platform="tiktok",
    client_id="client_john",
    media_urls=["https://example.com/video.mp4"]
))
```

---

## Troubleshooting

### "Profile ID not found"
**Problem:** Agent can't find profile_id in .env

**Solution:** Check .env file for typos:
```env
# ❌ Wrong - missing underscore
LATE_PROFILE_TWITTERclient_sarah=697b123...

# ✅ Correct
LATE_PROFILE_TWITTER_client_sarah=697b123...
```

### "Late API returns 401 Unauthorized"
**Problem:** Profile_id is wrong or expired

**Solution:**
1. Go to Late API dashboard
2. Check if profile is still connected
3. If disconnected, reconnect and get new profile_id
4. Update .env with new profile_id

### "Post appears on wrong account"
**Problem:** Using wrong client_id

**Solution:**
```python
# ❌ Wrong - using default_client but want Sarah's account
agent = PostingAgent(client_id="default_client")

# ✅ Correct
agent = PostingAgent(client_id="client_sarah")
```

---

## When to Upgrade to Database

**Keep using .env if:**
- You have < 10 clients
- You're comfortable manually editing .env
- Clients don't need self-service

**Upgrade to database when:**
- You have 10+ clients (env file gets messy)
- You want clients to connect their own accounts
- You need audit logs of connection changes
- You want to support connection expiration/renewal

---

## Summary

**To add a new client:**
1. Connect their accounts in Late API dashboard → Get profile_ids
2. Add to .env: `LATE_PROFILE_{PLATFORM}_{client_id}=profile_id`
3. Create agent: `PostingAgent(client_id="new_client_id")`
4. Post: `await agent.post_content(...)`

**That's it!** Your system already handles the rest automatically. 🎉

---

## Next Steps (Optional - When You're Ready)

1. **Build Client Dashboard** (web UI for clients to see their connected accounts)
2. **Add Database Storage** (migrate from .env to database table)
3. **Implement Self-Service OAuth** (let clients connect accounts themselves)
4. **Add YouTube OAuth** (for video uploads on behalf of clients)

But for now, **your current .env approach works perfectly!** ✅
