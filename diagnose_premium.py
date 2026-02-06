import requests
import os
import json

# Using known working values for this environment
URL = 'https://ldraroaloinsesjoayxc.supabase.co'
KEY = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImxkcmFyb2Fsb2luc2Vzam9heXhjIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NTYzMzEyNDYsImV4cCI6MjA3MTkwNzI0Nn0._F1o7W9ttSGCEh70dEM6l2dtpG5lieo1nQ7Q9zA2VUs'
SUPABASE_BUCKET = "monitor-data" 

HEADERS = {
    "apikey": KEY,
    "Authorization": f"Bearer {KEY}"
}

def diagnose_user(email):
    print(f"--- Diagnosing {email} ---")
    # 1. Check User table
    user_url = f"{URL}/rest/v1/users?email=eq.{email}&select=*"
    resp = requests.get(user_url, headers=HEADERS)
    if resp.status_code == 200 and resp.json():
        user = resp.json()[0]
        user_id = user['id']
        print(f"User ID: {user_id}")
        print(f"Name: {user.get('name')}")
        print(f"Bio: {user.get('bio')}")
        print(f"Location: {user.get('location')}")
        print(f"Avatar: {user.get('avatar_url')}")
        print(f"Sub Status: {user.get('subscription_status')}")
        print(f"Sub End: {user.get('subscription_end')}")
        
        # 2. Check Link table
        link_url = f"{URL}/rest/v1/user_telegram_links?user_id=eq.{user_id}&select=*"
        link_resp = requests.get(link_url, headers=HEADERS)
        if link_resp.status_code == 200 and link_resp.json():
            link_data = link_resp.json()[0]
            telegram_id = link_data.get('telegram_id')
            print(f"Linked Telegram ID: {telegram_id}")
            
            # 3. Check bot_users.json
            bucket = SUPABASE_BUCKET
            bot_users_url = f"{URL}/storage/v1/object/authenticated/{bucket}/discord_josh/bot_users.json"
            bot_resp = requests.get(bot_users_url, headers=HEADERS)
            if bot_resp.status_code == 200:
                bot_users = bot_resp.json()
                tg_data = bot_users.get(str(telegram_id))
                if tg_data:
                    print(f"Bot Users Data found: True")
                    print(f"Expiry in Bot Data: {tg_data.get('expiry')}")
                else:
                    print(f"No data found in bot_users.json for ID: {telegram_id}")
            else:
                print(f"Failed to fetch bot_users.json: {bot_resp.status_code}")
        else:
            print("No Telegram link found.")
    else:
        print(f"User not found or error: {resp.status_code}")

if __name__ == "__main__":
    diagnose_user("flizzypinkz@gmail.com")
