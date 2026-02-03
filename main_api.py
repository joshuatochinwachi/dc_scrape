#!/usr/bin/env python3
"""
main_api.py
Professional FastAPI backend for hollowScan Mobile App.
Provides endpoints for feed, categories, and subscription management.
"""
 
from fastapi import FastAPI, HTTPException, Depends, Query, Header, Body
from fastapi.middleware.cors import CORSMiddleware
import requests
import re
import os
import json
import hashlib
import string
import random
from typing import List, Optional, Dict, Any
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv
from supabase_utils import get_supabase_config, sanitize_text

# Load environment variables first
load_dotenv()

app = FastAPI(title="hollowScan Mobile API", version="1.0.0")

# Enable CORS for mobile development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# -------------------
# CONFIGURATION
# -------------------
URL, KEY = get_supabase_config()
HEADERS = {
    'apikey': KEY,
    'Authorization': f'Bearer {KEY}',
    'Content-Type': 'application/json'
}

# Mirrors telegram_bot.py initial_channels - Expanded for all regions
DEFAULT_CHANNELS = [
    # UK
    {"id": "1367813504786108526", "name": "Collectors Amazon", "url": "https://discord.com/channels/653646362453213205/1367813504786108526", "category": "UK Stores", "enabled": True},
    {"id": "855164313006505994", "name": "Argos Instore", "url": "https://discord.com/channels/653646362453213205/855164313006505994", "category": "UK Stores", "enabled": True},
    {"id": "864504557903937587", "name": "Restocks Online", "url": "https://discord.com/channels/653646362453213205/864504557903937587", "category": "UK Stores", "enabled": True},
    # USA
    {"id": "1385348512681689118", "name": "Amazon", "category": "USA Stores", "enabled": True},
    {"id": "1384205489679892540", "name": "Walmart", "category": "USA Stores", "enabled": True},
    # Canada
    {"id": "1391616295560155177", "name": "Pokemon Center", "category": "Canada Stores", "enabled": True},
    {"id": "1406802285337776210", "name": "Hobbiesville", "category": "Canada Stores", "enabled": True}
]

# -------------------
# IMAGE OPTIMIZATION (mirrors telegram_bot.py)
# -------------------
def optimize_image_url(url: str) -> str:
    """
    Optimize image URLs to force maximum resolution.
    Removes size restrictions from Amazon, eBay, and Discord proxy URLs.
    """
    if not url:
        return url
    
    try:
        # 1. Decode Discord Proxy URLs
        if "images-ext-" in url and "discordapp.net" in url:
            if "/https/" in url:
                url = "https://" + url.split("/https/", 1)[1]
            elif "/http/" in url:
                url = "http://" + url.split("/http/", 1)[1]
        
        # 2. Amazon Image Optimization - Remove size limits
        if any(domain in url for domain in ['media-amazon.com', 'images-amazon.com', 'ssl-images-amazon.com']):
            url = re.sub(r'\._[A-Z_]+[0-9]+_\.', '.', url)
            if "?" in url:
                url = url.split("?")[0]
        
        # 3. eBay Image Optimization - Force max resolution
        if "ebayimg.com" in url:
            if re.search(r's-l\d+\.', url):
                url = re.sub(r's-l\d+\.', 's-l1600.', url)
            if "?" in url:
                url = url.split("?")[0]
        
        # 4. Remove Discord proxy size limits
        if "discordapp.net" in url and "?" in url:
            base = url.split("?")[0]
            url = base
            
    except Exception:
        pass
    
    return url

# -------------------
# DATABASE HELPERS (Using Supabase Schema)
# -------------------
def get_user_by_id(user_id: str) -> Optional[Dict]:
    """Get user from UUID in users table"""
    try:
        response = requests.get(
            f"{URL}/rest/v1/users?id=eq.{user_id}",
            headers=HEADERS,
            timeout=10
        )
        if response.status_code == 200 and response.json():
            return response.json()[0]
    except Exception as e:
        print(f"[DB] Error fetching user: {e}")
    return None

def get_user_by_email(email: str) -> Optional[Dict]:
    """Get user from email in users table"""
    try:
        response = requests.get(
            f"{URL}/rest/v1/users?email=eq.{email}",
            headers=HEADERS,
            timeout=10
        )
        if response.status_code == 200 and response.json():
            return response.json()[0]
    except Exception as e:
        print(f"[DB] Error fetching user by email: {e}")
    return None

def create_user(email: str = None, apple_id: str = None) -> Optional[Dict]:
    """Create new user in users table"""
    try:
        payload = {
            "email": email,
            "apple_id": apple_id,
            "subscription_status": "free",
            "created_at": datetime.now(timezone.utc).isoformat()
        }
        response = requests.post(
            f"{URL}/rest/v1/users",
            headers=HEADERS,
            json=payload,
            timeout=10
        )
        if response.status_code in [200, 201]:
            result = response.json()
            return result[0] if isinstance(result, list) and len(result) > 0 else result
    except Exception as e:
        print(f"[DB] Error creating user: {e}")
    return None

def update_user_v1(user_id: str, data: Dict) -> bool:
    """Update user in users table"""
    try:
        response = requests.patch(
            f"{URL}/rest/v1/users?id=eq.{user_id}",
            headers=HEADERS,
            json=data,
            timeout=10
        )
        return response.status_code in [200, 201, 204]
    except Exception as e:
        print(f"[DB] Error updating user: {e}")
    return False

# -------------------
# AUTHENTICATION HELPERS
# -------------------
def hash_password(password: str) -> str:
    """Hash a password using SHA-256 with salt"""
    salt = os.getenv("AUTH_SALT", "hollow_secret_salt_2024")
    return hashlib.sha256((password + salt).encode()).hexdigest()

