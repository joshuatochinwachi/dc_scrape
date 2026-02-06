import urllib.request
import urllib.error
import json

def fetch_json(url):
    print(f"Fetching: {url}")
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req) as response:
        return json.loads(response.read().decode('utf-8'))

def test_flow():
    base_url = "http://127.0.0.1:8000"
    
    # 1. Get a valid product from feed
    try:
        # Use a real user_id from logs to ensure feed works
        feed_url = f"{base_url}/v1/feed?user_id=c504751b-2835-4ffb-b2bb-0f6f5f0d17ae&limit=1"
        feed_data = fetch_json(feed_url)
        
        products = feed_data.get("products", [])
        if not products:
            print("Feed returned no products. Cannot test detail.")
            return

        valid_product = products[0]
        valid_id = valid_product["id"]
        print(f"\nFound Valid Product ID: {valid_id}")
        
        # 2. Try to fetch detail for this valid ID
        detail_url = f"{base_url}/v1/product/detail?product_id={valid_id}"
        detail_data = fetch_json(detail_url)
        
        print("\nDetail Fetch Result:")
        print(json.dumps(detail_data, indent=2))
        
        if detail_data.get("success"):
            print("\n✅ API is working correctly for valid products.")
        else:
            print("\n❌ API failed for a known valid product.")

    except Exception as e:
        print(f"\nError: {e}")

if __name__ == "__main__":
    test_flow()
