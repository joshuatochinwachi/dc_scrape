import os
import time
import json
import logging
import threading
import traceback
import requests
import random
import asyncio
import re
import stripe
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from concurrent.futures import ThreadPoolExecutor
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto, BotCommand, BotCommandScopeChat, BotCommandScopeDefault
from telegram.constants import ParseMode
from telegram.error import BadRequest
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes, ConversationHandler
from bs4 import BeautifulSoup
import supabase_utils
from dotenv import load_dotenv
from io import BytesIO
from PIL import Image
import hashlib
import uuid

load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
# Support multiple admin IDs (comma-separated)
ADMIN_USER_IDS = [id.strip() for id in os.getenv("TELEGRAM_ADMIN_ID", "").split(",") if id.strip()]
# For backward compatibility
ADMIN_USER_ID = ADMIN_USER_IDS[0] if ADMIN_USER_IDS else None
SUPABASE_BUCKET = "monitor-data"
USERS_FILE = "bot_users.json"
CODES_FILE = "active_codes.json"
POLL_INTERVAL = 120
MAX_JOB_RUNTIME = 110
POTENTIAL_USERS_FILE = "potential_users.json"
broadcast_lock = asyncio.Lock()
job_start_time = None

sync_executor = ThreadPoolExecutor(max_workers=5, thread_name_prefix="sync_io")

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

# --- DATETIME PARSING UTILITY ---

def parse_iso_datetime(iso_string: str) -> datetime:
    """Parse ISO format datetime string with flexible microseconds."""
    if not iso_string:
        return datetime.utcnow()
    
    try:
        return datetime.fromisoformat(iso_string)
    except ValueError:
        try:
            if "." in iso_string:
                parts = iso_string.split(".")
                if "+" in parts[1]:
                    ms, tz = parts[1].split("+")
                    ms = (ms + "000000")[:6]
                    fixed_str = f"{parts[0]}.{ms}+{tz}"
                elif "-" in parts[1] and parts[1].count("-") > 0:
                    ms, tz = parts[1].rsplit("-", 1)
                    ms = (ms + "000000")[:6]
                    fixed_str = f"{parts[0]}.{ms}-{tz}"
                else:
                    ms = (parts[1] + "000000")[:6]
                    fixed_str = f"{parts[0]}.{ms}"
                return datetime.fromisoformat(fixed_str)
        except:
            pass
    
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


# --- IMPROVED IMAGE HANDLING ---

def get_image_dimensions_from_url(url: str) -> Optional[Tuple[int, int]]:
    """
    Extract dimensions from Discord proxy URL parameters or estimate from URL patterns.
    Returns (width, height) or None if cannot determine.
    """
    if not url:
        return None
    
    try:
        # Discord proxy URLs often have width=X&height=Y
        w_match = re.search(r'[?&]width=(\d+)', url)
        h_match = re.search(r'[?&]height=(\d+)', url)
        
        if w_match and h_match:
            return (int(w_match.group(1)), int(h_match.group(1)))
        
        # Amazon URLs with size indicators like _SL160_
        size_match = re.search(r'\._[A-Z]*(\d+)_\.', url)
        if size_match:
            size = int(size_match.group(1))
            return (size, size)
        
        # eBay URLs with s-lXXX pattern
        ebay_match = re.search(r's-l(\d+)\.', url)
        if ebay_match:
            size = int(ebay_match.group(1))
            return (size, size)
            
    except Exception as e:
        logger.debug(f"Could not extract dimensions from URL: {e}")
    
    return None


def is_high_quality_image(url: str, min_dimension: int = 160) -> bool:
    """
    Determine if an image URL is likely high quality without downloading it.
    """
    if not url:
        return False
    
    # Trusted high-res domains - ALWAYS consider these high quality
    trusted_domains = [
        'media-amazon.com',
        'images-amazon.com', 
        'ssl-images-amazon.com',
        'm.media-amazon.com',
        'ebayimg.com'
    ]
    
    url_lower = url.lower()
    
    # Check if it's from a trusted domain
    is_trusted = any(domain in url_lower for domain in trusted_domains)
    
    # Get dimensions if available
    dimensions = get_image_dimensions_from_url(url)
    
    if dimensions:
        width, height = dimensions
        # Image is high quality if either dimension is large enough
        is_large = width >= min_dimension or height >= min_dimension
        
        if is_trusted:
            # For trusted domains, be lenient - even 300px can be good quality
            return width >= 300 or height >= 300
        else:
            return is_large
    
    # If we can't determine dimensions but it's from a trusted domain, assume it's good
    if is_trusted:
        # But still reject obvious thumbnails
        if any(pattern in url_lower for pattern in ['_sl160_', '_ac_uy218_', 's-l300', 'thumb', 'icon']):
            return False
        return True
    
    # For non-Discord proxy URLs from unknown sources, we can't determine without downloading
    # Conservative: return False to trigger scraping
    if 'discordapp.net' not in url_lower:
        return False
    
    return False


def optimize_image_url(url: str) -> str:
    """
    Optimize image URLs to force maximum resolution.
    CRITICAL: Removes size restrictions from Amazon, eBay, and Discord proxy URLs.
    """
    if not url:
        return url
    
    try:
        original_url = url
        
        # 1. Decode Discord Proxy URLs
        if "images-ext-" in url and "discordapp.net" in url:
            if "/https/" in url:
                url = "https://" + url.split("/https/", 1)[1]
            elif "/http/" in url:
                url = "http://" + url.split("/http/", 1)[1]
        
        # 2. Amazon Image Optimization (CRITICAL)
        if any(domain in url for domain in ['media-amazon.com', 'images-amazon.com', 'ssl-images-amazon.com']):
            # Remove ALL size indicators: ._SL160_, ._AC_UY218_, etc.
            url = re.sub(r'\._[A-Z_]+[0-9]+_\.', '.', url)
            
            # Remove query parameters that limit quality
            if "?" in url:
                base_url = url.split("?")[0]
                # Keep only the base URL, no query params
                url = base_url
        
        # 3. eBay Image Optimization
        if "ebayimg.com" in url:
            # Force maximum resolution: s-l300 -> s-l1600
            if re.search(r's-l\d+\.', url):
                url = re.sub(r's-l\d+\.', 's-l1600.', url)
            
            # Remove quality-limiting query params
            if "?" in url:
                url = url.split("?")[0]
        
        # 4. Remove Discord proxy size limits
        if "discordapp.net" in url or "discord.com" in url:
            # Remove width/height parameters
            url = re.sub(r'[?&](width|height)=\d+', '', url)
            # Clean up dangling ? or &
            url = re.sub(r'\?&', '?', url)
            url = re.sub(r'[?&]$', '', url)
        
        if url != original_url:
            logger.debug(f"   ✨ Optimized URL: {original_url[:80]} -> {url[:80]}")
        
        return url
                
    except Exception as e:
        logger.error(f"Image optimization error: {e}")
        return url


def download_image_high_quality(image_url: str, max_size_mb: int = 10) -> Optional[bytes]:
    """
    Download image preserving maximum quality.
    Returns raw bytes without compression.
    """
    if not image_url or not image_url.startswith('http'):
        return None
    
    # Optimize URL first to get best quality
    image_url = optimize_image_url(image_url)
    
    try:
        # Realistic headers to avoid 403 errors
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'Referer': 'https://www.google.com/',
            'Sec-Fetch-Dest': 'image',
            'Sec-Fetch-Mode': 'no-cors',
            'Sec-Fetch-Site': 'cross-site',
            'Cache-Control': 'no-cache'
        }
        
        # Add domain-specific headers
        if 'amazon' in image_url:
            headers['Referer'] = 'https://www.amazon.com/'
        elif 'ebay' in image_url:
            headers['Referer'] = 'https://www.ebay.com/'
        
        response = requests.get(image_url, headers=headers, timeout=15, stream=True)
        response.raise_for_status()
        
        # Check content type
        content_type = response.headers.get('Content-Type', '')
        if not content_type.startswith('image/'):
            logger.warning(f"   ⚠️ Invalid content type: {content_type}")
            return None
        
        # Download with size limit
        max_size_bytes = max_size_mb * 1024 * 1024
        downloaded = b''
        
        for chunk in response.iter_content(chunk_size=8192):
            if chunk:
                downloaded += chunk
                if len(downloaded) > max_size_bytes:
                    logger.warning(f"   ⚠️ Image too large (>{max_size_mb}MB)")
                    return None
        
        # Verify it's a valid image by trying to open it
        try:
            img = Image.open(BytesIO(downloaded))
            width, height = img.size
            logger.info(f"   ✅ Downloaded image: {width}x{height} ({len(downloaded)//1024}KB)")
            
            # CRITICAL: Return original bytes, DO NOT re-encode
            return downloaded
            
        except Exception as img_err:
            logger.warning(f"   ⚠️ Invalid image data: {img_err}")
            return None
        
    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 403:
            logger.warning(f"   🚫 403 Forbidden: {image_url[:80]}")
        elif e.response.status_code == 404:
            logger.warning(f"   ❌ 404 Not Found: {image_url[:80]}")
        else:
            logger.warning(f"   ⚠️ HTTP {e.response.status_code}: {image_url[:80]}")
        return None
        
    except requests.exceptions.Timeout:
        logger.warning(f"   ⏱️ Timeout downloading: {image_url[:80]}")
        return None
        
    except Exception as e:
        logger.warning(f"   ⚠️ Download error: {str(e)[:80]}")
        return None


