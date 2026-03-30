"""
database/models.py — SQLAlchemy ORM models for Alita client portal.
"""
import sys
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, Boolean, DateTime, Text, Enum as SAEnum, ForeignKey
)
from sqlalchemy.orm import relationship
from database.db import Base
import enum


# ─────────────────────────────────────────────
# Enums
# ─────────────────────────────────────────────

class OnboardingStatus(str, enum.Enum):
    pending        = "pending"          # just signed up
    scraping       = "scraping"         # website scrape in progress
    research_queue = "research_queue"   # manual details submitted, awaiting admin review
    research_run   = "research_run"     # admin approved, deep research running
    complete       = "complete"         # RAG ingested, fully set up
    failed         = "failed"           # something went wrong


class DeepResearchStatus(str, enum.Enum):
    pending  = "pending"   # waiting for admin review
    approved = "approved"  # admin approved — ready to run
    rejected = "rejected"  # admin rejected — needs revision
    running  = "running"   # research actively in progress
    complete = "complete"  # done, ingested into RAG
    failed   = "failed"    # error during research


class OnboardingMethod(str, enum.Enum):
    website = "website"   # provided a URL to scrape
    manual  = "manual"    # filled in business details form
    files   = "files"     # uploaded PDF / DOCX / TXT / MD documents


class PlanTier(str, enum.Enum):
    free    = "free"
    starter = "starter"
    growth  = "growth"
    pro     = "pro"


class PlanStatus(str, enum.Enum):
    active    = "active"
    trialing  = "trialing"
    past_due  = "past_due"
    canceled  = "canceled"
    paused    = "paused"


class PlanPeriod(str, enum.Enum):
    monthly = "monthly"
    annual  = "annual"


# ─────────────────────────────────────────────
# Users (auth)
# ─────────────────────────────────────────────

class User(Base):
    __tablename__ = "users"

    id            = Column(String(36), primary_key=True)         # UUID
    email         = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    full_name     = Column(String(255), nullable=False)
    is_admin      = Column(Boolean, default=False)
    is_active     = Column(Boolean, default=True)
    created_at    = Column(DateTime, default=datetime.utcnow)
    last_login    = Column(DateTime, nullable=True)

    # Email verification
    email_verified = Column(Boolean, default=False)

    # Two-Factor Authentication
    mfa_enabled   = Column(Boolean, default=False)
    mfa_method    = Column(String(20), nullable=True)   # 'totp', 'email', 'sms'
    mfa_secret    = Column(String(100), nullable=True)  # TOTP secret (encrypted base32)
    phone_number  = Column(String(30), nullable=True)   # for SMS OTP

    # Social login (Google / Facebook)
    oauth_provider    = Column(String(30),  nullable=True)                 # 'google' | 'facebook'
    oauth_provider_id = Column(String(128), nullable=True, index=True)     # provider's user ID

    # One user → one client profile
    client_profile = relationship("ClientProfile", back_populates="user", uselist=False)


# ─────────────────────────────────────────────
# Client Profiles (business info + onboarding state)
# ─────────────────────────────────────────────

