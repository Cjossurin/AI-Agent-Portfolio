"""
One-time migration: add cleared_at column to client_notifications.
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

COL_NAME = "cleared_at"
COL_TYPE = "TIMESTAMP" if IS_POSTGRES else "DATETIME"
TABLE    = "client_notifications"

with engine.connect() as conn:
    inspector = inspect(engine)

    # Check table exists first
    if TABLE not in inspector.get_table_names():
        print(f"[migrate] Table '{TABLE}' does not exist yet — nothing to do.")
        sys.exit(0)

    existing = {c["name"] for c in inspector.get_columns(TABLE)}

    if COL_NAME in existing:
        print(f"[migrate] Column '{COL_NAME}' already exists on '{TABLE}' — skipping.")
    else:
        conn.execute(text(
            f'ALTER TABLE {TABLE} ADD COLUMN {COL_NAME} {COL_TYPE} DEFAULT NULL'
        ))
        conn.commit()
        print(f"[migrate] Added column '{COL_NAME}' ({COL_TYPE}) to '{TABLE}'.")

print("[migrate] Done.")
