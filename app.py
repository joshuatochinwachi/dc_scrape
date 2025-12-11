from dotenv import load_dotenv
load_dotenv()

import os
import time
import json
import threading
import queue
import base64
import logging
from datetime import datetime, timedelta
from flask import Flask, render_template_string, jsonify
from flask_socketio import SocketIO
from playwright.sync_api import sync_playwright
import supabase_utils
import smtplib
from email.message import EmailMessage
import telegram_bot

# --- Prevent event loop conflicts ---
os.environ['EVENTLET_NOKQUEUE'] = '1'

# --- Configuration ---
CHANNELS = os.getenv("CHANNELS", "").split(",")
# Clean up channels (remove empty strings/whitespace)
CHANNELS = [c.strip() for c in CHANNELS if c.strip()]

EMAIL_HOST = os.getenv("EMAIL_HOST", "smtp.gmail.com")
EMAIL_PORT = int(os.getenv("EMAIL_PORT", 587))
EMAIL_USER = os.getenv("EMAIL_USER", "")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD", "")
SUPABASE_BUCKET = "monitor-data"
UPLOAD_FOLDER = "discord_josh"
STORAGE_STATE_FILE = "storage_state.json"
LAST_MESSAGE_ID_FILE = "last_message_ids.json"
DATA_DIR = "data"

HEADLESS_MODE = os.getenv("HEADLESS", "False").lower() == "true"
os.makedirs(DATA_DIR, exist_ok=True)

# --- Flask App Setup ---
app = Flask(__name__)
# Reduce Flask logging
log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR) 

# Use threading mode to avoid async loop conflicts with sync Playwright
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

# --- Global State ---
archiver_state = {
    "status": "STOPPED",
    "logs": []
}
stop_event = threading.Event()
input_queue = queue.Queue()
archiver_thread = None
thread_lock = threading.Lock()

# --- Config Validation ---
if not CHANNELS:
    logging.error("ERROR: CHANNELS environment variable not set. Exiting.")
    exit(1)
if EMAIL_USER and not EMAIL_PASSWORD:
    logging.error("ERROR: EMAIL_PASSWORD required when EMAIL_USER is set.")
    exit(1)

# --- HTML Template (Simplified) ---
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

        function api(cmd) { fetch('/api/' + cmd, { method: 'POST' }); }
        
        // Simple click forwarding
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

def send_alert_email(subject, body):
    """Send alert email for critical issues"""
    if not EMAIL_USER or not EMAIL_PASSWORD:
        return False
    
    try:
        # Get render URL if available
        render_url = os.getenv("RENDER_SERVICE_URL", "https://your-render-url.onrender.com")
        restart_link = f"{render_url}/api/start"
        
        msg = EmailMessage()
        msg['Subject'] = f"[Discord Archiver Alert] {subject}"
        msg['From'] = EMAIL_USER
        msg['To'] = EMAIL_USER
        msg.set_content(f"{body}\n\n--- RESTART INSTRUCTIONS ---\n\n" + 
                       f"Option 1 (Click link): {restart_link}\n\n" +
                       f"Option 2 (Render Dashboard):\n" +
                       f"1. Go to https://dashboard.render.com\n" +
                       f"2. Click 'discord-archiver' service\n" +
                       f"3. Click 'Manual Deploy' > 'Deploy latest commit'\n\n" +
                       f"Check logs at: {render_url}/ (if you have web UI access)")
        
        with smtplib.SMTP_SSL(EMAIL_HOST, 465) as smtp:
            smtp.login(EMAIL_USER, EMAIL_PASSWORD)
            smtp.send_message(msg)
        
        log(f"📧 Alert email sent: {subject}")
        return True
    except Exception as e:
        log(f"❌ Failed to send alert email: {e}")
        return False

def set_status(status):
    archiver_state["status"] = status
    socketio.emit('status_update', {'status': status})

def clean_text(text):
    if not text: return ""
    text = str(text).replace('\x00', '')
    return ' '.join(text.split()).encode('ascii', 'ignore').decode('ascii')

