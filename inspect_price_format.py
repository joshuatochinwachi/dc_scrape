"""
Quick script to fetch recent messages from Supabase and inspect the price field format.
"""
import os
import json
import requests
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL", "").strip()
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "").strip()

if not SUPABASE_URL or not SUPABASE_KEY:
    print("❌ Missing SUPABASE_URL or SUPABASE_KEY in .env")
    exit(1)

headers = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}"
}

# Fetch recent messages
url = f"{SUPABASE_URL}/rest/v1/discord_messages"
params = {
    "select": "*",
    "order": "scraped_at.desc",
    "limit": 100
}

print("🔍 Fetching recent messages from Supabase...\n")
res = requests.get(url, headers=headers, params=params, timeout=15)

if res.status_code != 200:
    print(f"❌ API Error: {res.status_code}")
    exit(1)

messages = res.json()

print(f"Found {len(messages)} messages\n")

discount_found = 0
for i, msg in enumerate(messages):
    raw_data = msg.get("raw_data", {})
    embed = raw_data.get("embed", {})
    
    if not embed:
        continue
    
    fields = embed.get("fields", [])
    
    for field in fields:
        name = field.get("name", "").lower()
        value = field.get("value", "")
        
        # Look for price fields that might have discounts (contain % or multiple numbers)
        if "price" in name:
            # Check if this looks like a discount (has % or multiple price-like numbers)
            if "%" in value or value.count(".") > 1:
                discount_found += 1
                print(f"=== DISCOUNT PRICE FOUND (Message {i+1}) ===")
                print(f"Channel ID: {msg.get('channel_id')}")
                print(f"Title: {embed.get('title', 'N/A')[:60]}")
                print(f"Field Name: {field.get('name')}")
                print(f"Raw Value: '{value}'")
                print(f"repr: {repr(value)}")
                print()

if discount_found == 0:
    print("No discount prices found in recent messages.")
    print("\nShowing ALL price fields instead:\n")
    for i, msg in enumerate(messages):
        raw_data = msg.get("raw_data", {})
        embed = raw_data.get("embed", {})
        if not embed:
            continue
        fields = embed.get("fields", [])
        for field in fields:
            name = field.get("name", "").lower()
            value = field.get("value", "")
            if "price" in name:
                print(f"[{i+1}] {field.get('name')}: '{value}'")
