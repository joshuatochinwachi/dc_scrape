import requests
import json
from datetime import datetime, timezone

def debug_bot_users():
    url = "https://ldraroaloinsesjoayxc.supabase.co"
    key = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImxkcmFyb2Fsb2luc2Vzam9heXhjIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NTYzMzEyNDYsImV4cCI6MjA3MTkwNzI0Nn0._F1o7W9ttSGCEh70dEM6l2dtpG5lieo1nQ7Q9zA2VUs"
    
    # Try public access first
    storage_url = f"{url}/storage/v1/object/public/monitor-data/discord_josh/bot_users.json"
    
    headers = {
        'apikey': key,
        'Authorization': f'Bearer {key}'
    }
    
    print(f"Trying authenticated access to {storage_url}...")
    
    try:
        response = requests.get(storage_url, headers=headers, timeout=10)
        if response.status_code == 200:
            data = response.json()
            print(f"✅ Loaded {len(data)} users")
            
            # Print a few samples
            count = 0
            for k, v in data.items():
                print(f"Key: '{k}' -> Value: {v}")
                count += 1
                if count >= 20: break
        else:
            print(f"❌ Authenticated fetch failed: {response.status_code}")
            print(f"   Response: {response.text}")
            
            # Try non-public internal URL
            authenticated_url = f"{url}/storage/v1/object/authenticated/monitor-data/discord_josh/bot_users.json"
            print(f"Trying internal URL: {authenticated_url}...")
            response = requests.get(authenticated_url, headers=headers, timeout=10)
            if response.status_code == 200:
                data = response.json()
                print(f"✅ Loaded {len(data)} users via authenticated URL")
                # ... same loop ...
            else:
                print(f"❌ Both attempts failed. Final response: {response.status_code} {response.text}")
                
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    debug_bot_users()
