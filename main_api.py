#!/usr/bin/env python3
"""
main_api.py - OPTIMIZED
Professional FastAPI backend for hollowScan Mobile App.
Performance optimized for mobile with connection pooling and async operations.
"""

from fastapi import FastAPI, HTTPException, Depends, Query, Header, Body, BackgroundTasks
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
import httpx
import asyncio
import re
import time
from collections import defaultdict

import os
import json
import hashlib
import string
import random
from typing import List, Optional, Dict, Any
from pydantic import BaseModel
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv
from supabase_utils import get_supabase_config, sanitize_text
from functools import lru_cache
from contextlib import asynccontextmanager

from cache_utils import feed_cache, product_list_cache, user_cache, categories_cache


# --- HELPER: Robust Timestamp Parsing ---
def safe_parse_dt(dt_str: str) -> Optional[datetime]:
    if not dt_str: return None
    try:
        # Standard ISO format
        return datetime.fromisoformat(dt_str.replace('Z', '+00:00'))
    except ValueError:
        try:
            # Handle variable microsecond precision by stripping it or fixed 6
            # Basic fallback: First 19 chars (YYYY-MM-DDTHH:MM:SS) + TZ
            # This is a bit brute force but works for > comparison
            base = dt_str.split('.')[0]
            if '+' in dt_str:
                tz = dt_str.split('+')[-1]
                return datetime.fromisoformat(f"{base}+00:00" if tz == '00:00' else f"{base}+{tz}")
            else:
                return datetime.fromisoformat(f"{base}+00:00")
        except:
            return None

load_dotenv()

