
import requests
from bs4 import BeautifulSoup
import logging
from typing import List, Dict

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

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
        
        # Add basic anti-bot bypass headers
        headers.update({
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
            'Sec-Fetch-User': '?1',
            'Cache-Control': 'max-age=0',
        })
        
        logger.info(f"Fetching {url}...")
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

# Test with a known Amazon URL (UK) - may get blocked but worth a shot, or try Argos/Currys
# Using the product from inspection_output.txt
test_url = "https://www.amazon.co.uk/Pok%C3%A9mon-TCG-Collector-Chest-Gardevoir/dp/B0FP3SBK1S"
# Or a generic one if that fails
# test_url = "https://www.ebay.com/itm/123456789"

print(f"Testing URL: {test_url}")
images = fetch_product_images(test_url)
print("\nResults:")
for i, img in enumerate(images):
    print(f"{i+1}. {img}")

if not images:
    print("No images found (likely blocked or 403)")
