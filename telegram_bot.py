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
from concurrent.futures import ThreadPoolExecutor
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto, BotCommand, BotCommandScopeChat, BotCommandScopeDefault
from telegram.constants import ParseMode
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
from bs4 import BeautifulSoup
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
POTENTIAL_USERS_FILE = "potential_users.json"
# JOB LOCK AND TIMEOUT
broadcast_lock = asyncio.Lock()
job_start_time = None

# Thread pool for blocking sync operations (image downloading, web scraping)
sync_executor = ThreadPoolExecutor(max_workers=5, thread_name_prefix="sync_io")

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


# --- IMAGE SCRAPING FROM PRODUCT WEBSITES ---

def fetch_product_images(url: str, max_images: int = 3) -> List[str]:
    """
    Scrape product images from a website URL.
    Extracts up to max_images high-quality images.
    Returns list of image URLs.
    """
    if not url or not url.startswith('http'):
        return []
    
    try:
        # Set a proper user agent to avoid blocking
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.content, 'html.parser')
        images = []
        
        # Keywords to skip (logos, navigation, UI elements)
        skip_keywords = [
            'logo', 'icon', 'placeholder', 'avatar', 'pixel', '1x1', 'spinner', 'loading',
            'nav', 'menu', 'footer', 'header', 'banner', 'ad', 'social', 'share', 'btn',
            'badge', 'flag', 'currency', 'rating', 'star', 'heart', 'like', 'comment',
            'thumbnail', 'thumb', 'variant', 'swatch', 'color-swatch'
        ]
        
        # Keywords that indicate product images (MAIN images preferred)
        main_product_keywords = [
            'main', 'gallery', 'hero', 'primary', 'feature', 'featured',
            'large', 'full', 'display', 'showcase'
        ]
        
        # Secondary product keywords
        product_keywords = [
            'product', 'item', 'photo', 'image', 'picture', 'detail',
            'view', 'front', 'back', 'side'
        ]
        
        # Priority 0: Meta Tags (The most reliable verification)
        # Sites explicitly define these for social sharing
        for meta in soup.find_all('meta'):
            prop = meta.get('property', '')
            name = meta.get('name', '')
            if prop in ['og:image', 'twitter:image'] or name in ['og:image', 'twitter:image']:
                 meta_url = meta.get('content')
                 if meta_url and meta_url.startswith('http') and not any(k in meta_url.lower() for k in skip_keywords):
                     images.append({
                        'url': meta_url,
                        'alt': 'Meta Tag Image',
                        'priority': 1000 # Super high priority
                     })

        # Priority 1: Look for product images in data attributes and meta tags
        for img in soup.find_all('img'):
            img_url = img.get('src') or img.get('data-src') or img.get('data-lazy-src')
            if not img_url:
                continue
            
            # Convert relative URLs to absolute
            if img_url.startswith('/'):
                from urllib.parse import urljoin
                img_url = urljoin(url, img_url)
            
            # Skip data URIs
            if img_url.startswith('data:'):
                continue
            
            # 2a. HARD FILTER: Verify it looks like a product image
            # Discard tiny images which are likely icons
            if 'width' in img.attrs and 'height' in img.attrs:
                try:
                    w = int(str(img['width']).replace('px',''))
                    h = int(str(img['height']).replace('px',''))
                    if w < 100 or h < 100: continue # Too small to be a product
                except: pass
            
            # Skip if URL contains skip keywords

            img_url_lower = img_url.lower()
            if any(skip in img_url_lower for skip in skip_keywords):
                continue
            
            # Get alt text and class info
            alt_text = img.get('alt', '').lower()
            img_class = img.get('class', [])
            if isinstance(img_class, list):
                img_class = ' '.join(img_class).lower()
            else:
                img_class = str(img_class).lower()
            
            # Check ID attribute too
            img_id = img.get('id', '').lower()
            
            # Get parent container info
            parent = img.parent
            parent_class = ''
            parent_id = ''
            if parent:
                parent_class = parent.get('class', [])
                if isinstance(parent_class, list):
                    parent_class = ' '.join(parent_class).lower()
                else:
                    parent_class = str(parent_class).lower()
                
                parent_id = parent.get('id', '').lower()
                
                # Also check grandparent for gallery/main containers
                grandparent = parent.parent
                if grandparent:
                    gp_class = grandparent.get('class', [])
                    if isinstance(gp_class, list):
                        gp_class = ' '.join(gp_class).lower()
                    else:
                        gp_class = str(gp_class).lower()
                    parent_class += ' ' + gp_class
            
            # Calculate priority score
            priority = 0
            
            # HIGHEST PRIORITY: In main/gallery container
            if any(kw in parent_class or kw in parent_id for kw in ['main', 'gallery', 'hero', 'primary', 'feature']):
                priority += 500
            if any(kw in img_id for kw in ['main', 'gallery', 'hero', 'primary', 'feature']):
                priority += 450
            
            # VERY HIGH PRIORITY: Main product keywords in alt/class
            if any(kw in alt_text for kw in main_product_keywords):
                priority += 200
            if any(kw in img_class for kw in main_product_keywords):
                priority += 180
            
            # HIGH PRIORITY: General product keywords
            if any(kw in alt_text for kw in product_keywords):
                priority += 100
            if any(kw in img_class for kw in product_keywords):
                priority += 90
            if any(kw in parent_class for kw in product_keywords):
                priority += 80
            
            # MEDIUM PRIORITY: Product keywords in URL
            if any(kw in img_url_lower for kw in product_keywords):
                priority += 50
            
            # MEDIUM PRIORITY: Large images (product images usually 300px+)
            width = img.get('width')
            height = img.get('height')
            if width and height:
                try:
                    w = int(str(width).replace('px', ''))
                    h = int(str(height).replace('px', ''))
                    # Prefer larger images (main product images)
                    if w >= 500 and h >= 500:
                        priority += 100
                    elif w >= 300 and h >= 300:
                        priority += 50
                    elif w >= 200 and h >= 200:
                        priority += 10
                except:
                    pass
            
            # PENALTY: Likely a variant/option image
            if any(x in img_url_lower for x in ['variant', 'color', 'option']):
                priority -= 100
            
            # Skip if priority too low (likely decoration/nav)
            if priority < 10:
                continue
            
            images.append({
                'url': img_url,
                'alt': alt_text,
                'priority': priority
            })
        
        # Sort by priority (highest first)
        images.sort(key=lambda x: x['priority'], reverse=True)
        
        # Remove duplicates and return just URLs
        seen = set()
        result = []
        for img in images:
            img_url = img['url']
            if img_url not in seen and img_url:
                seen.add(img_url)
                result.append(img_url)
                if len(result) >= max_images:
                    break
        
        logger.info(f"   📸 Scraped {len(result)} product image(s) from website")
        if result:
            logger.info(f"      First image: {result[0][:100]}...")
        return result
        
    except Exception as e:
        logger.info(f"   ⚠️ Could not scrape images from {url}: {str(e)}")
        return []


