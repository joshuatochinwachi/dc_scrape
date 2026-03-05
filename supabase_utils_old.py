#!/usr/bin/env python3
"""
supabase_utils.py
FIXED: Uses direct HTTP requests to bypass Supabase client library issues
"""

import os
import json
import pickle
import requests
from typing import Optional, Dict, Any, List
from dotenv import load_dotenv
import re

load_dotenv()

BUCKET_NAME = "monitor-data"

# -------------------
# Configuration
# -------------------
def get_supabase_config():
    """Get Supabase configuration"""
    url = os.getenv("SUPABASE_URL", "").strip()
    key = os.getenv("SUPABASE_KEY", "").strip()
    
    if not url or not key:
        raise RuntimeError("❌ Missing SUPABASE_URL or SUPABASE_KEY")
    
    # Clean URL - remove trailing slash
    if url.endswith('/'):
        url = url[:-1]
    
    return url, key


# -------------------
# CRITICAL: Ultra-Aggressive Text Sanitization
# -------------------
def sanitize_text(text: str, max_length: int = 2000) -> str:
    """
    Ultra-aggressive text cleaning for HTTP safety
    """
    if not text:
        return ""
    
    text = str(text)
    
    # Step 1: Remove ALL problematic characters
    text = text.replace('\x00', '')  # Null bytes
    text = text.replace('\r', ' ')   # Carriage returns
    text = text.replace('\n', ' ')   # Newlines
    text = text.replace('\t', ' ')   # Tabs
    
    # Step 2: Remove ALL control characters (0-31) and DEL (127)
    text = ''.join(char for char in text if ord(char) >= 32 and ord(char) != 127)
    
    # Step 3: Collapse whitespace
    text = ' '.join(text.split())
    
    # Step 5: Limit length
    if len(text) > max_length:
        text = text[:max_length]
    
    return text.strip()


# -------------------
# NEW: Direct HTTP API for Database Operations
# -------------------
def insert_discord_messages_direct(messages: List[Dict[str, Any]], debug: bool = True) -> bool:
    """
    Insert messages using direct HTTP POST to Supabase REST API.
    This bypasses the Python client library which may have serialization issues.
    """
    if not messages:
        return False
    
    url, key = get_supabase_config()
    
    # Ultra-small batch size
    BATCH_SIZE = 5
    total_inserted = 0
    
    # Prepare headers
    headers = {
        'apikey': key,
        'Authorization': f'Bearer {key}',
        'Content-Type': 'application/json',
        'Prefer': 'resolution=ignore-duplicates, return=minimal'
    }
    
    endpoint = f"{url}/rest/v1/discord_messages"
    
    # Clean ALL messages first
    cleaned_messages = []
    for msg in messages:
        try:
            cleaned = {
                "id": int(msg["id"]),
                "channel_id": sanitize_text(str(msg.get("channel_id", "")), 50),
                "content": sanitize_text(msg.get("content", ""), 2000),
                "scraped_at": str(msg.get("scraped_at", ""))[:50],
                "raw_data": msg.get("raw_data", {})
            }
            
            # Only add if valid
            if cleaned["id"] and cleaned["channel_id"]:
                cleaned_messages.append(cleaned)
                
        except Exception as e:
            if debug:
                print(f"   ⚠️ Skipped message: {e}")
    
    if not cleaned_messages:
        if debug:
            print("   ❌ No valid messages after cleaning")
        return False
    
    # Send in tiny batches
    for i in range(0, len(cleaned_messages), BATCH_SIZE):
        batch = cleaned_messages[i : i + BATCH_SIZE]
        
        try:
            # Convert to JSON string
            json_data = json.dumps(batch, ensure_ascii=True)
            
            # Make direct HTTP POST
            response = requests.post(
                endpoint,
                headers=headers,
                data=json_data,
                timeout=30
            )
            
            if response.status_code in [200, 201, 204]:
                total_inserted += len(batch)
                if debug:
                    print(f"   ✅ Batch {i//BATCH_SIZE + 1} uploaded ({len(batch)} msgs)")
            else:
                if debug:
                    print(f"   ❌ Batch {i//BATCH_SIZE + 1} failed: HTTP {response.status_code}")
                    print(f"      Response: {response.text[:200]}")
                
        except Exception as e:
            if debug:
                print(f"   ❌ Batch {i//BATCH_SIZE + 1} error: {e}")
    
    if debug:
        print(f"✅ Inserted {total_inserted}/{len(messages)} messages")
    
    return total_inserted > 0