# --- Scraper Logic ---
def run_archiver_logic():
    log("🚀 Thread started.")
    
    # Small delay to ensure thread is detached from event loop
    time.sleep(0.5)
    
    # Paths
    state_path = os.path.join(DATA_DIR, STORAGE_STATE_FILE)
    remote_state_path = f"{UPLOAD_FOLDER}/{STORAGE_STATE_FILE}"
    last_ids_path = os.path.join(DATA_DIR, LAST_MESSAGE_ID_FILE)
    
    # Restore Session with retry
    retry_count = 0
    max_retries = 3
    while retry_count < max_retries:
        try:
            data = supabase_utils.download_file(state_path, remote_state_path, SUPABASE_BUCKET)
            if data:
                log("✅ Session restored from cloud.")
                break
        except Exception as e:
            retry_count += 1
            log(f"⚠️ Session restore failed (attempt {retry_count}/{max_retries}): {e}")
            if retry_count < max_retries:
                time.sleep(2 ** retry_count)  # Exponential backoff
            else:
                log("⚠️ Could not restore session, will need manual login.")

    # Load ID History
    last_ids = {}
    if os.path.exists(last_ids_path):
        try:
            with open(last_ids_path, 'r') as f: last_ids = json.load(f)
        except: pass

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=HEADLESS_MODE, args=['--disable-blink-features=AutomationControlled'])
            
            # Determine context storage
            context_args = {
                "viewport": {'width': 1280, 'height': 800},
                "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36"
            }
            if os.path.exists(state_path):
                context_args["storage_state"] = state_path
            
            context = browser.new_context(**context_args)
            page = context.new_page()
            
            set_status("RUNNING")

            while not stop_event.is_set():
                try:
                    # 1. Login Check
                    if "discord.com/login" in page.url or page.locator('div[class*="qrCodeContainer"]').count() > 0:
                        log("🔒 Login required. Please log in via the Web UI.")
                        page.goto("https://discord.com/login")
                        # Wait loop for user interaction
                        for _ in range(120): # Wait 2 mins max
                            if "discord.com/channels" in page.url: break
                            
                            # Process clicks
                            try:
                                while not input_queue.empty():
                                    action = input_queue.get_nowait()
                                    if action['type'] == 'click':
                                        vp = page.viewport_size
                                        page.mouse.click(action['x'] * vp['width'], action['y'] * vp['height'])
                            except: pass
                            
                            # Screenshot
                            try:
                                scr = page.screenshot(quality=40, type='jpeg')
                                socketio.emit('screenshot', base64.b64encode(scr).decode('utf-8'))
                            except: pass
                            time.sleep(1)

                        if "discord.com/channels" in page.url:
                            context.storage_state(path=state_path)
                            supabase_utils.upload_file(state_path, SUPABASE_BUCKET, remote_state_path, debug=False)
                            log("✅ Login saved.")
                        else:
                            # Login failed after 2 minutes
                            log("❌ Login failed after 2 minutes. Session expired or captcha blocking.")
                            send_alert_email(
                                "Login Failed - Manual Intervention Required",
                                "Discord login failed after 2 minutes.\nPossible causes:\n- Captcha required\n- Session expired\n- 2FA needed\n\nPlease restart from the web service when ready."
                            )
                            # Wait a bit before retrying
                            time.sleep(300)  # Wait 5 minutes before retrying login
                    
                    # 2. Scrape Channels
                    for channel_url in CHANNELS:
                        if stop_event.is_set(): break
                        
                        log(f"📂 Visiting {channel_url}...")
                        page_loaded = False
                        for retry in range(3):
                            try:
                                page.goto(channel_url, timeout=30000)
                                page.wait_for_selector('li[id^="chat-messages-"]', timeout=5000)
                                page_loaded = True
                                break
                            except Exception as e:
                                if retry < 2:
                                    wait_time = 2 ** (retry + 1)
                                    log(f"⚠️ Load failed (retry {retry + 1}/3): {str(e)[:80]}...")
                                    time.sleep(wait_time)
                                else:
                                    log(f"❌ Failed after 3 retries: {str(e)[:80]}...")
                        
                        if not page_loaded:
                            continue

                        messages = page.locator('li[id^="chat-messages-"]')
                        count = messages.count()
                        log(f"   Found {count} messages in DOM.")
                        
                        batch = []
                        current_ids = last_ids.get(channel_url, [])
                        
                        # Scrape last 10 messages only to be safe
                        start_idx = max(0, count - 10)
                        
                        for i in range(start_idx, count):
                            try:
                                msg = messages.nth(i)
                                
                                # ID Extraction
                                raw_id = msg.get_attribute('id')
                                if not raw_id: continue
                                msg_id = raw_id.replace('chat-messages-', '')
                                
                                if msg_id in current_ids: continue
                                
                                # Content Extraction (Robust Selector)
                                content = ""
                                # Try standard content div
                                content_loc = msg.locator('[id^="message-content-"]')
                                if content_loc.count() > 0:
                                    content = content_loc.inner_text()
                                
                                # Author Extraction
                                author = "Unknown"
                                header = msg.locator('h3')
                                if header.count() > 0:
                                    author = header.inner_text().split('\n')[0]

                                # Media (Simplified)
                                media = {"images": []}
                                imgs = msg.locator('img[class^="originalLink-"], a[href*="cdn.discordapp.com"] img')
                                for k in range(imgs.count()):
                                    src = imgs.nth(k).get_attribute('src')
                                    if src: media["images"].append({"url": src})

                                # Timestamp
                                # Discord timestamp is usually in a <time> tag
                                ts = datetime.utcnow().isoformat()
                                time_tag = msg.locator('time')
                                if time_tag.count() > 0:
                                    dt_str = time_tag.get_attribute('datetime')
                                    if dt_str: ts = dt_str

                                record = {
                                    "id": int(msg_id),
                                    "channel_id": int(channel_url.split('/')[-1]),
                                    "content": clean_text(content),
                                    "scraped_at": datetime.utcnow().isoformat(),
                                    "raw_data": {
                                        "author": clean_text(author),
                                        "timestamp": ts,
                                        "media": media,
                                        "channel_url": channel_url
                                    }
                                }
                                batch.append(record)
                                current_ids.append(msg_id)
                                
                            except Exception as e:
                                pass # Skip individual bad messages
                        
                        # Upload Batch
                        if batch:
                            log(f"   ⬆️ Uploading {len(batch)} new messages...")
                            supabase_utils.insert_discord_messages(batch)
                            
                            # Update Cache
                            if len(current_ids) > 200: current_ids = current_ids[-200:]
                            last_ids[channel_url] = current_ids
                            with open(last_ids_path, 'w') as f: json.dump(last_ids, f)

                        # Short sleep between channels
                        time.sleep(2)

                    # Wait before next cycle
                    log("💤 Cycle done. Sleeping 30s...")
                    for _ in range(30):
                        if stop_event.is_set(): break
                        time.sleep(1)
                    
                except Exception as e:
                    log(f"💥 Critical Loop Error: {e}")
                    time.sleep(10)
            
            context.close()
            browser.close()
    
    except Exception as e:
        log(f"❌ Fatal Playwright Error: {e}")
        import traceback
        traceback.print_exc()
        
        # Send critical error alert
        send_alert_email(
            "Critical Playwright Error",
            f"The scraper crashed with error:\n{str(e)}\n\nThis may be due to:\n- Event loop conflicts\n- Browser crashes\n- Severe network issues\n\nManually restart the service from Render dashboard."
        )
    
    set_status("STOPPED")

# --- Routes ---
@app.route('/')
def index(): return render_template_string(HTML_TEMPLATE)

@app.route('/api/start', methods=['POST'])
def start_worker():
    global archiver_thread
    with thread_lock:
        if archiver_thread and archiver_thread.is_alive():
            return jsonify({"status": "already_running"}), 409
        
        stop_event.clear()
        archiver_thread = threading.Thread(target=run_archiver_logic, daemon=True)
        archiver_thread.start()
    return jsonify({"status": "started"})

@app.route('/api/stop', methods=['POST'])
def stop_worker():
    stop_event.set()
    return jsonify({"status": "stopping"})

@app.route('/health')
def health(): return jsonify({"status": "ok"})

@app.route('/health', methods=['HEAD'])
def health_head(): return '', 200

@socketio.on('input')
def handle_input(data):
    input_queue.put(data)

if __name__ == '__main__':
    # Start Telegram Bot in background
    if os.getenv("TELEGRAM_TOKEN"):
        t_bot = threading.Thread(target=telegram_bot.run_bot, daemon=True)
        t_bot.start()
    
    # Development mode
    socketio.run(app, host='0.0.0.0', port=5000, debug=False, allow_unsafe_werkzeug=True)