class ClientProfile(Base):
    __tablename__ = "client_profiles"

    id                  = Column(String(36), primary_key=True)   # UUID
    user_id             = Column(String(36), ForeignKey("users.id"), unique=True, nullable=False)
    client_id           = Column(String(100), unique=True, nullable=False, index=True)  # e.g., "cool_cruise_co"

    # Business basics
    business_name       = Column(String(255), nullable=False)
    niche               = Column(String(255), nullable=True)      # auto-detected or entered
    website_url         = Column(String(500), nullable=True)
    description         = Column(Text, nullable=True)             # short business description

    # Manual details (Path B onboarding)
    target_audience     = Column(Text, nullable=True)
    services_products   = Column(Text, nullable=True)
    unique_value_prop   = Column(Text, nullable=True)
    location            = Column(String(255), nullable=True)
    competitors         = Column(Text, nullable=True)             # comma-separated

    # Onboarding state
    onboarding_method   = Column(SAEnum(OnboardingMethod), nullable=True)
    onboarding_status   = Column(SAEnum(OnboardingStatus), default=OnboardingStatus.pending)
    onboarding_error    = Column(Text, nullable=True)
    onboarding_step     = Column(Integer, default=0)              # 0=not started, 1-6=wizard steps, 7=complete
    rag_ready           = Column(Boolean, default=False)          # True once RAG is populated

    # ── Billing / Plan ─────────────────────────────────────────────
    plan_tier              = Column(String(20), default="free", nullable=False)    # free|starter|growth|pro
    plan_status            = Column(String(20), default="active", nullable=False)  # active|trialing|past_due|canceled
    plan_period            = Column(String(20), default="monthly", nullable=False) # monthly|annual
    stripe_customer_id     = Column(String(100), nullable=True, index=True)
    stripe_subscription_id = Column(String(100), nullable=True)
    trial_ends_at          = Column(DateTime, nullable=True)
    plan_activated_at      = Column(DateTime, nullable=True)

    # ── Monthly Usage Counters (reset each billing cycle) ──────────
    usage_posts_created         = Column(Integer, default=0)  # AI posts generated
    usage_images_created        = Column(Integer, default=0)  # AI images generated
    usage_videos_created        = Column(Integer, default=0)  # faceless videos generated
    usage_replies_sent          = Column(Integer, default=0)  # AI engagement replies
    usage_campaigns_sent        = Column(Integer, default=0)  # email campaigns sent
    usage_research_run          = Column(Integer, default=0)  # deep research sessions
    usage_competitive_research  = Column(Integer, default=0)  # competitive research reports
    usage_growth_strategy       = Column(Integer, default=0)  # growth strategy sessions
    usage_reset_at              = Column(DateTime, nullable=True)  # last counter reset

    # ── Add-On Tracking ─────────────────────────────────────────────
    active_addons           = Column(Text, default='{}')   # JSON: {addon_key: True}
    addon_subscription_ids  = Column(Text, default='{}')   # JSON: {addon_key: stripe_sub_id}

    # ── Persistent Flags (survive Railway redeploys) ────────────────
    tone_configured     = Column(Boolean, default=False)     # True once tone prefs saved

    # ── Tone / Style / Voice (survive Railway redeploys) ────────────
    tone_preferences_json   = Column(Text, nullable=True)   # Full tone_prefs.json content
    normalized_samples_text = Column(Text, nullable=True)   # Writing style DNA text
    creative_preferences_json = Column(Text, nullable=True) # Reference images + gen toggles
    voice_profile_json      = Column(Text, nullable=True)   # Full voice profile (style_dna etc.)

    # ── Email AI Agreement (permanent record) ──────────────────────
    email_ai_agreed_at    = Column(DateTime, nullable=True)    # when user accepted email AI terms
    email_ai_agreement_ip = Column(String(50), nullable=True)  # IP address at time of agreement

    # ── Scheduler / Auto-Reply Config (survive Railway redeploys) ──
    scheduler_config_json   = Column(Text, nullable=True)   # Per-client scheduler settings
    auto_reply_settings_json = Column(Text, nullable=True)  # Per-client DM/comment toggles

    # ── Notification preferences (email toggles per type) ───────────
    notification_email_prefs_json = Column(Text, nullable=True)  # JSON: {notification_type: bool}

    # ── Growth recommendation interest override ─────────────────────
    growth_interests_json = Column(Text, nullable=True)  # JSON: {"interests": ["social media saas", ...]}

    created_at          = Column(DateTime, default=datetime.utcnow)
    updated_at          = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # ── Meta (Instagram / Facebook) OAuth connection ────────────────────
    # Stored in the main PostgreSQL DB so they survive Railway redeploys.
    meta_user_id          = Column(String(64),  nullable=True, index=True)   # Meta numeric user id
    meta_ig_account_id    = Column(String(64),  nullable=True)               # Instagram business account id
    meta_ig_username      = Column(String(200), nullable=True)               # e.g. "nexarilyai"
    meta_facebook_page_id = Column(String(64),  nullable=True)               # Facebook page id
    meta_connected_at     = Column(DateTime,    nullable=True)               # when OAuth completed

    # Relationships
    user                        = relationship("User", back_populates="client_profile")
    deep_research_requests      = relationship("DeepResearchRequest", back_populates="client_profile")
    meta_oauth_token            = relationship("MetaOAuthToken", back_populates="client_profile",
                                               uselist=False, cascade="all, delete-orphan")
    gmail_oauth_token           = relationship("GmailOAuthToken", back_populates="client_profile",
                                               uselist=False, cascade="all, delete-orphan")
    email_imap_connection        = relationship("EmailIMAPConnection", back_populates="client_profile",
                                               uselist=False, cascade="all, delete-orphan")
    microsoft_oauth_token        = relationship("MicrosoftOAuthToken", back_populates="client_profile",
                                               uselist=False, cascade="all, delete-orphan")
    email_threads                = relationship("EmailThread", back_populates="client_profile",
                                               cascade="all, delete-orphan")


