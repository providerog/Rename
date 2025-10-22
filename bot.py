import sys
import asyncio
import traceback
from aiohttp import web
from pyrogram import Client
from pyrogram.enums import ParseMode
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyromod import listen
from datetime import datetime
import time
from config import *
# from plugins import web_server
from pyrogram import utils


class Bot(Client):
    def __init__(self):
        super().__init__(
            name="Bot",
            api_hash=API_HASH,
            api_id=APP_ID,
            plugins={"root": "plugins"},
            workers=TG_BOT_WORKERS,
            bot_token=TG_BOT_TOKEN
        )
        self.LOGGER = LOGGER
        self.start_time = None
        self.processed_messages = 0
        self.invitelinks = []
        self.username = None

    async def start(self):
        print("Bot starting...")
        await super().start()
        print("Bot started!")
        self.start_time = time.time()
        self.uptime = datetime.now()

        usr_bot_me = await self.get_me()
        self.username = usr_bot_me.username
        print(f"🚀 Bot Started as {self.username}")

        # Notify bot owner
        await self.send_message(
            chat_id=OWNER_ID,
            text=f"<b><blockquote>🤖 Bᴏᴛ Rᴇsᴛᴀʀᴛᴇᴅ!</blockquote></b>\n\n",
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True
        )
        print("🌐 Web server started!")

    async def stop(self, *args):
        await super().stop()
        print("🛑 Bot Stopped.")
