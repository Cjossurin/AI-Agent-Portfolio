# 💬 Alita Comment Management System

Professional Instagram comment dashboard with AI-powered auto-replies for Meta App Review.

## 🎯 Features

### ✅ Completed (Phase 2)
- **Professional Comment Dashboard** - Clean, dark-themed UI showing all posts and comments
- **Real Instagram Data** - Fetches actual posts, comments, and metrics via Meta Graph API
- **Manual Comment Replies** - Reply to comments directly from the dashboard
- **AI Auto-Reply** - Generate brand-voice replies using EngagementAgent
- **Sentiment Analysis** - Automatically detect positive/negative/neutral comments
- **Real-Time Monitoring** - Auto-refresh every 30 seconds to catch new comments
- **Multi-Account Support** - Manage comments across multiple Instagram Business accounts
- **Session Management** - Secure OAuth 2.0 authentication with encrypted tokens

## 🚀 Quick Start

### 1. Start the Web Server
```bash
python web_app.py
```

### 2. Connect Your Instagram Account
1. Visit `http://localhost:8000/comments/dashboard`
2. You'll be prompted to log in via OAuth
3. Click "Connect Instagram"
4. Grant permissions on Facebook
5. You'll be redirected back to the dashboard

### 3. Manage Comments
- Select an Instagram account from the grid
- View recent posts with comment counts
- Click "View comments" to expand threads
- Reply manually or use AI auto-reply
- Replies appear immediately on Instagram

## 📸 Dashboard Overview

```
┌─────────────────────────────────────────────┐
│  💬 Comment Management Dashboard            │
├─────────────────────────────────────────────┤
│                                              │
│  🔘 AI Auto-Reply [ON/OFF]                  │
│                                              │
│  📸 Your Instagram Accounts                 │
│  ┌─────────────┐  ┌─────────────┐          │
│  │ @account1   │  │ @account2   │          │
│  │ 12K followers│  │ 8K followers│          │
│  └─────────────┘  └─────────────┘          │
│                                              │
│  📝 Recent Posts                            │
│  ┌───────────────────────────────────────┐  │
│  │ [Image] Post caption...                │  │
│  │ ❤️ 245  💬 12  🕐 2h ago              │  │
│  │                                         │  │
│  │ View 12 comments →                      │  │
│  │                                         │  │
│  │ ┌─ @user1 😊 Positive                  │  │
│  │ │  "This is amazing!"                   │  │
│  │ │  [✍️ Reply] [🤖 AI Reply]           │  │
│  │ └─────────────────────────────────────  │  │
│  └───────────────────────────────────────┘  │
└─────────────────────────────────────────────┘
```

## 🔧 API Endpoints

### Comment Dashboard
- `GET /comments/dashboard` - Professional comment management UI
- `GET /comments/accounts` - List connected Instagram accounts
- `GET /comments/posts?account_id=X` - Get posts for an account
- `GET /comments/{post_id}` - Get comments for a post
- `POST /comments/{comment_id}/reply` - Send a reply
- `GET /comments/{comment_id}/ai-reply` - Generate AI reply
- `GET /comments/recent?account_id=X` - Real-time monitoring

### Authentication
All endpoints require OAuth 2.0 authentication via session cookie.

## 🤖 AI Auto-Reply

The AI auto-reply feature uses your EngagementAgent with:
- **Brand Voice** - Responses match your configured style
- **Context Awareness** - Pulls from your knowledge base
- **Sentiment Analysis** - Adapts tone based on comment sentiment
- **Character Limits** - Automatically truncates to Instagram's 200-char limit

### Example AI Replies

**Comment:** "This post is amazing! Love your content"
**AI Reply:** "Yo thank you so much! I really appreciate that 🙌 means a lot coming from you. What part resonated with you the most?"

**Comment:** "Where can I buy this?"
**AI Reply:** "Hey! You can check out our link in bio or DM me and I'll send you the details 👍"

