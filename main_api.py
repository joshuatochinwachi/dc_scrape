#!/usr/bin/env python3
"""
main_api.py - OPTIMIZED
Professional FastAPI backend for hollowScan Mobile App.
Performance optimized for mobile with connection pooling and async operations.
"""

from fastapi import FastAPI, HTTPException, Depends, Query, Header, Body, BackgroundTasks
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
import httpx
import asyncio
import re
import time

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
    limits = httpx.Limits(max_keepalive_connections=20, max_connections=100)
    timeout = httpx.Timeout(20.0, connect=5.0)
    http_client = httpx.AsyncClient(limits=limits, timeout=timeout, http2=True)
    print("[STARTUP] HTTP client initialized with connection pooling")
    
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

async def get_user_by_id(user_id: str) -> Optional[Dict]:
    try:
        response = await http_client.get(f"{URL}/rest/v1/users?id=eq.{user_id}&select=*", headers=HEADERS)
        if response.status_code == 200 and response.json(): return response.json()[0]
    except Exception as e: print(f"[DB] Error fetching user: {e}")
    return None

async def get_user_by_email(email: str) -> Optional[Dict]:
    try:
        response = await http_client.get(f"{URL}/rest/v1/users?email=eq.{email}&select=*", headers=HEADERS)
        if response.status_code == 200 and response.json(): return response.json()[0]
    except Exception as e: print(f"[DB] Error fetching user by email: {e}")
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

async def update_user(user_id: str, data: Dict, return_details: bool = False) -> Any:
    try:
        data["updated_at"] = datetime.now(timezone.utc).isoformat()
        response = await http_client.patch(f"{URL}/rest/v1/users?id=eq.{user_id}", headers=HEADERS, json=data)
        success = response.status_code in [200, 201, 204]
        if return_details:
            msg = "Success" if success else f"DB Error {response.status_code}: {response.text}"
            return success, msg
        return success
    except Exception as e:
        print(f"[DB] Error updating user: {e}")
        if return_details: return False, str(e)
    return False

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

async def get_verification_code_from_supabase(email: str) -> Optional[Dict]:
    try:
        response = await http_client.get(f"{URL}/rest/v1/email_verifications?email=eq.{email}&select=*", headers=HEADERS)
        if response.status_code == 200 and response.json():
            return response.json()[0]
    except Exception as e:
        print(f"[DB] Error fetching verification code: {e}")
    return None

async def upsert_verification_code_to_supabase(email: str, code: str, expires_at: str) -> bool:
    try:
        payload = {
            "email": email,
            "code": code,
            "expires_at": expires_at,
            "created_at": datetime.now(timezone.utc).isoformat()
        }
        # Use upsert (on_conflict email)
        headers = {**HEADERS, "Prefer": "resolution=merge-duplicates,return=representation"}
        response = await http_client.post(f"{URL}/rest/v1/email_verifications", headers=headers, json=payload)
        return response.status_code in [200, 201]
    except Exception as e:
        print(f"[DB] Error upserting verification code: {e}")
    return False

async def delete_verification_code_from_supabase(email: str) -> bool:
    try:
        response = await http_client.delete(f"{URL}/rest/v1/email_verifications?email=eq.{email}", headers=HEADERS)
        return response.status_code in [200, 204]
    except Exception as e:
        print(f"[DB] Error deleting verification code: {e}")
    return False

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
    expiry = datetime.fromisoformat(stored["expires_at"].replace('Z', '+00:00'))
    if datetime.now(timezone.utc) > expiry:
        raise HTTPException(status_code=400, detail="Code expired. Please request a new one.")
        
    if stored["code"] != code:
        raise HTTPException(status_code=400, detail="Invalid verification code")
        
    # Valid! Update user in DB
    user = await get_user_by_email(email)
    if not user: raise HTTPException(status_code=404, detail="User not found")
    
    success = await update_user(user["id"], {"email_verified": True})
    if not success: raise HTTPException(status_code=500, detail="Failed to update verification status")
    
    # Clean up code in Supabase
    await delete_verification_code_from_supabase(email)
    
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

@app.post("/v1/user/preferences")
async def update_preferences(user_id: str = Query(...), data: Dict = Body(...)):
    """Sync notification preferences to DB"""
    if not user_id: raise HTTPException(status_code=400, detail="User ID required")
    
    # data format: {"enabled": bool, "regions": {"USA Stores": ["ALL"], ...}}
    success = await update_user(user_id, {"notification_preferences": data})
    return {"success": success}

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

