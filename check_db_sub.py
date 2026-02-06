import requests
import json

def check_db_subscriptions():
    url = "https://ldraroaloinsesjoayxc.supabase.co"
    key = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImxkcmFyb2Fsb2luc2Vzam9heXhjIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NTYzMzEyNDYsImV4cCI6MjA3MTkwNzI0Nn0._F1o7W9ttSGCEh70dEM6l2dtpG5lieo1nQ7Q9zA2VUs"
    
    headers = {
        'apikey': key,
        'Authorization': f'Bearer {key}',
        'Content-Type': 'application/json'
    }
    
    results = {
        "latest_links": [],
        "premium_users_count": 0,
        "total_users": 0
    }
    
    try:
        links_url = f"{url}/rest/v1/user_telegram_links?select=user_id,telegram_id,telegram_username,linked_at&order=linked_at.desc&limit=5"
        resp = requests.get(links_url, headers=headers)
        if resp.status_code == 200:
            for l in resp.json():
                link_data = {
                    "user_id": l['user_id'],
                    "telegram_id": l['telegram_id'],
                    "telegram_username": l.get('telegram_username'),
                    "linked_at": l['linked_at'],
                    "user_db_status": None
                }
                
                # Check this user in users table
                u_url = f"{url}/rest/v1/users?id=eq.{l['user_id']}&select=id,email,subscription_status,subscription_end"
                u_resp = requests.get(u_url, headers=headers)
                if u_resp.status_code == 200 and u_resp.json():
                    link_data["user_db_status"] = u_resp.json()[0]
                
                results["latest_links"].append(link_data)
        
        # Count premium users
        u_count_url = f"{url}/rest/v1/users?subscription_status=eq.active&select=count"
        u_count_resp = requests.get(u_count_url, headers={**headers, "Prefer": "count=exact"})
        # Note: count might be in headers
        results["premium_users_count"] = u_count_resp.headers.get("Content-Range", "Unknown")
        
        with open("db_check_results.json", "w") as f:
            json.dump(results, f, indent=2)
        print("✅ Results saved to db_check_results.json")
        
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    check_db_subscriptions()