http_client: Optional[httpx.AsyncClient] = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage app lifespan with persistent HTTP client"""
    global http_client
    limits = httpx.Limits(max_keepalive_connections=50, max_connections=200)
    # INCREASED TIMEOUTS FOR SLOW NETWORKS
    timeout = httpx.Timeout(60.0, connect=30.0, read=60.0, write=60.0, pool=30.0)
    http_client = httpx.AsyncClient(limits=limits, timeout=timeout, http2=False)
    print("[STARTUP] HTTP client initialized (HTTP/2 Disabled for compatibility)")
    
    # Verify DB connectivity (With extra patient 90s timeout for startup)
    try:
        # Ping users table for a more reliable check than the root endpoint
        resp = await http_client.get(f"{URL}/rest/v1/users?limit=1", headers=HEADERS, timeout=90.0)
        if resp.status_code == 200:
            print("[STARTUP] Supabase connection: ✅ OK (Patience wins!)")
        else:
            print(f"[STARTUP] Supabase connection: ⚠️ FAILED (HTTP {resp.status_code})")
            print(f"          Response: {resp.text[:200]}")
    except Exception as e:
        print(f"[STARTUP] Supabase connection: ❌ ERROR ({repr(e)})")
    
    # Start background worker
    asyncio.create_task(background_notification_worker())
    
    yield

    await http_client.aclose()
    print("[SHUTDOWN] HTTP client closed")

app = FastAPI(title="hollowScan Mobile API", version="1.0.0", lifespan=lifespan)

app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"], max_age=3600)

URL, KEY = get_supabase_config()
HEADERS = {'apikey': KEY, 'Authorization': f'Bearer {KEY}', 'Content-Type': 'application/json', 'Prefer': 'return=representation'}
SUPABASE_BUCKET = "monitor-data"

# Global storage for push tokens (Move to DB irl)
USER_PUSH_TOKENS = {} # {user_id: [tokens]}
LAST_PUSH_CHECK_TIME = datetime.now(timezone.utc)
RECENT_ALERTS_LOG = [] # [(signature, timestamp)] to prevent duplicate spam

def _log_push(msg):
    try:
        with open("push_debug.log", "a") as f:
            f.write(f"[{datetime.now().isoformat()}] {msg}\n")
    except: pass

# Cache Stampede Protection: Ensures only 1 request hits DB for a specific filter set
PENDING_READS: Dict[str, asyncio.Event] = {}


DEFAULT_CHANNELS = [
    {"id": "1367813504786108526", "name": "Collectors Amazon", "category": "UK Stores", "enabled": True},
    {"id": "855164313006505994", "name": "Argos Instore", "category": "UK Stores", "enabled": True},
    {"id": "864504557903937587", "name": "Restocks Online", "category": "UK Stores", "enabled": True},
    {"id": "1394825979461111980", "name": "Chaos Cards", "category": "UK Stores", "enabled": True},
    {"id": "1445485120231571730", "name": "Magic Madhouse", "category": "UK Stores", "enabled": True},
    {"id": "1391616507406192701", "name": "Pokemon Center UK", "category": "UK Stores", "enabled": True},
    {"id": "1445485873083711628", "name": "Smyths Toys", "category": "UK Stores", "enabled": True},
    {"id": "1404906840118132928", "name": "Zaavi", "category": "UK Stores", "enabled": True},
    {"id": "1404910797448286319", "name": "John Lewis", "category": "UK Stores", "enabled": True},
    {"id": "1385348512681689118", "name": "Amazon", "category": "USA Stores", "enabled": True},
    {"id": "1384205489679892540", "name": "Walmart", "category": "USA Stores", "enabled": True},
    {"id": "1384205662023848018", "name": "Pokemon Center", "category": "USA Stores", "enabled": True},
    {"id": "1391616295560155177", "name": "Pokemon Center", "category": "Canada Stores", "enabled": True},
    {"id": "1406802285337776210", "name": "Hobbiesville", "category": "Canada Stores", "enabled": True}
]

@lru_cache(maxsize=1024)
def optimize_image_url(url: str) -> str:
    if not url: return url
    try:
        if "images-ext-" in url and "discordapp.net" in url:
            if "/https/" in url: url = "https://" + url.split("/https/", 1)[1]
            elif "/http/" in url: url = "http://" + url.split("/http/", 1)[1]
        if any(domain in url for domain in ['media-amazon.com', 'images-amazon.com', 'ssl-images-amazon.com']):
            url = re.sub(r'\._[A-Z_]+[0-9]+_\.', '.', url)
            if "?" in url: url = url.split("?")[0]
        if "ebayimg.com" in url:
            if re.search(r's-l\d+\.', url): url = re.sub(r's-l\d+\.', 's-l1600.', url)
            if "?" in url: url = url.split("?")[0]
        if "discordapp.net" in url and "?" in url: url = url.split("?")[0]
    except: pass
    return url

def db_retry(retries: int = 5, backoff: float = 1.0):
    """Decorator to retry DB operations on timeout or transient errors"""
    def decorator(func):
        async def wrapper(*args, **kwargs):
            for i in range(retries):
                try:
                    result = await func(*args, **kwargs)
                    # Handle logical failures that should be retried (e.g. 500 statement timeouts)
                    # If the function returns (False, msg) or similar, we can check it
                    if isinstance(result, tuple) and len(result) == 2:
                        success, detail = result
                        if not success and ("57014" in str(detail) or "timeout" in str(detail).lower()):
                            raise httpx.ReadTimeout(f"Logical Timeout: {detail}")
                    return result
                except (httpx.ReadTimeout, httpx.ConnectTimeout) as e:
                    wait = backoff * (2 ** i)
                    print(f"[RETRY] {func.__name__} failed ({type(e).__name__}). attempt {i+1}/{retries} in {wait}s...")
                    await asyncio.sleep(wait)
                except Exception as e:
                    print(f"[DB] Fatal error in {func.__name__}: {repr(e)}")
                    raise e
            print(f"[RETRY] {func.__name__} exhausted all {retries} retries.")
            return None
        return wrapper
    return decorator

@db_retry(retries=3, backoff=1.5)
async def get_user_by_id(user_id: str) -> Optional[Dict]:
    response = await http_client.get(f"{URL}/rest/v1/users?id=eq.{user_id}&select=*", headers=HEADERS)
    if response.status_code == 200 and response.json(): 
        return response.json()[0]
    elif response.status_code >= 500:
        raise httpx.ReadTimeout(f"Server Error {response.status_code}: {response.text}")
    elif response.status_code != 200:
        print(f"[DB] Fetch user (ID) failed: {response.status_code} {response.text[:200]}")
    return None

@db_retry(retries=3, backoff=1.5)
async def get_user_by_email(email: str) -> Optional[Dict]:
    response = await http_client.get(f"{URL}/rest/v1/users?email=eq.{email}&select=*", headers=HEADERS)
    if response.status_code == 200 and response.json(): 
        return response.json()[0]
    elif response.status_code >= 500:
        raise httpx.ReadTimeout(f"Server Error {response.status_code}: {response.text}")
    elif response.status_code != 200:
        print(f"[DB] Fetch user (Email) failed: {response.status_code} {response.text[:200]}")
    return None

async def create_user(email: str = None, apple_id: str = None) -> Optional[Dict]:
    try:
        payload = {"email": email, "apple_id": apple_id, "subscription_status": "free", "created_at": datetime.now(timezone.utc).isoformat()}
        response = await http_client.post(f"{URL}/rest/v1/users", headers=HEADERS, json=payload)
        if response.status_code in [200, 201]:
            result = response.json()
            return result[0] if isinstance(result, list) and len(result) > 0 else result
    except Exception as e: print(f"[DB] Error creating user: {e}")
    return None

@db_retry(retries=2, backoff=2.0)
async def update_user(user_id: str, data: Dict, return_details: bool = False) -> Any:
    data["updated_at"] = datetime.now(timezone.utc).isoformat()
    print(f"[DB] Updating user {user_id} with data: {data}")
    response = await http_client.patch(f"{URL}/rest/v1/users?id=eq.{user_id}", headers=HEADERS, json=data)
    success = response.status_code in [200, 201, 204]
    
    if success:
        print(f"[DB] Update successful for {user_id}")
    else:
        print(f"[DB] Update failed for {user_id}: {response.status_code} {response.text}")
    
    if not success and response.status_code >= 500:
        raise httpx.ReadTimeout(f"Server Error {response.status_code}: {response.text}")
    
    if return_details:
        msg = "Success" if success else f"DB Error {response.status_code}: {response.text}"
        return success, msg
    return success

@db_retry(retries=3, backoff=2.0)
async def delete_user_by_email(email: str) -> bool:
    """Helper to delete a user and all related data by email"""
    user = await get_user_by_email(email)
    if not user:
        return False
    
    user_id = user["id"]
    
    # 1. Delete from Supabase (Cascade handles user_telegram_links and saved_deals)
    response = await http_client.delete(f"{URL}/rest/v1/users?id=eq.{user_id}", headers=HEADERS)
    if response.status_code not in [200, 204]:
        print(f"[DB] Delete user from Supabase failed: {response.status_code} {response.text}")
        return False

    # 2. Cleanup verification codes
    await delete_verification_code_from_supabase(email)

    # 3. Local Push Token Cleanup
    if user_id in USER_PUSH_TOKENS:
        del USER_PUSH_TOKENS[user_id]
        try:
            os.makedirs("data", exist_ok=True)
            with open("data/push_tokens.json", "w") as f:
                json.dump(USER_PUSH_TOKENS, f)
            print(f"[AUTH] Cleaned up push tokens for deleted user {user_id}")
        except: pass

    # 4. Cache Invalidation
    try:
        user_cache.invalidate(f"user_status:{user_id}")
        user_cache.invalidate(f"user_profile:{user_id}")
        print(f"[AUTH] Invalidated cache for deleted user {email}")
    except: pass

    return True

async def verify_premium_status(user_id: str, user_data: Dict = None, background_tasks: BackgroundTasks = None) -> bool:
    """Strictly verify premium status, especially if source is Telegram"""
    try:
        if not user_data:
            user_data = await get_user_by_id(user_id)
        if not user_data: return False

        sub_status = user_data.get("subscription_status")
        sub_end = user_data.get("subscription_end")
        sub_source = user_data.get("subscription_source")
        
        is_premium = False
        if sub_status == "active" and sub_end:
            try:
                end_dt = datetime.fromisoformat(sub_end.replace('Z', '+00:00'))
                if end_dt.tzinfo is None: end_dt = end_dt.replace(tzinfo=timezone.utc)
                if end_dt > datetime.now(timezone.utc):
                    is_premium = True
            except: pass

        # STRICT CHECK for Telegram Source
        if is_premium and sub_source == "telegram":
            # Must verify link still exists
            links_resp = await http_client.get(
                f"{URL}/rest/v1/user_telegram_links?user_id=eq.{user_id}&select=telegram_id",
                headers=HEADERS
            )
            if links_resp.status_code != 200 or not links_resp.json():
                print(f"[STRICT] user {user_id} has no telegram link but is marked premium. Downgrading...")
                is_premium = False
                if background_tasks:
                    background_tasks.add_task(update_user, user_id, {
                        "subscription_status": "free",
                        "subscription_end": None,
                        "subscription_source": None
                    })
            else:
                # Link exists, verify with bot_users.json for immediate revocation
                telegram_id = links_resp.json()[0].get("telegram_id")
                bot_users = await get_bot_users_data()
                tg_user_data = bot_users.get(str(telegram_id), {})
                expiry_str = tg_user_data.get("expiry")
                
                valid_tg_premium = False
                if expiry_str:
                    try:
                        exp_dt = datetime.fromisoformat(expiry_str.replace('Z', '+00:00'))
                        if exp_dt.tzinfo is None: exp_dt = exp_dt.replace(tzinfo=timezone.utc)
                        if exp_dt > datetime.now(timezone.utc):
                            valid_tg_premium = True
                    except: pass
                
                if not valid_tg_premium:
                    print(f"[STRICT] user {user_id} telegram premium expired/revoked in bot_users. Downgrading...")
                    is_premium = False
                    if background_tasks:
                        background_tasks.add_task(update_user, user_id, {
                            "subscription_status": "free",
                            "subscription_end": None,
                            "subscription_source": None
                        })

        return is_premium
    except Exception as e:
        print(f"[STRICT] Error verifying premium for {user_id}: {e}")
        return False

async def link_telegram_account(user_id: str, telegram_id: str, telegram_username: str = None) -> bool:
    try:
        payload = {"user_id": user_id, "telegram_id": telegram_id, "telegram_username": telegram_username, "linked_at": datetime.now(timezone.utc).isoformat()}
        response = await http_client.post(f"{URL}/rest/v1/user_telegram_links", headers=HEADERS, json=payload)
        return response.status_code in [200, 201]
    except Exception as e: print(f"[DB] Error linking Telegram: {e}")
    return False

async def get_telegram_links_for_user(user_id: str) -> List[Dict]:
    try:
        response = await http_client.get(f"{URL}/rest/v1/user_telegram_links?user_id=eq.{user_id}&select=*", headers=HEADERS)
        if response.status_code == 200: return response.json()
    except Exception as e: print(f"[DB] Error fetching Telegram links: {e}")
    return []

@lru_cache(maxsize=1)
def get_auth_salt() -> str:
    return os.getenv("AUTH_SALT", "hollow_secret_salt_2024")

def hash_password(password: str) -> str:
    return hashlib.sha256((password + get_auth_salt()).encode()).hexdigest()

# --- EMAIL VERIFICATION (RESEND) ---
RESEND_API_KEY = os.getenv("RESEND_API_KEY")

async def send_email_via_resend(to_email: str, subject: str, html_content: str):
    if not RESEND_API_KEY:
        print("[RESEND] Error: No API Key configured")
        return False
    
    url = "https://api.resend.com/emails"
    headers = {
        "Authorization": f"Bearer {RESEND_API_KEY}",
        "Content-Type": "application/json"
    }
    # Professional sender address using verified domain
    payload = {
        "from": "hollowScan <no-reply@hollowscan.com>",
        "to": [to_email],
        "subject": subject,
        "html": html_content
    }
    
    try:
        response = await http_client.post(url, headers=headers, json=payload)
        if response.status_code in [200, 201]:
            print(f"[RESEND] Email sent successfully to {to_email}")
            return True
        else:
            print(f"[RESEND] Failed to send email: {response.status_code} {response.text}")
            return False
    except Exception as e:
        print(f"[RESEND] Error sending email: {e}")
        return False

def generate_verification_code() -> str:
    return ''.join(random.choice(string.digits) for _ in range(6))

@db_retry(retries=3, backoff=2.0)
async def get_verification_code_from_supabase(email: str) -> Optional[Dict]:
    response = await http_client.get(f"{URL}/rest/v1/email_verifications?email=eq.{email}&select=*", headers=HEADERS)
    if response.status_code == 200 and response.json():
        return response.json()[0]
    elif response.status_code >= 500:
        raise httpx.ReadTimeout(f"Server Error {response.status_code}: {response.text}")
    elif response.status_code != 200:
        print(f"[DB] Fetch verification failed: {response.status_code} {response.text[:200]}")
    return None

@db_retry(retries=3, backoff=2.0)
async def upsert_verification_code_to_supabase(email: str, code: str, expires_at: str) -> bool:
    payload = {
        "email": email,
        "code": code,
        "expires_at": expires_at,
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    # Use upsert (on_conflict email)
    headers = {**HEADERS, "Prefer": "resolution=merge-duplicates,return=representation"}
    response = await http_client.post(f"{URL}/rest/v1/email_verifications", headers=headers, json=payload)
    success = response.status_code in [200, 201]
    if not success and response.status_code >= 500:
        raise httpx.ReadTimeout(f"Server Error {response.status_code}: {response.text}")
    if not success:
        print(f"[DB] Upsert verification failed: {response.status_code} {response.text[:200]}")
    return success

@db_retry(retries=3, backoff=2.0)
async def delete_verification_code_from_supabase(email: str) -> bool:
    response = await http_client.delete(f"{URL}/rest/v1/email_verifications?email=eq.{email}", headers=HEADERS)
    success = response.status_code in [200, 204]
    if not success and response.status_code >= 500:
        raise httpx.ReadTimeout(f"Server Error {response.status_code}: {response.text}")
    if not success:
        print(f"[DB] Delete verification failed: {response.status_code} {response.text[:200]}")
    return success

async def trigger_email_verification(email: str, force: bool = False):
    """
    Triggers a verification email with cooldown logic.
    force=True bypasses the cooldown (used for manual resends with their own check).
    """
    try:
        # 1. Cooldown Check (60 seconds)
        if not force:
            stored = await get_verification_code_from_supabase(email)
            if stored:
                last_sent = safe_parse_dt(stored.get("created_at"))
                if last_sent:
                    elapsed = (datetime.now(timezone.utc) - last_sent).total_seconds()
                    if elapsed < 60:
                        print(f"[AUTH] Cooldown skip for {email} ({int(elapsed)}s elapsed)")
                        return False

        # 2. Generate and Save Code
        code = generate_verification_code()
        expires_at = (datetime.now(timezone.utc) + timedelta(hours=24)).isoformat()
        
        success = await upsert_verification_code_to_supabase(email, code, expires_at)
        if not success:
            print(f"[AUTH] Failed to save verification code for {email}")
            return False
        
        # 3. Send Email
        html = f"""
        <div style="font-family: sans-serif; padding: 20px; color: #333; max-width: 500px; margin: auto; border: 1px solid #eee; border-radius: 12px;">
            <h2 style="color: #007AFF; text-align: center;">Verify Your Email</h2>
            <p>Welcome to <b>hollowScan</b>! Use the code below to verify your email address and unlock all features:</p>
            <div style="background: #F2F2F7; padding: 20px; border-radius: 12px; font-size: 32px; font-weight: 800; text-align: center; letter-spacing: 10px; color: #1C1C1E; margin: 20px 0;">
                {code}
            </div>
            <p style="font-size: 14px; color: #8E8E93; text-align: center;">This code will expire in 24 hours.</p>
            <hr style="border: 0; border-top: 1px solid #eee; margin: 20px 0;">
            <p style="font-size: 12px; color: #AEAEB2; text-align: center;">If you didn't create an account, you can safely ignore this email.</p>
        </div>
        """
        sent = await send_email_via_resend(email, f"{code} is your hollowScan verification code", html)
        if sent:
            print(f"[AUTH] Verification email sent to {email}")
        return sent
    except Exception as e:
        print(f"[AUTH] Error in trigger_email_verification: {e}")
        return False

@app.post("/v1/auth/signup")
async def signup(background_tasks: BackgroundTasks, data: Dict = Body(...)):
    email = data.get("email")
    password = data.get("password")
    if not email or not password: raise HTTPException(status_code=400, detail="Email and password are required")
    existing = await get_user_by_email(email)
    if existing: raise HTTPException(status_code=400, detail="User with this email already exists")
    hashed = hash_password(password)
    try:
        payload = {"email": email, "password_hash": hashed, "subscription_status": "free", "email_verified": False, "created_at": datetime.now(timezone.utc).isoformat()}
        response = await http_client.post(f"{URL}/rest/v1/users", headers=HEADERS, json=payload)
        if response.status_code in [200, 201]:
            user = response.json()
            if isinstance(user, list) and len(user) > 0: user = user[0]
            # Trigger verification email in background
            background_tasks.add_task(trigger_email_verification, email)
            return {
                "success": True,
                "user": {
                    "id": user["id"],
                    "email": user["email"],
                    "name": user.get("name"),
                    "bio": user.get("bio"),
                    "location": user.get("location"),
                    "avatar_url": user.get("avatar_url"),
                    "is_premium": False,
                    "isPremium": False,
                    "subscription_status": "free",
                    "status": "free",
                    "email_verified": False,
                    "is_verified": False
                }
            }
        else: raise HTTPException(status_code=500, detail="Failed to create user")
    except Exception as e:
        print(f"[AUTH] Signup error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/v1/auth/resend-code")
async def resend_code(background_tasks: BackgroundTasks, data: Dict = Body(...)):
    email = data.get("email")
    if not email: raise HTTPException(status_code=400, detail="Email is required")
    
    # Check cooldown explicitly here to provide user feedback
    stored = await get_verification_code_from_supabase(email)
    if stored:
        last_sent = safe_parse_dt(stored.get("created_at"))
        if last_sent:
            elapsed = (datetime.now(timezone.utc) - last_sent).total_seconds()
            if elapsed < 60:
                remaining = int(60 - elapsed)
                raise HTTPException(status_code=429, detail=f"Please wait {remaining} seconds before resending.")
            
    # Trigger verification email in background (force=True since we did the check above)
    background_tasks.add_task(trigger_email_verification, email, force=True)
    return {"success": True, "message": "Verification code sent! Please check your inbox."}

@app.post("/v1/auth/verify-code")
async def verify_code(data: Dict = Body(...)):
    email = data.get("email")
    code = data.get("code")
    if not email or not code: raise HTTPException(status_code=400, detail="Email and code are required")
    
    stored = await get_verification_code_from_supabase(email)
    if not stored: raise HTTPException(status_code=404, detail="No verification pending for this email")
    
    # Check expiry
    expiry = safe_parse_dt(stored["expires_at"])
    if not expiry or datetime.now(timezone.utc) > expiry:
        raise HTTPException(status_code=400, detail="Code expired. Please request a new one.")
        
    if stored["code"] != code:
        raise HTTPException(status_code=400, detail="Invalid verification code")
        
    # Valid! Update user in DB
    user = await get_user_by_email(email)
    if not user: raise HTTPException(status_code=404, detail="User not found")
    
    success = await update_user(user["id"], {"email_verified": True})
    if not success: raise HTTPException(status_code=500, detail="Failed to update verification status")
    
    # Clean up code and cache
    await delete_verification_code_from_supabase(email)
    try:
        user_cache.invalidate(f"user_status:{user['id']}")
        print(f"[AUTH] Invalidated status cache for {email}")
    except Exception as ce:
        print(f"[AUTH] Cache invalidation skipped: {ce}")
    
    return {"success": True, "message": "Email verified successfully!"}

@app.post("/v1/auth/forgot-password")
async def forgot_password(data: Dict = Body(...)):
    email = data.get("email")
    if not email: raise HTTPException(status_code=400, detail="Email is required")
    
    user = await get_user_by_email(email)
    if not user:
        # Don't reveal if user exists for security, but we'll return success anyway
        return {"success": True, "message": "If an account exists with this email, a reset code has been sent."}
    
    code = generate_verification_code()
    # Shorter expiry for password reset: 1 hour
    expires_at = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
    
    success = await upsert_verification_code_to_supabase(email, code, expires_at)
    if not success: raise HTTPException(status_code=500, detail="Failed to initiate password reset")
    
    html = f"""
    <div style="font-family: sans-serif; padding: 20px; color: #333; max-width: 500px; margin: auto; border: 1px solid #eee; border-radius: 12px;">
        <h2 style="color: #4F46E5; text-align: center;">Reset Your Password</h2>
        <p>You requested to reset your <b>hollowScan</b> password. Use the code below to complete the reset:</p>
        <div style="background: #EEF2FF; padding: 20px; border-radius: 12px; font-size: 32px; font-weight: 800; text-align: center; letter-spacing: 10px; color: #4F46E5; margin: 20px 0;">
            {code}
        </div>
        <p style="font-size: 14px; color: #71717A; text-align: center;">This code will expire in 1 hour.</p>
        <hr style="border: 0; border-top: 1px solid #eee; margin: 20px 0;">
        <p style="font-size: 12px; color: #A1A1AA; text-align: center;">If you didn't request a password reset, you can safely ignore this email.</p>
    </div>
    """
    await send_email_via_resend(email, f"{code} is your hollowScan reset code", html)
    return {"success": True, "message": "Password reset code sent! Please check your inbox."}

@app.post("/v1/auth/reset-password")
async def reset_password(data: Dict = Body(...)):
    email = data.get("email")
    code = data.get("code")
    new_password = data.get("password")
    
    if not email or not code or not new_password:
        raise HTTPException(status_code=400, detail="Email, code, and new password are required")
    
    stored = await get_verification_code_from_supabase(email)
    if not stored: raise HTTPException(status_code=404, detail="No reset pending for this email")
    
    # Check expiry
    expiry = datetime.fromisoformat(stored["expires_at"].replace('Z', '+00:00'))
    if datetime.now(timezone.utc) > expiry:
        raise HTTPException(status_code=400, detail="Code expired. Please request a new one.")
        
    if stored["code"] != code:
        raise HTTPException(status_code=400, detail="Invalid reset code")
        
    # Valid! Update password in DB
    user = await get_user_by_email(email)
    if not user: raise HTTPException(status_code=404, detail="User not found")
    
    hashed = hash_password(new_password)
    success = await update_user(user["id"], {"password_hash": hashed})
    if not success: raise HTTPException(status_code=500, detail="Failed to update password")
    
    # Clean up code
    await delete_verification_code_from_supabase(email)
    
    return {"success": True, "message": "Password updated successfully! You can now log in."}


@app.post("/v1/user/push-token")
async def register_push_token(user_id: str = Query(...), token: str = Query(...)):
    if not user_id or not token: raise HTTPException(status_code=400, detail="User ID and token are required")
    
    # 1. Update local cache/file (fallback)
    if user_id not in USER_PUSH_TOKENS: USER_PUSH_TOKENS[user_id] = []
    if token not in USER_PUSH_TOKENS[user_id]:
        USER_PUSH_TOKENS[user_id].append(token)
        try:
            os.makedirs("data", exist_ok=True)
            with open("data/push_tokens.json", "w") as f:
                json.dump(USER_PUSH_TOKENS, f)
        except: pass
    
    # 2. Update Supabase (Primary)
    # Fetch current tokens first
    user = await get_user_by_id(user_id)
    if user:
        current_tokens = user.get("push_tokens") or []
        if not isinstance(current_tokens, list): current_tokens = []
        if token not in current_tokens:
            current_tokens.append(token)
            await update_user(user_id, {"push_tokens": current_tokens})
            print(f"[PUSH] Registered token for user {user_id} in DB")
            
    return {"success": True}

@app.delete("/v1/user/push-token")
async def unregister_push_token(user_id: str = Query(...), token: str = Query(...)):
    """Unregister a push token for a user (on logout)"""
    if not user_id or not token: raise HTTPException(status_code=400, detail="User ID and token are required")
    
    # 1. Update local cache
    if user_id in USER_PUSH_TOKENS and token in USER_PUSH_TOKENS[user_id]:
        USER_PUSH_TOKENS[user_id].remove(token)
        try:
            with open("data/push_tokens.json", "w") as f:
                json.dump(USER_PUSH_TOKENS, f)
        except: pass
        print(f"[PUSH] Unregistered token for user {user_id} in local cache")

    # 2. Update Supabase
    user = await get_user_by_id(user_id)
    if user:
        current_tokens = user.get("push_tokens") or []
        if not isinstance(current_tokens, list): current_tokens = []
        if token in current_tokens:
            current_tokens.remove(token)
            await update_user(user_id, {"push_tokens": current_tokens})
            print(f"[PUSH] Unregistered token for user {user_id} in DB")
            
    return {"success": True}

@app.post("/v1/user/change-password")
async def change_password(data: Dict = Body(...)):
    """Change user password (requires old password)"""
    user_id = data.get("user_id")
    old_password = data.get("old_password")
    new_password = data.get("new_password")
    
    if not user_id or not old_password or not new_password:
        raise HTTPException(status_code=400, detail="Missing fields")
        
    user = await get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
        
    # Verify old password
    stored_hash = user.get("password_hash")
    if not stored_hash:
        raise HTTPException(status_code=400, detail="Not authorized (No password set)")
        
    if hash_password(old_password) != stored_hash:
        raise HTTPException(status_code=401, detail="Incorrect old password")
        
    # Update to new password
    new_hash = hash_password(new_password)
    success = await update_user(user_id, {"password_hash": new_hash})
    if success:
        return {"success": True, "message": "Password updated successfully"}
    else:
        raise HTTPException(status_code=500, detail="Failed to update password")

@app.delete("/v1/user/account")
async def delete_account(email: str = Query(...)):
    """Delete a user account by email address"""
    if not email:
        raise HTTPException(status_code=400, detail="Email is required")
    
    success = await delete_user_by_email(email)
    if not success:
        # Check if user exists first to provide better error
        user = await get_user_by_email(email)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        raise HTTPException(status_code=500, detail="Failed to delete account")
    
    return {"success": True, "message": f"Account for {email} deleted successfully"}

# Sends push notification via Expo Push API
async def send_expo_push_notification(tokens: List[str], title: str, body: str, data: Dict = None):
    """
    Sends push notification via Expo Push API.
    Sends individually to avoid PUSH_TOO_MANY_EXPERIENCE_IDS if tokens belong to different project IDs.
    """
    if not tokens: return
    
    # Ensure http_client is ready
    if not http_client:
        print("[PUSH] Warning: http_client not initialized, skipping push.")
        return

    # Use a set to avoid duplicates
    unique_tokens = list(set(tokens))
    
    for token in unique_tokens:
        message = {
            "to": token,
            "sound": "default",
            "title": title,
            "body": body,
            "data": data or {},
            "badge": 1,
            "priority": "high",
            "channelId": "default",
            "ttl": 2419200
        }

        try:
            response = await http_client.post(
                "https://exp.host/--/api/v2/push/send",
                headers={
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                },
                json=message
            )
            
            if response.status_code != 200:
                print(f"[PUSH] Expo error for token {token[:15]}...: {response.text}")
            else:
                resp_data = response.json()
                # Expo returns a 'data' array with ticket info
                # If there's an error with a specific token (like it being unregistered), it will be in there
                push_resp = resp_data.get("data", {})
                if isinstance(push_resp, dict): # Single token response
                    if push_resp.get("status") == "error":
                        details = push_resp.get("details", {})
                        error_code = details.get("error")
                        
                        if error_code == "DeviceNotRegistered":
                            print(f"[PUSH] Stale Token Detected: {token[:20]}... Cleaning up from DB.")
                            # Automated Cleanup: Find any user who has this token and remove it
                            try:
                                # We search users WHERE push_tokens contains the token
                                # Supabase 'cs' (contains) operator for JSONB arrays
                                search_response = await http_client.get(
                                    f"{URL}/rest/v1/users?push_tokens=cs.%5B%22{token}%22%5D&select=id,push_tokens",
                                    headers=HEADERS
                                )
                                
                                if search_response.status_code == 200:
                                    affected_users = search_response.json()
                                    for user in affected_users:
                                        uid = user.get("id")
                                        utokens = user.get("push_tokens") or []
                                        if token in utokens:
                                            utokens.remove(token)
                                            await http_client.patch(
                                                f"{URL}/rest/v1/users?id=eq.{uid}",
                                                headers=HEADERS,
                                                json={"push_tokens": utokens}
                                            )
                                            print(f"[PUSH] Automatically removed stale token from user {uid}")
                            except Exception as cleanup_err:
                                print(f"[PUSH] Error during auto-cleanup: {cleanup_err}")
                                
                        elif error_code == "InvalidCredentials":
                            print(f"[PUSH] ALERT: InvalidCredentials for token {token[:20]}... (Check FCM V1 Config or Experience ID mismatch)")
                        else:
                            print(f"[PUSH] Token Error ({error_code}): {token[:20]}...")

        except Exception as e:
            print(f"[PUSH] Error sending to token {token[:15]}...: {e}")


# --- BOT USERS CACHE ---
bot_users_cache = {
    "data": {},
    "last_fetched": 0
}

async def get_bot_users_data():
    """Fetch and cache bot users data from Supabase Storage with Auth"""
    global bot_users_cache
    now = time.time()
    # Cache for 30 seconds (keep it fresh for "immediate" changes)
    if now - bot_users_cache["last_fetched"] < 30 and bot_users_cache["data"]:
        return bot_users_cache["data"]
        
    try:
        # Use authenticated URL and HEADERS for private access
        response = await http_client.get(
            f"{URL}/storage/v1/object/authenticated/{SUPABASE_BUCKET}/discord_josh/bot_users.json",
            headers=HEADERS
        )
        if response.status_code == 200:
            data = response.json()
            bot_users_cache["data"] = data
            bot_users_cache["last_fetched"] = now
            return data
        print(f"[BOT_USERS] Fetch failed: {response.status_code}")
    except Exception as e:
        print(f"[BOT] Error fetching bot users: {e}")
    
    return bot_users_cache.get("data", {})

# --- USER STATUS ENDPOINT ---

@app.get("/v1/user/status")
async def get_user_status(background_tasks: BackgroundTasks, user_id: str = Query(...)):
    """Get user's current subscription and verification status (cached)"""
    
    # Check cache first
    cache_key = f"user_status:{user_id}"
    cached_status = user_cache.get(cache_key)
    
    # SINGLEFLIGHT: Wait if another status check is in progress for this user
    if cached_status is None:
        if cache_key in PENDING_READS:
            print(f"[USER CACHE] {user_id[:8]} Waiting for in-progress status check...")
            await PENDING_READS[cache_key].wait()
            cached_status = user_cache.get(cache_key)
            if cached_status is not None:
                print(f"[USER CACHE] {user_id[:8]} OK - Stampede avoided! Shared status result.")
    
    if cached_status is not None:
        print(f"[USER CACHE] OK Hit for {user_id[:8]}...")
        return cached_status
    
    print(f"[USER CACHE] MISS - Fetching from DB for {user_id[:8]}...")
    
    event = asyncio.Event()
    PENDING_READS[cache_key] = event
    
    try:
        user_data = await get_user_by_id(user_id)
        if not user_data:
            return {"success": False, "message": "User not found"}

        is_premium = await verify_premium_status(user_id, user_data, background_tasks)
        subscription_end = user_data.get("subscription_end")
        
        if not is_premium:
            try:
                links_resp = await http_client.get(
                    f"{URL}/rest/v1/user_telegram_links?user_id=eq.{user_id}&select=telegram_id",
                    headers=HEADERS
                )
                if links_resp.status_code == 200 and links_resp.json():
                    telegram_id = links_resp.json()[0].get("telegram_id")
                    if telegram_id:
                        bot_users = await get_bot_users_data()
                        tg_user_data = bot_users.get(str(telegram_id), {})
                        expiry_str = tg_user_data.get("expiry")
                        if expiry_str:
                            try:
                                exp_dt = datetime.fromisoformat(expiry_str.replace('Z', '+00:00'))
                                if exp_dt.tzinfo is None: 
                                    exp_dt = exp_dt.replace(tzinfo=timezone.utc)
                                if exp_dt > datetime.now(timezone.utc):
                                    is_premium = True
                                    subscription_end = expiry_str
                                    background_tasks.add_task(update_user, user_id, {
                                        "subscription_status": "active",
                                        "subscription_end": expiry_str,
                                        "subscription_source": "telegram"
                                    })
                            except: 
                                pass
            except Exception as e:
                print(f"[STATUS] TG check failed: {e}")

        result = {
            "success": True,
            "is_premium": is_premium,
            "subscription_end": subscription_end,
            "status": "active" if is_premium else "free",
            "subscription_status": "active" if is_premium else "free",
            "email_verified": user_data.get("email_verified", False),
            "is_verified": user_data.get("email_verified", False),
            "email": user_data.get("email"),
            "name": user_data.get("name"),
            "bio": user_data.get("bio"),
            "location": user_data.get("location"),
            "avatar_url": user_data.get("avatar_url"),
            "region": user_data.get("region", "USA Stores"),
            "notification_preferences": user_data.get("notification_preferences") or {
                "enabled": True,
                "regions": ["USA Stores", "UK Stores", "Canada Stores"],
                "categories": [],
                "min_discount_percent": 0
            }
        }
        
        # CACHE THE RESULT
        user_cache.set(cache_key, result)
        return result
        
    except Exception as e:
        print(f"[STATUS] Error: {e}")
        return {"success": False, "message": str(e)}
    finally:
        if cache_key in PENDING_READS and PENDING_READS[cache_key] == event:
            event.set()
            del PENDING_READS[cache_key]

