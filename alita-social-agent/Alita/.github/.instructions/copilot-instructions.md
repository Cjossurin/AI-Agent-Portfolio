# GitHub Copilot Instructions for Alita Project

## Project Overview
Alita is an AI-powered social media and marketing automation system that manages complete marketing operations for multiple clients across different niches. The system handles content creation, engagement, lead conversion, and multi-platform distribution with 24/7 automation.

### Core Value Proposition
- **Multi-client support:** Handle 10-50+ different clients simultaneously
- **Multi-niche capability:** Each client can be in completely different industries
- **Multi-platform distribution:** Facebook, Instagram, TikTok, YouTube, Twitter/X, LinkedIn, Blog, Email
- **Voice matching:** AI writes in each client's unique voice/style
- **Expandable knowledge:** Clients can add documents to their RAG knowledgebase

---

## Architecture Overview

### Development Strategy: Complete Local Build First
**Status: Full Development Phase - Build All Components Before Deployment**

| Component | Development Approach | Final Service |
|-----------|---------------------|---------------|
| All Agents | Local development & testing | Complete before deployment |
| Client Dashboard | Full feature development | Complete before deployment |
| Database | Local PostgreSQL/SQLite | Railway/Supabase (production) |
| Vector DB | Local Qdrant | Qdrant Cloud (production) |
| Redis | Local Redis | Upstash (production) |
| APIs | Development keys | Production keys (final) |

**Focus: Complete all 11 agents and dashboard locally before any production deployment.**

### Architecture Type: Monolithic (Initially)
- Single Python application containing all agents
- Message queue for task management (Celery + Redis)
- Vector database for knowledge storage (Pinecone/Qdrant)
- PostgreSQL for relational data
- External API integrations for all platforms

### Core Components
1. **Orchestration Layer** - Central router and coordinator
2. **Marketing Intelligence Agent** - Master planner and strategist
3. **Content Creation Agent** - Multi-format content generator
4. **Growth Agent** - Audience building and engagement
5. **Posting Agent** - Multi-platform distribution with platform routing
6. ✅ **Engagement Agent** - Real-time interaction handling (Comments, DMs, Story Mentions)
7. **Email Marketing Agent** - Campaign management and automation
8. **Content Calendar Agent** - Scheduling and coordination
9. **Analytics & Reporting Agent** - Performance tracking
10. ✅ **RAG Knowledge System** - Multi-niche knowledge base (Qdrant + OpenAI embeddings)
11. **Late API Client** - Third-party platform integration
12. **Client Voice Matching System** - AI writes in client's style
13. ✅ **Document Processing Pipeline** - Automated ingestion of PDF, DOCX, and TXT files via `ingest.py`
14. ✅ **Webhook Receiver** - Instagram Comments, DMs, Story Mentions with idempotency

---

## Platform Integration Strategy

### Three-Tier Platform Routing

```python
PLATFORM_CONFIG = {
    # Tier 1: Direct API (Free)
    "facebook": {"method": "direct", "api": "Meta Graph API"},
    "instagram": {"method": "direct", "api": "Meta Graph API"},
    "youtube": {"method": "direct", "api": "YouTube Data API v3"},
    "blog": {"method": "direct", "api": "WordPress REST API"},
    
    # Tier 2: Via Late API ($33/mo total)
    "tiktok": {"method": "late", "api": "Late unified API"},
    "linkedin": {"method": "late", "api": "Late unified API"},
    "twitter": {"method": "late", "api": "Late unified API"},
    "threads": {"method": "late", "api": "Late unified API"},
    "reddit": {"method": "late", "api": "Late unified API"},
    "pinterest": {"method": "late", "api": "Late unified API"},
    "bluesky": {"method": "late", "api": "Late unified API"},
    
    # Tier 3: Manual fallback
    "snapchat": {"method": "manual", "api": None}
}
```

### Platform Routing in Code
When implementing posting functionality:
- Check platform tier before posting
- Use direct API for Tier 1 platforms
- Use Late API client for Tier 2 platforms
- Queue to manual_post_queue for Tier 3 or failures

---

## Code Style Guidelines

### Python Standards
- Use Python 3.11+ features
- Follow PEP 8 style guidelines
- Use type hints for ALL function parameters and return values
- Write docstrings for all classes and functions
- Keep functions small and focused (single responsibility)
- Use async/await for I/O operations

