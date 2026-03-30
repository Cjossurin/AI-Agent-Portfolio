 """
seed_railway_meta.py — Run this ONCE in railway shell after deploying.

Reads the Meta OAuth tokens from alita_oauth.db (if present) and migrates them
to the main PostgreSQL database so they survive future Railway redeploys.

Usage (in railway shell):
    cd /app
    python seed_railway_meta.py
"""
import os, sys, json, sqlite3
from pathlib import Path
from dotenv import load_dotenv
load_dotenv()

# ── 1. Run migrations first ───────────────────────────────────────────────────
print("Running DB migrations...")
from database.db import init_db, SessionLocal
init_db()
print()

# ── 2. Read tokens from alita_oauth.db ───────────────────────────────────────
OAUTH_DB = Path(__file__).parent / "database" / "alita_oauth.db"
if not OAUTH_DB.exists():
    print(f"alita_oauth.db not found at {OAUTH_DB}")
    print("No tokens to migrate. You will need to re-OAuth on Railway.")
    sys.exit(0)

print(f"Found alita_oauth.db at {OAUTH_DB}")
c = sqlite3.connect(str(OAUTH_DB))
c.row_factory = sqlite3.Row
rows = c.execute("SELECT * FROM user_tokens ORDER BY updated_at DESC").fetchall()
account_map = {r["user_id"]: dict(r) for r in c.execute("SELECT * FROM account_map").fetchall()}
c.close()

if not rows:
    print("No token rows found in alita_oauth.db.")
    sys.exit(0)

print(f"Found {len(rows)} token row(s)")

# ── 3. Migrate tokens to main DB ─────────────────────────────────────────────
import uuid
from datetime import datetime
from api.token_manager import decrypt_value, encrypt_value
from database.models import ClientProfile, MetaOAuthToken

db = SessionLocal()
try:
    profiles = db.query(ClientProfile).all()
    print(f"Found {len(profiles)} client profile(s)")

    for row in rows:
        meta_user_id = row["user_id"]
        acc = account_map.get(meta_user_id, {})
        ig_account_id = row["instagram_account_id"] or acc.get("instagram_account_id")
        facebook_page_id = row["facebook_page_id"] or acc.get("facebook_page_id")
        ig_username = acc.get("instagram_username")

        print(f"\n  Token for meta_user_id={meta_user_id}")
        print(f"  ig_account_id={ig_account_id}, fb_page_id={facebook_page_id}")

        # Decrypt then re-encrypt to ensure consistent key usage
        try:
            plaintext = decrypt_value(row["access_token_encrypted"])
        except Exception as e:
            print(f"  ⚠️  Could not decrypt token: {e} — skipping")
            continue

        # For single-client setup, match to demo_client (or whichever profile exists)
        # We match by ig_account_id if set, else first profile
        matched_profile = None
        if ig_account_id:
            for p in profiles:
                if p.meta_ig_account_id == ig_account_id:
                    matched_profile = p
                    break
        if not matched_profile and profiles:
            # Default: assign to first (or only) profile that has no Meta connection yet
            for p in profiles:
                if not p.meta_user_id:
                    matched_profile = p
                    break
        if not matched_profile and profiles:
            matched_profile = profiles[0]

        if not matched_profile:
            print("  ⚠️  No matching profile found — skipping")
            continue

        print(f"  Matched profile: {matched_profile.client_id}")

        # Update profile columns
        matched_profile.meta_user_id          = meta_user_id
        matched_profile.meta_ig_account_id    = ig_account_id
        matched_profile.meta_ig_username      = ig_username
        matched_profile.meta_facebook_page_id = facebook_page_id
        matched_profile.meta_connected_at     = datetime.utcnow()

        # Upsert MetaOAuthToken
        tok_row = db.query(MetaOAuthToken).filter(
            MetaOAuthToken.client_profile_id == matched_profile.id
        ).first()
        enc = encrypt_value(plaintext)
        if tok_row:
            tok_row.meta_user_id     = meta_user_id
            tok_row.access_token_enc = enc
            tok_row.scopes           = row["scopes"] or ""
            tok_row.is_long_lived    = bool(row["is_long_lived"])
            tok_row.expires_at       = str(row["expires_at"]) if row["expires_at"] else None
            tok_row.ig_account_id    = ig_account_id
            tok_row.facebook_page_id = facebook_page_id
            tok_row.updated_at       = datetime.utcnow()
        else:
            tok_row = MetaOAuthToken(
                id=str(uuid.uuid4()),
                client_profile_id=matched_profile.id,
                meta_user_id=meta_user_id,
                access_token_enc=enc,
                token_type=row["token_type"] or "bearer",
                scopes=row["scopes"] or "",
                is_long_lived=bool(row["is_long_lived"]),
                expires_at=str(row["expires_at"]) if row["expires_at"] else None,
                ig_account_id=ig_account_id,
                facebook_page_id=facebook_page_id,
            )
            db.add(tok_row)

    db.commit()
    print("\n✅ Migration complete! Meta tokens are now in PostgreSQL.")
    print("   Connection status will show correctly and survive future deploys.")

except Exception as e:
    db.rollback()
    print(f"\n❌ Error: {e}")
    import traceback; traceback.print_exc()
finally:
    db.close()
