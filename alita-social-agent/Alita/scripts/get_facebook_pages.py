"""
Helper script to get your Facebook Page ID from your access token.
This will show you which pages your token has access to.
"""

import asyncio
import os
from dotenv import load_dotenv
import httpx

load_dotenv()


async def get_facebook_pages():
    """Retrieve Facebook pages associated with the access token."""
    
    access_token = os.getenv("INSTAGRAM_ACCESS_TOKEN")
    
    if not access_token:
        print("❌ INSTAGRAM_ACCESS_TOKEN not found in .env file")
        return
    
    print("\n" + "="*80)
    print("FETCHING FACEBOOK PAGES")
    print("="*80)
    
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            # Get pages
            response = await client.get(
                "https://graph.facebook.com/v21.0/me/accounts",
                params={"access_token": access_token}
            )
            
            # Check for error response
            if response.status_code != 200:
                error_data = response.json() if response.text else {}
                error_message = error_data.get("error", {}).get("message", "Unknown error")
                error_code = error_data.get("error", {}).get("code", "Unknown code")
                print(f"\n❌ Facebook API Error:")
                print(f"   Status Code: {response.status_code}")
                print(f"   Error Code: {error_code}")
                print(f"   Message: {error_message}")
                print(f"\n💡 Your token might be expired or need additional permissions.")
                print(f"   Try regenerating your access token with 'pages_show_list' permission.")
                return
            
            data = response.json()
            
            pages = data.get("data", [])
            
            if not pages:
                print("\n❌ No Facebook Pages found for this access token.")
                print("   Make sure your access token has 'pages_manage_posts' permission.")
                return
            
            print(f"\n✅ Found {len(pages)} Facebook Page(s):\n")
            
            for i, page in enumerate(pages, 1):
                print(f"{i}. Name: {page.get('name')}")
                print(f"   ID: {page.get('id')}")
                print(f"   Category: {page.get('category', 'N/A')}")
                print(f"   Access Token: {page.get('access_token', 'N/A')[:50]}...")
                print()
            
            # Show recommendation
            if pages:
                first_page = pages[0]
                print("="*80)
                print("RECOMMENDED: Add this to your .env file:")
                print("="*80)
                print(f'FACEBOOK_PAGE_ID={first_page["id"]}')
                print(f'# {first_page["name"]}')
                print("="*80 + "\n")
                
    except Exception as e:
        print(f"\n❌ Error fetching pages: {str(e)}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(get_facebook_pages())