# ─────────────────────────────────────────────
# Meta OAuth Tokens  (persisted in main DB — survives Railway redeploys)
# ─────────────────────────────────────────────

class MetaOAuthToken(Base):
    """
    Stores the encrypted Meta (Facebook/Instagram) OAuth access token for a client.
    Lives in the main PostgreSQL database so it persists across Railway deploys
    (unlike the legacy alita_oauth.db SQLite file which lives only on the container OS).
    """
    __tablename__ = "meta_oauth_tokens"

    id                   = Column(String(36), primary_key=True)                              # UUID
    client_profile_id    = Column(String(36), ForeignKey("client_profiles.id"),
                                  unique=True, nullable=False, index=True)
    meta_user_id         = Column(String(64),  nullable=False, index=True)                   # Meta numeric id
    access_token_enc     = Column(Text, nullable=False)                                       # Fernet-encrypted
    token_type           = Column(String(20),  default="bearer")
    scopes               = Column(Text,        nullable=True)                                 # comma-separated
    is_long_lived        = Column(Boolean,     default=True)
    expires_at           = Column(String(50),  nullable=True)                                 # Unix ts as string
    ig_account_id        = Column(String(64),  nullable=True)
    facebook_page_id     = Column(String(64),  nullable=True)
    created_at           = Column(DateTime,    default=datetime.utcnow)
    updated_at           = Column(DateTime,    default=datetime.utcnow, onupdate=datetime.utcnow)

    client_profile       = relationship("ClientProfile", back_populates="meta_oauth_token")


# ─────────────────────────────────────────────
# Gmail OAuth Tokens  (persisted in main DB — survives Railway redeploys)
# ─────────────────────────────────────────────

class GmailOAuthToken(Base):
    """
    Stores Gmail OAuth refresh token for a client so the AI can read/send
    emails from the client's own Gmail inbox.
    Lives in PostgreSQL so it persists across Railway deploys.
    """
    __tablename__ = "gmail_oauth_tokens"

    id                   = Column(String(36), primary_key=True)
    client_profile_id    = Column(String(36), ForeignKey("client_profiles.id"),
                                  unique=True, nullable=False, index=True)
    email_address        = Column(String(255), nullable=False)              # Gmail address connected
    refresh_token_enc    = Column(Text, nullable=False)                     # Fernet-encrypted
    scopes               = Column(Text, nullable=True)                      # comma-separated
    created_at           = Column(DateTime, default=datetime.utcnow)
    updated_at           = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    client_profile       = relationship("ClientProfile", back_populates="gmail_oauth_token")


# ─────────────────────────────────────────────
# IMAP / SMTP Connections  (non-Gmail — Outlook, Yahoo, iCloud, custom domain)
# ─────────────────────────────────────────────

class EmailIMAPConnection(Base):
    """
    Stores IMAP/SMTP credentials for non-Gmail email providers.
    The app password is Fernet-encrypted at rest.
    Lives in PostgreSQL so it persists across Railway redeploys.
    """
    __tablename__ = "email_imap_connections"

    id                   = Column(String(36), primary_key=True)          # UUID
    client_profile_id    = Column(String(36), ForeignKey("client_profiles.id"),
                                  unique=True, nullable=False, index=True)
    email_address        = Column(String(255), nullable=False)            # e.g. user@outlook.com
    provider             = Column(String(50),  nullable=False)            # outlook/yahoo/icloud/zoho/custom
    imap_host            = Column(String(255), nullable=False)
    imap_port            = Column(Integer,     default=993)
    smtp_host            = Column(String(255), nullable=False)
    smtp_port            = Column(Integer,     default=587)
    password_enc         = Column(Text,        nullable=False)            # Fernet-encrypted app password
    created_at           = Column(DateTime,    default=datetime.utcnow)
    updated_at           = Column(DateTime,    default=datetime.utcnow, onupdate=datetime.utcnow)

    client_profile       = relationship("ClientProfile", back_populates="email_imap_connection")


# ─────────────────────────────────────────────
# Deep Research Requests (manual path — admin reviews before running)
# ─────────────────────────────────────────────

