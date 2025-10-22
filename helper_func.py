import base64
import re
import asyncio
import time
import logging
import datetime
from pytz import timezone
from datetime import datetime, timedelta
import string
import random
from bot import Bot
from pyrogram import filters
from pyrogram.enums import ChatMemberStatus
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors.exceptions.bad_request_400 import UserNotParticipant
from pyrogram.errors import FloodWait
from shortzy import Shortzy
from config import *
from database import db # Import db instance

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

# In your is_subscribed function:
async def is_subscribed(filter, client, update):
    """Check if user is subscribed to all FORCE_SUB_CHANNELS and REQUEST_SUB_CHANNELS."""
    settings = await db.get_settings()
    FORCE_SUB_CHANNELS = settings.get("FORCE_SUB_CHANNELS", [])
    REQUEST_SUB_CHANNELS = settings.get("REQUEST_SUB_CHANNELS", [])

    if not FORCE_SUB_CHANNELS and not REQUEST_SUB_CHANNELS:
        return True

    user_id = update.from_user.id
    if user_id in ADMINS:  # Allow admins without forcing them to join
        return True

    # Check regular force subscription channels
    for channel in FORCE_SUB_CHANNELS:
        try:
            member = await client.get_chat_member(channel, user_id)
            if member.status in [ChatMemberStatus.OWNER, ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.MEMBER]:
                continue  # User is subscribed to this channel, check next one
            else:
                return False  # Not subscribed
        except UserNotParticipant:
            return False  # User is not a participant
        except Exception as e:
            print(f"Error checking subscription: {e}")
            return False  # If any error occurs, assume not subscribed

    # Check request force subscription channels
    for channel in REQUEST_SUB_CHANNELS:
        try:
            # First check if user has a pending request
            if await db.has_pending_request(user_id, channel):
                continue  # User has a pending request, consider as subscribed

            # Then check if user is a member
            member = await client.get_chat_member(channel, user_id)
            if member.status in [ChatMemberStatus.OWNER, ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.MEMBER]:
                continue  # User is subscribed to this channel, check next one
            else:
                return False  # Not subscribed
        except UserNotParticipant:
            return False  # User is not a participant
        except Exception as e:
            print(f"Error checking request subscription: {e}")
            return False  # If any error occurs, assume not subscribed

    return True  # User is subscribed to all channels


async def is_subscribed2(filter, client, update):
    """Check if the user is subscribed to at least one channel from FORCE_SUB_CHANNELS."""
    settings = await db.get_settings()
    FORCE_SUB_CHANNELS = settings.get("FORCE_SUB_CHANNELS", [])
    if not FORCE_SUB_CHANNELS:
        return True

    user_id = update.from_user.id
    if user_id in ADMINS:
        return True

    for channel in FORCE_SUB_CHANNELS:
        try:
            member = await client.get_chat_member(channel, user_id)
            if member.status in [ChatMemberStatus.OWNER, ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.MEMBER]:
                return True  # User is subscribed to at least one channel
        except Exception as e:
            print(f"Error checking subscription status for channel {channel}: {e}")

    return False  # User is not subscribed to any required channel


async def get_messages(client, message_ids):
    if not message_ids:  # Ensure message_ids is valid
        print("No message IDs provided.")
        return []

    messages = []
    total_messages = 0

    while total_messages < len(message_ids):
        batch_ids = message_ids[total_messages:total_messages + 200]  # Limit batch size

        try:
            # Validate message IDs
            batch_ids = [int(msg_id) for msg_id in batch_ids if isinstance(msg_id, int) and 0 < msg_id < 2**31]

            if not batch_ids:
                print("No valid message IDs found.")
                break

            fetched_messages = await client.get_messages(
                chat_id=client.db_channel.id,
                message_ids=batch_ids
            )

            messages.extend(fetched_messages)
            total_messages += len(batch_ids)  # Increment processed messages

        except FloodWait as e:
            print(f"FloodWait triggered, waiting {e.x} seconds.")
            await asyncio.sleep(e.x)

        except Exception as e:
            print(f"Error fetching messages: {e}")

    return messages

async def get_message_id(client, message):
    if message.forward_from_chat:
        if message.forward_from_chat.id == client.db_channel.id:
            return message.forward_from_message_id
        else:
            return 0
    elif message.forward_sender_name:
        return 0
    elif message.text:
        pattern = r"https://t.me/(?:c/)?(.*)/(\d+)"
        matches = re.match(pattern, message.text)
        if not matches:
            return 0
        channel_id = matches.group(1)
        msg_id = int(matches.group(2))
        if channel_id.isdigit():
            if f"-100{channel_id}" == str(client.db_channel.id):
                return msg_id
        else:
            if channel_id == client.db_channel.username:
                return msg_id
    else:
        return 0

def get_readable_time(seconds):
    periods = [
        ('year', 60 * 60 * 24 * 365),
        ('month', 60 * 60 * 24 * 30),
        ('day', 60 * 60 * 24),
        ('hour', 60 * 60),
        ('minute', 60),
        ('second', 1)
    ]

    result = []
    for period_name, period_seconds in periods:
        if seconds >= period_seconds:
            period_value, seconds = divmod(seconds, period_seconds)
            result.append(f"{int(period_value)} {period_name}{'s' if period_value > 1 else ''}")

    return ', '.join(result)

def generate_token():
    return ''.join(random.choices(string.ascii_letters + string.digits, k=10))

async def get_reward_token(api_urls, api_keys, long_url):
    index = random.choice([0, 1])  # 50-50 probability
    shortzy = Shortzy(api_key=api_keys[index], base_site=api_urls[index])  # Use function parameters
    return await shortzy.convert(long_url)  # Fix `link` to `long_url`

async def get_shortlink(api_urls, api_keys, long_url):
    """Get a short link for the provided long URL using the Shortzy service."""
    if len(api_urls) < 2 or len(api_keys) < 2:
        raise ValueError("Insufficient API URLs or keys provided.")

    index = random.choice([0, 1])  # 50-50 probability
    shortzy = Shortzy(api_key=api_keys[index], base_site=api_urls[index])  # Use function parameters
    return await shortzy.convert(long_url)


def get_exp_time(seconds):
    periods = [('days', 86400), ('hours', 3600), ('mins', 60), ('secs', 1)]
    result = ''
    for period_name, period_seconds in periods:
        if seconds >= period_seconds:
            period_value, seconds = divmod(seconds, period_seconds)
            result += f'{int(period_value)} {period_name}'
    return result
