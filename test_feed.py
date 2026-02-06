import requests
import json

BASE_URL = "http://localhost:8000/v1"
USER_ID = "4d230c88-b532-47e1-a8a2-85949a25e6e0" # flizzypinkz@gmail.com

def test_feed():
    print(f"--- Testing Feed PAGINATION for {USER_ID} ---")
    url = f"{BASE_URL}/feed?user_id={USER_ID}&region=USA%20Stores&limit=10&offset=50"
    try:
        resp = requests.get(url)
        print(f"Status Code: {resp.status_code}")
        if resp.status_code == 200:
            data = resp.json()
            print(f"RES1: {len(data.get('products', []))}")
            print(f"RES2: {data.get('next_offset')}")
            print(f"RES3: {data.get('has_more')}")
            print(f"RES4: {data.get('is_premium')}")
        else:
            print(f"Error: {resp.text}")
    except Exception as e:
        print(f"Request failed: {e}")

if __name__ == "__main__":
    test_feed()