# -------------------
# AUTHENTICATION ENDPOINTS
# -------------------
@app.post("/v1/auth/signup")
async def signup(data: Dict = Body(...)):
    """
    Create a new user with email and password.
    """
    email = data.get("email")
    password = data.get("password")
    
    if not email or not password:
        raise HTTPException(status_code=400, detail="Email and password are required")
        
    # Check if user already exists
    existing_user = get_user_by_email(email)
    if existing_user:
        raise HTTPException(status_code=400, detail="User with this email already exists")
        
    # Create user
    hashed = hash_password(password)
    try:
        payload = {
            "email": email,
            "password_hash": hashed,
            "subscription_status": "free",
            "created_at": datetime.now(timezone.utc).isoformat()
        }
        
        # Inject directly via requests
        response = requests.post(
            f"{URL}/rest/v1/users",
            headers={**HEADERS, "Prefer": "return=representation"},
            json=payload,
            timeout=10
        )
        
        if response.status_code in [200, 201]:
            user = response.json()[0] if isinstance(response.json(), list) else response.json()
            return {
                "success": True,
                "user": {
                    "id": user["id"],
                    "email": user["email"],
                    "isPremium": user.get("subscription_status") == "active"
                }
            }
        else:
            print(f"[AUTH] Signup failed: {response.text}")
            raise HTTPException(status_code=500, detail="Failed to create user")
            
    except Exception as e:
        print(f"[AUTH] Signup error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/v1/auth/login")
async def login(data: Dict = Body(...)):
    """
    Login with email and password.
    """
    email = data.get("email")
    password = data.get("password")
    
    if not email or not password:
        raise HTTPException(status_code=400, detail="Email and password are required")
        
    user = get_user_by_email(email)
    if not user:
        # Check if it was an apple_id user just in case
        raise HTTPException(status_code=401, detail="Invalid email or password")
        
    # Verify password
    # If the user was created without a password (apple_id), password_hash might be null
    stored_hash = user.get("password_hash")
    if not stored_hash or stored_hash != hash_password(password):
        raise HTTPException(status_code=401, detail="Invalid email or password")
        
    return {
        "success": True,
        "user": {
            "id": user["id"],
            "email": user["email"],
            "isPremium": user.get("subscription_status") == "active",
            "subscriptionEnd": user.get("subscription_end")
        }
    }

def update_user(user_id: str, updates: Dict) -> bool:
    """Update user in users table"""
    try:
        updates["updated_at"] = datetime.now(timezone.utc).isoformat()
        response = requests.patch(
            f"{URL}/rest/v1/users?id=eq.{user_id}",
            headers=HEADERS,
            json=updates,
            timeout=10
        )
        return response.status_code in [200, 204]
    except Exception as e:
        print(f"[DB] Error updating user: {e}")
    return False

def link_telegram_account(user_id: str, telegram_id: str, telegram_username: str = None) -> Optional[Dict]:
    """Link Telegram account to user via user_telegram_links table"""
    try:
        payload = {
            "user_id": user_id,
            "telegram_id": telegram_id,
            "telegram_username": telegram_username,
            "linked_at": datetime.now(timezone.utc).isoformat()
        }
        response = requests.post(
            f"{URL}/rest/v1/user_telegram_links",
            headers=HEADERS,
            json=payload,
            timeout=10
        )
        if response.status_code in [200, 201]:
            return response.json()[0] if isinstance(response.json(), list) else response.json()
    except Exception as e:
        print(f"[DB] Error linking Telegram: {e}")
    return None

def get_telegram_links_for_user(user_id: str) -> List[Dict]:
    """Get all Telegram links for a user"""
    try:
        response = requests.get(
            f"{URL}/rest/v1/user_telegram_links?user_id=eq.{user_id}",
            headers=HEADERS,
            timeout=10
        )
        if response.status_code == 200:
            return response.json() or []
    except Exception as e:
        print(f"[DB] Error fetching Telegram links: {e}")
    return []

def save_deal(user_id: str, alert_id: str, alert_data: Dict) -> Optional[Dict]:
    """Save deal to saved_deals table"""
    try:
        payload = {
            "user_id": user_id,
            "alert_id": alert_id,
            "alert_data": alert_data,
            "saved_at": datetime.now(timezone.utc).isoformat()
        }
        response = requests.post(
            f"{URL}/rest/v1/saved_deals",
            headers=HEADERS,
            json=payload,
            timeout=10
        )
        if response.status_code in [200, 201]:
            return response.json()[0] if isinstance(response.json(), list) else response.json()
    except Exception as e:
        print(f"[DB] Error saving deal: {e}")
    return None

def get_saved_deals(user_id: str) -> List[Dict]:
    """Get all saved deals for a user"""
    try:
        response = requests.get(
            f"{URL}/rest/v1/saved_deals?user_id=eq.{user_id}",
            headers=HEADERS,
            timeout=10
        )
        if response.status_code == 200:
            return response.json() or []
    except Exception as e:
        print(f"[DB] Error fetching saved deals: {e}")
    return []

def update_user_quota(user_id: str, new_count: int):
    """Update daily free alerts viewed for user"""
    update_user(user_id, {
        "daily_free_alerts_viewed": new_count,
        "last_free_alert_reset": datetime.now(timezone.utc).isoformat()
    })

# Keep old function name for backward compatibility
def get_user_from_db(user_id: str):
    return get_user_by_id(user_id)

# -------------------
# ENDPOINTS
# -------------------

