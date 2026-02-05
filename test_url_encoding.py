
import os
import requests
from datetime import datetime, timezone, timedelta

def load_env_manual():
    env_vars = {}
    env_path = r"c:\Users\HP USER\Documents\Data Analyst\discord\.env"
    if os.path.exists(env_path):
        with open(env_path, 'r') as f:
            for line in f:
                if '=' in line and not line.startswith('#'):
                    key, val = line.strip().split('=', 1)
                    env_vars[key.strip()] = val.strip()
    return env_vars

def test_encoding():
    env = load_env_manual()
    url = env.get("SUPABASE_URL")
    key = env.get("SUPABASE_KEY")
    
    headers = {
        'apikey': key,
        'Authorization': f'Bearer {key}',
        'Content-Type': 'application/json'
    }

    # 1. Insert a fresh token
    test_token = "test-encoding-123"
    expires_at = (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat()
    requests.post(f"{url}/rest/v1/telegram_link_tokens", headers=headers, json={
        "token": test_token,
        "telegram_id": "888",
        "expires_at": expires_at
    })

    now_iso = datetime.now(timezone.utc).isoformat()
    print(f"Testing with now_iso: {now_iso}")

    # 2. Try with manual string (what main_api.py does)
    # The URL will contain a '+' if the ISO format includes it.
    manual_url = f"{url}/rest/v1/telegram_link_tokens?token=eq.{test_token}&expires_at=gt.{now_iso}&select=*"
    print(f"Manual URL: {manual_url}")
    resp_manual = requests.get(manual_url, headers=headers)
    print(f"Manual GET Result: {'FOUND' if resp_manual.json() else 'NOT FOUND'}")

    # 3. Try with proper encoding (using params)
    params = {
        "token": f"eq.{test_token}",
        "expires_at": f"gt.{now_iso}",
        "select": "*"
    }
    resp_encoded = requests.get(f"{url}/rest/v1/telegram_link_tokens", headers=headers, params=params)
    print(f"Encoded GET Result: {'FOUND' if resp_encoded.json() else 'NOT FOUND'}")
    print(f"Encoded URL used by requests: {resp_encoded.url}")

if __name__ == "__main__":
    test_encoding()
