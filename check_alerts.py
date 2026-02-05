
import requests
import json

URL = "https://ldraroaloinsesjoayxc.supabase.co"
KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImxkcmFyb2Fsb2luc2Vzam9heXhjIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NTYzMzEyNDYsImV4cCI6MjA3MTkwNzI0Nn0._F1o7W9ttSGCEh70dEM6l2dtpG5lieo1nQ7Q9zA2VUs"

def check_alerts_content():
    headers = {
        'apikey': KEY,
        'Authorization': f'Bearer {KEY}'
    }
    
    response = requests.get(f"{URL}/rest/v1/alerts?limit=5", headers=headers)
    if response.status_code == 200:
        data = response.json()
        if data:
            print(f"Found {len(data)} alerts.")
            print(json.dumps(data, indent=2))
        else:
            print("Alerts table is empty.")
    else:
        print(f"Error: {response.status_code} {response.text}")

if __name__ == "__main__":
    check_alerts_content()