def fetch_product_images(url: str, max_images: int = 3) -> List[str]:
    """
    Scrape high-res product images from a URL with improved anti-blocking.
    """
    # Skip known non-product pages
    skip_scrape = any(x in url.lower() for x in [
        'keepa.com', 'ebay.com/sch', 'camelcamelcamel',
        'login', 'cart', 'checkout', 'account', 'signin'
    ])
    
    if skip_scrape:
        logger.debug(f"   ⏭️ Skipping scrape of non-product page")
        return []
    
    # Enhanced User-Agent rotation
    user_agents = [
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15',
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0',
        'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    ]
    
    headers = {
        'User-Agent': random.choice(user_agents),
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9',
        'Accept-Encoding': 'gzip, deflate, br',
        'Referer': 'https://www.google.com/',
        'Upgrade-Insecure-Requests': '1',
        'Sec-Fetch-Dest': 'document',
        'Sec-Fetch-Mode': 'navigate',
        'Sec-Fetch-Site': 'none',
        'Sec-Fetch-User': '?1',
        'Cache-Control': 'max-age=0'
    }
    
    images = []
    
    try:
        if not url or not url.startswith('http'):
            return []
        
        response = requests.get(url, headers=headers, timeout=12)
        
        if response.status_code == 403:
            logger.warning(f"   🚫 403 Forbidden - site blocking scraper")
            return []
        
        if response.status_code != 200:
            logger.warning(f"   ⚠️ Scrape failed: HTTP {response.status_code}")
            return []
        
        soup = BeautifulSoup(response.text, 'html.parser')
        skip_keywords = ['logo', 'icon', 'banner', 'button', 'sprite', 'loading', 'placeholder', 'blank', 'ajax']
        
        # Priority 0: Meta Tags
        for meta in soup.find_all('meta'):
            prop = meta.get('property', '')
            name = meta.get('name', '')
            if prop in ['og:image', 'twitter:image'] or name in ['og:image', 'twitter:image']:
                meta_url = meta.get('content')
                if meta_url:
                    if meta_url.startswith('//'):
                        meta_url = 'https:' + meta_url
                    elif not meta_url.startswith('http'):
                        from urllib.parse import urljoin
                        meta_url = urljoin(url, meta_url)
                    
                    if meta_url.startswith('http') and not any(k in meta_url.lower() for k in skip_keywords):
                        images.append({
                            'url': meta_url,
                            'alt': 'Meta Tag Image',
                            'priority': 1000
                        })
        
        # Priority 1: JSON-LD Structured Data
        try:
            scripts = soup.find_all('script', type='application/ld+json')
            for script in scripts:
                if script.string:
                    try:
                        data = json.loads(script.string)
                        items = []
                        if isinstance(data, list):
                            items = data
                        elif isinstance(data, dict):
                            if '@graph' in data:
                                items.extend(data['@graph'])
                            items.append(data)
                        
                        for item in items:
                            if item.get('@type') in ['Product', 'ItemPage', 'IndividualProduct']:
                                img_data = item.get('image')
                                found_imgs = []
                                
                                if isinstance(img_data, str):
                                    found_imgs.append(img_data)
                                elif isinstance(img_data, list):
                                    for i in img_data:
                                        if isinstance(i, str):
                                            found_imgs.append(i)
                                        elif isinstance(i, dict) and 'url' in i:
                                            found_imgs.append(i['url'])
                                elif isinstance(img_data, dict) and 'url' in img_data:
                                    found_imgs.append(img_data['url'])
                                
                                for img_url in found_imgs:
                                    if img_url:
                                        if img_url.startswith('//'):
                                            img_url = 'https:' + img_url
                                        elif not img_url.startswith('http'):
                                            from urllib.parse import urljoin
                                            img_url = urljoin(url, img_url)
                                        
                                        if img_url.startswith('http') and not any(k in img_url.lower() for k in skip_keywords):
                                            images.append({
                                                'url': img_url,
                                                'alt': 'JSON-LD Image',
                                                'priority': 950
                                            })
                    except:
                        continue
        except Exception as json_err:
            logger.debug(f"   JSON-LD parse error: {json_err}")
        
        # Priority 2: Img Tags
        for img in soup.find_all('img'):
            img_url = img.get('src') or img.get('data-src') or img.get('data-lazy-src')
            if not img_url:
                continue
            
            if img_url.startswith('//'):
                img_url = 'https:' + img_url
            elif not img_url.startswith('http'):
                from urllib.parse import urljoin
                img_url = urljoin(url, img_url)
            
            if not img_url.startswith('http') or img_url.startswith('data:'):
                continue
            
            # Size check
            if 'width' in img.attrs and 'height' in img.attrs:
                try:
                    w = int(str(img['width']).replace('px', ''))
                    h = int(str(img['height']).replace('px', ''))
                    if w < 100 or h < 100:
                        continue
                except:
                    pass
            
            img_url_lower = img_url.lower()
            if any(skip in img_url_lower for skip in skip_keywords):
                continue
            
            score = 0
            alt_text = img.get('alt', '').lower()
            if 'product' in img_url_lower or 'product' in alt_text:
                score += 50
            if 'main' in img_url_lower:
                score += 20
            if 'gallery' in img_url_lower:
                score += 10
            if 'cdn.shopify.com' in img_url_lower:
                score += 30
            
            if score > 0:
                images.append({'url': img_url, 'priority': score})
        
        # Sort and deduplicate
        images.sort(key=lambda x: x['priority'], reverse=True)
        seen = set()
        final_images = []
        
        for img in images:
            if img['url'] not in seen and img['url']:
                seen.add(img['url'])
                final_images.append(img['url'])
        
        if final_images:
            logger.info(f"   📸 Scraped {len(final_images)} image(s)")
        
        return final_images[:max_images]
    
    except requests.exceptions.Timeout:
        logger.warning(f"   ⏱️ Scrape timeout")
        return []
    except requests.exceptions.RequestException as e:
        logger.warning(f"   ⚠️ Scrape error: {str(e)[:80]}")
        return []
    except Exception as e:
        logger.error(f"   ❌ Scrape error: {str(e)[:80]}")
        return []


def add_emoji_to_link_text(text: str) -> str:
    """Add emoji prefix to link text for better visual appeal"""
    emojis = {
        'sold': '💰', 'active': '⚡', 'google': '🔍', 'ebay': '🛒',
        'keepa': '📈', 'amazon': '🔎', 'selleramp': '💎', 'camel': '🐫',
        'buy': '🛒', 'shop': '🪀', 'cart': '🛒', 'checkout': '✅',
    }
    
    text_lower = text.lower()
    for keyword, emoji in emojis.items():
        if keyword in text_lower:
            return f"{emoji} {text}"
    
    return f"🔗 {text}"


def parse_tag_line(tag: str) -> Dict[str, Optional[str]]:
    """Parse Discord tag line above embeds."""
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
        
        # Persistence & Sync
        self.last_sync_time = 0
        self.sync_interval = 60 # Sync every 60s
        
        # Stripe Config
        self.stripe_price_id_monthly = os.getenv("STRIPE_PRICE_ID_MONTHLY")
        self.stripe_price_id_yearly = os.getenv("STRIPE_PRICE_ID_YEARLY")
        self.domain = os.getenv("DOMAIN", "http://localhost:5000")
        
        os.makedirs("data", exist_ok=True)
        self._load_state()

    def reload(self, force=False):
        """Reload user state from Supabase if stale or forced"""
        now = time.time()
        if not force and (now - self.last_sync_time) < self.sync_interval:
            return
            
        logger.info("🔄 Reloading user state from Supabase...")
        self._load_state()
        self.last_sync_time = now

    def _load_state(self):
        """Load state from Supabase with local fallback"""
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

    def get_user_categories(self, user_id: str) -> List[str]:
        """Get enabled categories for a user (default to all if not set)"""
        uid = str(user_id)
        if uid not in self.users: return []
        
        # If no preference set, default to ALL available categories
        user_cats = self.users[uid].get("subscribed_categories")
        if user_cats is None:
            return cm.get_categories()
        return user_cats

    def get_disabled_subcategories(self, user_id: str) -> List[str]:
        """Get list of disabled subcategory keys (Category:Subcategory)"""
        uid = str(user_id)
        if uid not in self.users: return []
        return self.users[uid].get("disabled_subcategories", [])

    def is_subscribed(self, user_id: str, category: str, subcategory: str) -> bool:
        """Check if user is subscribed to both category and subcategory"""
        uid = str(user_id)
        if uid not in self.users: return False
        
        # 1. Check Category
        enabled_cats = self.get_user_categories(uid)
        if category not in enabled_cats:
            return False
            
        # 2. Check Subcategory
        disabled_subs = self.get_disabled_subcategories(uid)
        sub_key = f"{category}:{subcategory}"
        if sub_key in disabled_subs:
            return False
            
        return True

    def toggle_category(self, user_id: str, category: str) -> bool:
        """Toggle a category for a user"""
        with self.lock:
            uid = str(user_id)
            if uid not in self.users: return False
            
            if "subscribed_categories" not in self.users[uid]:
                self.users[uid]["subscribed_categories"] = cm.get_categories()
                
            current_cats = self.users[uid]["subscribed_categories"]
            if category in current_cats:
                current_cats.remove(category)
                new_state = False
            else:
                current_cats.append(category)
                new_state = True
            
            self.users[uid]["subscribed_categories"] = current_cats
            self._sync_state()
            return new_state

    def toggle_subcategory(self, user_id: str, category: str, subcategory: str) -> bool:
        """Toggle a subcategory (stores Category:Subcategory in disabled_subcategories)"""
        with self.lock:
            uid = str(user_id)
            if uid not in self.users: return False
            
            if "disabled_subcategories" not in self.users[uid]:
                self.users[uid]["disabled_subcategories"] = []
                
            disabled_subs = self.users[uid]["disabled_subcategories"]
            sub_key = f"{category}:{subcategory}"
            
            if sub_key in disabled_subs:
                disabled_subs.remove(sub_key)
                new_state = True # Now enabled
            else:
                disabled_subs.append(sub_key)
                new_state = False # Now disabled
                
            self.users[uid]["disabled_subcategories"] = disabled_subs
            self._sync_state()
            return new_state

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
            # Retrieve existing data or initialize new
            user_data = self.users.get(str(user_id), {})
            
            # Update fields
            user_data["expiry"] = new_expiry.isoformat()
            user_data["username"] = username or user_data.get("username", "Unknown")
            if "alerts_paused" not in user_data:
                user_data["alerts_paused"] = False
            if "joined_at" not in user_data:
                user_data["joined_at"] = datetime.utcnow().isoformat()
            
            self.users[str(user_id)] = user_data
            if str(user_id) in self.potential_users:
                self.potential_users.pop(str(user_id))
            self._sync_state()
            return True

    def process_stripe_event(self, event):
        """Handle Stripe Webhook events"""
        event_type = event['type']
        data_object = event['data']['object']
        
        # Extract user_id from metadata or client_reference_id
        user_id = data_object.get('client_reference_id') or data_object.get('metadata', {}).get('user_id')
        
        if event_type == 'checkout.session.completed':
            customer_id = data_object.get('customer')
            subscription_id = data_object.get('subscription')
            
            # Identify the plan duration from the subscription
            days_to_add = 30 # Default Monthly
            try:
                sub = stripe.Subscription.retrieve(subscription_id)
                plan_interval = sub['items']['data'][0]['plan']['interval']
                if plan_interval == 'year':
                    days_to_add = 365 # Yearly
            except Exception as e:
                logger.warning(f"Could not determine plan interval: {e}")

            if user_id:
                with self.lock:
                    uid = str(user_id)
                    if uid not in self.users:
                        # Create user entry if it doesn't exist
                        self.users[uid] = {
                            "expiry": (datetime.utcnow() + timedelta(days=days_to_add)).isoformat(),
                            "username": data_object.get('customer_details', {}).get('name', 'Stripe User'),
                            "joined_at": datetime.utcnow().isoformat(),
                            "alerts_paused": False
                        }
                    
                    self.users[uid]["stripe_customer_id"] = customer_id
                    self.users[uid]["stripe_subscription_id"] = subscription_id
                    
                    # Set expiry based on plan (Extend if active, otherwise start fresh)
                    current_expiry_str = self.users[uid].get("expiry")
                    now = datetime.utcnow()
                    base_date = now
                    
                    if current_expiry_str:
                        try:
                            current_expiry = parse_iso_datetime(current_expiry_str)
                            if current_expiry > now:
                                base_date = current_expiry
                                logger.info(f"   ➕ Extending existing subscription for {uid}")
                        except: pass

                    new_expiry = base_date + timedelta(days=days_to_add)
                    self.users[uid]["expiry"] = new_expiry.isoformat()
                    
                    if uid in self.potential_users:
                        self.potential_users.pop(uid)
                    
                    self._sync_state()
                    logger.info(f"💰 Stripe: User {uid} subscribed via Checkout.")
                    
                    # Notify user immediately
                    success_msg = f"""
🎉 <b>Welcome to Hollowscan Premium!</b>

Your payment was successful and your subscription is now <b>Active</b> for the next {days_to_add} days.

🚀 You will now receive instant alerts. 
<b>Click /start to refresh your menu and see your status.</b>
"""
                    try:
                        api_url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
                        requests.post(api_url, json={"chat_id": uid, "text": success_msg, "parse_mode": "HTML"}, timeout=10)
                    except Exception as e:
                        logger.warning(f"Failed to send confirmation to {uid}: {e}")
        
        elif event_type == 'invoice.paid':
            # Recurring payment success
            customer_id = data_object.get('customer')
            subscription_id = data_object.get('subscription')
            
            days_to_add = 30
            try:
                sub = stripe.Subscription.retrieve(subscription_id)
                plan_interval = sub['items']['data'][0]['plan']['interval']
                if plan_interval == 'year':
                    days_to_add = 365
            except: pass

            if customer_id:
                with self.lock:
                    # Find user by customer_id
                    for uid, udata in self.users.items():
                        if udata.get('stripe_customer_id') == customer_id:
                            new_expiry = datetime.utcnow() + timedelta(days=days_to_add)
                            self.users[uid]["expiry"] = new_expiry.isoformat()
                            self._sync_state()
                            logger.info(f"✅ Stripe: User {uid} subscription renewed ({days_to_add} days).")
                            
                            # Notify user of renewal
                            renew_msg = f"✅ <b>Subscription Renewed!</b>\n\nYour premium access has been extended. Thank you for staying with us!"
                            try:
                                api_url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
                                requests.post(api_url, json={"chat_id": uid, "text": renew_msg, "parse_mode": "HTML"}, timeout=10)
                            except: pass
                            break
                            
        elif event_type == 'customer.subscription.deleted':
            # Subscription cancelled or expired
            customer_id = data_object.get('customer')
            if customer_id:
                with self.lock:
                    for uid, udata in self.users.items():
                        if udata.get('stripe_customer_id') == customer_id:
                            # Immediate expiry or let it run out? 
                            # Stripe usually sends this when it FINALLY ends.
                            self.users[uid]["expiry"] = datetime.utcnow().isoformat()
                            self._sync_state()
                            logger.info(f"❌ Stripe: User {uid} subscription terminated.")
                            break

    def get_active_users(self) -> List[str]:
        self.reload()
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
    
    def get_all_users(self) -> List[str]:
        """Get all known users (subscribed + potential)"""
        all_ids = set()
        with self.lock:
            all_ids.update(self.users.keys())
            all_ids.update(self.potential_users.keys())
        return list(all_ids)

    def get_expired_users(self) -> List[str]:
        """Get users with expired subscriptions"""
        expired = []
        now = datetime.utcnow()
        with self.lock:
            for uid, data in self.users.items():
                try:
                    expiry = parse_iso_datetime(data["expiry"])
                    if expiry < now:
                        expired.append(uid)
                except: 
                    pass
        return expired

    def get_potential_users_list(self) -> List[str]:
        """Get list of potential users"""
        with self.lock:
            return list(self.potential_users.keys())
    
    def get_expiry(self, user_id: str):
        return self.users.get(str(user_id), {}).get("expiry")
    
    def is_active(self, user_id: str) -> bool:
        self.reload()
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
    """
    OPTIMIZED VERSION - Uses database table instead of storage
    Reduces write operations from 720/day to ~12/day (95% reduction!)
    """
    
    def __init__(self):
        self.last_scraped_at = None
        self.sent_ids = set()
        self.recent_signatures = []  # Last 20 sent content signatures
        self.supabase_url, self.supabase_key = supabase_utils.get_supabase_config()
        self.time_based_signatures = {}  # {sig_hash: timestamp_iso}
        
        # State tracking to avoid unnecessary saves
        self._last_saved_state = None
        self._save_counter = 0  # Track number of saves
        
        self._init_cursor()

    def _init_cursor(self):
        """Load cursor from database bot_cursor table"""
        try:
            headers = {
                "apikey": self.supabase_key, 
                "Authorization": f"Bearer {self.supabase_key}",
                "Content-Type": "application/json"
            }
            
            # Fetch from bot_cursor table (should only have 1 row with id=1)
            res = requests.get(
                f"{self.supabase_url}/rest/v1/bot_cursor?id=eq.1",
                headers=headers,
                timeout=10
            )
            
            if res.status_code == 200 and res.json():
                data = res.json()[0]
                self.last_scraped_at = data.get("last_scraped_at")
                
                # Load sent_ids (convert from JSONB array to set)
                sent_ids_list = data.get("sent_ids", [])
                self.sent_ids = set(str(x) for x in sent_ids_list)
                
                # Load signatures
                self.recent_signatures = data.get("recent_signatures", [])
                self.time_based_signatures = data.get("time_based_signatures", {})
                
                logger.info(f"✅ Cursor loaded from DB: {len(self.sent_ids)} sent IDs, "
                           f"last_scraped: {self.last_scraped_at}")
            else:
                logger.warning(f"⚠️ No cursor found in DB, initializing new cursor")
                self._initialize_new_cursor()
                
        except Exception as e:
            logger.error(f"❌ Error loading cursor from DB: {e}")
            self._initialize_new_cursor()
    
    def _initialize_new_cursor(self):
        """Initialize cursor when no data exists"""
        self.last_scraped_at = (datetime.utcnow() - timedelta(hours=24)).isoformat()
        self.sent_ids = set()
        self.recent_signatures = []
        self.time_based_signatures = {}
        
        # Save initial state to database
        self._save_cursor(force=True)

    def _save_cursor(self, force: bool = False):
        """
        Save cursor to database (single UPDATE operation)
        
        OPTIMIZATION: Only saves if state actually changed OR force=True
        This reduces unnecessary writes significantly
        """
        try:
            # Create current state snapshot
            current_state = {
                "last_scraped_at": self.last_scraped_at,
                "sent_count": len(self.sent_ids),
                "sig_count": len(self.recent_signatures)
            }
            
            # Skip save if nothing changed (unless forced)
            if not force and current_state == self._last_saved_state:
                logger.debug("⏭️ Skipping cursor save - no changes")
                return
            
            headers = {
                "apikey": self.supabase_key, 
                "Authorization": f"Bearer {self.supabase_key}",
                "Content-Type": "application/json",
                "Prefer": "return=minimal"  # Don't return the updated row
            }
            
            # Prepare payload - keep arrays limited to prevent bloat
            payload = {
                "last_scraped_at": self.last_scraped_at,
                "sent_ids": list(self.sent_ids)[-5000:],  # Keep last 5000 IDs
                "recent_signatures": self.recent_signatures[-20:],  # Keep last 20
                "time_based_signatures": self.time_based_signatures,
                # updated_at is auto-updated by trigger
            }
            
            # Single UPDATE operation (NOT INSERT - much more efficient!)
            res = requests.patch(
                f"{self.supabase_url}/rest/v1/bot_cursor?id=eq.1",
                headers=headers,
                json=payload,
                timeout=10
            )
            
            if res.status_code in [200, 204]:
                self._last_saved_state = current_state
                self._save_counter += 1
                logger.info(f"💾 Cursor saved to DB (save #{self._save_counter})")
            else:
                logger.error(f"❌ Failed to save cursor: {res.status_code} - {res.text[:200]}")
                
        except Exception as e:
            logger.error(f"❌ Error saving cursor to DB: {e}")
            # Don't crash - cursor will be saved next time

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
                if content and "|" in content:
                    parts = [p.strip() for p in content.split("|")]
                    if len(parts) >= 3:
                        if not title and len(parts) > 1:
                            title = parts[1]
                        if not retailer and len(parts) > 2:
                            retailer = parts[2]
                        if not price:
                            price_match = re.search(r'[£$€]\s*[\d,]+\.?\d*', content)
                            if price_match:
                                price = price_match.group(0)
            
            # Final fallback for specific keywords
            if not retailer and "Argos" in content:
                retailer = "Argos Instore"
            
            # Create raw signature and hash it
            raw_sig = f"{retailer}|{title}|{price}".lower().strip()
            
            # If everything is still empty, use content hash or ID
            if raw_sig == "||":
                return hashlib.md5(content.encode()).hexdigest() if content else str(msg.get("id"))
                
            return hashlib.md5(raw_sig.encode()).hexdigest()
            
        except Exception as e:
            logger.error(f"Error generating signature: {e}")
            return str(msg.get("id"))

    def poll_new_messages(self):
        """
        Poll for new messages from discord_messages table
        
        OPTIMIZATION: Only saves cursor if new messages were actually found
        """
        try:
            if not self.last_scraped_at: 
                self.last_scraped_at = (datetime.utcnow() - timedelta(minutes=45)).isoformat()
            
            headers = {
                "apikey": self.supabase_key, 
                "Authorization": f"Bearer {self.supabase_key}"
            }
            
            url = f"{self.supabase_url}/rest/v1/discord_messages"
            params = {
                "scraped_at": f"gt.{self.last_scraped_at}", 
                "order": "scraped_at.asc",
                "limit": 100  # Fetch in batches
            }
            
            res = requests.get(url, headers=headers, params=params, timeout=45)
            
            if res.status_code != 200:
                logger.error(f"Poll failed: {res.status_code}")
                return []
            
            messages = res.json()
            
            if not messages:
                # No new messages - don't save cursor unnecessarily
                return []
            
            now_iso = datetime.utcnow().isoformat()
            now_dt = datetime.utcnow()
            
            # Prune time-based signatures older than 10 minutes
            pruned_sigs = {}
            for sig_hash, ts in self.time_based_signatures.items():
                try:
                    sig_time = parse_iso_datetime(ts)
                    if (now_dt - sig_time) < timedelta(minutes=10):
                        pruned_sigs[sig_hash] = ts
                except:
                    pass
            self.time_based_signatures = pruned_sigs

            new_messages = []
            latest_scraped_at = self.last_scraped_at
            
            for msg in messages:
                msg_id = msg.get("id")
                msg_scraped_at = msg.get("scraped_at")
                
                # Track latest timestamp
                if msg_scraped_at and msg_scraped_at > latest_scraped_at:
                    latest_scraped_at = msg_scraped_at
                
                # LAYER 1: Discord ID Check (All-time tracking)
                if not msg_id or str(msg_id) in self.sent_ids:
                    continue
                
                sig = self._get_content_signature(msg)
                
                # LAYER 2: Content Signature (Sliding Window - last 20)
                if sig in self.recent_signatures:
                    logger.info(f"⏭️ LAYER 2 BLOCK: Duplicate content window: {msg_id} (Sig: {sig[:8]})")
                    self.sent_ids.add(str(msg_id))
                    continue
                
                # LAYER 3: Time-Based Deduplication (10-minute window)
                if sig in self.time_based_signatures:
                    logger.info(f"⏭️ LAYER 3 BLOCK: Duplicate content within 10m: {msg_id} (Sig: {sig[:8]})")
                    self.sent_ids.add(str(msg_id))
                    continue

                # MESSAGE ACCEPTED - Add to tracking IMMEDIATELY
                new_messages.append(msg)
                self.sent_ids.add(str(msg_id))
                self.recent_signatures.append(sig)
                self.recent_signatures = self.recent_signatures[-20:]  # Keep last 20
                self.time_based_signatures[sig] = now_iso
            
            # Update cursor timestamp to latest message
            if latest_scraped_at > self.last_scraped_at:
                self.last_scraped_at = latest_scraped_at
            
            # OPTIMIZATION: Only save cursor if we actually found new messages
            if new_messages:
                self._save_cursor()
                logger.info(f"📨 Found {len(new_messages)} new messages, cursor saved")
            else:
                logger.debug(f"No new unique messages (checked {len(messages)} total)")
                
            return new_messages
            
        except Exception as e:
            logger.error(f"❌ Poll error: {e}")
            return []
    
    def update_cursor(self, scraped_at: str, msg_data: Optional[Dict] = None):
        """
        Manually update cursor to given scraped_at timestamp
        Used for error recovery or manual cursor adjustment
        """
        old_cursor = self.last_scraped_at
        self.last_scraped_at = scraped_at
        self._save_cursor(force=True)
        logger.info(f"🔄 Cursor manually updated: {old_cursor} -> {scraped_at}")



# --- CHANNEL MANAGER ---

class ChannelManager:
    def __init__(self):
        self.channels: List[Dict] = []
        self.lock = threading.Lock()
        self.local_path = "data/channels.json"
        self.remote_path = "discord_josh/channels.json"
        self.last_sync = 0
        os.makedirs("data", exist_ok=True)
        self.reload(force=True)

        # Pre-populate if empty (Migration)
        if not self.channels:
            initial_channels = [
                {"id": "1367813504786108526", "name": "Collectors Amazon", "url": "https://discord.com/channels/653646362453213205/1367813504786108526", "category": "UK Stores", "enabled": True},
                {"id": "855164313006505994", "name": "Argos Instore", "url": "https://discord.com/channels/653646362453213205/855164313006505994", "category": "UK Stores", "enabled": True},
                {"id": "864504557903937587", "name": "Restocks Online", "url": "https://discord.com/channels/653646362453213205/864504557903937587", "category": "UK Stores", "enabled": True}
            ]
            self.channels = initial_channels
            self._sync_state()

    def reload(self, force=False):
        """Reload channels from Supabase if more than 5 mins passed or forced"""
        now = time.time()
        if not force and (now - self.last_sync < 300):
            return
            
        try:
            data = supabase_utils.download_file(self.local_path, self.remote_path, SUPABASE_BUCKET)
            if data:
                self.channels = json.loads(data)
                self.last_sync = now
                logger.info(f"✅ Reloaded {len(self.channels)} channels from Supabase")
        except: pass
        
        if not self.channels and os.path.exists(self.local_path):
            try:
                with open(self.local_path, 'r') as f: 
                    self.channels = json.load(f)
                    self.last_sync = now
            except: pass

    def _sync_state(self):
        try:
            with open(self.local_path, 'w') as f: json.dump(self.channels, f, indent=2)
            supabase_utils.upload_file(self.local_path, SUPABASE_BUCKET, self.remote_path, debug=False)
            
            # Sync to SQL Categories table for the Mobile App
            supabase_utils.sync_categories_to_sql(self.channels)
            
        except Exception as e:
            logger.error(f"Channel sync error: {e}")

    def add_channel(self, url: str, category: str, name: str) -> bool:
        """Add a new channel"""
        with self.lock:
            # Extract ID from URL
            # Format: .../channels/GUILD_ID/CHANNEL_ID
            # Or just CHANNEL_ID if direct
            chan_id = url.strip('/').split('/')[-1]
            if not chan_id.isdigit(): return False
            
            # Check for duplicate
            if any(c['id'] == chan_id for c in self.channels):
                return False
                
            self.channels.append({
                "id": chan_id,
                "name": name,
                "url": url,
                "category": category,
                "enabled": True
            })
            self._sync_state()
            return True

    def remove_channel(self, chan_id: str) -> bool:
        """Remove a channel by ID"""
        with self.lock:
            initial_len = len(self.channels)
            self.channels = [c for c in self.channels if c['id'] != str(chan_id)]
            if len(self.channels) < initial_len:
                self._sync_state()
                return True
            return False

    def get_enabled_channels(self) -> List[Dict]:
        return [c for c in self.channels if c.get('enabled', True)]

    def get_categories(self) -> List[str]:
        """Get list of unique categories"""
        cats = set(c.get('category', 'Uncategorized') for c in self.channels)
        return sorted(list(cats))

    def get_subcategories(self, category: str) -> List[str]:
        """Get list of store names for a category"""
        subs = set(c.get('name', 'Unknown') for c in self.channels if c.get('category') == category)
        return sorted(list(subs))

cm = ChannelManager()
sm = SubscriptionManager()
poller = MessagePoller()

# --- ADMIN PERMISSION HELPERS ---

def is_superadmin(user_id: str) -> bool:
    """Check if user is one of the main admins from .env"""
    uid_str = str(user_id)
    return uid_str in ADMIN_USER_IDS

def is_admin(user_id: str) -> bool:
    """Check if user is either a superadmin or secondary admin"""
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
    "@Product Flips",
    "Experimental software. AI can be inaccurate, DYOR!",
    "www.crepchiefnotify.com",
    "CrepChiefNotify"
]