def download_image_without_compression(image_url: str) -> Optional[bytes]:
    """
    Download an image and return raw bytes without compression.
    Useful for preserving Discord embed image quality.
    """
    if not image_url or not image_url.startswith('http'):
        return None
    
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        response = requests.get(image_url, headers=headers, timeout=10)
        response.raise_for_status()
        
        # Return raw bytes to preserve original quality
        return response.content
        
    except Exception as e:
        logger.info(f"   ⚠️ Could not download image {image_url}: {str(e)}")
        return None


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
        self.potential_users: Dict[str, Dict] = {}
        self.lock = threading.Lock()
        self.remote_users_path = f"discord_josh/{USERS_FILE}"
        self.remote_codes_path = f"discord_josh/{CODES_FILE}"
        self.remote_potential_path = f"discord_josh/{POTENTIAL_USERS_FILE}"
        self.local_users_path = f"data/{USERS_FILE}"
        self.local_codes_path = f"data/{CODES_FILE}"
        self.local_potential_path = f"data/{POTENTIAL_USERS_FILE}"
        os.makedirs("data", exist_ok=True)
        self._load_state()

    def _load_state(self):
        """Load state from Supabase with local fallback"""
        # Load Users
        users_loaded = False
        try:
            data = supabase_utils.download_file(self.local_users_path, self.remote_users_path, SUPABASE_BUCKET)
            if data: 
                self.users = json.loads(data)
                users_loaded = True
                logger.info(f"✅ Loaded {len(self.users)} users from Supabase")
        except Exception as e:
            logger.warning(f"⚠️ Failed to download users from Supabase: {e}")
            
        if not users_loaded and os.path.exists(self.local_users_path):
            try:
                with open(self.local_users_path, 'r') as f:
                    self.users = json.load(f)
                logger.info(f"📂 Loaded {len(self.users)} users from local fallback")
            except Exception as e:
                logger.error(f"❌ Failed to load local users fallback: {e}")

        # Load Codes
        codes_loaded = False
        try:
            data = supabase_utils.download_file(self.local_codes_path, self.remote_codes_path, SUPABASE_BUCKET)
            if data:
                self.codes = json.loads(data)
                codes_loaded = True
        except Exception as e:
            logger.warning(f"⚠️ Failed to download codes from Supabase: {e}")

        if not codes_loaded and os.path.exists(self.local_codes_path):
            try:
                with open(self.local_codes_path, 'r') as f:
                    self.codes = json.load(f)
            except: pass

        # Load Potential Users
        potential_loaded = False
        try:
            data = supabase_utils.download_file(self.local_potential_path, self.remote_potential_path, SUPABASE_BUCKET)
            if data:
                self.potential_users = json.loads(data)
                potential_loaded = True
        except: pass

        if not potential_loaded and os.path.exists(self.local_potential_path):
            try:
                with open(self.local_potential_path, 'r') as f:
                    self.potential_users = json.load(f)
            except: pass

    def _sync_state(self):
        try:
            with open(self.local_users_path, 'w') as f: json.dump(self.users, f)
            supabase_utils.upload_file(self.local_users_path, SUPABASE_BUCKET, self.remote_users_path, debug=False)
            with open(self.local_codes_path, 'w') as f: json.dump(self.codes, f)
            supabase_utils.upload_file(self.local_codes_path, SUPABASE_BUCKET, self.remote_codes_path, debug=False)
            with open(self.local_potential_path, 'w') as f: json.dump(self.potential_users, f)
            supabase_utils.upload_file(self.local_potential_path, SUPABASE_BUCKET, self.remote_potential_path, debug=False)
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
            # Remove from potential users if they were there
            if str(user_id) in self.potential_users:
                self.potential_users.pop(str(user_id))
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
            "expiry_date": expiry.strftime("%Y-%m-%d %H:%M UTC"),
            "is_admin": user_data.get("is_admin", False)
        }

    def add_admin(self, user_id: str) -> bool:
        """Set a user as admin"""
        with self.lock:
            if str(user_id) not in self.users:
                # Add a placeholder user if they don't exist yet? 
                # Or just error out. Let's assume they must be in the system.
                return False
            self.users[str(user_id)]["is_admin"] = True
            self._sync_state()
            return True

    def remove_admin(self, user_id: str) -> bool:
        """Remove admin status from a user"""
        with self.lock:
            if str(user_id) in self.users:
                self.users[str(user_id)]["is_admin"] = False
                self._sync_state()
                return True
            return False

    def is_bot_admin(self, user_id: str) -> bool:
        """Check if a user is a secondary admin"""
        return self.users.get(str(user_id), {}).get("is_admin", False)

    def get_all_admins(self) -> List[str]:
        """Get list of all admin IDs (Superadmin + Secondary)"""
        admins = [str(ADMIN_USER_ID)]
        with self.lock:
            for uid, data in self.users.items():
                if data.get("is_admin"):
                    if uid not in admins:
                        admins.append(uid)
        return admins

    def get_expired_users_needing_reminder(self) -> List[str]:
        """Get users with expired subscriptions who haven't been reminded in 14 days"""
        needing_reminder = []
        now = datetime.utcnow()
        with self.lock:
            for uid, data in self.users.items():
                try:
                    expiry = parse_iso_datetime(data["expiry"])
                    if expiry < now:
                        last_reminder_str = data.get("last_expiry_reminder")
                        should_remind = False
                        
                        if not last_reminder_str:
                            should_remind = True
                        else:
                            last_reminder = parse_iso_datetime(last_reminder_str)
                            if (now - last_reminder).days >= 14:
                                should_remind = True
                        
                        if should_remind:
                            needing_reminder.append(uid)
                except Exception as e:
                    logger.error(f"Error checking reminder for {uid}: {e}")
        return needing_reminder

    def update_reminder_timestamp(self, user_id: str):
        """Update last_expiry_reminder timestamp only and sync to Supabase"""
        with self.lock:
            uid = str(user_id)
            if uid in self.users:
                self.users[uid]["last_expiry_reminder"] = datetime.utcnow().isoformat()
                self._sync_state()

    def track_potential_user(self, user_id: str, username: str):
        """Track user who ran /start but isn't subscribed"""
        with self.lock:
            uid = str(user_id)
            # Only add if not an active user and not already in potential list
            if uid not in self.users and uid not in self.potential_users:
                self.potential_users[uid] = {
                    "username": username or "Unknown",
                    "first_seen": datetime.utcnow().isoformat(),
                    "last_reminder": None
                }
                self._sync_state()

    def get_potential_users_needing_reminder(self) -> List[str]:
        """Get potential users who haven't been reminded in 14 days"""
        needing_reminder = []
        now = datetime.utcnow()
        with self.lock:
            for uid, data in self.potential_users.items():
                last_reminder_str = data.get("last_reminder")
                if not last_reminder_str:
                    # First reminder after 14 days of joining
                    first_seen = parse_iso_datetime(data["first_seen"])
                    if (now - first_seen).days >= 14:
                        needing_reminder.append(uid)
                else:
                    last_reminder = parse_iso_datetime(last_reminder_str)
                    if (now - last_reminder).days >= 14:
                        needing_reminder.append(uid)
        return needing_reminder

    def update_potential_reminder_timestamp(self, user_id: str):
        """Update last_reminder timestamp for potential user"""
        with self.lock:
            uid = str(user_id)
            if uid in self.potential_users:
                self.potential_users[uid]["last_reminder"] = datetime.utcnow().isoformat()
                self._sync_state()


