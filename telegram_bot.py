import os
import json
import logging
import threading
import traceback
import requests
import asyncio
import re
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto
from telegram.constants import ParseMode
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
import supabase_utils
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
ADMIN_USER_ID = os.getenv("TELEGRAM_ADMIN_ID")
SUPABASE_BUCKET = "monitor-data"
USERS_FILE = "bot_users.json"
CODES_FILE = "active_codes.json"
POLL_INTERVAL = 120  # 2 minutes to prevent overlap
MAX_JOB_RUNTIME = 110  # Maximum allowed runtime
# JOB LOCK AND TIMEOUT
broadcast_lock = asyncio.Lock()
job_start_time = None

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

# Global lock to prevent job overlap
broadcast_lock = asyncio.Lock()

# --- DATETIME PARSING UTILITY ---

def parse_iso_datetime(iso_string: str) -> datetime:
    """
    Parse ISO format datetime string with flexible microseconds.
    Handles variable-length microsecond strings (3-6 digits).
    """
    if not iso_string:
        return datetime.utcnow()
    
    try:
        # Try direct parsing first
        return datetime.fromisoformat(iso_string)
    except ValueError:
        # Handle variable-length microseconds
        try:
            if "." in iso_string:
                parts = iso_string.split(".")
                if "+" in parts[1]:
                    ms, tz = parts[1].split("+")
                    ms = (ms + "000000")[:6]  # Pad or truncate to 6 digits
                    fixed_str = f"{parts[0]}.{ms}+{tz}"
                elif "-" in parts[1] and parts[1].count("-") > 0:
                    ms, tz = parts[1].rsplit("-", 1)
                    ms = (ms + "000000")[:6]
                    fixed_str = f"{parts[0]}.{ms}-{tz}"
                else:
                    # No timezone
                    ms = (parts[1] + "000000")[:6]
                    fixed_str = f"{parts[0]}.{ms}"
                return datetime.fromisoformat(fixed_str)
        except:
            pass
    
    # Fallback
    return datetime.utcnow()

# --- LINK PARSING UTILITIES ---

def extract_markdown_links(text: str) -> List[Dict[str, str]]:
    """Extract markdown-style links from text"""
    if not text:
        return []
    
    pattern = r'\[([^\]]+)\]\(([^\)]+)\)'
    links = []
    
    for match in re.finditer(pattern, text):
        link_text = match.group(1).strip()
        link_url = match.group(2).strip()
        
        if link_url.startswith('http'):
            links.append({'text': link_text, 'url': link_url})
    
    return links


def categorize_links(links: List[Dict[str, str]]) -> Dict[str, List[Dict[str, str]]]:
    """Categorize links into eBay, FBA, Buy, Other"""
    categories = {'ebay': [], 'fba': [], 'buy': [], 'other': []}
    
    ebay_keywords = ['sold', 'active', 'google', 'ebay']
    fba_keywords = ['keepa', 'amazon', 'selleramp', 'fba', 'camel']
    buy_keywords = ['buy', 'shop', 'purchase', 'checkout', 'cart']
    
    for link in links:
        text_lower = link['text'].lower()
        url_lower = link['url'].lower()
        
        if any(kw in text_lower or kw in url_lower for kw in ebay_keywords):
            categories['ebay'].append(link)
        elif any(kw in text_lower or kw in url_lower for kw in fba_keywords):
            categories['fba'].append(link)
        elif any(kw in text_lower or kw in url_lower for kw in buy_keywords):
            categories['buy'].append(link)
        else:
            categories['other'].append(link)
    
    return categories


def add_emoji_to_link_text(text: str) -> str:
    """Add emoji prefix to link text for better visual appeal"""
    emojis = {
        'sold': '💰', 'active': '⚡', 'google': '🔍', 'ebay': '🛒',
        'keepa': '📈', 'amazon': '🔎', 'selleramp': '💎', 'camel': '🐫',
        'buy': '🛒', 'shop': '🏪', 'cart': '🛒', 'checkout': '✅',
    }
    
    text_lower = text.lower()
    for keyword, emoji in emojis.items():
        if keyword in text_lower:
            return f"{emoji} {text}"
    
    return f"🔗 {text}"


def parse_tag_line(tag: str) -> Dict[str, Optional[str]]:
    """
    Parse Discord tag line above embeds.
    Example: "@Product Flips | [UK] CRW-001-1ER | Casio | Just restocked for £0.00"
    """
    if not tag:
        return {}
    
    parts = [p.strip() for p in tag.split('|')]
    result = {
        'ping': None, 'region': None, 'product_code': None,
        'brand': None, 'action': None, 'price': None, 'raw': tag
    }
    
    for part in parts:
        if part.startswith('@'):
            result['ping'] = part
        elif part.startswith('[') and part.endswith(']'):
            result['region'] = part.strip('[]')
        elif any(kw in part.lower() for kw in ['restocked', 'in stock', 'available']):
            result['action'] = part
            price_match = re.search(r'[£$€]\s*[\d,]+\.?\d*', part)
            if price_match:
                result['price'] = price_match.group(0)
        else:
            if result['product_code'] is None:
                result['product_code'] = part
            elif result['brand'] is None:
                result['brand'] = part
    
    return result


