import os
import random
import logging
import asyncio
from datetime import datetime
from operator import add
from urllib.parse import quote_plus
from logging.handlers import RotatingFileHandler

from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, Message

# ═══════════════════════════════════════════════════════════════════════════════════
# 🔐 BOT CREDENTIALS & API SETTINGS
# ═══════════════════════════════════════════════════════════════════════════════════

TG_BOT_TOKEN = os.environ.get("TG_BOT_TOKEN", "8044543440:AAGJDD5MCpQ7_3MEYkD-8ZAQqqSF87QzPic")
APP_ID = int(os.environ.get("APP_ID", "21816206"))
API_ID = int(os.environ.get("APP_ID", "21816206"))
API_HASH = os.environ.get("API_HASH", "0a82243f31819a62df76947196fdaa0a")

OWNER_ID = int(os.environ.get("OWNER_ID", "7645440087"))
OWNER_TAG = os.environ.get("OWNER_TAG", "provider_og")
ADMIN_LIST = os.environ.get("ADMINS", "").split()
ADMINS = [int(admin) for admin in ADMIN_LIST if admin.isdigit()]
ADMINS.append(OWNER_ID)

SAVE_CHAT = -1002728160601

# ═══════════════════════════════════════════════════════════════════════════════════
# 🗄️ DATABASE SETTINGS
# ═══════════════════════════════════════════════════════════════════════════════════

DB_URL = os.environ.get("DB_URL", "mongodb://localhost:27017/")
DB_NAME = os.environ.get("DB_NAME", "billu")

# ═══════════════════════════════════════════════════════════════════════════════════
# 💎 PREMIUM SETTINGS
# ═══════════════════════════════════════════════════════════════════════════════════

FREE_LIMIT = int(os.environ.get("FREE_LIMIT", "50"))

PREMIUM_PLANS = {
    "7_days": {"name": "7 Days Premium", "price": "₹99", "days": 7},
    "3_months": {"name": "3 Months Premium", "price": "₹299", "days": 90},
    "6_months": {"name": "6 Months Premium", "price": "₹499", "days": 180}
}

# ═══════════════════════════════════════════════════════════════════════════════════
# 🎨 MEDIA & UI SETTINGS
# ═══════════════════════════════════════════════════════════════════════════════════

START_PIC = os.environ.get("START_PIC", "https://ibb.co/jZVkMBZT,https://ibb.co/jZVkMBZT").split(',')
ABOUT_PIC = os.environ.get("ABOUT_PIC", "https://ibb.co/ZpJdfDL6")

# ═══════════════════════════════════════════════════════════════════════════════════
# 📝 MESSAGE TEMPLATES
# ═══════════════════════════════════════════════════════════════════════════════════

START_MSG = os.environ.get("START_MESSAGE", "🚀 **Welcome to MEGA Renamer Bot!**\n\nRename your MEGA files with custom prefix easily!")

CUSTOM_CAPTION = """
{premium_message}
"""

BOT_STATS_TEXT = os.environ.get(
    "BOTS_STATS_TEXT",
    "<b>💻 SYSTEM OVERVIEW</b>\n"
    "☠️ <b>UPTIME:</b> {uptime}\n"
    "👥 <b>USERS:</b> {total_users}\n"
    "💎 <b>PREMIUM USERS:</b> {premium_users}\n"
)

USER_REPLY_TEXT = os.environ.get(
    "USER_REPLY_TEXT",
    "<b>🚫 ACCESS DENIED</b>\n"
    "You aren't authorized to DM directly.\n"
)

USER_REPLY_BUTTONS = [
    [InlineKeyboardButton("❰ ×× DD_FREE_DISHH -//- ❱", url="https://t.me/dd_free_dishh")]
]

PREMIUM_MSG = """
💎 **PREMIUM REQUIRED**

You've reached the free limit of {free_limit} files!

**Choose a Premium Plan:**

🔥 **7 Days** - ₹99
⚡ **3 Months** - ₹299
🚀 **6 Months** - ₹499

**Premium Benefits:**
✅ Unlimited file renaming
✅ Priority support
✅ Faster processing
✅ No daily limits

Contact admin to purchase premium!
"""

OWNER_TAG = os.environ.get("OWNER_TAG", "provider_og")

# ═══════════════════════════════════════════════════════════════════════════════════
# ⚙️ APP SETTINGS & CONFIGURATION
# ═══════════════════════════════════════════════════════════════════════════════════

PORT = os.environ.get("PORT", "8000")
TG_BOT_WORKERS = int(os.environ.get("TG_BOT_WORKERS", "100"))
DEFAULT_WELCOME = ""

# ═══════════════════════════════════════════════════════════════════════════════════
# 📋 LOGGING CONFIGURATION
# ═══════════════════════════════════════════════════════════════════════════════════

LOG_FILE_NAME = "NyxDesireX.txt"

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s - %(levelname)s] - %(name)s - %(message)s",
    datefmt='%d-%b-%y %H:%M:%S',
    handlers=[
        RotatingFileHandler(LOG_FILE_NAME, maxBytes=50000000, backupCount=10),
        logging.StreamHandler()
    ]
)

logging.getLogger("pyrogram").setLevel(logging.WARNING)

def LOGGER(name: str) -> logging.Logger:
    return logging.getLogger(name)
