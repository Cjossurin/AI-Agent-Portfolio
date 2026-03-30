# Copilot Instructions: Alita AI-Powered Marketing Automation System

**Version 4.1 - Production Ready**

## 🎯 System Overview

You are working on a comprehensive AI automation system that manages complete marketing operations for multiple clients across different niches. The system handles content creation, posting, engagement, and lead conversion with intelligent AI-driven strategy.

### Primary Objective
Build an intelligent automation system that handles multi-client, multi-niche, multi-platform marketing with 24/7 automation, voice matching, and expandable knowledge.

### System Scope
- **Multi-client support:** 10-50+ clients simultaneously
- **Multi-niche capability:** Completely different industries per client
- **Multi-platform distribution:** Facebook, Instagram, TikTok, YouTube, Twitter/X, LinkedIn, Blog, Email
- **24/7 automation:** Minimal human intervention once configured
- **Intelligent decision-making:** AI-driven strategy, not just scheduled posting
- **Voice matching:** AI writes in each client's unique voice/style
- **Expandable knowledge:** Clients can add documents to their knowledgebase
- **Production deployment:** Real infrastructure, real APIs, real costs

## 🗂️ Core System Components (18 Total)

| Component | Status | Priority | Your Responsibilities |
|-----------|--------|----------|----------------------|
| 1. **Orchestration Layer** | ✅ Core Done | P0 - Critical | Content workflow coordination (content_orchestrator.py) |
| 2. **Marketing Intelligence Agent** | 📋 Planned | P1 - High | Generate strategies, analyze performance, optimize campaigns |
| 3. **Content Creation Agent** | ✅ Verified | P0 - Critical | 86 templates, all platforms, voice matching integrated |
| 4. **Growth Agent** | 📋 Planned | P2 - Medium | Audience growth, follower acquisition, optimization |
| 5. **Posting Agent** | ✅ Verified | P0 - Critical | Three-tier routing, Late API integrated (agents/posting_agent.py) |
| 6. **Engagement Agent** | ⚠️  Partial | P0 - Critical | File exists but missing handle_comment/handle_dm implementations |
| 7. **Email Marketing Agent** | 📋 Planned | P3 - Low | Email campaign automation and management |
| 8. **Content Calendar Agent** | ⏳ In Progress | P1 - High | Scheduling, coordination, timing optimization |
| 9. **Analytics & Reporting Agent** | 📋 Planned | P2 - Medium | Performance tracking, insights, client reports |
| 10. **RAG Knowledge System** | ⚠️  Partial | P0 - Critical | File exists, needs retrieve_knowledge/add_document methods |
| 11. **Late API Client** | ✅ Verified | P0 - Critical | Full integration complete (api/late_client.py) |
| 12. **Client Voice Matching System** | ⚠️  Partial | P1 - High | normalize_style.py exists, needs method refactoring |
| 13. **Document Processing Pipeline** | ✅ Upload Done | P1 - High | PDF/DOCX/TXT upload, extraction, chunking, embedding |
| 14. **Deep Research Integration** | 📋 Planned | P2 - Medium | Claude deep research to knowledge base |
| 15. **Master Prompt System** | ✅ Implemented | P0 - Critical | Centralized prompt templates with dynamic variable injection |
| 16. **Conversation Memory System** | ✅ Implemented | P0 - Critical | Platform-compliant conversation history for DM context |
| 17. **Media Library & AI Remix** | 📋 Planned | P2 - Medium | Store, analyze, and remix archived videos/photos |
| 18. **Human Escalation & Guardrails** | ✅ Implemented | P0 - Critical | Keyword-triggered human handoff and abuse protection |

## 📊 Current Progress (50% Complete)

```
Core Infrastructure:        ████████████████ 100% ✅
Platform Integrations:      ████████████░░░░  75% ⏳
Content Generation:         ██████████████░░  85% ✅
Engagement Automation:      ███████████████░  90% ✅
Voice Matching:             ████████████░░░░  75% ⏳
Conversation Memory:        ████████████████ 100% ✅
Prompt Management:          ████████████████ 100% ✅
Analytics/Reporting:        ██░░░░░░░░░░░░░░  10% 📋
Client Management:          ████░░░░░░░░░░░░  25% 📋
Email Marketing:            ░░░░░░░░░░░░░░░░   0% 📋
Media Library:              ░░░░░░░░░░░░░░░░   0% 📋

OVERALL SYSTEM:             ██████████░░░░░░  50%
PRODUCTION READINESS:       ████████████░░░░  70%
```

