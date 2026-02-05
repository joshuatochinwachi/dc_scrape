import sys
import os
# Add current dir to path to import main_api
sys.path.append(os.getcwd())

from main_api import extract_product

# Mock channel map
channel_map = {
    "855164313006505994": {"id": "855164313006505994", "name": "Argos Instore", "category": "UK Stores"}
}

# Mock message mimicking the Nidoking Tins alert
# Based on the screenshot:
# - Title: Pokmon S&V 10 Team Rocket Nidoking Tins
# - Content has info about stores
# - Buttons for Ebay, Argos, StockX, SnkrDunk
mock_msg = {
    "id": "1458796591874965617",
    "channel_id": "855164313006505994",
    "scraped_at": "2026-02-04T16:29:00Z",
    "raw_data": {
        "embeds": [
            {
                "title": "Pokmon S&V 10 Team Rocket Nidoking Tins",
                "description": "📦 Pokmon S&V 10 Team Rocket Nidoking Tins\n━━━━━━━━━━━━━━━\n\n✅ Stores [Stock]: Sury Basin Argos (Inside Sainsbury's) [2]",
                "images": ["https://cdn.shopify.com/s/files/1/0631/5514/2847/files/A555D25GEN-PUR_1.jpg"]
            }
        ],
        "components": [
            {
                "type": 1,
                "components": [
                    {
                        "type": 2,
                        "label": "⚡ Ebay",
                        "style": 5,
                        "url": "https://ebay.com/sch/i.html?_nkw=Nidoking+Tins"
                    }
                ]
            },
            {
                "type": 1,
                "components": [
                    {
                        "type": 2,
                        "label": "🔗 Argos Instore",
                        "style": 5,
                        "url": "https://www.argos.co.uk/search/nidoking-tins"
                    },
                    {
                        "type": 2,
                        "label": "🔗 StockX",
                        "style": 5,
                        "url": "https://stockx.com/search?s=Nidoking+Tins"
                    }
                ]
            }
        ]
    }
}

print("Running extract_product test...")
result = extract_product(mock_msg, channel_map)

if result:
    print("\n✅ Extraction Success!")
    p_data = result["product_data"]
    print(f"Title: {p_data.get('title')}")
    print(f"Image: {p_data.get('image')}")
    print(f"Buy URL: {p_data.get('buy_url')}")
    print("Links Summary:")
    for cat, links in p_data.get("links", {}).items():
        print(f"  - {cat}: {len(links)} links")
        for l in links:
            print(f"    - [{l['text']}]({l['url']})")
    
    # Check if inclusive filter would pass
    has_image = p_data.get("image") and "placeholder" not in p_data.get("image")
    has_links = bool(p_data.get("buy_url") or (p_data.get("links") and any(p_data["links"].values())))
    has_any_price = bool(p_data.get("price") or p_data.get("resell") or p_data.get("was_price"))
    
    print(f"\nFilter Status: Image={has_image}, Links={has_links}, Price={has_any_price}")
    if has_image or has_links or has_any_price:
        print("🚀 PASSED: Product would be shown in feed.")
    else:
        print("❌ FAILED: Product would still be filtered out.")
else:
    print("\n❌ Extraction Failed (Returned None)")