# --- SUBSCRIPTION MANAGER ---

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
                    old_expiry = parse_iso_datetime(self.users[str(user_id)]["expiry"])
                    if old_expiry > datetime.utcnow(): current_expiry = old_expiry
                except: pass
            
            new_expiry = current_expiry + timedelta(days=days)
            self.users[str(user_id)] = {
                "expiry": new_expiry.isoformat(), 
                "username": username or "Unknown",
                "alerts_paused": False,
                "joined_at": self.users.get(str(user_id), {}).get("joined_at", datetime.utcnow().isoformat())
            }
            self._sync_state()
            return True

    def get_active_users(self) -> List[str]:
        active = []
        now = datetime.utcnow()
        with self.lock:
            for uid, data in self.users.items():
                try:
                    if parse_iso_datetime(data["expiry"]) > now:
                        if not data.get("alerts_paused", False):
                            active.append(uid)
                except: pass
        return active
    
    def get_expiry(self, user_id: str):
        return self.users.get(str(user_id), {}).get("expiry")
    
    def is_active(self, user_id: str) -> bool:
        expiry = self.get_expiry(str(user_id))
        if not expiry: return False
        try:
            return parse_iso_datetime(expiry) > datetime.utcnow()
        except:
            return False
    
    def toggle_pause(self, user_id: str) -> bool:
        """Toggle pause status, returns new paused state"""
        with self.lock:
            if str(user_id) not in self.users:
                return False
            current = self.users[str(user_id)].get("alerts_paused", False)
            self.users[str(user_id)]["alerts_paused"] = not current
            self._sync_state()
            return not current
    
    def get_user_stats(self, user_id: str) -> Dict:
        """Get user statistics"""
        user_data = self.users.get(str(user_id), {})
        if not user_data:
            return None
        
        expiry = parse_iso_datetime(user_data["expiry"])
        joined = parse_iso_datetime(user_data.get("joined_at", datetime.utcnow().isoformat()))
        now = datetime.utcnow()
        
        return {
            "username": user_data.get("username", "Unknown"),
            "days_remaining": (expiry - now).days if expiry > now else 0,
            "days_active": (now - joined).days,
            "is_paused": user_data.get("alerts_paused", False),
            "expiry_date": expiry.strftime("%Y-%m-%d %H:%M UTC")
        }


# --- MESSAGE POLLER ---

class MessagePoller:
    def __init__(self):
        self.last_scraped_at = None
        self.sent_hashes = set()
        self.supabase_url, self.supabase_key = supabase_utils.get_supabase_config()
        self.cursor_file = "bot_cursor.json"
        self.local_path = f"data/{self.cursor_file}"
        self.remote_path = f"discord_josh/{self.cursor_file}"
        self._init_cursor()

    def _init_cursor(self):
        try:
            data = supabase_utils.download_file(self.local_path, self.remote_path, SUPABASE_BUCKET)
            if data: 
                loaded = json.loads(data)
                self.last_scraped_at = loaded.get("last_scraped_at")
                self.sent_hashes = set(loaded.get("sent_hashes", []))
            if not self.last_scraped_at: 
                self.last_scraped_at = (datetime.utcnow() - timedelta(hours=24)).isoformat()
        except:
            self.last_scraped_at = (datetime.utcnow() - timedelta(hours=24)).isoformat()

    def _save_cursor(self):
        try:
            with open(self.local_path, 'w') as f: 
                json.dump({
                    "last_scraped_at": self.last_scraped_at,
                    "sent_hashes": list(self.sent_hashes)[-1000:]
                }, f)
            supabase_utils.upload_file(self.local_path, SUPABASE_BUCKET, self.remote_path, debug=False)
        except: pass

    def poll_new_messages(self):
        try:
            if not self.last_scraped_at: 
                self.last_scraped_at = (datetime.utcnow() - timedelta(minutes=45)).isoformat()
            
            headers = {"apikey": self.supabase_key, "Authorization": f"Bearer {self.supabase_key}"}
            url = f"{self.supabase_url}/rest/v1/discord_messages"
            params = {"scraped_at": f"gt.{self.last_scraped_at}", "order": "scraped_at.asc"}
            
            res = requests.get(url, headers=headers, params=params, timeout=45)
            if res.status_code != 200: return []
            
            messages = res.json()
            
            # Filter duplicates by content hash
            new_messages = []
            for msg in messages:
                content_hash = msg.get("raw_data", {}).get("content_hash")
                if content_hash and content_hash not in self.sent_hashes:
                    new_messages.append(msg)
                    self.sent_hashes.add(content_hash)
            
            # DO NOT update cursor here - will be updated after successful broadcast
            
            return new_messages
        except Exception as e:
            logger.error(f"Poll error: {e}")
            return []
    
    def update_cursor(self, scraped_at: str):
        """Update cursor to given scraped_at timestamp after successful processing"""
        self.last_scraped_at = scraped_at
        self._save_cursor()


sm = SubscriptionManager()
poller = MessagePoller()


# --- PROFESSIONAL MESSAGE FORMATTING ---

# Phrases to remove from messages
PHRASES_TO_REMOVE = [
    "CCN 2.0 | Profitable Pinger",
    " Monitors v2.0.0 | CCN x Zephyr Monitors #ad",
    " Monitors v2.0.0 | CCN x Zephyr Monitors",
    "CCN 2.0 | Profitable Pinger",
    "@Unfiltered",
    "CCN"
]

# Regex patterns to remove (for dynamic content like timestamps)
REGEX_PATTERNS_TO_REMOVE = [
    r'Monitors\s+v[\d.]+\s*\|\s*CCN\s+x\s+Zephyr\s+Monitors\s*\[\d{2}:\d{2}:\d{2}\]',
    r'\s*\|\s*CCN\s+x\s+Zephyr\s+Monitors\s+\[[^\]]+\].*',
    r'Today\s+at\s+\d{1,2}:\d{2}\s*(?:AM|PM)',
]

def clean_text(text: str) -> str:
    """Remove unwanted phrases from text"""
    if not text:
        return text
    
    # Remove literal phrases
    for phrase in PHRASES_TO_REMOVE:
        text = re.sub(re.escape(phrase), "", text, flags=re.IGNORECASE)
    
    # Remove patterns with regex
    for pattern in REGEX_PATTERNS_TO_REMOVE:
        text = re.sub(pattern, "", text, flags=re.IGNORECASE)
    
    # Clean up extra whitespace
    text = re.sub(r'\s+', ' ', text).strip()
    return text


# --- CHANNEL SPECIFIC FORMATTERS ---

