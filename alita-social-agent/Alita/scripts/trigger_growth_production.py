"""
Trigger Growth Agent on PRODUCTION (app.nexarilyai.com)
=======================================================
1. Logs in to get the alita_token cookie
2. Calls POST /api/growth/admin-test
3. Waits and checks for notifications
"""
import os
import sys
import time
import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv
load_dotenv()

BASE_URL = "https://app.nexarilyai.com"
EMAIL = os.getenv("ADMIN_EMAIL", "")
PASSWORD = os.getenv("ADMIN_PASSWORD", "")

if not EMAIL or not PASSWORD:
    # Try to get from env or ask
    print("ERROR: Set ADMIN_EMAIL and ADMIN_PASSWORD in .env to run this script")
    print("Add: ADMIN_EMAIL=you@example.com")
    print("Add: ADMIN_PASSWORD=your_password_here")
    sys.exit(1)

session = requests.Session()

# ── 1. Login ────────────────────────────────────────────────────────
print(f"\n{'='*60}")
print(f"  TRIGGERING GROWTH AGENT ON PRODUCTION")
print(f"  {BASE_URL}")
print(f"{'='*60}\n")

print(f"🔐 Logging in as {EMAIL}...")
login_resp = session.post(
    f"{BASE_URL}/account/login",
    data={"email": EMAIL, "password": PASSWORD, "next": "/dashboard"},
    allow_redirects=False,  # Don't follow redirect, just grab cookie
)

# The login returns a 303 redirect with Set-Cookie
if login_resp.status_code in (303, 302):
    print(f"   ✅ Login redirect: {login_resp.headers.get('location', 'unknown')}")
else:
    print(f"   ❌ Login failed: HTTP {login_resp.status_code}")
    print(f"   Response: {login_resp.text[:500]}")
    sys.exit(1)

# Check we got the cookie
token = session.cookies.get("alita_token")
if not token:
    print("   ❌ No alita_token cookie received!")
    print(f"   Cookies: {dict(session.cookies)}")
    # It might be in Set-Cookie header
    print(f"   Set-Cookie headers: {login_resp.headers.get('set-cookie', 'none')}")
    sys.exit(1)

print(f"   ✅ Got auth token: {token[:20]}...")

# ── 2. Verify we're authenticated ──────────────────────────────────
print(f"\n📋 Verifying auth...")
dash_resp = session.get(f"{BASE_URL}/dashboard", allow_redirects=False)
if dash_resp.status_code == 200:
    print(f"   ✅ Dashboard accessible (HTTP 200)")
elif dash_resp.status_code in (302, 303):
    loc = dash_resp.headers.get("location", "")
    if "login" in loc:
        print(f"   ❌ Redirected to login — auth failed")
        sys.exit(1)
    else:
        print(f"   ✅ Redirect to: {loc}")
else:
    print(f"   ⚠️ Dashboard returned HTTP {dash_resp.status_code}")

# ── 3. Fire the admin-test endpoint ────────────────────────────────
print(f"\n🚀 Triggering POST /api/growth/admin-test ...")
test_resp = session.post(f"{BASE_URL}/api/growth/admin-test")
print(f"   HTTP {test_resp.status_code}")

if test_resp.status_code == 200:
    data = test_resp.json()
    print(f"   ✅ {data.get('message', 'OK')}")
    report_id = data.get("report_id")
    print(f"   📊 Report ID: {report_id}")
elif test_resp.status_code == 401:
    print(f"   ❌ Unauthorized — cookie may not be valid for production")
    print(f"   Response: {test_resp.text[:500]}")
    sys.exit(1)
elif test_resp.status_code == 403:
    print(f"   ❌ Forbidden — user is not admin in production DB")
    print(f"   Response: {test_resp.text[:500]}")
    sys.exit(1)
else:
    print(f"   ❌ Unexpected: {test_resp.text[:500]}")
    sys.exit(1)

# ── 4. Wait and check notifications ────────────────────────────────
print(f"\n⏳ Waiting 90 seconds for background tasks to complete...")
for i in range(18):
    time.sleep(5)
    remaining = 90 - (i + 1) * 5
    if remaining > 0 and remaining % 15 == 0:
        print(f"   ... {remaining}s remaining")

# Check notifications via API
print(f"\n📬 Checking notifications...")
notif_resp = session.get(f"{BASE_URL}/api/notifications")
if notif_resp.status_code == 200:
    notifs = notif_resp.json()
    if isinstance(notifs, dict):
        items = notifs.get("notifications", notifs.get("items", []))
        unread = notifs.get("unread_count", "?")
    else:
        items = notifs
        unread = len([n for n in items if not n.get("is_read")])
    
    print(f"   📊 Total notifications returned: {len(items)}")
    print(f"   🔴 Unread: {unread}")
    print()
    
    for n in items[:20]:
        ntype = n.get("notification_type", n.get("type", "?"))
        title = n.get("title", "?")
        priority = n.get("priority", "?")
        created = n.get("created_at", "?")
        print(f"   📩 [{ntype}] {title}")
        print(f"      Priority: {priority} | {created}")
else:
    print(f"   ❌ Failed to fetch notifications: HTTP {notif_resp.status_code}")
    print(f"   {notif_resp.text[:300]}")

# ── 5. Check the growth report ──────────────────────────────────────
print(f"\n📊 Checking growth reports...")
reports_resp = session.get(f"{BASE_URL}/api/growth/reports")
if reports_resp.status_code == 200:
    reports = reports_resp.json()
    if isinstance(reports, list):
        print(f"   📈 Total reports: {len(reports)}")
        for r in reports[:5]:
            print(f"   📄 {r.get('report_id', '?')} | {r.get('created_at', '?')}")
    else:
        print(f"   Response: {str(reports)[:300]}")
else:
    print(f"   HTTP {reports_resp.status_code}: {reports_resp.text[:300]}")

print(f"\n{'='*60}")
print(f"  DONE — Check your dashboard at {BASE_URL}/dashboard")
print(f"  Notifications should appear in the bell icon 🔔")
print(f"{'='*60}\n")