### Type Hints Example
```python
from typing import Optional, List
from dataclasses import dataclass

@dataclass
class PostResult:
    platform: str
    success: bool
    post_id: Optional[str] = None
    method: str = "direct"
    error: Optional[str] = None

async def post_content(
    content: Content,
    platforms: List[str],
    client_id: str
) -> List[PostResult]:
    """Post content to specified platforms."""
    pass
```

---

## Directory Structure

```
alita/
├── agents/                    # All agent implementations
│   ├── __init__.py
│   ├── engagement_agent.py    # ✅ Real-time interaction handling
│   ├── content_agent.py       # Content creation
│   ├── posting_agent.py       # Multi-platform posting
│   ├── growth_agent.py        # Audience growth
│   ├── marketing_agent.py     # Strategy planning
│   ├── email_agent.py         # Email campaigns
│   ├── calendar_agent.py      # Content scheduling
│   ├── analytics_agent.py     # Reporting
│   └── rag_system.py          # ✅ Knowledge retrieval
├── api/                       # API clients
│   ├── late_client.py         # Late API integration
│   ├── meta_client.py         # Facebook/Instagram
│   └── youtube_client.py      # YouTube
├── database/                  # Database models and queries
├── storage/                   # File storage handling
├── utils/                     # ✅ Shared utility functions
│   ├── __init__.py
│   └── file_reader.py         # PDF/DOCX/TXT extraction
├── style_references/          # ✅ Writing samples for tone matching
│   ├── README.md
│   └── {client_id}/          # Client-specific styles (optional)
├── raw_style_inputs/          # ✅ Messy chat logs (before normalization)
│   └── README.md
├── knowledge_docs/            # ✅ Documents for RAG ingestion
├── normalize_style.py         # ✅ Chat log cleaning utility
├── webhooks/                  # Webhook handlers
├── models/                    # Pydantic models
├── main.py                    # Application entry
├── ingest.py                  # ✅ Knowledge ingestion script
├── webhook_receiver.py        # ✅ FastAPI webhook endpoints
└── web_app.py                 # Web interface
```

---

## Naming Conventions

### Python
- `snake_case` for functions and variables
- `PascalCase` for classes
- `UPPER_CASE` for constants
- Prefix private methods with underscore `_`
- Use descriptive names that indicate purpose

### Database Tables
- Use snake_case for table names
- Use plural names for tables: `clients`, `voice_samples`, `posts`
- Foreign keys: `{table_singular}_id` (e.g., `client_id`)

### API Endpoints
- Use lowercase with hyphens: `/webhook`, `/health`, `/api/v1/posts`
- RESTful conventions: GET for read, POST for create, PUT for update, DELETE for remove

---

## Database Schema Patterns

### Core Tables Structure
```python
# Always include these fields in tables:
base_fields = {
    "id": "UUID PRIMARY KEY DEFAULT gen_random_uuid()",
    "created_at": "TIMESTAMP DEFAULT NOW()",
    "updated_at": "TIMESTAMP DEFAULT NOW()"
}

# Client isolation - ALWAYS filter by client_id
# Never allow cross-client data access
```

### Key Tables
- `clients` - Client identification and configuration
- `platform_connections` - OAuth tokens and Late account mappings
- `content` - All content items
- `content_calendar` - Scheduled posts with posting method
- `engagement_log` - All interactions
- `voice_samples` - Client voice samples for matching
- `client_voice_settings` - Voice profiles
- `client_documents` - Uploaded documents for RAG
- `knowledge_chunks` - Processed document chunks
- `manual_post_queue` - Fallback queue for failed posts
- `rate_limits` - Track API usage per platform

---

## Agent Implementation Patterns

### Base Agent Structure
```python
from abc import ABC, abstractmethod
from typing import Optional
import logging

class BaseAgent(ABC):
    """Base class for all agents."""
    
    def __init__(self, client_id: str):
        self.client_id = client_id
        self.logger = logging.getLogger(self.__class__.__name__)
    
    @abstractmethod
    async def process(self, request: dict) -> dict:
        """Process incoming request."""
        pass
    
    async def get_client_voice_profile(self) -> Optional[dict]:
        """Retrieve client's voice profile for content generation."""
        pass
    
    async def query_rag(self, query: str) -> list:
        """Query RAG system for client-specific knowledge."""
        pass
```