CHANNEL_COLLECTORS = "1367813504786108526"
CHANNEL_ARGOS = "855164313006505994"
CHANNEL_RESTOCKS = "864504557903937587"

def _format_collectors_amazon(msg_data: Dict, embed: Dict) -> Tuple[List[str], List[List[InlineKeyboardButton]]]:
    """Formatter for Collectors Edge / Amazon V3 (Channel 136...)"""
    lines = []
    keyboard = []
    
    # 1. Header & Title (Retailer or Author)
    author_name = msg_data.get("raw_data", {}).get("author", {}).get("name")
    if not author_name and embed.get("author"):
        author_name = embed["author"].get("name")
        
    if author_name and "unknown" not in author_name.lower():
        lines.append(f"🏪 <b>{clean_text(author_name)}</b>")
        lines.append("")

    title = clean_text(embed.get("title", "Product Alert"))
    lines.append(f"📦 <b>{title}</b>")
    lines.append("━━━━━━━━━━━━━━━")
    lines.append("")
    
    # 2. ALL Fields (comprehensive)
    fields = embed.get("fields", [])
    seen_values = set()
    
    for f in fields:
        name = clean_text(f.get("name", ""))
        val = clean_text(f.get("value", ""))
        
        # Skip link/button fields and N/A values
        if not name or not val: continue
        if any(kw in name.lower() for kw in ['link', 'atc', 'qt', 'checkout']): continue
        if "n/a" in val.lower(): continue
        if val in seen_values: continue
        seen_values.add(val)
        
        # Smart icon selection
        name_lower = name.lower()
        if "price" in name_lower: icon = "💰"
        elif "stock" in name_lower or "in stock" in name_lower: icon = "✅"
        elif "type" in name_lower: icon = "🔖"
        elif "size" in name_lower: icon = "📏"
        elif "quantity" in name_lower or "qty" in name_lower: icon = "🔢"
        else: icon = "•"
        
        # Add currency symbol and bold prices
        if "price" in name_lower:
            # Add £ if no currency symbol present
            if not any(c in val for c in ['£', '$', '€']):
                val = f"£{val}"
            lines.append(f"{icon} <b>{name}:</b> <b>{val}</b>")
        else:
            lines.append(f"{icon} <b>{name}:</b> {val}")
        
    lines.append("")
    
    return lines, []

def _format_argos(msg_data: Dict, embed: Dict) -> Tuple[List[str], List[List[InlineKeyboardButton]]]:
    """Formatter for Argos Instore (Channel 855...)"""
    lines = []
    
    lines.append("🏪 <b>Argos Instore</b>")
    lines.append("")
    
    title = clean_text(embed.get("title", "Item Restock"))
    lines.append(f"📦 <b>{title}</b>")
    lines.append("━━━━━━━━━━━━━━━")
    lines.append("")
    
    # Display ALL fields
    fields = embed.get("fields", [])
    seen_values = set()
    
    for f in fields:
        name = clean_text(f.get("name", ""))
        val = clean_text(f.get("value", ""))
        
        if not name or not val: continue
        if any(kw in name.lower() for kw in ['link', 'atc', 'qt', 'checkout', 'offer id']): continue
        if "n/a" in val.lower(): continue
        if val in seen_values: continue
        seen_values.add(val)
        
        name_lower = name.lower()
        if "store" in name_lower or "availability" in name_lower: icon = "📍"
        elif "price" in name_lower: icon = "💰"
        elif "stock" in name_lower: icon = "✅"
        elif "size" in name_lower: icon = "📏"
        else: icon = "•"
        
        # Add currency to prices
        if "price" in name_lower and val:
            if not any(c in val for c in ['£', '$', '€']):
                val = f"£{val}"
        
        lines.append(f"{icon} <b>{name}:</b> {val}")
    
    return lines, []

def _format_restocks_currys(msg_data: Dict, embed: Dict) -> Tuple[List[str], List[List[InlineKeyboardButton]]]:
    """Formatter for Online Restocks / Currys (Channel 864...)"""
    lines = []
    
    # This channel puts "Product Info" with "Just Restocked At..."
    fields = embed.get("fields", [])
    prod_info = ""
    resell = ""
    price = ""
    
    for f in fields:
        name = clean_text(f.get("name", "")).lower()
        val = clean_text(f.get("value", ""))
        if "product info" in name: prod_info = val
        if "resell" in name and "n/a" not in val.lower(): resell = val
        if "price" in name and "n/a" not in val.lower(): price = val
        
    # Extract site from product info if possible
    site = "Online Restocks"
    if "just restocked at" in prod_info.lower():
        try:
            site = prod_info.lower().split("just restocked at")[-1].strip()
            site = site.replace("**", "").strip()
        except: pass
        
    lines.append(f"⚡ <b>{site.upper()}</b>")
    lines.append("")
    
    title = clean_text(embed.get("title", "Product"))
    lines.append(f"📦 <b>{title}</b>")
    lines.append("━━━━━━━━━━━━━━━")
    lines.append("")
    
    # Display ALL fields with smart prioritization
    seen_values = set()
    for f in fields:
        name = clean_text(f.get("name", ""))
        val = clean_text(f.get("value", ""))
        
        if not name or not val: continue
        if any(kw in name.lower() for kw in ['link', 'atc', 'qt', 'checkout', 'offer id']): continue  
        if "n/a" in val.lower(): continue
        if val in seen_values: continue
        seen_values.add(val)
        
        name_lower = name.lower()
        if "price" in name_lower: icon = "💰"
        elif "resell" in name_lower or "profit" in name_lower: icon = "📈"
        elif "type" in name_lower: icon = "🔖"
        elif "stock" in name_lower: icon = "✅"
        elif "product info" in name_lower: icon = "ℹ️"
        else: icon = "•"
        
        if "price" in name_lower:
            # Add £ if no currency symbol
            if not any(c in val for c in ['£', '$', '€']):
                val = f"£{val}"
            lines.append(f"{icon} <b>{name}:</b> <b>{val}</b>")
        else:
            lines.append(f"{icon} <b>{name}:</b> {val}")
        
    lines.append("")
    
    return lines, []