@app.get("/")
async def root():
    return {"status": "online", "app": "hollowScan API", "v": "1.0.0"}

@app.get("/v1/categories")
async def get_categories():
    """
    Fetch categories organized by region.
    Returns structure: { "UK Stores": [...store names...], "USA Stores": [...], "Canada Stores": [...] }
    """
    result = {}
    channels = []
    source = "none"
    
    # Try remote channels.json from Supabase (using authenticated access for private buckets)
    try:
        storage_url = f"{URL}/storage/v1/object/authenticated/monitor-data/discord_josh/channels.json"
        print(f"[CATEGORIES] Attempting remote fetch from: {storage_url[:50]}...")
        channels_response = requests.get(
            storage_url,
            headers=HEADERS,
            timeout=10
        )
        print(f"[CATEGORIES] Remote response status: {channels_response.status_code}")
        if channels_response.status_code == 200:
            channels = channels_response.json() or []
            source = "remote"
            print(f"[CATEGORIES] ✓ Loaded {len(channels)} channels from remote")
        else:
            print(f"[CATEGORIES] Remote request failed with status {channels_response.status_code}")
            if channels_response.text:
                print(f"[CATEGORIES] Response body: {channels_response.text[:200]}")
    except requests.exceptions.Timeout:
        print(f"[CATEGORIES] ✗ Remote channels fetch TIMEOUT (network issue)")
    except requests.exceptions.ConnectionError:
        print(f"[CATEGORIES] ✗ Remote channels fetch CONN ERROR (Supabase unreachable?)")
    except Exception as e:
        print(f"[CATEGORIES] ✗ Remote channels fetch failed: {type(e).__name__}: {e}")
    
    # Try local fallback with multiple common names
    if not channels:
        for filename in ["data/channels_.json", "data/channels.json", "channels.json"]:
            if os.path.exists(filename):
                try:
                    with open(filename, "r") as f:
                        channels = json.load(f)
                    if channels: break
                except: continue
    
    # If still no channels, use defaults
    if not channels:
        channels = DEFAULT_CHANNELS
        source = "defaults"
        print(f"[CATEGORIES] ⚠️ Using DEFAULT_CHANNELS ({len(channels)} channels) - this means Supabase is unreachable!")
    
    # Initialize regions
    result = {
        "UK Stores": [],
        "USA Stores": [],
        "Canada Stores": []
    }
    
    # Parse channels into categories by full region name
    for channel in channels:
        if not channel.get('enabled', True):
            continue
        
        region_name = channel.get('category', 'USA Stores').strip()
        store_name = channel.get('name', 'Unknown')
        
        # Normalize region names
        upper_reg = region_name.upper()
        if 'UK' in upper_reg:
            region_name = 'UK Stores'
        elif 'CANADA' in upper_reg:
            region_name = 'Canada Stores'
        elif 'USA' in upper_reg or 'UNITED STATES' in upper_reg or upper_reg.startswith('US'):
            region_name = 'USA Stores'
        elif upper_reg.startswith('CA') and ('STOR' in upper_reg or len(upper_reg) <= 3):
             region_name = 'Canada Stores'
        else:
            region_name = 'USA Stores'
        
        # Add unique store names (subcategories)
        if store_name not in result[region_name]:
            result[region_name].append(store_name)
    
    # Sort subcategories alphabetically and add "ALL" at the beginning
    for region in result:
        result[region] = sorted(result[region])
        result[region].insert(0, "ALL")  # Add ALL option at top
    
    print(f"[CATEGORIES] ✓ Final categories from {source}: {result}")
    return {"categories": result, "source": source, "channel_count": len(channels)}

# Debug endpoint to check Supabase connectivity
@app.get("/v1/debug/supabase")
async def debug_supabase():
    """Debug endpoint: Check Supabase connection and configuration"""
    diagnostics = {
        "supabase_url": URL[:30] + "..." if URL else "NOT SET",
        "supabase_key_set": bool(KEY),
        "env_vars_loaded": bool(URL and KEY),
        "tests": {}
    }
    
    # Test 1: Storage accessibility (authenticated)
    try:
        test_url = f"{URL}/storage/v1/object/authenticated/monitor-data/discord_josh/channels.json"
        print(f"[DEBUG] Testing storage connectivity...")
        response = requests.head(test_url, headers=HEADERS, timeout=5)
        diagnostics["tests"]["storage_head_request"] = {
            "status": response.status_code,
            "ok": response.status_code < 400
        }
    except Exception as e:
        diagnostics["tests"]["storage_head_request"] = {"error": str(e), "type": type(e).__name__}
    
    # Test 2: Fetch channels.json (authenticated)
    try:
        test_url = f"{URL}/storage/v1/object/authenticated/monitor-data/discord_josh/channels.json"
        print(f"[DEBUG] Fetching channels.json...")
        response = requests.get(test_url, headers=HEADERS, timeout=5)
        diagnostics["tests"]["channels_json_get"] = {
            "status": response.status_code,
            "content_length": len(response.content),
            "is_json": response.headers.get('content-type', '').startswith('application/json'),
            "ok": response.status_code == 200
        }
        if response.status_code != 200:
            diagnostics["tests"]["channels_json_get"]["error"] = response.text[:200]
    except Exception as e:
        diagnostics["tests"]["channels_json_get"] = {"error": str(e), "type": type(e).__name__}
    
    # Test 3: REST API accessibility (check users table)
    try:
        print(f"[DEBUG] Testing REST API...")
        response = requests.get(
            f"{URL}/rest/v1/users?limit=1",
            headers=HEADERS,
            timeout=5
        )
        diagnostics["tests"]["rest_api_users"] = {
            "status": response.status_code,
            "ok": response.status_code < 400
        }
    except Exception as e:
        diagnostics["tests"]["rest_api_users"] = {"error": str(e), "type": type(e).__name__}
    
    return diagnostics