# Regex patterns to remove (for dynamic content like timestamps)
REGEX_PATTERNS_TO_REMOVE = [
    r'Monitors\s+v[\d.]+\s*\|\s*CCN\s+x\s+Zephyr\s+Monitors\s*\[\d{2}:\d{2}:\d{2}\]',
    r'\s*\|\s*CCN\s+x\s+Zephyr\s+Monitors\s+\[[^\]]+\].*',
    r'Today\s+at\s+\d{1,2}:\d{2}\s*(?:AM|PM)',
    r'Experimental\s+software\.\s+AI\s+can\s+be\s+inaccurate,\s+DYOR!',
]

def clean_text(text: str) -> str:
    """Remove unwanted phrases from text and clean up markdown links"""
    if not text:
        return text
    
    # NEW: Strip markdown links [Text](URL) -> Text
    # We do this FIRST so PHRASES_TO_REMOVE can target the cleaned text
    text = re.sub(r'\[([^\]]+)\]\((https?://[^\)]+)\)', r'\1', text)
    
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
        # Added support for commas as thousands separators: (?:,\d{3})*
        return re.sub(r'(?<![£$€\d.])\d+(?:,\d{3})*(?:\.\d{1,2})?(?![%\d])', replacer, text)
    
    return add_currency_to_prices(value)