def format_telegram_message(msg_data: Dict) -> Tuple[str, List[str], Optional[InlineKeyboardMarkup]]:
    """
    Dispatcher for channel-specific formatting with Fallback to Generic.
    """
    raw = msg_data.get("raw_data", {})
    embed = raw.get("embed")
    # author = raw.get("author", {}) # Unused
    plain_content = msg_data.get("content", "")
    channel_id = str(msg_data.get("channel_id", ""))
    
    # Parse tag info just in case
    tag_info = parse_tag_line(plain_content) if plain_content else {}
    
    lines = []
    custom_buttons = []
    
    # === DISPATCHER ===
    if embed:
        if channel_id == CHANNEL_COLLECTORS:
            l, b = _format_collectors_amazon(msg_data, embed)
            lines.extend(l)
            custom_buttons.extend(b)
        elif channel_id == CHANNEL_ARGOS:
            l, b = _format_argos(msg_data, embed)
            lines.extend(l)
            custom_buttons.extend(b)
        elif channel_id == CHANNEL_RESTOCKS:
            l, b = _format_restocks_currys(msg_data, embed)
            lines.extend(l)
            custom_buttons.extend(b)
        else:
            # === FALLBACK/GENERIC FORMATTER (Original Logic Refined) ===
            # RETAILER/SOURCE
            retailer = None
            if embed.get("author"):
                retailer = clean_text(embed["author"].get("name"))
            elif tag_info.get("brand"):
                retailer = clean_text(tag_info["brand"])
            
            if retailer and "unknown" not in retailer.lower():
                lines.append(f"🏪 <b>{retailer}</b>")
                lines.append("")
            
            # TITLE
            title = clean_text(embed.get("title") or tag_info.get("product_code") or "Product Alert")
            if tag_info.get("region"): title = f"[{tag_info['region']}] {title}"
            
            lines.append(f"📦 <b>{title}</b>")
            lines.append("━━━━━━━━━━━━━━━")
            lines.append("")
            
            # DESC
            if embed.get("description"):
                desc = clean_text(embed["description"])[:400]
                if len(clean_text(embed["description"])) > 400: desc += "..."
                lines.append(desc)
                lines.append("")
            
            # FIELDS
            seen_values = set()
            if embed.get("fields"):
                for field in embed["fields"]:
                    name = clean_text(field.get("name", ""))
                    value = clean_text(field.get("value", ""))
                    
                    if name and value and not any(kw in name.lower() for kw in ['link', 'atc', 'qt', 'checkout', 'offer id']):
                        # Skip N/A values
                        if "n/a" in value.lower(): continue

                        if value in seen_values: continue
                        seen_values.add(value)
                        
                        # Enhanced emoji mapping for comprehensive field coverage
                        name_lower = name.lower()
                        if "status" in name_lower or "stock" in name_lower or "in stock" in name_lower: 
                            icon = "✅"
                        elif "price" in name_lower or "cost" in name_lower: 
                            icon = "💰"
                        elif "type" in name_lower:
                            icon = "🔖"
                        elif "resell" in name_lower or "profit" in name_lower: 
                            icon = "📈"
                        elif "member" in name_lower: 
                            icon = "👥"
                        elif "store" in name_lower or "shop" in name_lower: 
                            icon = "🏪"
                        elif "size" in name_lower: 
                            icon = "📏"
                        elif "product" in name_lower: 
                            icon = "📦"
                        elif "region" in name_lower or "location" in name_lower:
                            icon = "🌍"
                        elif "quantity" in name_lower or "qty" in name_lower:
                            icon = "🔢"
                        else: 
                            icon = "•"
                        
                        if "price" in name_lower:
                            # Add £ if no currency symbol
                            if not any(c in value for c in ['£', '$', '€']):
                                value = f"£{value}"
                            lines.append(f"{icon} <b>{name}:</b> <b>{value}</b>")
                        else:
                            lines.append(f"{icon} <b>{name}:</b> {value}")
            lines.append("")
        
        # FOOTER (Common)
        footer = embed.get("footer")
        if footer and "ccn" not in footer.lower() and "monitor" not in footer.lower():
            lines.append(f"⏰ {footer}")
        else:
            scraped_time = parse_iso_datetime(msg_data.get("scraped_at", datetime.utcnow().isoformat()))
            lines.append(f"⏰ {scraped_time.strftime('%H:%M UTC')}")
            
    else:
        # HUMAN MESSAGE FALLBACK (Refined)
        if plain_content:
            # Don't show generic title if content is short/simple
            if tag_info.get("product_code"): lines.append(f"📦 <b>{clean_text(tag_info['product_code'])}</b>")
            
            # Clean up content
            content_display = clean_text(plain_content)
            # If content starts with "Restocks |", bold it or make it a header
            if content_display.lower().startswith("restocks |"):
                parts = content_display.split("|")
                if len(parts) > 1:
                    header = parts[0].strip()
                    body = " | ".join(parts[1:]).strip()
                    lines.append(f"⚡ <b>{header}</b>")
                    lines.append("")
                    lines.append(body)
                else:
                    lines.append(content_display)
            else:
                 lines.append(content_display[:800])

            scraped_time = parse_iso_datetime(msg_data.get("scraped_at", datetime.utcnow().isoformat()))
            lines.append("")
            lines.append(f"⏰ {scraped_time.strftime('%H:%M:%S UTC')}")
    
    text = "\n".join(lines)
    
    # === IMAGE EXTRACTION ===
    images = []
    if embed:
        if embed.get("images"): images.extend(embed["images"][:3])
        elif embed.get("thumbnail"): images.append(embed["thumbnail"])
    
    # === BUTTON CREATION (GENERIC + CUSTOM) ===
    keyboard = []
    
    # Logic for button creation same as before (extracting from fields/links)
    if embed and embed.get("links"):
        all_links = embed["links"]
        seen_urls = set()
        ebay_links = []
        fba_links = []
        atc_links = []
        buy_links = []
        other_links = []
        
        for link in all_links:
            text_lower = link.get('text', '').lower()
            url = link.get('url', '')
            link_text = link.get('text', 'Link')
            field = link.get('field', '').lower()
            
            if not url or not url.startswith('http'): continue
            if url in seen_urls: continue
            
            if 'atc' in field or 'qt' in field:
                atc_links.append({'text': link_text, 'url': url, 'field': field})
                seen_urls.add(url)
            elif 'link' in field:
                # These are the main links from the Links field
                if any(kw in text_lower for kw in ['sold', 'active', 'google', 'ebay']):
                    ebay_links.append({'text': link_text, 'url': url})
                    seen_urls.add(url)
                elif any(kw in text_lower for kw in ['keepa', 'amazon', 'selleramp', 'camel']):
                    fba_links.append({'text': link_text, 'url': url})
                    seen_urls.add(url)
                elif any(kw in text_lower for kw in ['buy', 'shop', 'purchase', 'checkout', 'cart']):
                    buy_links.append({'text': link_text, 'url': url})
                    seen_urls.add(url)
                else:
                    other_links.append({'text': link_text, 'url': url})
                    seen_urls.add(url)
            else:
                # Uncategorized links from other fields
                if any(kw in text_lower for kw in ['sold', 'active', 'google', 'ebay']):
                    ebay_links.append({'text': link_text, 'url': url})
                    seen_urls.add(url)
                elif any(kw in text_lower for kw in ['keepa', 'amazon', 'selleramp', 'camel']):
                    fba_links.append({'text': link_text, 'url': url})
                    seen_urls.add(url)
                elif any(kw in text_lower for kw in ['buy', 'shop', 'purchase', 'checkout', 'cart']):
                    buy_links.append({'text': link_text, 'url': url})
                    seen_urls.add(url)
                else:
                    other_links.append({'text': link_text, 'url': url})
                    seen_urls.add(url)
        
        # Row 1: Price Checking (eBay links)
        if ebay_links:
            row = []
            for link in ebay_links[:3]:
                emoji = '💰' if 'sold' in link['text'].lower() else '⚡'
                btn_text = f"{emoji} {link['text'][:15]}"
                row.append(InlineKeyboardButton(btn_text, url=link['url']))
            if row:
                keyboard.append(row)
        
        # Row 2: FBA/Analysis
        if fba_links:
            row = []
            for link in fba_links[:3]:
                emoji = '📈' if 'keepa' in link['text'].lower() else '🔎'
                btn_text = f"{emoji} {link['text'][:15]}"
                row.append(InlineKeyboardButton(btn_text, url=link['url']))
            if row:
                keyboard.append(row)
        
        # Row 3: Direct Buy Links
        if buy_links:
            row = []
            for link in buy_links[:2]:
                btn_text = f"🛒 {link['text'][:18]}"
                row.append(InlineKeyboardButton(btn_text, url=link['url']))
            if row:
                keyboard.append(row)
        
        # Row 4: ATC (Add To Cart) Options
        if atc_links:
            row = []
            for link in atc_links[:5]:
                # Extract quantity from text if possible
                qty_match = re.search(r'\d+', link['text'])
                qty = qty_match.group(0) if qty_match else link['text']
                btn_text = f"🛒 {qty}"
                row.append(InlineKeyboardButton(btn_text, url=link['url']))
                if len(row) == 3:
                    keyboard.append(row)
                    row = []
            if row:
                keyboard.append(row)
        
        # Row 5: Other Links
        if other_links:
            row = []
            for link in other_links[:3]:
                btn_text = f"🔗 {link['text'][:15]}"
                row.append(InlineKeyboardButton(btn_text, url=link['url']))
            if row:
                keyboard.append(row)
    
    # Add custom buttons if any
    if custom_buttons:
        keyboard.extend(custom_buttons)
    
    return text, images, InlineKeyboardMarkup(keyboard) if keyboard else None