# Debug endpoint to check channel-to-region mapping
@app.get("/v1/debug/channels")
async def debug_channels():
    """Debug endpoint: Show which region each channel is mapped to"""
    channels = []
    channels_source = "unknown"
    
    try:
        storage_url = f"{URL}/storage/v1/object/authenticated/monitor-data/discord_josh/channels.json"
        channels_response = requests.get(
            storage_url,
            headers=HEADERS,
            timeout=10
        )
        if channels_response.status_code == 200:
            channels = channels_response.json() or []
            channels_source = "remote_success"
        else:
            channels_source = f"remote_failed_{channels_response.status_code}"
    except Exception as e:
        channels_source = f"remote_exception_{type(e).__name__}"

    if not channels and os.path.exists("data/channels.json"):
        try:
            with open("data/channels.json", "r") as f:
                channels = json.load(f)
            channels_source = "local_file"
        except Exception as e:
            channels_source = f"local_file_failed_{type(e).__name__}"

    if not channels:
        channels = DEFAULT_CHANNELS
        channels_source = "defaults"

    # Build mapping
    mapping = {"UK Stores": [], "USA Stores": [], "Canada Stores": []}
    unknown = []
    known_ids = set()
    
    for c in channels:
        if not c.get('enabled', True):
            continue
            
        ch_id = c.get('id')
        ch_name = c.get('name')
        raw_region = c.get('category', 'USA Stores').strip()
        known_ids.add(ch_id)
        
        # Normalize region
        if raw_region == 'UK Stores' or 'UK' in raw_region.upper():
            msg_region = 'UK Stores'
        elif raw_region == 'Canada Stores' or 'CANADA' in raw_region.upper():
            msg_region = 'Canada Stores'
        elif raw_region == 'USA Stores' or 'USA' in raw_region.upper():
            msg_region = 'USA Stores'
        else:
            msg_region = 'UNKNOWN'
            unknown.append({'id': ch_id, 'name': ch_name, 'raw_category': raw_region})
        
        if msg_region in mapping:
            mapping[msg_region].append({'id': ch_id, 'name': ch_name, 'raw_category': raw_region})
    
    # Find orphaned channel IDs (in messages but not in channels.json)
    try:
        messages_response = requests.get(
            f"{URL}/rest/v1/discord_messages?select=channel_id&order=scraped_at.desc&limit=300",
            headers=HEADERS,
            timeout=15
        )
        if messages_response.status_code == 200:
            messages = messages_response.json()
            orphaned_ids = {}
            for msg in messages:
                ch_id = str(msg.get('channel_id', ''))
                if ch_id and ch_id not in known_ids:
                    orphaned_ids[ch_id] = orphaned_ids.get(ch_id, 0) + 1
            
            # Show top orphaned IDs
            orphaned_list = sorted(orphaned_ids.items(), key=lambda x: x[1], reverse=True)[:10]
            orphaned_detail = [{"id": ch_id, "message_count": count} for ch_id, count in orphaned_list]
        else:
            orphaned_detail = []
    except Exception as e:
        print(f"[DEBUG] Error fetching orphaned IDs: {e}")
        orphaned_detail = []
    
    return {
        "total_channels": len(known_ids),
        "channels_source": channels_source,
        "mapping": mapping,
        "unknown_regions": unknown,
        "orphaned_channel_ids": orphaned_detail
    }

# -------------------
# DEDUPLICATION HELPER (mirrors telegram_bot.py)
# -------------------
def _clean_text_for_sig(text: str) -> str:
    """Standardize text for comparison by removing mentions, special chars, and extra space"""
    if not text: return ""
    # Remove Discord mentions <@...>, <@&...>, <#...>
    text = re.sub(r'<@&?\d+>|<#\d+>', '', text)
    # Remove specific tags like @Unfiltered Restocks or similar common mentions
    text = re.sub(r'@[A-Za-z0-9_]+\b', '', text)
    # Remove common separators
    text = text.replace('|', '').replace('[', '').replace(']', '')
    # Normalize whitespace and lowercase
    return " ".join(text.lower().split()).strip()

def _get_content_signature(msg: Dict) -> str:
    """Generate a signature for content-based deduplication (Retailer + Title + Price)"""
    try:
        raw = msg.get("raw_data", {})
        embed = raw.get("embed") or {}
        content = msg.get("content", "")
        
        retailer = ""
        title = ""
        price = ""
        
        # 1. Try Embed extraction
        if embed.get("author"):
            retailer = embed["author"].get("name", "")
        
        title = embed.get("title", "")
        
        # Extract price from embed fields
        for field in embed.get("fields", []):
            name = (field.get("name") or "").lower()
            if "price" in name:
                price = field.get("value", "")
                break
        
        # 2. FALLBACK: Parse plain text content if embed data missing
        if not retailer or not title or not price:
            # Pattern: "Product Name | Retailer | Just restocked for £XX.XX" (mentions removed by cleaner)
            if content and "|" in content:
                parts = [p.strip() for p in content.split("|")]
                if len(parts) >= 2:
                    # Search for price anywhere in content first
                    price_match = re.search(r'[£$€]\s*[\d,]+\.?\d*', content)
                    if price_match: price = price_match.group(0)
                    
                    if not title: title = parts[0]
                    if not retailer and len(parts) > 1: retailer = parts[1]
            
        # Final fallback for Argos or other specific keywords
        if not retailer and "Argos" in content:
            retailer = "Argos Instore"
            
        # Clean and hash
        # Clean and hash
        c_retailer = _clean_text_for_sig(retailer)
        c_title = _clean_text_for_sig(title)
        
        # Aggressive cleaning: use only first 25 chars of title to catch similar restock variants
        f_title = c_title[:25].strip()
        
        # Price cleaning: extract raw number
        num_match = re.search(r'[\d,]+\.?\d*', price)
        c_price = num_match.group(0).replace(',', '') if num_match else price.strip()
        
        raw_sig = f"{c_retailer}|{f_title}|{c_price}"
        
        if len(raw_sig) < 8: # Too weak, fallback to content hash
            return hashlib.md5(content.encode()).hexdigest() if content else str(msg.get("id"))
            
        return hashlib.md5(raw_sig.encode()).hexdigest()
    except Exception as e:
        return str(msg.get("id"))