# -------------------
# Legacy Supabase Client (for storage operations)
# -------------------
def get_supabase_client():
    """Create Supabase client (only for storage operations)"""
    from supabase import create_client
    url, key = get_supabase_config()
    return create_client(url, key)


def upload_file(file_path: str, bucket: str = BUCKET_NAME, remote_path: str = None, debug: bool = True) -> bool:
    if not os.path.exists(file_path):
        return False
    supabase = get_supabase_client()
    file_name = remote_path or os.path.basename(file_path)
    try:
        with open(file_path, "rb") as f:
            data = f.read()
        supabase.storage.from_(bucket).upload(file_name, data, {"upsert": "true"})
        if debug:
            print(f"✅ Uploaded {file_name}")
        return True
    except Exception as e:
        if debug:
            print(f"❌ Upload failed for {file_name}: {e}")
        return False


def download_file(save_path: str, file_name: str, bucket: str = BUCKET_NAME) -> Optional[bytes]:
    try:
        supabase = get_supabase_client()
        data = supabase.storage.from_(bucket).download(file_name)
        os.makedirs(os.path.dirname(save_path) or ".", exist_ok=True)
        with open(save_path, "wb") as f:
            f.write(data)
        return data
    except Exception as e:
        print(f"DL Error {file_name}: {e}")
        return None


# -------------------
# Wrapper function for compatibility
# -------------------
def insert_discord_messages(messages: List[Dict[str, Any]], debug: bool = True) -> bool:
    """
    Main insert function - uses direct HTTP API
    """
    return insert_discord_messages_direct(messages, debug)


# -------------------
# Test individual message
# -------------------
def test_single_message(message: Dict[str, Any]) -> bool:
    """Test if a single message can be inserted"""
    print(f"\n=== Testing Message ID: {message.get('id')} ===")
    
    # Show raw data
    content = message.get('content', '')
    print(f"Original length: {len(content)}")
    print(f"Preview: {content[:100]}")
    
    # Test sanitization
    cleaned = sanitize_text(content)
    print(f"Cleaned length: {len(cleaned)}")
    print(f"Cleaned preview: {cleaned[:100]}")
    
    # Try to insert
    result = insert_discord_messages([message], debug=True)
    print(f"Result: {'✅ Success' if result else '❌ Failed'}")
    
    return result


# -------------------
# CATEGORY SYNC FOR MOBILE APP
# -------------------
def sync_categories_to_sql(categories_list: List[Dict], debug: bool = True) -> bool:
    """
    Sync bot channels to the Supabase SQL 'categories' table.
    Ensures mobile filters match the active channels.
    """
    if not categories_list:
        return False
        
    url, key = get_supabase_config()
    headers = {
        'apikey': key,
        'Authorization': f'Bearer {key}',
        'Content-Type': 'application/json',
        'Prefer': 'resolution=merge-duplicates, return=minimal'
    }
    
    endpoint = f"{url}/rest/v1/categories"
    
    # 1. Map Bot Categories to SQL Structure
    # Bot 'category' field examples: "US Stores", "UK Stores", "Canada Stores"
    # SQL fields: country_code, category_name, display_name
    
    sql_categories = []
    seen = set()
    
    for c in categories_list:
        raw_cat = c.get('category', 'US Stores').upper()
        
        # Determine Country Code
        if 'UK' in raw_cat:
            country = 'UK'
        elif 'CANADA' in raw_cat or 'CA ' in raw_cat:
            country = 'CA'
        else:
            country = 'US'
            
        sub_name = c.get('name', 'Unknown')
        
        # Unique check within this batch
        key_pair = (country, sub_name)
        if key_pair in seen:
            continue
        seen.add(key_pair)
        
        sql_categories.append({
            "country_code": country,
            "category_name": sub_name,
            "display_name": f"{country} {sub_name}",
            "active": True
        })
        
    if not sql_categories:
        return False
        
    try:
        # Upsert into SQL
        response = requests.post(
            endpoint,
            headers=headers,
            json=sql_categories,
            timeout=30
        )
        
        if response.status_code in [200, 201, 204]:
            if debug: print(f"✅ Synced {len(sql_categories)} categories to SQL")
            return True
        else:
            if debug: 
                print(f"❌ Category sync failed: HTTP {response.status_code}")
                print(f"   Response: {response.text}")
            return False
            
    except Exception as e:
        if debug: print(f"❌ Category sync error: {e}")
        return False


