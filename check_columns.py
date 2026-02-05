
import requests
import json

URL = "https://ldraroaloinsesjoayxc.supabase.co"
KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImxkcmFyb2Fsb2luc2Vzam9heXhjIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NTYzMzEyNDYsImV4cCI6MjA3MTkwNzI0Nn0._F1o7W9ttSGCEh70dEM6l2dtpG5lieo1nQ7Q9zA2VUs"

def check_all_tables_concise():
    headers = {
        'apikey': KEY,
        'Authorization': f'Bearer {KEY}'
    }
    
    tables = ['alerts', 'categories', 'discord_messages', 'saved_deals', 'telegram_link_tokens', 'user_telegram_links', 'users', 'email_verifications']
    
    for table in tables:
        response = requests.get(f"{URL}/rest/v1/{table}?limit=1", headers=headers)
        if response.status_code == 200:
            data = response.json()
            if data and len(data) > 0:
                print(f"{table}: {', '.join(data[0].keys())}")
            else:
                # Try getting columns from OpenAPI spec for empty tables
                print(f"{table}: EMPTY")
        else:
            print(f"{table}: ERROR {response.status_code}")

if __name__ == "__main__":
    check_all_tables_concise()