def _clean_display_text(text: str) -> str:
    """Clean text for display by removing mentions, IDs, and ugly separators"""
    if not text: return ""
    # Remove Discord mentions <@...>, <@&...>, <#...>
    text = re.sub(r'<@&?\d+>|<#\d+>', '', text)
    # Remove specific tags at start like @Unfiltered Restocks | 
    text = re.sub(r'^[ \t]*@[A-Za-z0-9_ ]+([|:-]|$)', '', text)
    # Remove any @word mentions
    text = re.sub(r'@[A-Za-z0-9_]+\b', '', text)
    # Strip common separators if they are left at start/end
    text = text.strip().strip('|').strip(':').strip('-').strip()
    return text

# Helper for Feed and Alerts
def extract_product(msg, channel_map):
    raw = msg.get("raw_data", {})
    embed = raw.get("embed") or {}
    
    # Get channel info
    ch_id = str(msg.get("channel_id", ""))
    ch_info = channel_map.get(ch_id)
    if not ch_info: return None
    
    raw_region = ch_info.get('category', 'USA Stores').strip()
    upper_reg = raw_region.upper()
    if 'UK' in upper_reg: msg_region = 'UK Stores'
    elif 'CANADA' in upper_reg: msg_region = 'Canada Stores'
    else: msg_region = 'USA Stores'
    
    subcategory = ch_info.get('name', 'Unknown')
    
    # Extract and clean title
    raw_title = embed.get("title") or msg.get("content", "")[:100] or "HollowScan Product"
    title = _clean_display_text(raw_title)
    if not title: title = "HollowScan Product"
    
    description = embed.get("description") or ""
    if not description and msg.get("content"):
        description = re.sub(r'<@&?\d+>', '', msg.get("content", "")).strip()
        description = re.sub(r'\[([^\]]+)\]\((https?://[^\)]+)\)', r'\1', description)

    image = None
    if embed.get("images"):
        image = optimize_image_url(embed["images"][0])
    elif embed.get("image") and isinstance(embed["image"], dict):
        image = optimize_image_url(embed["image"].get("url"))
    elif embed.get("thumbnail") and isinstance(embed["thumbnail"], dict):
        image = optimize_image_url(embed["thumbnail"].get("url"))
    elif raw.get("attachments"):
        for att in raw["attachments"]:
            if any(att.get("filename", "").lower().endswith(ext) for ext in ['.png', '.jpg', '.jpeg', '.webp']):
                image = att.get("url")
                break
    if not image and msg.get("content"):
        img_match = re.search(r'(https?://[^\s]+(?:\.png|\.jpg|\.jpeg|\.webp))', msg["content"], re.IGNORECASE)
        if img_match: image = img_match.group(1)

    price, resell, roi = None, None, None
    details = []
    product_data_updates = {}
    
    if embed.get("fields"):
        for field in embed["fields"]:
            name = (field.get("name") or "").strip()
            val = (field.get("value") or "").strip()
            if not name or not val: continue
            if "[" in val and "](" in val: continue
            
            name_lower = name.lower()
            matches = re.findall(r'[\d,.]+', val)
            num = matches[-1].replace(',', '') if matches else None
            
            is_redundant = False
            if num:
                if any(k in name_lower for k in ["price", "retail", "cost"]):
                    if not price: 
                        price = num
                        if "~~" in val or "(" in val: product_data_updates["price_display"] = val
                    is_redundant = True
                elif any(k in name_lower for k in ["resell", "resale", "sell"]):
                    if not resell: resell = num
                    is_redundant = True
                elif any(k in name_lower for k in ["roi", "profit"]):
                    if not roi: roi = num
                    is_redundant = True
            details.append({"label": name, "value": val, "is_redundant": is_redundant})
    
    if not price:
        search_text = (msg.get("content") or "") + " " + description
        patterns = [r'[\$£€]\s*([\d,.]+)', r'(?:Now|Price|Retail|Cost):\s*([\d,.]+)', r'(?:\s|^)([\d]{1,4}\.[\d]{2})(?:\s|$)']
        for p in patterns:
            m = re.search(p, search_text, re.IGNORECASE)
            if m:
                price = m.group(1).replace(',', '')
                break

    all_links = embed.get("links") or []
    categorized_links = {"buy": [], "ebay": [], "fba": [], "other": []}
    primary_buy_url = None
    
    for link in all_links:
        url, text = link.get('url', ''), (link.get('text') or 'Link').strip()
        if not url: continue
        link_obj = {"text": text, "url": url}
        u_low, t_low = url.lower(), text.lower()
        
        if any(k in t_low or k in u_low for k in ['buy', 'shop', 'purchase', 'checkout', 'cart', 'link']):
            categorized_links["buy"].append(link_obj)
            if not primary_buy_url: primary_buy_url = url
        elif any(k in t_low or k in u_low for k in ['sold', 'active', 'google', 'ebay']): categorized_links["ebay"].append(link_obj)
        elif any(k in t_low or k in u_low for k in ['keepa', 'amazon', 'selleramp', 'fba', 'camel']): categorized_links["fba"].append(link_obj)
        else: categorized_links["other"].append(link_obj)
    
    if not primary_buy_url and embed.get("fields"):
         for field in embed["fields"]:
             link_match = re.search(r'\[([^\]]+)\]\((https?://[^\)]+)\)', field.get("value", ""))
             if link_match: primary_buy_url = link_match.group(2); break

    product_data = {
        "title": title[:100], "description": description[:500],
        "image": image or "https://via.placeholder.com/400",
        "price": price, "resell": resell, "roi": roi,
        "buy_url": primary_buy_url or (all_links[0].get('url') if all_links else None),
        "links": categorized_links, "details": details
    }
    product_data.update(product_data_updates)

    return {
        "id": str(msg.get("id")), "region": msg_region,
        "category_name": subcategory, "product_data": product_data,
        "created_at": msg.get("scraped_at"), "is_locked": False
    }