class DeepResearchRequest(Base):
    __tablename__ = "deep_research_requests"

    id                  = Column(String(36), primary_key=True)   # UUID
    client_profile_id   = Column(String(36), ForeignKey("client_profiles.id"), nullable=False)

    # The research brief assembled from the manual form
    research_query      = Column(Text, nullable=False)           # AI-generated query from form data
    raw_business_details = Column(Text, nullable=False)          # JSON dump of form submission

    # Admin review
    status              = Column(SAEnum(DeepResearchStatus), default=DeepResearchStatus.pending)
    admin_notes         = Column(Text, nullable=True)            # rejection reason or approval notes
    reviewed_by         = Column(String(255), nullable=True)     # admin email
    reviewed_at         = Column(DateTime, nullable=True)

    # Research results
    research_results    = Column(Text, nullable=True)            # raw research output
    ingested_at         = Column(DateTime, nullable=True)        # when added to RAG

    created_at          = Column(DateTime, default=datetime.utcnow)
    updated_at          = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    client_profile      = relationship("ClientProfile", back_populates="deep_research_requests")


# ─────────────────────────────────────────────
# Password Reset Tokens
# ─────────────────────────────────────────────

class PasswordResetToken(Base):
    __tablename__ = "password_reset_tokens"

    id         = Column(String(36), primary_key=True)
    user_id    = Column(String(36), ForeignKey("users.id"), nullable=False)
    token      = Column(String(100), unique=True, nullable=False, index=True)
    expires_at = Column(DateTime, nullable=False)
    used       = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)


# ─────────────────────────────────────────────
# Email Verification Tokens
# ─────────────────────────────────────────────

class EmailVerificationToken(Base):
    __tablename__ = "email_verification_tokens"

    id         = Column(String(36), primary_key=True)
    user_id    = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    token      = Column(String(100), unique=True, nullable=False, index=True)
    expires_at = Column(DateTime, nullable=False)
    used       = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)


# ─────────────────────────────────────────────
# Two-Factor OTP (email & SMS method codes)
# ─────────────────────────────────────────────

class TwoFactorOTP(Base):
    __tablename__ = "two_factor_otps"

    id         = Column(String(36), primary_key=True)
    user_id    = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    code       = Column(String(10), nullable=False)       # 6-digit OTP
    purpose    = Column(String(20), default="login")      # 'login' or 'setup'
    expires_at = Column(DateTime, nullable=False)
    used       = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)


# ─────────────────────────────────────────────
# Trusted Devices  (skip 2FA on recognized browsers / apps)
# ─────────────────────────────────────────────

class TrustedDevice(Base):
    __tablename__ = "trusted_devices"

    id           = Column(String(36), primary_key=True)
    user_id      = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    token_hash   = Column(String(64),  nullable=False, unique=True)  # SHA-256 of raw cookie value
    device_name  = Column(String(200), nullable=True)                # user-agent or custom label
    created_at   = Column(DateTime, default=datetime.utcnow)
    expires_at   = Column(DateTime, nullable=False)
    last_used_at = Column(DateTime, nullable=True)


# ─────────────────────────────────────────────
# WebAuthn / Passkey Credentials (fingerprint, Face ID, Windows Hello)
# ─────────────────────────────────────────────

class WebAuthnCredential(Base):
    __tablename__ = "webauthn_credentials"

    id            = Column(String(36), primary_key=True)
    user_id       = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    credential_id = Column(Text, nullable=False, unique=True, index=True)  # base64url bytes
    public_key    = Column(Text, nullable=False)                            # base64 COSE public key
    sign_count    = Column(Integer, default=0)
    device_name   = Column(String(200), nullable=True)   # e.g. "Touch ID on iPhone"
    created_at    = Column(DateTime, default=datetime.utcnow)
    last_used_at  = Column(DateTime, nullable=True)


# ─────────────────────────────────────────────
# Platform Connections  (Late-API social accounts — persisted in DB)
# ─────────────────────────────────────────────

