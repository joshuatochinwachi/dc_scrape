import json
import urllib.request
import urllib.error

def test_update():
    url = "http://127.0.0.1:8000/v1/user/profile"
    # Using the user_id seen in previous logs
    payload = {
        "user_id": "c504751b-2835-4ffb-b2bb-0f6f5f0d17ae",
        "name": "Debug User",
        "bio": "Testing update",
        "location": "Debug City"
    }
    
    print(f"Sending PATCH to {url} with payload: {json.dumps(payload, indent=2)}")
    
    jsondata = json.dumps(payload).encode('utf-8')
    req = urllib.request.Request(url, data=jsondata, method='PATCH')
    req.add_header('Content-Type', 'application/json')
    
    try:
        with urllib.request.urlopen(req) as response:
            print(f"\nStatus Code: {response.getcode()}")
            print(f"Response Body: {response.read().decode('utf-8')}")
    except urllib.error.HTTPError as e:
        print(f"\nHTTP Error {e.code}: {e.reason}")
        print(f"Response Body: {e.read().decode('utf-8')}")
    except Exception as e:
        print(f"Request failed: {e}")

if __name__ == "__main__":
    test_update()
