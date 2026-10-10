import os
import time
import json
import threading
import queue
import base64
import logging
import traceback
import requests
import asyncio
import nest_asyncio
import subprocess
import hashlib
import re
import random
import math
from datetime import datetime, timedelta
from flask import Flask, render_template_string, jsonify, request
from flask_socketio import SocketIO
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeout
import supabase_utils
import stripe
from dotenv import load_dotenv
load_dotenv()

# --- STRIPE CONFIG ---
stripe.api_key = os.getenv("STRIPE_SECRET_KEY")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET")

nest_asyncio.apply()

# --- ADVANCED ANTI-DETECTION CONFIGURATION ---
# CHANNELS = os.getenv("CHANNELS", "").split(",")
# CHANNELS = [c.strip() for c in CHANNELS if c.strip()]
from telegram_bot import cm # Import ChannelManager

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_ADMIN_ID = os.getenv("TELEGRAM_ADMIN_ID")

SUPABASE_BUCKET = "monitor-data"
UPLOAD_FOLDER = "discord_josh"
STORAGE_STATE_FILE = "storage_state.json"
LAST_MESSAGE_ID_FILE = "last_message_ids.json"
CHANNEL_METRICS_FILE = "channel_metrics.json"
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

LONG_SLEEP_MIN = 180          # 3 min sleep
LONG_SLEEP_MAX = 1200         # 20 min sleep
LONG_SLEEP_CHANCE = 0.05      # 5% chance after batch

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
    "scrolls_performed": 0,
    "idle_breaks_taken": 0,
    "mouse_movements": 0,
    "scrolls_performed": 0,
    "checks_since_idle": 0,  # Explicit counter for forced breaks
    "long_sleeps_taken": 0,
    "channel_metrics": {}  # {url: {'msg_count': 0, 'last_check': 0}}
}
stop_event = threading.Event()
input_queue = queue.Queue()
archiver_thread = None
thread_lock = threading.Lock()

if not cm.channels:
    logging.error("ERROR: No channels configured in ChannelManager.")

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

def send_telegram_alert(subject, body, alert_type=None, image_bytes=None):
    if not TELEGRAM_TOKEN or not TELEGRAM_ADMIN_ID:
        log(f"📧 Alert: {subject} (Telegram not configured)")
        return
    if alert_type and not should_send_alert(alert_type):
        return
    
    text = f"🎭 <b>STEALTH ALERT: {subject}</b>\n\n{body}"
    admin_ids = [id.strip() for id in TELEGRAM_ADMIN_ID.split(',') if id.strip()]
    
    for admin_id in admin_ids:
        try:
            if image_bytes:
                # Send as photo
                url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto"
                files = {'photo': ('screenshot.jpg', image_bytes, 'image/jpeg')}
                data = {'chat_id': admin_id, 'caption': text[:1024], 'parse_mode': 'HTML'}
                response = requests.post(url, data=data, files=files, timeout=20)
            else:
                # Send as text
                url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
                response = requests.post(
                    url,
                    json={"chat_id": admin_id, "text": text, "parse_mode": "HTML"},
                    timeout=10
                )
            
            if response.status_code == 200:
                log(f"✅ Alert sent to {admin_id}: {subject}")
            else:
                log(f"❌ Alert failed for {admin_id}: {response.status_code} {response.text}")
        except Exception as e:
            log(f"❌ Alert error for {admin_id}: {str(e)}")

    if alert_type:
        archiver_state["last_alert_time"][alert_type] = time.time()


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

async def take_long_sleep():
    """Simulate user logging off or sleeping (1-3 hours)"""
    archiver_state["long_sleeps_taken"] += 1
    sleep_duration = random.randint(LONG_SLEEP_MIN, LONG_SLEEP_MAX)
    
    log(f"😴 Taking LONG SLEEP ({sleep_duration//3600}h {(sleep_duration%3600)//60}m) - Simulating downtime...")
    set_status("SLEEPING")
    
    # Break into chunks
    for _ in range(sleep_duration):
        if stop_event.is_set(): break
        await asyncio.sleep(1)
        
    set_status("RUNNING")
    log(f"⏰ Waking up from long sleep")

async def handle_manual_inputs(page):
    """Process any manual inputs (clicks, typing) from the dashboard queue"""
    try:
        while not input_queue.empty():
            act = input_queue.get_nowait()
            vp = page.viewport_size
            if not vp: continue
            
            if act['type'] == 'mousedown':
                await page.mouse.move(act['x'] * vp['width'], act['y'] * vp['height'])
                await page.mouse.down()
            elif act['type'] == 'mousemove':
                await page.mouse.move(act['x'] * vp['width'], act['y'] * vp['height'])
            elif act['type'] == 'mouseup':
                await page.mouse.move(act['x'] * vp['width'], act['y'] * vp['height'])
                await page.mouse.up()
            elif act['type'] == 'keypress':
                await page.keyboard.press(act['key'])
            elif act['type'] == 'click':
                await page.mouse.click(act['x'] * vp['width'], act['y'] * vp['height'])
    except Exception:
        pass

