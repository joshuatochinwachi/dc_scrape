import os
import json
import logging
import threading
import traceback
import requests
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import Application, CommandHandler, ContextTypes
import supabase_utils
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
ADMIN_USER_ID = os.getenv("TELEGRAM_ADMIN_ID")
SUPABASE_BUCKET = "monitor-data"
USERS_FILE = "bot_users.json"
CODES_FILE = "active_codes.json"
POLL_INTERVAL = 30

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
# Silence httpx to prevent token leaks in logs
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

class SubscriptionManager:
    def __init__(self):
        self.users: Dict[str, Dict] = {} 
        self.codes: Dict[str, int] = {}
        self.lock = threading.Lock()
        self.remote_users_path = f"discord_josh/{USERS_FILE}"
        self.remote_codes_path = f"discord_josh/{CODES_FILE}"
        self.local_users_path = f"data/{USERS_FILE}"
        self.local_codes_path = f"data/{CODES_FILE}"
        os.makedirs("data", exist_ok=True)
        self._load_state()

    def _load_state(self):
        try:
            data = supabase_utils.download_file(self.local_users_path, self.remote_users_path, SUPABASE_BUCKET)
            if data: self.users = json.loads(data)
        except: pass
        try:
            data = supabase_utils.download_file(self.local_codes_path, self.remote_codes_path, SUPABASE_BUCKET)
            if data: self.codes = json.loads(data)
        except: pass

    def _sync_state(self):
        try:
            with open(self.local_users_path, 'w') as f: json.dump(self.users, f)
            supabase_utils.upload_file(self.local_users_path, SUPABASE_BUCKET, self.remote_users_path, debug=False)
            with open(self.local_codes_path, 'w') as f: json.dump(self.codes, f)
            supabase_utils.upload_file(self.local_codes_path, SUPABASE_BUCKET, self.remote_codes_path, debug=False)
        except Exception as e:
            logger.error(f"Sync error: {e}")

    def generate_code(self, days: int) -> str:
        import secrets
        code = secrets.token_hex(4).upper()
        with self.lock:
            self.codes[code] = days
            self._sync_state()
        return code

    def redeem_code(self, user_id: str, username: str, code: str) -> bool:
        with self.lock:
            if code not in self.codes: return False
            days = self.codes.pop(code)
            current_expiry = datetime.utcnow()
            if str(user_id) in self.users:
                try:
                    old_expiry = datetime.fromisoformat(self.users[str(user_id)]["expiry"])
                    if old_expiry > datetime.utcnow(): current_expiry = old_expiry
                except: pass
            
            new_expiry = current_expiry + timedelta(days=days)
            self.users[str(user_id)] = {"expiry": new_expiry.isoformat(), "username": username or "Unknown"}
            self._sync_state()
            return True

    def get_active_users(self) -> List[str]:
        active = []
        now = datetime.utcnow()
        with self.lock:
            for uid, data in self.users.items():
                try:
                    if datetime.fromisoformat(data["expiry"]) > now: active.append(uid)
                except: pass
        return active
    
    def get_expiry(self, user_id: str):
        return self.users.get(str(user_id), {}).get("expiry")

class MessagePoller:
    def __init__(self):
        self.last_scraped_at = None
        self.supabase_url, self.supabase_key = supabase_utils.get_supabase_config()
        self.cursor_file = "bot_cursor.json"
        self.local_path = f"data/{self.cursor_file}"
        self.remote_path = f"discord_josh/{self.cursor_file}"
        self._init_cursor()

    def _init_cursor(self):
        try:
            data = supabase_utils.download_file(self.local_path, self.remote_path, SUPABASE_BUCKET)
            if data: self.last_scraped_at = json.loads(data).get("last_scraped_at")
            if not self.last_scraped_at: self.last_scraped_at = (datetime.utcnow() - timedelta(hours=24)).isoformat()
        except:
            self.last_scraped_at = (datetime.utcnow() - timedelta(hours=24)).isoformat()

    def _save_cursor(self):
        try:
            with open(self.local_path, 'w') as f: json.dump({"last_scraped_at": self.last_scraped_at}, f)
            supabase_utils.upload_file(self.local_path, SUPABASE_BUCKET, self.remote_path, debug=False)
        except: pass

    def poll_new_messages(self):
        try:
            if not self.last_scraped_at: self.last_scraped_at = (datetime.utcnow() - timedelta(minutes=5)).isoformat()
            headers = {"apikey": self.supabase_key, "Authorization": f"Bearer {self.supabase_key}"}
            url = f"{self.supabase_url}/rest/v1/discord_messages"
            params = {"scraped_at": f"gt.{self.last_scraped_at}", "order": "scraped_at.asc"}
            
            res = requests.get(url, headers=headers, params=params, timeout=10)
            if res.status_code != 200: return []
            
            messages = res.json()
            if messages and isinstance(messages, list):
                self.last_scraped_at = messages[-1].get('scraped_at')
                self._save_cursor()
            return messages
        except Exception as e:
            logger.error(f"Poll error: {e}")
            return []

sm = SubscriptionManager()
poller = MessagePoller()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("👋 Discord Alert Bot Active.\n/redeem <CODE> to subscribe.")

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    expiry = sm.get_expiry(str(update.effective_user.id))
    await update.message.reply_text(f"✅ Active until: {expiry}" if expiry else "❌ Not subscribed.")

async def redeem(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args: return await update.message.reply_text("Usage: /redeem <CODE>")
    if sm.redeem_code(str(update.effective_user.id), update.effective_user.username, context.args[0].strip().upper()):
        await update.message.reply_text(f"🎉 Subscribed until {sm.get_expiry(str(update.effective_user.id))}")
    else:
        await update.message.reply_text("❌ Invalid code.")

async def gen_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_user.id) != str(ADMIN_USER_ID): return
    try:
        days = int(context.args[0])
        await update.message.reply_text(f"🔑 Code: `{sm.generate_code(days)}`")
    except: await update.message.reply_text("Usage: /gen <days>")

async def broadcast_job(context: ContextTypes.DEFAULT_TYPE):
    try:
        new_msgs = poller.poll_new_messages()
        if not new_msgs: return
        active_users = sm.get_active_users()
        if not active_users: return

        for msg in new_msgs:
            raw = msg.get("raw_data", {})
            text = f"📢 <b>{raw.get('author', 'Unknown')}</b> in #{raw.get('channel_url', '').split('/')[-1]}\n\n{msg.get('content', '')}"
            text = (text[:4000] + '..') if len(text) > 4000 else text
            
            for uid in active_users:
                try:
                    await context.bot.send_message(chat_id=uid, text=text, parse_mode=ParseMode.HTML, disable_web_page_preview=True)
                    img = raw.get("media", {}).get("images", [])
                    if img and "url" in img[0]:
                        await context.bot.send_photo(chat_id=uid, photo=img[0]["url"])
                except Exception as e: logger.error(f"Send fail {uid}: {e}")
    except Exception as e: logger.error(f"Job error: {e}")

def run_bot():
    """Run bot in thread-safe mode without signal handlers"""
    if not TELEGRAM_TOKEN: return
    
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(CommandHandler("redeem", redeem))
    app.add_handler(CommandHandler("gen", gen_code))
    
    if app.job_queue: 
        app.job_queue.run_repeating(broadcast_job, interval=POLL_INTERVAL, first=10)
    
    # Use stop_signals=[] to prevent signal handler registration
    # This allows the bot to run safely in a background thread
    app.run_polling(allowed_updates=Update.ALL_TYPES, stop_signals=[])