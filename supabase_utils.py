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


if __name__ == "__main__":
    print("Supabase Utils Loaded (Direct HTTP API Version)")
    
    # Test connection
    try:
        url, key = get_supabase_config()
        print(f"✅ Config loaded: {url[:30]}...")
    except Exception as e:
        print(f"❌ Config error: {e}")