# --- MESSAGE POLLER ---

class MessagePoller:
    def __init__(self):
        self.last_scraped_at = None
        self.sent_ids = set()
        self.recent_signatures = []  # Last 3 sent content signatures
        self.supabase_url, self.supabase_key = supabase_utils.get_supabase_config()
        self.cursor_file = "bot_cursor.json"
        self.local_path = f"data/{self.cursor_file}"
        self.remote_path = f"discord_josh/{self.cursor_file}"
        self.time_based_signatures = {}  # {sig_hash: timestamp_iso}
        self._init_cursor()

    def _init_cursor(self):
        try:
            data = supabase_utils.download_file(self.local_path, self.remote_path, SUPABASE_BUCKET)
            if data: 
                loaded = json.loads(data)
                self.last_scraped_at = loaded.get("last_scraped_at")
                # Support migration from sent_hashes to sent_ids
                self.sent_ids = set(loaded.get("sent_ids", loaded.get("sent_hashes", [])))
                # Load persistent signatures
                self.recent_signatures = loaded.get("recent_signatures", [])
                # Load time-based signatures
                self.time_based_signatures = loaded.get("time_based_signatures", {})
            if not self.last_scraped_at: 
                self.last_scraped_at = (datetime.utcnow() - timedelta(hours=24)).isoformat()
        except:
            self.last_scraped_at = (datetime.utcnow() - timedelta(hours=24)).isoformat()

    def _save_cursor(self):
        try:
            with open(self.local_path, 'w') as f: 
                json.dump({
                    "last_scraped_at": self.last_scraped_at,
                    "sent_ids": list(self.sent_ids)[-5000:],  # Increased to 5000 IDs
                    "recent_signatures": self.recent_signatures[-20:], # Increased to last 20
                    "time_based_signatures": self.time_based_signatures
                }, f)
            supabase_utils.upload_file(self.local_path, SUPABASE_BUCKET, self.remote_path, debug=False)
        except: pass

    def _get_content_signature(self, msg: Dict) -> str:
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
                # Pattern: "@Mention | Product Name | Retailer | Just restocked for £XX.XX"
                if content and "|" in content:
                    parts = [p.strip() for p in content.split("|")]
                    if len(parts) >= 3:
                        # parts[0] is usually @Mention, but sometimes it's the product
                        # We'll use the logic that if we still need title/retailer, we try to grab them
                        if not title and len(parts) > 1:
                            title = parts[1]
                        if not retailer and len(parts) > 2:
                            retailer = parts[2]
                        if not price:
                            # Extract price from any part that matches a currency pattern
                            # Search the whole content for the most likely price
                            price_match = re.search(r'[£$€]\s*[\d,]+\.?\d*', content)
                            if price_match:
                                price = price_match.group(0)
                
            # Final fallback for Argos or other specific keywords if still empty
            if not retailer and "Argos" in content:
                retailer = "Argos Instore"
            
            # Create raw signature and hash it
            raw_sig = f"{retailer}|{title}|{price}".lower().strip()
            
            # If everything is still empty, use content hash or ID
            if raw_sig == "||":
                return hashlib.md5(content.encode()).hexdigest() if content else str(msg.get("id"))
                
            import hashlib
            return hashlib.md5(raw_sig.encode()).hexdigest()
        except Exception as e:
            logger.error(f"Error generating signature: {e}")
            return str(msg.get("id"))

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
            now_iso = datetime.utcnow().isoformat()
            now_dt = datetime.utcnow()
            
            # Prune time-based signatures older than 10 minutes
            pruned_sigs = {}
            for s, ts in self.time_based_signatures.items():
                if (now_dt - parse_iso_datetime(ts)) < timedelta(minutes=10):
                    pruned_sigs[s] = ts
            self.time_based_signatures = pruned_sigs

            new_messages = []
            for msg in messages:
                msg_id = msg.get("id")
                # LAYER 1: Discord ID Check (All-time tracking)
                if not msg_id or str(msg_id) in self.sent_ids:
                    continue
                
                sig = self._get_content_signature(msg)
                
                # LAYER 2: Content Signature (Sliding Window - last 20)
                if sig in self.recent_signatures:
                    logger.info(f"⏭️ LAYER 2 BLOCK: Duplicate content window: {msg_id} (Sig: {sig})")
                    self.sent_ids.add(str(msg_id))
                    continue
                
                # LAYER 3: Time-Based Deduplication (10-minute window)
                if sig in self.time_based_signatures:
                    logger.info(f"⏭️ LAYER 3 BLOCK: Duplicate content within 10m: {msg_id} (Sig: {sig})")
                    self.sent_ids.add(str(msg_id))
                    continue

                # MESSAGE ACCEPTED - Add to tracking IMMEDIATELY
                new_messages.append(msg)
                self.sent_ids.add(str(msg_id))
                self.recent_signatures.append(sig)
                self.recent_signatures = self.recent_signatures[-20:] # Keep last 20
                self.time_based_signatures[sig] = now_iso
            
            if new_messages:
                # Save cursor immediately after polling if new messages found
                self._save_cursor()
                
            return new_messages
        except Exception as e:
            logger.error(f"Poll error: {e}")
            return []
    
    def update_cursor(self, scraped_at: str, msg_data: Optional[Dict] = None):
        """Update cursor to given scraped_at timestamp"""
        self.last_scraped_at = scraped_at
        self._save_cursor()


