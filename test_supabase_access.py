import requests
import os
from dotenv import load_dotenv

load_dotenv()

url = os.getenv("SUPABASE_URL", "").strip()
key = os.getenv("SUPABASE_KEY", "").strip()

headers = {
    "apikey": key,
    "Authorization": f"Bearer {key}"
}

print(f"Checking access to discord_messages...")
try:
    res = requests.get(f"{url}/rest/v1/discord_messages?limit=1", headers=headers, timeout=10)
    if res.status_code == 200:
        print("✅ Access to 'discord_messages' OK!")
        print(f"Data: {res.json()}")
    else:
        print(f"❌ Access failed: HTTP {res.status_code} {res.text}")
except Exception as e:
    print(f"❌ Error: {e}")
