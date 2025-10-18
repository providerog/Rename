import base64
import re
import asyncio
import time
import logging
import datetime
from pytz import timezone
from datetime import datetime, timedelta
import string
from bot import Bot
from pyrogram import filters
from pyrogram.enums import ChatMemberStatus
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors.exceptions.bad_request_400 import UserNotParticipant
from pyrogram.errors import FloodWait
from shortzy import Shortzy
from config import *
import random

IST = timezone("Asia/Kolkata")

logging.basicConfig(level=logging.DEBUG, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)  # Create a logger instance

# Define greeting based on the time of day
def get_greeting():
    current_hour = datetime.now().hour
    if current_hour < 12:
        return "🌞 Gᴏᴏᴅ Mᴏʀɴɪɴɢ"
    elif current_hour < 18:
        return "🌤️ Gᴏᴏᴅ Aғᴛᴇʀɴᴏᴏɴ"
    else:
        return "🌙 Gᴏᴏᴅ Eᴠᴇɴɪɴɢ"

# Randomized cool intro phrases
cool_phrases = [
    "🚀 Bᴇʏᴏɴᴅ Lɪᴍɪᴛꜱ, Bᴇʏᴏɴᴅ Iᴍᴀɢɪɴᴀᴛɪᴏɴ!",
    "⚡ Pᴏᴡᴇʀᴇᴅ Bʏ AI, Dᴇꜱɪɢɴᴇᴅ Fᴏʀ Pᴇʀꜰᴇᴄᴛɪᴏɴ.",
    "💡 I Dᴏɴ'ᴛ Jᴜꜱᴛ Rᴇᴘʟʏ— I Tʜɪɴᴋ.",
    "🤖 Wᴇʟᴄᴏᴍᴇ Tᴏ Tʜᴇ Fᴜᴛᴜʀᴇ ᴏғ Aᴜᴛᴏᴍᴀᴛɪᴏɴ!",
]

# Function to generate the dynamic start message
def get_start_msg(mention):
    greeting = get_greeting()  # Call get_greeting to get the current greeting
    random_phrase = random.choice(cool_phrases)

    return (
        f"<blockquote>{greeting}, {mention}! </blockquote>\n\n"
        f"<b>Jᴜsᴛ Sᴇɴᴅ Mᴇ A Pʀɪᴠᴀᴛᴇ Cʜᴀɴɴᴇʟ Pᴏsᴛ Lɪɴᴋ Rᴇsᴛ I Wɪʟʟ ʜᴀɴᴅʟᴇ</b>\n\n"
    )