## 🔌 Platform Integration Strategy

### Three-Tier Platform Routing

**TIER 1: Direct API (Free)**
- Meta (Facebook, Instagram) - Graph API
- YouTube - Data API v3
- WordPress/Blog - REST API

**TIER 2: Third-Party API (Late - $33/mo)**
- TikTok - Full video posting, PUBLIC visibility
- LinkedIn - Company pages + personal profiles
- Twitter/X - Posting + reading (saves $100/mo)
- Threads, Reddit, Pinterest, Bluesky

**TIER 3: Manual Posting Queue (Fallback)**
- Platform API outages
- Unsupported content types
- New platforms not yet integrated

### Why Late API?
- Multi-client support (50+ profiles for $33/mo)
- Cost savings: Replaces Twitter Basic ($100/mo) + solves TikTok/LinkedIn access
- Python SDK, high documented rate limits, 99.97% uptime
- Net savings of $67/mo

## 💰 Production Infrastructure & Costs

### Recommended Stack
- **App Hosting:** Railway / Render ($5-50/mo)
- **Database:** Supabase / PlanetScale (PostgreSQL, $0-25/mo)
- **Vector DB:** Qdrant Cloud (RAG, $0-95/mo)
- **Cache/Queue:** Upstash Redis (Celery, $0-25/mo)
- **File Storage:** Cloudflare R2 / S3 ($0-15/mo)
- **CDN:** Cloudflare (Free)
- **Monitoring:** Sentry, Logtail ($0-20/mo)
- **Late API:** $33-83/mo
- **Claude API:** $10-100+/mo (pay-per-use)
- **Meta Graph API:** Free

### Cost by Scale
- **Startup (1-5 clients):** $48/mo
- **Growth (5-20 clients):** $158/mo
- **Scale (20-50 clients):** $393/mo

### Cost Per Client
- 5 clients: $9.60/client
- 20 clients: $7.90/client
- 50 clients: $7.86/client
- **Target pricing:** $300-500/month per client
- **Gross margin:** 93-98%

---

# Copilot Instructions: Deep Research to Knowledge Base

---

## 🛠️ Implementation Phases & Priorities

### Phase 1: Foundation (✅ COMPLETED)
1. ✅ Database schema setup (PostgreSQL + Qdrant)
2. ✅ RAG document processing pipeline
3. ✅ Late API integration for multi-platform posting
4. ✅ Webhook receiver for platform events
5. ✅ Basic engagement agent (comments, DMs, story mentions)

### Phase 2: Core Automation (⏳ IN PROGRESS - 60% COMPLETE)
1. ✅ Content creation templates and prompts
2. ⏳ Voice matching system (80% complete)
3. ⏳ Content calendar coordination (40% complete)
4. 📋 Multi-client isolation and routing
5. 📋 Basic analytics tracking

### Phase 3: Intelligence Layer (📋 NEXT UP)
1. Marketing strategy generation
2. Automated content planning
3. Engagement optimization
4. Growth strategy automation
5. Performance-based adjustments

### Phase 4: Advanced Features (📋 PLANNED)
1. **Deep Research to Knowledge Base** (see below)
2. **Media Library & AI Remix** ⚠️ BUILD, TEST, PERFECT in this order:
   - **Build:** After Content Creation, Voice Matching, Calendar are stable
   - **Test:** Start with 10-50 videos to validate AI scene analysis
   - **Perfect:** Iterate on remix quality before client rollout
   - See `MEDIA_LIBRARY_FEATURE.md` for full plan
3. Email marketing integration
4. Advanced analytics and reporting
5. A/B testing framework
6. Predictive content optimization
6. Client dashboard and portal

