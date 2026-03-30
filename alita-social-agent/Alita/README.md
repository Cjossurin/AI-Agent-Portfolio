# Alita AI

**AI-Powered Multi-Client Social Media & Marketing Automation Platform**

Alita is a production-ready SaaS platform that manages complete marketing operations for multiple clients simultaneously across 8+ social media platforms. Built with FastAPI and powered by Anthropic Claude, it handles content creation, scheduling, posting, engagement, lead conversion, analytics, and billing — all with intelligent AI-driven strategy, voice matching, and expandable knowledge bases.

---

## Table of Contents

- [Features](#features)
- [Architecture Overview](#architecture-overview)
- [Tech Stack](#tech-stack)
- [Project Structure](#project-structure)
- [AI Agents](#ai-agents)
- [API Routes](#api-routes)
- [Platform Integrations](#platform-integrations)
- [Billing & Pricing](#billing--pricing)
- [Security](#security)
- [Getting Started](#getting-started)
- [Environment Variables](#environment-variables)
- [Deployment](#deployment)
- [CI/CD Pipeline](#cicd-pipeline)
- [Scripts & Utilities](#scripts--utilities)
- [Documentation](#documentation)
- [License](#license)

---

## Features

### Prompt Security
- Production-grade prompt bodies are not committed to source.
- Repository prompt files contain abstract templates only.
- Full prompts are loaded from private environment variables and/or secured datastore configuration at runtime.

### Multi-Client SaaS Architecture
- **10–50+ simultaneous clients** across completely different industries (travel, coaching, fitness, consulting, etc.)
- Isolated client profiles with niche-specific knowledge bases
- Per-client voice matching — AI writes in each client's unique style
- Guided onboarding flow: website scrape, manual input, or file upload
- Role-based access: Admin dashboard + client self-service portal

### AI Content Engine
- **86 prompt templates** across 8 platforms × 3 goal types (conversions, growth, engagement)
- Multi-model AI: Claude Haiku (fast/cheap) and Claude Sonnet (high-quality reasoning)
- Platform-optimized content (character limits, hashtags, hooks, CTAs)
- Content calendar with intelligent scheduling and platform-specific timing
- Deep research integration for data-backed content

### Faceless Video Generation
- **15 content categories** (motivational, educational, horror, Reddit storytelling, etc.)
- Multi-tier quality system (Basic → Standard → Premium → Ultra)
- AI voiceover via ElevenLabs, stock footage from Pexels/Pixabay
- AI animation via fal.ai (Kling/Wan models)
- Subtitle generation and background music support

### AI Image Generation
- Multi-model support: Flux, Midjourney (via GoAPI), DALL-E, GPT Image, Ideogram
- Platform-specific prompt optimization
- Semantic keyword research for prompt engineering
- Image hosting via ImgBB

### Marketing Intelligence
- Competitive research via Tavily API
- News/trend intelligence via NewsAPI
- YouTube trending analysis
- Weekly/monthly strategy generation
- Campaign planning with multi-day strategies

### Engagement & Growth
- Automated DM responses with human-like latency (30–90s delay)
- Comment management across platforms
- Follower discovery and smart engagement
- Rate-limited safety controls to prevent bot detection
- Human escalation system — users say "human"/"agent" to reach a real person

### RAG Knowledge System
- Qdrant vector database for semantic search
- Per-client document ingestion (PDF, DOCX, TXT)
- 15 agent-specific RAG knowledge bases
- Batch processing with category-aware retrieval

### Email & Notifications
- **Outbound**: Resend API for marketing campaigns
- **Inbound**: Gmail API for reading/sending from client inboxes
- **SMS**: Twilio for OTP and alerts
- Conversation categorization (Sale, Complaint, Question, etc.)

### Client Portal
- Signup with email/password or social login (Google, Facebook)
- Two-factor authentication: TOTP (Google Authenticator) + WebAuthn passkeys
- Dashboard with analytics, content calendar, media library
- Settings: connected platforms, billing, profile management

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────┐
│                    Client Portal (Web UI)                │
│              FastAPI HTML responses + JS                 │
└──────────────────────┬──────────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────────┐
│                   FastAPI Application                    │
│                     (web_app.py)                         │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌───────────┐  │
│  │Auth Routes│ │API Routes│ │OAuth     │ │Webhook    │  │
│  │(JWT+2FA) │ │(33 files)│ │Flows     │ │Receiver   │  │
│  └──────────┘ └──────────┘ └──────────┘ └───────────┘  │
└──────────────────────┬──────────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────────┐
│                    AI Agent Layer                        │
│  ┌─────────────┐ ┌────────────┐ ┌───────────────────┐   │
│  │Content Agent │ │Growth Agent│ │Marketing Intel    │   │
│  │(86 templates)│ │(targeting) │ │(strategy/trends)  │   │
│  └─────────────┘ └────────────┘ └───────────────────┘   │
│  ┌─────────────┐ ┌────────────┐ ┌───────────────────┐   │
│  │Posting Agent│ │Calendar    │ │Analytics Agent    │   │
│  │(3-tier)     │ │Agent       │ │(reporting)        │   │
│  └─────────────┘ └────────────┘ └───────────────────┘   │
│  ┌─────────────┐ ┌────────────┐ ┌───────────────────┐   │
│  │Engagement   │ │Email Agent │ │Faceless Video     │   │
│  │Agent        │ │(marketing) │ │Generator          │   │
│  └─────────────┘ └────────────┘ └───────────────────┘   │
│  ┌─────────────┐ ┌────────────┐ ┌───────────────────┐   │
│  │RAG System   │ │Image Gen   │ │Voice Matching     │   │
│  │(Qdrant)     │ │(multi-model│ │(Style DNA)        │   │
│  └─────────────┘ └────────────┘ └───────────────────┘   │
└──────────────────────┬──────────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────────┐
│                  Platform Routing                        │
│  ┌────────────────┐ ┌──────────────┐ ┌───────────────┐  │
│  │Tier 1: Direct  │ │Tier 2: Late  │ │Tier 3: Manual │  │
│  │Meta, YouTube,  │ │TikTok, X,    │ │Queue fallback │  │
│  │WordPress       │ │LinkedIn,     │ │for outages    │  │
│  │(Free)          │ │Threads, etc. │ │               │  │
│  └────────────────┘ └──────────────┘ └───────────────┘  │
└──────────────────────┬──────────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────────┐
│                   Data Layer                             │
│  ┌──────────┐ ┌────────────┐ ┌────────────────────────┐ │
│  │SQLAlchemy│ │Qdrant      │ │File Storage            │ │
│  │(SQLite / │ │(Vector DB  │ │(voice profiles, media, │ │
│  │PostgreSQL)│ │for RAG)   │ │ knowledge docs)        │ │
│  └──────────┘ └────────────┘ └────────────────────────┘ │
└─────────────────────────────────────────────────────────┘
```

---

## Tech Stack

| Layer | Technology | Purpose |
|-------|-----------|---------|
| **Web Framework** | FastAPI + Uvicorn | Async Python web server |
| **Language** | Python 3.11+ | Core application language |
| **Database** | SQLite (dev) / PostgreSQL (prod) | Relational data storage |
| **ORM** | SQLAlchemy 2.0 | Database models & migrations |
| **Vector DB** | Qdrant | RAG semantic search |
| **AI — Primary** | Anthropic Claude API | Content generation, voice matching, analytics |
| **AI — Secondary** | OpenAI GPT | Image generation, fallback |
| **AI — Research** | Google Gemini | Deep research capabilities |
| **Auth** | python-jose (JWT) + bcrypt | Session management & password hashing |
| **2FA** | pyotp + webauthn | TOTP codes & passkey authentication |
| **Payments** | Stripe | Subscriptions, add-ons, webhooks |
| **Email — Outbound** | Resend | Marketing campaigns & transactional email |
| **Email — Inbound** | Gmail API (OAuth) | Read/send from client inboxes |
| **SMS** | Twilio | OTP verification & alerts |
| **Social — Direct** | Meta Graph API, YouTube Data API | Facebook, Instagram, YouTube posting |
| **Social — Proxy** | Late API | TikTok, LinkedIn, X/Twitter, Threads, Pinterest, Reddit, Bluesky |
| **Voiceover** | ElevenLabs | AI narration for faceless videos |
| **Stock Media** | Pexels, Pixabay | Free stock video clips & images |
| **AI Animation** | fal.ai (Kling/Wan) | Video animation from static images |
| **Image Gen** | Ideogram, GoAPI (Midjourney), DALL-E, Flux | Multi-model image creation |
| **Image Hosting** | ImgBB | Public URL hosting for generated images |
| **Deployment** | Railway | PaaS with Procfile-based deploys |
| **CI/CD** | GitHub Actions | Linting, deployment, health checks |
| **Scraping** | BeautifulSoup4 + lxml | Website scraping for client onboarding |

---

## Project Structure

```
alita/
├── web_app.py                  # Main FastAPI application entry point (mounts all routers)
├── webhook_receiver.py         # Meta webhook handler (DMs, comments, human escalation)
├── content_orchestrator.py     # Content generation → posting workflow coordinator
├── cli_interface.py            # Interactive CLI management dashboard
├── conversation_memory.py      # Platform-compliant DM conversation context
├── prompt_templates.py         # Master prompt template system (86 templates)
├── init_db.py                  # Database initialization (called by Procfile on deploy)
├── guardrails_config.json      # Abuse protection configuration
├── Procfile                    # Railway deployment command
├── requirements.txt            # Python dependencies
├── .env.example                # Environment variable template
│
├── agents/                     # AI Agent modules (25 files)
│   ├── content_agent.py        #   Content creation with 86 templates
│   ├── posting_agent.py        #   Three-tier platform posting
│   ├── engagement_agent.py     #   DM/comment response automation
│   ├── growth_agent.py         #   Audience targeting & follower discovery
│   ├── analytics_agent.py      #   Performance tracking & reporting
│   ├── calendar_agent.py       #   RAG-powered content scheduling
│   ├── marketing_intelligence_agent.py  # Strategy & trend analysis
│   ├── email_marketing_agent.py #  Email campaign automation
│   ├── email_support_agent.py  #   Gmail inbox management
│   ├── faceless_generator.py   #   AI video generation pipeline
│   ├── image_generator.py      #   Multi-model image creation
│   ├── rag_system.py           #   Qdrant vector DB / document retrieval
│   ├── voice_matching_system.py #  Client voice/style matching
│   ├── alita_assistant.py      #   Conversational AI assistant
│   ├── agent_scheduler.py      #   Task scheduling & automation
│   ├── client_profile_manager.py # Client profile management
│   ├── content_calendar_orchestrator.py # Calendar coordination
│   ├── conversation_categorizer.py # DM/comment categorization
│   ├── faceless_rag.py         #   Video-specific RAG knowledge
│   ├── faceless_style_loader.py #  Video style configuration
│   ├── knowledge_base.py       #   Knowledge base management
│   ├── strategy_templates.py   #   Marketing strategy templates
│   └── growth_hacking_agent.py #   Advanced growth tactics
│
├── api/                        # FastAPI route modules (33 files)
│   ├── auth_routes.py          #   Login, signup, JWT, 2FA, passkeys
│   ├── admin_routes.py         #   Admin dashboard & management
│   ├── billing_routes.py       #   Stripe subscriptions & add-ons
│   ├── oauth_routes.py         #   Social login (Google, Facebook)
│   ├── platform_oauth_routes.py #  Platform connection OAuth flows
│   ├── meta_oauth.py           #   Meta/Facebook OAuth handler
│   ├── onboarding_routes.py    #   Client onboarding wizard
│   ├── settings_routes.py      #   User settings & preferences
│   ├── social_media_routes.py  #   Social media management
│   ├── post_creation_routes.py #   Content creation UI routes
│   ├── comment_routes.py       #   Comment management
│   ├── inbox_routes.py         #   Unified inbox
│   ├── messaging_routes.py     #   Direct messaging
│   ├── calendar_routes.py      #   Content calendar
│   ├── analytics_routes.py     #   Analytics dashboard
│   ├── growth_routes.py        #   Growth tools UI
│   ├── intelligence_routes.py  #   Marketing intelligence UI
│   ├── email_routes.py         #   Email marketing UI
│   ├── notification_routes.py  #   Notification management
│   ├── alita_assistant_routes.py # AI assistant chat
│   ├── client_connections_routes.py # Platform connections
│   ├── late_client.py          #   Late API client (7+ platforms)
│   ├── late_webhooks.py        #   Late API webhook handling
│   ├── threads_client.py       #   Threads API client
│   ├── threads_meta_client.py  #   Threads via Meta API
│   ├── threads_routes.py       #   Threads management
│   ├── twitter_client.py       #   Twitter/X API client
│   ├── tiktok_client.py        #   TikTok API client
│   ├── youtube_client.py       #   YouTube API client
│   ├── linkedin_client.py      #   LinkedIn API client
│   ├── whatsapp_client.py      #   WhatsApp Business API client
│   └── token_manager.py        #   OAuth token lifecycle management
│
├── database/                   # Database layer
│   ├── db.py                   #   SQLAlchemy engine & session factory
│   └── models.py               #   ORM models (User, ClientProfile, etc.)
│
├── utils/                      # Shared utilities (16 files)
│   ├── guardrails.py           #   Abuse protection & request filtering
│   ├── notification_manager.py #   Multi-channel notifications
│   ├── meta_graph.py           #   Meta Graph API helper
│   ├── meta_inbox_store.py     #   Inbox data caching
│   ├── connected_platforms.py  #   Platform connection state
│   ├── plan_limits.py          #   Subscription plan enforcement
│   ├── shared_layout.py        #   HTML layout components
│   ├── image_generator.py      #   Image generation utilities
│   ├── style_learner.py        #   Voice/style learning
│   ├── website_scraper.py      #   Onboarding website scraper
│   ├── file_reader.py          #   Document parsing (PDF/DOCX/TXT)
│   ├── auto_reply_settings.py  #   Auto-reply configuration
│   ├── cross_channel_memory.py #   Cross-platform memory
│   ├── follow_tracker.py       #   Growth follow tracking
│   └── platform_events.py      #   Platform event handling
│
├── prompts/                    # Generated prompt templates (85 .txt files)
├── Agent RAGs/                 # RAG knowledge bases (15 agent-specific directories)
├── knowledge_docs/             # Client business documents (PDF/DOCX)
├── faceless_video_prompts/     # Video prompt templates (15 categories)
├── image_generation_prompts/   # Image prompt engineering templates
├── storage/                    # Runtime data (calendars, connections, media)
├── scripts/                    # Admin & setup utilities
│   ├── create_admin.py         #   Create admin user account
│   ├── seed_railway_meta.py    #   Seed production database
│   ├── migrate_meta_columns.py #   Database column migrations
│   ├── add_tester.py           #   Add test users
│   ├── upgrade_admin_pro.py    #   Upgrade user to Pro plan
│   ├── get_facebook_pages.py   #   Fetch Facebook page IDs
│   ├── get_page_id.py          #   Get Instagram page ID
│   ├── update_templates.py     #   Update prompt templates
│   └── generate_content.py     #   Generate sample content
│
├── docs/                       # Documentation
│   ├── setup/                  #   Setup & installation guides
│   ├── architecture/           #   System architecture docs
│   ├── features/               #   Feature documentation
│   └── deployment/             #   Deployment guides
│
└── .github/
    └── workflows/
        ├── ci.yml              #   Continuous integration (lint)
        ├── deploy.yml          #   Production deployment
        └── health-check.yml    #   Uptime monitoring (every 15 min)
```

---

## AI Agents

The system uses **15 specialized AI agents**, each with its own RAG knowledge base:

| Agent | Module | Description |
|-------|--------|-------------|
| **Content Creation** | `agents/content_agent.py` | Generates platform-optimized content using 86 templates across 8 platforms × 3 goals |
| **Posting** | `agents/posting_agent.py` | Routes content through three-tier platform system (Direct → Late API → Manual Queue) |
| **Engagement** | `agents/engagement_agent.py` | Handles DM responses and comment replies with human-like timing |
| **Growth** | `agents/growth_agent.py` | Audience targeting, follower discovery, smart engagement with rate limiting |
| **Analytics** | `agents/analytics_agent.py` | Performance tracking, insights generation, ROI reporting |
| **Calendar** | `agents/calendar_agent.py` | RAG-powered content scheduling with platform-specific optimal timing |
| **Marketing Intelligence** | `agents/marketing_intelligence_agent.py` | Strategy generation, trend analysis, competitive research, campaign planning |
| **Email Marketing** | `agents/email_marketing_agent.py` | Automated email campaigns via Resend |
| **Email Support** | `agents/email_support_agent.py` | Gmail inbox management — reads and responds from client email |
| **Faceless Video** | `agents/faceless_generator.py` | AI video generation pipeline: script → voiceover → footage → assembly |
| **Image Generation** | `agents/image_generator.py` | Multi-model image creation (Flux, Midjourney, DALL-E, Ideogram) |
| **RAG System** | `agents/rag_system.py` | Qdrant vector database for semantic document retrieval |
| **Voice Matching** | `agents/voice_matching_system.py` | Client voice/style learning and matching |
| **Alita Assistant** | `agents/alita_assistant.py` | Conversational AI assistant for the dashboard |
| **Conversation Categorizer** | `agents/conversation_categorizer.py` | Auto-categorizes DMs/comments (Sale, Complaint, Question, etc.) |

---

## API Routes

The FastAPI application mounts **33 route modules** under the main app:

| Module | Prefix | Description |
|--------|--------|-------------|
| `auth_routes` | `/auth`, `/account` | Login, signup, JWT tokens, 2FA setup, passkeys, social login |
| `admin_routes` | `/admin` | Admin dashboard, client management, system monitoring |
| `billing_routes` | `/billing` | Stripe checkout, subscription management, add-on purchases |
| `onboarding_routes` | `/onboarding` | Client onboarding wizard (website scrape / manual / file upload) |
| `settings_routes` | `/settings` | User preferences, profile, connected accounts |
| `social_media_routes` | `/social` | Social media account management |
| `post_creation_routes` | `/posts` | Content creation, editing, scheduling |
| `comment_routes` | `/comments` | Comment management across platforms |
| `inbox_routes` | `/inbox` | Unified inbox for all platform messages |
| `calendar_routes` | `/calendar` | Content calendar visualization and management |
| `analytics_routes` | `/analytics` | Performance dashboards and reports |
| `growth_routes` | `/growth` | Growth tools, audience targeting |
| `intelligence_routes` | `/intelligence` | Marketing strategy and trend data |
| `email_routes` | `/email` | Email marketing campaigns |
| `notification_routes` | `/notifications` | In-app and push notifications |
| `platform_oauth_routes` | `/connect` | OAuth flows for connecting social platforms |
| `meta_oauth` | `/auth` | Meta/Facebook specific OAuth |
| `late_webhooks` | `/webhooks/late` | Late API webhook handling |
| `webhook_receiver` | `/webhook` | Meta webhook receiver (DMs, comments) |

---

## Platform Integrations

### Three-Tier Routing System

| Tier | Platforms | Method | Cost |
|------|-----------|--------|------|
| **Tier 1 — Direct API** | Facebook, Instagram, YouTube, WordPress | Native platform APIs | Free |
| **Tier 2 — Late API** | TikTok, LinkedIn, Twitter/X, Threads, Reddit, Pinterest, Bluesky | Late API proxy | ~$33/mo |
| **Tier 3 — Manual Queue** | Any platform during outages | Human-assisted posting | Free |

### Supported Actions per Platform

| Platform | Post | Stories | Reels/Video | Comments | DMs | Analytics |
|----------|------|---------|-------------|----------|-----|-----------|
| Facebook | ✅ | — | ✅ | ✅ | ✅ | ✅ |
| Instagram | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| TikTok | ✅ | — | ✅ | — | — | — |
| YouTube | ✅ | ✅ | ✅ | — | — | — |
| Twitter/X | ✅ | — | — | — | — | — |
| LinkedIn | ✅ | — | ✅ | — | — | — |
| Threads | ✅ | — | — | — | — | — |
| Email | ✅ | — | — | — | ✅ | ✅ |

---

## Billing & Pricing

### Subscription Tiers

| Feature | Free | Starter ($29/mo) | Growth ($79/mo) | Pro ($197/mo) |
|---------|------|-------------------|-----------------|---------------|
| Social Platforms | 2 | 4 | 6 | Unlimited |
| Posts/Month | 10 | 50 | 150 | Unlimited |
| AI Content Generation | Basic | Standard | Advanced | Premium |
| Analytics | Basic | Standard | Advanced | Full Suite |
| Faceless Video | — | 5/mo | 20/mo | Unlimited |
| RAG Knowledge Base | — | 10 docs | 50 docs | Unlimited |
| Email Marketing | — | — | ✅ | ✅ |
| Priority Support | — | — | — | ✅ |

### Add-On Products

| Add-On | Description |
|--------|-------------|
| Post Boost | Additional post credits |
| Engagement Boost | Enhanced engagement automation |
| Video Boost | Extra faceless video generation |
| AI Animation | Premium AI video animation |
| Premium Images | High-quality multi-model image generation |
| Email Campaign | Email marketing capabilities |
| Growth Strategy | Advanced growth automation |
| Research Boost | Deep research credits |
| YouTube Add-on | YouTube-specific features |
| Account Expansion | Additional social accounts |

---

## Security

- **Authentication**: JWT tokens with configurable expiry via `python-jose`
- **Password Hashing**: bcrypt with salt rounds via `passlib`
- **Two-Factor Auth**: TOTP (Google Authenticator compatible) via `pyotp` + WebAuthn passkeys via `webauthn`
- **OAuth 2.0**: Token encryption at rest via `cryptography` (Fernet)
- **Guardrails System**: Global abuse protection filtering all AI agent inputs
  - Blocks excessive length (>2,000 chars), repetition, profanity, banned patterns, spam
  - Configurable via `guardrails_config.json` with auto-reload every 60 seconds
  - All blocked requests logged for review
- **Human Escalation**: Keyword-triggered handoff ("human", "agent", "real person") pauses automation
- **Rate Limiting**: Per-platform rate controls on growth/engagement actions
- **Secrets Management**: All API keys stored in `.env` (excluded from git via `.gitignore`)

---

## Getting Started

### Prerequisites

- **Python 3.11+**
- **pip** (Python package manager)
- API keys for required services (see [Environment Variables](#environment-variables))

### Local Development Setup

```bash
# 1. Clone the repository
git clone https://github.com/your-org/alita.git
cd alita

# 2. Create and activate virtual environment
python -m venv .venv

# Windows
.venv\Scripts\activate

# macOS/Linux
source .venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure environment
cp .env.example .env
# Edit .env with your API keys (see Environment Variables section)

# 5. Initialize database and create admin user
python init_db.py

# 6. Run the application
uvicorn web_app:app --host 0.0.0.0 --port 8080 --reload

# App is now running at http://localhost:8080
```

### First-Time Admin Setup

After starting the app:

1. Navigate to `http://localhost:8080/login`
2. Log in with the admin credentials from your `.env` file (`ADMIN_EMAIL` / `ADMIN_PASSWORD`)
3. Go to Admin Dashboard → Add your first client
4. Connect social media platforms via OAuth flows in Settings → Connected Accounts

### CLI Dashboard

For command-line management:

```bash
python cli_interface.py
```

The CLI provides an interactive dashboard for managing workflows, viewing analytics, and controlling agents.

---

## Environment Variables

Copy `.env.example` to `.env` and configure the following. Variables are organized by priority tier:

### Tier 1 — Required (Core AI)

| Variable | Service | Description |
|----------|---------|-------------|
| `ANTHROPIC_API_KEY` | Anthropic | Claude API key for all AI operations |
| `CLAUDE_HAIKU_MODEL` | Anthropic | Fast model ID (e.g., `claude-haiku-4-5-20251001`) |
| `CLAUDE_SONNET_MODEL` | Anthropic | Quality model ID (e.g., `claude-sonnet-4-5-20250929`) |
| `CLAUDE_DEFAULT_MODEL` | Anthropic | Default model selection (`haiku` or `sonnet`) |
| `OPENAI_API_KEY` | OpenAI | For image generation and fallback |
| `DATABASE_URL` | — | Database connection string |
| `ADMIN_EMAIL` | — | Admin account email |
| `ADMIN_PASSWORD` | — | Admin account password |

### Tier 2 — Social Media Posting

| Variable | Service | Description |
|----------|---------|-------------|
| `META_APP_ID` | Meta | Facebook/Instagram app ID |
| `META_APP_SECRET` | Meta | App secret for OAuth |
| `FACEBOOK_PAGE_ID` | Meta | Page ID for posting |
| `FACEBOOK_PAGE_ACCESS_TOKEN` | Meta | Page access token |
| `INSTAGRAM_BUSINESS_ACCOUNT_ID` | Meta | IG business account ID |
| `INSTAGRAM_ACCESS_TOKEN` | Meta | IG access token |
| `LATE_API_KEY` | Late | API key for TikTok, LinkedIn, X, etc. |
| `LATE_PROFILE_*` | Late | Per-client profile IDs for each platform |
| `VERIFY_TOKEN` | Meta | Webhook verification token |

### Tier 3 — Content Intelligence & Media

| Variable | Service | Description |
|----------|---------|-------------|
| `TAVILY_API_KEY` | Tavily | Competitive research |
| `NEWSAPI_KEY` | NewsAPI | News/trend intelligence |
| `YOUTUBE_API_KEY` | Google | YouTube data & trending videos |
| `ELEVENLABS_API_KEY` | ElevenLabs | AI voiceover ($5/mo) |
| `PEXELS_API_KEY` | Pexels | Free stock video |
| `PIXABAY_API_KEY` | Pixabay | Backup stock video |
| `FAL_API_KEY` | fal.ai | AI animation (Kling/Wan) |
| `IDEOGRAM_API_KEY` | Ideogram | Text-accurate image generation |
| `GOAPI_API_KEY` | GoAPI | Midjourney image generation |
| `IMGBB_API_KEY` | ImgBB | Image hosting |
| `GEMINI_API_KEY` | Google | Deep research |

### Tier 4 — Email, SMS & Payments

| Variable | Service | Description |
|----------|---------|-------------|
| `RESEND_API_KEY` | Resend | Outbound email |
| `GMAIL_CLIENT_ID` | Google | Gmail OAuth client |
| `GMAIL_CLIENT_SECRET` | Google | Gmail OAuth secret |
| `TWILIO_ACCOUNT_SID` | Twilio | SMS account SID |
| `TWILIO_AUTH_TOKEN` | Twilio | SMS auth token |
| `TWILIO_PHONE_NUMBER` | Twilio | SMS sender number |
| `STRIPE_SECRET_KEY` | Stripe | Payment processing |
| `STRIPE_PUBLISHABLE_KEY` | Stripe | Client-side Stripe |
| `STRIPE_WEBHOOK_SECRET` | Stripe | Webhook verification |
| `STRIPE_PRICE_*` | Stripe | Subscription price IDs |
| `TOKEN_ENCRYPTION_KEY` | — | OAuth token encryption key |

### OAuth Redirect URIs

| Variable | Description |
|----------|-------------|
| `META_REDIRECT_URI` | Meta OAuth callback |
| `TWITTER_REDIRECT_URI` | Twitter OAuth callback |
| `TIKTOK_REDIRECT_URI` | TikTok OAuth callback |
| `GOOGLE_REDIRECT_URI` | YouTube OAuth callback |
| `GMAIL_REDIRECT_URI` | Gmail OAuth callback |
| `GOOGLE_LOGIN_REDIRECT_URI` | Google social login callback |
| `FACEBOOK_LOGIN_REDIRECT_URI` | Facebook social login callback |
| `APP_BASE_URL` | Base URL for all callbacks |

### Estimated Monthly Cost

| Tier | Cost | What You Get |
|------|------|--------------|
| Minimum (AI only) | ~$21/mo | Claude API + basic operations |
| Standard | ~$60–100/mo | + Late API + ElevenLabs + intelligence APIs |
| Full Suite | ~$150–250/mo | + All image models + Twilio + premium features |

---

## Deployment

### Railway (Recommended)

The project includes a `Procfile` for Railway deployment:

```
web: python init_db.py && uvicorn web_app:app --host 0.0.0.0 --port $PORT --timeout-keep-alive 30
```

**Steps:**

1. Push code to GitHub
2. Connect your GitHub repo to [Railway](https://railway.app)
3. Add all environment variables in Railway dashboard
4. Set `DATABASE_URL` to your Railway PostgreSQL connection string
5. Deploy — Railway will detect the Procfile automatically

### Environment Considerations

| Setting | Development | Production |
|---------|------------|------------|
| Database | SQLite (`sqlite:///./automation.db`) | PostgreSQL (Railway) |
| Stripe Keys | `sk_test_*` / `pk_test_*` | `sk_live_*` / `pk_live_*` |
| Debug | `ALITA_DEV_RELOAD=true` | `ALITA_DEV_RELOAD=false` |
| Base URL | `http://localhost:8080` | `https://your-app.up.railway.app` |

---

## CI/CD Pipeline

Three GitHub Actions workflows in `.github/workflows/`:

| Workflow | Trigger | Description |
|----------|---------|-------------|
| `ci.yml` | Push/PR to `main`, `develop` | Runs flake8 linting |
| `deploy.yml` | Push to `main` | Production deployment to Railway |
| `health-check.yml` | Every 15 minutes (cron) | Pings `/health` endpoint, alerts on failure |

---

## Scripts & Utilities

Admin and setup scripts are located in the `scripts/` directory:

| Script | Usage | Description |
|--------|-------|-------------|
| `create_admin.py` | `python scripts/create_admin.py` | Create initial admin user |
| `seed_railway_meta.py` | `python scripts/seed_railway_meta.py` | Seed production database with Meta config |
| `migrate_meta_columns.py` | `python scripts/migrate_meta_columns.py` | Run database column migrations |
| `add_tester.py` | `python scripts/add_tester.py` | Add test user accounts |
| `upgrade_admin_pro.py` | `python scripts/upgrade_admin_pro.py` | Upgrade a user to Pro plan |
| `get_facebook_pages.py` | `python scripts/get_facebook_pages.py` | Fetch Facebook page IDs |
| `get_page_id.py` | `python scripts/get_page_id.py` | Get Instagram business account ID |
| `update_templates.py` | `python scripts/update_templates.py` | Regenerate prompt templates |
| `generate_content.py` | `python scripts/generate_content.py` | Generate sample content for testing |

---

## Documentation

Additional documentation is available in the `docs/` directory:

### Setup Guides (`docs/setup/`)
- Quick Start Guide
- OAuth Setup Guide
- Stripe Payment Setup
- Multi-Platform Setup Guide
- Client Connection Setup
- How to Add a New Client

### Architecture (`docs/architecture/`)
- Agent Workflow Architecture
- Client Connection Architecture
- OAuth Architecture Validation
- Faceless Script Architecture
- Content Type Guidelines

### Features (`docs/features/`)
- Faceless Video System
- Comment Management
- Marketing Intelligence Guide
- Deep Research Feature
- CLI Usage Guide
- Video Customization
- Style Injection Guide
- Pricing Strategy

### Deployment (`docs/deployment/`)
- Unified App Release Guide
- Development Plan & Roadmap
- Meta App Review Plan

---

## License

Copyright (c) 2025–2026 Nexarily AI. All rights reserved.

This is proprietary software. Unauthorized copying, distribution, or modification of this project, via any medium, is strictly prohibited. See [LICENSE](LICENSE) for details.
