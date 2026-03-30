#!/usr/bin/env python3
"""
Script to create comprehensive Alita AI developer documentation in Confluence.
Uses Confluence REST API to post a single comprehensive page with all technical details.
"""

import os
import json
import requests
from dotenv import load_dotenv

load_dotenv()

# Confluence API credentials from .env
CONFLUENCE_BASE_URL = os.getenv("CONFLUENCE_BASE_URL")
CONFLUENCE_EMAIL = os.getenv("CONFLUENCE_EMAIL")
CONFLUENCE_API_TOKEN = os.getenv("CONFLUENCE_API_TOKEN")
CONFLUENCE_SPACE_KEY = os.getenv("CONFLUENCE_SPACE_KEY")
CONFLUENCE_PARENT_PAGE_ID = os.getenv("CONFLUENCE_PARENT_PAGE_ID")

# Confluence API endpoint
API_URL = f"{CONFLUENCE_BASE_URL}/rest/api/content"

# Page title
PAGE_TITLE = "Alita AI — Developer Reference"

# Build Confluence Storage Format (AKA markup) for the page
def build_page_content():
    """Build the complete Alita developer reference page in Confluence Storage Format"""
    
    content = """<h1>Alita AI — Developer Reference</h1>

<p><strong>Last Updated:</strong> March 1, 2026 | <strong>Status:</strong> Production-Ready | <strong>Deployment:</strong> Railway</p>

<hr />

<h2>📋 Table of Contents</h2>
<ol>
  <li><a href="#overview">Executive Summary</a></li>
  <li><a href="#tech-stack">Tech Stack</a></li>
  <li><a href="#system-reqs">System Requirements</a></li>
  <li><a href="#database">Database Schema</a></li>
  <li><a href="#architecture">Architecture Overview</a></li>
  <li><a href="#agents">AI Agents Reference</a></li>
  <li><a href="#api-routes">API Routes Overview</a></li>
  <li><a href="#setup">Setup &amp; Deployment</a></li>
  <li><a href="#troubleshooting">Troubleshooting</a></li>
  <li><a href="#references">Key Files &amp; References</a></li>
  <li><a href="#security">Configuration &amp; Security</a></li>
</ol>

<hr />

<h2 id="overview">📊 Executive Summary</h2>

<p><strong>Alita AI</strong> is a production-ready, multi-client SaaS platform for complete social media and marketing automation. It orchestrates 15 specialized AI agents across 8+ social media platforms with niche-specific content generation, posting, engagement tracking, and analytics reporting.</p>

<h3>Key Capabilities</h3>
<ul>
  <li><strong>🤖 AI Content Engine:</strong> 86 prompt templates across 8 platforms × 3 marketing goals</li>
  <li><strong>📹 Faceless Video Generation:</strong> 15 content categories with multi-tier quality (Basic → Ultra)</li>
  <li><strong>🖼️ Multi-Model Image Generation:</strong> Flux, Midjourney, DALL-E, Ideogram, GPT Image</li>
  <li><strong>📊 Marketing Intelligence:</strong> Competitive research, trend analysis, strategy generation</li>
  <li><strong>💬 Engagement Automation:</strong> DM/comment responses with human-like timing and human escalation</li>
  <li><strong>📧 Email Marketing:</strong> Outbound campaigns via Resend + inbound Gmail support inbox management</li>
  <li><strong>📱 Multi-Platform Posting:</strong> 8+ platforms with 3-tier routing (Direct API → Late API → Manual Queue)</li>
  <li><strong>🔍 RAG System:</strong> Qdrant vector DB for client-specific knowledge bases and semantic search</li>
  <li><strong>👤 Voice Matching:</strong> AI learns and replicates each client's unique writing style</li>
  <li><strong>💳 Billing &amp; Subscriptions:</strong> Stripe integration with 4 tiers (Free/Starter/Growth/Pro) + 10 premium add-ons</li>
</ul>

<h3>Quick Stats</h3>
<table>
  <tbody>
    <tr>
      <td><strong>AI Agents</strong></td>
      <td>15 specialized modules</td>
    </tr>
    <tr>
      <td><strong>API Routes</strong></td>
      <td>33 FastAPI endpoint modules</td>
    </tr>
    <tr>
      <td><strong>Social Platforms</strong></td>
      <td>10+ integrated (Direct API / Late API / Manual)</td>
    </tr>
    <tr>
      <td><strong>External APIs</strong></td>
      <td>25+ integrated services (Claude, OpenAI, ElevenLabs, Stripe, etc.)</td>
    </tr>
    <tr>
      <td><strong>Billing Tiers</strong></td>
      <td>4 subscription plans + 10 add-on products</td>
    </tr>
    <tr>
      <td><strong>Monthly Users Supported</strong></td>
      <td>10-50+ simultaneous clients</td>
    </tr>
    <tr>
      <td><strong>Production Status</strong></td>
      <td>Live on Railway with Stripe LIVE keys</td>
    </tr>
  </tbody>
</table>

<p><strong>Deployment URL:</strong> <a href="https://web-production-00e4.up.railway.app">https://web-production-00e4.up.railway.app</a></p>

<hr />

<h2 id="tech-stack">🛠️ Tech Stack</h2>

<h3>Core Languages &amp; Framework</h3>
<ul>
  <li><strong>Python 3.11+</strong> (primary language)</li>
  <li><strong>FastAPI</strong> + <strong>Uvicorn</strong> (async web framework)</li>
  <li><strong>SQLAlchemy 2.0</strong> (ORM)</li>
</ul>

<h3>Databases</h3>
<table>
  <tbody>
    <tr>
      <td><strong>Database</strong></td>
      <td><strong>Usage</strong></td>
      <td><strong>Environment</strong></td>
    </tr>
    <tr>
      <td>SQLite</td>
      <td>User Management, Client Profiles, OAuth Tokens, Billing</td>
      <td>Local Development</td>
    </tr>
    <tr>
      <td>PostgreSQL</td>
      <td>Same as SQLite</td>
      <td>Production (Railway)</td>
    </tr>
    <tr>
      <td>Qdrant</td>
      <td>Vector embeddings for client knowledge base semantic search</td>
      <td>Both (Remote)</td>
    </tr>
  </tbody>
</table>

<h3>AI/LLM APIs</h3>
<table>
  <tbody>
    <tr>
      <td><strong>Service</strong></td>
      <td><strong>Purpose</strong></td>
      <td><strong>Pricing</strong></td>
    </tr>
    <tr>
      <td>Anthropic Claude</td>
      <td>Primary AI (content gen, analytics, voice matching, reasoning)</td>
      <td>~$0.003-0.015 per 1K tokens</td>
    </tr>
    <tr>
      <td>Claude Haiku</td>
      <td>Fast &amp; cheap responses for simple tasks</td>
      <td>$0.25 per MTok (default model)</td>
    </tr>
    <tr>
      <td>Claude Sonnet</td>
      <td>High-quality reasoning for complex tasks</td>
      <td>$3 per MTok</td>
    </tr>
    <tr>
      <td>OpenAI GPT-4</td>
      <td>Fallback image generation &amp; advanced reasoning</td>
      <td>~$0.010-0.020 per image</td>
    </tr>
    <tr>
      <td>Google Gemini</td>
      <td>Deep research &amp; competitive analysis</td>
      <td>Part of API quota</td>
    </tr>
  </tbody>
</table>

<h3>Content Generation Services</h3>
<table>
  <tbody>
    <tr>
      <td><strong>Service</strong></td>
      <td><strong>Capability</strong></td>
      <td><strong>Tier</strong></td>
      <td><strong>Cost</strong></td>
    </tr>
    <tr>
      <td>ElevenLabs</td>
      <td>AI voiceover (video narration, voice synthesis)</td>
      <td>3</td>
      <td>$5/mo (30 min voice)</td>
    </tr>
    <tr>
      <td>fal.ai (Kling/Wan)</td>
      <td>AI video animation &amp; generation</td>
      <td>3</td>
      <td>Per-usage pricing</td>
    </tr>
    <tr>
      <td>Ideogram</td>
      <td>Text-accurate image generation (flyers, quotes, designs)</td>
      <td>2</td>
      <td>API-based</td>
    </tr>
    <tr>
      <td>GoAPI (Midjourney)</td>
      <td>High-quality artistic image generation</td>
      <td>2</td>
      <td>Per-usage pricing</td>
    </tr>
    <tr>
      <td>Pexels</td>
      <td>Free stock video clips &amp; images</td>
      <td>1</td>
      <td>Free</td>
    </tr>
    <tr>
      <td>Pixabay</td>
      <td>Free stock video/images backup source</td>
      <td>1</td>
      <td>Free</td>
    </tr>
    <tr>
      <td>ImgBB</td>
      <td>Public image hosting and CDN delivery</td>
      <td>1</td>
      <td>Free tier available</td>
    </tr>
  </tbody>
</table>

<h3>Marketing Intelligence &amp; Research</h3>
<table>
  <tbody>
    <tr>
      <td><strong>Service</strong></td>
      <td><strong>Purpose</strong></td>
      <td><strong>Tier</strong></td>
    </tr>
    <tr>
      <td>Tavily API</td>
      <td>Competitive research &amp; web scraping</td>
      <td>2</td>
    </tr>
    <tr>
      <td>NewsAPI</td>
      <td>News &amp; trend intelligence</td>
      <td>2</td>
    </tr>
    <tr>
      <td>YouTube Data API</td>
      <td>Trending video analysis &amp; research</td>
      <td>2</td>
    </tr>
  </tbody>
</table>

<h3>Social Media &amp; Communication Integrations</h3>
<table>
  <tbody>
    <tr>
      <td><strong>Platform</strong></td>
      <td><strong>Integration Type</strong></td>
      <td><strong>Features</strong></td>
    </tr>
    <tr>
      <td>Meta (Facebook/Instagram)</td>
      <td>Direct Graph API</td>
      <td>Posts, Stories, Reels, Comments, DMs, Analytics</td>
    </tr>
    <tr>
      <td>YouTube</td>
      <td>Direct Data API</td>
      <td>Posts, Shorts, Comments, Analytics</td>
    </tr>
    <tr>
      <td>TikTok</td>
      <td>Late API (proxy)</td>
      <td>Posts, Videos, Comments, Analytics</td>
    </tr>
    <tr>
      <td>LinkedIn</td>
      <td>Late API (proxy)</td>
      <td>Posts, Videos, Articles, Comments</td>
    </tr>
    <tr>
      <td>Twitter/X</td>
      <td>Late API (proxy)</td>
      <td>Tweets, Threads, Replies</td>
    </tr>
    <tr>
      <td>Threads</td>
      <td>Meta Graph + Late API</td>
      <td>Posts, Replies, Analytics</td>
    </tr>
    <tr>
      <td>Email (Gmail)</td>
      <td>Direct OAuth 2.0</td>
      <td>Read/Send from client inbox, thread management</td>
    </tr>
    <tr>
      <td>WhatsApp</td>
      <td>Business API</td>
      <td>Messages, Media, Templates</td>
    </tr>
    <tr>
      <td>Reddit, Pinterest, Bluesky</td>
      <td>Late API (proxy)</td>
      <td>Posts, Comments, Analytics</td>
    </tr>
  </tbody>
</table>

<h3>Authentication &amp; Security</h3>
<ul>
  <li><strong>JWT tokens</strong> (python-jose) for session management and API authentication</li>
  <li><strong>bcrypt</strong> password hashing with per-user salt</li>
  <li><strong>TOTP</strong> (Google Authenticator) via pyotp library</li>
  <li><strong>WebAuthn/Passkeys</strong> (FIDO2) via webauthn library</li>
  <li><strong>OAuth 2.0</strong> flows (Google, Facebook, Meta, Twitter, TikTok, YouTube, Gmail)</li>
  <li><strong>Cryptography (Fernet)</strong> for encrypting OAuth tokens at rest</li>
</ul>

<h3>Payments &amp; Billing</h3>
<ul>
  <li><strong>Stripe</strong> (subscriptions, add-ons, webhooks with stripe>=7.0.0)</li>
  <li><strong>4 subscription tiers:</strong> Free, Starter, Growth, Pro</li>
  <li><strong>10 add-on products:</strong> Post Boost, Engagement Boost, Video Boost, AI Animation, Premium Images, Email Campaigns, Growth Strategy, Research Boost, YouTube Add-on, Account Expansion</li>
  <li><strong>Usage tracking:</strong> Monthly counters auto-reset on billing cycle</li>
</ul>

<h3>Additional Services</h3>
<table>
  <tbody>
    <tr>
      <td><strong>Service</strong></td>
      <td><strong>Purpose</strong></td>
      <td><strong>Tier</strong></td>
    </tr>
    <tr>
      <td>Resend</td>
      <td>Outbound email campaigns &amp; transactional emails</td>
      <td>2</td>
    </tr>
    <tr>
      <td>Twilio</td>
      <td>SMS OTP verification &amp; alerts</td>
      <td>3</td>
    </tr>
    <tr>
      <td>Railway</td>
      <td>PaaS deployment with Procfile support</td>
      <td>Production</td>
    </tr>
    <tr>
      <td>GitHub Actions</td>
      <td>CI/CD (linting, auto-deploy, health checks)</td>
      <td>Production</td>
    </tr>
  </tbody>
</table>

<hr />

<h2 id="system-reqs">⚙️ System Requirements</h2>

<h3>Minimum System Requirements</h3>
<table>
  <tbody>
    <tr>
      <td><strong>Component</strong></td>
      <td><strong>Requirement</strong></td>
    </tr>
    <tr>
      <td>Python</td>
      <td>3.11 or higher</td>
    </tr>
    <tr>
      <td>Package Manager</td>
      <td>pip (comes with Python)</td>
    </tr>
    <tr>
      <td>Disk Space</td>
      <td>~250 MB (excluding venv)</td>
    </tr>
    <tr>
      <td>RAM</td>
      <td>512 MB minimum (1+ GB recommended)</td>
    </tr>
    <tr>
      <td>OS</td>
      <td>Windows, macOS, Linux</td>
    </tr>
  </tbody>
</table>

<h3>Essential API Keys (Tier 1 - Required for basic operation)</h3>
<table>
  <tbody>
    <tr>
      <td><strong>Service</strong></td>
      <td><strong>Environment Variable</strong></td>
      <td><strong>Purpose</strong></td>
    </tr>
    <tr>
      <td>Anthropic Claude</td>
      <td>ANTHROPIC_API_KEY</td>
      <td>Primary AI engine for content generation &amp; reasoning</td>
    </tr>
    <tr>
      <td>OpenAI GPT</td>
      <td>OPENAI_API_KEY</td>
      <td>Fallback image generation &amp; advanced tasks</td>
    </tr>
    <tr>
      <td>Database</td>
      <td>DATABASE_URL</td>
      <td>SQLite (dev) or PostgreSQL (production)</td>
    </tr>
  </tbody>
</table>

<h3>Recommended API Keys (Tiers 2-4)</h3>
<table>
  <tbody>
    <tr>
      <td><strong>Category</strong></td>
      <td><strong>Services</strong></td>
      <td><strong>Priority</strong></td>
    </tr>
    <tr>
      <td>Meta Integration</td>
      <td>META_APP_ID, META_APP_SECRET, FACEBOOK_PAGE_ACCESS_TOKEN, INSTAGRAM_ACCESS_TOKEN, INSTAGRAM_BUSINESS_ACCOUNT_ID</td>
      <td>High (Facebook/Instagram posting)</td>
    </tr>
    <tr>
      <td>Multi-Platform Posting</td>
      <td>LATE_API_KEY + LATE_PROFILE_* (TikTok, LinkedIn, Twitter, YouTube, Threads)</td>
      <td>High (broadest platform reach)</td>
    </tr>
    <tr>
      <td>Email Sending</td>
      <td>RESEND_API_KEY, EMAIL_FROM_ADDRESS</td>
      <td>High (email campaigns)</td>
    </tr>
    <tr>
      <td>Gmail Integration</td>
      <td>GMAIL_CLIENT_ID, GMAIL_CLIENT_SECRET, GMAIL_REDIRECT_URI</td>
      <td>Medium (email support inbox)</td>
    </tr>
    <tr>
      <td>Payments</td>
      <td>STRIPE_SECRET_KEY, STRIPE_PUBLISHABLE_KEY, STRIPE_WEBHOOK_SECRET</td>
      <td>High (billing &amp; subscriptions)</td>
    </tr>
    <tr>
      <td>Marketing Intelligence</td>
      <td>TAVILY_API_KEY, NEWSAPI_KEY, YOUTUBE_API_KEY, GEMINI_API_KEY</td>
      <td>Medium (research &amp; strategy)</td>
    </tr>
    <tr>
      <td>Media Generation</td>
      <td>ELEVENLABS_API_KEY, FAL_API_KEY, IDEOGRAM_API_KEY, GOAPI_API_KEY, PEXELS_API_KEY, PIXABAY_API_KEY</td>
      <td>Medium (video, image, voiceover)</td>
    </tr>
    <tr>
      <td>SMS Notifications</td>
      <td>TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_PHONE_NUMBER</td>
      <td>Low (OTP, alerts - currently on hold)</td>
    </tr>
  </tbody>
</table>

<h3>Estimated Monthly API Costs</h3>
<table>
  <tbody>
    <tr>
      <td><strong>Tier</strong></td>
      <td><strong>Monthly Cost</strong></td>
      <td><strong>Services Included</strong></td>
    </tr>
    <tr>
      <td>Minimal (AI only)</td>
      <td>~$21/mo</td>
      <td>Claude API only (limited usage)</td>
    </tr>
    <tr>
      <td>Standard</td>
      <td>~$60-100/mo</td>
      <td>Claude, Late API, ElevenLabs, Resend, Tavily, NewsAPI</td>
    </tr>
    <tr>
      <td>Full Suite</td>
      <td>~$150-250/mo</td>
      <td>All services including Midjourney, fal.ai, Gemini, Twilio</td>
    </tr>
  </tbody>
</table>

<hr />

<h2 id="database">🗄️ Database Schema</h2>

<h3>Core Tables (SQLAlchemy Models)</h3>

<h4>Users Table</h4>
<table>
  <tbody>
    <tr>
      <td><strong>Field</strong></td>
      <td><strong>Type</strong></td>
      <td><strong>Notes</strong></td>
    </tr>
    <tr>
      <td>id</td>
      <td>UUID (Primary Key)</td>
      <td>Unique user identifier</td>
    </tr>
    <tr>
      <td>email</td>
      <td>String (Unique, Indexed)</td>
      <td>Login email address</td>
    </tr>
    <tr>
      <td>password_hash</td>
      <td>String</td>
      <td>bcrypt hashed password with salt</td>
    </tr>
    <tr>
      <td>full_name</td>
      <td>String</td>
      <td>Display name</td>
    </tr>
    <tr>
      <td>is_admin, is_active</td>
      <td>Boolean</td>
      <td>Role &amp; account status</td>
    </tr>
    <tr>
      <td>email_verified</td>
      <td>Boolean</td>
      <td>Email verification status</td>
    </tr>
    <tr>
      <td>mfa_enabled, mfa_method</td>
      <td>Boolean, Enum</td>
      <td>MFA type: totp, email, sms, webauthn</td>
    </tr>
    <tr>
      <td>mfa_secret, phone_number</td>
      <td>String</td>
      <td>MFA credentials (encrypted)</td>
    </tr>
    <tr>
      <td>oauth_provider, oauth_provider_id</td>
      <td>String</td>
      <td>Social login (Google, Facebook)</td>
    </tr>
    <tr>
      <td>created_at, last_login</td>
      <td>DateTime</td>
      <td>Audit timestamps</td>
    </tr>
  </tbody>
</table>

<h4>ClientProfile Table ⭐ (Main Business Entity)</h4>
<table>
  <tbody>
    <tr>
      <td><strong>Field</strong></td>
      <td><strong>Type</strong></td>
      <td><strong>Notes</strong></td>
    </tr>
    <tr>
      <td>id</td>
      <td>UUID (Primary Key)</td>
      <td>Client unique identifier</td>
    </tr>
    <tr>
      <td>user_id</td>
      <td>UUID (FK to Users, Unique)</td>
      <td>Account owner relationship</td>
    </tr>
    <tr>
      <td>client_id</td>
      <td>String (Unique, Indexed)</td>
      <td>Human-readable client identifier</td>
    </tr>
    <tr>
      <td>business_name, niche, website_url</td>
      <td>String</td>
      <td>Client business information</td>
    </tr>
    <tr>
      <td>onboarding_method</td>
      <td>Enum</td>
      <td>website | manual | files</td>
    </tr>
    <tr>
      <td>onboarding_status</td>
      <td>Enum</td>
      <td>pending → scraping → research_queue → research_run → complete</td>
    </tr>
    <tr>
      <td>rag_ready</td>
      <td>Boolean</td>
      <td>Knowledge base ingestion complete</td>
    </tr>
    <tr>
      <td>plan_tier</td>
      <td>Enum</td>
      <td>free | starter | growth | pro</td>
    </tr>
    <tr>
      <td>plan_status</td>
      <td>Enum</td>
      <td>active | trialing | past_due | canceled | paused</td>
    </tr>
    <tr>
      <td>stripe_customer_id, stripe_subscription_id</td>
      <td>String</td>
      <td>Stripe integration IDs (encrypted)</td>
    </tr>
    <tr>
      <td>trial_ends_at</td>
      <td>DateTime</td>
      <td>Trial expiration (nullable)</td>
    </tr>
    <tr>
      <td>usage_posts_created, usage_images_created, usage_videos_created</td>
      <td>Integer</td>
      <td>Monthly usage counters (reset each billing cycle)</td>
    </tr>
    <tr>
      <td>usage_replies_sent, usage_campaigns_sent, usage_research_run</td>
      <td>Integer</td>
      <td>Additional monthly counters</td>
    </tr>
    <tr>
      <td>usage_reset_at</td>
      <td>DateTime</td>
      <td>Next billing cycle / counter reset date</td>
    </tr>
    <tr>
      <td>meta_user_id, meta_ig_account_id, meta_ig_username</td>
      <td>String</td>
      <td>Meta/Instagram OAuth data</td>
    </tr>
    <tr>
      <td>meta_facebook_page_id, meta_connected_at</td>
      <td>String, DateTime</td>
      <td>Facebook page integration &amp; timestamp</td>
    </tr>
    <tr>
      <td>created_at, updated_at</td>
      <td>DateTime</td>
      <td>Audit timestamps</td>
    </tr>
  </tbody>
</table>

<h4>Supporting Tables</h4>
<ul>
  <li><strong>MetaOAuthToken:</strong> Stores encrypted Meta OAuth tokens (refresh &amp; access tokens with expiry)</li>
  <li><strong>GmailOAuthToken:</strong> Stores encrypted Gmail OAuth tokens for email support inbox access</li>
  <li><strong>DeepResearchRequest:</strong> Tracks research pipeline status (pending → approved → running → complete)</li>
  <li><strong>PasswordResetToken:</strong> Temporary reset tokens with expiry for password recovery</li>
</ul>

<hr />

<h2 id="architecture">🏗️ Architecture Overview</h2>

<h3>Application Architecture</h3>
<pre><code>FastAPI Application (web_app.py)
│
├─ APIRouter 1: Authentication &amp; Auth (auth_routes.py)
├─ APIRouter 2: Admin Dashboard (admin_routes.py)
├─ APIRouter 3: Client Onboarding (onboarding_routes.py)
├─ APIRouter 4: Content Creation (post_creation_routes.py)
├─ APIRouter 5: Calendar Management (calendar_routes.py)
├─ APIRouter 6: Engagement (comment_routes.py, inbox_routes.py)
├─ APIRouter 7: Analytics (analytics_routes.py)
├─ APIRouter 8: Intelligence &amp; Growth (intelligence_routes.py, growth_routes.py)
├─ APIRouter 9: Email Campaigns (email_routes.py)
├─ APIRouter 10: Billing (billing_routes.py)
├─ APIRouter 11: Platform Connections (client_connections_routes.py)
├─ APIRouter 12: Platform-Specific (twitter_client.py, tiktok_client.py, etc.)
├─ APIRouter 13: Webhooks (webhook_receiver.py, late_webhooks.py)
└─ APIRouter 14: AI Assistant (alita_assistant_routes.py)

Database Layer (SQLAlchemy)
├─ SQLite (development: ./automation.db)
└─ PostgreSQL (production: Railway)

Message Brokers &amp; Real-Time
├─ APScheduler (Background task scheduling)
└─ WebSocket support (future: real-time updates)

Vector Database
└─ Qdrant (Client knowledge base semantic search via RAG)
</code></pre>

<h3>Data Flow Diagram</h3>
<pre><code>User Request (Dashboard/API)
    ↓
FastAPI Route Handler
    ↓
Authentication (JWT validation)
    ↓
Client Profile Validation (rate limits, usage allowances)
    ↓
AI Agent Pipeline
    ├─ Fetch context (RAG from Qdrant)
    ├─ Call LLM (Claude/GPT)
    ├─ Apply guardrails (abuse filtering)
    └─ Return result
    ↓
Database Write (SQLAlchemy ORM)
    ↓
Post to Social Platform(s)
    ├─ Try Direct API (Meta, YouTube)
    ├─ Fallback: Late API (TikTok, LinkedIn, X, Threads, etc.)
    └─ Fallback: Manual Queue (platform down)
    ↓
Response to User
</code></pre>

<h3>3-Tier Platform Posting Routing</h3>
<table>
  <tbody>
    <tr>
      <td><strong>Tier</strong></td>
      <td><strong>Services</strong></td>
      <td><strong>Cost</strong></td>
      <td><strong>Latency</strong></td>
    </tr>
    <tr>
      <td>1. Direct API</td>
      <td>Meta (FB/IG), YouTube, WordPress</td>
      <td>Free (API quota)</td>
      <td>~500ms</td>
    </tr>
    <tr>
      <td>2. Late API Proxy</td>
      <td>TikTok, LinkedIn, Twitter/X, Threads, Reddit, Pinterest, Bluesky</td>
      <td>~$33/mo for 10 platforms</td>
      <td>~1-2s</td>
    </tr>
    <tr>
      <td>3. Manual Queue</td>
      <td>Any platform during API outage</td>
      <td>Free (fallback)</td>
      <td>Manual review</td>
    </tr>
  </tbody>
</table>

<h3>RAG Knowledge Base Integration</h3>
<ul>
  <li><strong>Qdrant Vector DB:</strong> Stores embeddings of client documents (websites, files, past content)</li>
  <li><strong>Per-Client RAGs:</strong> 15 agent-specific knowledge bases in <code>Agent RAGs/</code> directories</li>
  <li><strong>Semantic Search:</strong> AI agents retrieve relevant context before generating content</li>
  <li><strong>Ingestion Pipeline:</strong> <code>knowledge_base.py</code> + <code>ingest.py</code> handle document upload &amp; indexing</li>
</ul>

<hr />

<h2 id="agents">🤖 AI Agents Reference</h2>

<table>
  <tbody>
    <tr>
      <td><strong>#</strong></td>
      <td><strong>Agent</strong></td>
      <td><strong>File</strong></td>
      <td><strong>Purpose</strong></td>
      <td><strong>Output Type</strong></td>
    </tr>
    <tr>
      <td>1</td>
      <td>Content Creation</td>
      <td>content_agent.py</td>
      <td>86 templates for platform-optimized content (posts, captions, hashtags, CTAs)</td>
      <td>JSON posts with metadata</td>
    </tr>
    <tr>
      <td>2</td>
      <td>Posting</td>
      <td>posting_agent.py</td>
      <td>3-tier routing (Direct → Late → Manual) content to correct platform</td>
      <td>PostingResult with success/failure tracking</td>
    </tr>
    <tr>
      <td>3</td>
      <td>Engagement</td>
      <td>engagement_agent.py</td>
      <td>Auto DM/comment responses with human-like timing &amp; human escalation</td>
      <td>JSON replies with confidence scores</td>
    </tr>
    <tr>
      <td>4</td>
      <td>Growth</td>
      <td>growth_agent.py</td>
      <td>Audience targeting, follower discovery, growth campaigns</td>
      <td>GrowthReport + engagement actions</td>
    </tr>
    <tr>
      <td>5</td>
      <td>Analytics</td>
      <td>analytics_agent.py</td>
      <td>Performance tracking, insights, ROI reports, trend analysis</td>
      <td>CrossPlatformReport with metrics</td>
    </tr>
    <tr>
      <td>6</td>
      <td>Calendar</td>
      <td>calendar_agent.py</td>
      <td>RAG-powered optimal posting schedule &amp; timing recommendations</td>
      <td>JSON schedule with times</td>
    </tr>
    <tr>
      <td>7</td>
      <td>Marketing Intelligence</td>
      <td>marketing_intelligence_agent.py</td>
      <td>Strategy generation, trend analysis, competitive research</td>
      <td>ContentStrategy + ideas</td>
    </tr>
    <tr>
      <td>8</td>
      <td>Email Marketing</td>
      <td>email_marketing_agent.py</td>
      <td>Outbound campaign automation via Resend with A/B testing</td>
      <td>Campaign JSON + optimization</td>
    </tr>
    <tr>
      <td>9</td>
      <td>Email Support</td>
      <td>email_support_agent.py</td>
      <td>Inbound Gmail inbox auto-response &amp; triage with escalation</td>
      <td>Auto-reply JSON + sentiment</td>
    </tr>
    <tr>
      <td>10</td>
      <td>Faceless Video Generator</td>
      <td>faceless_generator.py</td>
      <td>AI video pipeline (script → voice → footage → assembly)</td>
      <td>Video file + metadata</td>
    </tr>
    <tr>
      <td>11</td>
      <td>Image Generator</td>
      <td>image_generator.py</td>
      <td>Multi-model image creation (Flux, Midjourney, DALL-E, Ideogram)</td>
      <td>Image URL (ImgBB hosted)</td>
    </tr>
    <tr>
      <td>12</td>
      <td>RAG System</td>
      <td>rag_system.py</td>
      <td>Qdrant vector DB semantic search &amp; context retrieval</td>
      <td>Retrieved chunks + scores</td>
    </tr>
    <tr>
      <td>13</td>
      <td>Voice Matching</td>
      <td>voice_matching_system.py</td>
      <td>Client style/voice learning &amp; replication for brand consistency</td>
      <td>Style DNA profile</td>
    </tr>
    <tr>
      <td>14</td>
      <td>Alita Assistant</td>
      <td>alita_assistant.py</td>
      <td>Conversational AI for dashboard interactions &amp; support</td>
      <td>Chat responses</td>
    </tr>
    <tr>
      <td>15</td>
      <td>PPC Agent (Bonus)</td>
      <td>ppc_agent.py</td>
      <td>Ad campaign research, planning, copy generation, execution</td>
      <td>Campaign JSON + ad copy</td>
    </tr>
  </tbody>
</table>

<h3>Utility Modules</h3>
<ul>
  <li><strong>agent_scheduler.py:</strong> APScheduler-based task automation (daily posts, weekly analytics, growth campaigns)</li>
  <li><strong>client_profile_manager.py:</strong> Client CRUD operations &amp; onboarding state management</li>
  <li><strong>content_calendar_orchestrator.py:</strong> Coordinates Calendar + Content + Posting agents</li>
  <li><strong>conversation_categorizer.py:</strong> Auto-tags DMs/comments (Sale/Complaint/Question/etc.)</li>
  <li><strong>knowledge_base.py:</strong> Document ingestion CLI for knowledge base management</li>
  <li><strong>faceless_rag.py:</strong> Video-specific RAG knowledge &amp; prompts</li>
  <li><strong>faceless_style_loader.py:</strong> 15 video style templates (motivational, educational, horror, Reddit, etc.)</li>
  <li><strong>growth_hacking_agent.py:</strong> Advanced growth automation &amp; scaling strategies</li>
</ul>

<hr />

<h2 id="api-routes">📡 API Routes Overview</h2>

<p><strong>Total Routes:</strong> 33 FastAPI modules + 150+ individual endpoints</p>

<h3>Authentication &amp; Account Management</h3>
<table>
  <tbody>
    <tr>
      <td><strong>Endpoint</strong></td>
      <td><strong>Module</strong></td>
      <td><strong>Purpose</strong></td>
    </tr>
    <tr>
      <td>POST /account/login</td>
      <td>auth_routes.py</td>
      <td>Email/password authentication</td>
    </tr>
    <tr>
      <td>POST /account/signup</td>
      <td>auth_routes.py</td>
      <td>Create new account (optional social login Google/Facebook)</td>
    </tr>
    <tr>
      <td>POST /auth/2fa/setup</td>
      <td>auth_routes.py</td>
      <td>Enable TOTP, email, SMS, or passkey MFA</td>
    </tr>
    <tr>
      <td>POST /auth/2fa/verify</td>
      <td>auth_routes.py</td>
      <td>Verify MFA code during login</td>
    </tr>
    <tr>
      <td>POST /auth/password-reset</td>
      <td>auth_routes.py</td>
      <td>Request password reset (email token sent)</td>
    </tr>
    <tr>
      <td>GET /settings/profile</td>
      <td>settings_routes.py</td>
      <td>Retrieve user profile &amp; preferences</td>
    </tr>
    <tr>
      <td>PUT /settings/profile</td>
      <td>settings_routes.py</td>
      <td>Update user profile information</td>
    </tr>
  </tbody>
</table>

<h3>Admin &amp; Billing</h3>
<table>
  <tbody>
    <tr>
      <td><strong>Endpoint</strong></td>
      <td><strong>Module</strong></td>
      <td><strong>Purpose</strong></td>
    </tr>
    <tr>
      <td>GET /admin/dashboard</td>
      <td>admin_routes.py</td>
      <td>Admin overview (user counts, revenue, system health)</td>
    </tr>
    <tr>
      <td>GET /admin/clients</td>
      <td>admin_routes.py</td>
      <td>List all clients with stats &amp; pagination</td>
    </tr>
    <tr>
      <td>GET /admin/clients/{client_id}</td>
      <td>admin_routes.py</td>
      <td>Detailed client profile &amp; usage analytics</td>
    </tr>
    <tr>
      <td>POST /billing/checkout</td>
      <td>billing_routes.py</td>
      <td>Create Stripe checkout session for subscription</td>
    </tr>
    <tr>
      <td>POST /billing/subscribe</td>
      <td>billing_routes.py</td>
      <td>Upgrade/downgrade plan tier</td>
    </tr>
    <tr>
      <td>POST /billing/add-on</td>
      <td>billing_routes.py</td>
      <td>Purchase premium add-on (Post Boost, Video Boost, etc.)</td>
    </tr>
    <tr>
      <td>GET /billing/invoice</td>
      <td>billing_routes.py</td>
      <td>Retrieve invoice history &amp; receipt PDFs</td>
    </tr>
  </tbody>
</table>

<h3>Client Onboarding &amp; Platform Connections</h3>
<table>
  <tbody>
    <tr>
      <td><strong>Endpoint</strong></td>
      <td><strong>Module</strong></td>
      <td><strong>Purpose</strong></td>
    </tr>
    <tr>
      <td>POST /onboarding/start</td>
      <td>onboarding_routes.py</td>
      <td>Begin onboarding wizard (choose method: website/manual/files)</td>
    </tr>
    <tr>
      <td>POST /onboarding/website-scrape</td>
      <td>onboarding_routes.py</td>
      <td>Scrape &amp; ingest client website content</td>
    </tr>
    <tr>
      <td>POST /onboarding/upload-docs</td>
      <td>onboarding_routes.py</td>
      <td>Upload PDFs, DOCs, spreadsheets for knowledge base</td>
    </tr>
    <tr>
      <td>POST /onboarding/manual-input</td>
      <td>onboarding_routes.py</td>
      <td>Manually enter business info &amp; style guidelines</td>
    </tr>
    <tr>
      <td>GET /onboarding/status</td>
      <td>onboarding_routes.py</td>
      <td>Check onboarding pipeline status (pending → complete)</td>
    </tr>
    <tr>
      <td>GET /connect/meta/oauth</td>
      <td>client_connections_routes.py</td>
      <td>Initiate Meta OAuth flow for FB/IG integration</td>
    </tr>
    <tr>
      <td>GET /connect/meta/callback</td>
      <td>client_connections_routes.py</td>
      <td>Receive Meta OAuth callback with token</td>
    </tr>
    <tr>
      <td>GET /connect/gmail/oauth</td>
      <td>settings_routes.py</td>
      <td>Initiate Gmail OAuth for email support inbox</td>
    </tr>
    <tr>
      <td>GET /connect/youtube/oauth</td>
      <td>client_connections_routes.py</td>
      <td>Initiate YouTube Data API OAuth</td>
    </tr>
    <tr>
      <td>GET /connect/late-api/*</td>
      <td>client_connections_routes.py</td>
      <td>Late API connection for TikTok, LinkedIn, X, Threads</td>
    </tr>
  </tbody>
</table>

<h3>Content Creation &amp; Management</h3>
<table>
  <tbody>
    <tr>
      <td><strong>Endpoint</strong></td>
      <td><strong>Module</strong></td>
      <td><strong>Purpose</strong></td>
    </tr>
    <tr>
      <td>POST /posts/generate</td>
      <td>post_creation_routes.py</td>
      <td>AI-generate content for specified platform(s)</td>
    </tr>
    <tr>
      <td>POST /posts/create</td>
      <td>post_creation_routes.py</td>
      <td>Create new post (AI-generated or manual)</td>
    </tr>
    <tr>
      <td>PUT /posts/{post_id}</td>
      <td>post_creation_routes.py</td>
      <td>Edit draft post before publishing</td>
    </tr>
    <tr>
      <td>POST /posts/{post_id}/publish</td>
      <td>post_creation_routes.py</td>
      <td>Publish post to social platform(s)</td>
    </tr>
    <tr>
      <td>GET /posts</td>
      <td>post_creation_routes.py</td>
      <td>Retrieve post history with filters &amp; pagination</td>
    </tr>
    <tr>
      <td>GET /calendar</td>
      <td>calendar_routes.py</td>
      <td>Retrieve content calendar (month/week view)</td>
    </tr>
    <tr>
      <td>POST /calendar/schedule</td>
      <td>calendar_routes.py</td>
      <td>Schedule post for future date/time (with optimal timing AI)</td>
    </tr>
    <tr>
      <td>PUT /calendar/{post_id}</td>
      <td>calendar_routes.py</td>
      <td>Reschedule published/draft post</td>
    </tr>
  </tbody>
</table>

<h3>Engagement &amp; Analytics</h3>
<table>
  <tbody>
    <tr>
      <td><strong>Endpoint</strong></td>
      <td><strong>Module</strong></td>
      <td><strong>Purpose</strong></td>
    </tr>
    <tr>
      <td>GET /comments</td>
      <td>comment_routes.py</td>
      <td>Unified comments across all platforms</td>
    </tr>
    <tr>
      <td>POST /comments/{comment_id}/reply</td>
      <td>comment_routes.py</td>
      <td>AI auto-reply to comment (with human review option)</td>
    </tr>
    <tr>
      <td>GET /inbox</td>
      <td>inbox_routes.py</td>
      <td>Unified DM inbox across platforms (Meta, TikTok, etc.)</td>
    </tr>
    <tr>
      <td>POST /inbox/{message_id}/reply</td>
      <td>inbox_routes.py</td>
      <td>Send AI auto-reply to DM</td>
    </tr>
    <tr>
      <td>GET /analytics/dashboard</td>
      <td>analytics_routes.py</td>
      <td>Performance dashboard (views, likes, comments, followers)</td>
    </tr>
    <tr>
      <td>GET /analytics/post/{post_id}</td>
      <td>analytics_routes.py</td>
      <td>Detailed analytics for single post</td>
    </tr>
    <tr>
      <td>GET /analytics/report</td>
      <td>analytics_routes.py</td>
      <td>Generate PDF report (weekly/monthly/custom date range)</td>
    </tr>
    <tr>
      <td>GET /growth/strategies</td>
      <td>growth_routes.py</td>
      <td>AI-generated growth strategies for client niche</td>
    </tr>
    <tr>
      <td>POST /growth/run-campaign</td>
      <td>growth_routes.py</td>
      <td>Execute engagement campaigns (auto-comments, DMs)</td>
    </tr>
  </tbody>
</table>

<h3>AI Intelligence &amp; Email</h3>
<table>
  <tbody>
    <tr>
      <td><strong>Endpoint</strong></td>
      <td><strong>Module</strong></td>
      <td><strong>Purpose</strong></td>
    </tr>
    <tr>
      <td>GET /intelligence/market-research</td>
      <td>intelligence_routes.py</td>
      <td>Competitive analysis &amp; market trends (Tavily, NewsAPI)</td>
    </tr>
    <tr>
      <td>POST /intelligence/content-strategy</td>
      <td>intelligence_routes.py</td>
      <td>Generate content strategy for niche</td>
    </tr>
    <tr>
      <td>GET /intelligence/trending</td>
      <td>intelligence_routes.py</td>
      <td>Retrieve trending topics &amp; hashtags</td>
    </tr>
    <tr>
      <td>POST /email/campaign/create</td>
      <td>email_routes.py</td>
      <td>Create email campaign (copy, A/B test variants)</td>
    </tr>
    <tr>
      <td>POST /email/campaign/send</td>
      <td>email_routes.py</td>
      <td>Send campaign via Resend</td>
    </tr>
    <tr>
      <td>GET /email/campaign/analytics</td>
      <td>email_routes.py</td>
      <td>Open rates, click rates, conversions</td>
    </tr>
    <tr>
      <td>GET /email/inbox</td>
      <td>email_routes.py</td>
      <td>Fetch client emails from Gmail (support inbox)</td>
    </tr>
  </tbody>
</table>

<h3>Webhooks &amp; Integrations</h3>
<table>
  <tbody>
    <tr>
      <td><strong>Endpoint</strong></td>
      <td><strong>Module</strong></td>
      <td><strong>Purpose</strong></td>
    </tr>
    <tr>
      <td>POST /webhook/meta</td>
      <td>webhook_receiver.py</td>
      <td>Meta webhook receiver (new DMs, comments, mentions)</td>
    </tr>
    <tr>
      <td>GET /webhook/meta</td>
      <td>webhook_receiver.py</td>
      <td>Webhook verification (handshake)</td>
    </tr>
    <tr>
      <td>POST /webhooks/late/*</td>
      <td>late_webhooks.py</td>
      <td>Late API webhook for platform delivery confirmation</td>
    </tr>
    <tr>
      <td>POST /webhooks/stripe</td>
      <td>billing_routes.py</td>
      <td>Stripe webhook (subscription updates, payment success/failure)</td>
    </tr>
    <tr>
      <td>GET /auth/callback</td>
      <td>oauth_routes.py</td>
      <td>OAuth redirect callback handler (all platforms)</td>
    </tr>
  </tbody>
</table>

<hr />

<h2 id="setup">⚡ Setup &amp; Deployment</h2>

<h3>Local Development Setup</h3>

<h4>Step 1: Clone &amp; Install Dependencies</h4>
<pre><code># Clone repository (or navigate to existing directory)
cd ~/Documents/Alita

# Create Python virtual environment
python3.11 -m venv .venv

# Activate virtual environment
# On Windows (PowerShell):
.venv\\Scripts\\Activate.ps1

# On macOS/Linux (bash):
source .venv/bin/activate

# Install Python dependencies
pip install -r requirements.txt
</code></pre>

<h4>Step 2: Configure Environment Variables</h4>
<pre><code># Copy .env template (or check existing .env)
# Ensure these Tier 1 variables are set:
ANTHROPIC_API_KEY=[YOUR_ANTHROPIC_API_KEY]
OPENAI_API_KEY=[YOUR_OPENAI_API_KEY]
DATABASE_URL=sqlite:///./automation.db

# For full functionality, also set Tier 2-4 variables:
# - Meta: INSTAGRAM_APP_ID, INSTAGRAM_APP_SECRET, INSTAGRAM_ACCESS_TOKEN, etc.
# - Late API: LATE_API_KEY (for TikTok, LinkedIn, X, etc.)
# - Stripe: STRIPE_SECRET_KEY, STRIPE_PUBLISHABLE_KEY
# - Resend: RESEND_API_KEY
# - Gmail: GMAIL_CLIENT_ID, GMAIL_CLIENT_SECRET
</code></pre>

<h4>Step 3: Initialize Database</h4>
<pre><code># Create tables &amp; run migrations
python init_db.py

# Verify SQLite database created
ls -la automation.db
</code></pre>

<h4>Step 4: Create Admin Account</h4>
<pre><code># Run admin creation script
python scripts/create_admin.py

# Enter admin email &amp; password when prompted
# Email: (your admin email)
# Password: (strong password)
</code></pre>

<h4>Step 5: Start Development Server</h4>
<pre><code># Start FastAPI with hot-reload
uvicorn web_app:app --reload --host 0.0.0.0 --port 8000

# Server will be available at http://localhost:8000
# API docs at http://localhost:8000/docs (Swagger UI)
# ReDoc at http://localhost:8000/redoc
</code></pre>

<h3>Production Deployment (Railway)</h3>

<h4>Prerequisites</h4>
<ul>
  <li>Railway account created (<a href="https://railway.app">railway.app</a>)</li>
  <li>GitHub repository linked to Railway</li>
  <li>PostgreSQL database provisioned in Railway</li>
  <li>Environment variables set in Railway dashboard</li>
</ul>

<h4>Deployment Process</h4>
<pre><code># 1. Commit code to GitHub
git add .
git commit -m "Deploy to Railway"
git push origin main

# 2. Railway automatically detects Procfile
# 3. Runs init_db.py (migrations)
# 4. Starts FastAPI with Procfile command:
#    web: python init_db.py && uvicorn web_app:app --host 0.0.0.0 --port \$PORT

# 4. Verify deployment
curl https://web-production-00e4.up.railway.app/health
# Response: {"status": "healthy"}
</code></pre>

<h4>Environment Configuration (Railway Dashboard)</h4>
<table>
  <tbody>
    <tr>
      <td><strong>Variable</strong></td>
      <td><strong>Development</strong></td>
      <td><strong>Production</strong></td>
    </tr>
    <tr>
      <td>DATABASE_URL</td>
      <td>sqlite:///./automation.db</td>
      <td>postgresql://user:pass@host/db (Railway-provided)</td>
    </tr>
    <tr>
      <td>STRIPE_SECRET_KEY</td>
      <td>sk_test_... (test mode)</td>
      <td>sk_live_... (LIVE mode — real charges)</td>
    </tr>
    <tr>
      <td>STRIPE_PUBLISHABLE_KEY</td>
      <td>pk_test_...</td>
      <td>pk_live_...</td>
    </tr>
    <tr>
      <td>DEBUG</td>
      <td>true</td>
      <td>false</td>
    </tr>
    <tr>
      <td>LOG_LEVEL</td>
      <td>debug</td>
      <td>warn</td>
    </tr>
  </tbody>
</table>

<h3>CI/CD Pipeline (GitHub Actions)</h3>

<p>Automated workflows trigger on push/PR:</p>
<table>
  <tbody>
    <tr>
      <td><strong>Workflow</strong></td>
      <td><strong>File</strong></td>
      <td><strong>Trigger</strong></td>
      <td><strong>Actions</strong></td>
    </tr>
    <tr>
      <td>Code Linting &amp; Tests</td>
      <td>.github/workflows/ci.yml</td>
      <td>Push to any branch, PR</td>
      <td>flake8 linting, pytest (if available)</td>
    </tr>
    <tr>
      <td>Auto Deploy to Railway</td>
      <td>.github/workflows/deploy.yml</td>
      <td>Push to main branch</td>
      <td>Push to Railway (auto-triggers Railway deployment)</td>
    </tr>
    <tr>
      <td>Health Check</td>
      <td>.github/workflows/health-check.yml</td>
      <td>Every 15 minutes (cron)</td>
      <td>Pings /.well-known/health endpoint</td>
    </tr>
  </tbody>
</table>

<hr />

<h2 id="troubleshooting">🆘 Troubleshooting &amp; Common Issues</h2>

<h3>1. Missing or Invalid API Keys</h3>

<p><strong>Symptom:</strong> Endpoints return 401/403 or "API key not set"</p>

<p><strong>Solution:</strong></p>
<ul>
  <li>Verify <code>.env</code> file exists in project root</li>
  <li>Check that critical Tier 1 keys are set:
    <ul>
      <li><code>ANTHROPIC_API_KEY</code> (Claude API)</li>
      <li><code>OPENAI_API_KEY</code> (GPT fallback)</li>
      <li><code>DATABASE_URL</code> (SQLite or PostgreSQL)</li>
    </ul>
  </li>
  <li>For platform-specific features, verify platform keys:
    <ul>
      <li><code>INSTAGRAM_ACCESS_TOKEN</code> + <code>INSTAGRAM_BUSINESS_ACCOUNT_ID</code> (for Instagram posting)</li>
      <li><code>LATE_API_KEY</code> (for TikTok, LinkedIn, X, Threads)</li>
      <li><code>STRIPE_SECRET_KEY</code> (for billing)</li>
    </ul>
  </li>
  <li>Use <code>python -c "import os; print(os.getenv('ANTHROPIC_API_KEY'))"</code> to test if .env is loaded</li>
</ul>

<h3>2. Database Connection Errors</h3>

<p><strong>Symptom:</strong> "sqlite3.DatabaseError" or "could not connect to PostgreSQL"</p>

<p><strong>Solution:</strong></p>
<ul>
  <li><strong>SQLite (dev):</strong>
    <ul>
      <li>Ensure <code>DATABASE_URL=sqlite:///./automation.db</code></li>
      <li>Check disk space (SQLite file should not exceed 1GB usually)</li>
      <li>If corrupted: delete <code>automation.db</code> and re-run <code>python init_db.py</code></li>
    </ul>
  </li>
  <li><strong>PostgreSQL (production):</strong>
    <ul>
      <li>Verify <code>DATABASE_URL</code> is set to Railway-provided connection string</li>
      <li>Check Railway dashboard for database status</li>
      <li>Ensure firewall allows outbound connections to Railway IP</li>
      <li>Test with: <code>psql $DATABASE_URL -c "SELECT 1;"</code></li>
    </ul>
  </li>
</ul>

<h3>3. OAuth Token Expiry</h3>

<p><strong>Symptom:</strong> "Invalid OAuth token" or "Token expired" when posting to social platforms</p>

<p><strong>Solution:</strong></p>
<ul>
  <li><strong>Meta (FB/IG):</strong>
    <ul>
      <li>Re-run OAuth flow: <code>GET /connect/meta/oauth</code> → authorize → redirect back</li>
      <li>Check <code>MetaOAuthToken</code> table for token expiry (<code>expires_at</code> field)</li>
      <li>System auto-refreshes tokens, but manual refresh may be needed</li>
    </ul>
  </li>
  <li><strong>Gmail:</strong>
    <ul>
      <li>Re-run Gmail OAuth: <code>GET /settings/email/oauth</code></li>
      <li>Ensure <code>GMAIL_CLIENT_ID</code>, <code>GMAIL_CLIENT_SECRET</code>, <code>GMAIL_REDIRECT_URI</code> are correct</li>
    </ul>
  </li>
  <li><strong>Late API:</strong>
    <ul>
      <li>Check if platform profile is still active in Late dashboard</li>
      <li>Late API tokens typically last 90 days — verify in Late account settings</li>
    </ul>
  </li>
</ul>

<h3>4. AI Agent Failures / Guardrails Blocking Responses</h3>

<p><strong>Symptom:</strong> Agent returns "blocked_by_guardrails" or empty response</p>

<p><strong>Solution:</strong></p>
<ul>
  <li>Check <code>guardrails_config.json</code> for rules matching your content:
    <ul>
      <li>Max message length: 2,000 characters</li>
      <li>Max word count: 500 words</li>
      <li>Banned patterns: profanity, spam, gibberish</li>
    </ul>
  </li>
  <li>Review logs in <code>logs/</code> folder for "guardrails" entries</li>
  <li>If content is being incorrectly flagged, edit <code>guardrails_config.json</code> and restart server</li>
  <li><strong>Human escalation:</strong> If agent detects keywords like "human", "escalate", "real person" — it flags for manual review (expected behavior)</li>
</ul>

<h3>5. Webhook Delivery Issues (Meta, Stripe, Late API)</h3>

<p><strong>Symptom:</strong> Webhooks show "Undelivered" in platform dashboard</p>

<p><strong>Solution:</strong></p>
<ul>
  <li><strong>Meta Webhook:</strong>
    <ul>
      <li>Verify <code>VERIFY_TOKEN</code> matches in Meta app settings</li>
      <li>Check that endpoint <code>POST /webhook/meta</code> is publicly accessible (not behind VPN/firewall)</li>
      <li>Test with: <code>curl -X POST http://localhost:8000/webhook/meta</code> (should return 400 if no payload)</li>
    </ul>
  </li>
  <li><strong>Stripe Webhook:</strong>
    <ul>
      <li>Verify <code>STRIPE_WEBHOOK_SECRET</code> matches in Stripe dashboard</li>
      <li>Check that endpoint <code>POST /webhooks/stripe</code> is accessible</li>
      <li>Use <code>stripe listen --forward-to localhost:8000/webhooks/stripe</code> to test locally</li>
    </ul>
  </li>
  <li><strong>Late API Webhook:</strong>
    <ul>
      <li>Verify Late API integration credentials (<code>LATE_API_KEY</code>) are active</li>
      <li>Check Late dashboard for webhook endpoint configuration</li>
    </ul>
  </li>
  <li><strong>General troubleshooting:</strong>
    <ul>
      <li>Check server logs for webhook processing errors</li>
      <li>Ensure server is accessible from internet (not running on localhost in production)</li>
      <li>Verify firewall allows incoming HTTPS (443) traffic</li>
    </ul>
  </li>
</ul>

<h3>6. Stripe Live Mode Warnings</h3>

<p><strong>Symptom:</strong> Charging real money in development; test mode needs to be used</p>

<p><strong>Solution:</strong></p>
<ul>
  <li><strong>Current Status:</strong> Production is configured with <code>LIVE keys</code> (real charges) — <strong>CORRECT for production</strong></li>
  <li><strong>Local Development:</strong> Switch to test keys in <code>.env</code>:
    <pre><code># Development (change in .env, don't commit)
STRIPE_SECRET_KEY=sk_test_REPLACE_WITH_YOUR_TEST_SECRET_KEY
STRIPE_PUBLISHABLE_KEY=pk_test_REPLACE_WITH_YOUR_TEST_PUBLISHABLE_KEY

# Test using card: 4242 4242 4242 4242 (any future date, any CVC)
</code></pre>
  </li>
  <li>After testing, switch back to <code>LIVE keys</code> before deployment</li>
  <li><strong>Never commit test keys to production branch</strong> — use GitHub Actions secrets instead</li>
</ul>

<h3>7. Image/Video Generation Failures</h3>

<p><strong>Symptom:</strong> POST /posts/generate returns image generation error</p>

<p><strong>Solution:</strong></p>
<ul>
  <li>Verify image generation API keys are set:
    <ul>
      <li><code>GOAPI_API_KEY</code> (Midjourney) — primary</li>
      <li><code>IDEOGRAM_API_KEY</code> (text-accurate images) — secondary</li>
      <li><code>OPENAI_API_KEY</code> (DALL-E fallback)</li>
    </ul>
  </li>
  <li>Check image generation provider status:
    <ul>
      <li>Midjourney: Check <a href="https://www.goapi.ai">GoAPI dashboard</a></li>
      <li>Ideogram: Check <a href="https://ideogram.ai">Ideogram dashboard</a></li>
    </ul>
  </li>
  <li>Check if client plan allows image generation:
    <ul>
      <li>Free plan: Limited (5/month)</li>
      <li>Starter+: Included</li>
      <li>Check <code>plan_limits.py</code> for feature gates</li>
    </ul>
  </li>
  <li>Review logs: <code>tail -f logs/alita.log | grep -i image</code></li>
</ul>

<h3>8. Rate Limiting / "Too Many Requests"</h3>

<p><strong>Symptom:</strong> 429 Too Many Requests error from platform API</p>

<p><strong>Solution:</strong></p>
<ul>
  <li>Platform-specific rate limits:
    <ul>
      <li><strong>Meta Graph API:</strong> 200 calls per hour (check Insights in Meta app)</li>
      <li><strong>Late API:</strong> 10,000 requests/day (check Late dashboard)</li>
      <li><strong>Anthropic Claude:</strong> Token limits (check billing in Anthropic console)</li>
    </ul>
  </li>
  <li>Solutions:
    <ul>
      <li>Implement exponential backoff in agent (<code>time.sleep(2**retry_count)</code>)</li>
      <li>Batch requests (combine multiple posts into one API call)</li>
      <li>Stagger scheduled posts to avoid burst requests</li>
      <li>Upgrade Late API plan for higher limits</li>
    </ul>
  </li>
</ul>

<h3>9. No Content Generated (RAG Not Working)</h3>

<p><strong>Symptom:</strong> Content agent returns empty or generic content, not client-specific</p>

<p><strong>Solution:</strong></p>
<ul>
  <li>Verify RAG is enabled &amp; ready:
    <ul>
      <li>Check <code>ClientProfile.rag_ready</code> field is <code>true</code></li>
      <li>Run onboarding again if <code>false</code>: <code>POST /onboarding/website-scrape</code> or <code>/onboarding/upload-docs</code></li>
    </ul>
  </li>
  <li>Check Qdrant vector database:
    <ul>
      <li>Verify Qdrant is running &amp; accessible</li>
      <li>Check Qdrant collections: <code>python -c "from qdrant_client import QdrantClient; c = QdrantClient('localhost:6333'); print(c.get_collections())"</code></li>
    </ul>
  </li>
  <li>Check agent logs:
    <ul>
      <li"><code>Connection to Qdrant failed</code>" → restart Qdrant service</li>
      <li><code>No RAG results found</code> → client documents not ingested, run onboarding</li>
    </ul>
  </li>
</ul>

<h3>10. Running Tests / Linting Issues</h3>

<p><strong>Symptom:</strong> Code fails pre-commit checks or GitHub Actions</p>

<p><strong>Solution:</strong></p>
<ul>
  <li><strong>Linting (flake8):</strong>
    <pre><code># Run linting locally to find issues
flake8 . --max-line-length=120 --ignore=E501,W503

# Auto-fix some issues
autopep8 --in-place --aggressive --aggressive -r .
</code></pre>
  </li>
  <li><strong>Run Tests:</strong>
    <pre><code># If pytest is configured
pytest tests/ -v

# Run with coverage
pytest tests/ --cov=agents --cov=api
</code></pre>
  </li>
  <li><strong>Type Checking:</strong>
    <pre><code># Check type hints with mypy
mypy agents/ api/ utils/
</code></pre>
  </li>
</ul>

<hr />

<h2 id="references">📚 Key Files &amp; References</h2>

<h3>Core Application Files</h3>
<ul>
  <li><a href="https://example.com/web_app.py"><strong>web_app.py</strong></a> (~1,822 lines) — FastAPI main application, route mounting, middleware, exception handlers</li>
  <li><a href="https://example.com/init_db.py"><strong>init_db.py</strong></a> — Database initialization, migrations, seed data</li>
  <li><a href="https://example.com/requirements.txt"><strong>requirements.txt</strong></a> — Complete Python dependency list with pinned versions</li>
  <li><a href="https://example.com/.env"><strong>.env</strong></a> — Environment variables (177 total across Tier 1-4 services)</li>
</ul>

<h3>Database &amp; ORM</h3>
<ul>
  <li><a href="https://example.com/database/models.py"><strong>database/models.py</strong></a> (356 lines) — SQLAlchemy User, ClientProfile, OAuth token models</li>
  <li><a href="https://example.com/database/db.py"><strong>database/db.py</strong></a> — SQLAlchemy engine initialization, session management</li>
</ul>

<h3>AI Agents (15 modules)</h3>
<ul>
  <li><strong>agents/content_agent.py</strong> — 86 platform-specific prompt templates</li>
  <li><strong>agents/posting_agent.py</strong> — 3-tier platform routing &amp; delivery</li>
  <li><strong>agents/engagement_agent.py</strong> — Auto DM/comment responses</li>
  <li><strong>agents/analytics_agent.py</strong> — Performance tracking &amp; reporting</li>
  <li><strong>agents/rag_system.py</strong> — Qdrant vector DB semantic search</li>
  <li><strong>agents/voice_matching_system.py</strong> — Client style replication</li>
  <li><strong>agents/image_generator.py</strong> — Multi-model image generation</li>
  <li><strong>agents/faceless_generator.py</strong> — AI video pipeline</li>
  <li><strong>agents/marketing_intelligence_agent.py</strong> — Competitive research &amp; strategy</li>
  <li><strong>agents/growth_agent.py</strong> — Audience growth automation</li>
  <li><strong>agents/agent_scheduler.py</strong> — APScheduler-based task automation</li>
  <li><a href="https://example.com/agents/README.md"><strong>agents/README.md</strong></a> — Agent documentation</li>
</ul>

<h3>API Routes (33 modules)</h3>
<ul>
  <li><strong>api/auth_routes.py</strong> — Authentication, JWT, 2FA, OAuth</li>
  <li><strong>api/billing_routes.py</strong> — Stripe subscriptions &amp; webhooks</li>
  <li><strong>api/post_creation_routes.py</strong> — Content generation &amp; management</li>
  <li><strong>api/calendar_routes.py</strong> — Content calendar &amp; scheduling</li>
  <li><strong>api/analytics_routes.py</strong> — Performance dashboards</li>
  <li><strong>api/webhook_receiver.py</strong> — Meta webhook handling</li>
  <li><strong>api/linkedin_client.py, twitter_client.py, etc.</strong> — Platform-specific integrations</li>
</ul>

<h3>Configuration &amp; Documentation</h3>
<ul>
  <li><a href="https://example.com/README.md"><strong>README.md</strong></a> (683 lines) — Complete project documentation</li>
  <li><a href="https://example.com/CONTRIBUTING.md"><strong>CONTRIBUTING.md</strong></a> — Developer contribution guidelines</li>
  <li><a href="https://example.com/Procfile"><strong>Procfile</strong></a> — Railway deployment configuration</li>
  <li><a href="https://example.com/guardrails_config.json"><strong>guardrails_config.json</strong></a> — Abuse protection rules</li>
  <li><a href="https://example.com/docs"><strong>docs/</strong></a> — Architecture, setup, feature documentation</li>
</ul>

<h3>Script Utilities</h3>
<ul>
  <li><strong>scripts/create_admin.py</strong> — Create initial admin user</li>
  <li><strong>scripts/seed_railway_meta.py</strong> — Production database seeding</li>
  <li><strong>scripts/migrate_meta_columns.py</strong> — Database migrations</li>
  <li><strong>scripts/get_facebook_pages.py</strong> — Discover Facebook page IDs</li>
</ul>

<h3>Knowledge Bases</h3>
<ul>
  <li><strong>Agent RAGs/</strong> — 15 RAG directories with agent-specific prompts &amp; knowledge</li>
  <li><strong>knowledge_docs/</strong> — Client document storage for semantic search</li>
  <li><strong>faceless_video_prompts/</strong> — 15 video content category templates</li>
  <li><strong>image_generation_prompts/</strong> — Image generation prompt templates</li>
</ul>

<hr />

<h2 id="security">🔒 Configuration &amp; Security</h2>

<h3>.env File Structure</h3>

<p>The <code>.env</code> file contains 177 environment variables organized by service:</p>
<table>
  <tbody>
    <tr>
      <td><strong>Section</strong></td>
      <td><strong>Variables</strong></td>
      <td><strong>Count</strong></td>
      <td><strong>Required</strong></td>
    </tr>
    <tr>
      <td>Claude API Configuration</td>
      <td>ANTHROPIC_API_KEY, CLAUDE_HAIKU_MODEL, CLAUDE_SONNET_MODEL, CLAUDE_DEFAULT_MODEL</td>
      <td>4</td>
      <td>Yes</td>
    </tr>
    <tr>
      <td>OpenAI Configuration</td>
      <td>OPENAI_API_KEY</td>
      <td>1</td>
      <td>Yes</td>
    </tr>
    <tr>
      <td>Database</td>
      <td>DATABASE_URL</td>
      <td>1</td>
      <td>Yes</td>
    </tr>
    <tr>
      <td>Meta/Instagram</td>
      <td>INSTAGRAM_APP_ID/SECRET, INSTAGRAM_ACCESS_TOKEN, INSTAGRAM_BUSINESS_ACCOUNT_ID, VERIFY_TOKEN</td>
      <td>5</td>
      <td>Conditional</td>
    </tr>
    <tr>
      <td>Confluence</td>
      <td>CONFLUENCE_BASE_URL, CONFLUENCE_EMAIL, CONFLUENCE_API_TOKEN, CONFLUENCE_SPACE_KEY, CONFLUENCE_PARENT_PAGE_ID</td>
      <td>5</td>
      <td>No (documentation only)</td>
    </tr>
    <tr>
      <td>Late API &amp; Profiles</td>
      <td>LATE_API_KEY, LATE_PROFILE_* (10 platform profiles)</td>
      <td>11</td>
      <td>Conditional</td>
    </tr>
    <tr>
      <td>Media Uploads</td>
      <td>IMGBB_API_KEY</td>
      <td>1</td>
      <td>Conditional</td>
    </tr>
    <tr>
      <td>Intelligence APIs</td>
      <td>TAVILY_API_KEY, NEWSAPI_KEY, YOUTUBE_API_KEY, GEMINI_API_KEY</td>
      <td>4</td>
      <td>Conditional</td>
    </tr>
    <tr>
      <td>Media Generation</td>
      <td>PEXELS_API_KEY, PIXABAY_API_KEY, ELEVENLABS_API_KEY, FAL_API_KEY, IDEOGRAM_API_KEY, GOAPI_API_KEY</td>
      <td>6</td>
      <td>Conditional</td>
    </tr>
    <tr>
      <td>OAuth &amp; Encryption</td>
      <td>TOKEN_ENCRYPTION_KEY, META_APP_ID, META_APP_SECRET, REDIRECT_URIs</td>
      <td>6</td>
      <td>Yes</td>
    </tr>
    <tr>
      <td>Email (Resend)</td>
      <td>RESEND_API_KEY, EMAIL_FROM_ADDRESS, EMAIL_FROM_NAME</td>
      <td>3</td>
      <td>Conditional</td>
    </tr>
    <tr>
      <td>Gmail</td>
      <td>GMAIL_CLIENT_ID, GMAIL_CLIENT_SECRET, GMAIL_REDIRECT_URI</td>
      <td>3</td>
      <td>Conditional</td>
    </tr>
    <tr>
      <td>SMS (Twilio)</td>
      <td>TWILIO_SMS_ENABLED, TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_PHONE_NUMBER</td>
      <td>4</td>
      <td>No (on hold)</td>
    </tr>
    <tr>
      <td>Stripe Payments</td>
      <td>STRIPE_SECRET_KEY, STRIPE_PUBLISHABLE_KEY, STRIPE_WEBHOOK_SECRET, STRIPE_PRICE_* (13 prices), STRIPE_PROD_* (10 products)</td>
      <td>26</td>
      <td>Yes (production)</td>
    </tr>
    <tr>
      <td>Admin Account</td>
      <td>ADMIN_EMAIL, ADMIN_PASSWORD, ADMIN_NAME</td>
      <td>3</td>
      <td>Yes (setup)</td>
    </tr>
  </tbody>
</table>

<p><strong>Total: 177 environment variables</strong></p>

<h3>Security Features</h3>

<h4>Authentication &amp; Authorization</h4>
<ul>
  <li><strong>Password Hashing:</strong> bcrypt with per-user salt (not reversible)</li>
  <li><strong>Session Tokens:</strong> JWT (JSON Web Tokens) with configurable expiry (~30 days default)</li>
  <li><strong>Multi-Factor Authentication (MFA):</strong>
    <ul>
      <li>TOTP (Time-based One-Time Password) via Google Authenticator / Authy</li>
      <li>Email-based OTP (sent via Resend)</li>
      <li>SMS-based OTP (via Twilio, on hold pending A2P approval)</li>
      <li>WebAuthn / Passkeys (FIDO2 hardware key support)</li>
    </ul>
  </li>
  <li><strong>Social Login:</strong> OAuth 2.0 flows (Google, Facebook, Meta, Twitter, TikTok, YouTube)</li>
</ul>

<h4>Data Encryption</h4>
<ul>
  <li><strong>At-Rest Encryption:</strong> Fernet (symmetric encryption) for OAuth tokens &amp; sensitive data in database</li>
  <li><strong>In-Transit Encryption:</strong> HTTPS/TLS for all API communication (enforced in production)</li>
  <li><strong>Token Encryption:</strong> <code>TOKEN_ENCRYPTION_KEY</code> used for encrypting Meta/Gmail OAuth refresh tokens before storage</li>
</ul>

<h4>Abuse Prevention</h4>
<ul>
  <li><strong>Guardrails System:</strong> Auto-filters 100+ abuse patterns before posting
    <ul>
      <li>Profanity detection</li>
      <li>Spam indicators (repetition, suspicious links)</li>
      <li>Gibberish detection</li>
      <li>Length limits (2,000 char max per message)</li>
    </ul>
  </li>
  <li><strong>Human Escalation:</strong> If content contains "human", "agent", "real person", it flags for manual review</li>
  <li><strong>Rate Limiting:</strong> Per-client, per-platform request throttling to prevent shadowbans</li>
</ul>

<h4>Sensitive Data Handling</h4>
<ul>
  <li><strong>API Keys:</strong> Never logged or exposed in error messages</li>
  <li><strong>Passwords:</strong> Only bcrypt hashes stored</li>
  <li><strong>OAuth Tokens:</strong> Encrypted with Fernet before database storage</li>
  <li><strong>.env File:</strong> Should be <code>.gitignored</code> (never committed)</li>
  <li><strong>Logs:</strong> Sensitive data (tokens, passwords) redacted from logs</li>
</ul>

<h4>Database Security</h4>
<ul>
  <li><strong>SQL Injection Prevention:</strong> SQLAlchemy ORM parameterized queries (not raw SQL)</li>
  <li><strong>Row-Level Security:</strong> Users can only access their own client profiles and data</li>
  <li><strong>Admin Isolation:</strong> Admin user account with separate permissions</li>
</ul>

<h4>API Security</h4>
<ul>
  <li><strong>CORS (Cross-Origin Resource Sharing):</strong> Configured to allow only trusted domains</li>
  <li><strong>CSRF Protection:</strong> Token-based CSRF prevention for state-changing operations</li>
  <li><strong>Webhook Verification:</strong> Meta &amp; Stripe webhooks validated using signatures</li>
</ul>

<h3>guardrails_config.json</h3>

<p>Configurable abuse protection rules:</p>
<pre><code>{
  "max_message_length": 2000,
  "max_word_count": 500,
  "max_repetition_ratio": 0.5,
  "banned_patterns": [
    "profanity_list...",
    "spam_indicators...",
    "suspicious_urls..."
  ],
  "require_human_review_keywords": [
    "human", "real person", "agent", "escalate"
  ]
}
</code></pre>

<h3>Deployment Security Checklist</h3>

<table>
  <tbody>
    <tr>
      <td><strong>Item</strong></td>
      <td><strong>Status</strong></td>
      <td><strong>Notes</strong></td>
    </tr>
    <tr>
      <td>HTTPS / TLS Enabled</td>
      <td>✅ Yes</td>
      <td>Railway provides automatic SSL certificates</td>
    </tr>
    <tr>
      <td>.env File in .gitignore</td>
      <td>✅ Yes</td>
      <td>Never commit secrets to repo</td>
    </tr>
    <tr>
      <td>Admin Account Created</td>
      <td>✅ Yes</td>
      <td>Via scripts/create_admin.py (one-time setup)</td>
    </tr>
    <tr>
      <td>Stripe Live Keys Configured</td>
      <td>✅ Yes</td>
      <td>Production currently uses sk_live_* (REAL charges)</td>
    </tr>
    <tr>
      <td>Database Backups</td>
      <td>✅ Yes</td>
      <td>Railway PostgreSQL includes automated backups</td>
    </tr>
    <tr>
      <td>Webhook Verification Enabled</td>
      <td>✅ Yes</td>
      <td>Meta &amp; Stripe webhooks validated</td>
    </tr>
    <tr>
      <td>Rate Limiting</td>
      <td>✅ Yes</td>
      <td>Per-client platform-specific throttling</td>
    </tr>
    <tr>
      <td>CORS Configured</td>
      <td>✅ Yes</td>
      <td>Whitelist trusted domains in FastAPI middleware</td>
    </tr>
  </tbody>
</table>

<hr />

<h2>📞 Support &amp; Further Reading</h2>

<ul>
  <li><strong>GitHub Repo Issues:</strong> File bugs &amp; feature requests</li>
  <li><strong>Documentation:</strong> See <a href="https://example.com/README.md">README.md</a>, <a href="https://example.com/CONTRIBUTING.md">CONTRIBUTING.md</a>, <code>docs/</code> folder</li>
  <li><strong>API Documentation:</strong> Visit <code>http://localhost:8000/docs</code> (Swagger UI) when running locally</li>
  <li><strong>Contact:</strong> For production support, reach out to the development team</li>
</ul>

<hr />

<p><strong style="color: green;">✅ Alita AI is production-ready with live integrations across 8+ platforms, 15 AI agents, and comprehensive billing infrastructure.</strong></p>
"""
    
    return content