# --- USER PROFILE ENDPOINTS ---

class UserProfileUpdate(BaseModel):
    user_id: str
    name: Optional[str] = None
    location: Optional[str] = None
    bio: Optional[str] = None
    avatar_url: Optional[str] = None

@app.patch("/v1/user/profile")
async def update_user_profile(profile: UserProfileUpdate):
    """Update user profile details"""
    try:
        data = {}
        if profile.name is not None: data["name"] = profile.name
        if profile.location is not None: data["location"] = profile.location
        if profile.bio is not None: data["bio"] = profile.bio
        if profile.avatar_url is not None: data["avatar_url"] = profile.avatar_url
        
        if not data:
            return {"success": False, "message": "No changes provided"}
            
        success, msg = await update_user(profile.user_id, data, return_details=True)
        if success:
            # INVALIDATE CACHE
            user_cache.invalidate(f"user_status:{profile.user_id}")
            return {"success": True, "message": "Profile updated successfully"}
        else:
            return {"success": False, "message": f"Failed: {msg}"}
    except Exception as e:
        print(f"[PROFILE] Error updating: {e}")
        return {"success": False, "message": str(e)}

# --- TELEGRAM LINKING ENDPOINTS ---

@app.get("/v1/user/telegram/link-status")
async def get_telegram_link_status_endpoint(user_id: str = Query(...)):
    """Get user's telegram link status (cached & protected)"""
    
    cache_key = f"tg_link_status:{user_id}"
    cached_link = user_cache.get(cache_key)
    
    # SINGLEFLIGHT: Wait if another check is in progress
    if cached_link is None:
        if cache_key in PENDING_READS:
            print(f"[LINK CACHE] {user_id[:8]} Waiting for link status check...")
            await PENDING_READS[cache_key].wait()
            cached_link = user_cache.get(cache_key)
            if cached_link is not None:
                print(f"[LINK CACHE] {user_id[:8]} OK - Stampede avoided! Shared link status.")
    
    if cached_link is not None:
        return cached_link

    print(f"[LINK CACHE] MISS - Fetching from DB for {user_id[:8]}...")
    
    event = asyncio.Event()
    PENDING_READS[cache_key] = event

    try:
        links = await get_telegram_links_for_user(user_id)
        result = {"success": True, "linked": False}
        
        if links:
            print(f"[DEBUG] Found {len(links)} links for user {user_id}")
            link = links[0]
            telegram_id = link.get("telegram_id")
            
            # Check Premium Status from Bot Data
            bot_users = await get_bot_users_data()
            if not isinstance(bot_users, dict):
                bot_users = {}
                
            user_data = bot_users.get(str(telegram_id), {})
            expiry_str = user_data.get("expiry")
            
            is_premium = False
            premium_until = None
            
            if expiry_str:
                try:
                    expiry_dt = datetime.fromisoformat(expiry_str.replace('Z', '+00:00'))
                    if expiry_dt.tzinfo is None:
                        expiry_dt = expiry_dt.replace(tzinfo=timezone.utc)
                    if expiry_dt > datetime.now(timezone.utc):
                        is_premium = True
                        premium_until = expiry_str
                except:
                    pass

            result = {
                "success": True, 
                "linked": True, 
                "telegram_username": link.get("telegram_username"),
                "telegram_id": telegram_id,
                "is_premium": is_premium,
                "premium_until": premium_until
            }
        
        # Cache the result for 60s
        user_cache.set(cache_key, result)
        return result

    except Exception as e:
        print(f"[LINK] Status Error: {e}")
        return {"success": False, "message": str(e)}
    finally:
        if cache_key in PENDING_READS and PENDING_READS[cache_key] == event:
            event.set()
            del PENDING_READS[cache_key]