### Phase 5: Scale & Polish (📋 FUTURE)
1. Multi-region deployment
2. Advanced caching strategies
3. Cost optimization
4. White-label customization
5. Self-service client onboarding

### What's Working Now
- ✅ Webhook reception from Instagram, Facebook, TikTok
- ✅ Automated comment responses using RAG knowledge
- ✅ DM handling with context-aware responses
- ✅ Story mention tracking and response
- ✅ Document upload and processing (PDF, DOCX, TXT)
- ✅ Multi-platform posting via Late API
- ✅ Client voice extraction and matching

### What's Next
- 🎯 Complete voice matching UI and feedback system
- 🎯 Build content calendar coordination
- 🎯 Implement multi-client routing and isolation
- 🎯 Add basic analytics dashboard
- 🎯 Create client onboarding workflow
- 🎯 Build client dashboard framework (auth, navigation, user context)
- 🎯 Implement Deep Research to Knowledge Base (Phase 4)

---

## New Feature: Deep Research to Knowledge Base

You are responsible for supporting a new feature that allows clients to submit research queries, receive AI-generated research (with citations), and—after review—add the results to their knowledge base for retrieval-augmented generation (RAG).

### Key Responsibilities
- Implement and maintain a dashboard page for research queries and review
- Ensure backend endpoint accepts queries, calls Claude API (deep research), and stores results for review
- Track research status: `pending_review`, `approved`, `denied`
- Integrate approved research into the RAG/document pipeline, tagging with `source_type="deep_research"` and including the original query in metadata
- Follow existing document upload/review architecture patterns

### Workflow
1. Client submits a research query via dashboard
2. Backend processes query, returns research results with citations, and stores in `research_requests` table
3. Client reviews results; can approve (adds to knowledge base) or revise/deny
4. Approved research is processed through the document pipeline and made available for RAG

### Database Schema
- Table: `research_requests`
- Columns: `id`, `client_id`, `query`, `results`, `status`, `created_at`, `approved_at`
- Index: (`client_id`, `status`)

### Integration
- Approved research is treated as a document source in the RAG pipeline
- Tag with `source_type="deep_research"`
- Store original query in metadata

### UI/UX
- Form for research query
- Results preview with citations
- Approve/Revise workflow

---

**Always follow the above workflow and patterns when implementing or updating this feature.**

---

## Feature: Human Escalation System

**Status: ✅ Implemented**

This feature allows users to request a real human by using keywords, which stops automated responses and notifies the team.

### How It Works
1. **Keyword Detection**: Before generating AI responses, the system checks incoming messages for escalation keywords:
   - "human", "agent", "person", "real person", "real human"
   - "speak to someone", "talk to someone", "live person", "live agent"
   - "representative", "support", "help me", "speak with"

2. **Escalation Process**:
   - User's sender ID is added to `escalated_conversations` set
   - Automated responses are stopped for that conversation
   - User receives: "I'll connect you with someone from the team. They'll respond shortly! 💬"

3. **Notification**:
   - Terminal shows attention-grabbing alert with sender ID and message
   - Escalation is logged to `escalations.txt` for persistent tracking

4. **Management Endpoints**:
   - `GET /escalations` - List all escalated conversations
   - `DELETE /escalations/{sender_id}` - Clear specific escalation (resume automation)
   - `DELETE /escalations` - Clear all escalations

### Instagram Bio Update
Add to @nexarilyai bio: **"Reply 'HUMAN' to speak with a real person"**

### Implementation Location
- File: `webhook_receiver.py`
- Functions: `check_escalation_keywords()`, `log_escalation()`
- Global: `escalated_conversations` set, `ESCALATION_KEYWORDS` list

---

## Feature: Global Guardrails System

**Status: ✅ Implemented (January 24, 2026)**

A global input validation and content filtering system that protects all agents from abuse, inappropriate content, and resource-exhausting requests.

