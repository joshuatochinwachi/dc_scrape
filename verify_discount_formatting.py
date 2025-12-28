import os
import sys
from unittest.mock import MagicMock

# Mock environment variables before imports
os.environ["TELEGRAM_TOKEN"] = "mock_token"
os.environ["ADMIN_USER_ID"] = "12345"
os.environ["SUPABASE_URL"] = "https://mock.supabase.co"
os.environ["SUPABASE_KEY"] = "mock_key"

# Add current dir to path to import telegram_bot
sys.path.append(os.getcwd())

# Mock python-telegram-bot components if they are not installed or causing issues
try:
    import telegram
except ImportError:
    sys.modules["telegram"] = MagicMock()
    sys.modules["telegram.ext"] = MagicMock()
    sys.modules["telegram.constants"] = MagicMock()

from telegram_bot import format_price_value, format_telegram_message

def test_price_formatting():
    print("--- Testing format_price_value ---")
    
    test_cases = [
        # Simple prices
        ("2.95", "£2.95"),
        ("£2.95", "£2.95"),
        ("$10.00", "$10.00"),
        
        # Discount patterns - these should NOT produce £2.£99
        ("3.95 (-24%) 2.99", "<s>£3.95</s> (-24%) <b>£2.99</b>"),
        (" 0.95 (-47%) 0.5", "<s>£0.95</s> (-47%) <b>£0.5</b>"),
        ("2.95 (-32%) 1.99", "<s>£2.95</s> (-32%) <b>£1.99</b>"),
        ("£2.95 (-32%) £1.99", "<s>£2.95</s> (-32%) <b>£1.99</b>"),
        
        # Edge cases
        ("50", "£50"),
        ("21.99 GBP", "21.99 GBP"),  # Has currency label, don't add £
        ("154.44 GBP (208.52 USD)", "154.44 GBP (208.52 USD)"),  # Both have currency labels
    ]
    
    all_pass = True
    for input_val, expected in test_cases:
        actual = format_price_value(input_val)
        status = "✅" if actual == expected else "❌"
        if actual != expected:
            all_pass = False
        print(f"{status} Input: '{input_val}'")
        print(f"   Actual:   '{actual}'")
        print(f"   Expected: '{expected}'")
        if actual != expected:
            print(f"   ⚠️  MISMATCH!")
    
    return all_pass

def test_full_message_formatting():
    print("\n--- Testing format_telegram_message with discounted price ---")
    
    msg = {
        "channel_id": "864504557903937587", # CHANNEL_RESTOCKS
        "content": "",
        "scraped_at": "2025-12-26T14:00:00Z",
        "raw_data": {
            "embed": {
                "title": "Sushi Bolts Allen Head (Pk 8) Black - 1 IN",
                "fields": [
                    {"name": "Price", "value": "2.95 (-32%) 1.99"},
                    {"name": "Stock", "value": "In Stock"}
                ]
            }
        }
    }
    
    text, _, _ = format_telegram_message(msg)
    print(text)
    
    # Check for the new format with strikethrough and bold
    if "<s>£2.95</s>" in text and "<b>£1.99</b>" in text:
        print("✅ Message contains correctly formatted discount (strikethrough original, bold discounted)")
        return True
    else:
        print("❌ Message formatting FAILED")
        print("   Looking for: <s>£2.95</s> and <b>£1.99</b>")
        return False

if __name__ == "__main__":
    test_price_formatting()
    test_full_message_formatting()
