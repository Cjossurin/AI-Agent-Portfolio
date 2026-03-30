"""
Initialize admin account and demo profile if they don't exist.
Run automatically during Railway startup.
"""
import os
import sys
import uuid
from pathlib import Path

# Add workspace to path
sys.path.insert(0, str(Path(__file__).parent))
os.environ.setdefault("DATABASE_URL", "sqlite:///./automation.db")

# Normalize Railway's postgres:// to postgresql:// for SQLAlchemy 2.x
_db_url = os.getenv("DATABASE_URL", "sqlite:///./automation.db")
if _db_url.startswith("postgres://"):
    _db_url = _db_url.replace("postgres://", "postgresql://", 1)
    os.environ["DATABASE_URL"] = _db_url

from database.db import Base, engine, get_db, init_db
from database.models import User, ClientProfile, OnboardingStatus, OnboardingMethod

# Ensure ALL tables exist (imports every model via init_db)
init_db()

# Run additive column migrations on every boot (idempotent)
def _run_startup_migrations():
    from sqlalchemy import inspect as _inspect, text as _text
    DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./automation.db")
    IS_PG = DATABASE_URL.startswith("postgresql")
    _ts = "TIMESTAMP" if IS_PG else "DATETIME"
    _cols = [
        ("users", "mfa_enabled",   "BOOLEAN DEFAULT FALSE"),
        ("users", "mfa_method",    "VARCHAR(20)"),
        ("users", "mfa_secret",    "VARCHAR(100)"),
        ("users", "phone_number",  "VARCHAR(30)"),
        ("client_profiles", "meta_user_id",          "VARCHAR(64)"),
        ("client_profiles", "meta_ig_account_id",    "VARCHAR(64)"),
        ("client_profiles", "meta_ig_username",      "VARCHAR(200)"),
        ("client_profiles", "meta_facebook_page_id", "VARCHAR(64)"),
        ("client_profiles", "meta_connected_at",     _ts),
        ("client_profiles", "onboarding_step",        "INTEGER DEFAULT 0"),
        ("client_profiles", "email_ai_agreed_at",      _ts),
        ("client_profiles", "email_ai_agreement_ip",   "VARCHAR(50)"),
        ("client_profiles", "growth_interests_json",   "TEXT"),
    ]
    try:
        with engine.connect() as _conn:
            _insp = _inspect(engine)
            for _tbl, _col, _col_type in _cols:
                try:
                    _existing = {c["name"] for c in _insp.get_columns(_tbl)}
                    if _col not in _existing:
                        _conn.execute(_text(f"ALTER TABLE {_tbl} ADD COLUMN {_col} {_col_type}"))
                        print(f"  [migration] Added {_tbl}.{_col}")
                except Exception:
                    pass
            _conn.commit()
        try:
            from database.models import MetaOAuthToken
            MetaOAuthToken.__table__.create(bind=engine, checkfirst=True)
        except Exception:
            pass
        try:
            from database.models import GmailOAuthToken
            GmailOAuthToken.__table__.create(bind=engine, checkfirst=True)
        except Exception:
            pass
        try:
            from database.models import PlatformConnection
            PlatformConnection.__table__.create(bind=engine, checkfirst=True)
            print("  [migration] platform_connections table ensured")
        except Exception:
            pass
        # Rename old demo_client → default_client  (one-time migration)
        try:
            _conn.execute(_text(
                "UPDATE client_profiles SET client_id = 'default_client' "
                "WHERE client_id = 'demo_client'"
            ))
            _conn.execute(_text(
                "UPDATE platform_connections SET client_id = 'default_client' "
                "WHERE client_id = 'demo_client'"
            ))
            _conn.commit()
        except Exception:
            pass  # tables may not exist yet

        # Widen scheduled_posts.id from VARCHAR(36) to VARCHAR(64) if needed
        try:
            if IS_PG:
                _conn.execute(_text(
                    "ALTER TABLE scheduled_posts ALTER COLUMN id TYPE VARCHAR(64)"
                ))
                _conn.commit()
                print("  [migration] Widened scheduled_posts.id to VARCHAR(64)")
        except Exception:
            pass  # column may already be correct size or table may not exist

    except Exception as _me:
        print(f"  [migration] Warning: {_me}")

_run_startup_migrations()


def init_admin():
    """Create admin user if missing, and always ensure they are on Pro plan."""
    from passlib.context import CryptContext
    pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
    db = next(get_db())
    try:
        admin_email = os.getenv("ADMIN_EMAIL")
        admin_password = os.getenv("ADMIN_PASSWORD")
        admin_name     = os.getenv("ADMIN_NAME",     "Admin")

        if not admin_email or not admin_password:
            print("Skipping admin bootstrap: set ADMIN_EMAIL and ADMIN_PASSWORD in environment")
            return

        existing = db.query(User).filter(User.email == admin_email).first()
        if existing:
            print(f"Admin account exists: {admin_email}")
            profile = db.query(ClientProfile).filter(
                ClientProfile.user_id == existing.id
            ).first()
            if not profile:
                profile = ClientProfile(
                    id=str(uuid.uuid4()),
                    user_id=existing.id,
                    client_id="default_client",
                    business_name="Nexarily AI",
                    onboarding_status=OnboardingStatus.complete,
                    rag_ready=True,
                    plan_tier="pro",
                    plan_status="active",
                )
                db.add(profile)
                db.commit()
                print(f"  Created Pro profile for {admin_email}")
            else:
                if profile.plan_tier != "pro":
                    profile.plan_tier   = "pro"
                    profile.plan_status = "active"
                    db.commit()
                    print(f"  Upgraded {admin_email} to Pro")
                else:
                    print(f"  {admin_email} is already Pro")
            return

        admin = User(
            id=str(uuid.uuid4()),
            email=admin_email,
            password_hash=pwd_context.hash(admin_password),
            full_name=admin_name,
            is_admin=True,
            is_active=True,
        )
        db.add(admin)
        db.flush()

        profile = ClientProfile(
            id=str(uuid.uuid4()),
            user_id=admin.id,
            client_id="default_client",
            business_name="Nexarily AI",
            onboarding_status=OnboardingStatus.complete,
            rag_ready=True,
            plan_tier="pro",
            plan_status="active",
        )
        db.add(profile)
        db.commit()
        print(f"Created admin account: {admin_email} (Pro plan)")
    except Exception as e:
        print(f"Admin init error: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    init_admin()