### What It Protects Against
| Guardrail | Description | Example |
|-----------|-------------|---------|
| **Length** | Blocks excessively long messages | Messages over 2000 chars or 500 words |
| **Repetition** | Blocks repeated words/characters | "hello hello hello hello..." |
| **Profanity** | Blocks inappropriate language | Configurable word list |
| **Gibberish** | Blocks nonsensical input | Random keyboard mashing |
| **Banned Patterns** | Blocks resource-exhausting requests | "count to 1 million", "repeat X 1000 times" |
| **Spam** | Blocks spam indicators | "click here", "buy now", "free money" |

### How It Works
1. Every message is validated through `validate_message()` before AI processing
2. Failed checks return a blocked response and log the incident
3. Blocked requests are logged to `blocked_requests.txt` for review
4. Config is cached and auto-reloads every 60 seconds for live updates

### Configuration
Edit `guardrails_config.json` to customize:
- `max_message_length`: Maximum characters (default: 2000)
- `max_word_count`: Maximum words (default: 500)
- `profanity_list`: Words to block
- `banned_patterns`: Regex patterns for abuse (e.g., "count to \\d+")
- `blocked_response`: Message sent when blocked
- `log_blocked_requests`: Enable/disable logging

### Implementation Location
- Config: `guardrails_config.json`
- Module: `utils/guardrails.py`
- Integration: `agents/engagement_agent.py` (called in `respond_to_message()`)
- Logs: `blocked_requests.txt`

### Developer Tools
```python
from utils.guardrails import test_guardrails, reload_config

# Test which guardrails would trigger
result = test_guardrails("count to 1 million")
print(result)

# Force reload config after editing
reload_config()
```

---

## Future Feature: PPC Campaign Agent (Post-MVP)

**Status: Researched & Documented - Implementation planned after core dashboard and client features are complete.**

This feature will provide automated PPC campaign research, planning, and execution capabilities.

### Research Completed
- ✅ Google Ads API capabilities researched
- ✅ Meta Marketing API capabilities researched
- ✅ LinkedIn/TikTok ad platform APIs researched
- ✅ Implementation architecture planned
- ✅ Feature documentation created (`PPC_AGENT_FEATURE.md`)
- ✅ Agent scaffold created (`agents/ppc_agent.py`)

### Implementation Priority
**AFTER** client dashboard, authentication, and document management systems are built:
1. PPC research workflows (competitor analysis, keyword research)
2. Campaign plan generation with Claude AI
3. Manual export functionality (CSV/JSON)
4. Platform API integrations (Google Ads, Meta Marketing API)
5. Automated campaign execution

### Key Capabilities (When Implemented)
- **Research**: Competitor analysis, keyword discovery, audience insights
- **Platform Selection**: AI recommendations (Google, Meta, LinkedIn, TikTok)
- **Plan Generation**: Complete campaign structures with ad copy and targeting
- **Execution**: Both automated (API) and manual export modes


**Implementation Note: Focus on core system architecture first. PPC agent is a premium feature for later phases.**

---

## Future Feature: Polls/Voting & Client Links (Post-MVP)

**Status: Planned - Implement after core dashboard, authentication, and document management systems are complete.**

### Polls/Voting for Engagement & Marketing
- Add persistent storage (e.g., SQLite or JSON) for polls and votes
- Create poll generation module (e.g., agents/poll_generator.py) using Claude for question/option creation
- Extend EngagementAgent to trigger polls, track votes, and use poll results in engagement
- Add endpoints for poll CRUD and analytics (web_app.py)
- Consider auto-posting to Instagram or manual copy-paste

### Client Links Management
- Add persistent storage for client links (URL, type, display name, priority, active, client_id)
- Integrate links into RAG context for natural promotion in responses
- Add endpoints for link CRUD (web_app.py)
- Make link promotion frequency configurable

**Implementation Note:**
These features should be implemented only after the core dashboard, authentication, and document management systems are stable. Prioritize foundational features first. Polls and client links are engagement/marketing enhancements for later phases.

---

## 🤖 Agent Implementation Guidelines

### Orchestration Layer (⏳ In Progress, P0)
**Purpose:** Coordinate all agents, manage workflows, handle task routing  
**Responsibilities:**
- Route tasks to appropriate agents
- Manage agent dependencies and sequencing
- Handle failures and retries
- Coordinate multi-step workflows
- Maintain system state and context