# --- CHANNEL SPECIFIC FORMATTERS ---

CHANNEL_COLLECTORS = "1367813504786108526"
CHANNEL_ARGOS = "855164313006505994"
CHANNEL_RESTOCKS = "864504557903937587"

def _format_collectors_amazon(msg_data: Dict, embed: Dict) -> Tuple[List[str], List[List[InlineKeyboardButton]]]:
    """Formatter for Collectors Edge / Amazon V3 (Channel 136...)"""
    lines = []
    keyboard = []
    
    # 1. Header & Title (Retailer or Author) - DISABLED PER USER REQUEST
    # author_name = msg_data.get("raw_data", {}).get("author", {}).get("name")
    # if not author_name and embed.get("author"):
    #     author_name = embed["author"].get("name")
        
    # if author_name and "unknown" not in author_name.lower():
    #     lines.append(f"🏪 <b>{clean_text(author_name)}</b>")
    #     lines.append("")

    title = clean_text(embed.get("title"))
    if title and title != "None":
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
    
    # lines.append("🏪 <b>Argos Instore</b>")
    # lines.append("")
    
    title = clean_text(embed.get("title"))
    if title and title != "None":
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
        
    # lines.append(f"⚡ <b>{site.upper()}</b>")
    # lines.append("")
    
    title = clean_text(embed.get("title"))
    if title and title != "None":
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

# Utility functions consolidated at the top of the file


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
            # RETAILER/SOURCE - DISABLED PER USER REQUEST
            # retailer = None
            # if embed.get("author"):
            #     retailer = clean_text(embed["author"].get("name"))
            # elif tag_info.get("brand"):
            #     retailer = clean_text(tag_info["brand"])
            
            # if retailer and "unknown" not in retailer.lower():
            #     lines.append(f"🏪 <b>{retailer}</b>")
            #     lines.append("")
            
            # TITLE
            title = clean_text(embed.get("title") or tag_info.get("product_code"))
            if title and title != "None":
                if tag_info.get("region"): title = f"[{tag_info['region']}] {title}"
                lines.append(f"📦 <b>{title}</b>")
                lines.append("━━━━━━━━━━━━━━━")
                lines.append("")
            
            # DESC
            if embed.get("description"):
                desc_text = clean_text(embed["description"])
                # NEW: Title Prefix Deduplication
                # If desc starts with the exact title, strip it
                if title and desc_text.lower().startswith(title.lower()):
                    desc_text = desc_text[len(title):].strip()
                    if desc_text.startswith(":") or desc_text.startswith("-") or desc_text.startswith("|"):
                        desc_text = desc_text[1:].strip()
                
                if desc_text:
                    desc_display = desc_text[:400]
                    if len(desc_text) > 400: desc_display += "..."
                    lines.append(desc_display)
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
            cleaned_footer = clean_text(footer)
            if cleaned_footer:
                lines.append(f"⏰ {cleaned_footer}")
        else:
            scraped_time = parse_iso_datetime(msg_data.get("scraped_at", datetime.utcnow().isoformat()))
            lines.append(f"⏰ {scraped_time.strftime('%H:%M UTC')}")
            
    else:
        # HUMAN MESSAGE FALLBACK (Refined)
        if plain_content:
            product_code = clean_text(tag_info.get("product_code") or "")
            content_display = clean_text(plain_content)
            
            # Don't show generic title if it's identical to the content
            if product_code and product_code.lower() != content_display.lower():
                lines.append(f"📦 <b>{product_code}</b>")
            
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
        link_text = clean_text(link.get('text', 'Link'))
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
    image_bytes = None
    
    # 1. Get Best Candidate from Discord
    discord_candidate = None
    if embed:
        if embed.get("images"):
            discord_candidate = optimize_image_url(embed["images"][0])
        elif embed.get("thumbnail"):
            discord_candidate = optimize_image_url(embed["thumbnail"])
            
    # 2. Empirical Check: Download and Verify Pixels
    if discord_candidate:
        logger.info(f"   🔍 Verifying Discord candidate image: {discord_candidate[:60]}...")
        # Note: download_image_high_quality uses Pillow internally to verify
        downloaded = download_image_high_quality(discord_candidate)
        
        if downloaded:
            try:
                img = Image.open(BytesIO(downloaded))
                width, height = img.size
                
                # Trust it if it's high res (>= 400px in either dimension)
                # This covers long thin images or wide banners correctly
                if width >= 200 or height >= 200:
                    image_url = discord_candidate
                    image_bytes = downloaded
                    logger.info(f"   📸 ✅ Discord image is High-Res pixels ({width}x{height}). Skipping scrape.")
                else:
                    logger.info(f"   ⚠️ Discord image is Low-Res pixels ({width}x{height}).")
            except Exception as e:
                logger.warning(f"   ⚠️ Failed to verify Discord image pixels: {e}")

    # 3. Attempt Scraping ONLY if we don't have a high-res candidate yet
    if not image_url:
        target_scrape_url = None
        if title_links: target_scrape_url = title_links[0]['url']
        elif buy_links: target_scrape_url = buy_links[0]['url']
        elif atc_links: target_scrape_url = atc_links[0]['url']
        elif other_links: target_scrape_url = other_links[0]['url']
        
        if target_scrape_url:
            skip_scrape = any(x in target_scrape_url.lower() for x in ['keepa.com', 'ebay.com/sch', 'login', 'cart', 'checkout'])
            if not skip_scrape:
                logger.info(f"   🔍 Attempting to scrape images from: {target_scrape_url[:60]}...")
                scraped_images = fetch_product_images(target_scrape_url, max_images=1)
                if scraped_images:
                    scraped_url = scraped_images[0]
                    # Verify scraped image quality as well
                    logger.info(f"   🔍 Verifying scraped image: {scraped_url[:60]}...")
                    downloaded_scraped = download_image_high_quality(scraped_url)
                    if downloaded_scraped:
                        image_url = scraped_url
                        image_bytes = downloaded_scraped
                        logger.info(f"   📸 ✅ Using verified scraped website image.")

    # 4. Final Fallback (If scraping failed or returned low res, use the best we found)
    if not image_url and discord_candidate:
        image_url = discord_candidate
        # We might already have the bytes from step 2
        # Use them if available, otherwise just use the URL
        logger.info(f"   📸 Fallback to Discord image.")
    
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
    
    return text, image_url, InlineKeyboardMarkup(keyboard) if keyboard else None, image_bytes



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


def create_main_menu(user_id: str = None) -> InlineKeyboardMarkup:
    """Create main menu keyboard"""
    keyboard = []
    uid = str(user_id) if user_id else None
    user_data = sm.users.get(uid, {}) if uid else {}
    is_active = sm.is_active(uid) if uid else False
    has_stripe = bool(user_data.get("stripe_customer_id"))
    
    if is_active:
        keyboard.append([InlineKeyboardButton("📊 My Status", callback_data="status")])
        keyboard.append([InlineKeyboardButton("⚙️ Alert Settings", callback_data="settings")])
        keyboard.append([InlineKeyboardButton("🔔 Toggle Alerts", callback_data="toggle_pause")])
        
        # Bottom options - Everyone can use a code to add more days
        keyboard.append([InlineKeyboardButton("🎟️ Redeem Code", callback_data="redeem")])

        if has_stripe:
            keyboard.append([InlineKeyboardButton("💳 Manage Stripe / Billing", callback_data="billing")])
        else:
            # For code users, rename "Premium" to "Subscribe" to imply a shift to automated billing
            keyboard.append([InlineKeyboardButton("💎 Subscribe (Automated Billing)", callback_data="subscribe")])
    else:
        # User is expired or new
        keyboard.append([InlineKeyboardButton("💎 GET PREMIUM (Stripe)", callback_data="subscribe")])
        keyboard.append([InlineKeyboardButton("🎟️ Redeem Code", callback_data="redeem")])
        
    keyboard.append([InlineKeyboardButton("❓ Help & Commands", callback_data="help")])
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
            # CHECK CATEGORY & SUBCATEGORY SUBSCRIPTION
            msg_channel_id = str(msg.get("channel_id"))
            msg_category = "Uncategorized"
            msg_subcategory = "Unknown"
            for c in cm.channels:
                if c['id'] == msg_channel_id:
                    msg_category = c.get('category', 'Uncategorized')
                    msg_subcategory = c.get('name', 'Unknown')
                    break
            
            if not sm.is_subscribed(user_id, msg_category, msg_subcategory):
                logger.debug(f"   ⏭️ Skipping test alert for {user_id}: {msg_category}/{msg_subcategory} unsubscribed")
                continue

            text, image_url, keyboard, image_bytes = format_telegram_message(msg)
            
            # Prepare photo data once
            photo_data = image_url
            if image_bytes:
                # Reuse pre-verified bytes from formatting step
                photo_data = BytesIO(image_bytes)
                logger.info(f"   ✅ Using pre-verified image bytes ({len(image_bytes)} bytes)")
            elif image_url:
                try:
                    # Fallback for unexpected cases where we have URL but no bytes
                    loop = asyncio.get_event_loop()
                    downloaded = await loop.run_in_executor(sync_executor, download_image_high_quality, image_url)
                    if downloaded:
                        photo_data = BytesIO(downloaded)
                        logger.info(f"   ✅ Processed image via Pillow fallback ({len(downloaded)} bytes)")
                except Exception as e:
                    logger.warning(f"   ⚠️ Pillow processing failed, falling back to URL: {e}")

            # Send (Admin only)
            if photo_data:
                try:
                    # If it's BytesIO, seek(0) to be safe for multiple users (though not needed here)
                    if isinstance(photo_data, BytesIO): photo_data.seek(0)
                    
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

