import httpx
import os
from dotenv import load_dotenv

load_dotenv()

URL = os.getenv("SUPABASE_URL")
KEY = os.getenv("SUPABASE_KEY")
HEADERS = {
    "apikey": KEY,
    "Authorization": f"Bearer {KEY}"
}

async def check_user(email):
    async with httpx.AsyncClient() as client:
        url = f"{URL}/rest/v1/users?email=eq.{email}&select=*"
        resp = await client.get(url, headers=HEADERS)
        if resp.status_code == 200 and resp.json():
            user = resp.json()[0]
            print(f"User: {user['email']}")
            print(f"Email Verified (email_verified): {user.get('email_verified')}")
            print(f"Subscription Status: {user.get('subscription_status')}")
            print(f"Subscription Source: {user.get('subscription_source')}")
            print(f"Verification Field Check: {'email_verified' in user}, {'is_verified' in user}")
        else:
            print(f"User {email} not found or error: {resp.status_code}")
            if resp.status_code != 200:
                print(f"Response: {resp.text}")

if __name__ == "__main__":
    import asyncio
    # Check smartymetric@gmail.com and smartymetrics@gmail.com
    for email in ["smartymetric@gmail.com", "smartymetrics@gmail.com"]:
        asyncio.run(check_user(email))