**Implementation Notes:**
- Use Celery + Redis for task queue
- Implement retry logic with exponential backoff
- Log all orchestration decisions for debugging
- Maintain task status tracking

### Marketing Intelligence Agent (📋 Planned, P1)
**Purpose:** Generate strategies, analyze performance, optimize campaigns  
**Responsibilities:**
- Analyze market trends and competitor activity
- Generate content strategies
- Optimize posting times and frequency
- Recommend platform-specific tactics
- Performance analysis and insights

**Implementation Notes:**
- Integrate with Analytics & Reporting Agent
- Use Claude for strategic insights
- Cache strategy recommendations
- Implement A/B testing framework

### Content Creation Agent (⏳ In Progress, P0)
**Purpose:** AI-powered content generation with voice matching  
**Responsibilities:**
- Generate platform-specific content
- Match client voice and style
- Create captions, hashtags, CTAs
- Adapt content for different platforms
- Maintain brand consistency

**Implementation Notes:**
- Use Client Voice Matching System
- Leverage RAG Knowledge System for context
- Cache generated content for review
- Implement approval workflow

### Growth Agent (📋 Planned, P2)
**Purpose:** Audience growth, follower acquisition, optimization  
**Responsibilities:**
- Identify growth opportunities
- Recommend engagement tactics
- Track follower trends
- Optimize profile and bio
- Suggest collaboration opportunities

**Implementation Notes:**
- Integrate with Analytics Agent
- Monitor platform algorithm changes
- Track growth metrics
- Implement gradual ramp-up for new accounts

### Posting Agent (✅ Core Done, P0)
**Purpose:** Multi-platform posting via Late API  
**Responsibilities:**
- Schedule and publish posts
- Handle platform-specific formatting
- Manage media uploads
- Track posting status
- Implement retry logic

**Implementation Notes:**
- Use Late API for TikTok, LinkedIn, Twitter/X
- Use Meta Graph API for Facebook, Instagram
- Implement fallback to manual queue
- Log all posting activities

### Engagement Agent (✅ Comments Done, P0)
**Purpose:** Handle DMs, comments, story mentions  
**Responsibilities:**
- Monitor incoming engagement
- Respond to comments and DMs
- Track story mentions
- Escalate to human when needed
- Maintain conversation context

**Implementation Notes:**
- Use RAG Knowledge System for context
- Implement human escalation keywords
- Apply guardrails to all responses
- Log all interactions

### Email Marketing Agent (📋 Planned, P3)
**Purpose:** Email campaign automation and management  
**Responsibilities:**
- Create email campaigns
- Segment audiences
- Personalize content
- Track open/click rates
- Optimize send times

**Implementation Notes:**
- Integrate with email service provider (e.g., SendGrid, Mailchimp)
- Use voice matching for personalization
- Implement A/B testing
- Track campaign performance

### Content Calendar Agent (⏳ In Progress, P1)
**Purpose:** Scheduling, coordination, timing optimization  
**Responsibilities:**
- Plan content calendar
- Optimize posting schedule
- Coordinate cross-platform campaigns
- Balance content types
- Manage content pipeline

**Implementation Notes:**
- Integrate with Marketing Intelligence Agent
- Consider time zones and audience availability
- Implement conflict resolution
- Allow manual overrides

### Analytics & Reporting Agent (📋 Planned, P2)
**Purpose:** Performance tracking, insights, client reports  
**Responsibilities:**
- Track engagement metrics
- Generate performance reports
- Identify trends and patterns
- Provide actionable insights
- Create client dashboards

**Implementation Notes:**
- Aggregate data from all platforms
- Use data visualization libraries
- Implement custom report templates
- Schedule automated report delivery

### RAG Knowledge System (✅ Pipeline Done, P0)
**Purpose:** Document processing, retrieval, knowledge management  
**Responsibilities:**
- Process uploaded documents (PDF, DOCX, TXT)
- Extract and chunk text
- Generate embeddings
- Store in Qdrant vector database
- Retrieve relevant context for queries

