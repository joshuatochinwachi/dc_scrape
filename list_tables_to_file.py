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

try:
    res = requests.get(f"{url}/rest/v1/", headers=headers, timeout=10)
    if res.status_code == 200:
        spec = res.json()
        tables = sorted(spec.get("definitions", {}).keys())
        with open("tables_list.txt", "w") as f:
            for t in tables:
                f.write(f"{t}\n")
        print(f"✅ Found {len(tables)} tables and saved to tables_list.txt")
except Exception as e:
    print(f"❌ Error: {e}")
