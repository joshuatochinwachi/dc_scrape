
import os
import requests
import json
import uuid
from datetime import datetime, timezone, timedelta

def load_env_manual():
    env_vars = {}
    env_path = r"c:\Users\HP USER\Documents\Data Analyst\discord\.env"
    if os.path.exists(env_path):
        with open(env_path, 'r') as f:
            for line in f:
                if '=' in line and not line.startswith('#'):
                    # Handle multiple = in line (like in keys)
                    parts = line.strip().split('=', 1)
                    if len(parts) == 2:
                        env_vars[parts[0].strip()] = parts[1].strip()
    return env_vars

def verify_local_flow():
    print("🚀 Starting Local Flow Verification...")
    env = load_env_manual()
    
    # 1. Configuration Check
    supabase_url = env.get("SUPABASE_URL")
    supabase_key = env.get("SUPABASE_KEY")
    local_api = "http://localhost:8000"
    
    if not supabase_url or not supabase_key:
        print("❌ ERROR: Missing Supabase credentials in .env")
        return

    headers_supabase = {
        'apikey': supabase_key,
        'Authorization': f'Bearer {supabase_key}',
        'Content-Type': 'application/json',
        'Prefer': 'return=minimal'
    }

    # 2. Create a Token in Supabase (Simulating Bot)
    # We use the NEW logic: expires_at with 'Z'
    test_token = str(uuid.uuid4())
    expires_at = (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat().replace('+00:00', 'Z')
    
    print(f"--- 1. Storing Token in Supabase ---")
    print(f"Token: {test_token}")
    print(f"Expires At: {expires_at}")
    
    payload_store = {
        "token": test_token,
        "telegram_id": "local-test-user",
        "expires_at": expires_at
    }
    
    try:
        resp_store = requests.post(f"{supabase_url}/rest/v1/telegram_link_tokens", headers=headers_supabase, json=payload_store)
        if resp_store.status_code not in [200, 201, 204]:
            print(f"❌ FAILED to store token: {resp_store.status_code} {resp_store.text}")
            return
        print("✅ Token stored successfully in Supabase.")
    except Exception as e:
        print(f"❌ CRITICAL ERROR storing token: {e}")
        return

    # 3. Call LOCAL API to verify (Simulating App)
    print(f"\n--- 2. Calling LOCAL API (localhost:8000) ---")
    # Note: user_id 0000... is just for testing verification of the token
    payload_link = {
        "user_id": "00000000-0000-0000-0000-000000000000",
        "code": test_token
    }
    
    try:
        resp_api = requests.post(f"{local_api}/v1/user/telegram/link", json=payload_link, timeout=10)
        print(f"HTTP Status: {resp_api.status_code}")
        
        if resp_api.status_code == 200:
            data = resp_api.json()
            if data.get("success"):
                print("✅ SUCCESS! The local API correctly verified the token from Supabase.")
                print(f"Message: {data.get('message')}")
            else:
                print(f"❌ FAILED: API returned success=False")
                print(f"Error Message: {data.get('message')}")
                if "Invalid or expired code" in data.get('message', ''):
                    print("💡 Hint: Make sure you RESTART main_api.py to apply the new fixes.")
        else:
            print(f"❌ API Error: {resp_api.text}")
            
    except requests.exceptions.ConnectionError:
        print(f"❌ CONNECTION ERROR: Could not reach {local_api}. Is the server running?")
    except Exception as e:
        print(f"❌ ERROR calling API: {e}")

if __name__ == "__main__":
    verify_local_flow()