class PlatformConnection(Base):
    """
    Stores non-Meta social platform connections (Twitter, TikTok, LinkedIn,
    Threads, YouTube) that were previously only in client_connections.json.
    Living in the main database means they survive Railway redeploys.
    """
    __tablename__ = "platform_connections"

    id              = Column(String(36), primary_key=True)           # UUID
    client_id       = Column(String(100), nullable=False, index=True)  # matches ClientProfile.client_id
    platform        = Column(String(50),  nullable=False)              # e.g. "twitter", "tiktok"
    account_id      = Column(String(200), nullable=True)               # Late profile ID / account ID
    username        = Column(String(200), nullable=True)               # display username
    extra_json      = Column(Text,        nullable=True)               # any extra metadata as JSON
    connected_at    = Column(DateTime,    default=datetime.utcnow)
    updated_at      = Column(DateTime,    default=datetime.utcnow, onupdate=datetime.utcnow)


# ─────────────────────────────────────────────
# Scheduled Posts  (calendar data — persisted in DB, survives Railway redeploys)
# ─────────────────────────────────────────────

class ScheduledPost(Base):
    """
    Stores calendar scheduled posts in the main PostgreSQL database so they
    survive Railway container redeploys.  Previously stored only in ephemeral
    JSONL files at storage/scheduled_posts/{client_id}_posts.jsonl which were
    wiped on every deploy.
    """
    __tablename__ = "scheduled_posts"

    id              = Column(String(64), primary_key=True)                    # UUID or generated content ID
    client_id       = Column(String(100), nullable=False, index=True)         # matches ClientProfile.client_id
    platform        = Column(String(50),  nullable=False)                     # e.g. "instagram", "twitter"
    caption         = Column(Text,        nullable=True, default="")
    image_url       = Column(Text,        nullable=True, default="")
    content_type    = Column(String(50),  nullable=True, default="post")      # post/reel/story/carousel/thread/etc.
    scheduled_time  = Column(String(50),  nullable=True)                      # ISO datetime string
    topic           = Column(String(500), nullable=True, default="")
    seo_keywords    = Column(String(500), nullable=True, default="")
    auto_created    = Column(Boolean,     default=False)
    status          = Column(String(30),  default="scheduled")                # scheduled/posted/failed/cancelled
    created_at      = Column(DateTime,    default=datetime.utcnow)
    updated_at      = Column(DateTime,    default=datetime.utcnow, onupdate=datetime.utcnow)


# ─────────────────────────────────────────────
# Notifications  (persisted in main DB — survives Railway redeploys)
# ─────────────────────────────────────────────

class ClientNotification(Base):
    """
    Stores dashboard notifications (bell-icon alerts) in PostgreSQL so they
    persist across Railway container redeploys.  Previously stored only in
    ephemeral JSONL files at storage/notifications/ which were wiped on deploy.
    """
    __tablename__ = "client_notifications"

    id                = Column(String(64),  primary_key=True)                    # e.g. "notif_1234567890.123"
    client_id         = Column(String(100), nullable=False, index=True)          # matches ClientProfile.client_id
    notification_type = Column(String(50),  nullable=False, default="system")    # sale/lead/content_idea/system/etc.
    title             = Column(String(500), nullable=False)
    message           = Column(Text,        nullable=True, default="")
    priority          = Column(String(20),  nullable=False, default="medium")    # critical/high/medium/low
    read              = Column(Boolean,     default=False)
    metadata_json     = Column(Text,        nullable=True, default="{}")         # JSON: action_url, platform, etc.
    created_at        = Column(DateTime,    default=datetime.utcnow)
    read_at           = Column(DateTime,    nullable=True)
    cleared_at        = Column(DateTime,    nullable=True)                       # soft-delete: non-NULL = cleared; undo within 24 h


# ─────────────────────────────────────────────
# Client Knowledge Entries  (persisted in DB — survives Railway redeploys)
# ─────────────────────────────────────────────

class ClientKnowledgeEntry(Base):
    """
    Stores per-client knowledge base entries (business info, RAG source text)
    in PostgreSQL.  Previously stored only in ephemeral JSONL files at
    storage/knowledge/{client_id}/knowledge.jsonl which were wiped on deploy.
    The Qdrant vector index is rebuilt from these rows on startup.
    """
    __tablename__ = "client_knowledge_entries"

    id          = Column(String(64),  primary_key=True)                    # UUID or hash
    client_id   = Column(String(100), nullable=False, index=True)
    text        = Column(Text,        nullable=False)
    source      = Column(String(200), nullable=True, default="manual")     # manual/onboarding/research/upload
    category    = Column(String(200), nullable=True, default="")
    added_at    = Column(DateTime,    default=datetime.utcnow)


# ─────────────────────────────────────────────
# Growth Reports  (persisted in DB — survives Railway redeploys)
# ─────────────────────────────────────────────