**Implementation Notes:**
- Use Voyage AI or OpenAI Ada for embeddings
- Implement client-scoped isolation
- Tag documents with source_type
- Maintain metadata for context

### Late API Client (✅ Integration Ready, P0)
**Purpose:** Multi-platform posting integration  
**Responsibilities:**
- Post to TikTok, LinkedIn, Twitter/X, etc.
- Handle platform-specific formatting
- Manage webhook callbacks
- Track post status
- Implement error recovery

**Implementation Notes:**
- Use Late API Accelerate tier ($33/mo)
- Implement webhook signature verification
- Cache platform credentials
- Fallback to manual queue on failure

### Client Voice Matching System (⏳ In Progress, P1)
**Purpose:** Extract and replicate client writing style  
**Responsibilities:**
- Analyze client writing samples
- Extract style patterns
- Generate style profile
- Match voice in generated content
- Provide feedback mechanism

**Implementation Notes:**
- Minimum 5+ samples for quality
- Use Claude for style extraction
- Cache style profiles indefinitely
- Allow manual refinement

### Document Processing Pipeline (✅ Upload Done, P1)
**Purpose:** PDF/DOCX/TXT upload, extraction, chunking, embedding  
**Responsibilities:**
- Accept file uploads
- Extract text from documents
- Chunk text appropriately
- Generate embeddings
- Store in vector database

**Implementation Notes:**
- Support PDF, DOCX, TXT formats
- Implement client-scoped storage
- Track upload status
- Provide upload feedback

### Deep Research Integration (📋 Planned, P2)
**Purpose:** Claude deep research to knowledge base  
**Implementation:** See "Deep Research to Knowledge Base" section below

### Master Prompt System (✅ Implemented, P0)
**Purpose:** Centralized prompt templates with dynamic variable injection  
**Responsibilities:**
- Maintain matrix of prompt templates (content_type × platform)
- Support dynamic injection of {client_voice} and {rag_context}
- Allow user-defined master prompts for each content type/platform
- Provide fallback/default templates

**Implementation Notes:**
- File: `prompt_templates.py`
- Templates: facebook_post, instagram_reel, linkedin_article, twitter_thread, etc.
- Integration: Content Creation Agent uses `get_prompt_template(platform, content_type)`
- User updates templates directly in prompt_templates.py

### Conversation Memory System (✅ Implemented, P0)
**Purpose:** Platform-compliant conversation history for DM context  
**Responsibilities:**
- Store recent message history per thread (max 20 messages, 24h TTL)
- Track user consent for data storage
- Provide conversation context to Engagement Agent
- Automatic cleanup of expired conversations
- GDPR and platform policy compliant

**Implementation Notes:**
- File: `conversation_memory.py`
- Integration: Engagement Agent (`thread_id` parameter enables memory)
- Consent: Required before storing any data
- Data minimization: Only recent messages, automatic expiry

### Media Library & AI Remix (📋 Planned, P2 - DO NOT IMPLEMENT YET)
**Purpose:** Store, analyze, and remix archived videos/photos  
**Status:** ⚠️ DOCUMENTATION ONLY - Build in Phase 4 after Content Creation, Voice Matching, and Calendar are tested

**When to Implement:**
1. **Prerequisites:** Content Creation Agent tested and stable, Voice Matching working, Content Calendar operational
2. **Build Phase:** Phase 4 (8-10 weeks estimated)
3. **Test Phase:** Start with 10-50 videos, validate AI scene analysis accuracy
4. **Perfect Phase:** Iterate on remix quality before client rollout

**Responsibilities:**
- Upload and store client media (Instagram/Facebook archives)
- AI scene analysis (GPT-4 Vision or Google Cloud Vision)
- Semantic search for clips by scene, mood, keywords
- Automated content remixing for stories, reels, highlights
- Multi-client isolation

**Implementation Notes:**
- File: `MEDIA_LIBRARY_FEATURE.md` (detailed implementation plan - DO NOT START YET)
- Storage: Cloudflare R2 or AWS S3
- AI Analysis: GPT-4 Vision API for scene description
- Vector Search: Qdrant for semantic search
- Integration: Content Creation Agent can trigger remixes
- Timeline: 8-10 weeks (Phase 4 ONLY - after prerequisites complete)

