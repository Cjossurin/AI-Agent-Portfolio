# Unified Social Media App Review - Complete Setup Guide

## Overview
This document covers the complete setup and submission process for your unified Meta App Review covering all required advanced permissions for Facebook, Instagram, WhatsApp Business, and related platforms.

## Current Status

### ✅ Completed Integrations
- **Facebook Pages API**: Post management, comment handling, engagement tracking
- **Instagram Graph API**: Comment management, messaging, insights
- **OAuth 2.0 Flow**: User consent, token management, secure credential storage
- **Dashboard**: Unified social media management interface

### 🔄 Ready for Setup (On Backburner for Now)
- **WhatsApp Business API**: Messaging, templates, business profile
- **Threads API**: Via Late API integration

### 🆕 New Platform Integrations (Added)
- **Twitter/X API**: Native tweet posting, analytics, user timeline
- **TikTok API**: Video analytics, trending content, user profile
- **YouTube API**: Channel management, video analytics, search
- **Late API**: Multi-platform posting (TikTok, LinkedIn, Twitter, Threads, Reddit, Pinterest, Bluesky)

## Platform APIs and Credentials Required

### Facebook & Instagram (Meta)
**Status**: Already approved in your dashboard

Required Credentials:
```
META_APP_ID=your_app_id
META_APP_SECRET=your_app_secret
META_ACCESS_TOKEN=your_access_token
```

Already Approved Permissions:
- `instagram_business_basic`
- `instagram_business_manage_messages`
- `pages_show_list`
- `pages_manage_metadata`
- `instagram_manage_comments`
- `instagram_manage_insights`
- `instagram_content_publish`
- `instagram_manage_messages`
- `pages_read_engagement`
- `pages_read_user_content`
- `pages_manage_posts`
- `pages_manage_engagement`
- `business_management`
- `email` (for OAuth)
- `ads_management`

### Twitter/X API
**Status**: Requires API credentials

Setup Steps:
1. Go to https://developer.twitter.com/en/portal/dashboard
2. Create or select your project
3. Enable the Twitter API v2
4. Generate API credentials:
   - API Key (Bearer Token)
   - API Secret
   - Access Token
   - Access Token Secret
5. Add your User ID

Add to .env:
```
TWITTER_API_KEY=your_bearer_token
TWITTER_API_SECRET=your_api_secret
TWITTER_ACCESS_TOKEN=your_access_token
TWITTER_ACCESS_TOKEN_SECRET=your_access_token_secret
TWITTER_USER_ID=your_user_id
```

### TikTok API
**Status**: Requires OAuth setup

Setup Steps:
1. Go to https://developers.tiktok.com/
2. Create a developer account and app
3. Request access to TikTok API
4. Set up OAuth flow with redirect URL: `http://localhost:8000/auth/tiktok/callback`
5. Get OAuth credentials

Add to .env:
```
TIKTOK_CLIENT_ID=your_client_id
TIKTOK_CLIENT_SECRET=your_client_secret
TIKTOK_ACCESS_TOKEN=your_access_token
TIKTOK_USER_ID=your_user_id
```

### YouTube API
**Status**: Requires API key setup

Setup Steps:
1. Go to https://console.cloud.google.com/
2. Create a new project
3. Enable YouTube Data API v3
4. Create API credentials (API Key)
5. Optionally set up OAuth for user authentication

Add to .env:
```
YOUTUBE_API_KEY=your_api_key
YOUTUBE_CHANNEL_ID=your_channel_id
YOUTUBE_REFRESH_TOKEN=your_refresh_token (optional, for OAuth)
```

### Late API (Multi-platform)
**Status**: Already integrated, requires API key

Setup Steps:
1. Go to https://getlate.dev/
2. Sign up and create an account
3. Generate API key
4. Connect your TikTok, LinkedIn, Twitter, Threads accounts

Add to .env:
```
LATE_API_KEY=your_late_api_key
```

## Unified Dashboard

Access the unified social media dashboard at:
```
http://localhost:8000/social/dashboard
```

### Available Endpoints

#### Twitter/X
- `GET /social/twitter/post?text=hello` - Post a tweet
- `GET /social/twitter/analytics/{tweet_id}` - Get tweet analytics
- `GET /social/twitter/profile` - Get profile information

#### TikTok
- `GET /social/tiktok/profile` - Get profile information
- `GET /social/tiktok/videos?max_results=10` - Get user videos
- `GET /social/tiktok/analytics/{video_id}` - Get video analytics
- `GET /social/tiktok/trending/sounds?max_results=20` - Get trending sounds

#### YouTube
- `GET /social/youtube/channel` - Get channel information
- `GET /social/youtube/videos?max_results=10` - Get channel videos
- `GET /social/youtube/analytics/{video_id}` - Get video analytics
- `GET /social/youtube/trending?max_results=10` - Get trending videos

#### Late API
- `GET /social/late-api/status` - Check Late API configuration

## Demo Video Script (For Meta App Review)

### Part 1: Facebook & Instagram (10 minutes)
**Title**: Facebook & Instagram Advanced Permissions Demo

