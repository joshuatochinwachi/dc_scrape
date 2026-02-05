
import re

def verify_from_env_file():
    env_path = r"c:\Users\HP USER\Documents\Data Analyst\discord\.env"
    api_base = "https://web-production-18cf1.up.railway.app" # Default fallback
    
    if os.path.exists(env_path):
        with open(env_path, 'r') as f:
            content = f.read()
            match = re.search(r'API_BASE_URL=(.*)', content)
            if match:
                api_base = match.group(1).strip()
    
    print(f"Detected API_BASE_URL: {api_base}")
    
    token = "verify-token"
    # Logic from telegram_bot.py (handle_link)
    # redirect_url = f"{api_base}/v1/user/telegram/redirect?code={token}"
    
    if "localhost" in api_base:
        print("❌ FAILED: 'localhost' still in API_BASE_URL!")
    elif not api_base.startswith("https://"):
         print("❌ FAILED: API_BASE_URL should start with https:// for production.")
    else:
        print("✅ SUCCESS: API_BASE_URL is correctly configured for production.")

import os
if __name__ == "__main__":
    verify_from_env_file()