---

## Platform Integration & Cost Management (Production Readiness)

**You must ensure the following services and integrations are included in all production deployments and documentation:**

- **App Hosting:** Railway (MVP+), Render, DigitalOcean, AWS (as needed)
- **Database:** Supabase/PlanetScale (PostgreSQL)
- **Vector DB:** Qdrant Cloud (RAG, semantic search)
- **Cache/Queue:** Upstash Redis (Celery, async tasks)
- **File Storage:** Cloudflare R2 or AWS S3 (media, docs)
- **CDN:** Cloudflare (static/media delivery)
- **Monitoring/Logging:** Sentry, Logtail (production monitoring)
- **Faceless Video Generation:** Third-party API (e.g., Synthesia, HeyGen) for video content (add when video content is required)
- **API Posting (Multi-Platform):** Late API (getlate.dev) for TikTok, LinkedIn, Twitter/X, etc. (add as soon as multi-platform posting is needed)
- **AI/LLM:** Claude API (Anthropic), OpenAI (as needed)
- **Meta Graph API:** Facebook/Instagram (direct)
- **YouTube, TikTok, LinkedIn, Twitter/X:** Use Late API for posting unless direct API is required/available

### Implementation Timing
- **MVP:** Railway, Supabase, Qdrant, Upstash, Cloudflare R2, Meta Graph API, Claude API, basic monitoring
- **Post-MVP (Growth):** Add Late API for multi-platform posting, Sentry/Logtail for advanced monitoring, faceless video API if video content is needed, scale Upstash/Qdrant as usage grows
- **Scale:** Upgrade all services to paid tiers as client count/usage increases. Add Render/DigitalOcean/AWS as needed for redundancy or scale. Expand monitoring, backup, and analytics.

**Always document which services are in use, their costs, and when to implement/upgrade them.**

## Faceless Video Generation (When Needed)
- Integrate third-party video APIs (e.g., Synthesia, HeyGen) for automated video content. Add this feature when client or campaign requires video posts. Track costs and API usage.

## Late API for Multi-Platform Posting
- Use Late API (getlate.dev) for TikTok, LinkedIn, Twitter/X, Threads, Reddit, Pinterest, Bluesky, etc. Integrate as soon as posting to these platforms is required. Document API key management, webhook setup, and fallback/manual queue for outages.

## Storage, Queue, and Monitoring
- Use Upstash Redis for async tasks and caching. Use Cloudflare R2 or S3 for all file/media storage. Add Sentry and Logtail for error and performance monitoring as soon as you move to production.

## Cost Tracking
- Always update cost breakdowns in documentation and Confluence as you add/scale services. Include faceless video, Late API, storage, queue, and monitoring in all cost models.

## Implementation Roadmap (Summary)

1. **MVP:**
   - Railway, Supabase, Qdrant, Upstash, Cloudflare R2, Meta Graph API, Claude API
   - Direct posting to Facebook/Instagram
   - Basic monitoring/logging
2. **Growth:**
   - Add Late API for TikTok, LinkedIn, Twitter/X, etc.
   - Add Sentry/Logtail for advanced monitoring
   - Add faceless video API if/when video content is needed
   - Begin scaling Upstash/Qdrant as usage grows
3. **Scale:**
   - Upgrade all services to paid tiers as needed
   - Add Render/DigitalOcean/AWS for redundancy/scale
   - Expand monitoring, backup, analytics, and reporting

**Update this roadmap as new services or requirements emerge.**


---

## 🎨 Web UI Design System

**Rule: ALL app pages MUST use `build_page()` from `utils/shared_layout.py`.  
Never write raw `<!DOCTYPE html>` for app pages.  
Exception: Mid-OAuth interstitial callback pages (e.g., success/failure redirects in `client_connections_routes.py`) may use isolated minimal HTML.**

### Using `build_page()`

