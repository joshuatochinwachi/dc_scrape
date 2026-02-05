
import os
import requests
import json
import re
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

def check_supabase():
    env = load_env_manual()
    url = env.get("SUPABASE_URL")
    key = env.get("SUPABASE_KEY")
    
    if not url or not key:
        print("MISSING Supabase credentials in .env")
        return

    headers = {
        'apikey': key,
        'Authorization': f'Bearer {key}',
        'Content-Type': 'application/json'
    }

    print("--- 1. Testing Insertion ---")
    test_token = f"diag-{datetime.now().strftime('%H%M%S')}"
    test_id = "12345678"
    expires_at = (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat()
    
    payload = {
        "token": test_token,
        "telegram_id": test_id,
        "expires_at": expires_at
    }
    
    resp_ins = requests.post(f"{url}/rest/v1/telegram_link_tokens", headers=headers, json=payload)
    print(f"Insert Status: {resp_ins.status_code}")
    if resp_ins.status_code not in [200, 201, 204]:
        print(f"Insert Error: {resp_ins.text}")
        return

    print(f"SUCCESS: Token '{test_token}' inserted.")

    print("\n--- 2. Testing Retrieval (API Logic) ---")
    now_iso = datetime.now(timezone.utc).isoformat()
    params = {
        "token": f"eq.{test_token}",
        "expires_at": f"gt.{now_iso}",
        "select": "*"
    }
    
    resp_get = requests.get(f"{url}/rest/v1/telegram_link_tokens", headers=headers, params=params)
    print(f"GET Status: {resp_get.status_code}")
    if resp_get.status_code == 200:
        data = resp_get.json()
        if data:
            print("SUCCESS: Token found via filter!")
            print(json.dumps(data, indent=2))
        else:
            print("FAILURE: Token NOT found via filter (possibly timestamp precision or encoding issue)")
            # Try without the timestamp filter
            resp_no_time = requests.get(f"{url}/rest/v1/telegram_link_tokens", headers=headers, params={"token": f"eq.{test_token}"})
            if resp_no_time.status_code == 200 and resp_no_time.json():
                print("INFO: Token exists in DB, but the 'expires_at=gt.{now_iso}' filter failed it.")
                db_expires = resp_no_time.json()[0]['expires_at']
                print(f"   DB Expires At: {db_expires}")
                print(f"   Now ISO Used:  {now_iso}")
            else:
                print("FAILURE: Token not found even without time filter.")
    else:
        print(f"GET Error: {resp_get.text}")

    print("\n--- 3. Recent Tokens in DB ---")
    params_recent = {
        "select": "*",
        "order": "created_at.desc",
        "limit": 5
    }
    resp_recent = requests.get(f"{url}/rest/v1/telegram_link_tokens", headers=headers, params=params_recent)
    if resp_recent.status_code == 200:
        res_data = resp_recent.json()
        print(f"Found {len(res_data)} recent tokens.")
        for t in res_data:
            print(f"Token: {t['token']}, TG ID: {t['telegram_id']}, Expires: {t['expires_at']}")
    else:
        print(f"Recent check error: {resp_recent.text}")

if __name__ == "__main__":
    check_supabase()
