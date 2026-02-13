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

print(f"Checking table 'bot_cursor' with explicit schema headers...")
try:
    # Try with explicit public schema header
    h2 = headers.copy()
    h2["Accept-Profile"] = "public"
    
    res = requests.get(f"{url}/rest/v1/bot_cursor?limit=1", headers=h2, timeout=10)
    print(f"Public Schema Check: HTTP {res.status_code}")
    if res.status_code != 200:
        print(f"Response: {res.text}")
        
    # Check if it's in another common schema? (Unlikely but for completeness)
    # Actually, let's just check the "definitions" specifically in the root spec again
    root = requests.get(f"{url}/rest/v1/", headers=headers, timeout=10)
    spec = root.json()
    if "bot_cursor" in spec.get("definitions", {}):
        print("✅ 'bot_cursor' FOUND in OpenAPI definitions!")
    else:
        print("❌ 'bot_cursor' NOT FOUND in OpenAPI definitions!")

except Exception as e:
    print(f"❌ Error: {e}")
