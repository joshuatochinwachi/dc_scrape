import requests
import os
import json
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv()

URL = os.getenv("SUPABASE_URL")
KEY = os.getenv("SUPABASE_KEY")
HEADERS = {
    "apikey": KEY,
    "Authorization": f"Bearer {KEY}",
    "Content-Type": "application/json"
}

def diagnose():
    print(f"URL: {URL}")
    print("Fetching latest 5 messages from discord_messages...")
    try:
        response = requests.get(
            f"{URL}/rest/v1/discord_messages?order=scraped_at.desc&limit=5",
            headers=HEADERS
        )
        if response.status_code != 200:
            print(f"Error: {response.status_code}")
            print(response.text)
            return

        messages = response.json()
        print(f"Found {len(messages)} messages.\n")

        for i, msg in enumerate(messages):
            print(f"--- Message {i+1} ---")
            print(f"ID: {msg.get('id')}")
            print(f"Scraped At: {msg.get('scraped_at')}")
            print(f"Channel ID: {msg.get('channel_id')}")
            print(f"Content Preview: {str(msg.get('content'))[:100]}...")
            
            raw_data = msg.get('raw_data')
            print(f"Raw Data Type: {type(raw_data)}")
            
            if isinstance(raw_data, str):
                print("⚠️ Raw Data is a STRING (needs json.loads)")
                try:
                    raw_data = json.loads(raw_data)
                    print("✅ Successfully parsed string to DICT")
                except:
                    print("❌ Failed to parse string")
            
            if isinstance(raw_data, dict):
                print(f"Raw Data Keys: {list(raw_data.keys())}")
                if 'embeds' in raw_data:
                    print(f"Embeds Count: {len(raw_data['embeds'])}")
                if 'embed' in raw_data:
                    print("Has single 'embed' key")
            
            print("\n")
    except Exception as e:
        print(f"Request failed: {e}")

if __name__ == "__main__":
    diagnose()
