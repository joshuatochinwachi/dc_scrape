import os
from dotenv import load_dotenv
import supabase_utils
import requests
import json

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

def check_schema():
    print("Fetching latest message...")
    headers = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}
    url = f"{SUPABASE_URL}/rest/v1/discord_messages"
    params = {"limit": 1, "order": "scraped_at.desc"}
    
    try:
        res = requests.get(url, headers=headers, params=params)
        res.raise_for_status()
        messages = res.json()
        
        if messages:
            msg = messages[0]
            print("\nKeys in message:")
            print(list(msg.keys()))
            if "channel_id" in msg:
                print(f"\n✅ channel_id found: {msg['channel_id']}")
            else:
                print("\n❌ channel_id NOT found")
                
            # Also check raw_data just in case
            if "raw_data" in msg:
                print("raw_data keys:", list(msg["raw_data"].keys()))
        else:
            print("No messages found.")
            
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    check_schema()
