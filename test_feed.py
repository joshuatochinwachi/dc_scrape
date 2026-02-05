import requests
import json

# Test the actual feed endpoint
url = "http://10.246.149.243:8000/v1/feed"
params = {
    "user_id": "test_user",
    "region": "UK",
    "limit": 50
}

print("Fetching feed from API...")
response = requests.get(url, params=params, timeout=15)

if response.status_code == 200:
    data = response.json()
    products = data.get("products", [])
    print(f"\n✅ API Response OK - Found {len(products)} products")
    
    # Search for Nidoking
    nidoking_found = None
    for p in products:
        title = p.get("product_data", {}).get("title", "")
        if "nidoking" in title.lower():
            nidoking_found = p
            break
    
    if nidoking_found:
        print("\n🎉 SUCCESS: Nidoking Tins found in feed!")
        pd = nidoking_found["product_data"]
        print(f"  Title: {pd.get('title')}")
        print(f"  Image: {pd.get('image', 'N/A')[:60]}...")
        print(f"  Price: {pd.get('price', 'N/A')}")
        print(f"  Links: {sum(len(v) for v in pd.get('links', {}).values())} total")
        for cat, links in pd.get("links", {}).items():
            if links:
                print(f"    - {cat}: {[l['text'] for l in links[:3]]}")
    else:
        print("\n⚠️ Nidoking Tins NOT found in feed.")
        print("Showing first 5 products:")
        for i, p in enumerate(products[:5]):
            title = p.get("product_data", {}).get("title", "Unknown")
            print(f"  {i+1}. {title}")
else:
    print(f"\n❌ API Error: {response.status_code}")
    print(response.text[:500])
