#!/usr/bin/env python3
"""
Bootstrap script — creates the first admin user.

Usage:
    python create_admin.py

Reads ADMIN_EMAIL and ADMIN_PASSWORD from .env (or environment).
If an admin with that email already exists, it will just promote them.
"""

import os
import sys
from dotenv import load_dotenv

load_dotenv()

ADMIN_EMAIL    = os.getenv("ADMIN_EMAIL")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD")
ADMIN_NAME     = os.getenv("ADMIN_NAME", "Admin")

if not ADMIN_EMAIL or not ADMIN_PASSWORD:
    print("❌  ADMIN_EMAIL and ADMIN_PASSWORD must be set in .env")
    print("    Add these two lines to your .env file:")
    print("    ADMIN_EMAIL=you@example.com")
    print("    ADMIN_PASSWORD=your_secure_password")
    sys.exit(1)

# Import after env is loaded so DATABASE_URL is available
from database.db import init_db, SessionLocal
from database.models import User
from api.auth_routes import hash_password
import uuid

init_db()  # ensure tables exist

db = SessionLocal()
try:
    existing = db.query(User).filter(User.email == ADMIN_EMAIL.strip().lower()).first()

    if existing:
        if not existing.is_admin:
            existing.is_admin = True
            db.commit()
            print(f"✅  Promoted existing user '{ADMIN_EMAIL}' to admin.")
        else:
            print(f"ℹ️   Admin user '{ADMIN_EMAIL}' already exists — nothing to do.")
    else:
        admin = User(
            id           = str(uuid.uuid4()),
            email        = ADMIN_EMAIL.strip().lower(),
            password_hash= hash_password(ADMIN_PASSWORD),
            full_name    = ADMIN_NAME,
            is_admin     = True,
            is_active    = True,
        )
        db.add(admin)
        db.commit()
        print(f"✅  Admin user created!")
        print(f"    Email:    {ADMIN_EMAIL}")
        print(f"    Login at: /account/login")
finally:
    db.close()