@app.post("/v1/user/telegram/link")
async def link_telegram_endpoint(data: Dict = Body(...)):
    user_id = data.get("user_id")
    token = data.get("code") # App sends 'code' for the token string
    
    if not user_id or not token:
        raise HTTPException(status_code=400, detail="Missing user_id or code")
        
    # 1. Verify Token
    try:
        # Check token and expiry
        now_iso = datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
        response = await http_client.get(
            f"{URL}/rest/v1/telegram_link_tokens",
            params={
                "token": f"eq.{token}",
                "expires_at": f"gt.{now_iso}",
                "select": "*"
            }, 
            headers=HEADERS
        )
        
        if response.status_code != 200 or not response.json():
            return {"success": False, "message": "Invalid or expired code"}
            
        token_data = response.json()[0]
        telegram_id = token_data.get("telegram_id")
        
        if not telegram_id:
            return {"success": False, "message": "Invalid token data"}
            
        # 2. Link Account Transfer Logic
        # Check if this Telegram account is already linked to SOMEONE ELSE
        existing_link_check = await http_client.get(
            f"{URL}/rest/v1/user_telegram_links?telegram_id=eq.{telegram_id}&select=user_id",
            headers=HEADERS
        )
        
        if existing_link_check.status_code == 200 and existing_link_check.json():
            for link in existing_link_check.json():
                old_user_id_val = link.get('user_id')
                if old_user_id_val and old_user_id_val != user_id:
                    print(f"[LINK] Revoking premium for old user {old_user_id_val} during transfer...")
                    # 1. Unlink from old user
                    await http_client.delete(f"{URL}/rest/v1/user_telegram_links?user_id=eq.{old_user_id_val}", headers=HEADERS)
                    # 2. Reset old user's premium status IMMEDIATELY
                    await update_user(old_user_id_val, {
                        "subscription_status": "free",
                        "subscription_end": None,
                        "subscription_source": None
                    })

        success = await link_telegram_account(user_id, telegram_id)
        
        if success:
            # 3. Check for Premium to sync
            bot_users = await get_bot_users_data()
            user_data = bot_users.get(str(telegram_id), {})
            expiry_str = user_data.get("expiry")
            is_premium_telegram = False
            
            if expiry_str:
                try:
                    expiry_dt = datetime.fromisoformat(expiry_str.replace('Z', '+00:00'))
                    if expiry_dt.tzinfo is None: expiry_dt = expiry_dt.replace(tzinfo=timezone.utc)
                    if expiry_dt > datetime.now(timezone.utc):
                        is_premium_telegram = True
                except: pass
            
            if is_premium_telegram:
                await update_user(user_id, {
                    "subscription_status": "active",
                    "subscription_end": expiry_str,
                    "subscription_source": "telegram"
                })
                print(f"[LINK] Synced premium status for user {user_id} from Telegram {telegram_id}")

            # INVALIDATE CACHE
            user_cache.invalidate(f"user_status:{user_id}")

            # 4. Consume Token (Delete it)
            await http_client.delete(f"{URL}/rest/v1/telegram_link_tokens?token=eq.{token}", headers=HEADERS)
            return {"success": True, "message": "Account linked successfully" + (" and premium status synced!" if is_premium_telegram else "")}
        else:
            return {"success": False, "message": "Failed to create link"}
            
    except Exception as e:
        print(f"[LINK] Error linking: {e}")
        return {"success": False, "message": str(e)}