async def subscribe(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show plan selection menu"""
    user_id = str(update.effective_user.id)
    msg = update.effective_message
    
    if not sm.stripe_price_id_monthly:
        if msg:
            await msg.reply_text("❌ Payments are currently disabled (Price ID not set).")
        return

    keyboard = [
        [InlineKeyboardButton("📅 Monthly Plan - £4.99/mo", callback_data="sub_choice:monthly")],
        [InlineKeyboardButton("🗓️ Yearly Plan - £55.50/yr", callback_data="sub_choice:yearly")],
        [InlineKeyboardButton("◀️ Back", callback_data="back:main")]
    ]
    
    reply_text = """
💎 <b>Upgrade to Hollowscan Premium</b>

Choose the plan that fits you best. Get instant professional alerts, full stock data, and direct action links.

✨ <b>Benefits:</b>
• ⚡️ Real-time notifications
• 🖼️ Product images
• 🔗 Direct action links
• 📊 Full stock & price data
• ⏸️ Pause/Resume anytime
"""
    
    if update.callback_query:
        await update.callback_query.edit_message_text(reply_text, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        await update.message.reply_text(reply_text, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(keyboard))

async def handle_subscribe_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Generate Checkout link for specific plan"""
    query = update.callback_query
    await query.answer()
    
    user = update.effective_user
    user_id = str(user.id)
    choice = query.data.split(":")[1]
    
    price_id = sm.stripe_price_id_monthly if choice == "monthly" else sm.stripe_price_id_yearly
    
    if not price_id:
        await query.edit_message_text("❌ This plan is currently unavailable.")
        return

    await query.edit_message_text("⏳ Generating your secure checkout link...")
    
    try:
        session = stripe.checkout.Session.create(
            payment_method_types=['card'],
            line_items=[{
                'price': price_id,
                'quantity': 1,
            }],
            mode='subscription',
            client_reference_id=user_id,
            metadata={'user_id': user_id, 'username': user.username or user.first_name, 'plan': choice},
            success_url=f"https://t.me/{(await context.bot.get_me()).username}",
            cancel_url=f"https://t.me/{(await context.bot.get_me()).username}",
        )
        
        reply_text = f"""
🚀 <b>Your {choice.capitalize()} Subscription Link</b>

Click below to complete your payment securely via Stripe:

{session.url}

<i>Link expires in 24 hours. Subscription renews automatically every {choice[:-2] if choice=='monthly' else 'year'}.</i>
"""
        # We can't use edit_message_text because of the link length sometimes causing issues with InlineButtons or just to be clean
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=reply_text,
            parse_mode=ParseMode.HTML
        )
        
    except Exception as e:
        logger.error(f"Stripe Session Error: {e}")
        await query.edit_message_text("❌ Failed to generate checkout link. Please contact admin.")

async def billing_portal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Generate Stripe Billing Portal Link"""
    user_id = str(update.effective_user.id)
    user_data = sm.users.get(user_id, {})
    customer_id = user_data.get("stripe_customer_id")
    
    # Safety: identify if this is a callback or a message
    msg = update.effective_message
    
    if not customer_id:
        text = "❌ You don't have an active automated subscription. If you used a code, contact admin."
        if msg:
            await msg.reply_text(text)
        return

    try:
        session = stripe.billing_portal.Session.create(
            customer=customer_id,
            return_url=f"https://t.me/{(await context.bot.get_me()).username}",
        )
        text = f"🛠️ <b>Manage Your Subscription</b>\n\nUse the link below to update your payment method or cancel your subscription:\n\n{session.url}"
        if msg:
            await msg.reply_text(text, parse_mode=ParseMode.HTML)
    except stripe.error.InvalidRequestError as e:
        logger.error(f"Stripe Customer Error: {e}")
        if "No such customer" in str(e):
            # Clean up stale ID
            with sm.lock:
                if "stripe_customer_id" in sm.users.get(user_id, {}):
                    del sm.users[user_id]["stripe_customer_id"]
                if "stripe_subscription_id" in sm.users.get(user_id, {}):
                    del sm.users[user_id]["stripe_subscription_id"]
                sm._sync_state()
            
            if msg:
                await msg.reply_text("⚠️ Your subscription record was not found in Stripe (likely a Test/Live mismatch). I have reset your billing link. Please try /subscribe to link a valid account.")
        else:
            if msg:
                await msg.reply_text(f"❌ Stripe Error: {str(e)}")

    except Exception as e:
        logger.error(f"Stripe Portal Error: {e}")
        if msg:
            await msg.reply_text("❌ Error opening billing portal.")

async def link_app_account(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Link Telegram account to app account using link key"""
    user_id = str(update.effective_user.id)
    username = update.effective_user.username or update.effective_user.first_name
    
    # Get link key from command args
    if not context.args or len(context.args) < 1:
        await update.message.reply_text(
            "❌ <b>Invalid Link Key</b>\n\n"
            "Usage: <code>/link ABC123</code>\n\n"
            "Get your link key from the HollowScan app:\n"
            "1. Open the app\n"
            "2. Go to Profile\n"
            "3. Tap 'Connect Telegram'\n"
            "4. Copy the link key\n"
            "5. Come back here and send: /link [KEY]",
            parse_mode=ParseMode.HTML
        )
        return
    
    link_key = context.args[0].upper()  # e.g., "ABC123"
    
    try:
        print(f"[LINK] Attempting to link {username} (ID: {user_id}) with key {link_key}")
        
        # 1. Load pending links from backend
        import os
        links_file = "data/pending_telegram_links.json"
        
        if not os.path.exists(links_file):
            await update.message.reply_text(
                "❌ <b>Invalid Link Key</b>\n\n"
                "This key is not recognized or has expired.\n\n"
                "Please get a new link key from the HollowScan app.",
                parse_mode=ParseMode.HTML
            )
            return
        
        with open(links_file, 'r') as f:
            pending_links = json.load(f)
        
        # 2. Check if key exists and is valid
        if link_key not in pending_links:
            await update.message.reply_text(
                "❌ <b>Invalid Link Key</b>\n\n"
                f"The key '<code>{link_key}</code>' is not recognized or has expired.\n\n"
                "Please get a new link key from the HollowScan app.",
                parse_mode=ParseMode.HTML
            )
            return
        
        link_info = pending_links[link_key]
        
        # 3. Check if already used
        if link_info.get('used'):
            await update.message.reply_text(
                "⚠️ <b>Already Linked</b>\n\n"
                f"This link key has already been used.\n\n"
                "Get a new link key from the HollowScan app.",
                parse_mode=ParseMode.HTML
            )
            return
        
        # 4. Check if expired (15 minute window)
        from datetime import datetime, timezone
        try:
            expires_at = datetime.fromisoformat(link_info['expires_at'].replace('Z', '+00:00'))
            if datetime.now(timezone.utc) > expires_at:
                await update.message.reply_text(
                    "⏰ <b>Link Key Expired</b>\n\n"
                    "This link key has expired (valid for 15 minutes).\n\n"
                    "Get a new link key from the HollowScan app.",
                    parse_mode=ParseMode.HTML
                )
                return
        except Exception as e:
            logger.error(f"Error checking expiry: {e}")
        
        # 5. Get the app user ID from the pending link
        app_user_id = link_info['user_id']
        
        # 6. Mark link as used and update with Telegram info
        link_info['used'] = True
        link_info['used_at'] = datetime.now(timezone.utc).isoformat()
        link_info['telegram_id'] = user_id
        link_info['telegram_username'] = username
        
        with open(links_file, 'w') as f:
            json.dump(pending_links, f, indent=2)
        
        print(f"[LINK] Key {link_key} marked as used for Telegram user {user_id}")
        
        # 7. Call the backend endpoint to complete the linking
        import requests
        api_base = os.getenv("API_BASE_URL", "https://web-production-18cf1.up.railway.app")
        api_url = f"{api_base}/v1/user/telegram/link"
        
        try:
            response = requests.post(
                api_url,
                params={
                    "user_id": app_user_id,
                    "telegram_chat_id": int(user_id),
                    "telegram_username": username
                },
                timeout=10
            )
            
            if response.status_code == 200:
                data = response.json()
                
                if data.get('is_premium'):
                    await update.message.reply_text(
                        "🎉 <b>Account Linked & Premium Synced!</b>\n\n"
                        "Your HollowScan app account has been successfully linked to Telegram!\n"
                        "Your premium status has been synced from the app.\n\n"
                        f"✨ Premium until: {data.get('premium_until', 'N/A')}",
                        parse_mode=ParseMode.HTML
                    )
                else:
                    await update.message.reply_text(
                        "✅ <b>Account Linked!</b>\n\n"
                        "Your HollowScan app account has been successfully linked to Telegram!\n\n"
                        "💡 <b>Tip:</b> Upgrade to premium in the app to unlock all features.",
                        parse_mode=ParseMode.HTML
                    )
                print(f"[LINK] Successfully linked {username} (Telegram {user_id}) to app user {app_user_id}")
            else:
                logger.error(f"Backend error: {response.status_code} {response.text}")
                await update.message.reply_text(
                    "⚠️ <b>Linking Failed</b>\n\n"
                    "There was an error connecting to the app backend.\n\n"
                    "Please try again or contact support.",
                    parse_mode=ParseMode.HTML
                )
        
        except requests.exceptions.RequestException as req_error:
            logger.error(f"Request error: {req_error}")
            await update.message.reply_text(
                "⚠️ <b>Linking Failed</b>\n\n"
                "Could not reach the app backend. Please try again shortly.",
                parse_mode=ParseMode.HTML
            )
    
    except json.JSONDecodeError:
        logger.error("Error decoding pending links JSON")
        await update.message.reply_text(
            "⚠️ <b>System Error</b>\n\n"
            "There was an error processing your link. Please try again.",
            parse_mode=ParseMode.HTML
        )
    except Exception as e:
        logger.error(f"Link error: {e}")
        await update.message.reply_text(
            "❌ <b>Linking Error</b>\n\n"
            f"Error: {str(e)}",
            parse_mode=ParseMode.HTML
        )


# --- ACCOUNT LINKING HANDLERS ---

async def handle_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /link command to connect Telegram to Mobile App"""
    user_id = str(update.effective_user.id)
    chat_type = update.effective_chat.type
    
    if chat_type != 'private':
        await update.message.reply_text("⚠️ Please use this command in a private chat with the bot.")
        return

    # Generate secure token
    token = str(uuid.uuid4())
    
    # Store in Supabase (10 min expiry)
    success = await asyncio.to_thread(supabase_utils.store_telegram_link_token, token, user_id)
    
    if success:
        # Use a redirect URL (Since Telegram buttons don't support hollowscan://)
        api_base = os.getenv("API_BASE_URL", "https://web-production-18cf1.up.railway.app")
        redirect_url = f"{api_base}/v1/user/telegram/redirect?code={token}"
        
        keyboard = [
            [InlineKeyboardButton("🔗 Connect Account", url=redirect_url)]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            "**🔗 Connect to hollowScan**\n\n"
            "Tap the button below to link your Telegram account to the mobile app.\n"
            "This will open a secure window to verify the connection.",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=reply_markup
        )
    else:
        await update.message.reply_text("❌ Failed to generate link. Please try again later.")

async def handle_unlink(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /unlink command"""
    user_id = str(update.effective_user.id)
    
    # Delete link from Supabase
    success = await asyncio.to_thread(supabase_utils.delete_user_telegram_link, user_id)
    
    if success:
        await update.message.reply_text("✅ Your Telegram account has been unlinked from hollowScan.")
    else:
        await update.message.reply_text("❌ Failed to unlink or account was not linked.")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Welcome message with main menu"""
    user_id = str(update.effective_user.id)
    username = update.effective_user.username or update.effective_user.first_name
    
    # Check for deep link parameter (from app)
    # Format: https://t.me/Bot?start=link_<USER_ID>
    if context.args and len(context.args) > 0:
        param = context.args[0]
        
        # New Direct Link Flow
        if param.startswith("link_"):
            app_user_id = param.replace("link_", "")
            await update.message.reply_text("🔄 Linking your account...")
            
            # Prepare premium info if applicable
            premium_info = None
            if sm.is_active(user_id):
                user_data = sm.users.get(str(user_id), {})
                premium_info = {
                    "status": "active",
                    "end": user_data.get('expiry'),  # Raw ISO timestamp
                    "source": "telegram"
                }

            # Call robust linking util
            result = await asyncio.to_thread(
                supabase_utils.link_app_user_to_telegram, 
                app_user_id, 
                user_id, 
                f"@{username}" if username else None,
                premium_info
            )
            
            if result.get("success"):
                await update.message.reply_text(
                    "✅ **Successfully Linked!**\n\n"
                    "Your Telegram account is now connected to the HollowScan App.\n"
                    "You can return to the app now.",
                    parse_mode=ParseMode.MARKDOWN
                )
            else:
                await update.message.reply_text(f"❌ Linking Failed: {result.get('message')}")
            return

        elif param == "link_account":
             # Legacy flow - deprecated but kept for safety
            await handle_link(update, context)
            return
    
    # Track as potential user if not subscribed
    sm.track_potential_user(user_id, username)
    
    welcome_text = f"""
