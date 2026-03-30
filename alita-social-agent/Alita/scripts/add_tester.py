"""
Add your personal Facebook account as a tester in the Meta app.

This allows you to receive webhooks in development mode immediately,
without waiting for app review.

You just need your Facebook User ID.
"""

import os
import requests
from dotenv import load_dotenv

load_dotenv()

META_APP_ID = os.getenv("META_APP_ID") or os.getenv("INSTAGRAM_APP_ID")
META_APP_SECRET = os.getenv("META_APP_SECRET") or os.getenv("INSTAGRAM_APP_SECRET")
API_VERSION = "v22.0"
BASE = f"https://graph.facebook.com/{API_VERSION}"


def get_app_access_token():
    """Get an app access token using client credentials."""
    r = requests.get(f"{BASE}/oauth/access_token", params={
        "client_id": META_APP_ID,
        "client_secret": META_APP_SECRET,
        "grant_type": "client_credentials",
    })
    data = r.json()
    if "access_token" in data:
        return data["access_token"]
    else:
        print(f"❌ Failed: {data}")
        return None


def get_your_user_id():
    """Get your personal Facebook User ID."""
    print("\n" + "="*60)
    print("🔍 Getting Your Facebook User ID")
    print("="*60)
    
    print("\n📱 To find your Facebook User ID:")
    print("  1. Go to https://www.facebook.com/me")
    print("  2. The URL will show: facebook.com/[YOUR_USER_ID]")
    print("  3. Copy that number")
    print("\nOr visit: https://findmyfbid.com")
    
    user_id = input("\n👤 Enter your Facebook User ID: ").strip()
    
    if not user_id or not user_id.isdigit():
        print("❌ Invalid user ID")
        return None
    
    return user_id


def add_user_as_tester(user_id: str, app_token: str):
    """Add a user as a tester of the app."""
    print("\n" + "="*60)
    print("➕ Adding User as App Tester")
    print("="*60)
    
    url = f"{BASE}/{META_APP_ID}/testers"
    params = {
        "user": user_id,
        "access_token": app_token
    }
    
    print(f"\n📡 POST {url}")
    print(f"   user: {user_id}")
    
    r = requests.post(url, params=params)
    data = r.json()
    
    if r.status_code == 200 and data.get("success"):
        print(f"\n✅ SUCCESS! User {user_id} is now a tester!")
        print("\n🎉 You can now:")
        print("   1. Comment on the Facebook Page from your personal account")
        print("   2. Webhooks will fire immediately (in dev mode)")
        print("   3. The server will reply automatically")
        return True
    else:
        error = data.get("error", data)
        print(f"\n❌ Failed: {error}")
        
        if "already" in str(error).lower():
            print("\n💡 You might already be a tester!")
        
        return False


def main():
    print("\n" + "🧪 "*20)
    print("ADD YOURSELF AS APP TESTER (Development Mode)")
    print("🧪 "*20)
    
    print("\n📝 This will add your personal Facebook account as a tester.")
    print("   Then you can immediately test comment webhooks.")
    
    # Get app token
    app_token = get_app_access_token()
    if not app_token:
        print("\n❌ Could not get app access token")
        return
    
    print(f"\n✅ Got app access token: {app_token[:20]}...")
    
    # Get user ID
    user_id = get_your_user_id()
    if not user_id:
        return
    
    # Add as tester
    success = add_user_as_tester(user_id, app_token)
    
    if success:
        print("\n" + "="*60)
        print("✨ NEXT STEPS")
        print("="*60)
        print("""
1. Go to your Facebook Page: facebook.com/[YourPageName]
2. Create a post (or use existing)
3. Comment on it from your personal account
4. Wait 5-10 seconds
5. Check if the bot replied automatically!

If it worked:
  ✅ Comments are working in dev mode!
  ✅ No need to wait for app review
  ✅ This is safe for testing

To make it production-ready (LIVE mode):
  - You'll need to submit the app for review
  - This typically takes 1-3 weeks
  - Or proceed with dev mode for now
        """)


if __name__ == "__main__":
    main()