@app.get("/v1/feed")
async def get_feed(
    user_id: str,
    region: Optional[str] = "ALL",
    category: Optional[str] = "ALL",
    offset: int = 0,
    limit: int = 20,
    country: Optional[str] = None,
    search: Optional[str] = None
):
    """
    Paginated feed of products with robust filtering and overfetching.
    """
    # Alias country to region for backward compatibility with some client calls
    if country and (not region or region == "ALL"):
        region = country
        
    # 1. Fetch channel mapping
    channels = []
    try:
        storage_url = f"{URL}/storage/v1/object/authenticated/monitor-data/discord_josh/channels.json"
        channels_response = requests.get(storage_url, headers=HEADERS, timeout=10)
        if channels_response.status_code == 200:
            channels = channels_response.json() or []
    except: pass

    if not channels:
        for filename in ["data/channels_.json", "data/channels.json", "channels.json"]:
            if os.path.exists(filename):
                try:
                    with open(filename, "r") as f:
                        channels = json.load(f)
                    if channels: break
                except: continue

    if not channels:
        channels = DEFAULT_CHANNELS

    # 2. Determine target channel IDs
    target_ids = []
    if region and region.strip().upper() != "ALL":
        req_reg = region.strip().upper()
        if 'UK' in req_reg: norm_reg = 'UK'
        elif 'CANADA' in req_reg or 'CA' in req_reg: norm_reg = 'CANADA'
        else: norm_reg = 'USA'

        for c in channels:
            c_cat = (c.get('category') or '').upper()
            c_name = (c.get('name') or '').upper()
            is_region_match = norm_reg in c_cat or (norm_reg == 'USA' and 'US' in c_cat)
            
            if category and category.strip().upper() != "ALL":
                if is_region_match and c_name == category.strip().upper():
                    target_ids.append(c['id'])
            elif is_region_match:
                target_ids.append(c['id'])
    
    id_filter = ""
    if target_ids:
        id_filter = f"&channel_id=in.({','.join(target_ids)})"

    # Build channel map once
    channel_map = {}
    for c in channels:
        if c.get('enabled', True):
            channel_map[c['id']] = {
                'category': c.get('category', 'USA Stores').strip(),
                'name': c.get('name', 'Unknown').strip()
            }
    for c in DEFAULT_CHANNELS:
        if c['id'] not in channel_map:
            channel_map[c['id']] = {
                'category': c.get('category', 'USA Stores').strip(),
                'name': c.get('name', 'Unknown').strip()
            }

    # 3. Quota enforcement (Check early to set scan depth)
    premium_user = False
    try:
        user = get_user_from_db(user_id)
        if user and user.get("subscription_status") == "active":
            premium_user = True
    except Exception as e:
        print(f"[FEED] Quota check error: {e}")

    # 4. Robust Fetch Loop
    all_products = []
    seen_signatures = set()
    current_sql_offset = offset
    chunks_scanned = 0
    
    # Increase scan depth for free users vs premium, and even more for searches
    base_max = 12 if premium_user else 6
    # Deep scan: 8x depth for searches to find older products
    max_chunks = base_max * 8 if search else base_max
    
    while len(all_products) < limit and chunks_scanned < max_chunks:
        batch_limit = 50
        query = f"order=scraped_at.desc&offset={current_sql_offset}&limit={batch_limit}{id_filter}"
        
        # Add server-side search filter for efficiency if possible
        if search and search.strip():
            keywords = [k.strip() for k in search.split() if len(k.strip()) > 1]
            if keywords:
                # Search both content and the embed title inside JSONB raw_data
                or_parts = []
                for k in keywords:
                    or_parts.append(f"content.ilike.*{k}*")
                    or_parts.append(f"raw_data->embed->>title.ilike.*{k}*")
                    or_parts.append(f"raw_data->embed->>description.ilike.*{k}*")
                
                query += f"&or=({','.join(or_parts)})"
            
        try:
            # Increase timeout for deep search
            response = requests.get(f"{URL}/rest/v1/discord_messages?{query}", headers=HEADERS, timeout=20)
            if response.status_code != 200: break
            
            messages = response.json()
            if not messages: break
            
            for msg in messages:
                # Deduplication logic
                sig = _get_content_signature(msg)
                if sig in seen_signatures:
                    continue
                
                # Extraction
                prod = extract_product(msg, channel_map)
                
                # PROFESSIONAL FILTERING: Skip items with no price or price is 0.0
                if not prod:
                    continue
                
                p_data = prod.get("product_data", {})
                price_val = p_data.get("price")
                resale_val = p_data.get("resell")
                
                try:
                    p_num = float(str(price_val or 0).replace(',', ''))
                    r_num = float(str(resale_val or 0).replace(',', ''))
                    if p_num == 0 and r_num == 0:
                        # Skip items with no price info
                        continue
                except (ValueError, TypeError):
                    # If we can't parse the price, skip it if it's completely missing
                    if not price_val and not resale_val:
                        continue

                # Search Filter (In-memory verification)
                if search and search.strip():
                    search_keywords = [k.lower().strip() for k in search.split() if k.strip()]
                    
                    # Target fields for search
                    title_low = prod["product_data"]["title"].lower()
                    desc_low = prod["product_data"]["description"].lower()
                    cat_low = prod["category_name"].lower()
                    ret_low = (prod.get("product_data", {}).get("retailer") or "").lower()
                    
                    # Match if ANY keyword appears in ANY field
                    match_found = False
                    for kw in search_keywords:
                        if kw in title_low or kw in desc_low or kw in cat_low or kw in ret_low:
                            match_found = True
                            break
                    
                    if not match_found: continue

                # Double check region/cat filters in memory (Post-extraction)
                if region and region.strip().upper() != "ALL":
                    if prod["region"].strip() != region.strip(): continue
                if category and category.strip().upper() != "ALL":
                    if prod["category_name"].upper().strip() != category.upper().strip(): continue
                
                all_products.append(prod)
                seen_signatures.add(sig)
                if len(all_products) >= limit: break
                
            current_sql_offset += len(messages)
            chunks_scanned += 1
            if len(messages) < batch_limit: break # End of database
        except Exception as e:
            print(f"[FEED] Error in batch fetch: {e}")
            break

    # 5. Result Trimming for Free Tier
    
    # If not premium, strictly limit total visible to 4 across all pages
    if not premium_user:
        # If offset is already 4 or more, don't return any more products
        if offset >= 4:
            return {
                "products": [],
                "next_offset": offset,
                "has_more": False,
                "is_premium": False,
                "total_count": offset + len(all_products) # Hint for paywall
            }
        
        # Limit this batch so total doesn't exceed 4
        all_products = all_products[:4 - offset]
        for product in all_products:
            product["is_locked"] = False # Ensure the first 4 are always UNLOCKED

    print(f"[FEED] Scan complete. Found {len(all_products)} products after scanning {current_sql_offset - offset} messages.")
    
    return {
        "products": all_products,
        "next_offset": current_sql_offset,
        "has_more": premium_user and (len(all_products) >= limit),
        "is_premium": premium_user,
        "total_count": 100 # Static hint for "100+ more deals" or similar
    }