# -------------------
# ALERT STORAGE FOR MOBILE APP
# -------------------
def insert_alert(country_code: str, category_name: str, product_data: Dict, debug: bool = True) -> bool:
    """
    Insert a structured product alert into the Supabase SQL 'alerts' table.
    """
    if not product_data:
        return False
        
    url, key = get_supabase_config()
    headers = {
        'apikey': key,
        'Authorization': f'Bearer {key}',
        'Content-Type': 'application/json',
        'Prefer': 'return=minimal'
    }
    
    endpoint = f"{url}/rest/v1/alerts"
    
    payload = {
        "country_code": country_code,
        "category_name": category_name,
        "product_data": product_data
    }
    
    try:
        response = requests.post(
            endpoint,
            headers=headers,
            json=payload,
            timeout=30
        )
        
        if response.status_code in [200, 201, 204]:
            if debug: print(f"✅ Alert stored: {product_data.get('title', 'Product')[:30]}...")
            return True
        else:
            if debug: 
                print(f"❌ Alert storage failed: HTTP {response.status_code}")
                print(f"   Response: {response.text}")
            return False
            
    except Exception as e:
        if debug: print(f"❌ Alert storage error: {e}")
        return False


# -------------------
# TELEGRAM ACCOUNT LINKING
# -------------------
def store_telegram_link_token(token: str, telegram_id: str, debug: bool = True) -> bool:
    """
    Store a temporary link token in Supabase.
    """
    url, key = get_supabase_config()
    headers = {
        'apikey': key,
        'Authorization': f'Bearer {key}',
        'Content-Type': 'application/json',
        'Prefer': 'return=minimal'
    }
    
    endpoint = f"{url}/rest/v1/telegram_link_tokens"
    
    # Expires in 10 minutes
    from datetime import datetime, timedelta, timezone
    expires_at = (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat().replace('+00:00', 'Z')
    
    payload = {
        "token": token,
        "telegram_id": str(telegram_id),
        "expires_at": expires_at
    }
    
    try:
        response = requests.post(endpoint, headers=headers, json=payload, timeout=10)
        if response.status_code in [200, 201, 204]:
            if debug: print(f"✅ Stored link token for {telegram_id}")
            return True
        else:
            if debug: print(f"❌ Failed to store token: {response.status_code} {response.text}")
            return False
    except Exception as e:
        if debug: print(f"❌ Token storage error: {e}")
        return False

def delete_user_telegram_link(telegram_id: str, debug: bool = True) -> bool:
    """
    Unlink a Telegram account via the bot.
    """
    url, key = get_supabase_config()
    headers = {
        'apikey': key,
        'Authorization': f'Bearer {key}'
    }
    
    # DELETE /user_telegram_links?telegram_id=eq.X
    endpoint = f"{url}/rest/v1/user_telegram_links?telegram_id=eq.{telegram_id}"
    
    try:
        response = requests.delete(endpoint, headers=headers, timeout=10)
        if response.status_code in [200, 204]:
            if debug: print(f"✅ Unlinked Telegram ID {telegram_id}")
            return True
        else:
            if debug: print(f"❌ Link deletion failed: {response.status_code} {response.text}")
            return False
    except Exception as e:
        if debug: print(f"❌ Link deletion error: {e}")
        return False

def link_app_user_to_telegram(user_id: str, telegram_id: str, telegram_username: str = None, premium_info: Dict = None, debug: bool = True) -> Dict:
    """
    Robustly link an App User to a Telegram ID.
    Handles duplicates, updates timestamps, and syncs premium status.
    """
    url, key = get_supabase_config()
    headers = {
        'apikey': key,
        'Authorization': f'Bearer {key}',
        'Content-Type': 'application/json',
        'Prefer': 'return=minimal'
    }
    
    from datetime import datetime, timezone
    now_iso = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', 'Z')

    try:
        # 1. Check if already linked
        check_resp = requests.get(
            f"{url}/rest/v1/user_telegram_links?telegram_id=eq.{telegram_id}&select=user_id",
            headers=headers,
            timeout=10
        )
        if check_resp.status_code == 200:
            existing = check_resp.json()
            if existing:
                existing_uid = existing[0]['user_id']
                if existing_uid != user_id:
                    # Telegram account linked to someone else - unlink it first (force re-link)
                    if debug: print(f"[LINK] Telegram {telegram_id} was linked to {existing_uid}, re-linking to {user_id}...")
                    delete_resp = requests.delete(
                        f"{url}/rest/v1/user_telegram_links?telegram_id=eq.{telegram_id}",
                        headers=headers,
                        timeout=10
                    )
                    if delete_resp.status_code not in [200, 204]:
                        if debug: print(f"❌ Failed to unlink old connection: {delete_resp.text}")
                else:
                    # Already linked to correct user
                    if debug: print(f"[LINK] Telegram {telegram_id} already linked to {user_id}, updating...")

        # 2. Upsert Link
        payload = {
            "user_id": user_id,
            "telegram_id": str(telegram_id),
            "telegram_username": telegram_username,
            "linked_at": now_iso
        }
        
        # Using upsert so it updates if exists/re-adds
        upsert_resp = requests.post(
            f"{url}/rest/v1/user_telegram_links", 
            headers={**headers, "Prefer": "resolution=merge-duplicates"},
            json=payload, 
            timeout=10
        )
        
        if upsert_resp.status_code not in [200, 201, 204]:
            if debug: print(f"❌ Link upsert failed: {upsert_resp.text}")
            return {"success": False, "message": "Database link failed."}

        # 3. Sync Premium (if provided)
        # premium_info = {"status": "active", "end": "ISO-DATE", "source": "telegram"}
        if premium_info and premium_info.get("status") == "active":
            user_update = {
                "subscription_status": "active",
                "subscription_end": premium_info.get("end"),
                "subscription_source": premium_info.get("source", "telegram")
            }
            # Only update if user is NOT already premium on app? 
            # Strategy: Overwrite with latest Telegram premium always, or check? 
            # For now, we trust the bot's call to sync.
            
            patch_resp = requests.patch(
                f"{url}/rest/v1/users?id=eq.{user_id}",
                headers=headers,
                json=user_update,
                timeout=10
            )
            if debug: print(f"✅ Synced premium for {user_id}: {patch_resp.status_code}")

        if debug: print(f"✅ Linked {user_id} <-> {telegram_id}")
        return {"success": True, "message": "Successfully linked!"}

    except Exception as e:
        if debug: print(f"❌ Link Exception: {e}")
        return {"success": False, "message": str(e)}


if __name__ == "__main__":
    print("Supabase Utils Loaded (Direct HTTP API Version)")
    
    # Test connection
    try:
        url, key = get_supabase_config()
        print(f"✅ Config loaded: {url[:30]}...")
    except Exception as e:
        print(f"❌ Config error: {e}")