👋 <b>Welcome to Hollowscan!</b>

<i>Hello {username}!</i> Get instant product alerts with all the data you need.

🎯 <b>Features:</b>
• Real-time deal notifications
• Custom category preferences  
• Premium tier for advanced features

Use /settings to customize your alerts or /help for all commands.

📊 <b>Status:</b>
"""
    
    if sm.is_active(user_id):
        stats = sm.get_user_stats(user_id)
        welcome_text += f"✅ <b>Active</b> – {stats['days_remaining']} days remaining\n"
        if stats['is_paused']:
            welcome_text += "⏸️ Alerts currently paused\n"
        
        # Show tip only for active users
        welcome_text += '\n💡 <b>Tip:</b> Click on "⚙️ <b>Alert Settings</b>" below to toggle ✅ on or ❌ off any country store you want to receive (or stop receiving) notifications from. Customize your experience!'
    else:
        welcome_text += "❌ <b>Not subscribed</b>\n\nRedeem a code or subscribe below to get started!\n"

    await update.message.reply_text(
        welcome_text,
        parse_mode=ParseMode.HTML,
        reply_markup=create_main_menu(user_id)
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
            welcome_text = f"👋 <b>Welcome to Hollowscan!</b>\n\n<i>Hello {username}!</i> Get instant product alerts with all the data you need.\n\n🎯 <b>Features:</b>\n• ⚡️ Real-time notifications\n• 🖼️ Product images\n• 🔗 Direct action links\n• 📊 Full stock & price data\n• ⏸️ Pause/Resume anytime\n\n📊 <b>Status:</b>\n"
            if sm.is_active(user_id):
                stats = sm.get_user_stats(user_id)
                welcome_text += f"✅ <b>Active</b> – {stats['days_remaining']} days remaining\n"
                if stats['is_paused']:
                    welcome_text += "⏸️ Alerts currently paused\n"
                
                # Show tip only for active users
                welcome_text += '\n💡 <b>Tip:</b> Click on "⚙️ <b>Alert Settings</b>" below to toggle ✅ on or ❌ off any country store you want to receive (or stop receiving) notifications from. Customize your experience!'
            else:
                welcome_text += "❌ <b>Not subscribed</b>\n\nRedeem a code or subscribe below to get started!\n"
            
            try:
                await query.edit_message_text(welcome_text, parse_mode=ParseMode.HTML, reply_markup=create_main_menu(user_id))
            except BadRequest as e:
                if "Message is not modified" not in str(e):
                    raise e
            return
            
        elif menu_to_go == "settings":
            # Show main settings (category menu)
            all_cats = cm.get_categories()
            user_cats = sm.get_user_categories(user_id)
            text = "⚙️ <b>Alert Category Settings</b>\n\nTap a category to manage its stores:"
            buttons = []
            for cat in all_cats:
                is_enabled = cat in user_cats
                status_icon = "✅" if is_enabled else "❌"
                buttons.append([InlineKeyboardButton(f"{status_icon} {cat.replace('_', ' ')}", callback_data=f"settings_cat:{cat}")])
            await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=create_menu_with_back(buttons, "main"))
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
        text += f"\n\n<i>Last updated: {datetime.utcnow().strftime('%H:%M:%S')} UTC</i>"
        
        buttons = [[InlineKeyboardButton("🔄 Refresh", callback_data="status")]]
        try:
            await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=create_menu_with_back(buttons, "main"))
        except BadRequest as e:
            if "Message is not modified" not in str(e):
                raise e
    
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
    
    elif action == "subscribe":
        # Redirect to subscribe command logic
        await subscribe(update, context)
        return

    elif action == "billing":
        # Redirect to billing portal logic
        await billing_portal(update, context)
        return
    
    elif action.startswith("sub_choice:"):
        await handle_subscribe_choice(update, context)
        return
    
    elif action == "settings":
        if not sm.is_active(user_id):
            text = "❌ <b>Not Subscribed</b>\n\nUse /start to redeem a code!"
            await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=create_menu_with_back([], "main"))
            return

        all_cats = cm.get_categories()
        user_cats = sm.get_user_categories(user_id)
        
        text = "⚙️ <b>Alert Category Settings</b>\n\nTap a category to manage its stores:"
        
        buttons = []
        for cat in all_cats:
            is_enabled = cat in user_cats
            status_icon = "✅" if is_enabled else "❌"
            buttons.append([InlineKeyboardButton(f"{status_icon} {cat.replace('_', ' ')}", callback_data=f"settings_cat:{cat}")])
            
        await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=create_menu_with_back(buttons, "main"))

    elif action.startswith("settings_cat:") or action.startswith("toggle_subcat:") or action.startswith("toggle_cat:"):
        # Determine category and specific command
        parts = action.split(":", 2)
        cmd = parts[0]
        cat = parts[1]
        
        if cmd == "toggle_subcat":
            sub = parts[2]
            sm.toggle_subcategory(user_id, cat, sub)
        elif cmd == "toggle_cat":
            sm.toggle_category(user_id, cat)

        # Build / Refresh Subcategory Menu
        all_subs = cm.get_subcategories(cat)
        user_cats = sm.get_user_categories(user_id)
        is_cat_enabled = cat in user_cats
        disabled_subs = sm.get_disabled_subcategories(user_id)

        status_text = "✅ ENABLED" if is_cat_enabled else "❌ DISABLED (Turn on to see stores)"
        text = f"⚙️ <b>Store Settings: {cat.replace('_', ' ')}</b>\n\nCategory Status: <b>{status_text}</b>"
        
        buttons = []
        # Master Toggle
        toggle_label = "🔴 Disable Category" if is_cat_enabled else "🟢 Enable Category"
        buttons.append([InlineKeyboardButton(toggle_label, callback_data=f"toggle_cat:{cat}")])
        buttons.append([InlineKeyboardButton("━━━━━━━━━━━━━━━", callback_data="none")])
        
        row = []
        for sub in all_subs:
            sub_key = f"{cat}:{sub}"
            is_sub_enabled = (sub_key not in disabled_subs)
            sub_icon = "✅" if is_sub_enabled else "❌"
            
            # Safety: Telegram callback_data limit is 64 bytes
            sub_callback = f"toggle_subcat:{cat}:{sub}"
            if len(sub_callback.encode('utf-8')) > 64:
                # Truncate sub name if needed (unlikely but safe)
                sub_callback = f"toggle_subcat:{cat}:{sub[:20]}"
            
            row.append(InlineKeyboardButton(f"{sub_icon} {sub}", callback_data=sub_callback))
            if len(row) == 2:
                buttons.append(row)
                row = []
        if row: buttons.append(row)

        try:
            await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=create_menu_with_back(buttons, "settings"))
        except BadRequest as e:
            if "Message is not modified" not in str(e):
                raise e

    elif action == "none":
        # Decorative separator, ignore click
        pass
                
    elif action == "help":
        text = """
❓ <b>Help & Information</b>

<b>How It Works:</b>
1️⃣ Redeem a code OR Subscribe via Stripe
2️⃣ Receive real-time alerts with images & links
3️⃣ Click buttons to check eBay, Keepa, Amazon instantly

<b>Getting Premium:</b>
• Use <b>/subscribe</b> to pick a monthly/yearly plan
• Use <b>/start</b> to redeem a promo code
• Use <b>/billing</b> to manage your subscription

<b>Commands:</b>
• /start - Main menu & status
• /subscribe - Upgrade to Premium

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
        await update.message.reply_text("⛔ Admin only.")
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

async def add_channel_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin: Add a new channel to scrape"""
    if not is_admin(update.effective_user.id): 
        await update.message.reply_text("⛔ Admin only.")
        return

    # Usage: /add_channel <url> <category> <name...>
    if not context.args or len(context.args) < 3:
        await update.message.reply_text(
            "Usage: /add_channel <url> <category> <name>\n"
            "Example: /add_channel https://discord.com/.../12345 USA_Stores Target USA",
            disable_web_page_preview=True
        )
        return

    url = context.args[0]
    category = context.args[1].replace("_", " ")[:20] 
    name = " ".join(context.args[2:])[:20]

    if cm.add_channel(url, category, name):
        await update.message.reply_text(
            f"✅ <b>Channel Added!</b>\n\n"
            f"📝 Name: {name}\n"
            f"📂 Category: {category}\n"
            f"🔗 ID: {url.split('/')[-1]}",
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True
        )
    else:
        await update.message.reply_text("❌ Failed to add channel. Check URL or if duplicate.")

async def remove_channel_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin: Remove a channel"""
    if not is_admin(update.effective_user.id): 
        await update.message.reply_text("⛔ Admin only.")
        return

    if not context.args:
        await update.message.reply_text("Usage: /remove_channel <channel_id>")
        return
    
    chan_id = context.args[0]
    if cm.remove_channel(chan_id):
        await update.message.reply_text(f"✅ Channel <code>{chan_id}</code> removed.", parse_mode=ParseMode.HTML)
    else:
        await update.message.reply_text("❌ Channel ID not found.", parse_mode=ParseMode.HTML)

