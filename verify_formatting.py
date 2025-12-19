import sys
import os
# Add current dir to path to import telegram_bot
sys.path.append(os.getcwd())

from telegram_bot import format_telegram_message, is_duplicate_source, CHANNEL_COLLECTORS, CHANNEL_ARGOS, CHANNEL_RESTOCKS

def test_filtering():
    print("\n--- Testing Filtering (Profit Pinger) ---")
    msg_bad = {
        "content": "Alert from Profitable Pinger",
        "raw_data": {"embed": {"fields": [{"name": "Source", "value": "Profitable Pinger"}]}}
    }
    if is_duplicate_source(msg_bad): print("✅ Profit Pinger correctly filtered")
    else: print("❌ Profit Pinger FAILED to filter")

    msg_good = {
        "content": "Good alert",
        "raw_data": {"embed": {"fields": [{"name": "Source", "value": "Amazon"}]}}
    }
    if not is_duplicate_source(msg_good): print("✅ Good alert allowed")
    else: print("❌ Good alert INCORRECTLY filtered")

def test_collectors_na():
    print("\n--- Testing Collectors (Leading N/A removal) ---")
    msg = {
        "channel_id": CHANNEL_COLLECTORS,
        "content": "",
        "scraped_at": "2025-12-19T10:00:00",
        "raw_data": {
            "author": {"name": "Amazon UK V3"}, # Known Author
            "embed": {
                "title": "Clean Product",
                "fields": [
                    {"name": "Price", "value": "N/A"}, # Should be hidden
                    {"name": "Stock", "value": "5"}
                ]
            }
        }
    }
    text, _, _ = format_telegram_message(msg)
    print(text)
    if "Price:</b>" not in text: print("✅ N/A Price hidden")
    else: print("❌ N/A Price SHOWING")
    if "Stock:</b> 5" in text: print("✅ Stock showing")
    else: print("❌ Stock missing")

def test_unknown_author():
    print("\n--- Testing Unknown Author Removal ---")
    msg = {
        "channel_id": "999999", # Generic
        "content": "",
        "scraped_at": "2025-12-19T10:00:00",
        "raw_data": {
            "author": {"name": "Unknown"}, 
            "embed": {
                "title": "Good Product",
                "description": "Desc"
            }
        }
    }
    text, _, _ = format_telegram_message(msg)
    print(text)
    if "Unknown" not in text: print("✅ Unknown author hidden")
    else: print("❌ Unknown author showing")

if __name__ == "__main__":
    test_filtering()
    test_collectors_na()
    test_unknown_author()