@app.get("/v1/user/telegram/redirect", response_class=HTMLResponse)
async def telegram_redirect_page(code: str = Query(...)):
    """A helper page to redirect from Telegram to the Mobile App"""
    # This page solves the 'unsupported protocol' error in Telegram buttons
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Connecting to hollowScan...</title>
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <style>
            body {{ font-family: -apple-system, sans-serif; display: flex; flex-direction: column; align-items: center; justify-content: center; height: 100vh; background: #0A0A0B; color: white; text-align: center; padding: 20px; }}
            .loader {{ border: 4px solid #1C1C1E; border-top: 4px solid #4F46E5; border-radius: 50%; width: 40px; height: 40px; animation: spin 2s linear infinite; margin-bottom: 20px; }}
            @keyframes spin {{ 0% {{ transform: rotate(0deg); }} 100% {{ transform: rotate(360deg); }} }}
            .btn {{ display: inline-block; padding: 12px 24px; background: #4F46E5; color: white; text-decoration: none; border-radius: 8px; font-weight: bold; margin-top: 20px; text-transform: uppercase; letter-spacing: 1px; }}
        </style>
    </head>
    <body>
        <div class="loader"></div>
        <h2 style="margin: 0;">Linking your account...</h2>
        <p style="color: #9CA3AF; margin-top: 8px;">If you are not redirected automatically, tap the button below.</p>
        <a href="hollowscan://link?code={code}" class="btn">Open hollowScan</a>
        <script>
            // Attempt automatic redirect
            window.location.href = "hollowscan://link?code={code}";
            // Fallback for some browsers: if they stay on page for 3 seconds
            setTimeout(function() {{
                window.location.href = "hollowscan://link?code={code}";
            }}, 2000);
        </script>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)

@app.post("/v1/user/telegram/unlink")
async def unlink_telegram_endpoint(data: Dict = Body(...)):
    user_id = data.get("user_id")
    if not user_id:
         raise HTTPException(status_code=400, detail="Missing user_id")
         
    try:
        # 1. Delete Link from DB
        response = await http_client.delete(f"{URL}/rest/v1/user_telegram_links?user_id=eq.{user_id}", headers=HEADERS)
        
        # 2. Reset Premium Status if it was inherited from Telegram
        user = await get_user_by_id(user_id)
        if user and user.get("subscription_source") == "telegram" or (user and user.get("subscription_status") == "active" and user.get("subscription_source") == None):
             # Force reset if linked to Telegram even if source is missing (safety)
             await update_user(user_id, {
                 "subscription_status": "free",
                 "subscription_end": None,
                 "subscription_source": None
             })
             print(f"[LINK] Reset premium status for user {user_id} after unlinking Telegram")

        # INVALIDATE CACHE
        user_cache.invalidate(f"user_status:{user_id}")

        if response.status_code in [200, 204]:
             return {"success": True, "message": "Unlinked successfully and premium status reset."}
        return {"success": False, "message": "Failed to unlink"}
    except Exception as e:
        print(f"[LINK] Unlink error: {e}")
        return {"success": False, "message": str(e)}

def _parse_price_to_float(price_str: any) -> float:
    if not price_str: return 0.0
    try:
        # Remove currency symbols and commas, keep digits and dots
        clean = re.sub(r'[^0-9.]', '', str(price_str))
        if not clean or clean == '.' or clean == '..': return 0.0
        return float(clean)
    except:
        return 0.0

async def background_notification_worker():
    """Background task to poll for new products and notify users"""
    global LAST_PUSH_CHECK_TIME, RECENT_ALERTS_LOG
    print("[PUSH] Worker started")
    _log_push("Worker started")
    
    while True:
        try:
            await asyncio.sleep(30)
            if not http_client: continue
            
            try:
                response = await asyncio.wait_for(http_client.get(f"{URL}/rest/v1/users?push_tokens=not.is.null&select=id,notification_preferences,push_tokens", headers=HEADERS), timeout=30.0)
                users_data = [u for u in response.json() if u.get("push_tokens")] if response.status_code == 200 else []
            except Exception as e:
                _log_push(f"Error fetching users: {e}")
                continue
            
            if not users_data: continue
            
            try:
                response = await asyncio.wait_for(http_client.get(f"{URL}/rest/v1/discord_messages?order=scraped_at.desc&limit=20", headers=HEADERS), timeout=30.0)
                if response.status_code != 200: continue
                messages = response.json()
                
                new_messages = [m for m in messages if safe_parse_dt(m.get("scraped_at")) and safe_parse_dt(m.get("scraped_at")) > LAST_PUSH_CHECK_TIME]
                
                if new_messages:
                    print(f"[PUSH] {len(new_messages)} new products detected")
                    _log_push(f"Processing {len(new_messages)} new messages")
                    
                    try: product_list_cache.invalidate("feed_global")
                    except: pass
                    
                    channels = await get_channels_data()
                    channel_map = {c['id']: {'category': c.get('category', 'USA Stores').strip(), 'name': c.get('name', 'Unknown').strip()} for c in channels if c.get('enabled', True)}
                    for c in DEFAULT_CHANNELS:
                        if c['id'] not in channel_map: channel_map[c['id']] = {'category': c.get('category', 'USA Stores').strip(), 'name': c.get('name', 'Unknown').strip()}

                    # Clean up old signatures (older than 15 mins)
                    cutoff = datetime.now() - timedelta(minutes=15)
                    RECENT_ALERTS_LOG = [x for x in RECENT_ALERTS_LOG if x[1] > cutoff]
                    current_batch_signatures = set()
                    max_msg_time = LAST_PUSH_CHECK_TIME

                    for msg in new_messages:
                        msg_id = msg.get("id")
                        m_time = safe_parse_dt(msg.get("scraped_at"))
                        if m_time and m_time > max_msg_time: max_msg_time = m_time
                        
                        try:
                            # Content Deduplication
                            sig = _get_content_signature(msg)
                            if sig in current_batch_signatures or any(x[0] == sig for x in RECENT_ALERTS_LOG):
                                _log_push(f"Skipping duplicate signature {sig} for message {msg_id}")
                                continue
                            
                            # TRANSFORM & QUALIFY
                            product = extract_product(msg, channel_map)
                            if not product: continue
                            
                            p_data = product.get("product_data", {})
                            
                            # QUALITY QUALIFICATION (Matches Home Feed)
                            has_image = p_data.get("image") and "placeholder" not in p_data.get("image")
                            has_links = bool(p_data.get("buy_url") or (p_data.get("links") and any(p_data["links"].values())))
                            
                            price_val = _parse_price_to_float(p_data.get("price"))
                            was_val = _parse_price_to_float(p_data.get("was_price"))
                            resell_val = _parse_price_to_float(p_data.get("resell"))
                            
                            has_any_price = price_val > 0 or resell_val > 0 or was_val > 0
                            
                            if not (has_image or has_any_price or has_links):
                                _log_push(f"Skipping msg {msg_id} - Low quality")
                                continue

                            # DISCOUNT CALCULATION
                            current_discount = 0
                            if resell_val > price_val and price_val > 0:
                                current_discount = 100 # Profit deals bypass min %
                            elif was_val > price_val and price_val > 0:
                                current_discount = int(((was_val - price_val) / was_val) * 100)

                            # FILTER USERS
                            region_raw = product.get("region", "USA Stores")
                            store_label = product.get("category_name", "HollowScan")
                            title_raw = str(p_data.get("title") or "Deal Alert")
                            
                            target_tokens = []
                            for u in users_data:
                                prefs = u.get("notification_preferences") or {}
                                if not prefs.get("enabled", True): continue
                                if prefs.get("regions") and region_raw not in prefs["regions"]: continue
                                if prefs.get("categories") and len(prefs["categories"]) > 0 and "ALL" not in [c.upper() for c in prefs["categories"]]:
                                    if store_label not in prefs["categories"]: continue
                                if current_discount < prefs.get("min_discount_percent", 0): continue
                                tokens = u.get("push_tokens") or []
                                if isinstance(tokens, list): target_tokens.extend(tokens)

                            if not target_tokens: continue

                            # PROFESSIONAL FORMATTING
                            region_label = region_raw.replace(" Stores", "").strip()
                            currency = "£" if "UK" in region_raw.upper() else "$"
                            
                            discount_prefix = "🎉 "
                            if resell_val > price_val:
                                discount_prefix = f"💰 {currency}{resell_val - price_val:.2f} Profit: "
                            elif current_discount >= 5 and was_val > 0:
                                discount_prefix = f"📉 {current_discount}% OFF: "

                            final_title = f"{discount_prefix}{title_raw[:45]}..." if len(title_raw) > 45 else f"{discount_prefix}{title_raw}"
                            
                            body_parts = []
                            price_info = ""
                            if price_val > 0:
                                price_info = f"Now: {currency}{p_data['price']}"
                                if was_val > price_val:
                                    price_info += f" (Was {currency}{p_data['was_price']})"
                            elif resell_val > 0:
                                price_info = f"Resell: {currency}{p_data['resell']}"
                            
                            if price_info: body_parts.append(price_info)
                            body_parts.append(f"Store: {store_label}")
                            if region_label: body_parts.append(f"Reg: {region_label}")
                            final_body = " | ".join(body_parts)
                            
                            await send_expo_push_notification(list(set(target_tokens)), final_title, final_body, {"product_id": str(msg_id), "image": p_data.get("image")})
                            
                            current_batch_signatures.add(sig)
                            RECENT_ALERTS_LOG.append((sig, datetime.now()))

                        except Exception as msg_err:
                            _log_push(f"Error processing message {msg_id}: {msg_err}")
                    
                    LAST_PUSH_CHECK_TIME = max_msg_time
                        
            except asyncio.TimeoutError:
                _log_push("Timeout fetching messages")
            except Exception as e:
                _log_push(f"Error in push loop: {e}")
                
        except asyncio.CancelledError: break
        except Exception as e:
            _log_push(f"CRITICAL Worker error: {e}")
            await asyncio.sleep(60)

    print("[PUSH] Worker stopped")

@app.post("/v1/auth/login")
async def login(background_tasks: BackgroundTasks, data: Dict = Body(...)):
    email = data.get("email")
    password = data.get("password")
    if not email or not password:
        print(f"[AUTH] Missing email or password in request data: {data.keys()}")
        raise HTTPException(status_code=400, detail="Email and password are required")
    
    user = await get_user_by_email(email)
    if not user:
        print(f"[AUTH] User not found for email: {email}")
        raise HTTPException(status_code=401, detail="Invalid email or password")
        
    stored_hash = user.get("password_hash")
    provided_hash = hash_password(password)
    
    if not stored_hash:
        print(f"[AUTH] User {email} has no password_hash in DB")
        raise HTTPException(status_code=401, detail="Invalid email or password")
        
    if stored_hash != provided_hash:
        print(f"[AUTH] Password mismatch for {email}")
        # print(f"DEBUG: stored={stored_hash}, provided={provided_hash}")
        raise HTTPException(status_code=401, detail="Invalid email or password")
    
    print(f"[AUTH] Login successful for {email}")
    
    is_verified = user.get("email_verified", False)
    is_premium = user.get("subscription_status") == "active"
    subscription_end = user.get("subscription_end")
    
    # AUTO-TRIGGER verification if not verified
    if not is_verified:
        print(f"[AUTH] Unverified login for {email}, triggering background code")
        background_tasks.add_task(trigger_email_verification, email)

    return {
        "success": True, 
        "user": {
            "id": user["id"], 
            "email": user["email"],
            "name": user.get("name"),
            "bio": user.get("bio"),
            "location": user.get("location"),
            "avatar_url": user.get("avatar_url"),
            "is_premium": is_premium,
            "isPremium": is_premium, 
            "subscription_status": user.get("subscription_status", "free"),
            "status": user.get("subscription_status", "free"),
            "subscription_end": subscription_end,
            "subscriptionEnd": subscription_end,
            "email_verified": is_verified,
            "is_verified": is_verified
        }
    }


@app.post("/v1/auth/apple")
async def apple_signin(data: Dict = Body(...)):
    apple_id = data.get("apple_id")
    email = data.get("email")
    if not apple_id: raise HTTPException(status_code=400, detail="Apple ID is required")
    try:
        response = await http_client.get(f"{URL}/rest/v1/users?apple_id=eq.{apple_id}&select=*", headers=HEADERS)
        if response.status_code == 200 and response.json():
            user = response.json()[0]
        else:
            user = await create_user(email=email, apple_id=apple_id)
            if not user: raise HTTPException(status_code=500, detail="Failed to create user")
        return {"success": True, "user": {"id": user["id"], "email": user["email"], "isPremium": user.get("subscription_status") == "active"}}
    except HTTPException: raise
    except Exception as e:
        print(f"[AUTH] Apple signin error: {e}")
        raise HTTPException(status_code=500, detail=f"Error with Apple sign-in: {str(e)}")

def _clean_text_for_sig(text: str) -> str:
    if not text: return ""
    text = re.sub(r'<@&?\d+>|<#\d+>', '', text)
    text = re.sub(r'@[A-Za-z0-9_]+\b', '', text)
    text = text.replace('|', '').replace('[', '').replace(']', '')
    return " ".join(text.lower().split()).strip()

def _get_content_signature(msg: Dict) -> str:
    try:
        raw = msg.get("raw_data", {})
        embed = raw.get("embed") or {}
        content = msg.get("content", "")
        retailer = embed.get("author", {}).get("name", "") if embed.get("author") else ""
        title = embed.get("title", "")
        price = ""
        for field in embed.get("fields", []):
            name = (field.get("name") or "").lower()
            if "price" in name:
                price = field.get("value", "")
                break
        if not retailer or not title or not price:
            if content and "|" in content:
                parts = [p.strip() for p in content.split("|")]
                if len(parts) >= 2:
                    price_match = re.search(r'[£$€]\s*[\d,]+\.?\d*', content)
                    if price_match: price = price_match.group(0)
                    if not title: title = parts[0]
                    if not retailer and len(parts) > 1: retailer = parts[1]
        if not retailer and "Argos" in content: retailer = "Argos Instore"
        c_retailer = _clean_text_for_sig(retailer)
        c_title = _clean_text_for_sig(title)
        # Increase length to 60 and add a snippet of description for better uniqueness
        f_title = c_title[:60].strip()
        desc_snippet = _clean_text_for_sig(embed.get("description", ""))[:15]
        
        num_match = re.search(r'[\d,]+\.?\d*', price)
        c_price = num_match.group(0).replace(',', '') if num_match else price.strip()
        
        raw_sig = f"{c_retailer}|{f_title}|{c_price}|{desc_snippet}"
        if len(raw_sig) < 8: return hashlib.md5(content.encode()).hexdigest() if content else str(msg.get("id"))
        return hashlib.md5(raw_sig.encode()).hexdigest()
    except: return str(msg.get("id"))

def _clean_display_text(text: str) -> str:
    if not text: return ""
    text = re.sub(r'<@&?\d+>|<#\d+>', '', text)
    text = re.sub(r'^[ \t]*@[A-Za-z0-9_ ]+([|:-]|$)', '', text)
    text = re.sub(r'@[A-Za-z0-9_]+\b', '', text)
    text = text.strip().strip('|').strip(':').strip('-').strip()
    return text

def extract_product(msg, channel_map):
    raw = msg.get("raw_data", {})
    embeds = raw.get("embeds", [])
    embed = raw.get("embed") or (embeds[0] if embeds else {})
    ch_id = str(msg.get("channel_id", ""))
    ch_info = channel_map.get(ch_id)
    if not ch_info:
        # Fallback: Try to guess or use default instead of returning None
        ch_info = {"name": "HollowScan Deal", "category": "USA Stores"}
        # If it's a known UK ID prefix or content has £, suggest UK
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
    if not description and msg.get("content"):
        description = re.sub(r'<@&?\d+>', '', msg.get("content", "")).strip()
        description = re.sub(r'\[([^\]]+)\]\((https?://[^\)]+)\)', r'\1', description)

    image = None
    if embed.get("images"): image = optimize_image_url(embed["images"][0])
    elif embed.get("image") and isinstance(embed["image"], dict): image = optimize_image_url(embed["image"].get("url"))
    elif embed.get("thumbnail") and isinstance(embed["thumbnail"], dict): image = optimize_image_url(embed["thumbnail"].get("url"))

    if not image and embeds:
        for extra_embed in embeds:
            if extra_embed.get("images"): image = optimize_image_url(extra_embed["images"][0]); break
            elif extra_embed.get("image") and isinstance(extra_embed["image"], dict): image = optimize_image_url(extra_embed["image"].get("url")); break
            elif extra_embed.get("thumbnail") and isinstance(extra_embed["thumbnail"], dict): image = optimize_image_url(extra_embed["thumbnail"].get("url")); break

    if not image and raw.get("attachments"):
        for att in raw["attachments"]:
            if any(att.get("filename", "").lower().endswith(ext) for ext in ['.png', '.jpg', '.jpeg', '.webp']): image = att.get("url"); break

    if not image and msg.get("content"):
        img_match = re.search(r'(https?://[^\s]+(?:\.png|\.jpg|\.jpeg|\.webp))', msg["content"], re.IGNORECASE)
        if img_match: image = img_match.group(1)

    price, resell, roi, was_price = None, None, None, None
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
            # Use the FIRST match as the primary price (e.g. "39.95 CAD (29.29 USD)" -> 39.95)
            num = matches[0].replace(',', '') if matches else None

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
                elif "roi" in name_lower or "profit" in name_lower:
                    if not roi: roi = num
                    is_redundant = True
                elif any(k in name_lower for k in ["was", "before", "original"]):
                    if not was_price: was_price = num
                    is_redundant = True

            if not is_redundant: details.append({"label": name, "value": val})

    all_links = []
    # 1. Title URL
    if embed.get("title_url"): all_links.append({"url": embed["title_url"], "text": "Link"})
    
    # 2. Field Markdown Links
    if embed.get("fields"):
        for field in embed["fields"]:
            val = field.get("value", "")
            matches = re.findall(r'\[([^\]]+)\]\((https?://[^\)]+)\)', val)
            for text, url in matches: all_links.append({"url": url, "text": text})

    # 3. Dedicated Links Array (from archiver)
    if embed.get("links"):
        for link in embed["links"]:
            l_url = link.get("url")
            l_text = link.get("text") or "Link"
            if l_url and l_url.startswith("http") and not any(x["url"] == l_url for x in all_links):
                all_links.append({"url": l_url, "text": l_text})

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

    components = raw.get("components", [])
    for comp_row in components:
        sub_comps = comp_row.get("components", [])
        for comp in sub_comps:
            url = comp.get("url")
            label = comp.get("label") or "Link"
            if url and url.startswith("http"):
                link_obj = {"text": label, "url": url}
                u_low, t_low = url.lower(), label.lower()
                if any(ext['url'] == url for sub in categorized_links.values() for ext in sub): continue
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
        "price": price, "was_price": was_price, "resell": resell, "roi": roi,
        "buy_url": primary_buy_url or (all_links[0].get('url') if all_links else None),
        "links": categorized_links, "details": details
    }
    product_data.update(product_data_updates)
    return {"id": str(msg.get("id")), "region": msg_region, "category_name": subcategory, "product_data": product_data, "created_at": msg.get("scraped_at"), "is_locked": False}


# Root route handled by SPA dashboard below

@app.get("/v1/categories")
async def get_categories():
    # Check cache first
    cache_key = "categories"
    cached_result = categories_cache.get(cache_key)
    if cached_result is not None:
        print("[CATEGORIES CACHE] OK Hit")
        return cached_result
    
    print("[CATEGORIES CACHE] MISS Miss - Fetching from storage")
    
    result = {}
    channels = []
    source = "none"
    try:
        storage_url = f"{URL}/storage/v1/object/authenticated/monitor-data/discord_josh/channels.json"
        channels_response = await http_client.get(storage_url, headers=HEADERS)
        if channels_response.status_code == 200:
            channels = channels_response.json() or []
            source = "remote"
            print(f"[CATEGORIES] OK Loaded {len(channels)} channels from remote")
    except Exception as e: print(f"[CATEGORIES] MISS Remote channels fetch failed: {type(e).__name__}: {e}")
    if not channels:
        for filename in ["data/channels_.json", "data/channels.json", "channels.json"]:
            if os.path.exists(filename):
                try:
                    with open(filename, "r") as f: channels = json.load(f)
                    if channels: break
                except: continue
    if not channels:
        channels = DEFAULT_CHANNELS
        source = "defaults"
    result = {"UK Stores": [], "USA Stores": [], "Canada Stores": []}
    for channel in channels:
        if not channel.get('enabled', True): continue
        region_name = channel.get('category', 'USA Stores').strip()
        store_name = channel.get('name', 'Unknown')
        upper_reg = region_name.upper()
        if 'UK' in upper_reg: region_name = 'UK Stores'
        elif 'CANADA' in upper_reg: region_name = 'Canada Stores'
        elif 'USA' in upper_reg or 'UNITED STATES' in upper_reg or upper_reg.startswith('US'): region_name = 'USA Stores'
        else: region_name = 'USA Stores'
        if store_name not in result[region_name]: result[region_name].append(store_name)
    for region in result:
        result[region] = sorted(result[region])
        result[region].insert(0, "ALL")
        
    result_data = {
        "categories": result, 
        "source": source, 
        "channel_count": len(channels)
    }
    
    # Cache it
    categories_cache.set(cache_key, result_data)
    return result_data

async def get_channels_data():
    """Helper to fetch channels from storage or local fallback"""
    channels = []
    try:
        storage_url = f"{URL}/storage/v1/object/authenticated/monitor-data/discord_josh/channels.json"
        channels_response = await http_client.get(storage_url, headers=HEADERS)
        if channels_response.status_code == 200: channels = channels_response.json() or []
    except: pass
    
    if not channels:
        for filename in ["data/channels_.json", "data/channels.json", "channels.json"]:
            if os.path.exists(filename):
                try:
                    with open(filename, "r") as f: 
                        channels = json.load(f)
                        if channels: break
                except: continue
    return channels or DEFAULT_CHANNELS

@app.get("/v1/feed")
async def get_feed(
    user_id: str, 
    background_tasks: BackgroundTasks, 
    region: Optional[str] = "ALL", 
    category: Optional[str] = "ALL", 
    offset: int = 0, 
    limit: int = 20, 
    country: Optional[str] = None, 
    search: Optional[str] = None,
    force_refresh: bool = False  # NEW: Allow manual cache bypass
):
    # Normalize inputs
    if country and (not region or region == "ALL"): region = country
    
    # Generate base cache key (GLOBAL - shared across all users with same filters)
    base_cache_key = product_list_cache.get_base_cache_key(region, category, search or "")
    
    # Check if we have cached results for this filter
    cached_data = None
    if not force_refresh:
        cached_data = product_list_cache.get(base_cache_key)
    
    # SINGLEFLIGHT: Protect against Cache Stampede
    if cached_data is None and not force_refresh:
        if base_cache_key in PENDING_READS:
            # Another request is already scanning for this key! Let's wait for it.
            print(f"[FEED CACHE] {user_id[:8]} Waiting for in-progress DB scan...")
            await PENDING_READS[base_cache_key].wait()
            # Scan finished, now grab the result from cache
            cached_data = product_list_cache.get(base_cache_key)
            if cached_data is not None:
                print(f"[FEED CACHE] {user_id[:8]} OK - Stampede avoided! Using result from concurrent scan.")
    
    # Still no data? We might be the first or it's a force refresh
    event = None
    if cached_data is None and not force_refresh:
        event = asyncio.Event()
        PENDING_READS[base_cache_key] = event

    try:
        all_products = []
        current_sql_offset = offset
        db_end_reached = False
        cache_refill_mode = False
        
        if cached_data is not None:
            all_products, next_sql_offset, db_end_reached = cached_data
            
            # Check if requested page is already in research OR if DB is fully exhausted
            # If we have enough products to satisfy the offset+limit, OR we know there's no more in DB, return hit
            if (offset + limit <= len(all_products)) or db_end_reached:
                print(f"[FEED CACHE] OK - Serving page from {len(all_products)} cached products")
                
                # Check premium status
                premium_user = await verify_premium_status(user_id, background_tasks=background_tasks)
                
                # Slice for requested page
                page_products = all_products[offset:offset+limit]
                has_more = (offset + limit) < len(all_products) or (not db_end_reached)
                
                # Apply free user limits
                if not premium_user:
                    if len(page_products) > 4:
                        page_products = page_products[:4]
                        has_more = False
                    for product in page_products:
                        product["is_locked"] = False
                
                return {
                    "products": page_products,
                    "next_offset": offset + limit if has_more else offset + len(page_products),
                    "has_more": has_more,
                    "is_premium": premium_user,
                    "total_count": len(all_products) if db_end_reached else len(all_products) + 100
                }
            else:
                # AUTO-REFILL: We have some products, but user scrolled past them.
                # Continue from the last scanned SQL offset.
                print(f"[FEED CACHE] PARTIAL HIT - Refilling cache from SQL offset {next_sql_offset}...")
                current_sql_offset = next_sql_offset
                cache_refill_mode = True
        else:
            # Cache miss - fetch from scratch
            print(f"[FEED CACHE] MISS - Fetching from DB for user {user_id[:8]}...")
            all_products = []
            current_sql_offset = offset

        # ======= DB FETCHING LOGIC =======
        search_is_active = bool(search and search.strip())
        channels = await get_channels_data()
        
        channel_map = {}
        for c in channels:
            if c.get('enabled', True): channel_map[c['id']] = {'category': c.get('category', 'USA Stores').strip(), 'name': c.get('name', 'Unknown').strip()}
        for c in DEFAULT_CHANNELS:
            if c['id'] not in channel_map: channel_map[c['id']] = {'category': c.get('category', 'USA Stores').strip(), 'name': c.get('name', 'Unknown').strip()}
        
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
                    if is_region_match and c_name == category.strip().upper(): target_ids.append(c['id'])
                elif is_region_match: target_ids.append(c['id'])
        id_filter = ""
        if target_ids: id_filter = f"&channel_id=in.({','.join(target_ids)})"
        
        premium_user = await verify_premium_status(user_id, background_tasks=background_tasks)
        
        # Population seen_signatures for deduplication (especially important for refill)
        seen_signatures = set()
        if all_products:
            for p in all_products:
                if "content_signature" in p:
                    seen_signatures.add(p["content_signature"])
        
        chunks_scanned = 0
        base_max = 100 if premium_user else 30
        search_multiplier = 20 if search else 1
        max_chunks = base_max * search_multiplier
        batch_limit = 1000 if search else 50
        
        # Target size for the cache fill
        if cache_refill_mode:
            cache_fill_target = len(all_products) + 50 # Add a small batch on refill
        else:
            cache_fill_target = 300 if search_is_active else 100
        
        db_end_reached = False
        while len(all_products) < cache_fill_target and chunks_scanned < max_chunks:
            query = f"order=scraped_at.desc&offset={current_sql_offset}&limit={batch_limit}"
            if id_filter and not search_is_active: query += id_filter
                 
            if search_is_active:
                keywords = [k.strip() for k in search.split() if len(k.strip()) >= 1]
                if keywords:
                    or_parts = []
                    for k in keywords:
                        or_parts.append(f"content.ilike.*{k}*")
                        or_parts.append(f"raw_data->embeds->0->>title.ilike.*{k}*")
                        or_parts.append(f"raw_data->embeds->0->>description.ilike.*{k}*")
                        or_parts.append(f"raw_data->embed->>title.ilike.*{k}*")
                        or_parts.append(f"raw_data->embed->>description.ilike.*{k}*")
                        or_parts.append(f"raw_data->embeds->0->fields->0->>value.ilike.*{k}*")
                        or_parts.append(f"raw_data->embeds->0->fields->1->>value.ilike.*{k}*")
                        or_parts.append(f"raw_data->embeds->0->author->>name.ilike.*{k}*")
                    query += f"&or=({','.join(or_parts)})"
                    
            try:
                response = await http_client.get(f"{URL}/rest/v1/discord_messages?{query}", headers=HEADERS)
                if response.status_code != 200: break
                messages = response.json()
                if not messages: 
                    db_end_reached = True
                    break
                    
                for msg in messages:
                    sig = _get_content_signature(msg)
                    if sig in seen_signatures: continue
                    prod = extract_product(msg, channel_map)
                    if not prod: continue
                    
                    # Filtering logic
                    p_data = prod.get("product_data", {})
                    has_image = p_data.get("image") and "placeholder" not in p_data.get("image")
                    has_links = bool(p_data.get("buy_url") or (p_data.get("links") and any(p_data["links"].values())))
                    try:
                        p_num = float(str(p_data.get("price") or 0).replace(',', ''))
                        r_num = float(str(p_data.get("resell") or 0).replace(',', ''))
                        w_num = float(str(p_data.get("was_price") or 0).replace(',', ''))
                        has_any_price = p_num > 0 or r_num > 0 or w_num > 0
                    except: has_any_price = False
                    
                    if not (has_image or has_any_price or has_links): continue
                    
                    if search_is_active:
                        search_keywords = [k.lower().strip() for k in search.split() if k.strip()]
                        search_blob = f"{p_data.get('title','')}\n{p_data.get('description','')}\n{prod.get('category_name','')}".lower()
                        if not any(kw in search_blob for kw in search_keywords): continue
    
                    if not search_is_active:
                        if region and region.strip().upper() != "ALL" and prod["region"].strip() != region.strip(): continue
                        if category and category.strip().upper() != "ALL" and prod["category_name"].upper().strip() != category.upper().strip(): continue
                    
                    prod["content_signature"] = sig # Ensure sig is stored for deduplication
                    all_products.append(prod)
                    seen_signatures.add(sig)
                
                current_sql_offset += len(messages)
                chunks_scanned += 1
                if len(messages) < batch_limit: 
                    db_end_reached = True
                    break
            except Exception as e:
                print(f"[FEED] Error in batch fetch: {e}")
                break
    
        # Update cache with the potentially larger list
        product_list_cache.set(base_cache_key, all_products, current_sql_offset, db_end_reached)
        
        # Slice and return
        total_found = len(all_products)
        page_products = all_products[offset:offset+limit]
        has_more = (offset + limit) < total_found or (not db_end_reached)
        
        if not premium_user:
            if len(page_products) > 4:
                page_products = page_products[:4]
                has_more = False
            for product in page_products: product["is_locked"] = False
        
        result = {
            "products": page_products, 
            "next_offset": offset + limit if has_more else offset + len(page_products), 
            "has_more": has_more, 
            "is_premium": premium_user, 
            "total_count": total_found if db_end_reached else total_found + 100
        }
        
        print(f"[FEED] Complete. Found {total_found} products (scanned up to SQL offset {current_sql_offset}). Returning {len(page_products)} @ offset {offset}.")
        return result
    finally:
        # Cleanup Singleflight event
        if event:
            event.set()
            if PENDING_READS.get(base_cache_key) == event:
                del PENDING_READS[base_cache_key]

# NOTE: Primary /v1/user/status endpoint is defined at line ~715 with full functionality
# Duplicate endpoint removed to fix FastAPI duplicate operation ID warning

@app.get("/v1/deals/saved")
async def get_saved_deals(user_id: str = Query(...)):
    if not user_id: raise HTTPException(status_code=400, detail="User ID required")
    try:
        response = await http_client.get(
            f"{URL}/rest/v1/saved_deals?user_id=eq.{user_id}&select=*",
            headers=HEADERS
        )
        if response.status_code == 200:
            saved = response.json()
            return {"success": True, "deals": [row.get("alert_data") for row in saved if row.get("alert_data")]}
        return {"success": False, "deals": [], "message": f"DB Error: {response.status_code}"}
    except Exception as e:
        print(f"[DEALS] Error fetching saved: {e}")
        return {"success": False, "deals": [], "message": str(e)}

@app.post("/v1/deals/save")
async def save_deal(data: Dict = Body(...)):
    user_id = data.get("user_id")
    alert_id = data.get("alert_id")
    alert_data = data.get("alert_data")
    
    if not user_id or not alert_id or not alert_data:
        raise HTTPException(status_code=400, detail="Missing user_id, alert_id, or alert_data")
    
    try:
        payload = {
            "user_id": user_id,
            "alert_id": str(alert_id),
            "alert_data": alert_data,
            "saved_at": datetime.now(timezone.utc).isoformat()
        }
        response = await http_client.post(
            f"{URL}/rest/v1/saved_deals",
            headers={**HEADERS, "Prefer": "resolution=merge-duplicates"},
            json=payload
        )
        if response.status_code in [200, 201]:
            return {"success": True, "message": "Deal saved!"}
        return {"success": False, "message": f"DB Error: {response.status_code} {response.text}"}
    except Exception as e:
        print(f"[DEALS] Error saving: {e}")
        return {"success": False, "message": str(e)}

@app.delete("/v1/deals/saved")
async def delete_saved_deal(user_id: str = Query(...), alert_id: str = Query(...)):
    if not user_id or not alert_id:
        raise HTTPException(status_code=400, detail="User ID and Alert ID required")
    try:
        response = await http_client.delete(
            f"{URL}/rest/v1/saved_deals?user_id=eq.{user_id}&alert_id=eq.{alert_id}",
            headers=HEADERS
        )
        if response.status_code in [200, 204]:
            return {"success": True, "message": "Deal removed!"}
        return {"success": False, "message": f"DB Error: {response.status_code}"}
    except Exception as e:
        print(f"[DEALS] Error deleting: {e}")
        return {"success": False, "message": str(e)}

@app.get("/v1/product/detail")
async def get_product_detail(product_id: str = Query(...)):
    """Fetch a single product by its ID for deep linking"""
    try:
        # 1. Fetch from discord_messages
        response = await http_client.get(
            f"{URL}/rest/v1/discord_messages?id=eq.{product_id}&select=*",
            headers=HEADERS
        )
        if response.status_code == 200 and response.json():
            msg = response.json()[0]
            
            # 2. Extract using existing logic
            channels = await get_channels_data()
            channel_map = {}
            for c in channels:
                channel_map[c['id']] = {'category': c.get('category', 'USA Stores'), 'name': c.get('name', 'Unknown')}
            
            prod = extract_product(msg, channel_map)
            if prod:
                return {"success": True, "product": prod}
        
        return {"success": False, "message": "Product not found"}
    except Exception as e:
        print(f"[PRODUCT] Error fetching detail: {e}")
        return {"success": False, "message": str(e)}

@app.get("/share/{product_id}", response_class=HTMLResponse)
async def share_product_page(product_id: str):
    """Render a premium landing page for shared products with deep link support"""
    detail_res = await get_product_detail(product_id)
    if not detail_res.get("success"):
        return f"<html><head><title>Deal Not Found</title></head><body style='background:#0A0A0B;color:white;text-align:center;padding-top:100px;'><h1>Deal Expired or Not Found</h1><p>This deal may have been removed or is no longer available.</p></body></html>"
    
    prod = detail_res["product"]
    data = prod.get("product_data", {})
    title = data.get("title", "HollowScan Deal")
    desc = data.get("description", "Check out this deal on HollowScan!")
    img = data.get("image") or "https://hollowscan.com/icon.png"
    
    # Robust price display for web
    price_val = data.get("price")
    currency = "£" if "UK" in prod.get("region", "") else "$"
    display_price = f"{currency}{price_val}" if price_val else "Check Price"
    
    region = prod.get("region", "USA")
    deep_link = f"hollowscan://product/{product_id}"

    # Construct HTML with premium feel and OG tags
    html = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>{title} | HollowScan</title>
        
        <!-- Open Graph / Social Previews -->
        <meta property="og:type" content="website">
        <meta property="og:title" content="{title}">
        <meta property="og:description" content="{desc[:150]}...">
        <meta property="og:image" content="{img}">
        <meta name="twitter:card" content="summary_large_image">
        
        <style>
            body {{
                margin: 0; padding: 0;
                background-color: #0A0A0B;
                color: #FAFAFA;
                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
                display: flex; justify-content: center; align-items: center;
                min-height: 100vh;
                text-align: center;
            }}
            .card {{
                max-width: 400px; width: 90%;
                background: rgba(255, 255, 255, 0.03);
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 24px; padding: 32px;
                backdrop-filter: blur(10px);
                box-shadow: 0 20px 40px rgba(0,0,0,0.5);
            }}
            .image-box {{
                width: 100%; border-radius: 16px; 
                background: #1C1C1E; overflow: hidden;
                margin-bottom: 24px; border: 1px solid rgba(255,255,255,0.05);
            }}
            .image-box img {{ width: 100%; display: block; }}
            h1 {{ font-size: 22px; font-weight: 800; margin-bottom: 8px; line-height: 1.3; }}
            .price {{ color: #3B82F6; font-size: 24px; font-weight: 900; margin-bottom: 20px; }}
            .btn {{
                background: #3B82F6; color: white;
                text-decoration: none; font-weight: 800;
                padding: 16px 32px; border-radius: 14px;
                display: block; transition: transform 0.2s;
                font-size: 16px;
            }}
            .btn:active {{ transform: scale(0.96); }}
            .footer {{ margin-top: 32px; font-size: 12px; opacity: 0.5; }}
        </style>
        
        <script>
            // Auto-redirect to app
            window.onload = function() {{
                setTimeout(function() {{
                    window.location.href = "{deep_link}";
                }}, 500);
            }};
        </script>
    </head>
    <body>
        <div class="card">
            <div class="image-box">
                <img src="{img}" alt="Product image">
            </div>
            <h1>{title}</h1>
            <div class="price">{display_price}</div>
            <a href="{deep_link}" class="btn">Open in HollowScan App</a>
            <div class="footer">
                Shared via HollowScan Deals • {region}
            </div>
        </div>
    </body>
    </html>
    """
    return html


# ========================================
# PUSH NOTIFICATION ENDPOINTS
# ========================================

@app.post("/v1/user/push-token")
async def save_push_token(user_id: str, token: str):
    """Save user's Expo push token for notifications"""
    try:
        # Fetch current push_tokens
        response = await http_client.get(
            f"{URL}/rest/v1/users?id=eq.{user_id}&select=push_tokens",
            headers=HEADERS
        )
        
        if response.status_code != 200:
            raise HTTPException(status_code=500, detail="Failed to fetch user")
        
        users = response.json()
        if not users:
            raise HTTPException(status_code=404, detail="User not found")
        
        current_tokens = users[0].get("push_tokens") or []
        
        # Add token if not already present
        if token not in current_tokens:
            current_tokens.append(token)
            
            # Update database
            update_response = await http_client.patch(
                f"{URL}/rest/v1/users?id=eq.{user_id}",
                headers=HEADERS,
                json={"push_tokens": current_tokens}
            )
            
            if update_response.status_code not in [200, 204]:
                raise HTTPException(status_code=500, detail="Failed to save token")
        
        print(f"[PUSH] Saved token for user {user_id}")
        return {"success": True, "message": "Push token saved"}
    
    except Exception as e:
        print(f"[PUSH] Error saving token: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/v1/user/push-token")
async def delete_push_token(user_id: str, token: str):
    """Remove user's push token (on logout)"""
    try:
        # Fetch current push_tokens
        response = await http_client.get(
            f"{URL}/rest/v1/users?id=eq.{user_id}&select=push_tokens",
            headers=HEADERS
        )
        
        if response.status_code != 200:
            return {"success": False, "message": "User not found"}
        
        users = response.json()
        if not users:
            return {"success": False, "message": "User not found"}
        
        current_tokens = users[0].get("push_tokens") or []
        
        # Remove token if present
        if token in current_tokens:
            current_tokens.remove(token)
            
            # Update database
            update_response = await http_client.patch(
                f"{URL}/rest/v1/users?id=eq.{user_id}",
                headers=HEADERS,
                json={"push_tokens": current_tokens}
            )
            
            if update_response.status_code not in [200, 204]:
                return {"success": False, "message": "Failed to remove token"}
        
        print(f"[PUSH] Removed token for user {user_id}")
        return {"success": True, "message": "Push token removed"}
    
    except Exception as e:
        print(f"[PUSH] Error removing token: {e}")
        return {"success": False, "message": str(e)}


@app.get("/v1/user/notification-preferences")
async def get_notification_preferences(user_id: str):
    """Get user's notification preferences"""
    try:
        response = await http_client.get(
            f"{URL}/rest/v1/users?id=eq.{user_id}&select=notification_preferences",
            headers=HEADERS
        )
        
        if response.status_code != 200:
            raise HTTPException(status_code=500, detail="Failed to fetch preferences")
        
        users = response.json()
        if not users:
            raise HTTPException(status_code=404, detail="User not found")
        
        preferences = users[0].get("notification_preferences") or {
            "enabled": True,
            "regions": ["USA Stores", "UK Stores", "Canada Stores"],
            "categories": [],  # Empty = all categories
            "min_discount_percent": 0
        }
        
        return {"success": True, "preferences": preferences}
    
    except Exception as e:
        print(f"[PUSH] Error fetching preferences: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/v1/user/notification-preferences")
@app.post("/v1/user/preferences")
async def update_notification_preferences(user_id: str, preferences: Dict[str, Any] = Body(...)):
    """Update user's notification preferences"""
    try:
        # Validate preferences structure
        valid_preferences = {
            "enabled": preferences.get("enabled", True),
            "regions": preferences.get("regions", ["USA Stores", "UK Stores", "Canada Stores"]),
            "categories": preferences.get("categories", []),
            "min_discount_percent": preferences.get("min_discount_percent", 0)
        }
        
        # Update database
        response = await http_client.patch(
            f"{URL}/rest/v1/users?id=eq.{user_id}",
            headers=HEADERS,
            json={"notification_preferences": valid_preferences}
        )
        
        if response.status_code not in [200, 204]:
            raise HTTPException(status_code=500, detail="Failed to update preferences")
        
        # INVALIDATE CACHE
        user_cache.invalidate(f"user_status:{user_id}")
        
        print(f"[PUSH] Updated preferences for user {user_id}: {valid_preferences}")
        return {"success": True, "message": "Preferences updated", "preferences": valid_preferences}
    
    except Exception as e:
        print(f"[PUSH] Error updating preferences: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/v1/cache/invalidate")
async def invalidate_cache(
    user_id: Optional[str] = None,
    cache_type: str = "all"  # "all", "feed", "user", "categories"
):
    """
    Admin endpoint to manually invalidate cache
    Use this when you know data has changed and want immediate refresh
    """
    try:
        if cache_type == "all" or cache_type == "feed":
            if user_id:
                feed_cache.invalidate(f"feed:{user_id}")
                product_list_cache.invalidate(f"feed_global")  # NEW: Clear product cache too
                print(f"[CACHE] Invalidated feed cache for user {user_id}")
            else:
                feed_cache.invalidate()
                product_list_cache.invalidate()  # NEW: Clear product cache too
                print("[CACHE] Invalidated all feed caches")
        
        if cache_type == "all" or cache_type == "user":
            if user_id:
                user_cache.invalidate(f"user_status:{user_id}")
                print(f"[CACHE] Invalidated user cache for {user_id}")
            else:
                user_cache.invalidate()
                print("[CACHE] Invalidated all user caches")
        
        if cache_type == "all" or cache_type == "categories":
            categories_cache.invalidate()
            print("[CACHE] Invalidated categories cache")
        
        return {"success": True, "message": f"Cache invalidated: {cache_type}"}
    except Exception as e:
        print(f"[CACHE] Invalidation error: {e}")
        return {"success": False, "message": str(e)}


@app.get("/v1/cache/stats")
async def get_cache_stats():
    """Get cache statistics for monitoring"""
    return {
        "feed_cache": feed_cache.get_stats(),
        "product_list_cache": product_list_cache.get_stats(),  # NEW
        "user_cache": user_cache.get_stats(),
        "categories_cache": categories_cache.get_stats()
    }


# --- ADMIN MANAGEMENT ENDPOINTS ---

ADMIN_API_KEY = os.getenv("ADMIN_API_KEY")

async def verify_admin_key(x_admin_key: str = Header(None)):
    if not x_admin_key or x_admin_key != ADMIN_API_KEY:
        raise HTTPException(status_code=403, detail="Unauthorized admin access")
    return True

@app.get("/v1/admin/users")
async def admin_get_users(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=100),
    search: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    admin_auth: bool = Depends(verify_admin_key)
):
    """Fetch all users with Telegram linking info and premium sources"""
    offset = (page - 1) * limit
    
    # Base query for users
    query = f"{URL}/rest/v1/users?select=*,user_telegram_links(*)"
    
    params = []
    if search:
        params.append(f"email=ilike.*{search}*")
    if status:
        params.append(f"subscription_status=eq.{status}")
    
    if params:
        query += "&" + "&".join(params)
    
    query += f"&order=created_at.desc"
    
    # Get total count for pagination and set range
    count_headers = {
        **HEADERS, 
        "Prefer": "count=exact",
        "Range": f"{offset}-{offset + limit - 1}"
    }
    
    try:
        response = await http_client.get(query, headers=count_headers)
        if response.status_code not in [200, 206]:
            raise HTTPException(status_code=response.status_code, detail=response.text)
        
        users = response.json()
        total_count = int(response.headers.get("Content-Range", "0-0/0").split("/")[-1])
        
        return {
            "success": True,
            "users": users,
            "pagination": {
                "total": total_count,
                "page": page,
                "limit": limit,
                "pages": (total_count + limit - 1) // limit
            }
        }
    except Exception as e:
        print(f"[ADMIN] Error fetching users: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/v1/admin/user/subscription")
async def admin_update_subscription(
    background_tasks: BackgroundTasks,
    data: Dict = Body(...),
    admin_auth: bool = Depends(verify_admin_key)
):
    """Manually override user subscription status"""
    user_id = data.get("user_id")
    status = data.get("status") # 'active', 'free', 'expired'
    end_date = data.get("end_date") # ISO string
    source = data.get("source", "manual")
    
    if not user_id or not status:
        raise HTTPException(status_code=400, detail="User ID and status are required")
    
    update_data = {
        "subscription_status": status,
        "subscription_end": end_date,
        "subscription_source": source
    }
    
    success = await update_user(user_id, update_data)
    if success:
        print(f"[ADMIN] Subscription updated for {user_id} -> {status}")
        # Invalidate cache
        background_tasks.add_task(user_cache.invalidate, f"user_status:{user_id}")
        return {"success": True, "message": f"Subscription updated for user {user_id}"}
    else:
        raise HTTPException(status_code=500, detail="Failed to update subscription")

@app.post("/v1/admin/user/status")
async def admin_toggle_account_status(
    background_tasks: BackgroundTasks,
    data: Dict = Body(...),
    admin_auth: bool = Depends(verify_admin_key)
):
    """Enable/Disable user account access (mocking a ban feature)"""
    user_id = data.get("user_id")
    is_active = data.get("is_active", True) # Boolean
    
    if not user_id:
        raise HTTPException(status_code=400, detail="User ID is required")
    
    # If activating, default to 'free' if no other status provided
    # If banning, set status to 'banned'
    status = "free" if is_active else "banned"
    print(f"[ADMIN] Toggling account status for {user_id} to {status} (is_active={is_active})")
    
    success = await update_user(user_id, {"subscription_status": status})
    
    # If we had a dedicated column, we'd use that. For now, let's assume we update a flag
    # update_user(user_id, {"is_active": is_active})
    
    if success:
        background_tasks.add_task(user_cache.invalidate, f"user_status:{user_id}")
        return {"success": True, "message": f"User account status updated to {'Active' if is_active else 'Banned'}"}
    else:
        raise HTTPException(status_code=500, detail="Failed to update account status")

@app.get("/v1/admin/analytics")
async def admin_get_analytics(admin_auth: bool = Depends(verify_admin_key)):
    """Get high-level analytics for the dashboard"""
    try:
        # 1. Total User Count
        count_resp = await http_client.get(f"{URL}/rest/v1/users?select=id", headers={**HEADERS, "Prefer": "count=exact"})
        total_users = int(count_resp.headers.get("Content-Range", "0-0/0").split("/")[-1])
        
        # 2. Subscription Distribution
        sub_resp = await http_client.get(f"{URL}/rest/v1/users?select=subscription_status,subscription_source", headers=HEADERS)
        users_data = sub_resp.json()
        
        distribution = defaultdict(int)
        sources = defaultdict(int)
        
        for u in users_data:
            status = u.get("subscription_status", "free")
            source = u.get("subscription_source", "none") or "none"
            distribution[status] += 1
            if status == "active":
                sources[source] += 1
        
        # 3. Last 24h Signups
        yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        recent_resp = await http_client.get(f"{URL}/rest/v1/users?created_at=gt.{yesterday}&select=id", headers={**HEADERS, "Prefer": "count=exact"})
        new_users_24h = int(recent_resp.headers.get("Content-Range", "0-0/0").split("/")[-1])

        return {
            "success": True,
            "analytics": {
                "total_users": total_users,
                "new_users_24h": new_users_24h,
                "subscription_distribution": dict(distribution),
                "premium_sources": dict(sources)
            }
        }
    except Exception as e:
        print(f"[ADMIN] Analytics error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/health")
async def health_check():
    return {"status": "healthy", "timestamp": datetime.now(timezone.utc).isoformat()}

# --- STATIC FRONTEND SERVING (ADMIN DASHBOARD) ---

# 1. Mount static assets (JS, CSS, Images)
# Note: This MUST be after all API routes to avoid shadowing
ADMIN_DIST_DIR = os.path.join(os.path.dirname(__file__), "admin_dashboard", "dist")

if os.path.exists(ADMIN_DIST_DIR):
    app.mount("/assets", StaticFiles(directory=os.path.join(ADMIN_DIST_DIR, "assets")), name="static")
    print(f"[SERVER] Mounted Admin Dashboard assets from {ADMIN_DIST_DIR}")

    @app.get("/")
    @app.get("/{full_path:path}")
    async def serve_dashboard(full_path: str = ""):
        # Serve index.html for the root or any non-API route
        index_path = os.path.join(ADMIN_DIST_DIR, "index.html")
        if os.path.exists(index_path):
            return FileResponse(index_path)
        return {"error": "Dashboard build not found"}
else:
    print(f"[SERVER] Warning: Admin Dashboard dist folder not found at {ADMIN_DIST_DIR}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)