def is_duplicate_source(msg_data: Dict) -> bool:
    """
    Check if message is from a duplicate source (like Profitable Pinger).
    These are filtered out to avoid duplicate alerts.
    """
    raw = msg_data.get("raw_data", {})
    embed = raw.get("embed") or {}
    plain_content = msg_data.get("content", "")
    
    # Check author name
    author_name = (raw.get("author", {}) or {}).get("name", "")
    if author_name and "profitable pinger" in author_name.lower():
        return True
    
    # Check embed author (only if embed exists)
    if embed:
        embed_author = (embed.get("author") or {}).get("name", "")
        if embed_author and "profitable pinger" in embed_author.lower():
            return True
        
        # Check footer (bot signature)
        footer = embed.get("footer", "")
        if footer and "profitable pinger" in footer.lower():
            return True
    
    # Check all fields in embed
    if embed and embed.get("fields"):
        for field in embed["fields"]:
            val = (field.get("value") or "").lower()
            name = (field.get("name") or "").lower()
            if "profitable pinger" in val or "profitable pinger" in name:
                return True
                
    # Check title and description
    if embed:
        title = (embed.get("title") or "").lower()
        desc = (embed.get("description") or "").lower()
        if "profitable pinger" in title or "profitable pinger" in desc:
            return True


    return False


def create_main_menu() -> InlineKeyboardMarkup:
    """Create main menu keyboard"""
    keyboard = [
        [InlineKeyboardButton("📊 My Status", callback_data="status")],
        [InlineKeyboardButton("🔔 Toggle Alerts", callback_data="toggle_pause")],
        [InlineKeyboardButton("🎟️ Redeem Code", callback_data="redeem")],
        [InlineKeyboardButton("❓ Help", callback_data="help")]
    ]
    return InlineKeyboardMarkup(keyboard)


