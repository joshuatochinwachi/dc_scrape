"""
WSGI entry point for production (Gunicorn)
Starts both Flask/SocketIO and Telegram bot in isolated threads
"""
import os
import threading
from dotenv import load_dotenv

load_dotenv()

# Fix: Import telegram_bot directly from the file, not from 'app'
import telegram_bot
from app import app, run_archiver_logic_async

# Start Telegram Bot in background thread (isolated)
if os.getenv("TELEGRAM_TOKEN"):
    t_bot = threading.Thread(target=telegram_bot.run_bot, daemon=True)
    t_bot.start()

# Start archiver in a standard isolated thread
def start_archiver():
    # Use standard thread to ensure clean context for Playwright
    t_archiver = threading.Thread(target=run_archiver_logic_async, daemon=True)
    t_archiver.start()

# Start archiver immediately on startup
start_archiver()

if __name__ != '__main__':
    application = app