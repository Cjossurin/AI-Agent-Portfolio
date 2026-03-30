#!/usr/bin/env python3
"""Clear all scheduled posts for the admin profile on Railway (PostgreSQL)."""

import os
import sys

# Add project root to path
sys.path.insert(0, os.path.dirname(__file__))

from database.db import SessionLocal
from database.models import User, ScheduledPost

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
        print("❌ Admin user not found on Railway")
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
                print(f"✅ Deleted {count} scheduled post(s) on Railway")
            else:
                print("ℹ️  Calendar already empty on Railway")
    
    db.close()

except Exception as e:
    print(f"❌ Error: {e}")
    import traceback
    traceback.print_exc()
    exit(1)
