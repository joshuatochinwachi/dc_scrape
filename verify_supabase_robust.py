import os
import requests
import json
from dotenv import load_dotenv

load_dotenv()

def verify_supabase():
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_KEY")
    
    headers = {
        'apikey': key,
        'Authorization': f'Bearer {key}'
    }
    
    print(f"--- Supabase Connectivity Test ---")
    print(f"URL: {url}")
    
    # 1. Test basic reachability
    try:
        r = requests.get(f"{url}/rest/v1/", headers=headers)
        print(f"Root API Status: {r.status_code}")
        if r.status_code != 200:
            print(f"Error: {r.text}")
    except Exception as e:
        print(f"Connection Error: {e}")
        return

    # 2. Test Users table (for Login)
    try:
        r = requests.get(f"{url}/rest/v1/users?select=count", headers=headers)
        print(f"Users Table Status: {r.status_code}")
        print(f"Users Count (Header): {r.headers.get('Content-Range')}")
        if r.status_code == 200:
            print("Successfully connected to Users table.")
        else:
            print(f"Error: {r.text}")
    except Exception as e:
        print(f"User Table Fetch Error: {e}")

    # 3. Test a sample query
    try:
        r = requests.get(f"{url}/rest/v1/users?limit=1", headers=headers)
        if r.status_code == 200:
            data = r.json()
            if data:
                print(f"Sample User Email: {data[0].get('email')}")
            else:
                print("Users table is empty.")
        else:
            print(f"Sample query failed: {r.status_code}")
    except Exception as e:
        print(f"Query Error: {e}")

if __name__ == "__main__":
    verify_supabase()
