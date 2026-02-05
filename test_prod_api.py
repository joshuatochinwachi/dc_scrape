
import os
import requests
import json
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

def test_production_api():
    env = load_env_manual()
    # 1. Prepare Token in Supabase
    url = env.get("SUPABASE_URL")
    key = env.get("SUPABASE_KEY")
    api_base = env.get("API_BASE_URL", "https://web-production-18cf1.up.railway.app")
    
    headers = {
        'apikey': key,
        'Authorization': f'Bearer {key}',
        'Content-Type': 'application/json'
    }

    test_token = f"prod-test-{datetime.now().strftime('%H%M%S')}"
    telegram_id = "1220056877" # The user's ID from previous logs
    expires_at = (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat()
    
    print(f"--- 1. Inserting Token '{test_token}' into Supabase ---")
    resp_ins = requests.post(f"{url}/rest/v1/telegram_link_tokens", headers=headers, json={
        "token": test_token,
        "telegram_id": telegram_id,
        "expires_at": expires_at
    })
    if resp_ins.status_code not in [200, 201, 204]:
        print(f"Insertion Failed: {resp_ins.text}")
        return
    print("Insertion Success.")

    # 2. Call Railway API
    # We need a valid app user_id. I'll try to find one from the 'users' table or use a dummy one.
    # Actually, the API first checks the code, then links.
    # If it says 'Invalid or expired code', it means step 2 failed.
    
    print(f"\n--- 2. Calling Railway API to verify token ---")
    prod_url = f"{api_base}/v1/user/telegram/link"
    # Use a dummy user_id if we don't have a real one, the token verification happens FIRST.
    payload = {
        "user_id": "00000000-0000-0000-0000-000000000000", 
        "code": test_token
    }
    
    print(f"URL: {prod_url}")
    print(f"Payload: {payload}")
    
    resp_api = requests.post(prod_url, json=payload)
    print(f"API Status: {resp_api.status_code}")
    print(f"API Response: {resp_api.text}")

if __name__ == "__main__":
    test_production_api()
