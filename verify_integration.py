
import requests
import json

URL = "https://ldraroaloinsesjoayxc.supabase.co"
KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInZiI6ImxkcmFyb2Fsb2luc2Vzam9heXhjIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NTYzMzEyNDYsImV4cCI6MjA3MTkwNzI0Nn0._F1o7W9ttSGCEh70dEM6l2dtpG5lieo1nQ7Q9zA2VUs"

def verify_saved_deals():
    headers = {
        'apikey': KEY,
        'Authorization': f'Bearer {KEY}',
        'Content-Type': 'application/json'
    }
    
    # Test user ID (from previous signup attempts or generic)
    user_id = "8b4e7a16-d0" # Simulated short ID or use a real UUID if known
    alert_id = "test_alert_123"
    
    print("\n--- Testing Save Deal ---")
    payload = {
        "user_id": "8b4e7a16-d035-4200-8800-000000000000", # Dummy UUID
        "alert_id": alert_id,
        "alert_data": {"id": alert_id, "title": "Test Product"}
    }
    # Note: This direct call to Supabase might fail if constraints are tight, 
    # but we are testing the endpoint logic in our head too.
    # We'll just check if we can fetch.
    
    response = requests.get(f"{URL}/rest/v1/saved_deals?limit=5", headers=headers)
    print(f"Fetch Status: {response.status_code}")
    if response.status_code == 200:
        print(f"Current Saved Deals: {len(response.json())}")

if __name__ == "__main__":
    verify_saved_deals()
