
import requests
import json

URL = "https://ldraroaloinsesjoayxc.supabase.co"
KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImxkcmFyb2Fsb2luc2Vzam9heXhjIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NTYzMzEyNDYsImV4cCI6MjA3MTkwNzI0Nn0._F1o7W9ttSGCEh70dEM6l2dtpG5lieo1nQ7Q9zA2VUs"

def migrate():
    # Unfortunately, standard REST API doesn't allow ALTER TABLE.
    # We have to rely on the columns being there or use some other trick.
    # I'll check if they are there first.
    
    headers = {
        'apikey': KEY,
        'Authorization': f'Bearer {KEY}'
    }
    
    # Check current columns
    response = requests.get(f"{URL}/rest/v1/users?limit=1", headers=headers)
    if response.status_code == 200:
        data = response.json()
        if data:
            cols = list(data[0].keys())
            print(f"Current columns: {cols}")
            
            missing = []
            if 'notification_preferences' not in cols: missing.append('notification_preferences')
            if 'push_tokens' not in cols: missing.append('push_tokens')
            
            if not missing:
                print("All necessary columns exist.")
                return
                
            print(f"Missing columns: {missing}")
            print("Please run the following SQL in Supabase Dashboard:")
            for col in missing:
                print(f"ALTER TABLE users ADD COLUMN IF NOT EXISTS {col} JSONB DEFAULT '{{}}';")
        else:
            print("Users table is empty, cannot detect columns via REST easily.")
    else:
        print(f"Error checking columns: {response.status_code}")

if __name__ == "__main__":
    migrate()