async def list_channels_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin: List all channels"""
    if not is_admin(update.effective_user.id): 
        await update.message.reply_text("⛔ Admin only.")
        return

    channels = cm.get_enabled_channels()
    if not channels:
        await update.message.reply_text("ℹ️ No channels configured.")
        return

    text = "📺 <b>Configured Channels</b>\n\n"
    current_cat = None
    
    # Sort by category then name
    sorted_chans = sorted(channels, key=lambda x: (x.get('category', 'Z'), x['name']))
    
    for c in sorted_chans:
        cat = c.get('category', 'Uncategorized').replace("_", " ")
        if cat != current_cat:
            text += f"📂 <b>{cat}</b>\n"
            current_cat = cat
        text += f"• {c['name']} (<code>{c['id']}</code>)\n"

    await update.message.reply_text(text, parse_mode=ParseMode.HTML)

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
            err_msg = f"⚠️ <b>Broadcast job TIMEOUT</b> after {elapsed:.1f}s - forcing termination"
            logger.error(f"❌ Broadcast job TIMEOUT after {elapsed:.1f}s - forcing termination")
            await notify_admins(context, err_msg)
            
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

Your access to Hollowscan has expired. 

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

You recently checked out Hollowscan but haven't activated your subscription yet. 

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
        err_msg = f"❌ <b>Polling Failed</b>: {type(e).__name__}: {e}"
        logger.error(f"❌ Failed to poll messages: {e}")
        await notify_admins(context, err_msg)
        return
    
    if not new_msgs:
        logger.debug("🔭 Poll: No new messages found")
        return
    
    # Filter out duplicate sources, unwanted restock alerts, and noisy patterns
    filtered_msgs = []
    
    # Noise/Restock patterns to filter
    NOISE_PATTERNS = ["@Currys +", "Just restocked for"]
    # Keywords that override filtering (instructions)
    INSTRUCTION_KEYWORDS = ["refresh", "details", "access", "step", "tip", "screen", "wait"]

    for msg in new_msgs:
        # LAYER A: Existing filters (Duplicate source/Restock filter)
        if is_duplicate_source(msg) or is_restock_filter_match(msg):
            continue
            
        # LAYER B: Aggressive Duplicate Content Check (If Title == Description/Content)
        # We check this before formatting to save CPU
        raw = msg.get("raw_data", {})
        embed = raw.get("embed") or {}
        title = (embed.get("title") or "").strip().lower()
        desc = (embed.get("description") or "").strip().lower()
        content = (msg.get("content") or "").strip().lower()
        
        if title and (title == desc or title == content):
            logger.info(f"⏭️ FILTERED: Identical Title and Content ({msg.get('id')})")
            continue

        # LAYER C: Noisy Mass-Restock Alerts (e.g. Currys)
        # We don't filter if it looks like an instruction
        is_instruction = any(kw in (desc + content).lower() for kw in INSTRUCTION_KEYWORDS)
        if not is_instruction:
            is_noise = any(pattern.lower() in (desc + content).lower() for pattern in NOISE_PATTERNS)
            if is_noise:
                logger.info(f"⏭️ FILTERED: Noisy restock pattern ({msg.get('id')})")
                continue

        filtered_msgs.append(msg)
    
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
            text, image_url, keyboard, image_bytes = format_telegram_message(msg)
            logger.debug(f"   ✓ Formatted (text={len(text)} chars, image={'yes' if image_url else 'no'})")
            
            # Validate message is not empty
            if not text or len(text.strip()) == 0:
                continue
            
        except Exception as e:
            logger.error(f"   ❌ Failed to format message {msg_idx + 1}: {type(e).__name__}: {e}")
            continue
        
        # Prepare photo data once per message
        photo_data = image_url
        if image_bytes:
            # Reuse pre-verified bytes from formatting step
            photo_data = image_bytes
            logger.info(f"   ✅ Using pre-verified message image bytes ({len(image_bytes)} bytes)")
        elif image_url:
            try:
                # Fallback for unexpected cases
                loop = asyncio.get_event_loop()
                downloaded = await loop.run_in_executor(sync_executor, download_image_high_quality, image_url)
                if downloaded:
                    photo_data = downloaded
                    logger.info(f"   ✅ Processed message image via Pillow fallback ({len(downloaded)} bytes)")
            except Exception as e:
                logger.warning(f"   ⚠️ Pillow processing failed: {e}")

        # Send to all active users with rate limiting
        sent_count = 0
        failed_count = 0
        
        # Determine Category & Subcategory
        msg_channel_id = str(msg.get("channel_id"))
        msg_category = "Uncategorized"
        msg_subcategory = "Unknown"
        for c in cm.channels:
            if c['id'] == msg_channel_id:
                msg_category = c.get('category', 'Uncategorized')
                msg_subcategory = c.get('name', 'Unknown')
                break
        
        # Send to all active users with rate limiting
        sent_count = 0
        failed_count = 0
        
        for uid in active_users:
            # CHECK SUBSCRIPTION
            if not sm.is_subscribed(uid, msg_category, msg_subcategory):
                continue

            try:
                # Send with timeout protection
                if photo_data:
                    try:
                        # Prepare the payload (BytesIO if we have raw bytes)
                        current_photo = photo_data
                        if isinstance(photo_data, bytes):
                            current_photo = BytesIO(photo_data)
                            
                        await asyncio.wait_for(
                            context.bot.send_photo(
                                chat_id=uid,
                                photo=current_photo,
                                caption=text[:1024],
                                parse_mode=ParseMode.HTML,
                                reply_markup=keyboard
                            ),
                            timeout=12.0
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
    BotCommand("add_channel", "Add scraper channel"),
    BotCommand("remove_channel", "Remove scraper channel"),
    BotCommand("channels", "List all channels"),
]

# Additional commands for superadmin
SUPERADMIN_COMMANDS = [
    BotCommand("start", "Start the bot and see main menu"),
    BotCommand("help", "Show available commands"),
    BotCommand("gen", "Generate subscription code (e.g., /gen 30)"),
    BotCommand("test", "Test recent alerts (e.g., /test 5)"),
    BotCommand("add_admin", "Add a user as admin (e.g., /add_admin 123456)"),
    BotCommand("remove_admin", "Remove admin status (e.g., /remove_admin 123456)"),
    BotCommand("add_channel", "Add scraper channel"),
    BotCommand("remove_channel", "Remove scraper channel"),
    BotCommand("channels", "List all channels"),
]

async def setup_bot_commands(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Set up command menus for different user roles (Run as Job)"""
    application = context.application
    try:
        logger.info("🛠️ Setting up command menus...")
        # 1. Set default commands for all users
        await application.bot.set_my_commands(DEFAULT_COMMANDS, scope=BotCommandScopeDefault())
        logger.info("   ✅ Default command menu set")
        
        # 2. Set SUPERADMIN_COMMANDS for IDs in .env
        for admin_id in ADMIN_USER_IDS:
            try:
                await application.bot.set_my_commands(
                    SUPERADMIN_COMMANDS, 
                    scope=BotCommandScopeChat(chat_id=int(admin_id))
                )
                logger.info(f"   ✅ Superadmin menu set for .env user {admin_id}")
            except Exception as e:
                logger.debug(f"   Could not set superadmin menu for {admin_id}: {e}")

        # 3. Set ADMIN_COMMANDS for secondary admins Managed by bot
        for user_id, user_data in sm.users.items():
            if user_id in ADMIN_USER_IDS: continue # Skip if already set as superadmin
            
            if user_data.get("is_admin", False):
                try:
                    await application.bot.set_my_commands(
                        ADMIN_COMMANDS, 
                        scope=BotCommandScopeChat(chat_id=int(user_id))
                    )
                    logger.info(f"   ✅ Admin menu set for user {user_id}")
                except Exception as e:
                    logger.debug(f"   Could not set admin menu for {user_id}: {e}")
                
                # Small delay to avoid rate limits
                await asyncio.sleep(0.5)
                
    except Exception as e:
        logger.error(f"   ❌ Failed to set command menus: {e}")

# --- BROADCAST FEATURE ---

BROADCAST_TARGET, BROADCAST_MESSAGE, BROADCAST_PIN, BROADCAST_CONFIRM = range(4)

async def broadcast_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start the broadcast conversation"""
    user_id = str(update.effective_user.id)
    if not is_admin(user_id):
        await update.message.reply_text("⛔ You are not authorized to use this command.")
        return ConversationHandler.END

    keyboard = [
        [
            InlineKeyboardButton("All Users", callback_data="target_all"),
            InlineKeyboardButton("Active Users", callback_data="target_active")
        ],
        [
            InlineKeyboardButton("Expired Users", callback_data="target_expired"),
            InlineKeyboardButton("Potential Users", callback_data="target_potential")
        ],
        [InlineKeyboardButton("❌ Cancel", callback_data="cancel")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "📢 <b>Broadcast Wizard</b>\n\nSelect the target audience for your broadcast:",
        reply_markup=reply_markup,
        parse_mode=ParseMode.HTML
    )
    return BROADCAST_TARGET

async def broadcast_target(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle target selection"""
    query = update.callback_query
    await query.answer()
    
    if query.data == "cancel":
        await query.edit_message_text("❌ Broadcast cancelled.")
        return ConversationHandler.END
        
    target = query.data.replace("target_", "")
    context.user_data["broadcast_target"] = target
    
    target_names = {
        "all": "All Users",
        "active": "Active Subscribers",
        "expired": "Expired Subscribers",
        "potential": "Potential Users"
    }
    
    await query.edit_message_text(
        f"🎯 Target: <b>{target_names.get(target, target)}</b>\n\n"
        "Now send the message you want to broadcast.\n"
        "• You can send <b>Text</b> or a <b>Photo with Caption</b>.\n"
        "• Supported formatting: <code>&lt;b&gt;bold&lt;/b&gt;</code>, <code>&lt;i&gt;italics&lt;/i&gt;</code>, <code>&lt;code&gt;copyable&lt;/code&gt;</code>.",
        parse_mode=ParseMode.HTML
    )
    return BROADCAST_MESSAGE

async def broadcast_message_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle the broadcast content input"""
    message = update.message
    
    # Store message details
    if message.photo:
        # Get the largest photo
        file_id = message.photo[-1].file_id
        caption = message.caption or ""
        context.user_data["broadcast_content"] = {
            "type": "photo",
            "file_id": file_id,
            "text": caption
        }
        
    elif message.text:
        text = message.text
        context.user_data["broadcast_content"] = {
            "type": "text",
            "text": text
        }
    else:
        await message.reply_text("⚠️ Please send text or a photo.")
        return BROADCAST_MESSAGE

    # Ask for pinning preference
    keyboard = [
        [InlineKeyboardButton("✅ Pin (Notify)", callback_data="pin_notify")],
        [InlineKeyboardButton("🔕 Pin (Silent)", callback_data="pin_silent")],
        [InlineKeyboardButton("❌ Don't Pin", callback_data="pin_no")],
        [InlineKeyboardButton("🚫 Cancel Broadcast", callback_data="cancel")]
    ]
    
    # Replying with the pin question
    if message.photo:
        await message.reply_photo(
            photo=context.user_data["broadcast_content"]["file_id"],
            caption=f"📢 <b>PREVIEW (Target: {context.user_data['broadcast_target']})</b>\n\n{context.user_data['broadcast_content']['text']}\n\n-------------------\n📌 <b>Do you want to pin this message?</b>",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    else:
        await message.reply_text(
            text=f"📢 <b>PREVIEW (Target: {context.user_data['broadcast_target']})</b>\n\n{context.user_data['broadcast_content']['text']}\n\n-------------------\n📌 <b>Do you want to pin this message?</b>",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
    return BROADCAST_PIN

async def broadcast_pin_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle the pinning choice and move to confirmation"""
    query = update.callback_query
    await query.answer()
    
    choice = query.data
    if choice == "cancel":
        await query.edit_message_text("❌ Broadcast cancelled.")
        return ConversationHandler.END
        
    # Store pin preference
    pin_mode = "no"
    if choice == "pin_notify":
        pin_mode = "notify"
    elif choice == "pin_silent":
        pin_mode = "silent"
        
    context.user_data["broadcast_pin"] = pin_mode
    
    # Now send final confirmation
    target = context.user_data["broadcast_target"]
    pin_text = {
        "notify": "✅ Pin & Notify",
        "silent": "🔕 Pin Silently",
        "no": "❌ No Pin"
    }.get(pin_mode)
    
    # Update the preview message to show confirmation button
    keyboard = [
        [InlineKeyboardButton("🚀 EXECUTE BROADCAST", callback_data="confirm_send")],
        [InlineKeyboardButton("❌ Cancel", callback_data="cancel")]
    ]
    
    confirm_text = (
        f"📢 <b>FINAL CONFIRMATION</b>\n\n"
        f"🎯 Target: <b>{target}</b>\n"
        f"📌 Pinning: <b>{pin_text}</b>\n\n"
        "Ready to send?"
    )

    try:
        if query.message.photo:
             await query.edit_message_caption(
                 caption=confirm_text,
                 reply_markup=InlineKeyboardMarkup(keyboard),
                 parse_mode=ParseMode.HTML
             )
        else:
             await query.edit_message_text(
                 text=confirm_text,
                 reply_markup=InlineKeyboardMarkup(keyboard),
                 parse_mode=ParseMode.HTML
             )
    except Exception as e:
        logger.warning(f"Error updating confirmation msg: {e}")
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=confirm_text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.HTML
        )
        
    return BROADCAST_CONFIRM