# Sends push notification via Expo Push API
async def send_expo_push_notification(tokens: List[str], title: str, body: str, data: Dict = None):
    if not tokens: return
    
    # Ensure http_client is ready
    if not http_client:
        print("[PUSH] Warning: http_client not initialized, skipping push.")
        return

    message = {
        "to": tokens,
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
            print(f"[PUSH] Expo error: {response.text}")
    except Exception as e:
        # Catch ALL exceptions to prevent worker crash
        print(f"[PUSH] Error sending push: {e}")


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
    """Get user's current subscription and verification status"""
    try:
        user_data = await get_user_by_id(user_id)
        if not user_data:
            return {"success": False, "message": "User not found"}

        # 1. Use strict verification for existing status
        is_premium = await verify_premium_status(user_id, user_data, background_tasks)
        subscription_end = user_data.get("subscription_end")
        
        # 2. PROACTIVE: Also check Telegram linking status if not already premium
        if not is_premium:
            try:
                # Check if user has a linked telegram account
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
                                if exp_dt.tzinfo is None: exp_dt = exp_dt.replace(tzinfo=timezone.utc)
                                if exp_dt > datetime.now(timezone.utc):
                                    is_premium = True
                                    subscription_end = expiry_str
                                    # Sync back to DB so subsequent checks are faster
                                    background_tasks.add_task(update_user, user_id, {
                                        "subscription_status": "active",
                                        "subscription_end": expiry_str,
                                        "subscription_source": "telegram"
                                    })
                            except: pass
            except Exception as e:
                print(f"[STATUS] TG check failed: {e}")

        return {
            "success": True,
            "is_premium": is_premium,
            "subscription_end": subscription_end,
            "status": "active" if is_premium else "free",
            "subscription_status": "active" if is_premium else "free", # Keeping both for safety
            "email_verified": user_data.get("email_verified", False),
            "is_verified": user_data.get("email_verified", False), # Keeping both for safety
            "email": user_data.get("email"),
            "name": user_data.get("name"),
            "bio": user_data.get("bio"),
            "location": user_data.get("location"),
            "avatar_url": user_data.get("avatar_url"),
            "region": user_data.get("region", "USA Stores")
        }
    except Exception as e:
        print(f"[STATUS] Error: {e}")
        return {"success": False, "message": str(e)}

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
            return {"success": True, "message": "Profile updated successfully"}
        else:
            return {"success": False, "message": f"Failed: {msg}"}
    except Exception as e:
        print(f"[PROFILE] Error updating: {e}")
        return {"success": False, "message": str(e)}

# --- TELEGRAM LINKING ENDPOINTS ---

@app.get("/v1/user/telegram/link-status")
async def get_telegram_link_status_endpoint(user_id: str = Query(...)):
    print(f"[DEBUG] Checking Telegram status for user: '{user_id}'")
    try:
        links = await get_telegram_links_for_user(user_id)
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
                    # Simple ISO parse
                    expiry_dt = datetime.fromisoformat(expiry_str.replace('Z', '+00:00'))
                    if expiry_dt.tzinfo is None:
                        expiry_dt = expiry_dt.replace(tzinfo=timezone.utc)
                        
                    now_dt = datetime.now(timezone.utc)
                    if expiry_dt > now_dt:
                        is_premium = True
                        premium_until = expiry_str
                except Exception as e:
                    print(f"[DATE] Parse error: {e}")
                    pass

            return {
                "success": True, 
                "linked": True, 
                "telegram_username": link.get("telegram_username"),
                "telegram_id": telegram_id,
                "is_premium": is_premium,
                "premium_until": premium_until
            }
        return {"success": True, "linked": False}
    except Exception as e:
        print(f"[LINK] Status Error: {e}")
        return {"success": False, "message": str(e)}

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

        if response.status_code in [200, 204]:
             return {"success": True, "message": "Unlinked successfully and premium status reset."}
        return {"success": False, "message": "Failed to unlink"}
    except Exception as e:
        print(f"[LINK] Unlink error: {e}")
        return {"success": False, "message": str(e)}

async def background_notification_worker():
    """Background task to poll for new products and notify users"""
    global LAST_PUSH_CHECK_TIME
    print("[PUSH] Worker started")
    
    # Load tokens from file at startup
    global USER_PUSH_TOKENS
    try:
        if os.path.exists("data/push_tokens.json"):
            with open("data/push_tokens.json", "r") as f:
                USER_PUSH_TOKENS = json.load(f)
    except: pass

    while True:
        try:
            await asyncio.sleep(60) # Check every 60 seconds
            
            # 1. Fetch all users with push tokens and their preferences
            if not http_client:
                 continue
                 
            try:
                response = await http_client.get(f"{URL}/rest/v1/users?select=id,notification_preferences,push_tokens", headers=HEADERS)
                
                users_data = []
                if response.status_code == 200:
                    users_data = response.json()
                else:
                    # Fallback to local memory tokens if DB columns aren't ready yet
                    # Only log this once per restart to avoid spam
                    if 'MIGRATION_WARNED' not in globals():
                        print(f"[PUSH] Warning: User preferences DB columns missing (Status {response.status_code}). Using local cache.")
                        print(f"       Please run the SQL migration to enable cloud sync.")
                        globals()['MIGRATION_WARNED'] = True
                    
                    for uid, tokens in USER_PUSH_TOKENS.items():
                        users_data.append({"id": uid, "push_tokens": tokens, "notification_preferences": {}})
            except Exception as e:
                print(f"[PUSH] Error fetching users: {e}")
                users_data = []
            
            if not users_data:
                continue

            # 2. Get latest products since LAST_PUSH_CHECK_TIME
            # We check the last 5 messages to ensure we don't miss any during worker overlap
            query = f"order=scraped_at.desc&limit=5"
            try:
                response = await http_client.get(f"{URL}/rest/v1/discord_messages?{query}", headers=HEADERS)
                if response.status_code == 200 and response.json():
                    messages = response.json()
                    new_messages = []
                    for m in messages:
                        dt = safe_parse_dt(m.get("scraped_at"))
                        if dt and dt > LAST_PUSH_CHECK_TIME:
                            new_messages.append(m)
                    
                    if new_messages:
                        print(f"[PUSH] {len(new_messages)} new product(s) detected. Processing notifications...")
                        
                        for msg in new_messages:
                            msg_region = msg.get("region", "USA Stores")
                            msg_category = msg.get("category_name", "General")
                            product_data = msg.get("product_data", {})
                            
                            # Professional Formatting
                            title = product_data.get("title", "New Deal Detected!")
                            if len(title) > 50: title = title[:47] + "..."
                            
                            # Generate sleek title with discount info
                            raw_was = str(product_data.get("was_price", "") or product_data.get("resell_price", "") or "")
                            raw_now = str(product_data.get("price", "") or "")
                            
                            # Clean prices for logic
                            def clean_p(v):
                                if not v or v.lower() in ["n/a", "0.0", "0"]: return 0
                                return float(re.sub(r'[^0-9.]', '', v))
                            
                            price_val = clean_p(raw_now)
                            was_val = clean_p(raw_was)
                            
                            # Generate Prefix
                            prefix = "🔥"
                            if was_val > price_val and price_val > 0:
                                discount = int(((was_val - price_val) / was_val) * 100)
                                if discount >= 10:
                                    prefix = f"📉 {discount}% OFF"
                            
                            final_title = f"{prefix}: {title}"
                            
                            # Enhanced informative body
                            body_parts = []
                            if price_val > 0:
                                body_parts.append(f"Price: ${raw_now}")
                            if was_val > 0 and was_val != price_val:
                                body_parts.append(f"Market: ${raw_was}")
                            
                            # Add Store/Region info
                            region_label = msg_region.replace(" Stores", "")
                            body_parts.append(f"{region_label} {msg_category}")
                            
                            body = " | ".join(body_parts)
                            
                            # Target specific users based on preferences
                            target_tokens = []
                            for u in users_data:
                                prefs = u.get("notification_preferences") or {}
                                tokens = u.get("push_tokens")
                                if not tokens: continue
                                
                                # Check master toggle (if stored in prefs)
                                if prefs.get("enabled") == False: continue
                                
                                # Check region/category filtering
                                # Format: {"USA Stores": ["ALL"], "UK Stores": ["flips"]}
                                user_regions = prefs.get("regions", {})
                                if not user_regions: 
                                    # Default: notify everyone if no prefs set (or you could be strict)
                                    target_tokens.extend(tokens if isinstance(tokens, list) else [tokens])
                                    continue
                                    
                                if msg_region in user_regions:
                                    allowed_cats = user_regions[msg_region]
                                    if "ALL" in allowed_cats or msg_category in allowed_cats:
                                        target_tokens.extend(tokens if isinstance(tokens, list) else [tokens])
                            
                            if target_tokens:
                                print(f"[PUSH] Sending to {len(set(target_tokens))} devices...")
                                await send_expo_push_notification(list(set(target_tokens)), final_title, body, {"product_id": str(msg["id"])})
                        
                        LAST_PUSH_CHECK_TIME = datetime.now(timezone.utc)
            except Exception as e:
                print(f"[PUSH] Error processing messages: {e}")
                
        except Exception as e:
            print(f"[PUSH] Worker error: {e}")
            await asyncio.sleep(60) # Sleep before retry


@app.post("/v1/auth/login")
async def login(background_tasks: BackgroundTasks, data: Dict = Body(...)):
    email = data.get("email")
    password = data.get("password")
    if not email or not password: raise HTTPException(status_code=400, detail="Email and password are required")
    user = await get_user_by_email(email)
    if not user: raise HTTPException(status_code=401, detail="Invalid email or password")
    stored_hash = user.get("password_hash")
    if not stored_hash or stored_hash != hash_password(password): raise HTTPException(status_code=401, detail="Invalid email or password")
    
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


@app.get("/")
async def root():
    return {"status": "online", "app": "hollowScan API", "v": "1.0.0"}

@app.get("/v1/categories")
async def get_categories():
    result = {}
    channels = []
    source = "none"
    try:
        storage_url = f"{URL}/storage/v1/object/authenticated/monitor-data/discord_josh/channels.json"
        channels_response = await http_client.get(storage_url, headers=HEADERS)
        if channels_response.status_code == 200:
            channels = channels_response.json() or []
            source = "remote"
            print(f"[CATEGORIES] ✓ Loaded {len(channels)} channels from remote")
    except Exception as e: print(f"[CATEGORIES] ✗ Remote channels fetch failed: {type(e).__name__}: {e}")
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
    return {"categories": result, "source": source, "channel_count": len(channels)}

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
async def get_feed(user_id: str, background_tasks: BackgroundTasks, region: Optional[str] = "ALL", category: Optional[str] = "ALL", offset: int = 0, limit: int = 20, country: Optional[str] = None, search: Optional[str] = None):
    if country and (not region or region == "ALL"): region = country
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
    premium_user = False
    try:
        premium_user = await verify_premium_status(user_id, background_tasks=background_tasks)
    except Exception as e: print(f"[FEED] Quota check error: {e}")
    all_products = []
    seen_signatures = set()
    current_sql_offset = offset
    chunks_scanned = 0
    # Increase scan depth for searches (Premium gets 1,000,000 message potential lookback)
    # Each request scans a chunk; has_more lets them keep "digging"
    base_max = 50 if premium_user else 30
    search_multiplier = 20 if search else 1
    max_chunks = base_max * search_multiplier
    batch_limit = 1000 if search else 50 # Much larger batches during search for speed
    
    db_end_reached = False
    while len(all_products) < limit and chunks_scanned < max_chunks:
        search_is_active = bool(search and search.strip())
        query = f"order=scraped_at.desc&offset={current_sql_offset}&limit={batch_limit}"
        
        # Region/Category Filter ONLY if NOT searching (to make search truly GLOBAL)
        if id_filter and not search_is_active:
             query += id_filter
             
        if search_is_active:
            keywords = [k.strip() for k in search.split() if len(k.strip()) >= 1]
            if keywords:
                or_parts = []
                for k in keywords:
                    # Optimized SQL Filter (Titles, Descriptions, Content, and Core Fields)
                    or_parts.append(f"content.ilike.*{k}*")
                    or_parts.append(f"raw_data->embeds->0->>title.ilike.*{k}*")
                    or_parts.append(f"raw_data->embeds->0->>description.ilike.*{k}*")
                    or_parts.append(f"raw_data->embed->>title.ilike.*{k}*")
                    or_parts.append(f"raw_data->embed->>description.ilike.*{k}*")
                    # Added back critical field checks for monitors that use them
                    or_parts.append(f"raw_data->embeds->0->fields->0->>value.ilike.*{k}*")
                    or_parts.append(f"raw_data->embeds->0->fields->1->>value.ilike.*{k}*")
                    or_parts.append(f"raw_data->embeds->0->author->>name.ilike.*{k}*")
                query += f"&or=({','.join(or_parts)})"
                
        try:
            response = await http_client.get(f"{URL}/rest/v1/discord_messages?{query}", headers=HEADERS)
            if response.status_code != 200: 
                print(f"[FEED] Error {response.status_code}: {response.text}")
                break
            messages = response.json()
            if not messages: 
                db_end_reached = True
                break
                
            for msg in messages:
                sig = _get_content_signature(msg)
                if sig in seen_signatures: continue
                prod = extract_product(msg, channel_map)
                if not prod: continue
                
                # Product refinement
                p_data = prod.get("product_data", {})
                price_val = p_data.get("price")
                resale_val = p_data.get("resell")
                was_val = p_data.get("was_price")
                has_image = p_data.get("image") and "placeholder" not in p_data.get("image")
                has_links = bool(p_data.get("buy_url") or (p_data.get("links") and any(p_data["links"].values())))
                
                try:
                    p_num = float(str(price_val or 0).replace(',', ''))
                    r_num = float(str(resale_val or 0).replace(',', ''))
                    w_num = float(str(was_val or 0).replace(',', ''))
                    has_any_price = p_num > 0 or r_num > 0 or w_num > 0
                except (ValueError, TypeError): has_any_price = bool(price_val or resale_val or was_val)
                
                # Product qualification: MUST have an image OR a price OR a buy link (matching Home Feed)
                if not (has_image or has_any_price or has_links): continue
                
                # Final Keyword Filter (OR logic on text blob)
                if search_is_active:
                    search_keywords = [k.lower().strip() for k in search.split() if k.strip()]
                    search_blob = f"{prod['product_data'].get('title','')}\n{prod['product_data'].get('description','')}\n{prod.get('category_name','')}"
                    for detail in prod["product_data"].get("details", []):
                        search_blob += f"\n{detail.get('label','')}: {detail.get('value','')}"
                    
                    search_blob = search_blob.lower()
                    match_found = False
                    for kw in search_keywords:
                        if kw in search_blob:
                            match_found = True
                            break
                    if not match_found: continue

                # Normal View Filtering (NOT for search)
                if not search_is_active:
                    if region and region.strip().upper() != "ALL":
                        if prod["region"].strip() != region.strip(): continue
                    if category and category.strip().upper() != "ALL":
                        if prod["category_name"].upper().strip() != category.upper().strip(): continue
                
                all_products.append(prod)
                seen_signatures.add(sig)
                if len(all_products) >= limit: break
            
            current_sql_offset += len(messages)
            chunks_scanned += 1
            # If we didn't find enough products but haven't hit the end, keep scanning
            if len(messages) < batch_limit: 
                db_end_reached = True
                break
        except Exception as e:
            print(f"[FEED] Error in batch fetch: {e}")
            break

    # Search Paging Logic:
    has_more = not db_end_reached
    
    if not premium_user:
        # Limit free users to 4 products total
        if len(all_products) > 4:
            all_products = all_products[:4]
            has_more = False
        for product in all_products: product["is_locked"] = False
        
    print(f"[FEED] Search/Feed complete. Found {len(all_products)} products scanning {current_sql_offset - offset} messages.")
    return {"products": all_products, "next_offset": current_sql_offset, "has_more": has_more, "is_premium": premium_user, "total_count": 100}

@app.get("/v1/user/status")
async def get_user_status(user_id: str):
    user = await get_user_by_id(user_id)
    if not user: raise HTTPException(status_code=404, detail="User not found")
    return {
        "status": user.get("subscription_status"), 
        "views_used": user.get("daily_free_alerts_viewed", 0), 
        "views_limit": 4, 
        "is_premium": user.get("subscription_status") == "active",
        "email_verified": user.get("email_verified", False)
    }



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


@app.get("/health")
async def health_check():
    return {"status": "healthy", "timestamp": datetime.now(timezone.utc).isoformat()}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)