
import httpx
import asyncio
from datetime import datetime, timezone

async def test_httpx():
    # We'll use a local debug server or just print what httpx does under the hood if possible
    # but simplest is to test against a public echo service if available
    # Or just test against Supabase again but with httpx
    
    # Let's use the actual Supabase URL from .env
    def load_env_manual():
        import os
        env_vars = {}
        env_path = r"c:\Users\HP USER\Documents\Data Analyst\discord\.env"
        if os.path.exists(env_path):
            with open(env_path, 'r') as f:
                for line in f:
                    if '=' in line and not line.startswith('#'):
                        key, val = line.strip().split('=', 1)
                        env_vars[key.strip()] = val.strip()
        return env_vars

    env = load_env_manual()
    url = env.get("SUPABASE_URL")
    key = env.get("SUPABASE_KEY")
    
    headers = {
        'apikey': key,
        'Authorization': f'Bearer {key}'
    }

    test_token = "test-httpx-123"
    now_iso = datetime.now(timezone.utc).isoformat()
    
    # Python 3.11+ isoformat() with timezone.utc uses +00:00
    # Earlier versions might use +00:00 or Z depending on how it's handled.
    print(f"now_iso: {now_iso}")

    async with httpx.AsyncClient() as client:
        # Manual string interpolation (main_api.py style)
        manual_url = f"{url}/rest/v1/telegram_link_tokens?token=eq.{test_token}&expires_at=gt.{now_iso}"
        print(f"Calling manual URL: {manual_url}")
        
        # We don't even need the token to exist, we just want to see if we get a 200 (even if empty)
        # or a 400 Bad Request if the timestamp parsing fails.
        resp = await client.get(manual_url, headers=headers)
        print(f"Status: {resp.status_code}")
        if resp.status_code == 400:
            print(f"Error: {resp.text}")
        else:
            print(f"Data: {resp.json()}")

if __name__ == "__main__":
    asyncio.run(test_httpx())