@app.get("/v1/feed_old")
async def get_feed_legacy(
    user_id: str,
    region: Optional[str] = "ALL",
    category: Optional[str] = "ALL",
    offset: int = 0,
    limit: int = 20
):
    # This remains for anyone still using the old array-only format if needed
    result = await get_feed(user_id, region, category, offset, limit)
    return result["products"]

@app.get("/v1/alerts/{alert_id}")
async def get_alert_detail(alert_id: str, user_id: str):
    """Detailed product view with quota enforcement."""
    user = get_user_from_db(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
        
    is_premium = user.get("subscription_status") == "active"
    current_views = user.get("daily_free_alerts_viewed", 0)
    
    # 1. Quota Check
    if not is_premium and current_views >= 4:
        raise HTTPException(status_code=403, detail="Daily free limit reached. Subscribe for unlimited access.")
        
    # 2. Fetch Alert
    response = requests.get(
        f"{URL}/rest/v1/alerts?id=eq.{alert_id}",
        headers=HEADERS,
        timeout=10
    )
    
    if response.status_code != 200 or not response.json():
        raise HTTPException(status_code=404, detail="Alert not found")
        
    alert = response.json()[0]
    
    # 3. Increment Counter if viewing for the first time today (simple logic for now)
    if not is_premium:
        update_user_quota(user_id, current_views + 1)
        
    return alert

@app.get("/v1/user/status")
async def get_user_status(user_id: str):
    """Check subscription status and daily quota."""
    user = get_user_from_db(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
        
    return {
        "status": user.get("subscription_status"),
        "views_used": user.get("daily_free_alerts_viewed", 0),
        "views_limit": 4,
        "is_premium": user.get("subscription_status") == "active"
    }

def generate_link_key() -> str:
    """Generate a random 6-character alphanumeric link key"""
    chars = string.ascii_uppercase + string.digits
    return ''.join(random.choice(chars) for _ in range(6))

def load_pending_links() -> Dict:
    """Load pending Telegram links from file"""
    links_file = "data/pending_telegram_links.json"
    if os.path.exists(links_file):
        try:
            with open(links_file, 'r') as f:
                return json.load(f)
        except Exception as e:
            print(f"[TELEGRAM] Error loading pending links: {e}")
    return {}

def save_pending_links(links: Dict) -> bool:
    """Save pending Telegram links to file"""
    links_file = "data/pending_telegram_links.json"
    try:
        os.makedirs(os.path.dirname(links_file), exist_ok=True)
        with open(links_file, 'w') as f:
            json.dump(links, f, indent=2)
        return True
    except Exception as e:
        print(f"[TELEGRAM] Error saving pending links: {e}")
        return False

@app.post("/v1/user/telegram/generate-key")
async def generate_telegram_link_key(user_id: str = Query(...)):
    """
    Generate a link key for Telegram account linking.
    User sends this key to the bot with /link command.
    
    Args:
        user_id: UUID of app user
    
    Returns:
        Link key and instructions
    """
    try:
        print(f"[TELEGRAM] Generating link key for user {user_id}")
        
        # 1. Verify user exists
        user = get_user_by_id(user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        # 2. Generate unique key
        link_key = generate_link_key()
        
        # 3. Store in pending links with expiry (15 minutes)
        pending_links = load_pending_links()
        pending_links[link_key] = {
            "user_id": user_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "expires_at": (datetime.now(timezone.utc) + timedelta(minutes=15)).isoformat(),
            "used": False
        }
        
        if not save_pending_links(pending_links):
            raise HTTPException(status_code=500, detail="Failed to save link key")
        
        print(f"[TELEGRAM] Generated key {link_key} for user {user_id}")
        
        return {
            "success": True,
            "link_key": link_key,
            "message": f"Send this message to @Hollowscan_bot: /link {link_key}",
            "expires_in_minutes": 15
        }
            
    except HTTPException:
        raise
    except Exception as e:
        print(f"[TELEGRAM] Error generating link key: {e}")
        raise HTTPException(status_code=500, detail=f"Error generating link key: {str(e)}")

@app.get("/v1/user/telegram/link-status")
async def check_telegram_link_status(user_id: str = Query(...)):
    """
    Check if user's pending Telegram link has been completed.
    
    Args:
        user_id: UUID of app user
    
    Returns:
        Link status and user info if linked
    """
    try:
        pending_links = load_pending_links()
        
        # Check if any pending link matches this user
        for link_key, link_info in pending_links.items():
            if link_info['user_id'] == user_id and link_info.get('used'):
                # Link was completed
                print(f"[TELEGRAM] Link confirmed for user {user_id}")
                
                # Get the linked telegram chat id from database
                telegram_links = get_telegram_links_for_user(user_id)
                if telegram_links:
                    latest_link = telegram_links[-1]  # Most recent link
                    return {
                        "success": True,
                        "linked": True,
                        "telegram_id": latest_link.get('telegram_id'),
                        "telegram_username": latest_link.get('telegram_username'),
                        "is_premium": latest_link.get('is_premium', False)
                    }
        
        # Not yet linked
        return {
            "success": True,
            "linked": False,
            "message": "Waiting for you to send the link command to the Telegram bot"
        }
            
    except Exception as e:
        print(f"[TELEGRAM] Error checking link status: {e}")
        raise HTTPException(status_code=500, detail=f"Error checking link status: {str(e)}")

@app.post("/v1/user/telegram/link")
async def link_telegram_account_endpoint(user_id: str = Query(...), telegram_chat_id: int = Query(...), telegram_username: str = Query(None)):
    """
    Link a Telegram account to user profile using user_telegram_links table.
    Checks if user has active premium on Telegram bot and syncs status.
    
    Args:
        user_id: UUID of app user
        telegram_chat_id: Telegram chat ID (from bot /start command)
        telegram_username: Optional Telegram username
    
    Returns:
        Updated user subscription status and link info
    """
    try:
        print(f"[TELEGRAM] Linking user {user_id} to chat_id {telegram_chat_id}")
        
        # 1. Verify user exists
        user = get_user_by_id(user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        # 2. Load telegram bot users from data file to check premium status
        telegram_users_path = "data/bot_users.json"
        is_telegram_premium = False
        telegram_expiry = None
        
        if os.path.exists(telegram_users_path):
            with open(telegram_users_path, 'r') as f:
                telegram_users = json.load(f)
                chat_id_str = str(telegram_chat_id)
                telegram_user_data = telegram_users.get(chat_id_str, {})
                
                # Check if premium (expiry in future)
                if telegram_user_data and 'expiry' in telegram_user_data:
                    try:
                        expiry_date = datetime.fromisoformat(telegram_user_data['expiry'].replace('Z', '+00:00'))
                        if expiry_date > datetime.now(timezone.utc):
                            is_telegram_premium = True
                            telegram_expiry = telegram_user_data['expiry']
                            print(f"[TELEGRAM] User is PREMIUM until {telegram_expiry}")
                    except Exception as e:
                        print(f"[TELEGRAM] Error parsing expiry: {e}")
        
        # 3. Store Telegram link in user_telegram_links table
        link_result = link_telegram_account(
            user_id=user_id,
            telegram_id=str(telegram_chat_id),
            telegram_username=telegram_username
        )
        
        if not link_result:
            raise HTTPException(status_code=500, detail="Failed to save Telegram link")
        
        # 4. If premium on Telegram, update subscription in users table
        if is_telegram_premium:
            update_user(user_id, {
                "subscription_status": "active",
                "subscription_end": telegram_expiry,
                "subscription_source": "telegram"
            })
            print(f"[TELEGRAM] User {user_id} upgraded to premium")
        
        # 5. Return response
        return {
            "success": True,
            "message": "Telegram account linked" + (" and premium status synced!" if is_telegram_premium else ""),
            "is_premium": is_telegram_premium,
            "premium_until": telegram_expiry,
            "telegram_chat_id": telegram_chat_id,
            "telegram_username": telegram_username
        }
            
    except HTTPException:
        raise
    except Exception as e:
        print(f"[TELEGRAM] Error linking account: {e}")
        raise HTTPException(status_code=500, detail=f"Error linking Telegram account: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
