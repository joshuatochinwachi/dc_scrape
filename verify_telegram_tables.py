
import requests
import json
import os
# from dotenv import load_dotenv

# load_dotenv()

# Use the values from check_categories.py if env vars aren't set in this shell context, 
# but preferably read from .env or hardcoded constants if that's what the user prefers.
# I'll try to read from main_api.py mechanism or just hardcode the keys I saw earlier if needed.
# Converting the hardcoded keys from step 2957 check_categories.py for reliability since I can see them.

URL = "https://ldraroaloinsesjoayxc.supabase.co"
KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImxkcmFyb2Fsb2luc2Vzam9heXhjIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NTYzMzEyNDYsImV4cCI6MjA3MTkwNzI0Nn0._F1o7W9ttSGCEh70dEM6l2dtpG5lieo1nQ7Q9zA2VUs"

HEADERS = {
    'apikey': KEY,
    'Authorization': f'Bearer {KEY}'
}

def check_table(table_name):
    print(f"\n--- Checking table: {table_name} ---")
    try:
        # Fetch 1 record to see columns
        response = requests.get(f"{URL}/rest/v1/{table_name}?limit=1", headers=HEADERS)
        if response.status_code == 200:
            data = response.json()
            if len(data) > 0:
                print("Columns found:", list(data[0].keys()))
                print("Sample Data:", json.dumps(data[0], indent=2))
            else:
                print("Table is accessible but empty. Cannot confirm all columns unless we try to insert or OPTIONS (if supported).")
                # Try OPTIONS to get schema info if PostgREST allows (often it doesn't without proper setup, but let's try GET first)
                # Alternative: Attempt to insert a dummy row if needed, but let's report empty first.
        else:
            print(f"Error accessing table: {response.status_code} {response.text}")
    except Exception as e:
        print(f"Exception: {e}")

if __name__ == "__main__":
    check_table("telegram_link_tokens")
    check_table("user_telegram_links")
