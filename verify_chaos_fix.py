import json
import re
from main_api import extract_product, _get_content_signature

# Mock message similar to what Chaos Cards might send
mock_msg = {
    "id": "1450000000000000000",
    "channel_id": "1394825979461111980", # Chaos Cards ID
    "content": "Pokemon Trading Card Game: Silver Tempest Booster Pack Available Now!",
    "scraped_at": "2025-12-10T12:00:00Z",
    "raw_data": {
        "embeds": [{
            "title": "Pokemon Trading Card Game: Silver Tempest Booster Pack",
            "description": "Restock alert for Silver Tempest booster packs.",
            "fields": [
                {"name": "Price", "value": "£3.95"},
                {"name": "Status", "value": "In Stock"}
            ],
            "links": [
                {"text": "Buy Now", "url": "https://www.chaoscards.co.uk/prod/pokemon-silver-tempest-booster"}
            ]
        }]
    }
}

# Define a minimal channel map
channel_map = {
    "1394825979461111980": {"name": "Chaos Cards", "category": "UK Stores"}
}

def test_extraction():
    print("--- Testing Product Extraction ---")
    result = extract_product(mock_msg, channel_map)
    
    if not result:
        print("FAIL: extract_product returned None")
        return

    p_data = result["product_data"]
    print(f"Title: {p_data['title']}")
    print(f"Region: {result['region']}")
    print(f"Retailer: {result['category_name']}")
    print(f"Price: {p_data['price']}")
    print(f"Links found: {len(p_data['links']['buy'])}")
    
    if p_data['links']['buy']:
        print(f"Primary Buy URL: {p_data['links']['buy'][0]['url']}")
    
    # Check if links array was used
    if any(l['url'] == "https://www.chaoscards.co.uk/prod/pokemon-silver-tempest-booster" for l in p_data['links']['buy']):
        print("SUCCESS: Buy link correctly extracted from 'links' array!")
    else:
        print("FAIL: Buy link NOT found in 'links' array output.")

def test_signature():
    print("\n--- Testing Signature Uniqueness ---")
    sig1 = _get_content_signature(mock_msg)
    
    # Create a slightly different message (different set)
    mock_msg_2 = json.loads(json.dumps(mock_msg))
    mock_msg_2["raw_data"]["embeds"][0]["title"] = "Pokemon Trading Card Game: Lost Origin Booster Pack"
    mock_msg_2["raw_data"]["embeds"][0]["links"][0]["url"] = "https://www.chaoscards.co.uk/prod/pokemon-lost-origin-booster"
    
    sig2 = _get_content_signature(mock_msg_2)
    
    print(f"Signature 1: {sig1}")
    print(f"Signature 2: {sig2}")
    
    if sig1 != sig2:
        print("SUCCESS: Signatures are unique for different sets!")
    else:
        print("FAIL: Signatures collided!")

if __name__ == "__main__":
    test_extraction()
    test_signature()
