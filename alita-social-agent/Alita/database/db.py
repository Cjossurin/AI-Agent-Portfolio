"""
database/db.py — SQLAlchemy engine + session factory
Works with SQLite (local dev) and PostgreSQL (production Railway).
"""
import os
import sys
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./automation.db")

# Railway gives postgres:// but SQLAlchemy 2.x requires postgresql://
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

# SQLite needs check_same_thread=False
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

_engine_kwargs = dict(connect_args=connect_args)
if DATABASE_URL.startswith("postgresql"):
    _engine_kwargs["pool_size"] = 5
    _engine_kwargs["max_overflow"] = 10
    _engine_kwargs["pool_pre_ping"] = True

engine = create_engine(DATABASE_URL, **_engine_kwargs)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    """FastAPI dependency — yields a DB session and closes it after use."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """Create all tables if they don't exist. Call once at app startup."""
    from database.models import (  # noqa: F401
        User, ClientProfile, DeepResearchRequest, PasswordResetToken,
        MetaOAuthToken, GmailOAuthToken, PlatformConnection, ScheduledPost,
        ClientNotification, ClientKnowledgeEntry,
        EmailIMAPConnection, EmailVerificationToken, TwoFactorOTP,
        TrustedDevice, WebAuthnCredential,
        GrowthReport, GrowthCampaignRun,
        MicrosoftOAuthToken, EmailThread, EmailMessageRecord,
        EmailSubscriber, EmailCampaignRecord,
    )
    Base.metadata.create_all(bind=engine)

    # Apply additive column migrations (safe to re-run — checks before altering)
    _run_migrations()
    print("Database tables initialized.")


def _run_migrations():
    """Add any new columns / tables that don't exist yet. Idempotent."""
    from sqlalchemy import inspect as _inspect, text as _text
    IS_PG = DATABASE_URL.startswith("postgresql")
    _ts_type = "TIMESTAMP" if IS_PG else "DATETIME"

    _NEW_COLS = [
        ("client_profiles", "meta_user_id",          "VARCHAR(64)"),
        ("client_profiles", "meta_ig_account_id",    "VARCHAR(64)"),
        ("client_profiles", "meta_ig_username",      "VARCHAR(200)"),
        ("client_profiles", "meta_facebook_page_id", "VARCHAR(64)"),
        ("client_profiles", "meta_connected_at",     _ts_type),
        ("client_profiles", "tone_configured",       "BOOLEAN DEFAULT FALSE"),
        # ── Tone / Style / Voice persistence ────────────────────────
        ("client_profiles", "tone_preferences_json",     "TEXT"),
        ("client_profiles", "normalized_samples_text",   "TEXT"),
        ("client_profiles", "creative_preferences_json", "TEXT"),
        ("client_profiles", "voice_profile_json",        "TEXT"),
        ("client_profiles", "scheduler_config_json",     "TEXT"),
        ("client_profiles", "auto_reply_settings_json",  "TEXT"),
        ("client_profiles", "notification_email_prefs_json",  "TEXT"),
        # ── Email AI compliance ─────────────────────────────────────
        ("client_profiles", "email_ai_agreed_at",        _ts_type),
        ("client_profiles", "email_ai_agreement_ip",     "VARCHAR(50)"),
        # ── Notifications: soft-delete & read tracking ──────────────
        ("client_notifications", "read_at",    _ts_type),
        ("client_notifications", "cleared_at", _ts_type),
    ]

    try:
        with engine.connect() as _conn:
            _inspector = _inspect(engine)
            for _table, _col, _col_type in _NEW_COLS:
                try:
                    _existing = {c["name"] for c in _inspector.get_columns(_table)}
                    if _col not in _existing:
                        _conn.execute(_text(f"ALTER TABLE {_table} ADD COLUMN {_col} {_col_type}"))
                        print(f"  [migration] Added {_table}.{_col}")
                except Exception as _ce:
                    pass  # Column may already exist or table may not exist yet
            _conn.commit()
    except Exception as _me:
        print(f"  [migration] Warning: {_me}")
