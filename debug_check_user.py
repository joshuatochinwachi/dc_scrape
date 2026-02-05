import requests

URL = "https://ldraroaloinsesjoayxc.supabase.co"
KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImxkcmFyb2Fsb2luc2Vzam9heXhjIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NTYzMzEyNDYsImV4cCI6MjA3MTkwNzI0Nn0._F1o7W9ttSGCEh70dEM6l2dtpG5lieo1nQ7Q9zA2VUs"
HEADERS = {
    "apikey": KEY,
    "Authorization": f"Bearer {KEY}",
    "Content-Type": "application/json"
}

def check_user(email):
    print(f"Checking user: {email}")
    resp = requests.get(f"{URL}/rest/v1/users?email=eq.{email}&select=*", headers=HEADERS)
    if resp.status_code == 200 and resp.json():
        user = resp.json()[0]
        user_id = user['id']
        print(f"Found User ID: {user_id}")
        
        # Check links
        link_resp = requests.get(f"{URL}/rest/v1/user_telegram_links?user_id=eq.{user_id}&select=*", headers=HEADERS)
        if link_resp.status_code == 200:
            links = link_resp.json()
            if links:
                print(f"LNK Found {len(links)} links for this user:")
                for l in links:
                    print(f"LNK - Telegram ID: {l['telegram_id']}, Username: {l.get('telegram_username', 'N/A')}")
            else:
                print("LNK No Telegram links found for this user ID.")
        else:
            print(f"LNK Error checking links: {link_resp.text}")
    else:
        print(f"USR User not found: {resp.text}")

if __name__ == "__main__":
    check_user("smirhty@gmail.com")
