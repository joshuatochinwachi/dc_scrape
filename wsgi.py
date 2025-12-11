"""
WSGI entry point for production (Gunicorn)
Starts both Flask/SocketIO and Telegram bot in isolated threads
"""
import os
import threading
import asyncio
from dotenv import load_dotenv

load_dotenv()

# CRITICAL FIX: Disable asyncio before importing app
# This prevents conflicts with Playwright sync API
def disable_asyncio():
    """Completely disable asyncio event loop"""
    try:
        loop = asyncio.get_event_loop()
        if loop and loop.is_running():
            loop.close()
    except:
        pass
    
    try:
        asyncio.set_event_loop_policy(None)
        asyncio.set_event_loop(None)
    except:
        pass

# Call before any imports that might create event loops
disable_asyncio()

# Import telegram_bot directly from the file, not from 'app'
import telegram_bot
from app import app, run_archiver_logic_async, stop_event

# Start Telegram Bot in background thread (isolated)
if os.getenv("TELEGRAM_TOKEN"):
    def run_telegram_safe():
        """Run telegram bot in isolated thread"""
        try:
            telegram_bot.run_bot()
        except Exception as e:
            print(f"Telegram bot error: {e}")
    
    t_bot = threading.Thread(target=run_telegram_safe, daemon=True)
    t_bot.start()

# Start archiver in a standard isolated thread
def start_archiver():
    """Use standard thread to ensure clean context for Playwright"""
    # Wait a bit for Flask to fully initialize
    import time
    time.sleep(2)
    
    # Don't auto-start - let user click "Start Archiver" button
    # This gives them time to monitor the interface
    print("[WSGI] Ready. Visit web interface to start archiver.")

# Start archiver initialization in background
init_thread = threading.Thread(target=start_archiver, daemon=True)
init_thread.start()

# Export application for Gunicorn
if __name__ != '__main__':
    application = app
else:
    # For direct execution (testing)
    app.run(host='0.0.0.0', port=5000)