Content to demonstrate:
1. **Instagram Comment Management**
   - Show managing comments on a post
   - Demonstrate filtering and responding
   - Show insights data

2. **Instagram Direct Messages**
   - Send a test message
   - Show message history

3. **Facebook Page Management**
   - Create and publish a post
   - Manage comments
   - Show page insights

4. **End-to-End OAuth Flow**
   - Login with Meta credentials
   - Show permission request screen
   - Show token stored securely

### Part 2: Twitter/X Integration (5 minutes)
**Title**: Twitter/X API Integration Demo

Content to demonstrate:
1. **Tweet Posting**
   - Post a tweet from the dashboard
   - Show tweet appears on Twitter

2. **Analytics**
   - Show tweet impressions and engagement
   - Display user timeline

3. **User Profile**
   - Show profile information retrieval

### Part 3: TikTok Integration (5 minutes)
**Title**: TikTok Analytics and Profile Demo

Content to demonstrate:
1. **Profile Information**
   - Show user profile with follower count
   - Display bio and statistics

2. **Video Analytics**
   - Show video list
   - Display views, likes, comments for each video

3. **Trending Content**
   - Show trending sounds
   - Show hashtag suggestions

### Part 4: YouTube Integration (5 minutes)
**Title**: YouTube Channel Management Demo

Content to demonstrate:
1. **Channel Information**
   - Show channel name, subscribers, total views
   - Display verification status

2. **Video Management**
   - List channel videos
   - Show upload date and thumbnail

3. **Video Analytics**
   - Show views, likes, comments per video
   - Display comment list for a video

## .env Configuration Template

```bash
# Meta (Facebook & Instagram)
META_APP_ID=your_app_id
META_APP_SECRET=your_app_secret
META_ACCESS_TOKEN=your_access_token
META_REFRESH_TOKEN=your_refresh_token

# Twitter/X
TWITTER_API_KEY=your_bearer_token
TWITTER_API_SECRET=your_api_secret
TWITTER_ACCESS_TOKEN=your_access_token
TWITTER_ACCESS_TOKEN_SECRET=your_access_token_secret
TWITTER_USER_ID=your_user_id

# TikTok
TIKTOK_CLIENT_ID=your_client_id
TIKTOK_CLIENT_SECRET=your_client_secret
TIKTOK_ACCESS_TOKEN=your_access_token
TIKTOK_USER_ID=your_user_id

# YouTube
YOUTUBE_API_KEY=your_api_key
YOUTUBE_CHANNEL_ID=your_channel_id
YOUTUBE_REFRESH_TOKEN=your_refresh_token

# Late API (Multi-platform)
LATE_API_KEY=your_late_api_key

# WhatsApp (on backburner)
WHATSAPP_BUSINESS_ACCOUNT_ID=your_account_id
WHATSAPP_PHONE_NUMBER_ID=your_phone_number_id
WHATSAPP_ACCESS_TOKEN=your_access_token
```

## Testing Checklist

- [ ] Facebook Pages: Create post, manage comments, view insights
- [ ] Instagram: Reply to comments, send message, view profile insights
- [ ] OAuth flow: Login, permissions request, token storage
- [ ] Twitter: Post tweet, view profile, check analytics
- [ ] TikTok: View profile, fetch videos, display analytics
- [ ] YouTube: Display channel info, list videos, show analytics
- [ ] Late API: Verify configuration and supported platforms
- [ ] Dashboard: All social media cards display correctly
- [ ] Error handling: Graceful failures for missing credentials

## Running the Server

```bash
# Start the development server
python web_app.py

# Server will run on http://localhost:8000
# Dashboard: http://localhost:8000/social/dashboard
```

## Next Steps

1. **Configure API Credentials**
   - Add Twitter, TikTok, YouTube API keys to .env
   - Test each platform individually

2. **Record Demo Videos**
   - Follow the demo script above
   - Create separate videos for each platform
   - Ensure captions/audio clearly explain features

3. **Submit Meta App Review** (when ready)
   - Use the unified dashboard in your demo
   - Include videos for all required permissions
   - Reference this documentation in app description

4. **Monitor Approval Status**
   - Check Meta for Developers dashboard regularly
   - Respond to any clarification requests within 5 days
   - Expected approval time: 3-5 business days

## Support Resources

- **Twitter API Docs**: https://developer.twitter.com/en/docs/twitter-api
- **TikTok API Docs**: https://developers.tiktok.com/
- **YouTube API Docs**: https://developers.google.com/youtube/v3
- **Late API Docs**: https://docs.getlate.dev/
- **Meta for Developers**: https://developers.facebook.com/

## Important Notes

✅ **Ready for Meta App Review**: Facebook & Instagram integrations with all approved permissions  
⏳ **On Backburner**: WhatsApp Business, Threads (Late API)  
🆕 **New Additions**: Twitter, TikTok, YouTube for comprehensive platform coverage  
📊 **Multi-Platform Support**: Late API enables posting to 7+ platforms with single integration