def create_menu_with_back(buttons: List[List[InlineKeyboardButton]], back_to: str = "main") -> InlineKeyboardMarkup:
    """Create menu with back button"""
    keyboard = buttons + [
        [InlineKeyboardButton("◀️ Back", callback_data=f"back:{back_to}")]
    ]
    return InlineKeyboardMarkup(keyboard)


# --- COMMAND HANDLERS ---

async def test_alerts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Test command to replay recent N messages.
    Usage: /test [N] (default 1)
    """
    user_id = str(update.effective_user.id)
    if user_id != ADMIN_USER_ID:
        await update.message.reply_text("⛔ Admin only.")
        return

    try:
        count = 1
        if context.args:
            count = int(context.args[0])
            count = min(max(count, 1), 10)  # Clamp between 1 and 10
    except ValueError:
        await update.message.reply_text("usage: /test [number]")
        return

    await update.message.reply_text(f"🔍 Fetching last {count} messages...")
    
    # Fetch from Supabase directly
    try:
        headers = {"apikey": poller.supabase_key, "Authorization": f"Bearer {poller.supabase_key}"}
        url = f"{poller.supabase_url}/rest/v1/discord_messages"
        params = {
            "select": "*",
            "order": "scraped_at.desc",
            "limit": count
        }
        
        res = requests.get(url, headers=headers, params=params, timeout=10)
        if res.status_code != 200:
            await update.message.reply_text(f"❌ API Error: {res.status_code}")
            return
            
        messages = res.json()
        if not messages:
            await update.message.reply_text("⚠️ No messages found in DB.")
            return

        # Reverse to show oldest first behavior? 
        # Actually usually nice to see latest, but broadcasting sends older first.
        # Let's send in the order fetched (descending) or reverse for chronological replay.
        # Let's do reverse to mimic "stream"
        messages.reverse() 
        
        for msg in messages:
            text, images, keyboard = format_telegram_message(msg)
            
            # Send (Admin only)
            if images:
                try:
                   await context.bot.send_photo(
                        chat_id=user_id,
                        photo=images[0],
                        caption=text,
                        parse_mode=ParseMode.HTML,
                        reply_markup=keyboard
                    )
                except Exception as e:
                     await context.bot.send_message(
                        chat_id=user_id,
                        text=f"Image failed: {text}",
                        parse_mode=ParseMode.HTML,
                        reply_markup=keyboard
                    )
            else:
                 await context.bot.send_message(
                    chat_id=user_id,
                    text=text,
                    parse_mode=ParseMode.HTML,
                    reply_markup=keyboard
                )
            await asyncio.sleep(0.5)

        await update.message.reply_text("✅ Test complete.")

    except Exception as e:
        logger.error(f"Test error: {e}")
        await update.message.reply_text(f"❌ Error: {str(e)}")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Welcome message with main menu"""
    user_id = str(update.effective_user.id)
    username = update.effective_user.username or update.effective_user.first_name
    
    welcome_text = f"""
👋 <b>Welcome to Professional Discord Alerts!</b>

Hello {username}! Get instant product alerts with all the data you need.

<b>🎯 Features:</b>
• ⚡ Real-time notifications
• 🖼️ Product images
• 🔗 Direct action links
• 📊 Full stock & price data
• ⏸️ Pause/Resume anytime

<b>📋 Status:</b>
"""
    
    if sm.is_active(user_id):
        stats = sm.get_user_stats(user_id)
        welcome_text += f"✅ <b>Active</b> - {stats['days_remaining']} days remaining\n"
        if stats['is_paused']:
            welcome_text += "⏸️ Alerts currently paused\n"
    else:
        welcome_text += "❌ <b>Not subscribed</b>\n\nRedeem a code to get started!\n"
    
    await update.message.reply_text(
        welcome_text,
        parse_mode=ParseMode.HTML,
        reply_markup=create_main_menu()
    )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle inline keyboard button presses with back navigation"""
    query = update.callback_query
    await query.answer()
    
    user_id = str(update.effective_user.id)
    action = query.data
    
    # Handle back button
    if action.startswith("back:"):
        menu_to_go = action.split(":", 1)[1]
        if menu_to_go == "main":
            await query.edit_message_text("📋 <b>Main Menu</b>", parse_mode=ParseMode.HTML, reply_markup=create_main_menu())
        return
    
    if action == "status":
        if not sm.is_active(user_id):
            text = "❌ <b>Not Subscribed</b>\n\nUse /start to redeem a code!"
        else:
            stats = sm.get_user_stats(user_id)
            text = f"""
📊 <b>Your Subscription</b>

👤 User: {stats['username']}
⏰ Expires: {stats['expiry_date']}
⏳ Days Left: {stats['days_remaining']}
📅 Member Since: {stats['days_active']} days

🔔 Alerts: {'⏸️ PAUSED' if stats['is_paused'] else '✅ Active'}
"""
        
        buttons = [[InlineKeyboardButton("🔄 Refresh", callback_data="status")]]
        await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=create_menu_with_back(buttons, "main"))
    
    elif action == "toggle_pause":
        if not sm.is_active(user_id):
            buttons = []
            await query.edit_message_text("❌ You need an active subscription!", parse_mode=ParseMode.HTML, reply_markup=create_menu_with_back(buttons, "main"))
            return
        
        new_state = sm.toggle_pause(user_id)
        status = "⏸️ PAUSED" if new_state else "✅ RESUMED"
        
        text = f"""
{status} <b>Alerts {status}</b>

Your alerts have been {'paused' if new_state else 'resumed'}.
Toggle anytime from the menu.
"""
        buttons = [[InlineKeyboardButton("📊 Status", callback_data="status")]]
        await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=create_menu_with_back(buttons, "main"))
    
    elif action == "redeem":
        text = """
🎟️ <b>Redeem Subscription Code</b>

Send your code in this format:
<code>XXXXXXXX</code>

Example: <code>ABC123DEF456</code>

