"""
Get Facebook Page ID from your Page Access Token using /me endpoint.
"""

import asyncio
import os
from dotenv import load_dotenv
import httpx

load_dotenv()


async def get_page_id_from_token():
    """Get Page ID using /me endpoint with Page token."""
    
    access_token = os.getenv("INSTAGRAM_ACCESS_TOKEN")
    
    if not access_token:
        print("❌ INSTAGRAM_ACCESS_TOKEN not found in .env file")
        return
    
    print("\n" + "="*80)
    print("FETCHING PAGE ID FROM TOKEN")
    print("="*80)
    
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            # Call /me to get Page info
            response = await client.get(
                "https://graph.facebook.com/v21.0/me",
                params={
                    "access_token": access_token,
                    "fields": "id,name,category,instagram_business_account"
                }
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
                return
            
            data = response.json()
            
            # Display Page info
            print(f"\n✅ Page Information Retrieved:\n")
            print(f"Page Name: {data.get('name', 'N/A')}")
            print(f"Page ID: {data.get('id', 'N/A')}")
            print(f"Category: {data.get('category', 'N/A')}")
            
            # Check for Instagram Business Account
            ig_account = data.get('instagram_business_account')
            if ig_account:
                print(f"Instagram Business Account ID: {ig_account.get('id', 'N/A')}")
            
            # Show recommendation
            page_id = data.get('id')
            if page_id:
                print("\n" + "="*80)
                print("✅ SUCCESS! Add this to your .env file:")
                print("="*80)
                print(f'FACEBOOK_PAGE_ID={page_id}')
                print("="*80 + "\n")
                
                # Automatically update .env if user wants
                print("Would you like to automatically add this to your .env file? (Ctrl+C to cancel)")
                await asyncio.sleep(2)
                
                # Add to .env
                env_path = ".env"
                with open(env_path, 'r') as f:
                    env_content = f.read()
                
                if 'FACEBOOK_PAGE_ID' not in env_content:
                    with open(env_path, 'a') as f:
                        f.write(f'\n# Facebook Page ID (for posting)\nFACEBOOK_PAGE_ID={page_id}\n')
                    print(f"✅ Added FACEBOOK_PAGE_ID to .env file!\n")
                else:
                    print(f"ℹ️  FACEBOOK_PAGE_ID already exists in .env file. Update it manually if needed.\n")
                
    except asyncio.CancelledError:
        print("\n❌ Cancelled by user")
    except Exception as e:
        print(f"\n❌ Error: {str(e)}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(get_page_id_from_token())
