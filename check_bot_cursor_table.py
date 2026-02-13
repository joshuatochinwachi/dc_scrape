import requests
import os
from dotenv import load_dotenv

load_dotenv()

url = os.getenv("SUPABASE_URL", "").strip()
key = os.getenv("SUPABASE_KEY", "").strip()

if url.endswith('/'): url = url[:-1]

headers = {
    "apikey": key,
    "Authorization": f"Bearer {key}",
    "Content-Type": "application/json"
}

print(f"Checking table: {url}/rest/v1/bot_cursor?select=*&limit=1")
try:
    res = requests.get(f"{url}/rest/v1/bot_cursor?select=*&limit=1", headers=headers, timeout=10)
    if res.status_code == 200:
        print("✅ Table 'bot_cursor' exists!")
        print(f"Data: {res.json()}")
    elif res.status_code == 404:
        print("❌ Table 'bot_cursor' does NOT exist (404).")
    else:
        print(f"❓ Table check returned status {res.status_code}: {res.text}")
except Exception as e:
    print(f"❌ Error checking table: {e}")