Get a code from your administrator!
"""
        buttons = []
        await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=create_menu_with_back(buttons, "main"))
    
    elif action == "help":
        text = """
❓ <b>Help & Information</b>

<b>How It Works:</b>
1️⃣ Redeem a subscription code
2️⃣ Receive real-time alerts with images & links
3️⃣ Click buttons to check eBay, Keepa, Amazon instantly

<b>Commands:</b>
• /start - Main menu & status

<b>Tips:</b>
• Enable Telegram notifications
• Keep alerts active for drops
• Use pause when needed

<b>Need Support?</b>
Contact your administrator!
"""
        buttons = []
        await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=create_menu_with_back(buttons, "main"))


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle code redemption"""
    user_id = str(update.effective_user.id)
    username = update.effective_user.username or update.effective_user.first_name
    text = update.message.text.strip().upper()
    
    code = text.replace("-", "").replace(" ", "")
    
    if len(code) >= 8 and len(code) <= 16:
        if sm.redeem_code(user_id, username, code):
            stats = sm.get_user_stats(user_id)
            response = f"""
🎉 <b>Code Redeemed Successfully!</b>

✅ Subscription Active
⏰ Expires: {stats['expiry_date']}
⏳ Days: {stats['days_remaining']}

You'll now receive professional alerts!
Use /start for the menu.
"""
            await update.message.reply_text(response, parse_mode=ParseMode.HTML)
        else:
            await update.message.reply_text(
                "❌ <b>Invalid Code</b>\n\nCheck your code and try again.",
                parse_mode=ParseMode.HTML
            )
    else:
        await update.message.reply_text(
            "💡 Send a subscription code or use /start for the menu.",
            parse_mode=ParseMode.HTML
        )