async def dismiss_discord_modals(page):
    """Dismiss any Discord overlay modals with force-click and retries"""
    await asyncio.sleep(1.5) # Give modal time to appear
    try:
        dismiss_selectors = [
            'button[aria-label="Close"]',
            'button[aria-label="Dismiss"]',
            '[class*="closeButton"]',
            '[class*="layerContainer"] button[aria-label="Close"]',
            '[class*="premiumPromo"] button',
            '[class*="nitroModal"] button',
            'button:has-text("Maybe later")',
            'button:has-text("Not now")'
        ]
        
        for selector in dismiss_selectors:
            try:
                btn = page.locator(selector).first
                if await btn.count() > 0:
                    log(f"   🚫 Attempting to dismiss modal: {selector}")
                    # Use force=True because modals often have "un-clickable" transparent layers
                    await btn.click(force=True, timeout=2000)
                    log(f"   ✅ Modal dismissed")
                    await asyncio.sleep(0.5)
            except:
                continue
        
        await page.keyboard.press('Escape')
    except Exception:
        pass

async def navigate_to_channel(page, channel_url):
    """
    Navigate to a channel by clicking (human-like) or fallback to direct URL.
    URL format: https://discord.com/channels/{server_id}/{channel_id}
    """
    try:
        parts = channel_url.rstrip('/').split('/')
        if len(parts) < 2:
            log(f"   ⚠️ Invalid URL format, using direct nav")
            await page.goto(channel_url, timeout=30000)
            return
            
        channel_id = parts[-1]
        server_id = parts[-2]
        
        log(f"   🖱️ Click Nav: Server={server_id}, Channel={channel_id}")
        
        # Check if we're already on the right server
        current_url = page.url
        current_server = current_url.split('/channels/')[-1].split('/')[0] if '/channels/' in current_url else None
        
        # --- STEP 1: Click Server Icon (if needed) ---
        if current_server != server_id:
            log(f"   🖱️ Server switch detected: {current_server} -> {server_id}")
            log(f"   🖱️ Switching to server...")
            server_selectors = [
                f'[data-list-item-id="guildsnav___{server_id}"]',
                f'a[href*="/channels/{server_id}"]',
                f'div[data-dnd-name] a[href*="/{server_id}"]',
            ]
            server_clicked = False
            
            # FAR LEFT SCROLLER (Servers)
            server_scroller = page.locator('nav[aria-label*="Servers"], [class*="guilds"], [class*="listItem"]').first
            
            for attempt in range(4):  # Try finding and scrolling server list
                for sel in server_selectors:
                    try:
                        server_icon = page.locator(sel).first
                        if await server_icon.count() > 0:
                            # Ensure it's in view
                            await server_icon.scroll_into_view_if_needed(timeout=2000)
                            await asyncio.sleep(0.3)
                            
                            if await server_icon.is_visible():
                                await server_icon.hover()
                                await asyncio.sleep(random.uniform(0.2, 0.5))
                                await server_icon.click()
                                log(f"   ✅ Server icon clicked")
                                await asyncio.sleep(random.uniform(2.0, 4.0)) # Wait longer for server switch
                                server_clicked = True
                                break
                    except: continue
                
                if server_clicked: break
                    
                # Scroll the server list specifically
                try:
                    if await server_scroller.count() > 0:
                        log(f"   📜 Scrolling Server list (Attempt {attempt+1})...")
                        await server_scroller.evaluate("el => el.scrollBy(0, 300)")
                        await asyncio.sleep(0.6)
                except: break
            
            if not server_clicked:
                log(f"   ⚠️ Server icon not found after scrolling, forcing URL")
                await save_sidebar_html(page, f"server_sidebar_{server_id}")
                await page.goto(f"https://discord.com/channels/{server_id}", timeout=20000)
                await asyncio.sleep(random.uniform(3.0, 5.0))
        else:
            log(f"   ✅ Already on correct server")
        
        # --- STEP 1.5: Wait for channel list to populate ---
        log(f"   ⏳ Waiting for channel list to load...")
        try:
            # Check for loading indicators
            loading_selectors = [
                '[class*="loading-"]',
                '[class*="scrollerBase"] >> text="Loading"',
                'div[class*="loading"]'
            ]
            loading_visible = False
            for ls in loading_selectors:
                if await page.locator(ls).count() > 0:
                    loading_visible = True
                    break
            
            if loading_visible:
                log(f"   ⏳ Discord showing loading state, waiting...")
                # Wait for loading to hide, but don't hang forever
                try:
                    await page.wait_for_selector('[class*="loading"]', state="hidden", timeout=10000)
                except:
                    log(f"   ⚠️ Loading indicator persistent, forcing continue...")

            # Wait for any channel-like link to ensure sidebar is populated
            await page.wait_for_selector('nav[aria-label*="Channels"] a[href*="/channels/"], [class*="sidebar"] a[href*="/channels/"]', timeout=10000)
            await asyncio.sleep(random.uniform(1.5, 3.0)) 
        except Exception as e:
            log(f"   ⚠️ Channel list load slow: {e}")
        
        # --- STEP 2: Expand collapsed categories ---
        await expand_collapsed_categories(page)
        
        # --- STEP 3: Click Channel in Sidebar ---
        log(f"   🖱️ Looking for channel in sidebar...")
        channel_selectors = [
            f'a[href$="/{channel_id}"]',
            f'a[href*="/{server_id}/{channel_id}"]',
            f'[data-list-item-id="channels___{channel_id}"]',
            f'li[id*="{channel_id}"] a',
            f'div[class*="containerDefault"] a[href*="/{channel_id}"]',
        ]
        
        clicked = False
        # Target the scroller specifically inside the Channels area (middle panel)
        # 1. Try nav with 'channel' label but NOT 'server' (most reliable)
        # 2. Try scroller inside sidebar container
        # 3. Fallback to broad channelsList
        channel_list_container = page.locator('nav[aria-label*="channel"]:not([aria-label*="server"]) [class*="scrollerBase"], [class*="sidebar"] nav [class*="scrollerBase"], [class*="channelsList"] [class*="scrollerBase"]').first
        
        # DEBUG: Log container label to verify isolation
        try:
            if await channel_list_container.count() > 0:
                parent_nav = channel_list_container.locator('xpath=./ancestor::nav').first
                label = await parent_nav.get_attribute("aria-label") or "Unknown"
                log(f"   📂 Channel scroller active (Label: {label})")
        except: pass

        # Human-like: Hover mouse over sidebar to focus it for scrolling
        try:
            await channel_list_container.hover()
            await asyncio.sleep(0.5)
        except: pass

        # --- ATTEMPT 1: Search and Scroll ---
        for attempt in range(8):  # Even more attempts for deep channel trees
            # 1. Expand categories every 2 attempts
            if attempt % 2 == 0:
                await expand_collapsed_categories(page)

            # 2. Check all selectors
            for selector in channel_selectors:
                try:
                    channel_elem = page.locator(selector).first
                    if await channel_elem.count() > 0:
                        # Scroll to it
                        await channel_elem.scroll_into_view_if_needed(timeout=2000)
                        await asyncio.sleep(0.5)
                        
                        if await channel_elem.is_visible():
                            await channel_elem.hover()
                            await asyncio.sleep(random.uniform(0.2, 0.4))
                            await channel_elem.click()
                            clicked = True
                            log(f"   ✅ Channel clicked via sidebar")
                            await asyncio.sleep(random.uniform(1.0, 2.0))
                            break
                except: continue
            
            if clicked: break
            
            # 3. Scroll down bit by bit
            try:
                if await channel_list_container.count() > 0:
                    log(f"   📜 Scrolling down (Attempt {attempt+1})...")
                    # Use a smaller scroll for better discovery
                    await channel_list_container.evaluate("el => el.scrollBy(0, 300)")
                    await asyncio.sleep(0.8) # Wait for virtual scroller to render
                else: break
            except: break

        # --- ATTEMPT 2: Reset to top and try one last time ---
        if not clicked:
            try:
                log(f"   📜 Resetting scroll to top and checking one last time...")
                if await channel_list_container.count() > 0:
                    await channel_list_container.evaluate("el => el.scrollTo(0, 0)")
                    await asyncio.sleep(1.0)
                    for selector in channel_selectors:
                        channel_elem = page.locator(selector).first
                        if await channel_elem.count() > 0:
                            await channel_elem.click()
                            clicked = True
                            log(f"   ✅ Channel clicked after scroll reset")
                            break
            except: pass
        
        # --- FALLBACK: Reload and try one last time (THE ULTIMATE FIX) ---
        if not clicked:
            log(f"   ⚠️ Channel still not found. Hard refreshing page...")
            try:
                await page.reload(timeout=30000)
                await smart_delay(5, 8)
                await expand_collapsed_categories(page)
                # Quick check after reload
                for selector in channel_selectors:
                    channel_elem = page.locator(selector).first
                    if await channel_elem.count() > 0:
                        await channel_elem.click()
                        clicked = True
                        log(f"   ✅ Channel clicked after hard refresh")
                        break
            except: pass

        # --- FINAL FALLBACK: Direct URL ---
        if not clicked:
            log(f"   ⚠️ Channel not clickable, saving sidebar for inspection...")
            await save_sidebar_html(page, f"channel_sidebar_{channel_id}")
            await page.goto(channel_url, timeout=30000)
            await asyncio.sleep(4) # Let URL load finish

        # --- STEP 4: Message Area Activity (New) ---
        try:
            log(f"   👀 Focusing message area...")
            # Target the chat message area scroller
            msg_scroller = page.locator('main[class*="chatContent"] [class*="scrollerBase"], [aria-label*="Messages"] [class*="scrollerBase"]').first
            if await msg_scroller.count() > 0:
                await msg_scroller.hover()
                await asyncio.sleep(random.uniform(0.5, 1.0))
                
                # Perform a human-like "reading" scroll
                scroll_amount = random.randint(2, 4)
                log(f"   📜 Skimming {scroll_amount} message chunks...")
                for _ in range(scroll_amount):
                    direction = -200 if random.random() < 0.3 else 300 # Mostly down, occasionally up
                    await msg_scroller.evaluate(f"el => el.scrollBy(0, {direction})")
                    await asyncio.sleep(random.uniform(0.8, 1.5))
                
                # Scroll to bottom to ensure latest stuff is loaded
                await msg_scroller.evaluate("el => el.scrollTo(0, el.scrollHeight)")
                await asyncio.sleep(1.0)
        except: pass

        # --- FINAL VERIFICATION ---
        current_url = page.url
        match = current_url.endswith(channel_id) or f"/{channel_id}" in current_url
        log(f"   👁️ Landing Verification: {current_url} ({'Success' if match else 'Mismatch'})")
        if not match:
             # If it still mismatch, try one last direct goto
             log(f"   ⚠️ Landing mismatch. Forcing direct navigation...")
             await page.goto(channel_url, timeout=30000)
             await asyncio.sleep(3)
            
    except Exception as e:
        log(f"   ⚠️ Navigation error: {e}")
        await page.goto(channel_url, timeout=30000)

