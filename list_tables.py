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

print(f"Listing all tables via PostgREST...")
try:
    # PostgREST root returns OpenAPI spec with table info
    res = requests.get(f"{url}/rest/v1/", headers=headers, timeout=10)
    if res.status_code == 200:
        spec = res.json()
        tables = spec.get("definitions", {}).keys()
        print(f"✅ Found {len(tables)} tables:")
        for t in sorted(tables):
            print(f" - {t}")
    else:
        print(f"❌ Failed to list tables: HTTP {res.status_code} {res.text}")
except Exception as e:
    print(f"❌ Error: {e}")
