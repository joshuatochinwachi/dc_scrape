from dotenv import load_dotenv
load_dotenv()

import os
import time
import json
import threading
import queue
import base64
import logging
import requests
from datetime import datetime, timedelta
from flask import Flask, render_template_string, jsonify
from flask_socketio import SocketIO
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout
import supabase_utils

# --- Prevent event loop conflicts ---
os.environ['EVENTLET_NOKQUEUE'] = '1'

# --- Configuration ---
CHANNELS = os.getenv("CHANNELS", "").split(",")
CHANNELS = [c.strip() for c in CHANNELS if c.strip()]

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_ADMIN_ID = os.getenv("TELEGRAM_ADMIN_ID")

SUPABASE_BUCKET = "monitor-data"
UPLOAD_FOLDER = "discord_josh"
STORAGE_STATE_FILE = "storage_state.json"
LAST_MESSAGE_ID_FILE = "last_message_ids.json"
DATA_DIR = "data"

HEADLESS_MODE = os.getenv("HEADLESS", "False").lower() == "true"
os.makedirs(DATA_DIR, exist_ok=True)

# --- Alert Configuration ---
ERROR_THRESHOLD = 5
ALERT_COOLDOWN = 1800

# --- Flask App Setup ---
app = Flask(__name__)
log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR) 

socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

# --- Global State ---
archiver_state = {
    "status": "STOPPED",
    "logs": [],
    "error_counts": {},
    "last_alert_time": {},
    "last_success_time": {}
}
stop_event = threading.Event()
input_queue = queue.Queue()
archiver_thread = None
thread_lock = threading.Lock()

if not CHANNELS:
    logging.error("ERROR: CHANNELS environment variable not set. Exiting.")
    exit(1)