sm = SubscriptionManager()
poller = MessagePoller()

# --- ADMIN PERMISSION HELPERS ---

def is_superadmin(user_id: str) -> bool:
    """Check if user is the main admin from .env"""
    return str(user_id) == str(ADMIN_USER_ID)

def is_admin(user_id: str) -> bool:
    """Check if user is either superadmin or secondary admin"""
    uid_str = str(user_id)
    return is_superadmin(uid_str) or sm.is_bot_admin(uid_str)

async def notify_admins(context: ContextTypes.DEFAULT_TYPE, text: str):
    """Notify all admins of an event/error"""
    admin_ids = sm.get_all_admins()
    for aid in admin_ids:
        try:
            await context.bot.send_message(chat_id=aid, text=text, parse_mode=ParseMode.HTML)
        except Exception as e:
            logger.error(f"Failed to notify admin {aid}: {e}")


# --- PROFESSIONAL MESSAGE FORMATTING ---

# Phrases to remove from messages
PHRASES_TO_REMOVE = [
    "CCN 2.0 | Profitable Pinger",
    " Monitors v2.0.0 | CCN x Zephyr Monitors #ad",
    " Monitors v2.0.0 | CCN x Zephyr Monitors",
    "CCN 2.0 | Profitable Pinger",
    "@Unfiltered",
    "CCN",
    "@Product Flips"
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

def format_price_value(value: str) -> str:
    """
    Format price value for Telegram with smart discount detection.
    
    Detects patterns like:
    - '2.95 (-32%) 1.99' -> '<s>£2.95</s> (-32%) <b>£1.99</b>'
    - '£2.95 (-32%) £1.99' -> '<s>£2.95</s> (-32%) <b>£1.99</b>'
    - '~~2.95~~ 1.99' -> '<s>£2.95</s> <b>£1.99</b>'
    - Simple prices like '5.99' -> '£5.99'
    """
    if not value: 
        return value
    
    # Strip leading/trailing whitespace
    value = value.strip()
    
    # Helper to ensure currency symbol
    def ensure_currency(price_str):
        price_str = price_str.strip()
        if price_str and not any(c in price_str for c in ['£', '$', '€']):
            return f"£{price_str}"
        return price_str
    
    # Pattern 1: Detect discount format "ORIGINAL_PRICE (PERCENT%) DISCOUNTED_PRICE"
    # Matches: "2.95 (-32%) 1.99", "£2.95 (-32%) £1.99", "0.95 (-47%) 0.5"
    discount_pattern = r'([£$€]?\d+(?:[.,]\d{1,2})?)[\s]*\((-?\d+%?)\)[\s]*([£$€]?\d+(?:[.,]\d{1,2})?)'
    
    match = re.search(discount_pattern, value)
    if match:
        original_price = ensure_currency(match.group(1))
        discount_percent = match.group(2)
        # Ensure percent has % if it doesn't
        if '%' not in discount_percent:
            discount_percent = f"{discount_percent}%"
        discounted_price = ensure_currency(match.group(3))
        
        # Format: strikethrough original, bold discounted
        return f"<s>{original_price}</s> ({discount_percent}) <b>{discounted_price}</b>"
    
    # Pattern 2: Discord markdown strikethrough ~~text~~
    if '~~' in value:
        # Convert ~~text~~ to <s>text</s>
        value = re.sub(r'~~([^~]+)~~', r'<s>\1</s>', value)
        
        # Find any remaining prices and ensure they have currency + bold the last one
        prices = re.findall(r'[£$€]?\d+(?:[.,]\d{1,2})?', value)
        if prices:
            last_price = prices[-1]
            # Bold the discounted price (last price not in strikethrough)
            if f"<s>{last_price}</s>" not in value and f"<s>£{last_price}</s>" not in value:
                value = value.replace(last_price, f"<b>{ensure_currency(last_price)}</b>", 1)
    
    # Pattern 3: Simple price without discount - just ensure currency symbol
    # Only add currency if it's a simple standalone price
    simple_price_pattern = r'^[£$€]?\d+(?:[.,]\d{1,2})?$'
    if re.match(simple_price_pattern, value.strip()):
        return ensure_currency(value.strip())
    
    # Fallback: ensure all standalone numeric prices have currency symbols
    # But don't match numbers that are part of a decimal (like "99" in "2.99")
    # And don't add £ to numbers that are followed by currency codes like USD, EUR
    def add_currency_to_prices(text):
        def replacer(m):
            price = m.group(0)
            # Check what comes after this match in the original text
            end_pos = m.end()
            suffix = text[end_pos:end_pos+10].strip().upper()
            
            # Don't add £ if followed by currency code (it already has a denomination)
            if suffix.startswith(('USD', 'EUR', 'GBP', 'CAD', 'AUD')):
                return price  # Leave as-is, it has a currency label
            
            if not any(c in price for c in ['£', '$', '€']):
                return f"£{price}"
            return price
        # Match complete prices only - must not be preceded by decimal point, currency, or digit
        # and must not be followed by % or digit (unless it's the decimal portion)
        return re.sub(r'(?<![£$€\d.])\d+(?:\.\d{1,2})?(?![%\d])', replacer, text)
    
    return add_currency_to_prices(value)


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
            val = format_price_value(val)
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
            val = format_price_value(val)
        
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
            val = format_price_value(val)
            lines.append(f"{icon} <b>{name}:</b> <b>{val}</b>")
        else:
            lines.append(f"{icon} <b>{name}:</b> {val}")
        
    lines.append("")
    
    return lines, []

def optimize_image_url(url: str) -> str:
    """
    Optimize image URLs to force high resolution.
    Fixes Amazon _SL160_ thumbnails and eBay s-l300 thumbnails.
    """
    if not url: return url
    
    try:
        # 1. Decode Discord Proxy URLs
        # Example: .../external/HASH/https/m.media-amazon.com/...
        if "images-ext-1.discordapp.net" in url or "images-ext-2.discordapp.net" in url:
            # Try to extract the real URL from the path
            # Pattern: /external/[hash]/[protocol]/[domain]/[path]
            # Simple heuristic: find the recurrence of 'http'
            if "/https/" in url:
                url = "https://" + url.split("/https/", 1)[1]
            elif "/http/" in url:
                url = "http://" + url.split("/http/", 1)[1]
                
        # 2. Amazon Image Optimization
        # Pattern: ._SL160_.jpg -> .jpg  (Removes size constraint)
        if "media-amazon.com" in url or "ssl-images-amazon.com" in url:
            # Remove size indicators: ._SL160_  ._AC_UY218_  etc.
            # Regex look for ._XX###_.
            url = re.sub(r'\._[A-Z_]+[0-9]+_\.', '.', url)
            
            # Remove query params like ?format=webp
            if "?" in url:
                url = url.split("?")[0]

        # 3. eBay Image Optimization
        # Pattern: s-l300.jpg -> s-l1600.jpg (Max resolution)
        if "ebayimg.com" in url:
            if re.search(r's-l\d+\.', url):
                url = re.sub(r's-l\d+\.', 's-l1600.', url)
                
    except Exception as e:
        logger.error(f"Image optimization error for {url}: {e}")
        
    return url


def format_telegram_message(msg_data: Dict) -> Tuple[str, Optional[str], Optional[InlineKeyboardMarkup], bool]:
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
                            value = format_price_value(value)
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
    
    # === LINK PARSING (Moved up for image scraping) ===
    all_links = embed.get("links", []) if embed else []
    seen_urls = set()
    title_links = []
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
        link_type = link.get('type', '').lower() # Check for 'title' type
        
        if not url or not url.startswith('http'): continue
        if url in seen_urls: continue
        
        # Helper to categorize
        def add_category(cat_list):
            cat_list.append({'text': link_text, 'url': url, 'field': field})
            seen_urls.add(url)
            
        if link_type == 'title':
            add_category(title_links)
        elif 'atc' in field or 'qt' in field:
            add_category(atc_links)

        elif 'link' in field:
            if any(kw in text_lower for kw in ['sold', 'active', 'google', 'ebay']):
                add_category(ebay_links)
            elif any(kw in text_lower for kw in ['keepa', 'amazon', 'selleramp', 'camel']):
                add_category(fba_links)
            elif any(kw in text_lower for kw in ['buy', 'shop', 'purchase', 'checkout', 'cart']):
                add_category(buy_links)
            else:
                add_category(other_links)
        else:
            if any(kw in text_lower for kw in ['sold', 'active', 'google', 'ebay']):
                add_category(ebay_links)
            elif any(kw in text_lower for kw in ['keepa', 'amazon', 'selleramp', 'camel']):
                add_category(fba_links)
            elif any(kw in text_lower for kw in ['buy', 'shop', 'purchase', 'checkout', 'cart']):
                add_category(buy_links)
            else:
                add_category(other_links)

    # === IMAGE STRATEGY ===
    # Strategy: "Trusted Resolution" vs "Scrape"
    # 1. Get Discord Embed Image and Optimize it.
    # 2. If it's a "Trusted Retailer" (Amazon/eBay) where we KNOW we fixed the resolution -> Use it (Fast).
    # 3. If it's an unknown site (potential low res or logo) -> Scrape Website.
    # 4. Fallback -> Use Discord Image.

    image_url = None
    is_discord_image = False
    
    # 1. Get Candidate from Discord (Raw & Optimized)
    discord_raw = None
    discord_opt = None
    if embed:
        if embed.get("images"):
            discord_raw = embed["images"][0]
            discord_opt = optimize_image_url(discord_raw) # removes width/height params if possible
        elif embed.get("thumbnail"):
            discord_raw = embed["thumbnail"]
            discord_opt = optimize_image_url(discord_raw)
            
    # 2. Check Resolution & Trust
    use_discord_candidate = False
    
    if discord_opt:
        # A. Trusted High-Res (Amazon/eBay) - ALWAYS USE
        trusted_domains = ['amazon', 'ebay', 'media-amazon', 'ebayimg']
        if any(d in discord_opt.lower() for d in trusted_domains):
            use_discord_candidate = True
            logger.info(f"   📸 Trusted High-Res Image (Skipping Scrape): {discord_opt[:60]}...")
            
        # B. Check Resolution from Raw Proxy URL (if not trusted yet)
        if not use_discord_candidate and discord_raw:
             # Look for width=XXX&height=YYY params in the raw discord proxy url
             w_match = re.search(r'width=(\d+)', discord_raw)
             h_match = re.search(r'height=(\d+)', discord_raw)
             
             if w_match and h_match:
                 w = int(w_match.group(1))
                 h = int(h_match.group(1))
                 # Relaxed check: valid if EITHER dimension is large enough (e.g. 160x1600 is fine)
                 if w >= 300 or h >= 300:
                     use_discord_candidate = True
                     logger.info(f"   📸 Discord Image is High-Res ({w}x{h}). Using it.")
                 else:
                     logger.info(f"   ⚠️ Discord Image is Low-Res ({w}x{h}). Will Scrape.")
                     
             elif not "discordapp.net" in discord_raw:
                 # If it's NOT a proxy URL (it's a direct link), we assume it's good?
                 # Or if no width/height params found?
                 # If we can't determine res, safe to scrape?
                 # Let's say if it's original source and not proxy, it might be fine, but to be safe for "Evo Cards" etc, let's scrape if unknown.
                 pass

    if use_discord_candidate:
        image_url = discord_opt
        is_discord_image = True # treat as verified
        
    else:
        # 3. Attempt Scraping (For unknown sites or unverified resolution)
        target_scrape_url = None
        
        # Priority: Title > Buy > ATC > Other
        if title_links: target_scrape_url = title_links[0]['url']
        elif buy_links: target_scrape_url = buy_links[0]['url']
        elif atc_links: target_scrape_url = atc_links[0]['url']
        elif other_links: target_scrape_url = other_links[0]['url']
        
        # Don't scrape generic pages
        if target_scrape_url:
            skip_scrape = any(x in target_scrape_url.lower() for x in ['keepa.com', 'ebay.com/sch', 'login', 'cart', 'checkout'])
            if not skip_scrape:
                logger.info(f"   🔍 Attempting to scrape images from: {target_scrape_url[:60]}...")
                scraped_images = fetch_product_images(target_scrape_url, max_images=1)
                if scraped_images:
                    image_url = scraped_images[0]
                    is_discord_image = False
                    logger.info(f"   📸 ✅ Using scraped website image: {image_url[:60]}...")

        # 4. Fallback to Discord Candidate
        if not image_url and discord_opt:
            image_url = discord_opt
            is_discord_image = True
            logger.info(f"   📸 Fallback to Discord image (Optimized): {image_url[:60]}...")
    
    # === BUTTON CREATION ===
    keyboard = []
    
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
    
    return text, image_url, InlineKeyboardMarkup(keyboard) if keyboard else None, is_discord_image



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


def is_restock_filter_match(msg_data: Dict) -> bool:
    """
    Check if message contains "Just restocked for" phrase.
    These are filtered out based on user request.
    """
    content = (msg_data.get("content") or "").lower()
    if "just restocked for" in content:
        return True
    
    raw = msg_data.get("raw_data", {})
    embed = raw.get("embed") or {}
    
    # Check title and description
    title = (embed.get("title") or "").lower()
    desc = (embed.get("description") or "").lower()
    if "just restocked for" in title or "just restocked for" in desc:
        return True
    
    # Check fields
    if embed.get("fields"):
        for field in embed["fields"]:
            val = (field.get("value") or "").lower()
            name = (field.get("name") or "").lower()
            if "just restocked for" in val or "just restocked for" in name:
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
    if not is_admin(user_id):
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
            text, image_url, keyboard, is_discord_image = format_telegram_message(msg)
            
            # Send (Admin only)
            if image_url:
                try:
                    # If Discord image, download raw bytes to preserve quality
                    photo_data = image_url
                    if is_discord_image:
                        # Run blocking sync operation in thread pool to avoid blocking event loop
                        loop = asyncio.get_event_loop()
                        downloaded = await loop.run_in_executor(sync_executor, download_image_without_compression, image_url)
                        if downloaded:
                            # Wrap bytes in BytesIO to preserve quality (no compression)
                            from io import BytesIO
                            photo_data = BytesIO(downloaded)
                            logger.info(f"   ✅ Downloaded image as bytes ({len(downloaded)} bytes)")
                    
                    await context.bot.send_photo(
                        chat_id=user_id,
                        photo=photo_data,
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
    
    # Track as potential user if not subscribed
    sm.track_potential_user(user_id, username)
    
    welcome_text = f"""
👋 <b>Welcome to KTTYDROPS!</b>

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
    username = update.effective_user.username or update.effective_user.first_name or "User"
    action = query.data
    
    # Handle back button
    if action.startswith("back:"):
        menu_to_go = action.split(":", 1)[1]
        if menu_to_go == "main":
            # Show the same welcome content as /start
            welcome_text = f"""
👋 <b>Welcome to KTTYDROPS!</b>

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
            
            await query.edit_message_text(welcome_text, parse_mode=ParseMode.HTML, reply_markup=create_main_menu())
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
    if not is_admin(update.effective_user.id): 
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

async def add_bot_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Superadmin: Add a new admin"""
    if not is_superadmin(update.effective_user.id):
        await update.message.reply_text("⛔ Only the superadmin can add other admins.")
        return
    
    if not context.args:
        await update.message.reply_text("Usage: /add_admin <user_id>")
        return
    
    target_id = context.args[0]
    if sm.add_admin(target_id):
        await update.message.reply_text(f"✅ User <code>{target_id}</code> is now an admin.", parse_mode=ParseMode.HTML)
    else:
        await update.message.reply_text(f"❌ Could not add user <code>{target_id}</code> as admin. Make sure they have interacted with the bot first.", parse_mode=ParseMode.HTML)

async def remove_bot_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Superadmin: Remove an admin"""
    if not is_superadmin(update.effective_user.id):
        await update.message.reply_text("⛔ Only the superadmin can remove other admins.")
        return
    
    if not context.args:
        await update.message.reply_text("Usage: /remove_admin <user_id>")
        return
    
    target_id = context.args[0]
    if sm.remove_admin(target_id):
        await update.message.reply_text(f"✅ User <code>{target_id}</code> is no longer an admin.", parse_mode=ParseMode.HTML)
    else:
        await update.message.reply_text(f"❌ User <code>{target_id}</code> not found or not an admin.", parse_mode=ParseMode.HTML)

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
            err_msg = f"❌ <b>Broadcast job error</b> after {elapsed:.1f}s: {type(e).__name__}: {e}"
            logger.error(f"❌ Broadcast job error after {elapsed:.1f}s: {type(e).__name__}: {e}")
            logger.error(f"   Full traceback: {traceback.format_exc()}")
            await notify_admins(context, err_msg)
        
        finally:
            job_start_time = None


async def expiry_reminder_job(context: ContextTypes.DEFAULT_TYPE):
    """Notify users with expired subscriptions once every two weeks"""
    expired_uids = sm.get_expired_users_needing_reminder()
    if not expired_uids:
        return

    logger.info(f"⏰ EXPIRY REMINDERS: Sending to {len(expired_uids)} user(s)")
    
    reminder_text = """
⚠️ <b>Subscription Expired</b>

Your access to KTTYDROPS has expired. 

To continue receiving real-time notifications with product images and direct links, please redeem a new subscription code.

🎟️ <b>How to renew:</b>
1. Contact your administrator for a new code.
2. Use the <b>"🎟️ Redeem Code"</b> button in the main menu.
3. Paste your code to reactivate instantly!

<i>You will receive a reminder every two weeks.</i>
"""
    
    sent = 0
    for uid in expired_uids:
        try:
            await context.bot.send_message(
                chat_id=uid,
                text=reminder_text,
                parse_mode=ParseMode.HTML,
                reply_markup=create_main_menu()
            )
            sm.update_reminder_timestamp(uid)
            sent += 1
            await asyncio.sleep(0.1)  # Small delay between users
        except Exception as e:
            err_str = str(e).lower()
            if "chat not found" in err_str or "bot was blocked" in err_str or "user not found" in err_str:
                logger.warning(f"⏩ Skipping unreachable user {uid} for 14 days ({e})")
                sm.update_reminder_timestamp(uid)
            else:
                logger.error(f"Failed to send expiry reminder to {uid}: {e}")
            
    if sent > 0:
        logger.info(f"✅ Sent {sent} expiry reminder(s)")

async def potential_user_reminder_job(context: ContextTypes.DEFAULT_TYPE):
    """Notify potential users who haven't subscribed once every two weeks"""
    potential_uids = sm.get_potential_users_needing_reminder()
    if not potential_uids:
        return

    logger.info(f"⏰ POTENTIAL USER REMINDERS: Sending to {len(potential_uids)} user(s)")
    
    reminder_text = """
👋 <b>Ready to get started?</b>

You recently checked out KTTYDROPS but haven't activated your subscription yet. 

<b>Why subscribe?</b>
• ⚡ <b>Instant Alerts:</b> Be the first to know about product drops.
• 🖼️ <b>Full Data:</b> Images, stock levels, and prices included.
• 🔗 <b>Quick Actions:</b> Direct links to eBay, Amazon, and more.

🎟️ <b>How to get access:</b>
1. Contact your administrator to get a subscription code.
2. Use the <b>"🎟️ Redeem Code"</b> button in the main menu.
3. Start receiving professional alerts immediately!

<i>You will receive a reminder every two weeks.</i>
"""
    
    sent = 0
    for uid in potential_uids:
        try:
            await context.bot.send_message(
                chat_id=uid,
                text=reminder_text,
                parse_mode=ParseMode.HTML,
                reply_markup=create_main_menu()
            )
            sm.update_potential_reminder_timestamp(uid)
            sent += 1
            await asyncio.sleep(0.1)
        except Exception as e:
            err_str = str(e).lower()
            if "chat not found" in err_str or "bot was blocked" in err_str or "user not found" in err_str:
                logger.warning(f"⏩ Skipping unreachable potential user {uid} for 14 days ({e})")
                sm.update_potential_reminder_timestamp(uid)
            else:
                logger.error(f"Failed to send potential reminder to {uid}: {e}")
            
    if sent > 0:
        logger.info(f"✅ Sent {sent} potential user reminder(s)")


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
    
    # Filter out duplicate sources and unwanted restock alerts
    filtered_msgs = [
        msg for msg in new_msgs 
        if not is_duplicate_source(msg) and not is_restock_filter_match(msg)
    ]
    
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
            text, image_url, keyboard, is_discord_image = format_telegram_message(msg)
            logger.debug(f"   ✓ Formatted (text={len(text)} chars, image={'yes' if image_url else 'no'})")
            
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
                if image_url:
                    try:
                        # If Discord image, download raw bytes to preserve quality
                        photo_data = image_url
                        if is_discord_image:
                            # Run blocking sync operation in thread pool to avoid blocking event loop
                            loop = asyncio.get_event_loop()
                            downloaded = await loop.run_in_executor(sync_executor, download_image_without_compression, image_url)
                            if downloaded:
                                # Wrap bytes in BytesIO to preserve quality (no compression)
                                from io import BytesIO
                                photo_data = BytesIO(downloaded)
                        
                        await asyncio.wait_for(
                            context.bot.send_photo(
                                chat_id=uid,
                                photo=photo_data,
                                caption=text[:1024],
                                parse_mode=ParseMode.HTML,
                                reply_markup=keyboard
                            ),
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
                poller.update_cursor(msg_scraped_at, msg)
                logger.debug(f"   📌 Cursor updated to: {msg_scraped_at}")

# 4. COMMAND MENU SETUP

# Default commands for all users
DEFAULT_COMMANDS = [
    BotCommand("start", "Start the bot and see main menu"),
    BotCommand("help", "Show available commands"),
]

# Additional commands for admins
ADMIN_COMMANDS = [
    BotCommand("start", "Start the bot and see main menu"),
    BotCommand("help", "Show available commands"),
    BotCommand("gen", "Generate subscription code (e.g., /gen 30)"),
    BotCommand("test", "Test recent alerts (e.g., /test 5)"),
]

# Additional commands for superadmin
SUPERADMIN_COMMANDS = [
    BotCommand("start", "Start the bot and see main menu"),
    BotCommand("help", "Show available commands"),
    BotCommand("gen", "Generate subscription code (e.g., /gen 30)"),
    BotCommand("test", "Test recent alerts (e.g., /test 5)"),
    BotCommand("add_admin", "Add a user as admin (e.g., /add_admin 123456)"),
    BotCommand("remove_admin", "Remove admin status (e.g., /remove_admin 123456)"),
]

async def setup_bot_commands(application: Application) -> None:
    """Set up command menus for different user roles"""
    try:
        # Set default commands for all users
        await application.bot.set_my_commands(DEFAULT_COMMANDS, scope=BotCommandScopeDefault())
        logger.info("   ✅ Default command menu set")
        
        # Set admin commands for secondary admins
        for user_id, user_data in sm.users.items():
            if user_data.get("is_admin", False):
                try:
                    await application.bot.set_my_commands(
                        ADMIN_COMMANDS, 
                        scope=BotCommandScopeChat(chat_id=int(user_id))
                    )
                    logger.info(f"   ✅ Admin menu set for user {user_id}")
                except Exception as e:
                    logger.debug(f"   Could not set admin menu for {user_id}: {e}")
        
        # Set superadmin commands
        if ADMIN_USER_ID:
            try:
                await application.bot.set_my_commands(
                    SUPERADMIN_COMMANDS, 
                    scope=BotCommandScopeChat(chat_id=int(ADMIN_USER_ID))
                )
                logger.info(f"   ✅ Superadmin menu set for {ADMIN_USER_ID}")
            except Exception as e:
                logger.debug(f"   Could not set superadmin menu: {e}")
                
    except Exception as e:
        logger.error(f"   ❌ Failed to set command menus: {e}")

async def show_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show available commands based on user role"""
    user_id = str(update.effective_user.id)
    
    # Build menu based on role
    if is_superadmin(user_id):
        menu_text = """
🎛️ <b>Superadmin Commands</b>

<b>General:</b>
/start - Main menu & status
/help - Show this command list

<b>Admin Tools:</b>
/gen [days] - Generate subscription code
/test [count] - Test recent alerts

<b>User Management:</b>
/add_admin [user_id] - Add an admin
/remove_admin [user_id] - Remove an admin
"""
    elif is_admin(user_id):
        menu_text = """
🎛️ <b>Admin Commands</b>

<b>General:</b>
/start - Main menu & status
/help - Show this command list

<b>Admin Tools:</b>
/gen [days] - Generate subscription code
/test [count] - Test recent alerts
"""
    else:
        menu_text = """
📋 <b>Available Commands</b>

/start - Main menu & status
/help - Show this command list

Use the menu buttons for more options!
"""
    
    if update.message:
        await update.message.reply_text(menu_text, parse_mode=ParseMode.HTML)
    elif update.callback_query:
        await update.callback_query.message.reply_text(menu_text, parse_mode=ParseMode.HTML)

# 5. RUN BOT FUNCTION
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
        
        app = Application.builder().token(TELEGRAM_TOKEN).post_init(setup_bot_commands).build()
        
        # Command Handlers
        app.add_handler(CommandHandler("start", start))
        app.add_handler(CommandHandler("gen", gen_code))
        app.add_handler(CommandHandler("add_admin", add_bot_admin))
        app.add_handler(CommandHandler("remove_admin", remove_bot_admin))
        app.add_handler(CommandHandler("test", test_alerts))
        app.add_handler(CommandHandler("help", show_help))  # Help command
        app.add_handler(CallbackQueryHandler(button_handler))
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
        
        if app.job_queue:
            logger.info("   Adding broadcast job with overlap protection...")
            app.job_queue.run_repeating(
                broadcast_job, 
                interval=POLL_INTERVAL, 
                first=10
            )

            # Register expiry reminders (Check daily)
            logger.info("   Adding bi-weekly expiry reminder job...")
            app.job_queue.run_repeating(
                expiry_reminder_job,
                interval=86400, # Once a day
                first=30        # Start after 30 seconds
            )

            # Register potential user reminders (Check daily)
            logger.info("   Adding bi-weekly potential user reminder job...")
            app.job_queue.run_repeating(
                potential_user_reminder_job,
                interval=86400, # Once a day
                first=60        # Start after 60 seconds
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