### Engagement Response Flow
When generating responses:
1. Classify engagement (question/compliment/complaint)
2. Query RAG system for relevant knowledge
3. Retrieve client voice profile
4. Generate response with AI in client's voice
5. Check if escalation needed
6. Send response via appropriate API

---

## Style Injection System (✅ IMPLEMENTED)

### How It Works
The bot loads writing samples from the `style_references/` folder on startup and uses them to match your tone and style.

### Folder Structure
```
style_references/
├── README.md                   # Usage instructions
├── my_past_dms.pdf            # Your writing samples
├── instagram_replies.txt
└── {client_id}/               # Client-specific (future)
    └── client_style.pdf
```

### Implementation Details
- **File reading**: Shared utilities in `utils/file_reader.py`
- **Loading**: Once on startup in `EngagementAgent.__init__()`
- **Supported formats**: PDF, DOCX, TXT
- **Fallback**: If no files found, uses default neutral tone
- **Per-client**: Checks `style_references/{client_id}/` first, then root folder

### Usage

**Option A: Normalize Messy Chat Logs (Recommended)**
1. Drop raw chat exports (PDF/DOCX/TXT) into `raw_style_inputs/`
2. Run `python normalize_style.py` to clean with Claude AI
3. Claude extracts and formats your writing style automatically
4. Output saved to `style_references/demo_client/normalized_samples.txt`
5. Restart the bot to load the cleaned samples

**Option B: Add Pre-Formatted Samples**
1. Export your past DM conversations or social media posts to PDF/DOCX/TXT
2. Drop files into `style_references/` folder
3. Restart the bot - it will load and mimic your style
4. Add 10-20 samples for best results

### normalize_style.py Utility
- **Purpose**: Converts messy chat logs into clean training data
- **Model**: Uses `claude-sonnet-4-20250514` for intelligent parsing
- **Input**: Raw chat logs in `raw_style_inputs/`
- **Output**: Formatted samples in `style_references/demo_client/normalized_samples.txt`
- **Format**: `Context: [them] → My Reply: [you]`

---

## Voice Matching System

### Voice Profile Structure
```python
voice_profile = {
    "style_description": "Friendly and approachable...",
    "detected_tone": "friendly",  # friendly/professional/casual/witty/formal
    "common_phrases": ["Happy to help!", "Great question!"],
    "average_response_length": 45,
    "traits": {
        "uses_emojis": True,
        "emoji_frequency": "low",
        "asks_questions": True,
        "uses_exclamations": True,
        "formality_level": "casual-professional"
    }
}
```

### Voice Sample Requirements
- Minimum 5 samples to activate voice matching
- 5-9 samples = Basic accuracy
- 10-19 samples = Good accuracy
- 20+ samples = Excellent accuracy

### Situation Categories
```python
SITUATION_TYPES = [
    # Engagement (replying)
    "question", "compliment", "complaint", "general_comment",
    # Content creation
    "promotional_post", "educational_post", "entertaining_post", "personal_post",
    # Direct messages
    "inquiry_dm", "lead_dm", "support_dm", "followup_dm"
]
```

---

## Late API Integration

### Client Setup
```python
from dataclasses import dataclass
from typing import Optional, List
import httpx
import os

class LateAPIClient:
    BASE_URL = "https://getlate.dev/api/v1"
    
    def __init__(self, api_key: str = None):
        self.api_key = api_key or os.getenv("LATE_API_KEY")
        self.client = httpx.AsyncClient(
            base_url=self.BASE_URL,
            headers={"Authorization": f"Bearer {self.api_key}"},
            timeout=30.0
        )
    
    async def create_post(self, text: str, platforms: List[str], 
                         media_urls: Optional[List[str]] = None) -> dict:
        """Create a post across multiple platforms."""
        pass
    
    async def health_check(self) -> bool:
        """Check if Late API is available."""
        pass
```

### Rate Limits by Tier
- Free: 60 requests/minute
- Build ($13/mo): 120 requests/minute
- Accelerate ($33/mo): 600 requests/minute ← **Recommended for production**
- Unlimited ($83/mo): 1200 requests/minute ← **Best for high volume**