## 📊 Sentiment Detection

Comments are automatically categorized:
- 😊 **Positive** - Contains: love, amazing, great, awesome, beautiful, ❤️, 😍, 🔥
- 😞 **Negative** - Contains: hate, terrible, awful, bad, worst, horrible
- 😐 **Neutral** - Everything else

## 🔐 Security

- **OAuth 2.0** - Industry-standard authentication
- **Encrypted Tokens** - Fernet encryption for tokens at rest
- **Session Management** - Secure httpOnly cookies
- **CSRF Protection** - State tokens for OAuth flow
- **Token Expiry** - Auto-refresh long-lived tokens (60-day validity)

## 🎨 UI Features

- **Dark Theme** - Professional Instagram-inspired design
- **Responsive Layout** - Works on desktop and mobile
- **Real-Time Updates** - Auto-refresh every 30 seconds
- **Badge System** - Visual indicators for comment status
- **Expandable Threads** - Click to view/hide comments
- **Inline Reply Forms** - Reply without leaving the dashboard

## 📹 Meta App Review Demo

To record your screencast for Meta App Review:

### Required Flow
1. **Start at login page** - Show the consent screen
2. **Grant permissions** - Demonstrate OAuth flow
3. **View dashboard** - Show connected accounts and posts
4. **View comments** - Expand a post's comment section
5. **Manual reply** - Type and send a manual reply
6. **AI reply** - Generate and send an AI-powered reply
7. **Verify on Instagram** - Open Instagram app and show the replies appeared

### Recording Tips
- Use English UI
- Add captions explaining each step
- Show voiceover explaining the flow
- Keep video under 5 minutes
- Use screen recording software (OBS, Loom, etc.)

## 🐛 Troubleshooting

### "Not Authenticated"
- Make sure you've completed the OAuth flow
- Check if your session cookie is valid
- Re-login at `/auth/login`

### "Token Expired"
- Click "Reconnect" in the dashboard
- Long-lived tokens last 60 days
- System auto-refreshes before expiry

### "Failed to load posts"
- Verify your Instagram account is a Business or Creator account
- Ensure it's linked to a Facebook Page
- Check App Roles in developers.facebook.com

### AI Reply Not Working
- EngagementAgent requires Claude API key
- Check `ANTHROPIC_API_KEY` in `.env`
- Falls back to default friendly replies if unavailable

## 📁 File Structure

```
api/
├── meta_oauth.py          # Meta Graph API client
├── token_manager.py       # Encrypted token storage
├── oauth_routes.py        # OAuth login/callback routes
└── comment_routes.py      # Comment dashboard routes

agents/
└── engagement_agent.py    # AI reply generation

database/
└── alita_oauth.db        # SQLite database (encrypted tokens)

web_app.py                # Main FastAPI application
test_comment_system.py    # System test suite
```

## 🚦 Testing

Run the test suite:
```bash
python test_comment_system.py
```

Expected output:
```
✅ OAuth 2.0 client configured
✅ Token manager operational
✅ Comment dashboard routes ready
✅ API methods available
✅ AI auto-reply engine ready
```

## 📈 Next Steps (Phase 3-4)

- [ ] Record Meta App Review screencast
- [ ] Submit for `instagram_manage_comments` approval
- [ ] Implement auto-moderation rules
- [ ] Add comment templates library
- [ ] Build analytics dashboard
- [ ] Create webhook-based live notifications

## 🔗 Related Documentation

- [OAuth Architecture](OAUTH_ARCHITECTURE_VALIDATION.md)
- [Meta App Review Plan](META_APP_REVIEW_PLAN.md)
- [Style Injection Guide](STYLE_INJECTION_GUIDE.md)

## 📞 Support

For issues or questions:
1. Check troubleshooting section above
2. Review Meta's [Instagram API docs](https://developers.facebook.com/docs/instagram-api)
3. Test with `python test_comment_system.py`

---

**Built with ❤️ for Meta App Review**
