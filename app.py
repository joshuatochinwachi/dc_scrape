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
import asyncio
from datetime import datetime, timedelta
from flask import Flask, render_template_string, jsonify
from flask_socketio import SocketIO
from playwright.sync_api import sync_playwright
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

# --- Flask App Setup ---
app = Flask(__name__)
log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR) 

# Threading mode is required for Playwright Sync
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

def send_telegram_alert(subject, body):
    if not TELEGRAM_TOKEN or not TELEGRAM_ADMIN_ID: return
    text = f"⚠️ <b>ARCHIVER ALERT: {subject}</b>\n\n{body}"
    try:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            json={"chat_id": TELEGRAM_ADMIN_ID, "text": text, "parse_mode": "HTML"},
            timeout=10
        )
    except: pass

def set_status(status):
    archiver_state["status"] = status
    socketio.emit('status_update', {'status': status})

def clean_text(text):
    if not text: return ""
    text = str(text).replace('\x00', '')
    return ' '.join(text.split()).encode('ascii', 'ignore').decode('ascii')

# --- Scraper Logic ---
def run_archiver_logic_async():
    log("🚀 Thread started.")
    try:
        # Detach from any existing asyncio loop to satisfy Playwright Sync
        asyncio.set_event_loop(asyncio.new_event_loop())
    except: pass
    
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
                    # Login Check
                    if "discord.com/login" in page.url:
                        log("🔒 Login required. Please log in via Web UI.")
                        page.goto("https://discord.com/login")
                        
                        success = False
                        for _ in range(120): 
                            if "discord.com/channels" in page.url: 
                                success = True
                                break
                            try:
                                while not input_queue.empty():
                                    action = input_queue.get_nowait()
                                    if action['type'] == 'click':
                                        vp = page.viewport_size
                                        page.mouse.click(action['x'] * vp['width'], action['y'] * vp['height'])
                            except: pass
                            try:
                                scr = page.screenshot(quality=40, type='jpeg')
                                socketio.emit('screenshot', base64.b64encode(scr).decode('utf-8'))
                            except: pass
                            time.sleep(1)

                        if success:
                            context.storage_state(path=state_path)
                            supabase_utils.upload_file(state_path, SUPABASE_BUCKET, remote_state_path, debug=False)
                            log("✅ Login saved.")
                        else:
                            log("❌ Login timed out.")
                            send_telegram_alert("Login Required", "Manual login required.")
                            time.sleep(300) 
                            continue 
                    
                    # Scrape
                    for channel_url in CHANNELS:
                        if stop_event.is_set(): break
                        log(f"📂 Visiting {channel_url}...")
                        
                        try:
                            page.goto(channel_url, timeout=30000)
                            page.wait_for_selector('li[id^="chat-messages-"]', timeout=5000)
                        except:
                            log(f"⚠️ Failed to load {channel_url}")
                            continue

                        messages = page.locator('li[id^="chat-messages-"]')
                        count = messages.count()
                        batch = []
                        current_ids = last_ids.get(channel_url, [])
                        
                        for i in range(max(0, count - 10), count):
                            try:
                                msg = messages.nth(i)
                                raw_id = msg.get_attribute('id')
                                if not raw_id: continue
                                msg_id = raw_id.replace('chat-messages-', '')
                                if msg_id in current_ids: continue
                                
                                content = ""
                                c_loc = msg.locator('[id^="message-content-"]')
                                if c_loc.count(): content = c_loc.inner_text()
                                
                                author = "Unknown"
                                h_loc = msg.locator('h3')
                                if h_loc.count(): author = h_loc.inner_text().split('\n')[0]

                                media = {"images": []}
                                imgs = msg.locator('img[class^="originalLink-"], a[href*="cdn.discordapp.com"] img')
                                for k in range(imgs.count()):
                                    src = imgs.nth(k).get_attribute('src')
                                    if src: media["images"].append({"url": src})

                                ts = datetime.utcnow().isoformat()
                                t_loc = msg.locator('time')
                                if t_loc.count(): ts = t_loc.get_attribute('datetime') or ts

                                batch.append({
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
                                })
                                current_ids.append(msg_id)
                            except: pass
                        
                        if batch:
                            log(f"   ⬆️ Uploading {len(batch)} msgs...")
                            supabase_utils.insert_discord_messages(batch)
                            if len(current_ids) > 200: current_ids = current_ids[-200:]
                            last_ids[channel_url] = current_ids
                            with open(last_ids_path, 'w') as f: json.dump(last_ids, f)

                        time.sleep(2)

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
        log(f"❌ Fatal Error: {e}")
        send_telegram_alert("Scraper Crashed", str(e))
    
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

@app.route('/health')
def health(): return jsonify({"status": "ok"})

@socketio.on('input')
def handle_input(data): input_queue.put(data)

if __name__ == '__main__':
    # For local testing only
    import telegram_bot
    if os.getenv("TELEGRAM_TOKEN"):
        t_bot = threading.Thread(target=telegram_bot.run_bot, daemon=True)
        t_bot.start()
    socketio.run(app, host='0.0.0.0', port=5000, debug=False, allow_unsafe_werkzeug=True)