### Current Status: Production Ready
We have capital for paid services. Use Accelerate or Unlimited tier for production.

---

## Error Handling Patterns

### Platform Fallback Strategy
```python
async def post_with_fallback(content: Content, platform: str, client_id: str):
    """Post with automatic fallback to manual queue."""
    try:
        if platform in DIRECT_PLATFORMS:
            return await post_direct(content, platform, client_id)
        elif platform in LATE_PLATFORMS:
            return await post_via_late(content, platform, client_id)
    except (APIError, RateLimitError) as e:
        # Fallback to manual queue
        await queue_manual_post(content, platform, client_id, reason=str(e))
        return PostResult(platform=platform, success=False, method="manual_queue")
```

### Retry Logic
- Use exponential backoff for API failures
- Max 3 retries for transient errors
- Immediate fallback for auth/policy errors
- Log all failures with full context

---

## Security Best Practices

### Credentials
- NEVER hardcode secrets or tokens
- Use environment variables for ALL sensitive data
- Store OAuth tokens encrypted in database
- Rotate API keys periodically

### Data Isolation
- ALWAYS filter queries by `client_id`
- Never expose one client's data to another
- Validate `client_id` on every request
- Use database-level isolation where possible

### Webhook Security
- Verify webhook signatures for each platform
- Validate incoming data structure
- Rate limit webhook endpoints
- Log suspicious activity

### Required Environment Variables
```bash
# AI & APIs
ANTHROPIC_API_KEY=                  # Claude API key
OPENAI_API_KEY=                     # OpenAI embeddings
LATE_API_KEY=                       # Late API authentication

# Meta/Instagram
INSTAGRAM_ACCESS_TOKEN=             # Page Access Token
INSTAGRAM_BUSINESS_ACCOUNT_ID=      # Your IG Business ID
META_APP_ID=                        # Facebook App ID
META_APP_SECRET=                    # Facebook App Secret
VERIFY_TOKEN=                       # Webhook verification token

# Database & Storage (Production)
DATABASE_URL=                       # PostgreSQL connection string
REDIS_URL=                          # Redis connection string
QDRANT_URL=                         # Qdrant Cloud URL (or use local)
QDRANT_API_KEY=                     # Qdrant Cloud API key

# Optional
YOUTUBE_API_KEY=                    # YouTube Data API key
AWS_ACCESS_KEY_ID=                  # For S3 storage
AWS_SECRET_ACCESS_KEY=              # For S3 storage
```

### Production Deployment
Set these environment variables in your cloud provider's dashboard (Railway, Render, etc.) - never commit them to git.

---

## Testing Guidelines

### Test Categories
- **Unit tests:** Individual agent functions, RAG retrieval, rate limiting
- **Integration tests:** Agent-to-agent communication, platform APIs, Late API
- **End-to-end tests:** Complete workflows (comment → response)
- **Load tests:** High volume, rate limiting under pressure

### Testing Patterns
```python
import pytest
from unittest.mock import AsyncMock, patch

@pytest.mark.asyncio
async def test_engagement_response_with_voice():
    """Test that responses use client's voice profile."""
    agent = EngagementAgent(client_id="test_client")
    
    with patch.object(agent, 'get_client_voice_profile') as mock_voice:
        mock_voice.return_value = {"detected_tone": "friendly"}
        
        response = await agent.generate_response(
            message="What are your hours?",
            situation_type="question"
        )
        
        assert response is not None
        mock_voice.assert_called_once()
```

### Test Coverage
- Aim for >80% code coverage
- Test both success and error cases
- Test platform routing logic (direct vs Late vs manual)
- Test voice profile extraction
- Test CSV normalization pipeline
- Test document processing

---

## Performance Optimization

### Caching Strategy
- Cache voice profiles (update on sample changes)
- Cache RAG embeddings
- Cache rate limit counters in Redis
- Use connection pooling for databases

### Async Best Practices
- Use `asyncio.gather()` for parallel operations
- Don't block event loop with sync operations
- Use background tasks for long-running processes
- Implement proper connection cleanup

### Rate Limiting
- Track per-platform, per-client limits
- ✅ **IMPLEMENTED:** Randomize timing to appear human (0-120 second delays before replying to comments)
- ✅ **IMPLEMENTED:** Prevent infinite loops by ignoring comments from business account itself
- Implement cooldown periods
- Handle rate limit errors gracefully