class GrowthReport(Base):
    """
    Stores AI-generated growth hacking reports in PostgreSQL.
    Previously saved as JSON files at storage/growth_reports/{client_id}/*.json
    which were wiped on every Railway container redeploy.
    """
    __tablename__ = "growth_reports"

    id          = Column(String(64),  primary_key=True)             # report_id (e.g. uuid hex)
    client_id   = Column(String(100), nullable=False, index=True)
    goal        = Column(Text,        nullable=True, default="")
    report_json = Column(Text,        nullable=False)               # Full strategy JSON
    created_at  = Column(DateTime,    default=datetime.utcnow)


# ─────────────────────────────────────────────
# Growth Campaign Runs  (persisted in DB — survives Railway redeploys)
# ─────────────────────────────────────────────

class GrowthCampaignRun(Base):
    """
    Stores GrowthAgent campaign run results in PostgreSQL.
    Previously saved as JSON files at storage/growth_campaigns/{client_id}/*.json
    which were wiped on every Railway container redeploy.
    """
    __tablename__ = "growth_campaign_runs"

    id          = Column(String(64),  primary_key=True)             # run_id
    client_id   = Column(String(100), nullable=False, index=True)
    platform    = Column(String(50),  nullable=True, default="instagram")
    dry_run     = Column(Boolean,     default=True)
    result_json = Column(Text,        nullable=False)               # Full result JSON
    created_at  = Column(DateTime,    default=datetime.utcnow)


# ─────────────────────────────────────────────────────────────────
# Recommendation Actions  (followed / dismissed)
# ─────────────────────────────────────────────────────────────────

class RecommendationAction(Base):
    """
    Tracks which growth recommendations a client has acted on (followed or dismissed).
    Used to permanently exclude these accounts from future Claude prompts.
    """
    __tablename__ = "recommendation_actions"

    id          = Column(String(64),  primary_key=True)
    client_id   = Column(String(100), nullable=False, index=True)
    action      = Column(String(20),  nullable=False)               # "followed" | "dismissed"
    name        = Column(String(300), nullable=False)               # display name / @handle
    url         = Column(String(500), nullable=True)                # profile URL
    platform    = Column(String(50),  nullable=True)
    created_at  = Column(DateTime,    default=datetime.utcnow)


# ─────────────────────────────────────────────────────────────────
# Microsoft OAuth Tokens  (persisted in main DB)
# ─────────────────────────────────────────────────────────────────

class MicrosoftOAuthToken(Base):
    """
    Stores encrypted Microsoft (Outlook / Hotmail / Live) OAuth tokens.
    Uses Microsoft Identity Platform v2.0 with scopes openid email Mail.Read Mail.Send.
    """
    __tablename__ = "microsoft_oauth_tokens"

    id                   = Column(String(36), primary_key=True)
    client_profile_id    = Column(String(36), ForeignKey("client_profiles.id"),
                                  unique=True, nullable=False, index=True)
    email_address        = Column(String(255), nullable=False)
    access_token_enc     = Column(Text, nullable=False)         # Fernet-encrypted
    refresh_token_enc    = Column(Text, nullable=False)         # Fernet-encrypted
    token_expires_at     = Column(DateTime, nullable=True)      # When access token expires
    scopes               = Column(Text, nullable=True)
    created_at           = Column(DateTime, default=datetime.utcnow)
    updated_at           = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    client_profile       = relationship("ClientProfile", back_populates="microsoft_oauth_token")


# ─────────────────────────────────────────────────────────────────
# Email Threads  (persistent email conversation storage)
# ─────────────────────────────────────────────────────────────────

class EmailCategory(str, enum.Enum):
    lead    = "lead"
    support = "support"
    general = "general"
    spam    = "spam"

class EmailThreadStatus(str, enum.Enum):
    active   = "active"
    archived = "archived"
    resolved = "resolved"