# --- HTML Template ---
HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Discord Archiver Portal</title>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/socket.io/4.0.1/socket.io.js"></script>
    <style>
        body { font-family: monospace; background: #222; color: #eee; margin: 0; padding: 20px; }
        .container { display: flex; gap: 20px; }
        .controls { min-width: 250px; }
        .view { flex-grow: 1; text-align: center; }
        img { max-width: 100%; border: 1px solid #555; }
        .log-box { height: 400px; overflow-y: scroll; background: #111; border: 1px solid #333; padding: 10px; font-size: 11px; margin-top: 10px; }
        button { padding: 8px; width: 100%; margin-bottom: 5px; cursor: pointer; background: #444; color: white; border: none; }
        button:hover { background: #555; }
        .status { padding: 10px; text-align: center; font-weight: bold; margin-bottom: 15px; }
        .running { background: #2fdd2f; color: #000; }
        .stopped { background: #dd2f2f; color: #fff; }
    </style>
</head>
<body>
    <div class="container">
        <div class="controls">
            <div id="status-display" class="status stopped">STOPPED</div>
            <button onclick="api('start')">Start Archiver</button>
            <button onclick="api('stop')">Stop Archiver</button>
            <button onclick="testStatus()">Check Status</button>
            <div id="stats" style="background: #111; padding: 10px; margin: 10px 0; font-size: 11px; border: 1px solid #333;"></div>
            <div class="log-box" id="logs"></div>
        </div>
        <div class="view">
            <h3>Live Browser View</h3>
            <img id="live-stream" src="" alt="Stream inactive" />
        </div>
    </div>
    <script>
        var socket = io();
        var img = document.getElementById('live-stream');
        var logs = document.getElementById('logs');
        var stats = document.getElementById('stats');
        
        socket.on('screenshot', data => img.src = 'data:image/jpeg;base64,' + data);
        socket.on('log', data => {
            var div = document.createElement('div');
            div.textContent = `[${new Date().toLocaleTimeString()}] ${data.message}`;
            logs.appendChild(div);
            logs.scrollTop = logs.scrollHeight;
        });
        socket.on('status_update', data => {
            var el = document.getElementById('status-display');
            el.textContent = data.status;
            el.className = 'status ' + (data.status === 'RUNNING' ? 'running' : 'stopped');
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
                    let html = '<b>Status Check:</b><br>';
                    html += 'Archiver: ' + data.archiver_status + '<br><br>';
                    html += '<b>Error Counts:</b><br>';
                    for (let [url, count] of Object.entries(data.error_counts || {})) {
                        html += url.split('/').pop() + ': ' + count + ' errors<br>';
                    }
                    html += '<br><b>Last Success:</b><br>';
                    for (let [url, time] of Object.entries(data.last_success || {})) {
                        html += url.split('/').pop() + ': ' + new Date(time).toLocaleTimeString() + '<br>';
                    }
                    stats.innerHTML = html;
                })
                .catch(e => stats.innerHTML = 'Error: ' + e);
        }
        
        img.onclick = function(e) {
            var rect = img.getBoundingClientRect();
            socket.emit('input', {
                type: 'click', 
                x: (e.clientX - rect.left) / rect.width,
                y: (e.clientY - rect.top) / rect.height
            });
        };
    </script>
</body>
</html>
"""

def log(message):
    print(f"[Scraper] {message}")
    archiver_state["logs"].append(message)
    if len(archiver_state["logs"]) > 50: archiver_state["logs"].pop(0)
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
    
    text = f"⚠️ <b>ARCHIVER ALERT: {subject}</b>\n\n{body}"
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
        else:
            log(f"❌ Alert failed: HTTP {response.status_code}")
    except Exception as e:
        log(f"❌ Alert error: {str(e)}")

def set_status(status):
    archiver_state["status"] = status
    socketio.emit('status_update', {'status': status})

def clean_text(text):
    if not text: return ""
    text = str(text).replace('\x00', '')
    return ' '.join(text.split()).encode('ascii', 'ignore').decode('ascii')

def track_channel_error(channel_url, error_msg):
    archiver_state["error_counts"][channel_url] = archiver_state["error_counts"].get(channel_url, 0) + 1
    error_count = archiver_state["error_counts"][channel_url]
    
    if error_count >= ERROR_THRESHOLD:
        alert_type = f"channel_error_{channel_url}"
        last_success = archiver_state["last_success_time"].get(channel_url)
        
        if last_success:
            downtime = datetime.utcnow() - datetime.fromisoformat(last_success)
            downtime_str = f"Down for {int(downtime.total_seconds() / 60)} minutes"
        else:
            downtime_str = "No successful scrapes yet"
        
        body = (
            f"Channel: {channel_url}\n"
            f"Consecutive failures: {error_count}\n"
            f"Status: {downtime_str}\n"
            f"Error: {error_msg}\n\n"
            f"Possible causes:\n"
            f"• Session expired (needs re-login)\n"
            f"• Discord detecting automation\n"
            f"• Channel access revoked\n"
            f"• Network/server issues"
        )
        send_telegram_alert(f"Channel Access Failed ({error_count}x)", body, alert_type)

def track_channel_success(channel_url):
    archiver_state["error_counts"][channel_url] = 0
    archiver_state["last_success_time"][channel_url] = datetime.utcnow().isoformat()

def wait_for_messages_to_load(page, max_wait=15):
    """
    Improved message detection with multiple strategies and scrolling
    """
    # Multiple possible selectors Discord might use
    SELECTORS = [
        'li[id^="chat-messages-"]',  # Original selector
        '[class*="message-"][class*="cozy"]',  # Message container classes
        '[id^="message-content-"]',  # Message content IDs
        'div[class*="messageContent-"]',  # Alternative message content
        '[data-list-item-id^="chat-messages"]',  # Data attributes
    ]
    
    log("   🔍 Waiting for messages to load...")
    start_time = time.time()
    
    # First, wait for the chat area to be present
    try:
        page.wait_for_selector('main[class*="chatContent"], div[class*="chat-"]', timeout=5000)
        log("   ✅ Chat area detected")
    except:
        log("   ⚠️ Chat area not found")
    
    # Try scrolling to trigger lazy loading
    for scroll_attempt in range(3):
        try:
            # Scroll up to load older messages
            page.evaluate("window.scrollTo(0, 0)")
            time.sleep(0.5)
            
            # Try each selector
            for selector in SELECTORS:
                try:
                    elements = page.locator(selector)
                    count = elements.count()
                    if count > 0:
                        log(f"   ✅ Found {count} messages using selector: {selector}")
                        return selector, elements
                except:
                    continue
            
            # If no messages found, scroll down and try again
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            time.sleep(0.5)
            
        except Exception as e:
            log(f"   ⚠️ Scroll attempt {scroll_attempt + 1} error: {str(e)}")
    
    elapsed = time.time() - start_time
    log(f"   ❌ No messages found after {elapsed:.1f}s")
    return None, None

# --- Scraper Logic ---
def run_archiver_logic_async():
    log("🚀 Thread started.")
    
    import asyncio
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.set_event_loop(None)
    except RuntimeError:
        pass
    
    state_path = os.path.join(DATA_DIR, STORAGE_STATE_FILE)
    remote_state_path = f"{UPLOAD_FOLDER}/{STORAGE_STATE_FILE}"
    last_ids_path = os.path.join(DATA_DIR, LAST_MESSAGE_ID_FILE)
    
    retry_count = 0
    while retry_count < 3:
        try:
            data = supabase_utils.download_file(state_path, remote_state_path, SUPABASE_BUCKET)
            if data:
                log("✅ Session restored.")
                break
        except:
            retry_count += 1
            if retry_count < 3: time.sleep(2)

    last_ids = {}
    if os.path.exists(last_ids_path):
        try:
            with open(last_ids_path, 'r') as f: last_ids = json.load(f)
        except: pass

    browser = None
    context = None
    page = None
    
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=HEADLESS_MODE, 
                args=['--disable-blink-features=AutomationControlled']
            )
            context_args = {
                "viewport": {'width': 1280, 'height': 800},
                "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36"
            }
            if os.path.exists(state_path): context_args["storage_state"] = state_path
            
            context = browser.new_context(**context_args)
            page = context.new_page()
            set_status("RUNNING")

            while not stop_event.is_set():
                try:
                    current_url = page.url
                    
                    # Check if login is needed
                    if "login" in current_url.lower() or current_url == "about:blank" or "discord.com/channels" not in current_url:
                        log("🔒 Login required. Navigating to login page...")
                        send_telegram_alert(
                            "Login Required", 
                            "Discord session expired. Please log in via the web interface.\n\nThe scraper will wait for 10 minutes for you to log in.",
                            "login_required"
                        )
                        
                        try:
                            page.goto("https://discord.com/login", timeout=30000)
                        except:
                            pass
                        
                        success = False
                        wait_cycles = 0
                        max_wait_cycles = 120
                        
                        while wait_cycles < max_wait_cycles and not stop_event.is_set():
                            try:
                                scr = page.screenshot(quality=40, type='jpeg')
                                socketio.emit('screenshot', base64.b64encode(scr).decode('utf-8'))
                            except: pass
                            
                            try:
                                while not input_queue.empty():
                                    action = input_queue.get_nowait()
                                    if action['type'] == 'click':
                                        vp = page.viewport_size
                                        page.mouse.click(action['x'] * vp['width'], action['y'] * vp['height'])
                            except: pass
                            
                            if "discord.com/channels" in page.url and "/login" not in page.url:
                                success = True
                                break
                            
                            time.sleep(5)
                            wait_cycles += 1
                            
                            if wait_cycles % 12 == 0:
                                log(f"⏳ Waiting for login... ({wait_cycles * 5}s elapsed)")

                        if success:
                            context.storage_state(path=state_path)
                            supabase_utils.upload_file(state_path, SUPABASE_BUCKET, remote_state_path, debug=False)
                            log("✅ Login saved successfully!")
                            send_telegram_alert(
                                "Login Successful",
                                "Successfully logged in to Discord. Scraping will now resume.",
                                "login_success"
                            )
                        else:
                            log("❌ Login timeout - will retry in 5 minutes")
                            send_telegram_alert(
                                "Login Timeout",
                                "No login detected after 10 minutes. Will retry in 5 minutes.\n\nPlease ensure you can access the web interface.",
                                "login_timeout"
                            )
                            time.sleep(300)
                            continue 
                    
                    # Scrape channels
                    for channel_url in CHANNELS:
                        if stop_event.is_set(): break
                        log(f"📂 Visiting {channel_url}...")
                        
                        try:
                            page.goto(channel_url, timeout=30000)
                            time.sleep(3)  # Give page more time to load
                            
                            current_url = page.url
                            page_title = page.title()
                            
                            # Take diagnostic screenshot
                            try:
                                scr = page.screenshot(quality=40, type='jpeg')
                                socketio.emit('screenshot', base64.b64encode(scr).decode('utf-8'))
                            except: pass
                            
                            # Check for failure conditions
                            if "login" in current_url.lower():
                                raise Exception("Redirected to login - session expired")
                            
                            if "verify" in current_url.lower() or "captcha" in page.content().lower():
                                raise Exception("Discord verification/captcha required")
                            
                            # Use improved message detection
                            selector, messages = wait_for_messages_to_load(page)
                            
                            if not selector or not messages:
                                raise Exception("No messages found - possible access issue or DOM changed")
                            
                        except PlaywrightTimeout as e:
                            error_msg = (
                                f"Timeout loading channel\n"
                                f"Current URL: {page.url}\n"
                                f"Page Title: {page.title()}\n"
                            )
                            log(f"⚠️ Failed to load {channel_url} - Timeout")
                            log(f"   Debug: URL={page.url}, Title={page.title()}")
                            track_channel_error(channel_url, error_msg)
                            continue
                        except Exception as e:
                            error_msg = f"{str(e)}\nURL: {page.url if page else 'unknown'}"
                            log(f"⚠️ Failed to load {channel_url} - {str(e)}")
                            track_channel_error(channel_url, error_msg)
                            continue

                        # Parse messages
                        count = messages.count()
                        log(f"   📊 Found {count} messages")
                        
                        if count == 0:
                            log(f"⚠️ No messages found in {channel_url}")
                            track_channel_error(channel_url, "No messages visible")
                            continue
                        
                        batch = []
                        current_ids = last_ids.get(channel_url, [])
                        
                        for i in range(max(0, count - 10), count):
                            try:
                                msg = messages.nth(i)
                                
                                # Try to get message ID from various possible attributes
                                raw_id = None
                                for id_attr in ['id', 'data-list-item-id', 'data-message-id']:
                                    raw_id = msg.get_attribute(id_attr)
                                    if raw_id: break
                                
                                if not raw_id: continue
                                
                                # Extract numeric ID
                                msg_id = raw_id.replace('chat-messages-', '').replace('message-', '')
                                if msg_id in current_ids: continue
                                
                                # Get message content
                                content = ""
                                for content_sel in ['[id^="message-content-"]', '[class*="messageContent-"]']:
                                    try:
                                        c_loc = msg.locator(content_sel).first
                                        if c_loc.count(): 
                                            content = c_loc.inner_text()
                                            break
                                    except: pass
                                
                                # Get author
                                author = "Unknown"
                                for author_sel in ['h3', '[class*="username-"]', '[class*="author-"]']:
                                    try:
                                        h_loc = msg.locator(author_sel).first
                                        if h_loc.count(): 
                                            author = h_loc.inner_text().split('\n')[0]
                                            break
                                    except: pass

                                # Get media
                                media = {"images": []}
                                imgs = msg.locator('img[class*="original"], a[href*="cdn.discordapp.com"] img')
                                for k in range(imgs.count()):
                                    src = imgs.nth(k).get_attribute('src')
                                    if src: media["images"].append({"url": src})

                                # Get timestamp
                                ts = datetime.utcnow().isoformat()
                                t_loc = msg.locator('time')
                                if t_loc.count(): ts = t_loc.first.get_attribute('datetime') or ts

                                batch.append({
                                    "id": int(msg_id) if msg_id.isdigit() else hash(msg_id),
                                    "channel_id": int(channel_url.split('/')[-1]),
                                    "content": clean_text(content),
                                    "scraped_at": datetime.utcnow().isoformat(),
                                    "raw_data": {
                                        "author": clean_text(author),
                                        "timestamp": ts,
                                        "media": media,
                                        "channel_url": channel_url
                                    }
                                })
                                current_ids.append(msg_id)
                            except Exception as e:
                                log(f"   ⚠️ Error parsing message: {str(e)}")
                        
                        if batch:
                            log(f"   ⬆️ Uploading {len(batch)} msgs...")
                            try:
                                supabase_utils.insert_discord_messages(batch)
                                track_channel_success(channel_url)
                            except Exception as e:
                                log(f"   ❌ Upload failed: {str(e)}")
                                send_telegram_alert(
                                    "Database Upload Failed",
                                    f"Failed to upload {len(batch)} messages\nError: {str(e)}",
                                    "upload_error"
                                )
                            
                            if len(current_ids) > 200: current_ids = current_ids[-200:]
                            last_ids[channel_url] = current_ids
                            with open(last_ids_path, 'w') as f: json.dump(last_ids, f)
                        else:
                            track_channel_success(channel_url)

                        time.sleep(2)

                    log("💤 Cycle done. Sleeping 30s...")
                    for _ in range(30):
                        if stop_event.is_set(): break
                        time.sleep(1)
                    
                except Exception as e:
                    log(f"💥 Critical Loop Error: {e}")
                    send_telegram_alert(
                        "Critical Error in Scrape Loop",
                        f"Error: {str(e)}\n\nThe scraper will retry in 10 seconds.",
                        "loop_error"
                    )
                    time.sleep(10)
            
            if context: context.close()
            if browser: browser.close()
    
    except Exception as e:
        log(f"❌ Fatal Error: {e}")
        send_telegram_alert(
            "Scraper Crashed",
            f"Fatal error occurred:\n{str(e)}\n\nScraper has stopped. Please restart manually.",
            "fatal_error"
        )
    
    set_status("STOPPED")

@app.route('/')
def index(): return render_template_string(HTML_TEMPLATE)

@app.route('/api/start', methods=['POST'])
def start_worker():
    global archiver_thread
    with thread_lock:
        if archiver_thread and archiver_thread.is_alive():
            return jsonify({"status": "already_running"}), 409
        stop_event.clear()
        archiver_thread = threading.Thread(target=run_archiver_logic_async, daemon=True)
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
        "last_success": archiver_state["last_success_time"],
        "archiver_status": archiver_state["status"]
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