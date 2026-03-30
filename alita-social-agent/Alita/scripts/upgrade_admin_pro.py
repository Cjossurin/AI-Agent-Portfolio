"""
One-time script: Upgrade an admin account to Pro plan.
Works with both SQLite (local) and PostgreSQL (Railway).
Run with: python upgrade_admin_pro.py
"""
import os
from dotenv import load_dotenv
load_dotenv()

from database.db import SessionLocal, init_db
from database.models import User, ClientProfile

# Ensure tables/migrations are up to date
init_db()

db = SessionLocal()
ADMIN_EMAIL = os.getenv("ADMIN_EMAIL")

if not ADMIN_EMAIL:
    raise RuntimeError("Set ADMIN_EMAIL in environment before running this script")

try:
    user = db.query(User).filter(User.email == ADMIN_EMAIL).first()
    if not user:
        print(f"User '{ADMIN_EMAIL}' not found.")
        db.close()
        exit(1)

    print(f"Found user: id={user.id}  name={user.full_name}  email={user.email}")

    profile = db.query(ClientProfile).filter(ClientProfile.user_id == user.id).first()
    if not profile:
        print("No ClientProfile found for this user.")
        db.close()
        exit(1)

    print(f"Current plan: tier={profile.plan_tier}  status={profile.plan_status}  client_id={profile.client_id}")

    profile.plan_tier   = "pro"
    profile.plan_status = "active"
    db.commit()

    db.refresh(profile)
    print(f"\n✅ Plan upgraded:  tier={profile.plan_tier}  status={profile.plan_status}")

except Exception as e:
    db.rollback()
    print(f"Error: {e}")
    import traceback; traceback.print_exc()
finally:
    db.close()