async def broadcast_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Execute the broadcast"""
    query = update.callback_query
    await query.answer()
    
    if query.data == "cancel":
        await query.edit_message_text("❌ Broadcast cancelled.")
        return ConversationHandler.END
    
    target = context.user_data.get("broadcast_target")
    content = context.user_data.get("broadcast_content")
    pin_mode = context.user_data.get("broadcast_pin", "no")
    
    # Get recipients
    recipients = []
    if target == "all":
        recipients = sm.get_all_users()
    elif target == "active":
        recipients = sm.get_active_users()
    elif target == "expired":
        recipients = sm.get_expired_users()
    elif target == "potential":
        recipients = sm.get_potential_users_list()
    
    # Check if we are editing a text message or a caption (if photo)
    try:
        if update.callback_query.message.photo:
            await query.edit_message_caption(caption=f"🚀 Sending broadcast to {len(recipients)} users...")
        else:
            await query.edit_message_text(f"🚀 Sending broadcast to {len(recipients)} users...")
    except Exception as e:
        logger.warning(f"Could not edit broadcast status message: {e}")
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=f"🚀 Sending broadcast to {len(recipients)} users..."
        )
    
    success_count = 0
    fail_count = 0
    
    for user_id in recipients:
        try:
            sent_msg = None
            if content["type"] == "photo":
                sent_msg = await context.bot.send_photo(
                    chat_id=user_id,
                    photo=content["file_id"],
                    caption=content["text"],
                    parse_mode=ParseMode.HTML
                )
            else:
                sent_msg = await context.bot.send_message(
                    chat_id=user_id,
                    text=content["text"],
                    parse_mode=ParseMode.HTML
                )
            
            # Pinning Logic
            if sent_msg and pin_mode in ["notify", "silent"]:
                try:
                    await context.bot.pin_chat_message(
                        chat_id=user_id,
                        message_id=sent_msg.message_id,
                        disable_notification=(pin_mode == "silent")
                    )
                except Exception as pin_error:
                     # Often fails if bot not admin or private chat restrictions, just log it
                     logger.debug(f"Failed to pin for {user_id}: {pin_error}")

            success_count += 1
            await asyncio.sleep(0.05) # Rate limit protection
        except Exception as e:
            logger.warning(f"Failed to broadcast to {user_id}: {e}")
            fail_count += 1
            
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=f"✅ <b>Broadcast Complete</b>\n\nSuccessful: {success_count}\nFailed: {fail_count}",
        parse_mode=ParseMode.HTML
    )
    
    return ConversationHandler.END

async def broadcast_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancel conversation"""
    await update.message.reply_text("❌ Broadcast cancelled.")
    return ConversationHandler.END

# --- UNPIN FEATURE ---

UNPIN_TARGET, UNPIN_CONFIRM = range(2)

async def unpin_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start the unpin wizard"""
    user_id = str(update.effective_user.id)
    if not is_admin(user_id):
        await update.message.reply_text("⛔ You are not authorized.")
        return ConversationHandler.END
        
    keyboard = [
        [
            InlineKeyboardButton("All Users", callback_data="target_all"),
            InlineKeyboardButton("Active Users", callback_data="target_active")
        ],
        [InlineKeyboardButton("❌ Cancel", callback_data="cancel")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "📌 <b>Unpin Wizard</b>\n\nWho do you want to unpin ALL messages for?\n"
        "(This will clear the pin bar for these users)",
        reply_markup=reply_markup,
        parse_mode=ParseMode.HTML
    )
    return UNPIN_TARGET

async def unpin_target_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle target selection for unpinning"""
    query = update.callback_query
    await query.answer()
    
    if query.data == "cancel":
        await query.edit_message_text("❌ Unpin cancelled.")
        return ConversationHandler.END
        
    target = query.data.replace("target_", "")
    context.user_data["unpin_target"] = target
    
    target_names = {"all": "All Users", "active": "Active Subscribers"}
    
    # Confirmation Step
    keyboard = [
        [InlineKeyboardButton("🗑️ YES, UNPIN EVERYTHING", callback_data="confirm_unpin")],
        [InlineKeyboardButton("❌ Cancel", callback_data="cancel")]
    ]
    
    await query.edit_message_text(
        f"⚠️ <b>CONFIRM UNPIN</b>\n\nTarget: <b>{target_names.get(target, target)}</b>\n\n"
        "Are you sure you want to remove ALL pinned messages for these users?",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=ParseMode.HTML
    )
    return UNPIN_CONFIRM

async def unpin_execute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Execute unpin all"""
    query = update.callback_query
    await query.answer()
    
    if query.data == "cancel":
        await query.edit_message_text("❌ Unpin cancelled.")
        return ConversationHandler.END
        
    target = context.user_data.get("unpin_target")
    
    recipients = []
    if target == "all":
        recipients = sm.get_all_users()
    elif target == "active":
        recipients = sm.get_active_users()
        
    await query.edit_message_text(f"🗑️ Unpinning messages for {len(recipients)} users...")
    logger.info(f"🗑️ Starting unpin_all for {len(recipients)} users (Target: {target})")
    
    count = 0
    fail_count = 0
    for user_id in recipients:
        try:
            # unpin_all_chat_messages returns True on success
            success = await context.bot.unpin_all_chat_messages(chat_id=user_id)
            if success:
                count += 1
            else:
                logger.warning(f"   ⚠️ Unpin returned False for {user_id}")
                fail_count += 1
            await asyncio.sleep(0.05)
        except Exception as e:
            logger.warning(f"   ❌ Unpin failed for {user_id}: {e}")
            fail_count += 1
            
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=f"✅ <b>Unpin Complete</b>\n\nCleared pins for {count} users.\nFailed/No Pins: {fail_count}",
        parse_mode=ParseMode.HTML
    )
    return ConversationHandler.END

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

<b>Broadcast & Announcements:</b>
/broadcast - Send message/photo to users
/unpin_all - Clear all pinned messages

<b>Admin Tools:</b>
/gen [days] - Generate subscription code
/test [count] - Test recent alerts

<b>Channel Management:</b>
/add_channel [url] [category] [name] - Add scraper
/remove_channel [id] - Remove scraper
/channels - List all channels

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

<b>Broadcast & Announcements:</b>
/broadcast - Send message/photo to users
/unpin_all - Clear all pinned messages

<b>Admin Tools:</b>
/gen [days] - Generate subscription code
/test [count] - Test recent alerts

<b>Channel Management:</b>
/add_channel [url] [category] [name] - Add scraper
/remove_channel [id] - Remove scraper
/channels - List all channels
"""
    else:
        menu_text = """
📋 <b>Available Commands</b>

/start - Main menu & status
/subscribe - Upgrade to Premium
/billing - Manage subscription
/help - Show this command list

Use the menu buttons for more options!
"""
    
    if update.message:
        await update.message.reply_text(menu_text, parse_mode=ParseMode.HTML)
    elif update.callback_query:
        await update.callback_query.message.reply_text(menu_text, parse_mode=ParseMode.HTML)

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Log the error and send a message to notify the developer/admin"""
    # 1. Log the error
    logger.error("Exception while handling an update:", exc_info=context.error)
    
    # 2. Extract Traceback for Admin
    tb_list = traceback.format_exception(None, context.error, context.error.__traceback__)
    tb_string = "".join(tb_list)

    # 3. Notify User
    if isinstance(update, Update):
        # Stop loading spinner if it's a callback query
        if update.callback_query:
            try:
                await update.callback_query.answer("❌ An error occurred.")
            except: pass

        if update.effective_message:
            text = "❌ <b>An internal error occurred.</b>\nOur team has been notified. Please try again later."
            try:
                await update.effective_message.reply_text(text, parse_mode=ParseMode.HTML)
            except: pass

    # 4. Notify Admins
    if ADMIN_USER_IDS:
        admin_text = f"🚨 <b>ERROR ALERT</b>\n\n"
        admin_text += f"👤 User: {update.effective_user.id if update and update.effective_user else 'None'}\n"
        admin_text += f"💬 Message: <code>{update.effective_message.text if update and update.effective_message else 'None'}</code>\n\n"
        admin_text += f"📦 <b>Traceback:</b>\n<code>{tb_string[-3000:]}</code>" # Send last 3k chars to stay under limit
        
        for admin_id in ADMIN_USER_IDS:
            try:
                await context.bot.send_message(chat_id=int(admin_id), text=admin_text, parse_mode=ParseMode.HTML)
            except Exception as e:
                logger.error(f"Failed to notify admin {admin_id}: {e}")

# 5. RUN BOT FUNCTION
def run_bot():
    """Run bot with professional alert system (Resilient version)"""
    import nest_asyncio
    nest_asyncio.apply()
    
    # Create a fresh event loop for this thread to avoid loop conflicts
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    retry_count = 0
    max_retries = 3
    
    while retry_count < max_retries:
        try:
            if not TELEGRAM_TOKEN:
                logger.error("❌ TELEGRAM_TOKEN not set!")
                return
            
            logger.info("\n" + "=" * 80)
            logger.info(f"🚀 TELEGRAM BOT INITIALIZATION (Attempt {retry_count + 1})")
            logger.info("=" * 80)
            logger.info(f"   Token: {TELEGRAM_TOKEN[:15]}...***{TELEGRAM_TOKEN[-5:]}")
            logger.info(f"   Admin ID: {ADMIN_USER_ID}")
            
            app = Application.builder().token(TELEGRAM_TOKEN).build()
            
            # --- Handler Registration ---
            # Broadcast Handler
            broadcast_handler = ConversationHandler(
                per_message=False,
                entry_points=[CommandHandler("broadcast", broadcast_start)],
                states={
                    BROADCAST_TARGET: [CallbackQueryHandler(broadcast_target)],
                    BROADCAST_MESSAGE: [MessageHandler(filters.TEXT | filters.PHOTO, broadcast_message_input)],
                    BROADCAST_PIN: [CallbackQueryHandler(broadcast_pin_choice)],
                    BROADCAST_CONFIRM: [CallbackQueryHandler(broadcast_confirm)],
                },
                fallbacks=[
                    CommandHandler("cancel", broadcast_cancel),
                    CallbackQueryHandler(broadcast_cancel, pattern="^cancel$")
                ]
            )
            app.add_handler(broadcast_handler)

            # Unpin Handler
            unpin_handler = ConversationHandler(
                per_message=False,
                entry_points=[CommandHandler("unpin_all", unpin_start)],
                states={
                    UNPIN_TARGET: [CallbackQueryHandler(unpin_target_handler)],
                    UNPIN_CONFIRM: [CallbackQueryHandler(unpin_execute)]
                },
                fallbacks=[CallbackQueryHandler(broadcast_cancel, pattern="^cancel$")]
            )
            app.add_handler(unpin_handler)

            app.add_handler(CommandHandler("start", start))
            app.add_handler(CommandHandler("link", handle_link))
            app.add_handler(CommandHandler("unlink", handle_unlink))
            app.add_handler(CommandHandler("gen", gen_code))
            app.add_handler(CommandHandler("add_admin", add_bot_admin))
            app.add_handler(CommandHandler("remove_admin", remove_bot_admin))
            app.add_handler(CommandHandler("test", test_alerts))
            app.add_handler(CommandHandler("add_channel", add_channel_cmd))
            app.add_handler(CommandHandler("remove_channel", remove_channel_cmd))
            app.add_handler(CommandHandler("channels", list_channels_cmd))
            app.add_handler(CommandHandler("subscribe", subscribe))
            app.add_handler(CommandHandler("billing", billing_portal))
            app.add_handler(CommandHandler("help", show_help))
            app.add_handler(CallbackQueryHandler(button_handler))
            app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
            
            app.add_error_handler(error_handler)
            
            if app.job_queue:
                app.job_queue.run_repeating(broadcast_job, interval=POLL_INTERVAL, first=10)
                app.job_queue.run_repeating(expiry_reminder_job, interval=86400, first=30)
                app.job_queue.run_repeating(potential_user_reminder_job, interval=86400, first=60)
                app.job_queue.run_once(setup_bot_commands, when=5)
            
            active_count = len(sm.get_active_users())
            logger.info(f"   📊 Users: {len(sm.users)} total, {active_count} active")
            logger.info("📡 Starting polling loop...")
            
            # Explicitly set stop_signals=[] for threaded operation
            # stop_signals=[] prevents run_polling from trying to listen to OS signals (impossible in thread)
            app.run_polling(allowed_updates=Update.ALL_TYPES, stop_signals=[])
            break # Exit loop if run_polling returns normally (e.g. stop requested)

        except Exception as e:
            retry_count += 1
            logger.error(f"❌ BOT CRASH (Attempt {retry_count}): {e}")
            if "ExtBot is not properly initialized" in str(e) or "NetworkError" in str(e):
                logger.warning("   💡 Potentially transient initialization/network failure. Retrying in 10s...")
                time.sleep(10)
            else:
                logger.error(traceback.format_exc())
                break
    
    if retry_count >= max_retries:
        logger.error("🛑 Bot failed to start after maximum retries.")
