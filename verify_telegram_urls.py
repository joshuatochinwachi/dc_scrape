
import os
from dotenv import load_dotenv

def verify_urls():
    load_dotenv()
    
    api_base = os.getenv("API_BASE_URL", "https://web-production-18cf1.up.railway.app")
    print(f"API_BASE_URL from env: {api_base}")
    
    token = "test-token-123"
    redirect_url = f"{api_base}/v1/user/telegram/redirect?code={token}"
    
    print(f"Generated Redirect URL: {redirect_url}")
    
    if "localhost" in redirect_url:
        print("❌ FAILED: 'localhost' found in generated URL!")
    elif not redirect_url.startswith("https://"):
        print("⚠️ WARNING: URL does not start with https:// (required by Telegram for buttons if not localhost)")
    else:
        print("✅ SUCCESS: URL looks correct for production.")

if __name__ == "__main__":
    verify_urls()