```python
from utils.shared_layout import build_page

return HTMLResponse(build_page(
    title="Page Title",           # Browser tab title
    active_nav="settings",        # Highlights sidebar item (see valid values below)
    body_content=html_string,     # Your page HTML (no <html>/<body> tags)
    user_name=user.full_name,
    business_name=profile.business_name,
    extra_css="",                 # Optional additional CSS string
    extra_js="",                  # Optional JS string (no <script> tags)
    topbar_title=None,            # Optional custom topbar title
))
```

### Valid `active_nav` Values

`dashboard` · `create-post` · `calendar` · `inbox` · `comments` · `notifications` · `analytics` · `image-generator` · `social` · `email-marketing` · `intelligence` · `settings` · `connect` · `auto-reply` · `tone` · `knowledge` · `creative` · `email` · `security` · `billing`

### Design Tokens

| Token | Value | Usage |
|-------|-------|-------|
| Page background | `#f0f2f5` | Applied by `build_page()` automatically |
| Primary text | `#1c1e21` | Body copy, headings |
| Muted / secondary text | `#90949c` | Subtitles, hints, labels |
| Border / divider | `#dde0e4` | Card borders, `<hr>` |
| Brand purple | `#5c6ac4` | Buttons, active states, highlights |
| Brand gradient | `linear-gradient(135deg, #5c6ac4, #764ba2)` | Hero elements, primary CTAs |
| Active nav bg | `#ede8f5` | Sidebar active item background |
| Active nav text | `#5c6ac4` | Sidebar active item text |

### Card Pattern

```html
<div class="card">
  <h2>Section Title</h2>
  <div class="sub">One-sentence description of what this section does.</div>
  <!-- content -->
</div>
```

Equivalent inline style (when `_SETTINGS_CSS` is not loaded):
```html
<div style="background:#fff;border-radius:12px;padding:24px;
            box-shadow:0 1px 4px rgba(0,0,0,.06);margin-bottom:24px">
```

### Button Patterns

```html
<!-- Primary action -->
<button type="submit" class="btn-primary">Save Changes</button>

<!-- Secondary / cancel -->
<a href="/settings" class="btn-secondary">← Back</a>

<!-- Danger -->
<button class="btn-danger">Delete</button>
```

### Section Grouping Label (between cards)

```html
<div class="hub-section-title">⚙️ Section Name</div>
```

### Typography

```html
<!-- Page-level title (once per page, at top) -->
<h1 style="font-size:1.4rem;font-weight:700;color:#1c1e21;margin:0 0 6px">Page Name</h1>
<p style="color:#90949c;font-size:.9rem;margin:0">One-line page description.</p>

<!-- Card heading (inside card) -->
<h2>Card Title</h2>

<!-- Hint text inside a card -->
<div class="sub">Descriptive hint. Keep to one or two sentences.</div>
```

### Notice / Alert Boxes

```html
<!-- Warning / tip -->
<div class="notice">Important note. <strong>Bold key words.</strong></div>

<!-- Success -->
<div style="background:#e8f5e9;border-left:4px solid #27ae60;padding:12px 16px;
            border-radius:0 8px 8px 0;font-size:.88rem;color:#2e7d32">
  ✅ Action completed successfully.
</div>
```

### Input Fields

Always use `.s-input` for consistent focus states:

```html
<input type="text" class="s-input" placeholder="...">
<textarea class="s-input" rows="4" placeholder="..."></textarea>
<select class="s-input">...</select>
```

### Toggle Switch

```html
<label class="sw">
  <input type="checkbox" id="my-toggle" onchange="handleToggle()">
  <span class="sw-track"></span>
</label>
```

### Grid Layouts

```css
/* Two equal columns */
display:grid; grid-template-columns:1fr 1fr; gap:16px;

/* Responsive card grid */
display:grid; grid-template-columns:repeat(auto-fill,minmax(255px,1fr)); gap:16px;
```

### Known Non-Uniform Pages (Technical Debt — migrate when touched)

- `api/oauth_routes.py` — Meta OAuth flow pages
- `api/platform_oauth_routes.py` — Platform OAuth callbacks
- `api/threads_routes.py` — Threads OAuth page

OAuth interstitial callbacks in `api/client_connections_routes.py` are **intentionally** standalone HTML and do not need migrating.
