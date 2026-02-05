
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

def verify_logic():
    env = load_env_manual()
    url = env.get("SUPABASE_URL")
    key = env.get("SUPABASE_KEY")
    
    headers = {
        'apikey': key,
        'Authorization': f'Bearer {key}',
        'Content-Type': 'application/json'
    }

    test_token = "final-verify-token"
    # New logic: .replace('+00:00', 'Z')
    expires_at = (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat().replace('+00:00', 'Z')
    
    print(f"Storing with expires_at: {expires_at}")
    requests.post(f"{url}/rest/v1/telegram_link_tokens", headers=headers, json={
        "token": test_token,
        "telegram_id": "999",
        "expires_at": expires_at
    })

    # Retrieval logic:
    now_iso = datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
    print(f"Retrieving with now_iso: {now_iso}")
    
    params = {
        "token": f"eq.{test_token}",
        "expires_at": f"gt.{now_iso}",
        "select": "*"
    }
    
    resp = requests.get(f"{url}/rest/v1/telegram_link_tokens", headers=headers, params=params)
    print(f"Result Status: {resp.status_code}")
    if resp.status_code == 200 and resp.json():
        print("SUCCESS: Token retrieved with new Z logic and params encoding.")
        print(json.dumps(resp.json(), indent=2))
    else:
        print("FAILURE: Could not retrieve token.")
        print(f"Response: {resp.text}")

if __name__ == "__main__":
    verify_logic()