class EmailThread(Base):
    """A conversation thread in the client's inbox."""
    __tablename__ = "email_threads"

    id                   = Column(String(64), primary_key=True)
    client_profile_id    = Column(String(36), ForeignKey("client_profiles.id"),
                                  nullable=False, index=True)
    external_thread_id   = Column(String(500), nullable=True, index=True)
    subject              = Column(Text, nullable=True)
    sender_email         = Column(String(255), nullable=True)
    sender_name          = Column(String(255), nullable=True)
    category             = Column(SAEnum(EmailCategory), default=EmailCategory.general)
    status               = Column(SAEnum(EmailThreadStatus), default=EmailThreadStatus.active)
    message_count        = Column(Integer, default=0)
    last_message_at      = Column(DateTime, nullable=True)
    created_at           = Column(DateTime, default=datetime.utcnow)
    updated_at           = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    client_profile       = relationship("ClientProfile", back_populates="email_threads")
    messages             = relationship("EmailMessageRecord", back_populates="thread",
                                        cascade="all, delete-orphan",
                                        order_by="EmailMessageRecord.received_at")


# ─────────────────────────────────────────────────────────────────
# Email Messages  (individual emails within a thread)
# ─────────────────────────────────────────────────────────────────

class DraftStatus(str, enum.Enum):
    none     = "none"       # outbound or no draft generated
    pending  = "pending"    # AI draft waiting for approval
    approved = "approved"   # user approved, about to send
    rejected = "rejected"   # user rejected the draft
    sent     = "sent"       # draft was sent

class EmailMessageRecord(Base):
    """A single email message (inbound or outbound) within a thread."""
    __tablename__ = "email_messages"

    id                   = Column(String(64), primary_key=True)
    thread_id            = Column(String(64), ForeignKey("email_threads.id"),
                                  nullable=False, index=True)
    client_profile_id    = Column(String(36), ForeignKey("client_profiles.id"),
                                  nullable=False, index=True)
    external_message_id  = Column(String(500), nullable=True, index=True)
    direction            = Column(String(10), nullable=False, default="inbound")  # inbound | outbound
    sender_email         = Column(String(255), nullable=True)
    sender_name          = Column(String(255), nullable=True)
    subject              = Column(Text, nullable=True)
    body_text            = Column(Text, nullable=True)
    body_html            = Column(Text, nullable=True)
    ai_category          = Column(String(30), nullable=True)    # lead, support, general, spam
    ai_draft_reply       = Column(Text, nullable=True)          # AI-generated reply text
    draft_status         = Column(SAEnum(DraftStatus), default=DraftStatus.none)
    received_at          = Column(DateTime, default=datetime.utcnow)
    created_at           = Column(DateTime, default=datetime.utcnow)

    thread               = relationship("EmailThread", back_populates="messages")


# ─────────────────────────────────────────────────────────────────
# Email Subscribers  (campaign recipient lists)
# ─────────────────────────────────────────────────────────────────

class SubscriberStatus(str, enum.Enum):
    active       = "active"
    unsubscribed = "unsubscribed"
    bounced      = "bounced"

class EmailSubscriber(Base):
    """An email subscriber for campaign sending."""
    __tablename__ = "email_subscribers"

    id                   = Column(String(64), primary_key=True)
    client_profile_id    = Column(String(36), ForeignKey("client_profiles.id"),
                                  nullable=False, index=True)
    email                = Column(String(255), nullable=False)
    name                 = Column(String(255), nullable=True, default="")
    tags                 = Column(Text, nullable=True, default="")        # comma-separated
    status               = Column(SAEnum(SubscriberStatus), default=SubscriberStatus.active)
    created_at           = Column(DateTime, default=datetime.utcnow)


# ─────────────────────────────────────────────────────────────────
# Email Campaigns  (plans + send state, persisted in DB)
# ─────────────────────────────────────────────────────────────────

class CampaignStatus(str, enum.Enum):
    draft   = "draft"
    queued  = "queued"
    sending = "sending"
    sent    = "sent"
    failed  = "failed"

class EmailCampaignRecord(Base):
    """An email campaign plan + execution record."""
    __tablename__ = "email_campaigns"

    id                   = Column(String(64), primary_key=True)
    client_profile_id    = Column(String(36), ForeignKey("client_profiles.id"),
                                  nullable=False, index=True)
    campaign_type        = Column(String(50), nullable=True)
    campaign_goal        = Column(String(50), nullable=True)
    target_segment       = Column(String(50), nullable=True)
    content_brief        = Column(Text, nullable=True)
    plan_json            = Column(Text, nullable=True)          # AI-generated plan JSON
    status               = Column(SAEnum(CampaignStatus), default=CampaignStatus.draft)
    total_recipients     = Column(Integer, default=0)
    sent_count           = Column(Integer, default=0)
    error_log            = Column(Text, nullable=True)
    created_at           = Column(DateTime, default=datetime.utcnow)
    updated_at           = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
