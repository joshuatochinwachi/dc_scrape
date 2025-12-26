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
        ("2.95", "£2.95"),
        ("£2.95", "£2.95"),
        ("$10.00", "$10.00"),
        ("~~2.95~~ (-32%) 1.99", "<s>£2.95</s> (-32%) £1.99"),
        ("~~£2.95~~ (-32%) £1.99", "<s>£2.95</s> (-32%) £1.99"),
        ("~~15.00~~ 10.00", "<s>£15.00</s> £10.00"),
        ("Sale Price: 45.00", "Sale Price: £45.00"),
        ("Was ~~50~~ now 40", "Was <s>£50</s> now £40"),
    ]
    
    for input_val, expected in test_cases:
        actual = format_price_value(input_val)
        status = "✅" if actual == expected else "❌"
        print(f"{status} Input: '{input_val}'")
        print(f"   Actual:   '{actual}'")
        print(f"   Expected: '{expected}'")

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
                    {"name": "Price", "value": "~~2.95~~ (-32%) 1.99"},
                    {"name": "Stock", "value": "In Stock"}
                ]
            }
        }
    }
    
    text, _, _ = format_telegram_message(msg)
    print(text)
    
    if "<s>£2.95</s> (-32%) £1.99" in text:
        print("✅ Message contains correctly formatted discount")
    else:
        print("❌ Message formatting FAILED")
        
    if "💰 <b>Price:</b> <b><s>£2.95</s> (-32%) £1.99</b>" in text:
        print("✅ Price field is correctly bolded and iconified")
    else:
        print("❌ Price field formatting incorrect")

if __name__ == "__main__":
    test_price_formatting()
    test_full_message_formatting()