async def save_sidebar_html(page, name_prefix):
    """Save sidebar HTML for DOM inspection when clicking fails"""
    try:
        os.makedirs("data/dom_inspection", exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # 1. Try to get server list (THE FAR LEFT ICON COLUMN)
        try:
            server_list = await page.locator('nav[aria-label*="Servers"], [class*="guilds"]').first.inner_html()
            with open(f"data/dom_inspection/{name_prefix}_servers_{timestamp}.html", 'w', encoding='utf-8') as f:
                f.write(f"<!-- Saved at {timestamp} -->\n")
                f.write(server_list)
        except: pass
        
        # 2. Try to get channel list (THE MIDDLE COLUMN WITH CHANNEL NAMES)
        try:
            # We look for the scroller that actually contains the channels
            channel_selectors = [
                'nav[aria-label*="channel"]:not([aria-label*="server"])', 
                '[class*="sidebar"] nav[class*="container"]',
                '[class*="sidebar"] [class*="scrollerBase"]',
                '[class*="channelsList"]'
            ]
            for sel in channel_selectors:
                loc = page.locator(sel).first
                if await loc.count() > 0:
                    html = await loc.inner_html()
                    with open(f"data/dom_inspection/{name_prefix}_channels_{timestamp}.html", 'w', encoding='utf-8') as f:
                        f.write(f"<!-- Saved at {timestamp} Selector: {sel} -->\n")
                        f.write(html)
                    break
        except: pass
            
        log(f"   💾 Sidebar HTML saved to data/dom_inspection/")
    except Exception as e:
        log(f"   ⚠️ Could not save sidebar HTML: {e}")

async def expand_collapsed_categories(page):
    """Expand any collapsed category folders in the channel sidebar"""
    try:
        # 1. Broad selectors for category headers/folders
        category_selectors = [
            'div[class*="containerDefault"] [role="button"]', 
            '[class*="category"] [role="button"]',
            '[aria-expanded="false"][class*="containerDefault"]',
            'svg[class*="icon"][class*="collapsed"]',
            '[class*="name"] [class*="overflow"]' # Sometimes the name itself is the button
        ]
        
        found_any = False
        for selector in category_selectors:
            try:
                headers = page.locator(selector)
                count = await headers.count()
                if count > 0:
                    for i in range(count):
                        try:
                            header = headers.nth(i)
                            # Only click if it's actually collapsed (check aria-expanded if present)
                            aria_expanded = await header.get_attribute("aria-expanded")
                            
                            # If it's explicitly false or we just want to be sure (no attribute)
                            if aria_expanded == "false" or aria_expanded is None:
                                # Ensure it's in view before clicking
                                await header.scroll_into_view_if_needed(timeout=1000)
                                if await header.is_visible():
                                    await header.click()
                                    found_any = True
                                    await asyncio.sleep(0.2)
                        except: continue
                    if found_any: break
            except: continue
            
        if found_any:
            log(f"   📂 Expanded hidden categories")
            await asyncio.sleep(0.5)
    except Exception as e:
        pass
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

    return random.choice(agents)

# --- PERSISTENCE & SAMPLING ---
def save_channel_metrics():
    """Save metrics to local JSON and upload to Supabase"""
    try:
        local_path = os.path.join(DATA_DIR, CHANNEL_METRICS_FILE)
        remote_path = f"{UPLOAD_FOLDER}/{CHANNEL_METRICS_FILE}"
        
        with open(local_path, 'w') as f:
            json.dump(archiver_state["channel_metrics"], f)
            
        # Upload in background to not block
        threading.Thread(target=supabase_utils.upload_file, args=(local_path, SUPABASE_BUCKET, remote_path)).start()
        log("💾 Saved channel metrics to Supabase")
    except Exception as e:
        log(f"⚠️ Failed to save metrics: {e}")

def load_channel_metrics():
    """Load metrics from Supabase on startup"""
    try:
        local_path = os.path.join(DATA_DIR, CHANNEL_METRICS_FILE)
        remote_path = f"{UPLOAD_FOLDER}/{CHANNEL_METRICS_FILE}"
        
        log("🔄 Downloading channel metrics from Supabase...")
        data = supabase_utils.download_file(local_path, remote_path, SUPABASE_BUCKET)
        
        if data and os.path.exists(local_path):
            with open(local_path, 'r') as f:
                archiver_state["channel_metrics"] = json.load(f)
            log(f"✅ Loaded metrics for {len(archiver_state['channel_metrics'])} channels")
        else:
            log("ℹ️ No remote metrics found. Starting fresh.")
    except Exception as e:
        log(f"⚠️ Failed to load metrics: {e}")

def get_small_batch_channels(available_channels, batch_size=None):
    """
    Select channels using Weighted Reservoir Sampling + 1 Exploration Slot.
    """
    if batch_size is None:
        batch_size = random.randint(3, 5)
    
    # Ensure metrics exist
    for url in available_channels:
        if url not in archiver_state["channel_metrics"]:
            archiver_state["channel_metrics"][url] = {'msg_count': 0, 'last_check': 0}

    # 1. Identify "Exploration Pool" (Bottom 33% by msg count OR 0 msgs)
    all_metrics = []
    for url in available_channels:
        msg_count = archiver_state["channel_metrics"][url].get('msg_count', 0)
        all_metrics.append({'url': url, 'count': msg_count})
    
    all_metrics.sort(key=lambda x: x['count'])
    
    # Define "Low Activity" threshold
    threshold_idx = max(1, len(all_metrics) // 3)
    low_activity_pool = [x['url'] for x in all_metrics[:threshold_idx]]
    
    # Ensure 0-msg channels are always in the pool
    zero_msg_channels = [x['url'] for x in all_metrics if x['count'] == 0]
    
    # Combine and deduplicate
    exploration_pool = list(set(low_activity_pool + zero_msg_channels))
    
    # Sort pool by last_check to implement a cooldown/round-robin (oldest check first)
    exploration_pool_with_times = []
    for url in exploration_pool:
        last_check = archiver_state["channel_metrics"][url].get('last_check', 0)
        exploration_pool_with_times.append({'url': url, 'last_check': last_check})
    
    exploration_pool_with_times.sort(key=lambda x: x['last_check'])
    exploration_pool = [x['url'] for x in exploration_pool_with_times]

    selected_channels = []
    
    # --- PHASE 1: EXPLORATION SLOT (1 Channel) ---
    exploration_pick = None
    if exploration_pool:
        # Pick the oldest checked one from the exploration pool (Robin-Robin)
        exploration_pick = exploration_pool[0]
        selected_channels.append(exploration_pick)
        log(f"🕵️ Exploration Pick: {exploration_pick.split('/')[-1]} (Last checked: {int(time.time() - archiver_state['channel_metrics'][exploration_pick].get('last_check', 0))}s ago)")
        
    # --- PHASE 2: WEIGHTED SELECTION (Remaining Slots) ---
    remaining_slots = batch_size - len(selected_channels)
    
    weighted_candidates = []
    for url in available_channels:
        if url in selected_channels: continue # Skip already picked
        
        metrics = archiver_state["channel_metrics"][url]
        msg_count = metrics.get('msg_count', 0)
        
        # Calculate Weight: log(N+1) + 1
        weight = math.log(msg_count + 1) + 1
        score = random.random() ** (1 / weight)
        
        weighted_candidates.append({'url': url, 'score': score, 'msgs': msg_count})
    
    weighted_candidates.sort(key=lambda x: x['score'], reverse=True)
    
    # Pick top K
    weighted_picks = weighted_candidates[:remaining_slots]
    for c in weighted_picks:
        selected_channels.append(c['url'])
        
    random.shuffle(selected_channels)
    
    log(f"🎲 Selected Batch ({len(selected_channels)}):")
    for url in selected_channels:
        m = archiver_state["channel_metrics"][url].get('msg_count', 0)
        marker = "🕵️" if url == exploration_pick else "🔥"
        log(f"   - {marker} {url.split('/')[-1]} (Msgs: {m})")
        
    return selected_channels

def get_weighted_channel_order(available_channels):
    # Legacy wrapper if needed, but we use get_small_batch_channels now
    return get_small_batch_channels(available_channels)

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

def track_channel_error(channel_url, error_msg, image_bytes=None):
    archiver_state["error_counts"][channel_url] = archiver_state["error_counts"].get(channel_url, 0) + 1
    
    # Always notify admin of errors as requested, but keep the alert_type to allow internal cooldown if needed
    alert_type = f"channel_error_{channel_url}"
    send_telegram_alert(
        f"Channel Error: {channel_url.split('/')[-1]}", 
        f"Channel: {channel_url}\nError: {error_msg}\nTotal Failures: {archiver_state['error_counts'][channel_url]}", 
        image_bytes=image_bytes
    )

def track_channel_success(channel_url):
    if channel_url in archiver_state["error_counts"]:
        del archiver_state["error_counts"][channel_url]
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
        "title_url": None,
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
                if title_url:
                    embed_data["title_url"] = title_url
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
                            
                            // Replace <s> and <strike> with ~~text~~
                            clone.querySelectorAll('s, strike').forEach(s => {
                                s.textContent = `~~${s.textContent}~~`;
                            });
                            
                            // Check for elements with line-through style
                            clone.querySelectorAll('*').forEach(el => {
                                let style = window.getComputedStyle(el);
                                if (style.textDecoration && style.textDecoration.includes('line-through') && !el.textContent.includes('~~')) {
                                    el.textContent = `~~${el.textContent}~~`;
                                }
                            });

                            // Replace <a> tags with markdown [Text](URL)
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
            img_candidates = []
            
            # 1. Comprehensive Discord image locators (Thumbnail, Full Image, Media, Wrapper)
            selectors = [
                'img[class*="embedThumbnail"]',
                '[class*="embedThumbnail"] img',
                'img[class*="embedImage"]',
                '[class*="embedImage"] img',
                '[class*="embedMedia"] img',
                '[class*="imageWrapper"] img',
                'article[class*="embed"] img:not([class*="embedAuthorIcon"]):not([class*="embedFooterIcon"])',
            ]
            
            for sel in selectors:
                elems = embed.locator(sel)
                cnt = await elems.count()
                for k in range(min(cnt, 5)):
                    elem = elems.nth(k)
                    src = await elem.get_attribute('src')
                    
                    # If Discord is lazy loading and src is a data:image base64 blur gradient
                    if src and src.startswith('data:image'):
                        # Check the parent <a> link which Discord wraps around the image
                        try:
                            parent_a = elem.locator('xpath=ancestor::a[1]')
                            if await parent_a.count() > 0:
                                a_href = await parent_a.get_attribute('href')
                                if a_href and a_href.startswith('http'):
                                    src = a_href
                        except: pass
                        
                        # Also check data-src or data-original
                        if src and src.startswith('data:image'):
                            try:
                                d_src = await elem.get_attribute('data-src') or await elem.get_attribute('data-original')
                                if d_src and d_src.startswith('http'):
                                    src = d_src
                            except: pass

                    if src and src.startswith('http') and not src.startswith('data:image'):
                        if src not in img_candidates:
                            img_candidates.append(src)
            
            # Check attachments if no embed images
            if not img_candidates:
                try:
                    att_elems = message_element.locator('[class*="attachment"] img, [id^="message-accessories-"] img')
                    att_cnt = await att_elems.count()
                    for k in range(min(att_cnt, 3)):
                        att_src = await att_elems.nth(k).get_attribute('src')
                        if att_src and att_src.startswith('http') and not att_src.startswith('data:image'):
                            if att_src not in img_candidates:
                                img_candidates.append(att_src)
                except: pass

            if img_candidates:
                embed_data["images"].extend(img_candidates)
                embed_data["thumbnail"] = img_candidates[0]
            else:
                # 2. If Discord DOM didn't have an image, check product links and scrape high-res image
                cand_urls = []
                if embed_data.get("title_url"):
                    cand_urls.append(embed_data["title_url"])
                for l in embed_data.get('links', []):
                    u = l.get('url', '')
                    if u.startswith('http') and u not in cand_urls:
                        cand_urls.append(u)
                target_url = None
                skip_patterns = ['keepa.com', 'ebay.com/sch', 'login', 'cart', 'checkout', 'bugs.zephr', '/member/']
                for u in cand_urls:
                    if not any(x in u.lower() for x in skip_patterns):
                        target_url = u
                        break
                if target_url:
                    try:
                        from telegram_bot import fetch_product_images
                        scraped = fetch_product_images(target_url, max_images=1)
                        if scraped and scraped[0].startswith('http'):
                            embed_data["images"].append(scraped[0])
                            embed_data["thumbnail"] = scraped[0]
                    except: pass
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
        'article[class*="message-"]',
        '[role="listitem"]',
    ]
    
    log("   🔍 Loading messages...")
    try:
        # Increase timeout and wait for a more generic chat container
        await page.wait_for_selector('main[class*="chatContent"], div[class*="chat-"], [class*="messagesWrapper-"]', timeout=30000)
    except: pass
    
    for attempt in range(5): # Increase attempts
        await page.evaluate("window.scrollTo(0, 0)")
        await smart_delay(0.5, 1.5)
        for selector in SELECTORS:
            try:
                elements = page.locator(selector)
                if await elements.count() > 0:
                    return selector, elements
            except: continue
        
        # If not found, scroll to bottom and wait a bit longer
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await smart_delay(1.0, 2.0)
    
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
        
    # Load Persistent Metrics
    load_channel_metrics()
    last_metric_save = time.time()

    while not stop_event.is_set():
        try:
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
                        '--disable-gpu',
                        '--proxy-bypass-list=*',
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
                                    scr = await page.screenshot(quality=85, type='jpeg')
                                    socketio.emit('screenshot', base64.b64encode(scr).decode('utf-8'))
                                except: pass
                                
                                await handle_manual_inputs(page)
                                
                                if "discord.com/channels" in page.url and "/login" not in page.url:
                                    await context.storage_state(path=state_path)
                                    supabase_utils.upload_file(state_path, SUPABASE_BUCKET, remote_state_path, debug=False)
                                    log("✅ Login success!")
                                    await smart_delay(3, 7)
                                    await dismiss_discord_modals(page)
                                    break
                                
                                await asyncio.sleep(5)
                                wait_cycles += 1
                                if wait_cycles % 10 == 0: log(f"⏳ {wait_cycles*5}s elapsed...")


                        # Dynamic Channel Loading (Small Batch Strategy)
                        cm.reload() 
                        enabled_channels = cm.get_enabled_channels()
                        all_urls = [c['url'] for c in enabled_channels]
                        
                        if not all_urls:
                            log("⚠️ No enabled channels found. Waiting...")
                            await asyncio.sleep(60)
                            continue

                        # Pick a small batch (3-5 channels)
                        channels_to_check = get_small_batch_channels(all_urls)
                        
                        for channel_url in channels_to_check:
                            if stop_event.is_set(): break


                            # --- IDLE BREAK CHECK (Per Channel) ---
                            # Logic: Random (10%) OR Forced after 15 channels without break
                            # Duration is random (IDLE_BREAK_MIN to IDLE_BREAK_MAX) handled by take_idle_break
                            
                            should_break = False
                            archiver_state["checks_since_idle"] += 1
                            
                            if archiver_state["checks_since_idle"] >= 15:
                                log("⚠️ Forced idle break (15 channels limit reached)")
                                should_break = True
                            elif random.random() < 0.10:
                                should_break = True
                                
                            if should_break: 
                                await take_idle_break()
                                archiver_state["last_alert_time"]["last_idle_break"] = time.time()
                                archiver_state["checks_since_idle"] = 0 # Reset counter
                                if stop_event.is_set(): break
                            
                            # Persistent failure check
                            if archiver_state["error_counts"].get(channel_url, 0) > 2:
                                log(f"   🔄 Channel {channel_url.split('/')[-1]} has high error count. Hard refreshing...")
                                try:
                                    await page.reload(timeout=30000)
                                    await smart_delay(5, 10)
                                except: pass

                            archiver_state["total_checks"] += 1
                            log(f"📂 [{archiver_state['total_checks']}] {channel_url.split('/')[-1]}")
                            
                            try:
                                # Always use click navigation (fallback to URL only if click fails)
                                await handle_manual_inputs(page)
                                await dismiss_discord_modals(page)  # Clear modals before navigation
                                await navigate_to_channel(page, channel_url)
                                await handle_manual_inputs(page)
                                await dismiss_discord_modals(page)  # Dismiss any overlay modals (e.g. Nitro promos)
                                await smart_delay(2, 5)
                                
                                # Human behavior simulation
                                if random.random() < MOUSE_MOVEMENT_CHANCE:
                                    await advanced_mouse_movement(page)
                                
                                if random.random() < SCROLL_CHANCE:
                                    await realistic_scroll_behavior(page)
                                
                                # Random pause (thinking/reading)
                                await simulate_human_pause()
                                
                                try:
                                    scr = await page.screenshot(quality=85, type='jpeg')
                                    socketio.emit('screenshot', base64.b64encode(scr).decode('utf-8'))
                                except: pass
                                
                                selector, messages = await wait_for_messages_to_load(page)
                                if not messages:
                                    log("   ⚠️ No messages")
                                    # Diagnostic info
                                    page_title = await page.title()
                                    page_url = page.url
                                    err_screenshot = None
                                    try:
                                        err_screenshot = await page.screenshot(quality=70, type='jpeg')
                                    except: pass
                                    
                                    track_channel_error(channel_url, f"No messages found.\nURL: {page_url}\nTitle: {page_title}", image_bytes=err_screenshot)
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
                                    raw_id = await msg.get_attribute('id') or await msg.get_attribute('data-list-item-id') or ""
                                    # Discord snowflake IDs are 17-19 digits. Extract the final numeric segment.
                                    match = re.search(r'(\d{17,19})$', raw_id)
                                    msg_id = match.group(1) if match else raw_id.replace('chat-messages-', '').replace('message-', '')
                                    
                                    if not msg_id or msg_id in current_ids: continue
                                    
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
                                        title = (embed_data.get('title') or 'No title')[:40]
                                        log(f"   ✅ {title}...")
                                        if embed_data.get('links'):
                                            log(f"      🔗 {len(embed_data['links'])} link(s)")
                                    else:
                                        log(f"   📝 {plain_content[:40]}...")
                                    
                                    # Random micro-delay between messages
                                    await asyncio.sleep(random.gauss(0.2, 0.1))

                                # Update Activity Metrics
                                if channel_url not in archiver_state["channel_metrics"]:
                                    archiver_state["channel_metrics"][channel_url] = {'msg_count': 0}
                                archiver_state["channel_metrics"][channel_url]['msg_count'] += len(batch)
                                archiver_state["channel_metrics"][channel_url]['last_check'] = time.time()

                                if batch:
                                    log(f"   ⬆️ {len(batch)} new message(s)")
                                    supabase_utils.insert_discord_messages(batch)
                                    last_ids[channel_url] = current_ids[-200:]
                                    with open(last_ids_path, 'w') as f: json.dump(last_ids, f)
                                
                                track_channel_success(channel_url)
                                await smart_delay(CHANNEL_DELAY_MIN, CHANNEL_DELAY_MAX)

                            except Exception as e:
                                import traceback
                                tb = traceback.format_exc()
                                log(f"   ⚠️ Exception in channel loop: {str(e)}")
                                # Diagnostic info
                                page_title = "Unknown"
                                page_url = channel_url
                                err_screenshot = None
                                try:
                                    page_title = await page.title()
                                    page_url = page.url
                                    err_screenshot = await page.screenshot(quality=70, type='jpeg')
                                except: pass
                                track_channel_error(channel_url, f"{str(e)}\nURL: {page_url}\nTitle: {page_title}\n\nTraceback:\n{tb}", image_bytes=err_screenshot)
                                await smart_delay(4, 8)

                        
                        # Save metrics periodically
                        if time.time() - last_metric_save > 600: # Every 10 mins
                            save_channel_metrics()
                            last_metric_save = time.time()

                        # --- LONG SLEEP CHECK (Post Batch) ---
                        if random.random() < LONG_SLEEP_CHANCE:
                            await take_long_sleep()
                            if stop_event.is_set(): break

                        # Randomized "Session Delay" between batches
                        # Mimics a user checking a few channels, then doing something else
                        next_check = get_next_check_interval()
                        archiver_state["idle_breaks_taken"] += 1
                        log(f"💤 Batch Complete. Taking session break ({int(next_check)}s)...")
                        
                        for _ in range(int(next_check)):
                            if stop_event.is_set(): break
                            await asyncio.sleep(1)

                    except Exception as e:
                        log(f"💥 Browser loop error: {str(e)[:100]}")
                        send_telegram_alert("Browser Loop Error", f"Error: {str(e)}\nLoop continuing...")
                        if "Page crashed" in str(e) or "Target closed" in str(e) or "Browser closed" in str(e):
                            log("🔄 Critical browser failure detected. Restarting session...")
                            break # Break inner loop to re-init playwright
                        await asyncio.sleep(15)
                
                if context:
                    await context.close()
                if browser:
                    await browser.close()
                log("✅ Browser session closed")

        except Exception as e:
            log(f"💥 Top-level error: {str(e)[:100]}")
            send_telegram_alert("CRITICAL: Top-level Archiver Error", f"The archiver loop encountered a major error: {str(e)}\nRestarting loop in 15s...")
            await asyncio.sleep(15)
    
    log("✅ Archiver logic stopped")
    
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

@app.route('/webhook/stripe', methods=['POST'])
def stripe_webhook():
    payload = request.data
    sig_header = request.headers.get('Stripe-Signature')

    if not STRIPE_WEBHOOK_SECRET:
        log("⚠️ STRIPE_WEBHOOK_SECRET not set")
        return 'Webhook Secret Missing', 500

    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, STRIPE_WEBHOOK_SECRET
        )
    except ValueError as e:
        return 'Invalid payload', 400
    except stripe.error.SignatureVerificationError as e:
        return 'Invalid signature', 400

    # Import bot's subscription manager to process events
    try:
        from telegram_bot import sm
        sm.process_stripe_event(event)
    except Exception as e:
        log(f"❌ Stripe Webhook Error: {e}")
        return 'Internal Server Error', 500

    return jsonify(success=True)

@socketio.on('input')
def handle_input(data): input_queue.put(data)


# if __name__ == '__main__':
#     import telegram_bot
#     if os.getenv("TELEGRAM_TOKEN"):
#         t_bot = threading.Thread(target=telegram_bot.run_bot, daemon=True)
#         t_bot.start()
#     socketio.run(app, host='0.0.0.0', port=5000, debug=False, allow_unsafe_werkzeug=True)

if __name__ == '__main__':
    import telegram_bot
    if os.getenv("TELEGRAM_TOKEN"):
        t_bot = threading.Thread(target=telegram_bot.run_bot, daemon=True)
        t_bot.start()
    
    # SSL is handled by Nginx, so we just run standard socketio on localhost
    socketio.run(app, host='127.0.0.1', port=5000, debug=False, allow_unsafe_werkzeug=True)