def create_confluence_page():
    """Create the page in Confluence using REST API"""
    
    import base64
    
    # Use Basic Auth with email:api_token
    auth_string = base64.b64encode(
        f"{CONFLUENCE_EMAIL}:{CONFLUENCE_API_TOKEN}".encode()
    ).decode()
    
    headers = {
        "Authorization": f"Basic {auth_string}",
        "Content-Type": "application/json",
    }
    
    page_content = build_page_content()
    
    # Confluence payload for creating a page
    payload = {
        "type": "page",
        "title": PAGE_TITLE,
        "space": {"key": CONFLUENCE_SPACE_KEY},
        "ancestors": [{"id": int(CONFLUENCE_PARENT_PAGE_ID)}],  # Add to parent page
        "body": {
            "storage": {
                "value": page_content,
                "representation": "storage"
            }
        }
    }
    
    print(f"📝 Creating Confluence page: '{PAGE_TITLE}'")
    print(f"🔗 Confluence Space: {CONFLUENCE_SPACE_KEY}")
    print(f"📍 Parent Page ID: {CONFLUENCE_PARENT_PAGE_ID}")
    print(f"🌐 Base URL: {CONFLUENCE_BASE_URL}")
    print()
    
    try:
        response = requests.post(
            API_URL,
            json=payload,
            headers=headers,
            timeout=30
        )
        
        if response.status_code in [200, 201]:
            page_data = response.json()
            page_id = page_data.get("id")
            page_url = f"{CONFLUENCE_BASE_URL}/pages/viewpage.action?pageId={page_id}"
            
            print("✅ SUCCESS! Page created in Confluence")
            print(f"📄 Page ID: {page_id}")
            print(f"🔗 View Page: {page_url}")
            print()
            print("📋 Page Contents:")
            print(f"  • Executive Summary")
            print(f"  • Tech Stack (databases, APIs, services)")
            print(f"  • System Requirements (Tier 1-4 API keys)")
            print(f"  • Database Schema (Users, ClientProfile, OAuth tokens)")
            print(f"  • Architecture Overview (FastAPI, agents, data flow)")
            print(f"  • AI Agents Reference (15 agents table)")
            print(f"  • API Routes Overview (33 modules, 150+ endpoints)")
            print(f"  • Setup & Deployment (local dev + Railway production)")
            print(f"  • Troubleshooting (10 common issues & solutions)")
            print(f"  • Key Files & References (links to source code)")
            print(f"  • Configuration & Security (encryption, MFA, abuse prevention)")
            print()
            return True
            
        elif response.status_code == 401:
            print("❌ ERROR: Unauthorized (invalid API token)")
            print(f"Response: {response.text}")
            return False
            
        elif response.status_code == 404:
            print("❌ ERROR: Not found (check space key / parent page ID)")
            print(f"Response: {response.text}")
            return False
            
        else:
            print(f"❌ ERROR: HTTP {response.status_code}")
            print(f"Response: {response.text}")
            return False
            
    except requests.exceptions.ConnectionError:
        print(f"❌ ERROR: Could not connect to {CONFLUENCE_BASE_URL}")
        print("   Check that Confluence URL is correct and accessible")
        return False
    except Exception as e:
        print(f"❌ ERROR: {str(e)}")
        return False


if __name__ == "__main__":
    # Validate environment variables
    required_vars = [
        "CONFLUENCE_BASE_URL",
        "CONFLUENCE_EMAIL",
        "CONFLUENCE_API_TOKEN",
        "CONFLUENCE_SPACE_KEY",
        "CONFLUENCE_PARENT_PAGE_ID"
    ]
    
    missing_vars = [var for var in required_vars if not os.getenv(var)]
    
    if missing_vars:
        print("❌ ERROR: Missing required environment variables:")
        for var in missing_vars:
            print(f"  - {var}")
        print()
        print("Ensure these are set in .env file:")
        print("  CONFLUENCE_BASE_URL=https://your-instance.atlassian.net/wiki")
        print("  CONFLUENCE_EMAIL=your-email@example.com")
        print("  CONFLUENCE_API_TOKEN=your-api-token")
        print("  CONFLUENCE_SPACE_KEY=SPACE_KEY")
        print("  CONFLUENCE_PARENT_PAGE_ID=12345")
        exit(1)
    
    # Create the page
    success = create_confluence_page()
    exit(0 if success else 1)
