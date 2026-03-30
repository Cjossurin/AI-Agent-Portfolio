#!/usr/bin/env python3
"""Clear all scheduled posts for the admin profile (LOCAL SQLite)."""

import os

from database.db import SessionLocal, engine
from database.models import User, ScheduledPost, Base

# Initialize the database if it doesn't exist
Base.metadata.create_all(bind=engine)
print("✅ Database initialized")

db = SessionLocal()
try:
    admin_email = os.getenv("ADMIN_EMAIL")
    if not admin_email:
        raise RuntimeError("Set ADMIN_EMAIL in environment before running this script")

    # Find admin user
    admin_user = db.query(User).filter(
        User.email == admin_email
    ).first()
    
    if not admin_user:
        print("❌ Admin user not found locally")
        print("   Hint: Run `python create_admin.py` to create the admin account first")
    else:
        admin_profile = admin_user.client_profile
        if not admin_profile:
            print("❌ Admin user has no profile")
        else:
            client_id = admin_profile.client_id
            print(f"✅ Found admin: {admin_user.full_name} ({admin_user.email})")
            print(f"   Client: {admin_profile.business_name} (ID: {client_id})")
            
            # Count posts
            count = db.query(ScheduledPost).filter(
                ScheduledPost.client_id == client_id
            ).count()
            print(f"   Posts in calendar: {count}")
            
            # Delete all scheduled posts
            if count > 0:
                db.query(ScheduledPost).filter(
                    ScheduledPost.client_id == client_id
                ).delete()
                db.commit()
                print(f"✅ Deleted {count} scheduled post(s) locally")
            else:
                print("ℹ️  Calendar already empty locally")
finally:
    db.close()
