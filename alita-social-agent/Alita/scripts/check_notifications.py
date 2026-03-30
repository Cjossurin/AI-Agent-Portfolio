"""
Diagnostic script: check what notifications exist in the database for the
default client and why they may not be showing on the notifications page.

Run with:  .venv\Scripts\python.exe scripts/check_notifications.py
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from database.db import init_db, SessionLocal, DATABASE_URL
from database.models import ClientNotification, ClientProfile, GrowthReport

print(f"\n{'='*70}")
print(f"DATABASE_URL = {DATABASE_URL[:30]}...{DATABASE_URL[-15:]}" if len(DATABASE_URL) > 50 else f"DATABASE_URL = {DATABASE_URL}")
print(f"{'='*70}\n")

init_db()
db = SessionLocal()

# 1. Find the client profile
profiles = db.query(ClientProfile).all()
print(f"--- Client Profiles ({len(profiles)}) ---")
for p in profiles:
    print(f"  client_id={p.client_id!r}  user_id={p.user_id!r}  niche={p.niche!r}  plan={p.plan_tier!r}")
print()

# 2. For each client, show ALL notifications (including cleared)
for p in profiles:
    cid = p.client_id
    all_notifs = (
        db.query(ClientNotification)
        .filter(ClientNotification.client_id == cid)
        .order_by(ClientNotification.created_at.desc())
        .all()
    )
    visible = [n for n in all_notifs if n.cleared_at is None]
    cleared = [n for n in all_notifs if n.cleared_at is not None]

    print(f"--- Notifications for client_id={cid!r} ---")
    print(f"  Total in DB: {len(all_notifs)}   Visible: {len(visible)}   Cleared: {len(cleared)}")
    print()

    if all_notifs:
        for n in all_notifs:
            status = "CLEARED" if n.cleared_at else ("READ" if n.read else "UNREAD")
            cleared_info = f"  cleared_at={n.cleared_at}" if n.cleared_at else ""
            print(f"  [{status:>7}] {n.notification_type:<20} | {n.title[:60]:<60} | {n.created_at}{cleared_info}")
        print()
    else:
        print("  (none)\n")

# 3. Check GrowthReport table
for p in profiles:
    cid = p.client_id
    reports = (
        db.query(GrowthReport)
        .filter(GrowthReport.client_id == cid)
        .order_by(GrowthReport.created_at.desc())
        .all()
    )
    print(f"--- Growth Reports for client_id={cid!r}: {len(reports)} ---")
    for r in reports:
        print(f"  id={r.id}  goal={r.goal[:50] if r.goal else ''}  created_at={r.created_at}")
    print()

# 4. Check JSONL fallback files
from pathlib import Path
notif_dir = Path("storage/notifications")
if notif_dir.exists():
    print(f"--- JSONL fallback files in {notif_dir} ---")
    for f in notif_dir.glob("*.jsonl"):
        lines = open(f, encoding="utf-8").readlines()
        print(f"  {f.name}: {len(lines)} entries")
else:
    print(f"--- No JSONL fallback directory ({notif_dir}) ---")

db.close()
print("\nDone.")