async def gen_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin: Generate codes"""
    if str(update.effective_user.id) != str(ADMIN_USER_ID): 
        return
    
    try:
        days = int(context.args[0])
        code = sm.generate_code(days)
        await update.message.reply_text(
            f"🔑 <b>New Code Generated</b>\n\nCode: <code>{code}</code>\nDuration: {days} days",
            parse_mode=ParseMode.HTML
        )
    except:
        await update.message.reply_text("Usage: /gen <days>")

async def broadcast_job(context: ContextTypes.DEFAULT_TYPE):
    """
    Poll for new messages and broadcast with timeout protection.
    Uses async lock to prevent overlap and timeout to prevent hanging.
    """
    global job_start_time
    
    # Check if lock is already acquired (job still running)
    if broadcast_lock.locked():
        logger.warning("⚠️  Previous broadcast job still running - SKIPPING this cycle")
        if job_start_time:
            elapsed = (datetime.utcnow() - job_start_time).total_seconds()
            logger.warning(f"   Job has been running for {elapsed:.1f}s")
        return
    
    # Acquire lock
    async with broadcast_lock:
        job_start_time = datetime.utcnow()
        logger.info(f"🔄 Broadcast job started at {job_start_time.strftime('%H:%M:%S')}")
        
        try:
            # Wrap the entire job in a timeout
            await asyncio.wait_for(
                _broadcast_job_inner(context),
                timeout=MAX_JOB_RUNTIME
            )
            
            elapsed = (datetime.utcnow() - job_start_time).total_seconds()
            logger.info(f"✅ Broadcast job completed in {elapsed:.1f}s")
            
        except asyncio.TimeoutError:
            elapsed = (datetime.utcnow() - job_start_time).total_seconds()
            logger.error(f"❌ Broadcast job TIMEOUT after {elapsed:.1f}s - forcing termination")
            
        except Exception as e:
            elapsed = (datetime.utcnow() - job_start_time).total_seconds()
            logger.error(f"❌ Broadcast job error after {elapsed:.1f}s: {type(e).__name__}: {e}")
            logger.error(f"   Full traceback: {traceback.format_exc()}")
        
        finally:
            job_start_time = None


async def _broadcast_job_inner(context: ContextTypes.DEFAULT_TYPE):
    """Inner broadcast logic - separated for timeout handling"""
    
    # Poll for new messages
    try:
        new_msgs = poller.poll_new_messages()
    except Exception as e:
        logger.error(f"❌ Failed to poll messages: {e}")
        return
    
    if not new_msgs:
        logger.debug("🔭 Poll: No new messages found")
        return
    
    # Filter out duplicate sources
    filtered_msgs = [msg for msg in new_msgs if not is_duplicate_source(msg)]
    
    if len(filtered_msgs) < len(new_msgs):
        skipped_count = len(new_msgs) - len(filtered_msgs)
        logger.info(f"📬 Poll: Found {len(new_msgs)} message(s), skipped {skipped_count} duplicate source(s)")
    else:
        logger.info(f"📬 Poll: Found {len(new_msgs)} new message(s)")
    
    if not filtered_msgs:
        logger.debug("🔭 No messages after filtering duplicates")
        return
    
    # Get active users
    active_users = sm.get_active_users()
    
    if not active_users:
        logger.warning(f"⚠️  BROADCAST BLOCKED: No active users!")
        logger.warning(f"   Total users: {len(sm.users)}")
        logger.warning(f"   New messages waiting: {len(filtered_msgs)}")
        return
    
    logger.info(f"📤 BROADCAST: {len(filtered_msgs)} message(s) → {len(active_users)} active user(s)")
    
    # Process messages with batching
    for msg_idx, msg in enumerate(filtered_msgs):
        try:
            logger.debug(f"   🔨 Formatting message {msg_idx + 1}/{len(filtered_msgs)}...")
            text, images, keyboard = format_telegram_message(msg)
            logger.debug(f"   ✓ Formatted (text={len(text)} chars, images={len(images) if images else 0})")
            
            # Validate message is not empty
            if not text or len(text.strip()) == 0:
                logger.error(f"   ❌ Message {msg_idx + 1} produced empty text - SKIPPING")
                logger.error(f"      Channel ID: {msg.get('channel_id')}")
                logger.error(f"      Has embed: {bool(msg.get('raw_data', {}).get('embed'))}")
                logger.error(f"      Content: {msg.get('content', '')[:100]}")
                continue
            
        except Exception as e:
            logger.error(f"   ❌ Failed to format message {msg_idx + 1}: {type(e).__name__}: {e}")
            continue
        
        # Send to all active users with rate limiting
        sent_count = 0
        failed_count = 0
        
        for uid in active_users:
            try:
                # Send with timeout protection
                if images:
                    try:
                        await asyncio.wait_for(
                            context.bot.send_photo(
                                chat_id=uid,
                                photo=images[0],
                                caption=text[:1024],
                                parse_mode=ParseMode.HTML,
                                reply_markup=keyboard
                            ),
                            timeout=10.0
                        )
                        
                        # Send additional images if multiple
                        if len(images) > 1:
                            media_group = [InputMediaPhoto(img) for img in images[1:3]]
                            await asyncio.wait_for(
                                context.bot.send_media_group(chat_id=uid, media=media_group),
                                timeout=10.0
                            )
                        sent_count += 1
                        
                    except asyncio.TimeoutError:
                        logger.warning(f"   ⏱️  {uid}: Photo send timeout")
                        # Fallback to text
                        await asyncio.wait_for(
                            context.bot.send_message(
                                chat_id=uid,
                                text=text,
                                parse_mode=ParseMode.HTML,
                                reply_markup=keyboard,
                                disable_web_page_preview=False
                            ),
                            timeout=10.0
                        )
                        sent_count += 1
                        
                    except Exception as photo_error:
                        logger.error(f"   ❌ {uid}: Photo failed - {type(photo_error).__name__}")
                        # Fallback to text
                        try:
                            await asyncio.wait_for(
                                context.bot.send_message(
                                    chat_id=uid,
                                    text=text,
                                    parse_mode=ParseMode.HTML,
                                    reply_markup=keyboard,
                                    disable_web_page_preview=False
                                ),
                                timeout=10.0
                            )
                            sent_count += 1
                        except:
                            failed_count += 1
                else:
                    # Text-only
                    await asyncio.wait_for(
                        context.bot.send_message(
                            chat_id=uid,
                            text=text,
                            parse_mode=ParseMode.HTML,
                            reply_markup=keyboard,
                            disable_web_page_preview=False
                        ),
                        timeout=10.0
                    )
                    sent_count += 1
            
            except asyncio.TimeoutError:
                logger.warning(f"   ⏱️  {uid}: Message send timeout")
                failed_count += 1
                
            except Exception as e:
                error_str = str(e)
                if "user not found" in error_str.lower() or "chat_id_invalid" in error_str.lower():
                    logger.warning(f"   ⛔ {uid}: User invalid/blocked")
                elif "bot was blocked" in error_str.lower():
                    logger.warning(f"   🚫 {uid}: Bot blocked by user")
                elif "badrequest" in error_str.lower():
                    # Log full error for BadRequest to diagnose formatting issues
                    logger.error(f"   ❌ {uid}: BadRequest - {error_str}")
                    logger.error(f"      Message preview: {text[:200]}...")
                else:
                    logger.error(f"   ❌ {uid}: {type(e).__name__}: {error_str}")
                failed_count += 1
            
            # Rate limit protection - small delay between users
            await asyncio.sleep(0.05)
        
        logger.info(f"   📊 Message {msg_idx + 1}: ✅ {sent_count} sent, ❌ {failed_count} failed")
        
        # Update cursor ONLY after successful processing of this message
        # This ensures failed messages are retried on next poll
        if sent_count > 0:  # At least one user received it
            msg_scraped_at = msg.get("scraped_at")
            if msg_scraped_at:
                poller.update_cursor(msg_scraped_at)
                logger.debug(f"   📌 Cursor updated to: {msg_scraped_at}")


# 4. UPDATE run_bot() FUNCTION
def run_bot():
    """Run bot with professional alert system"""
    try:
        if not TELEGRAM_TOKEN:
            logger.error("❌ TELEGRAM_TOKEN not set!")
            return
        
        logger.info("\n" + "=" * 80)
        logger.info("🚀 TELEGRAM BOT INITIALIZATION")
        logger.info("=" * 80)
        logger.info(f"   Token: {TELEGRAM_TOKEN[:15]}...***{TELEGRAM_TOKEN[-5:]}")
        logger.info(f"   Admin ID: {ADMIN_USER_ID}")
        logger.info(f"   Poll Interval: {POLL_INTERVAL} seconds")
        logger.info(f"   Max Runtime: {MAX_JOB_RUNTIME} seconds")
        
        app = Application.builder().token(TELEGRAM_TOKEN).build()
        
        # Command Handlers
        app.add_handler(CommandHandler("start", start))
        app.add_handler(CommandHandler("gen", gen_code))
        app.add_handler(CommandHandler("test", test_alerts))  # New Test Command
        app.add_handler(CallbackQueryHandler(button_handler))
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
        
        if app.job_queue:
            logger.info("   Adding broadcast job with overlap protection...")
            app.job_queue.run_repeating(
                broadcast_job, 
                interval=POLL_INTERVAL, 
                first=10
            )
            logger.info(f"   ✅ Job queue running (poll every {POLL_INTERVAL}s)")
        
        # Show active users count on startup
        active_count = len(sm.get_active_users())
        total_count = len(sm.users)
        logger.info(f"   📊 Users: {total_count} total, {active_count} active")
        logger.info("=" * 80 + "\n")
        
        logger.info("📡 Starting polling loop...")
        app.run_polling(allowed_updates=Update.ALL_TYPES, stop_signals=[])
        
    except KeyboardInterrupt:
        logger.info("⚠️  Bot interrupted by user")
    except Exception as e:
        logger.error(f"❌ CRITICAL BOT ERROR: {e}")
        logger.error(traceback.format_exc())
