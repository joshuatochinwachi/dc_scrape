import json
import re
import hashlib

# --- FUNCTIONS COPIED FROM main_api.py FOR STANDALONE TESTING ---

def _clean_text_for_sig(text: str) -> str:
    if not text: return ""
    text = re.sub(r'<@&?\d+>|<#\d+>', '', text)
    text = re.sub(r'@[A-Za-z0-9_]+\b', '', text)
    text = text.replace('|', '').replace('[', '').replace(']', '')
    return " ".join(text.lower().split()).strip()

def _get_content_signature(msg: dict) -> str:
    try:
        raw = msg.get("raw_data", {})
        embeds = raw.get("embeds", [])
        embed = raw.get("embed") or (embeds[0] if embeds else {})
        content = msg.get("content", "")
        retailer = embed.get("author", {}).get("name", "") if embed.get("author") else ""
        title = embed.get("title", "")
        price = ""
        for field in embed.get("fields", []):
            name = (field.get("name") or "").lower()
            if "price" in name:
                price = field.get("value", "")
                break
        
        c_retailer = _clean_text_for_sig(retailer)
        c_title = _clean_text_for_sig(title)
        f_title = c_title[:60].strip()
        desc_snippet = _clean_text_for_sig(embed.get("description", ""))[:15]
        
        num_match = re.search(r'[\d,]+\.?\d*', price)
        c_price = num_match.group(0).replace(',', '') if num_match else price.strip()
        
        raw_sig = f"{c_retailer}|{f_title}|{c_price}|{desc_snippet}"
        if len(raw_sig) < 8: return hashlib.md5(content.encode()).hexdigest() if content else str(msg.get("id"))
        return hashlib.md5(raw_sig.encode()).hexdigest()
    except Exception as e:
        print(f"Sig error: {e}")
        return str(msg.get("id"))

def _clean_display_text(text: str) -> str:
    if not text: return ""
    text = re.sub(r'<@&?\d+>|<#\d+>', '', text)
    text = re.sub(r'^[ \t]*@[A-Za-z0-9_ ]+([|:-]|$)', '', text)
    text = re.sub(r'@[A-Za-z0-9_]+\b', '', text)
    text = text.strip().strip('|').strip(':').strip('-').strip()
    return text

def optimize_image_url(url: str) -> str:
    return url # Mock

def extract_product(msg, channel_map):
    raw = msg.get("raw_data", {})
    embeds = raw.get("embeds", [])
    embed = raw.get("embed") or (embeds[0] if embeds else {})
    ch_id = str(msg.get("channel_id", ""))
    ch_info = channel_map.get(ch_id)
    if not ch_info:
        ch_info = {"name": "HollowScan Deal", "category": "USA Stores"}
        content = msg.get("content", "")
        if "£" in content or "chaos" in content.lower():
            ch_info["category"] = "UK Stores"

    raw_region = ch_info.get('category', 'USA Stores').strip()
    upper_reg = raw_region.upper()
    if 'UK' in upper_reg: msg_region = 'UK Stores'
    elif 'CANADA' in upper_reg: msg_region = 'Canada Stores'
    else: msg_region = 'USA Stores'

    subcategory = ch_info.get('name', 'Unknown')
    raw_title = embed.get("title") or msg.get("content", "")[:100] or "HollowScan Product"
    title = _clean_display_text(raw_title)
    if not title: title = "HollowScan Product"

    description = embed.get("description") or ""
    image = None
    if embed.get("images"): image = optimize_image_url(embed["images"][0])
    elif embed.get("image") and isinstance(embed["image"], dict): image = optimize_image_url(embed["image"].get("url"))

    price, resell, roi, was_price = None, None, None, None
    details = []
    product_data_updates = {}

    if embed.get("fields"):
        for field in embed["fields"]:
            name = (field.get("name") or "").strip().lower()
            val = (field.get("value") or "").strip()
            if "price" in name: price = val

    all_links = []
    # Dedicated Links Array (from archiver) - THIS IS THE FIX
    if embed.get("links"):
        for link in embed["links"]:
            l_url = link.get("url")
            l_text = link.get("text") or "Link"
            if l_url and l_url.startswith("http"):
                all_links.append({"url": l_url, "text": l_text})

    categorized_links = {"buy": [], "other": []}
    primary_buy_url = None

    for link in all_links:
        url, text = link.get('url', ''), link.get('text', 'Link')
        if "chaoscards" in url or "buy" in text.lower():
            categorized_links["buy"].append({"text": text, "url": url})
            if not primary_buy_url: primary_buy_url = url

    product_data = {
        "title": title[:100], "description": description[:500],
        "image": image or "https://via.placeholder.com/400",
        "price": price,
        "buy_url": primary_buy_url or (all_links[0].get('url') if all_links else None),
        "links": categorized_links, "details": details
    }
    return {"id": str(msg.get("id")), "region": msg_region, "category_name": subcategory, "product_data": product_data}

# --- TEST DATA ---

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
                {"name": "Price", "value": "£3.95"}
            ],
            "links": [
                {"text": "Buy Now", "url": "https://www.chaoscards.co.uk/prod/pokemon-silver-tempest-booster"}
            ]
        }]
    }
}

channel_map = {
    "1394825979461111980": {"name": "Chaos Cards", "category": "UK Stores"}
}

def run_tests():
    print("--- Running Standalone Verification ---")
    
    # Test 1: Extraction
    res = extract_product(mock_msg, channel_map)
    print(f"Extracted Store: {res['category_name']}")
    print(f"Extracted Region: {res['region']}")
    
    buy_links = res["product_data"]["links"]["buy"]
    print(f"Buy Links Count: {len(buy_links)}")
    if buy_links:
        print(f"Link 1 URL: {buy_links[0]['url']}")
        if "chaoscards" in buy_links[0]['url']:
            print("✅ SUCCESS: Chaos Cards link correctly extracted from 'links' array.")
        else:
            print("❌ FAIL: Link not correctly extracted.")
    else:
        print("❌ FAIL: No Buy links found.")

    # Test 2: Signature
    sig1 = _get_content_signature(mock_msg)
    
    msg2 = json.loads(json.dumps(mock_msg))
    msg2["raw_data"]["embeds"][0]["title"] = "Pokemon Trading Card Game: LOST ORIGIN SET - Booster Pack"
    sig2 = _get_content_signature(msg2)
    
    print(f"Sig 1: {sig1}")
    print(f"Sig 2: {sig2}")
    if sig1 != sig2:
        print("✅ SUCCESS: Signatures are unique for similar Pokemon titles.")
    else:
        print("❌ FAIL: Signature collision.")

if __name__ == "__main__":
    run_tests()
