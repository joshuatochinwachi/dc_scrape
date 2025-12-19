import os
import time
import json
import threading
import queue
import base64
import logging
import requests
import asyncio
import nest_asyncio
import subprocess
import hashlib
import re
import random
from datetime import datetime, timedelta
from flask import Flask, render_template_string, jsonify
from flask_socketio import SocketIO
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeout
import supabase_utils
from dotenv import load_dotenv
load_dotenv()

nest_asyncio.apply()

# --- ADVANCED ANTI-DETECTION CONFIGURATION ---
CHANNELS = os.getenv("CHANNELS", "").split(",")
CHANNELS = [c.strip() for c in CHANNELS if c.strip()]

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_ADMIN_ID = os.getenv("TELEGRAM_ADMIN_ID")

SUPABASE_BUCKET = "monitor-data"
UPLOAD_FOLDER = "discord_josh"
STORAGE_STATE_FILE = "storage_state.json"
LAST_MESSAGE_ID_FILE = "last_message_ids.json"
DATA_DIR = "data"

HEADLESS_MODE = os.getenv("HEADLESS", "True").lower() == "true"
DEBUG_ENV = os.getenv("DEBUG", "").lower()
DEBUG_MODE = DEBUG_ENV in ("true", "1", "yes", "on")
os.makedirs(DATA_DIR, exist_ok=True)

# --- EXTREME RANDOMIZATION SETTINGS ---
BASE_POLL_INTERVAL = 60       # Base seconds between checks
POLL_JITTER_MIN = 30          # Min random addition
POLL_JITTER_MAX = 120         # Max random addition (up to 3 min total)

ACTION_DELAY_MIN = 1.2        # Min delay between actions
ACTION_DELAY_MAX = 5.5        # Max delay

READING_TIME_MIN = 4          # Simulate human reading
READING_TIME_MAX = 12         # Up to 12 seconds reading

CHANNEL_DELAY_MIN = 3         # Between channels
CHANNEL_DELAY_MAX = 10

MOUSE_MOVEMENT_CHANCE = 0.45  # 45% chance to move mouse
SCROLL_CHANCE = 0.55          # 55% chance to scroll
IDLE_BREAK_CHANCE = 0.15      # 15% chance for long idle break

IDLE_BREAK_MIN = 180          # 3 min idle
IDLE_BREAK_MAX = 600          # 10 min idle (simulate AFK)

ERROR_THRESHOLD = 5
ALERT_COOLDOWN = 1800

# --- Flask Setup ---
app = Flask(__name__)
logging.getLogger('werkzeug').setLevel(logging.ERROR)
logging.getLogger('apscheduler').setLevel(logging.WARNING)

socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

# --- Global State ---
archiver_state = {
    "status": "STOPPED",
    "logs": [],
    "error_counts": {},
    "last_alert_time": {},
    "last_success_time": {},
    "session_start_time": None,
    "total_checks": 0,
    "idle_breaks_taken": 0,
    "mouse_movements": 0,
    "scrolls_performed": 0
}
stop_event = threading.Event()
input_queue = queue.Queue()
archiver_thread = None
thread_lock = threading.Lock()

if not CHANNELS:
    logging.error("ERROR: CHANNELS environment variable not set.")

HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Discord Stealth Archiver</title>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/socket.io/4.0.1/socket.io.js"></script>
    <style>
        body { font-family: monospace; background: #1a1a1a; color: #00ff00; margin: 0; padding: 20px; }
        .container { display: flex; gap: 20px; }
        .controls { min-width: 300px; }
        .view { flex-grow: 1; text-align: center; }
        img { max-width: 100%; border: 2px solid #00ff00; box-shadow: 0 0 10px rgba(0,255,0,0.3); }
        .log-box { height: 400px; overflow-y: scroll; background: #0a0a0a; border: 1px solid #00ff00; padding: 10px; font-size: 10px; margin-top: 10px; }
        button { padding: 10px; width: 100%; margin-bottom: 8px; cursor: pointer; background: #003300; color: #00ff00; border: 1px solid #00ff00; font-weight: bold; }
        button:hover { background: #005500; box-shadow: 0 0 5px rgba(0,255,0,0.5); }
        .status { padding: 12px; text-align: center; font-weight: bold; margin-bottom: 15px; border: 2px solid; }
        .running { background: #003300; color: #00ff00; border-color: #00ff00; animation: pulse 2s infinite; }
        .stopped { background: #330000; color: #ff3333; border-color: #ff3333; }
        @keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.7; } }
        .stats-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 5px; font-size: 9px; }
        .stat-item { background: #0a0a0a; padding: 5px; border: 1px solid #003300; }
        .stat-label { color: #00aa00; }
        .stat-value { color: #00ff00; font-weight: bold; }
    </style>
</head>
<body>
    <div class="container">
        <div class="controls">
            <div id="status-display" class="status stopped">● OFFLINE</div>
            <button onclick="api('start')">▶ START STEALTH MODE</button>
            <button onclick="api('stop')">■ STOP ARCHIVER</button>
            <button onclick="testStatus()">⟳ REFRESH STATS</button>
            <div id="stats" style="background: #0a0a0a; padding: 10px; margin: 10px 0; font-size: 10px; border: 1px solid #00ff00;"></div>
            <div class="log-box" id="logs"></div>
        </div>
        <div class="view">
            <h3 style="color: #00ff00;">🎭 LIVE STEALTH VIEW</h3>
            <img id="live-stream" src="" alt="Waiting for stream..." />
        </div>
    </div>
    <script>
        var socket = io();
        var img = document.getElementById('live-stream');
        var logs = document.getElementById('logs');
        var stats = document.getElementById('stats');
        var isDragging = false;
        
        socket.on('screenshot', data => img.src = 'data:image/jpeg;base64,' + data);
        socket.on('log', data => {
            var div = document.createElement('div');
            div.innerHTML = `<span style="color:#666">[${new Date().toLocaleTimeString()}]</span> ${data.message}`;
            logs.appendChild(div);
            logs.scrollTop = logs.scrollHeight;
            if (logs.children.length > 100) logs.removeChild(logs.firstChild);
        });
        socket.on('status_update', data => {
            var el = document.getElementById('status-display');
            if (data.status === 'RUNNING') {
                el.textContent = '● STEALTH ACTIVE';
                el.className = 'status running';
            } else {
                el.textContent = '● OFFLINE';
                el.className = 'status stopped';
            }
        });

        function api(cmd) { 
            fetch('/api/' + cmd, { method: 'POST' })
                .then(r => r.json())
                .then(d => console.log(d))
                .catch(e => console.error(e));
        }
        
        function testStatus() {
            fetch('/api/test', { method: 'POST' })
                .then(r => r.json())
                .then(data => {
                    let html = '<div class="stats-grid">';
                    html += `<div class="stat-item"><div class="stat-label">Status</div><div class="stat-value">${data.archiver_status}</div></div>`;
                    html += `<div class="stat-item"><div class="stat-label">Total Checks</div><div class="stat-value">${data.total_checks || 0}</div></div>`;
                    html += `<div class="stat-item"><div class="stat-label">Mouse Moves</div><div class="stat-value">${data.mouse_movements || 0}</div></div>`;
                    html += `<div class="stat-item"><div class="stat-label">Scrolls</div><div class="stat-value">${data.scrolls || 0}</div></div>`;
                    html += `<div class="stat-item"><div class="stat-label">Idle Breaks</div><div class="stat-value">${data.idle_breaks || 0}</div></div>`;
                    html += `<div class="stat-item"><div class="stat-label">Errors</div><div class="stat-value">${Object.keys(data.error_counts || {}).length}</div></div>`;
                    html += '</div><br><b style="color:#00aa00">Last Success:</b><br>';
                    for (let [url, time] of Object.entries(data.last_success || {})) {
                        html += `<div style="font-size:9px">${url.split('/').pop()}: ${new Date(time).toLocaleTimeString()}</div>`;
                    }
                    stats.innerHTML = html;
                })
                .catch(e => stats.innerHTML = '<span style="color:#ff3333">Error: ' + e + '</span>');
        }
        
        function getCoords(e) {
            var rect = img.getBoundingClientRect();
            return {
                x: (e.clientX - rect.left) / rect.width,
                y: (e.clientY - rect.top) / rect.height
            };
        }

        img.onmousedown = function(e) {
            isDragging = true;
            var coords = getCoords(e);
            socket.emit('input', { type: 'mousedown', x: coords.x, y: coords.y });
        };

        img.onmousemove = function(e) {
            if (!isDragging) return;
            var coords = getCoords(e);
            socket.emit('input', { type: 'mousemove', x: coords.x, y: coords.y });
        };

        img.onmouseup = function(e) {
            isDragging = false;
            var coords = getCoords(e);
            socket.emit('input', { type: 'mouseup', x: coords.x, y: coords.y });
        };

        // Keyboard Support
        document.addEventListener('keydown', function(e) {
            // Prevent default browser actions for common keys to avoid scrolling/refreshing
            if(["ArrowUp","ArrowDown","ArrowLeft","ArrowRight","Space"].indexOf(e.code) > -1) {
                e.preventDefault();
            }
            socket.emit('input', { type: 'keypress', key: e.key });
        });
        
        setInterval(testStatus, 10000);
    </script>
</body>
</html>
"""

def log(message):
    timestamp = datetime.now().strftime("%H:%M:%S")
    print(f"[{timestamp}] {message}")
    archiver_state["logs"].append(message)
    if len(archiver_state["logs"]) > 100: archiver_state["logs"].pop(0)
    socketio.emit('log', {'message': message})

def should_send_alert(alert_type):
    last_alert = archiver_state["last_alert_time"].get(alert_type, 0)
    return time.time() - last_alert > ALERT_COOLDOWN

def send_telegram_alert(subject, body, alert_type=None):
    if not TELEGRAM_TOKEN or not TELEGRAM_ADMIN_ID:
        log(f"📧 Alert: {subject} (Telegram not configured)")
        return
    if alert_type and not should_send_alert(alert_type):
        return
    
    text = f"🎭 <b>STEALTH ALERT: {subject}</b>\n\n{body}"
    try:
        response = requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            json={"chat_id": TELEGRAM_ADMIN_ID, "text": text, "parse_mode": "HTML"},
            timeout=10
        )
        if response.status_code == 200:
            log(f"✅ Alert sent: {subject}")
            if alert_type:
                archiver_state["last_alert_time"][alert_type] = time.time()
    except Exception as e:
        log(f"❌ Alert error: {str(e)}")

def set_status(status):
    archiver_state["status"] = status
    socketio.emit('status_update', {'status': status})

def clean_text(text):
    if not text: return ""
    text = str(text).replace('\x00', '')
    return ' '.join(text.split()).encode('ascii', 'ignore').decode('ascii')

# --- ADVANCED RANDOMIZATION FUNCTIONS ---
async def smart_delay(base_min, base_max, variance=0.3):
    """Intelligent delay with Gaussian distribution for more natural randomness"""
    mid = (base_min + base_max) / 2
    sigma = (base_max - base_min) * variance
    delay = random.gauss(mid, sigma)
    delay = max(base_min, min(base_max, delay))
    await asyncio.sleep(delay)

async def random_typing_delay():
    """Simulate realistic typing delays (between keypresses)"""
    delay = random.gauss(0.15, 0.05)
    delay = max(0.05, min(0.4, delay))
    await asyncio.sleep(delay)

async def simulate_human_pause():
    """Random pause like a human thinking or getting distracted"""
    if random.random() < 0.3:  # 30% chance
        pause_duration = random.uniform(2, 8)
        await asyncio.sleep(pause_duration)

async def advanced_mouse_movement(page):
    """Ultra-realistic mouse movement with curves and acceleration"""
    try:
        viewport = page.viewport_size
        if not viewport:
            return
        
        archiver_state["mouse_movements"] += 1
        
        # Start from current position (random)
        start_x = random.randint(50, viewport['width'] - 50)
        start_y = random.randint(50, viewport['height'] - 50)
        
        # Move to multiple points (2-5 moves)
        num_moves = random.randint(2, 5)
        
        for _ in range(num_moves):
            target_x = random.randint(100, viewport['width'] - 100)
            target_y = random.randint(100, viewport['height'] - 100)
            
            # Calculate distance for speed adjustment
            distance = ((target_x - start_x)**2 + (target_y - start_y)**2)**0.5
            steps = max(5, int(distance / 50))  # More steps for longer distances
            
            # Bezier curve simulation for natural movement
            for i in range(steps):
                t = i / steps
                # Add randomness to path
                noise_x = random.uniform(-15, 15)
                noise_y = random.uniform(-15, 15)
                
                current_x = start_x + (target_x - start_x) * t + noise_x
                current_y = start_y + (target_y - start_y) * t + noise_y
                
                await page.mouse.move(current_x, current_y)
                # Variable speed (faster in middle, slower at start/end)
                speed_factor = 1 - abs(t - 0.5) * 0.5
                await asyncio.sleep(0.01 / speed_factor)
            
            start_x, start_y = target_x, target_y
            await smart_delay(0.2, 0.6)
            
    except Exception as e:
        log(f"⚠️ Mouse movement error: {e}")

async def realistic_scroll_behavior(page):
    """Advanced scrolling with momentum and natural deceleration"""
    try:
        archiver_state["scrolls_performed"] += 1
        
        # Multiple scroll actions in sequence
        num_scrolls = random.randint(2, 5)
        
        for _ in range(num_scrolls):
            # Scroll direction weighted (70% down, 30% up - natural reading behavior)
            scroll_down = random.random() < 0.7
            
            if scroll_down:
                base_scroll = random.randint(150, 600)
            else:
                base_scroll = -random.randint(100, 400)
            
            # Simulate momentum with multiple small scrolls
            momentum_steps = random.randint(3, 8)
            for step in range(momentum_steps):
                # Deceleration effect
                step_scroll = base_scroll * (1 - step / momentum_steps) / momentum_steps
                await page.evaluate(f"window.scrollBy(0, {step_scroll})")
                await asyncio.sleep(random.uniform(0.02, 0.08))
            
            # Pause between scroll actions
            await smart_delay(0.4, 1.2)
            
            # Sometimes scroll back up a bit (like re-reading)
            if random.random() < 0.25:
                await page.evaluate(f"window.scrollBy(0, {random.randint(-100, -50)})")
                await smart_delay(0.3, 0.7)
                
    except Exception as e:
        log(f"⚠️ Scroll error: {e}")

async def simulate_reading_pattern(page):
    """Simulate eye movement and reading time based on content length"""
    try:
        # Get approximate content height
        content_height = await page.evaluate("document.body.scrollHeight")
        viewport_height = page.viewport_size['height']
        
        # More content = more reading time
        base_read_time = READING_TIME_MIN
        extra_time = (content_height / viewport_height) * 2
        total_read_time = min(base_read_time + extra_time, READING_TIME_MAX)
        
        # Add Gaussian randomness
        read_time = random.gauss(total_read_time, total_read_time * 0.2)
        read_time = max(3, min(15, read_time))
        
        await asyncio.sleep(read_time)
        
    except:
        await smart_delay(READING_TIME_MIN, READING_TIME_MAX)

async def take_idle_break():
    """Simulate user going AFK (away from keyboard)"""
    archiver_state["idle_breaks_taken"] += 1
    idle_duration = random.randint(IDLE_BREAK_MIN, IDLE_BREAK_MAX)
    log(f"💤 Taking idle break ({idle_duration//60}m {idle_duration%60}s) - simulating AFK...")
    
    # Break it into chunks so we can still stop if needed
    for _ in range(idle_duration):
        if stop_event.is_set():
            break
        await asyncio.sleep(1)
    
    log(f"🔄 Returning from idle break")

def get_realistic_user_agent():
    """Return weighted realistic user agents (favor common ones)"""
    agents_weighted = [
        # Windows Chrome (most common - 60%)
        ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36", 30),
        ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36", 30),
        # Mac Chrome (20%)
        ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36", 20),
        # Firefox (15%)
        ("Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:122.0) Gecko/20100101 Firefox/122.0", 10),
        ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:122.0) Gecko/20100101 Firefox/122.0", 5),
        # Edge (5%)
        ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0", 5),
    ]
    
    agents = []
    for agent, weight in agents_weighted:
        agents.extend([agent] * weight)
    
    return random.choice(agents)

def get_next_check_interval():
    """Gaussian distribution for check intervals - more natural clustering"""
    mid = BASE_POLL_INTERVAL + (POLL_JITTER_MIN + POLL_JITTER_MAX) / 2
    sigma = (POLL_JITTER_MAX - POLL_JITTER_MIN) / 3
    interval = random.gauss(mid, sigma)
    return max(BASE_POLL_INTERVAL + POLL_JITTER_MIN, 
               min(BASE_POLL_INTERVAL + POLL_JITTER_MAX, interval))

async def save_message_html_for_inspection(message_element, message_id):
    """Save raw HTML for debugging"""
    try:
        html = await message_element.inner_html()
        filename = f"data/message_inspection_{message_id}.html"
        os.makedirs("data", exist_ok=True)
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(f"<!-- Message ID: {message_id} -->\n")
            f.write(f"<!-- Timestamp: {datetime.utcnow().isoformat()} -->\n")
            f.write(html)
        log(f"   💾 HTML saved: {filename}")
        return filename
    except Exception as e:
        log(f"   ⚠️ HTML save error: {e}")
        return None

def track_channel_error(channel_url, error_msg):
    archiver_state["error_counts"][channel_url] = archiver_state["error_counts"].get(channel_url, 0) + 1
    if archiver_state["error_counts"][channel_url] >= ERROR_THRESHOLD:
        alert_type = f"channel_error_{channel_url}"
        send_telegram_alert(f"Channel Access Failed", f"Channel: {channel_url}\nError: {error_msg}", alert_type)

def track_channel_success(channel_url):
    archiver_state["error_counts"][channel_url] = 0
    archiver_state["last_success_time"][channel_url] = datetime.utcnow().isoformat()

def generate_content_hash(content_dict):
    content_str = json.dumps(content_dict, sort_keys=True)
    return hashlib.md5(content_str.encode()).hexdigest()

def extract_markdown_links(text):
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

def ensure_browsers_installed():
    log("🔧 Checking Playwright browsers...")
    try:
        subprocess.run(["playwright", "install", "chromium"], check=True, capture_output=True)
        log("✅ Browsers ready")
    except Exception as e:
        log(f"⚠️ Browser install warning: {e}")

async def extract_embed_data(message_element):
    """Extract embed data from Discord message"""
    embed_data = {
        "title": None,
        "description": None,
        "fields": [],
        "images": [],
        "thumbnail": None,
        "color": None,
        "author": None,
        "footer": None,
        "timestamp": None,
        "links": []
    }
    
    try:
        embed = message_element.locator('article[class*="embedFull"]').first
        if await embed.count() == 0:
            embed = message_element.locator('article[class*="embed"]').first
        if await embed.count() == 0:
            return None
        
        try:
            color_style = await embed.get_attribute('style')
            if color_style and 'border-left-color' in color_style:
                embed_data["color"] = color_style
        except: pass
        
        try:
            author_elem = embed.locator('[class*="embedAuthor"] a, [class*="embedAuthor"] span, [class*="embedAuthorName"]').first
            if await author_elem.count() > 0:
                author_name = await author_elem.inner_text()
                author_url = await author_elem.get_attribute('href')
                embed_data["author"] = {"name": clean_text(author_name), "url": author_url}
                if author_url and author_url not in [l.get("url") for l in embed_data["links"]]:
                    embed_data["links"].append({"type": "author", "text": clean_text(author_name), "url": author_url})
        except: pass
        
        try:
            title_elem = embed.locator('[class*="embedTitle"] a, [class*="embedTitle"]').first
            if await title_elem.count() > 0:
                title_text = await title_elem.inner_text()
                title_url = await title_elem.get_attribute('href')
                embed_data["title"] = clean_text(title_text)
                if title_url and title_url not in [l.get("url") for l in embed_data["links"]]:
                    embed_data["links"].append({"type": "title", "text": embed_data["title"], "url": title_url})
        except: pass
        
        try:
            field_containers = embed.locator('[class*="embedField"]')
            field_count = await field_containers.count()
            
            for i in range(field_count):
                field = field_containers.nth(i)
                field_name_elem = field.locator('[class*="embedFieldName"]').first
                field_name = ""
                if await field_name_elem.count() > 0:
                    field_name = clean_text(await field_name_elem.inner_text())
                
                field_value = ""
                field_value_elem = field.locator('[class*="embedFieldValue"]').first
                if await field_value_elem.count() > 0:
                    # Try to preserve links as Markdown [Text](URL)
                    # We execute JS to replace <a> tags with markdown text
                    try:
                        field_value = await field_value_elem.evaluate("""element => {
                            let clone = element.cloneNode(true);
                            clone.querySelectorAll('a').forEach(a => {
                                if (a.href) {
                                    a.textContent = `[${a.textContent}](${a.href})`;
                                }
                            });
                            return clone.innerText;
                        }""")
                    except:
                        field_value = await field_value_elem.inner_text()
                    
                    field_value = clean_text(field_value)
                
                if field_name or field_value:
                    embed_data["fields"].append({"name": field_name, "value": field_value})
                    
                    # (Optional: we still keep the separate links list for fallback/buttons if needed)
                    try:
                        value_links = field_value_elem.locator('a[href]')
                        link_count = await value_links.count()
                        for j in range(link_count):
                            link_elem = value_links.nth(j)
                            href = await link_elem.get_attribute('href')
                            text = await link_elem.inner_text()
                            if href and href not in [l.get("url") for l in embed_data["links"]]:
                                embed_data["links"].append({
                                    "field": field_name,
                                    "text": clean_text(text),
                                    "url": href
                                })
                    except: pass
        except: pass
        
        try:
            thumb_elem = embed.locator('img[class*="embedThumbnail"]').first
            if await thumb_elem.count() == 0:
                thumb_elem = embed.locator('[class*="embedThumbnail"] img').first
            
            if await thumb_elem.count() > 0:
                thumb_src = await thumb_elem.get_attribute('src')
                if thumb_src:
                    embed_data["images"].append(thumb_src)
        except: pass
        
        try:
            footer_elem = embed.locator('[class*="embedFooter"]').first
            if await footer_elem.count() > 0:
                embed_data["footer"] = clean_text(await footer_elem.inner_text())
        except: pass
        
        return embed_data if any([embed_data["title"], embed_data["fields"], embed_data["links"]]) else None
    except Exception as e:
        log(f"   ⚠️ Embed error: {e}")
        return None

async def extract_message_author(message_element):
    """Extract author info with robust fallbacks"""
    try:
        # Priority 1: ID-based (Most specific, confirmed in inspection)
        author_elem = message_element.locator('[id^="message-username-"]').first
        
        # Priority 2: Standard Class-based
        if await author_elem.count() == 0:
            author_elem = message_element.locator('span[class*="username"]').first
            
        # Priority 3: Header-based
        if await author_elem.count() == 0:
            author_elem = message_element.locator('h3 span').first

        if await author_elem.count() > 0:
            # Get text from the first visible part (often the username span inside the wrapper)
            author_name = await author_elem.inner_text()
            
            is_bot = await message_element.locator('[class*="botTag"]').count() > 0
            
            # Avatar fallback
            avatar_elem = message_element.locator('img[class*="avatar"]').first
            avatar_url = None
            if await avatar_elem.count() > 0:
                avatar_url = await avatar_elem.get_attribute('src')
                
            return {"name": clean_text(author_name), "is_bot": is_bot, "avatar": avatar_url}
    except: pass
    return {"name": "Unknown", "is_bot": False, "avatar": None}

async def wait_for_messages_to_load(page):
    SELECTORS = [
        'li[id^="chat-messages-"]',
        '[class*="message-"][class*="cozy"]',
        '[id^="message-content-"]',
        'div[class*="messageContent-"]',
        '[data-list-item-id^="chat-messages"]',
    ]
    
    log("   🔍 Loading messages...")
    try:
        await page.wait_for_selector('main[class*="chatContent"], div[class*="chat-"]', timeout=5000)
    except: pass
    
    for attempt in range(3):
        await page.evaluate("window.scrollTo(0, 0)")
        await smart_delay(0.4, 1.0)
        for selector in SELECTORS:
            try:
                elements = page.locator(selector)
                if await elements.count() > 0:
                    return selector, elements
            except: continue
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await smart_delay(0.4, 1.0)
    
    return None, None

async def detect_account_picker(page):
    selectors = [
        'button[class*="userButton"]',
        '[class*="accountPicker"]',
        '[class*="SelectAccount"]',
        'div:has-text("Select Account")',
        'div:has-text("Which account?")',
    ]
    for selector in selectors:
        try:
            if await page.locator(selector).count() > 0:
                return True
        except: pass
    return False

async def async_archiver_logic():
    """MAXIMUM STEALTH Discord scraper"""
    log("🎭 ULTRA-STEALTH MODE ACTIVATED")
    log(f"⚙️ Config: Base={BASE_POLL_INTERVAL}s + Jitter={POLL_JITTER_MIN}-{POLL_JITTER_MAX}s")
    log(f"🎲 Random breaks enabled: {IDLE_BREAK_CHANCE*100}% chance")
    
    archiver_state["session_start_time"] = datetime.utcnow().isoformat()
    archiver_state["total_checks"] = 0
    archiver_state["idle_breaks_taken"] = 0
    archiver_state["mouse_movements"] = 0
    archiver_state["scrolls_performed"] = 0
    
    if DEBUG_MODE:
        log("🛠 DEBUG: HTML capture enabled")
    
    state_path = os.path.join(DATA_DIR, STORAGE_STATE_FILE)
    remote_state_path = f"{UPLOAD_FOLDER}/{STORAGE_STATE_FILE}"
    last_ids_path = os.path.join(DATA_DIR, LAST_MESSAGE_ID_FILE)
    
    try:
        data = supabase_utils.download_file(state_path, remote_state_path, SUPABASE_BUCKET)
        if data: log("✅ Session restored")
    except: pass

    last_ids = {}
    if os.path.exists(last_ids_path):
        try:
            with open(last_ids_path, 'r') as f: last_ids = json.load(f)
        except: pass

    async with async_playwright() as p:
        user_agent = get_realistic_user_agent()
        log(f"🎭 UA: {user_agent[:60]}...")
        
        browser = await p.chromium.launch(
            headless=HEADLESS_MODE,
            args=[
                '--disable-blink-features=AutomationControlled',
                '--disable-dev-shm-usage',
                '--no-sandbox',
                '--disable-web-security',
                '--disable-features=IsolateOrigins,site-per-process',
                '--disable-site-isolation-trials',
                f'--user-agent={user_agent}'
            ]
        )
        
        # Randomize viewport (common resolutions)
        viewports = [
            {'width': 1920, 'height': 1080},
            {'width': 1366, 'height': 768},
            {'width': 1536, 'height': 864},
            {'width': 1440, 'height': 900},
            {'width': 2560, 'height': 1440}
        ]
        viewport = random.choice(viewports)
        
        context = await browser.new_context(
            viewport=viewport,
            user_agent=user_agent,
            storage_state=state_path if os.path.exists(state_path) else None,
            locale='en-US',
            timezone_id='America/New_York',
            permissions=['notifications'],
            color_scheme='dark' if random.random() > 0.3 else 'light',
            device_scale_factor=random.choice([1, 1.25, 1.5, 2])
        )
        
        # Maximum anti-detection scripts
        await context.add_init_script("""
            // Remove webdriver flag
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });
            
            // Randomize plugins
            Object.defineProperty(navigator, 'plugins', {
                get: () => {
                    const plugins = [
                        {name: 'Chrome PDF Plugin', filename: 'internal-pdf-viewer'},
                        {name: 'Chrome PDF Viewer', filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai'},
                        {name: 'Native Client', filename: 'internal-nacl-plugin'}
                    ];
                    return plugins;
                }
            });
            
            // Override chrome object
            window.chrome = {
                runtime: {},
                loadTimes: function() {},
                csi: function() {},
                app: {}
            };
            
            // Add realistic timing
            const originalQuery = window.navigator.permissions.query;
            window.navigator.permissions.query = (parameters) => (
                parameters.name === 'notifications' ?
                    Promise.resolve({ state: Notification.permission }) :
                    originalQuery(parameters)
            );
            
            // Remove automation indicators
            delete navigator.__proto__.webdriver;
        """)
        
        page = await context.new_page()
        set_status("RUNNING")

        while not stop_event.is_set():
            try:
                # Random idle break check
                if random.random() < IDLE_BREAK_CHANCE:
                    await take_idle_break()
                    if stop_event.is_set(): break
                
                # Login Logic
                if "login" in page.url or "discord.com/channels" not in page.url:
                    log("🔐 Login required...")
                    try: 
                        await page.goto("https://discord.com/login", timeout=10000)
                        await smart_delay(2, 5)
                    except: pass
                    
                    account_picker_detected = await detect_account_picker(page)
                    if account_picker_detected:
                        log("👤 Account picker detected")
                        send_telegram_alert("Account Picker", "Manual selection needed", "warning")
                    
                    wait_cycles = 0
                    while wait_cycles < 120 and not stop_event.is_set():
                        try:
                            scr = await page.screenshot(quality=40, type='jpeg')
                            socketio.emit('screenshot', base64.b64encode(scr).decode('utf-8'))
                        except: pass
                        
                        try:
                            while not input_queue.empty():
                                act = input_queue.get_nowait()
                                if act['type'] == 'click':
                                    vp = page.viewport_size
                                    # Realistic click offset
                                    x_jitter = random.gauss(0, 3)
                                    y_jitter = random.gauss(0, 3)
                                    x = (act['x'] * vp['width']) + x_jitter
                                    y = (act['y'] * vp['height']) + y_jitter
                                    
                                    # Simulate human click (press + delay + release)
                                    await page.mouse.move(x, y)
                                    await asyncio.sleep(random.uniform(0.05, 0.15))
                                    await page.mouse.down()
                                    await asyncio.sleep(random.uniform(0.05, 0.12))
                                    await page.mouse.up()
                                elif act['type'] == 'mousedown':
                                    vp = page.viewport_size
                                    await page.mouse.move(act['x'] * vp['width'], act['y'] * vp['height'])
                                    await page.mouse.down()
                                elif act['type'] == 'mousemove':
                                    vp = page.viewport_size
                                    await page.mouse.move(act['x'] * vp['width'], act['y'] * vp['height'])
                                elif act['type'] == 'mouseup':
                                    vp = page.viewport_size
                                    await page.mouse.move(act['x'] * vp['width'], act['y'] * vp['height'])
                                    await page.mouse.up()
                                elif act['type'] == 'keypress':
                                    await page.keyboard.press(act['key'])
                        except: pass
                        
                        if "discord.com/channels" in page.url and "/login" not in page.url:
                            await context.storage_state(path=state_path)
                            supabase_utils.upload_file(state_path, SUPABASE_BUCKET, remote_state_path, debug=False)
                            log("✅ Login success!")
                            await smart_delay(3, 7)
                            break
                        
                        await asyncio.sleep(5)
                        wait_cycles += 1
                        if wait_cycles % 10 == 0: log(f"⏳ {wait_cycles*5}s elapsed...")

                # Shuffle channels for unpredictability
                channels_to_check = CHANNELS.copy()
                random.shuffle(channels_to_check)
                
                # Randomly skip some channels sometimes (10% chance per channel)
                if random.random() < 0.3:
                    skip_count = random.randint(0, min(2, len(channels_to_check)))
                    if skip_count > 0:
                        channels_to_check = channels_to_check[skip_count:]
                        log(f"🎲 Randomly skipping {skip_count} channel(s) this cycle")
                
                for channel_url in channels_to_check:
                    if stop_event.is_set(): break
                    
                    archiver_state["total_checks"] += 1
                    log(f"📂 [{archiver_state['total_checks']}] {channel_url.split('/')[-1]}")
                    
                    try:
                        await page.goto(channel_url, timeout=30000)
                        await smart_delay(2, 5)
                        
                        # Human behavior simulation
                        if random.random() < MOUSE_MOVEMENT_CHANCE:
                            await advanced_mouse_movement(page)
                        
                        if random.random() < SCROLL_CHANCE:
                            await realistic_scroll_behavior(page)
                        
                        # Random pause (thinking/reading)
                        await simulate_human_pause()
                        
                        try:
                            scr = await page.screenshot(quality=40, type='jpeg')
                            socketio.emit('screenshot', base64.b64encode(scr).decode('utf-8'))
                        except: pass
                        
                        selector, messages = await wait_for_messages_to_load(page)
                        if not messages:
                            log("   ⚠️ No messages")
                            track_channel_error(channel_url, "No messages")
                            await smart_delay(CHANNEL_DELAY_MIN, CHANNEL_DELAY_MAX)
                            continue
                        
                        # Simulate reading
                        await simulate_reading_pattern(page)
                        
                        count = await messages.count()
                        batch = []
                        current_ids = last_ids.get(channel_url, [])
                        
                        debug_saved = False
                        for i in range(max(0, count - 10), count):
                            msg = messages.nth(i)
                            raw_id = await msg.get_attribute('id') or await msg.get_attribute('data-list-item-id')
                            if not raw_id: continue
                            
                            msg_id = raw_id.replace('chat-messages-', '').replace('message-', '')
                            if msg_id in current_ids: continue
                            
                            if DEBUG_MODE and not debug_saved:
                                await save_message_html_for_inspection(msg, msg_id)
                                debug_saved = True
                            
                            author_data = await extract_message_author(msg)
                            embed_data = await extract_embed_data(msg)
                            
                            content_loc = msg.locator('[id^="message-content-"]').first
                            plain_content = await content_loc.inner_text() if await content_loc.count() else ""
                            
                            message_data = {
                                "id": int(msg_id) if msg_id.isdigit() else abs(hash(msg_id)) % (10 ** 15),
                                "channel_id": channel_url.split('/')[-1],
                                "content": clean_text(plain_content),
                                "scraped_at": datetime.utcnow().isoformat(),
                                "raw_data": {
                                    "author": author_data,
                                    "channel_url": channel_url,
                                    "embed": embed_data,
                                    "has_embed": embed_data is not None
                                }
                            }
                            
                            hash_content = {
                                "content": plain_content,
                                "embed_title": embed_data.get("title") if embed_data else None,
                                "embed_desc": embed_data.get("description") if embed_data else None
                            }
                            message_data["raw_data"]["content_hash"] = generate_content_hash(hash_content)
                            
                            batch.append(message_data)
                            current_ids.append(msg_id)
                            
                            if embed_data:
                                title = embed_data.get('title', 'No title')[:40]
                                log(f"   ✅ {title}...")
                                if embed_data.get('links'):
                                    log(f"      🔗 {len(embed_data['links'])} link(s)")
                            else:
                                log(f"   📝 {plain_content[:40]}...")
                            
                            # Random micro-delay between messages
                            await asyncio.sleep(random.gauss(0.2, 0.1))

                        if batch:
                            log(f"   ⬆️ {len(batch)} new message(s)")
                            supabase_utils.insert_discord_messages(batch)
                            last_ids[channel_url] = current_ids[-200:]
                            with open(last_ids_path, 'w') as f: json.dump(last_ids, f)
                        
                        track_channel_success(channel_url)
                        await smart_delay(CHANNEL_DELAY_MIN, CHANNEL_DELAY_MAX)

                    except Exception as e:
                        log(f"   ⚠️ {str(e)[:80]}")
                        track_channel_error(channel_url, str(e))
                        await smart_delay(4, 8)

                # Randomized next check interval
                next_check = get_next_check_interval()
                log(f"💤 Next: {int(next_check)}s (Stats: {archiver_state['total_checks']} checks, {archiver_state['mouse_movements']} moves, {archiver_state['scrolls_performed']} scrolls)")
                
                for _ in range(int(next_check)):
                    if stop_event.is_set(): break
                    await asyncio.sleep(1)

            except Exception as e:
                log(f"💥 Critical: {str(e)[:100]}")
                await asyncio.sleep(15)
        
        if context:
            await context.close()
        if browser:
            await browser.close()
        log("✅ Session ended")
    
    set_status("STOPPED")

def run_archiver_thread_wrapper():
    nest_asyncio.apply()
    ensure_browsers_installed()
    
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(async_archiver_logic())
        loop.close()
    except Exception as e:
        log(f"FATAL: {e}")
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.run_coroutine_threadsafe(async_archiver_logic(), loop)
        except:
            pass

@app.route('/')
def index(): return render_template_string(HTML_TEMPLATE)

@app.route('/api/start', methods=['POST'])
def start_worker():
    global archiver_thread
    with thread_lock:
        if archiver_thread and archiver_thread.is_alive():
            return jsonify({"status": "already_running"}), 409
        stop_event.clear()
        archiver_thread = threading.Thread(target=run_archiver_thread_wrapper, daemon=True)
        archiver_thread.start()
    return jsonify({"status": "started"})

@app.route('/api/stop', methods=['POST'])
def stop_worker():
    stop_event.set()
    return jsonify({"status": "stopping"})

@app.route('/api/test', methods=['POST'])
def test_channel():
    if not archiver_thread or not archiver_thread.is_alive():
        return jsonify({"status": "error", "message": "Archiver not running"}), 400
    return jsonify({
        "status": "ok",
        "error_counts": archiver_state["error_counts"],
        "archiver_status": archiver_state["status"],
        "last_success": archiver_state["last_success_time"],
        "total_checks": archiver_state["total_checks"],
        "session_start": archiver_state["session_start_time"],
        "mouse_movements": archiver_state["mouse_movements"],
        "scrolls": archiver_state["scrolls_performed"],
        "idle_breaks": archiver_state["idle_breaks_taken"]
    })

@app.route('/health')
def health(): return jsonify({"status": "ok"})

@socketio.on('input')
def handle_input(data): input_queue.put(data)


if __name__ == '__main__':
    import telegram_bot
    if os.getenv("TELEGRAM_TOKEN"):
        t_bot = threading.Thread(target=telegram_bot.run_bot, daemon=True)
        t_bot.start()
    socketio.run(app, host='0.0.0.0', port=5000, debug=False, allow_unsafe_werkzeug=True)