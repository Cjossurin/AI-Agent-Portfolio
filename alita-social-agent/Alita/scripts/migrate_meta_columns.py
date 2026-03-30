"""
One-time migration: add Meta OAuth columns to client_profiles and create meta_oauth_tokens table.
Safe to run multiple times (checks before altering).
"""
import os, sys
from dotenv import load_dotenv
load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./automation.db")
IS_POSTGRES = DATABASE_URL.startswith("postgresql")

from sqlalchemy import create_engine, text, inspect

connect_args = {"check_same_thread": False} if not IS_POSTGRES else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args)

NEW_COLS = [
    ("meta_user_id",          "VARCHAR(64)"),
    ("meta_ig_account_id",    "VARCHAR(64)"),
    ("meta_ig_username",      "VARCHAR(200)"),
    ("meta_facebook_page_id", "VARCHAR(64)"),
    ("meta_connected_at",     "TIMESTAMP" if IS_POSTGRES else "DATETIME"),
]

with engine.connect() as conn:
    inspector = inspect(engine)
    existing = {c["name"] for c in inspector.get_columns("client_profiles")}

    for col_name, col_type in NEW_COLS:
        if col_name not in existing:
            conn.execute(text(f"ALTER TABLE client_profiles ADD COLUMN {col_name} {col_type}"))
            print(f"  ✅ Added column client_profiles.{col_name}")
        else:
            print(f"  ℹ️  Column client_profiles.{col_name} already exists")

    conn.commit()

# Create meta_oauth_tokens table if missing
from database.models import MetaOAuthToken  # noqa — registers with Base
from database.db import Base
MetaOAuthToken.__table__.create(bind=engine, checkfirst=True)
print("  ✅ meta_oauth_tokens table ready")

print("\nMigration complete.")