---

## Dependencies

### Core Framework
- FastAPI - Web framework and API endpoints
- Uvicorn - ASGI server
- Pydantic - Data validation

### Database & Storage
- SQLAlchemy - ORM
- asyncpg - Async PostgreSQL driver
- Redis - Caching and rate limiting
- Pinecone/Qdrant - Vector database

### AI & Processing
- anthropic - Claude API client
- httpx - Async HTTP client
- pdfplumber - PDF text extraction
- python-docx - DOCX processing

### Task Queue
- Celery - Background task processing
- Redis - Message broker

### Add all dependencies to requirements.txt
All Python dependencies (including new ones like `qdrant-client`, `fastapi`, `uvicorn`, and `anthropic`) must be added to `requirements.txt`. Contributors should run `pip install -r requirements.txt` after pulling changes or when new dependencies are introduced.

---

## Quick Reference

### Platform Status Enum
```python
from enum import Enum

class PlatformStatus(Enum):
    FULLY_AUTOMATED = "fully_automated"
    VIA_THIRD_PARTY = "via_third_party"
    DEGRADED = "degraded"
    MANUAL_ONLY = "manual_only"
    OFFLINE = "offline"
```

### Content Workflow States
```python
CONTENT_STATES = [
    "ideation",    # Topic approved, not created
    "draft",       # Created, needs review
    "scheduled",   # Approved and scheduled
    "published",   # Live on platforms
    "completed",   # Campaign finished
    "manual_queue", # Awaiting human posting
    "failed"       # Needs retry or intervention
]
```

### Voice Status Levels
```python
VOICE_STATUS = {
    "inactive": "0-4 samples",
    "basic": "5-9 samples",
    "good": "10-19 samples",
    "excellent": "20+ samples"
}
```

---

## Implementation Priority

### Foundation Complete (✅ Completed)
1. ✅ RAG Knowledge System with Qdrant
2. ✅ AI Engagement Agent (Claude-powered)
3. ✅ **Style Injection System** - AI mimics your writing tone from sample files
4. ✅ Instagram Comment replies
5. ✅ Instagram DM replies
6. ✅ Story Mention handling
7. ✅ Automated document ingestion (PDF, DOCX, TXT)
8. ✅ Idempotency (duplicate prevention)
9. ✅ Human-like reply delays

### Core Agent Development (🚧 Current Focus)
1. 🚧 Content Creation Agent - Multi-format content generation
2. 🚧 Voice Matching System - Complete client-specific customization
3. 📋 Marketing Intelligence Agent - Strategy and planning
4. 📋 Growth Agent - Audience building and optimization
5. 📋 Posting Agent - Multi-platform distribution with routing
6. 📋 Email Marketing Agent - Campaign automation
7. 📋 Content Calendar Agent - Scheduling and coordination
8. 📋 Analytics & Reporting Agent - Performance insights
9. 📋 Orchestration Layer - Agent coordination and workflows

### Client Dashboard Development (📋 Next Phase)
1. Authentication and user management system
2. Client onboarding and setup workflows
3. Voice sample upload and management interface
4. Document upload and knowledge base management
5. Deep research query and approval interface
6. Content creation and approval workflows
7. Analytics and reporting dashboards
8. Multi-client isolation and data management
9. Platform connection and configuration management
10. Advanced settings and customization interfaces

### Integration & Testing (📋 Final Phase)
1. Agent-to-agent communication protocols
2. End-to-end workflow testing
3. Multi-client isolation validation
4. Performance and load testing
5. Security audit and compliance
6. Complete system integration testing

### Production Deployment (📋 Only After Complete Build)
1. Infrastructure setup and configuration
2. Monitoring and alerting systems
3. Deployment automation
4. Beta testing with select clients
5. Go-live execution

### Agent Development Order (Complete Each Fully):
1. **Core business logic and algorithms**
2. **Database models and data persistence**
3. **API endpoints and external integrations**
4. **Background tasks and async processing**
5. **Inter-agent communication protocols**
6. **Error handling and fallback systems**
7. **Comprehensive testing suite**
8. **Performance optimization**
9. **Documentation and code comments**
10. **Integration with dashboard interfaces**
