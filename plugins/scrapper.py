from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from mega import Mega
import asyncio
import time
import logging
import json
from datetime import datetime
from database import db
import sys
from pyrogram.enums import ParseMode
import pytz
import os
from config import *

logger = logging.getLogger(__name__)

# Global storage for active sessions and prefixes - now with user isolation
mega_sessions = {}
user_prefixes = {}
active_operations = {}  # Track active operations per user

IST = pytz.timezone("Asia/Kolkata")

# Bot start time for uptime calculation
bot_start_time = datetime.now(IST)

# ═══════════════════════════════════════════════════════════════════════════════════
# 🔧 ʜᴇʟᴘᴇʀ ғᴜɴᴄᴛɪᴏɴs
# ═══════════════════════════════════════════════════════════════════════════════════

async def get_mega_session(user_id):
    """Get or create Mega session for user"""
    if user_id not in mega_sessions:
        session_data = await db.get_mega_session(user_id)
        if session_data:
            try:
                mega = Mega()
                mega_sessions[user_id] = mega.login(session_data['email'], session_data['password'])
                await db.update_mega_session_usage(user_id)
                return mega_sessions[user_id], True
            except Exception as e:
                return None, f"ʟᴏɢɪɴ ғᴀɪʟᴇᴅ: {str(e)}"
        else:
            return None, "ᴘʟᴇᴀsᴇ ʟᴏɢɪɴ ғɪʀsᴛ"
    return mega_sessions[user_id], True

def is_media_file(filename):
    """Check if file is a media file"""
    if not filename:
        return False

    media_exts = ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp', '.tiff', '.svg', '.ico',
                  '.mp4', '.avi', '.mkv', '.mov', '.wmv', '.flv', '.webm', '.m4v', '.3gp', '.ts', '.mts']

    return any(filename.lower().endswith(ext) for ext in media_exts)

def get_file_extension(filename):
    """Get file extension"""
    if '.' in filename:
        return '.' + filename.split('.')[-1]
    return ''

def has_prefix_already(filename, prefix):
    """Check if filename already starts with the prefix"""
    if filename.startswith("@dd_free_dishh"):
        return True
    return filename.startswith(prefix + " ") or filename.startswith(prefix)

async def check_user_limit(user_id, files_count):
    """Check if user can rename files based on limit"""
    user_data = await db.get_user(user_id)
    is_premium = await db.is_premium_user(user_id)

    if is_premium:
        return True, "ᴘʀᴇᴍɪᴜᴍ ᴜsᴇʀ - ᴜɴʟɪᴍɪᴛᴇᴅ"

    if not user_data:
        await db.add_user(user_id)
        user_data = await db.get_user(user_id)

    current_count = user_data.get('files_renamed', 0)
    remaining = FREE_LIMIT - current_count

    # If user has already reached the limit
    if remaining <= 0:
        return False, f"ʟɪᴍɪᴛ ᴇxᴄᴇᴇᴅᴇᴅ! ʏᴏᴜ ʜᴀᴠᴇ ᴜsᴇᴅ ᴀʟʟ {FREE_LIMIT} ғʀᴇᴇ ʀᴇɴᴀᴍᴇs"

    # If user wants to process more files than remaining, allow processing up to the limit
    if files_count > remaining:
        return True, f"ᴡɪʟʟ ᴘʀᴏᴄᴇss ᴏɴʟʏ {remaining} ғɪʟᴇs (ʀᴇᴍᴀɪɴɪɴɢ ʟɪᴍɪᴛ)"

    return True, f"ʀᴇᴍᴀɪɴɪɴɢ: {remaining - files_count} ᴀғᴛᴇʀ ᴛʜɪs ᴏᴘᴇʀᴀᴛɪᴏɴ"

async def optimized_batch_rename_async(mega_session, batch_files, prefix, user_id, progress_callback=None):
    """Async optimized batch rename with prefix only"""
    results = []

    for i, (old_name, file_id) in enumerate(batch_files):
        if user_id in active_operations and not active_operations[user_id].get('active', True):
            break

        try:
            if has_prefix_already(old_name, prefix):
                results.append(('skipped', old_name, None))
                continue

            # Correct renaming logic to avoid data loss and collisions
            new_name = f"{prefix} {old_name}"

            try:
                # Get the file node using its handle (file_id)
                file_node = mega_session.files.get(file_id)
                if file_node:
                     await asyncio.get_event_loop().run_in_executor(
                        None, mega_session.rename, file_node, new_name
                    )
                     results.append(('success', old_name, new_name))
                else:
                    results.append(('failed', old_name, "File node not found in session cache"))
            except Exception as e:
                logger.error(f"Rename failed for '{old_name}' with new name '{new_name}': {e}")
                results.append(('failed', old_name, str(e)))

        except Exception as e:
            logger.error(f"General error for '{old_name}': {e}")
            results.append(('failed', old_name, f"General error: {str(e)}"))

        if progress_callback and (i + 1) % 10 == 0:
            try:
                await progress_callback(i + 1, len(batch_files), results)
            except:
                pass

        await asyncio.sleep(0.01)

    return results

# ═══════════════════════════════════════════════════════════════════════════════════
# 🎯 ᴄᴏᴍᴍᴀɴᴅ ʜᴀɴᴅʟᴇʀs
# ═══════════════════════════════════════════════════════════════════════════════════

@Client.on_message(filters.private & filters.command(["prefix", "suffix"]))
async def prefix_command(client, message):
    """Set default prefix"""
    try:
        parts = message.text.split(None, 1)
        if len(parts) != 2:
            user_id = message.from_user.id
            current = user_prefixes.get(user_id, "Not set")
            await message.reply(
                f"**📝 ᴘʀᴇғɪx ᴍᴀɴᴀɢᴇᴍᴇɴᴛ**\n\n"
                f"**ᴄᴜʀʀᴇɴᴛ:** `{current}`\n\n"
                f"**ᴜsᴀɢᴇ:** `/prefix nyxking`\n"
                f"**ᴄʟᴇᴀʀ:** `/prefix clear`"
            )
            return

        prefix = parts[1].strip()
        user_id = message.from_user.id

        if prefix.lower() == "clear":
            if user_id in user_prefixes:
                del user_prefixes[user_id]
            await message.reply("✅ **ᴘʀᴇғɪx ᴄʟᴇᴀʀᴇᴅ!**")
        else:
            user_prefixes[user_id] = prefix
            await message.reply(f"✅ **ᴘʀᴇғɪx sᴇᴛ:** `{prefix}`")

    except Exception as e:
        await message.reply(f"❌ ᴇʀʀᴏʀ: {str(e)}")

@Client.on_message(filters.private & filters.command("login"))
async def mega_login(client, message):
    """Login to Mega"""
    try:
        await db.add_user(message.from_user.id, message.from_user.username)

        parts = message.text.split(None, 2)
        if len(parts) != 3:
            await message.reply(
                "**ᴜsᴀɢᴇ:** `/login your_email@example.com your_password`"
            )
            return

        email, password = parts[1], parts[2]
        await message.delete()

        status = await message.reply("🔄 ʟᴏɢɢɪɴɢ ɪɴᴛᴏ ᴍᴇɢᴀ.ɴᴢ...")

        try:
            # Run login in executor to avoid blocking
            mega = Mega()
            session = await asyncio.get_event_loop().run_in_executor(
                None, mega.login, email, password
            )
            mega_sessions[message.from_user.id] = session

            # Save to database and verify
            saved_successfully = await db.save_mega_session(message.from_user.id, email, password)
            if saved_successfully:
                await status.edit("<blockquote>✅ sᴜᴄᴄᴇssғᴜʟʟʏ ʟᴏɢɢᴇᴅ ɪɴᴛᴏ ᴍᴇɢᴀ.ɴᴢ..!</blockquote>")
            else:
                await status.edit(
                    "⚠️ **ʟᴏɢɪɴ sᴜᴄᴄᴇssғᴜʟ, ʙᴜᴛ ғᴀɪʟᴇᴅ ᴛᴏ sᴀᴠᴇ sᴇssɪᴏɴ!**\n\n"
                    "ᴛʜɪs ᴍᴇᴀɴs ᴛʜᴇ `/mega` ᴄᴏᴍᴍᴀɴᴅ ᴍɪɢʜᴛ ғᴀɪʟ.\n"
                    "ᴘʟᴇᴀsᴇ ᴛʀʏ `/logout` ᴀɴᴅ `/login` ᴀɢᴀɪɴ."
                )
        except Exception as e:
            await status.edit(f"❌ ʟᴏɢɪɴ ғᴀɪʟᴇᴅ: {str(e)}")

    except Exception as e:
        await message.reply(f"❌ ᴇʀʀᴏʀ: {str(e)}")

@Client.on_message(filters.private & filters.command("mega"))
async def mega_command_handler(client, message):
    """Handle /mega command"""
    try:
        user_id = message.from_user.id

        # Check if user already has an active operation
        if user_id in active_operations and active_operations[user_id].get('active', False):
            await message.reply(
                "⚠️ **ʏᴏᴜ ᴀʟʀᴇᴀᴅʏ ʜᴀᴠᴇ ᴀɴ ᴀᴄᴛɪᴠᴇ ᴏᴘᴇʀᴀᴛɪᴏɴ!**\n\n"
                "ᴘʟᴇᴀsᴇ ᴡᴀɪᴛ ғᴏʀ ɪᴛ ᴛᴏ ᴄᴏᴍᴘʟᴇᴛᴇ ᴏʀ ᴜsᴇ `/stop` ᴛᴏ ᴄᴀɴᴄᴇʟ."
            )
            return

        await db.add_user(user_id, message.from_user.username)
        await db.update_user_activity(user_id)

        # Check if user is logged in
        session, result = await get_mega_session(user_id)
        if not session:
            await message.reply(
                "❌ **ᴘʟᴇᴀsᴇ ʟᴏɢɪɴ ғɪʀsᴛ!**\n\n"
                "**ᴜsᴇ:** `/login your_email@example.com your_password`"
            )
            return

        # Check if user has prefix set
        if user_id not in user_prefixes:
            await message.reply(
                "❌ **ɴᴏ ᴘʀᴇғɪx sᴇᴛ!**\n\n"
                "**sᴇᴛ ᴘʀᴇғɪx ғɪʀsᴛ:** `/prefix nyxking`"
            )
            return

        prefix = user_prefixes[user_id]

        # Mark operation as active
        active_operations[user_id] = {'active': True, 'start_time': time.time()}

        try:
            await handle_mega_folder_processing_async(session, message, prefix, user_id)
        finally:
            # Always clean up active operation
            if user_id in active_operations:
                active_operations[user_id]['active'] = False

    except Exception as e:
        logger.error(f"Error in mega command: {e}")
        await message.reply(f"❌ ᴇʀʀᴏʀ: {str(e)}")
        # Clean up on error
        if user_id in active_operations:
            active_operations[user_id]['active'] = False

async def handle_mega_folder_processing_async(mega_session, message, prefix, user_id):
    """Handle mega folder processing with limits - async version"""
    try:
        status = await message.reply("🚀 **ᴘʀᴏᴄᴇssɪɴɢ sᴛᴀʀᴛɪɴɢ...**")
        start_time = time.time()

        # Get user credentials for second session
        session_data = await db.get_mega_session(user_id)
        if not session_data:
            return await status.edit("❌ ᴄᴏᴜʟᴅ ɴᴏᴛ ʀᴇᴛʀɪᴇᴠᴇ sᴇssɪᴏɴ ᴅᴀᴛᴀ ғᴏʀ ᴅᴜᴀʟ sᴄʀᴀᴘᴘᴇʀ.")

        # Create a second Mega session
        mega_session_2 = Mega()
        await asyncio.get_event_loop().run_in_executor(
            None, mega_session_2.login, session_data['email'], session_data['password']
        )

        # Get all files and cache (run in executor to avoid blocking)
        logger.info("🔥 Getting all files and caching...")
        all_files, _ = await asyncio.gather(
            asyncio.get_event_loop().run_in_executor(None, mega_session.get_files),
            asyncio.get_event_loop().run_in_executor(None, mega_session_2.get_files)
        )

        if not all_files:
            return await status.edit("❌ ɴᴏ ғɪʟᴇs ғᴏᴜɴᴅ ɪɴ ʏᴏᴜʀ ᴀᴄᴄᴏᴜɴᴛ")

        await status.edit(f"🚀 **ғᴏᴜɴᴅ {len(all_files)} ɪᴛᴇᴍs. sᴜᴘᴇʀ-ғᴀsᴛ ᴀsʏɴᴄ ғɪʟᴛᴇʀɪɴɢ...**")

        # Filter media files
        media_files_to_process = []
        for file_id, file_data in all_files.items():
            # Check if operation was cancelled
            if not active_operations.get(user_id, {}).get('active', True):
                return await status.edit("❌ **ᴏᴘᴇʀᴀᴛɪᴏɴ ᴄᴀɴᴄᴇʟʟᴇᴅ!**")

            if not isinstance(file_data, dict) or file_data.get('t') == 1:
                continue

            old_name = ""
            if isinstance(file_data.get('a'), dict):
                old_name = file_data['a'].get('n', '')
            elif isinstance(file_data.get('a'), str):
                try:
                    parsed = json.loads(file_data['a'])
                    old_name = parsed.get('n', '') if isinstance(parsed, dict) else ''
                except:
                    pass

            if old_name and is_media_file(old_name) and not has_prefix_already(old_name, prefix):
                media_files_to_process.append((old_name, file_id))

        total_media_files = len(media_files_to_process)
        if total_media_files == 0:
            return await status.edit("✅ **ɴᴏ ᴍᴇᴅɪᴀ ғɪʟᴇs ɴᴇᴇᴅ ʀᴇɴᴀᴍɪɴɢ!**")

        # Check user limits
        can_process, limit_msg = await check_user_limit(user_id, total_media_files)

        # Get user data to check remaining limit
        user_data = await db.get_user(user_id)
        is_premium = await db.is_premium_user(user_id)
        current_count = user_data.get('files_renamed', 0) if user_data else 0
        remaining_limit = FREE_LIMIT - current_count

        if not can_process:
            # Show premium plans only if user has 0 remaining files
            premium_buttons = []
            for plan_key, plan_data in PREMIUM_PLANS.items():
                premium_buttons.append([
                    InlineKeyboardButton(
                        f"💎 {plan_data['name']} - {plan_data['price']}",
                        callback_data=f"buy_{plan_key}"
                    )
                ])
            premium_buttons.append([
                InlineKeyboardButton("👨‍💼 ᴄᴏɴᴛᴀᴄᴛ ᴀᴅᴍɪɴ", url=f"https://t.me/{OWNER_TAG}")
            ])

            await status.edit(
                PREMIUM_MSG.format(free_limit=FREE_LIMIT),
                reply_markup=InlineKeyboardMarkup(premium_buttons)
            )
            return

        # If user has limited files remaining, process only that many
        if not is_premium and total_media_files > remaining_limit:
            media_files_to_process = media_files_to_process[:remaining_limit]
            total_media_files = len(media_files_to_process)
            await status.edit(f"🚀 **ᴘʀᴏᴄᴇssɪɴɢ {total_media_files} ғɪʟᴇs (ʏᴏᴜʀ ʀᴇᴍᴀɪɴɪɴɢ ʟɪᴍɪᴛ)...**")
        else:
            await status.edit(f"🚀 **ғᴏᴜɴᴅ {total_media_files} ᴍᴇᴅɪᴀ ғɪʟᴇs.ᴘʀᴏᴄᴇssɪɴɢ...**")

        renamed_count = 0
        failed_count = 0
        skipped_count = 0

        # Split files for dual scrapers
        mid_index = len(media_files_to_process) // 2
        files_batch_1 = media_files_to_process[:mid_index]
        files_batch_2 = media_files_to_process[mid_index:]

        total_processed_files = 0
        counter_lock = asyncio.Lock()

        async def run_scraper(session, files_batch):
            nonlocal renamed_count, failed_count, skipped_count, total_processed_files
            batch_size = 25

            for i in range(0, len(files_batch), batch_size):
                if not active_operations.get(user_id, {}).get('active', True):
                    break

                batch = files_batch[i:i + batch_size]
                results = await optimized_batch_rename_async(session, batch, prefix, user_id)

                async with counter_lock:
                    for result_type, old_name, new_name in results:
                        if result_type == 'success':
                            renamed_count += 1
                        elif result_type == 'skipped':
                            skipped_count += 1
                        else:
                            failed_count += 1

                    total_processed_files += len(batch)

                await asyncio.sleep(0.01)

        async def progress_updater():
            while active_operations.get(user_id, {}).get('active', True) and total_processed_files < total_media_files:
                async with counter_lock:
                    current_processed = total_processed_files
                    current_renamed = renamed_count
                    current_failed = failed_count
                    current_skipped = skipped_count

                if current_processed > 0:
                    try:
                        elapsed_time = time.time() - start_time
                        progress_percent = (current_processed / total_media_files) * 100
                        files_per_second = current_processed / elapsed_time if elapsed_time > 0 else 0
                        eta_seconds = (total_media_files - current_processed) / files_per_second if files_per_second > 0 else 0
                        eta_minutes = eta_seconds / 60

                        await status.edit(
                            f"🚀 **ᴘʀᴏᴄᴇssɪɴɢ... ({current_processed}/{total_media_files})**\n\n"
                            f"✅ **ʀᴇɴᴀᴍᴇᴅ:** {current_renamed}\n"
                            f"❌ **ғᴀɪʟᴇᴅ:** {current_failed}\n"
                            f"⏭️ **sᴋɪᴘᴘᴇᴅ:** {current_skipped}\n"
                            f"🏷️ **ᴘʀᴇғɪx:** `{prefix}`\n"
                            f"📊 **ᴘʀᴏɢʀᴇss:** {progress_percent:.1f}%\n"
                            f"⚡ **sᴘᴇᴇᴅ:** {files_per_second:.1f} ғɪʟᴇs/sᴇᴄ\n"
                            f"⏱️ **ᴇᴛᴀ:** ~{eta_minutes:.1f}ᴍɪɴ\n"
                        )
                    except Exception:
                        pass # Ignore errors in progress updates

                await asyncio.sleep(2)

        # Run scrapers and progress updater concurrently
        scraper_task_1 = run_scraper(mega_session, files_batch_1)
        scraper_task_2 = run_scraper(mega_session_2, files_batch_2)
        progress_task = progress_updater()

        await asyncio.gather(scraper_task_1, scraper_task_2, progress_task)

        # Update user's renamed files count
        await db.increment_files_renamed(user_id, renamed_count)

        # Final result
        total_time = time.time() - start_time
        avg_speed = total_media_files / total_time if total_time > 0 else 0

        # Add info about remaining limit for free users
        limit_info = ""
        if not is_premium:
            new_remaining = remaining_limit - renamed_count
            if new_remaining <= 0:
                limit_info = f"\n\n🚨 **ʏᴏᴜ'ᴠᴇ ʀᴇᴀᴄʜᴇᴅ ʏᴏᴜʀ ғʀᴇᴇ ʟɪᴍɪᴛ!**\n💎 **ᴜᴘɢʀᴀᴅᴇ ᴛᴏ ᴘʀᴇᴍɪᴜᴍ ғᴏʀ ᴜɴʟɪᴍɪᴛᴇᴅ ʀᴇɴᴀᴍɪɴɢ**"
            else:
                limit_info = f"\n\n🎯 **ʀᴇᴍᴀɪɴɪɴɢ ғʀᴇᴇ ʟɪᴍɪᴛ:** {new_remaining} ғɪʟᴇs"

        result_text = (
            f"🚀 <b>ᴘʀᴏᴄᴇssɪɴɢ ᴄᴏᴍᴘʟᴇᴛᴇ!</b>\n\n"
            f"✅ <b>sᴜᴄᴄᴇssғᴜʟʟʏ ʀᴇɴᴀᴍᴇᴅ:</b> {renamed_count}\n"
            f"❌ <b>ғᴀɪʟᴇᴅ:</b> {failed_count}\n"
            f"⏭️ <b>sᴋɪᴘᴘᴇᴅ:</b> {skipped_count}\n"
            f"🏷️ <b>ᴘʀᴇғɪx ᴀᴘᴘʟɪᴇᴅ:</b> <code>{prefix}</code>\n"
            f"⏱️ <b>ᴛᴏᴛᴀʟ ᴛɪᴍᴇ:</b> {total_time:.1f} sᴇᴄᴏɴᴅs ({total_time/60:.1f} ᴍɪɴ)\n"
            f"⚡ <b>ᴀᴠᴇʀᴀɢᴇ sᴘᴇᴇᴅ:</b> {avg_speed:.1f} ғɪʟᴇs/sᴇᴄ\n"
            f"📊 <b>sᴜᴄᴄᴇss ʀᴀᴛᴇ:</b> {(renamed_count/(renamed_count+failed_count)*100) if (renamed_count+failed_count) > 0 else 0:.1f}%\n"
            f"🔄 <b>ᴍᴏᴅᴇ:</b> ᴅᴜᴀʟ-sᴄʀᴀᴘᴘᴇʀ ᴀsʏɴᴄ\n"
            f"🕒 <b>ᴄᴏᴍᴘʟᴇᴛᴇᴅ:</b> {datetime.now().strftime('%H:%M:%S')}"
            f"{limit_info}"
        )

        await status.edit(result_text)

    except Exception as e:
        logger.error(f"❌ Async processing error: {e}")
        await message.reply(f"❌ **ᴀsʏɴᴄ ᴘʀᴏᴄᴇssɪɴɢ ᴇʀʀᴏʀ:** {str(e)}")

@Client.on_message(filters.private & filters.command("status"))
async def mega_status(client, message):
    """Check mega session status"""
    try:
        user_id = message.from_user.id
        await db.add_user(user_id, message.from_user.username)
        await db.update_user_activity(user_id)

        session, result = await get_mega_session(user_id)
        user_data = await db.get_user(user_id)
        is_premium = await db.is_premium_user(user_id)
        premium_info = await db.get_user_premium_info(user_id)

        # Check if user has active operation
        is_active = user_id in active_operations and active_operations[user_id].get('active', False)
        active_time = ""
        if is_active:
            start_time = active_operations[user_id].get('start_time', time.time())
            elapsed = time.time() - start_time
            active_time = f"\n🔄 **ᴀᴄᴛɪᴠᴇ ᴏᴘᴇʀᴀᴛɪᴏɴ:** {elapsed/60:.1f} ᴍɪɴᴜᴛᴇs"

        if session:
            try:
                files_renamed = user_data.get('files_renamed', 0) if user_data else 0
                remaining_files = "ᴜɴʟɪᴍɪᴛᴇᴅ" if is_premium else str(FREE_LIMIT - files_renamed)

                premium_text = ""
                if is_premium and premium_info:
                    end_date = premium_info['end_date'].strftime('%d-%m-%Y')
                    premium_text = f"💎 **ᴘʀᴇᴍɪᴜᴍ:** {premium_info['plan_type']} (ᴇxᴘɪʀᴇs: {end_date})\n"

                status_text = (
                    f"✅ **ᴍᴇɢᴀ sᴇssɪᴏɴ ᴀᴄᴛɪᴠᴇ**\n\n"
                    f"🏷️ **ᴄᴜʀʀᴇɴᴛ ᴘʀᴇғɪx:** `{user_prefixes.get(user_id, 'ɴᴏᴛ sᴇᴛ')}`\n"
                    f"📊 **ғɪʟᴇs ʀᴇɴᴀᴍᴇᴅ:** {files_renamed}\n"
                    f"🎯 **ʀᴇᴍᴀɪɴɪɴɢ:** {remaining_files}\n"
                    f"{premium_text}"
                )
                await message.reply(status_text)
            except Exception as e:
                await message.reply(f"✅ **ᴍᴇɢᴀ sᴇssɪᴏɴ ᴀᴄᴛɪᴠᴇ** (ᴅᴇᴛᴀɪʟs ᴜɴᴀᴠᴀɪʟᴀʙʟᴇ: {str(e)})")
        else:
            await message.reply(
                f"❌ **ɴᴏᴛ ʟᴏɢɢᴇᴅ ɪɴ**\n\n"
                f"**ᴇʀʀᴏʀ:** {result}\n"
                f"**ᴜsᴇ:** `/login email password`"
            )
    except Exception as e:
        await message.reply(f"❌ ᴇʀʀᴏʀ ᴄʜᴇᴄᴋɪɴɢ sᴛᴀᴛᴜs: {str(e)}")

@Client.on_message(filters.private & filters.command("logout"))
async def mega_logout(client, message):
    """Logout from mega"""
    try:
        user_id = message.from_user.id

        # Cancel any active operations
        if user_id in active_operations:
            active_operations[user_id]['active'] = False

        # Clear session
        if user_id in mega_sessions:
            del mega_sessions[user_id]

        await db.delete_mega_session(user_id)
        await message.reply("✅ **sᴜᴄᴄᴇssғᴜʟʟʏ ʟᴏɢɢᴇᴅ ᴏᴜᴛ ғʀᴏᴍ ᴍᴇɢᴀ**")
    except Exception as e:
        await message.reply(f"❌ ᴇʀʀᴏʀ: {str(e)}")


@Client.on_message(filters.private & filters.command("clear") & filters.user(ADMINS))
async def clear_all_requests(client: Client, message: Message):
    """Clear all join requests from database"""
    try:
        # Delete all join requests
        result = await db.join_requests.delete_many({})

        await message.reply(
            f"🗑️ **ᴀʟʟ ᴊᴏɪɴ ʀᴇǫᴜᴇsᴛs ᴄʟᴇᴀʀᴇᴅ!**\n\n"
            f"✅ **ᴅᴇʟᴇᴛᴇᴅ:** {result.deleted_count} ʀᴇǫᴜᴇsᴛs"
        )

    except Exception as e:
        await message.reply(f"❌ **ᴇʀʀᴏʀ:** {str(e)}")


@Client.on_message(filters.private & filters.command("help"))
async def mega_help(client, message):
    """Show mega commands help"""
    help_text = (
        f"🚀 **ᴍᴇɢᴀ ʀᴇɴᴀᴍᴇʀ - ᴍᴜʟᴛɪ-ᴜsᴇʀ ᴀsʏɴᴄ ᴠᴇʀsɪᴏɴ**\n\n"
        f"**sᴇᴛᴜᴘ:**\n"
        f"`/login email password` - ʟᴏɢɪɴ ᴛᴏ ᴍᴇɢᴀ\n"
        f"`/prefix nyxking` - sᴇᴛ ғɪʟᴇɴᴀᴍᴇ ᴘʀᴇғɪx\n\n"
        f"**ᴜsᴀɢᴇ:**\n"
        f"`/mega` - ʀᴇɴᴀᴍᴇ ᴀʟʟ ᴍᴇᴅɪᴀ ғɪʟᴇs (ᴀsʏɴᴄ ᴍᴜʟᴛɪ-ᴜsᴇʀ)\n\n"
        f"**ᴍᴀɴᴀɢᴇᴍᴇɴᴛ:**\n"
        f"`/status` - ᴄʜᴇᴄᴋ ʟᴏɢɪɴ sᴛᴀᴛᴜs & ᴀᴄᴛɪᴠᴇ ᴏᴘᴇʀᴀᴛɪᴏɴs\n"
        f"`/logout` - ʟᴏɢᴏᴜᴛ ғʀᴏᴍ ᴍᴇɢᴀ\n"
        f"`/prefix clear` - ᴄʟᴇᴀʀ ᴄᴜʀʀᴇɴᴛ ᴘʀᴇғɪx\n"
        f"`/test` - ǫᴜɪᴄᴋ ᴛᴇsᴛ ᴡɪᴛʜ 10 ғɪʟᴇs\n"
        f"`/stop` - ᴄᴀɴᴄᴇʟ ᴀᴄᴛɪᴠᴇ ᴏᴘᴇʀᴀᴛɪᴏɴ\n\n"
        f"**🚀 ᴍᴜʟᴛɪ-ᴜsᴇʀ ᴀsʏɴᴄ ғᴇᴀᴛᴜʀᴇs:**\n"
        f"✅ **ᴄᴏɴᴄᴜʀʀᴇɴᴛ ᴘʀᴏᴄᴇssɪɴɢ** - ᴍᴜʟᴛɪᴘʟᴇ ᴜsᴇʀs ᴄᴀɴ ʀᴇɴᴀᴍᴇ sɪᴍᴜʟᴛᴀɴᴇᴏᴜsʟʏ\n"
        f"✅ **ᴀsʏɴᴄ ᴏᴘᴇʀᴀᴛɪᴏɴs** - ɴᴏɴ-ʙʟᴏᴄᴋɪɴɢ ᴘʀᴏᴄᴇssɪɴɢ\n"
        f"✅ **ᴇxᴇᴄᴜᴛᴏʀ ᴛʜʀᴇᴀᴅs** - ᴍᴇɢᴀ ᴏᴘs ɪɴ sᴇᴘᴀʀᴀᴛᴇ ᴛʜʀᴇᴀᴅs\n"
        f"✅ **ᴏᴘᴇʀᴀᴛɪᴏɴ ᴛʀᴀᴄᴋɪɴɢ** - ᴘʀᴇᴠᴇɴᴛs ᴅᴜᴘʟɪᴄᴀᴛᴇ ᴏᴘs\n"
        f"✅ **ᴄᴀɴᴄᴇʟʟᴀᴛɪᴏɴ sᴜᴘᴘᴏʀᴛ** - sᴛᴏᴘ ᴏᴘᴇʀᴀᴛɪᴏɴs ᴀɴʏᴛɪᴍᴇ\n"
        f"✅ **sᴍᴀʀᴛ ʙᴀᴛᴄʜɪɴɢ** - 50 ғɪʟᴇs ᴘᴇʀ ʙᴀᴛᴄʜ\n"
        f"✅ **ʀᴇᴀʟ-ᴛɪᴍᴇ ᴘʀᴏɢʀᴇss** - ʟɪᴠᴇ ᴜᴘᴅᴀᴛᴇs\n\n"
        f"**💎 ᴘʀᴇᴍɪᴜᴍ sʏsᴛᴇᴍ:**\n"
        f"🆓 **ғʀᴇᴇ:** {FREE_LIMIT} ғɪʟᴇs ʟɪᴍɪᴛ\n"
        f"💎 **ᴘʀᴇᴍɪᴜᴍ:** ᴜɴʟɪᴍɪᴛᴇᴅ ʀᴇɴᴀᴍɪɴɢ\n\n"
        f"**ᴘᴇʀғᴏʀᴍᴀɴᴄᴇ (ᴍᴜʟᴛɪ-ᴜsᴇʀ ᴀsʏɴᴄ):**\n"
        f"🚀 **sᴘᴇᴇᴅ:** ~3-7 ғɪʟᴇs/sᴇᴄ (5-10x ғᴀsᴛᴇʀ)\n"
        f"🚀 **1000 ғɪʟᴇs:** ~3-7 ᴍɪɴᴜᴛᴇs\n"
        f"🚀 **4000 ғɪʟᴇs:** ~10-20 ᴍɪɴᴜᴛᴇs\n"
        f"👥 **ᴍᴜʟᴛɪ-ᴜsᴇʀ:** ᴀʟʟ ᴜsᴇʀs ᴄᴀɴ ᴡᴏʀᴋ sɪᴍᴜʟᴛᴀɴᴇᴏᴜsʟʏ\n\n"
        f"**sᴜᴘᴘᴏʀᴛᴇᴅ ᴍᴇᴅɪᴀ:**\n"
        f"📷 **ɪᴍᴀɢᴇs:** jpg, png, gif, webp, etc.\n"
        f"🎬 **ᴠɪᴅᴇᴏs:** mp4, mkv, avi, mov, etc.\n\n"
        f"**ᴇxᴀᴍᴘʟᴇ ʀᴇɴᴀᴍɪɴɢ:**\n"
        f"📁 `movie.mp4` → `nyxking movie.mp4`\n\n"
        f"**💡 ᴛʜɪs ɪs ᴛʜᴇ ғᴀsᴛᴇsᴛ ᴍᴜʟᴛɪ-ᴜsᴇʀ ᴠᴇʀsɪᴏɴ ᴘᴏssɪʙʟᴇ!**\n"
        f"**🔥 ɴᴏ ᴍᴏʀᴇ ᴡᴀɪᴛɪɴɢ ғᴏʀ ᴏᴛʜᴇʀ ᴜsᴇʀs!**"
    )
    await message.reply(help_text)

@Client.on_message(filters.private & filters.command("test"))
async def quick_test(client, message):
    """Quick test with first 10 media files"""
    try:
        user_id = message.from_user.id

        # Check if user already has an active operation
        if user_id in active_operations and active_operations[user_id].get('active', False):
            await message.reply(
                "⚠️ **ʏᴏᴜ ᴀʟʀᴇᴀᴅʏ ʜᴀᴠᴇ ᴀɴ ᴀᴄᴛɪᴠᴇ ᴏᴘᴇʀᴀᴛɪᴏɴ!**\n\n"
                "ᴘʟᴇᴀsᴇ ᴡᴀɪᴛ ғᴏʀ ɪᴛ ᴛᴏ ᴄᴏᴍᴘʟᴇᴛᴇ ᴏʀ ᴜsᴇ `/stop` ᴛᴏ ᴄᴀɴᴄᴇʟ."
            )
            return

        await db.add_user(user_id, message.from_user.username)
        await db.update_user_activity(user_id)

        # Check login and prefix
        session, result = await get_mega_session(user_id)
        if not session:
            return await message.reply("❌ ᴘʟᴇᴀsᴇ ʟᴏɢɪɴ ғɪʀsᴛ: `/login email password`")

        if user_id not in user_prefixes:
            return await message.reply("❌ ᴘʟᴇᴀsᴇ sᴇᴛ ᴘʀᴇғɪx ғɪʀsᴛ: `/prefix nyxking`")

        prefix = user_prefixes[user_id]

        # Mark operation as active
        active_operations[user_id] = {'active': True, 'start_time': time.time()}

        try:
            status = await message.reply("🧪 **ǫᴜɪᴄᴋ ᴛᴇsᴛ - ᴀsʏɴᴄ ᴘʀᴏᴄᴇssɪɴɢ ғɪʀsᴛ 10 ᴍᴇᴅɪᴀ ғɪʟᴇs...**")

            # Get files and filter first 10 media files (async)
            all_files = await asyncio.get_event_loop().run_in_executor(
                None, session.get_files
            )
            media_files = []

            for file_id, file_data in all_files.items():
                if len(media_files) >= 10:
                    break

                if not isinstance(file_data, dict) or file_data.get('t') == 1:
                    continue

                old_name = ""
                if isinstance(file_data.get('a'), dict):
                    old_name = file_data['a'].get('n', '')
                elif isinstance(file_data.get('a'), str):
                    try:
                        parsed = json.loads(file_data['a'])
                        old_name = parsed.get('n', '') if isinstance(parsed, dict) else ''
                    except:
                        pass

                if old_name and is_media_file(old_name) and not has_prefix_already(old_name, prefix):
                    media_files.append((old_name, file_id))

            if not media_files:
                return await status.edit("✅ **ɴᴏ ᴍᴇᴅɪᴀ ғɪʟᴇs ɴᴇᴇᴅ ʀᴇɴᴀᴍɪɴɢ ɪɴ ғɪʀsᴛ 10!**")

            # Process the files asynchronously
            start_time = time.time()
            results = await optimized_batch_rename_async(session, media_files, prefix, user_id)
            end_time = time.time()

            # Count results
            success_count = sum(1 for r in results if r[0] == 'success')
            failed_count = sum(1 for r in results if r[0] == 'failed')
            skipped_count = sum(1 for r in results if r[0] == 'skipped')

            # Update user's renamed files count
            await db.increment_files_renamed(user_id, success_count)

            result_text = (
                f"🧪 **ᴀsʏɴᴄ ǫᴜɪᴄᴋ ᴛᴇsᴛ ᴄᴏᴍᴘʟᴇᴛᴇ!**\n\n"
                f"✅ **ʀᴇɴᴀᴍᴇᴅ:** {success_count}\n"
                f"❌ **ғᴀɪʟᴇᴅ:** {failed_count}\n"
                f"⏭️ **sᴋɪᴘᴘᴇᴅ:** {skipped_count}\n"
                f"⏱️ **ᴛɪᴍᴇ:** {end_time - start_time:.1f} sᴇᴄᴏɴᴅs\n"
                f"⚡ **sᴘᴇᴇᴅ:** {len(media_files) / (end_time - start_time):.1f} ғɪʟᴇs/sᴇᴄ\n"
                f"🔧 **ᴍᴇᴛʜᴏᴅ:** ᴍᴜʟᴛɪ-ᴜsᴇʀ ᴀsʏɴᴄ ᴏᴘᴛɪᴍɪᴢᴇᴅ\n"
                f"📊 **sᴜᴄᴄᴇss ʀᴀᴛᴇ:** {(success_count/(success_count+failed_count)*100) if (success_count+failed_count) > 0 else 0:.1f}%\n"
                f"👥 **ᴄᴏɴᴄᴜʀʀᴇɴᴄʏ:** ᴏᴛʜᴇʀ ᴜsᴇʀs ᴄᴀɴ ᴡᴏʀᴋ sɪᴍᴜʟᴛᴀɴᴇᴏᴜsʟʏ\n\n"
                f"🚀 **ʀᴇᴀᴅʏ ғᴏʀ ғᴜʟʟ ᴘʀᴏᴄᴇssɪɴɢ ᴡɪᴛʜ `/mega`**\n\n"
                f"💡 **ғᴀsᴛᴇsᴛ ᴍᴜʟᴛɪ-ᴜsᴇʀ ᴠᴇʀsɪᴏɴ ᴘᴏssɪʙʟᴇ!**"
            )

            await status.edit(result_text)

        finally:
            # Clean up active operation
            if user_id in active_operations:
                active_operations[user_id]['active'] = False

    except Exception as e:
        logger.error(f"Quick test error: {e}")
        await message.reply(f"❌ ᴀsʏɴᴄ ǫᴜɪᴄᴋ ᴛᴇsᴛ ғᴀɪʟᴇᴅ: {str(e)}")
        # Clean up on error
        if user_id in active_operations:
            active_operations[user_id]['active'] = False

@Client.on_message(filters.private & filters.command("stop"))
async def mega_stop(client, message):
    """Emergency stop - cancel active operation"""
    try:
        user_id = message.from_user.id

        # Check if user has active operation
        if user_id not in active_operations or not active_operations[user_id].get('active', False):
            await message.reply("❌ **ɴᴏ ᴀᴄᴛɪᴠᴇ ᴏᴘᴇʀᴀᴛɪᴏɴ ᴛᴏ ᴄᴀɴᴄᴇʟ**")
            return

        # Cancel the operation
        active_operations[user_id]['active'] = False

        await message.reply(
            f"🛑 **ᴏᴘᴇʀᴀᴛɪᴏɴ ᴄᴀɴᴄᴇʟʟᴇᴅ!**\n\n"
            f"✅ ʏᴏᴜʀ ᴀᴄᴛɪᴠᴇ ʀᴇɴᴀᴍɪɴɢ ᴏᴘᴇʀᴀᴛɪᴏɴ ʜᴀs ʙᴇᴇɴ sᴛᴏᴘᴘᴇᴅ\n"
            f"✅ ʏᴏᴜ ᴄᴀɴ sᴛᴀʀᴛ ᴀ ɴᴇᴡ ᴏᴘᴇʀᴀᴛɪᴏɴ ɴᴏᴡ\n\n"
            f"ᴜsᴇ `/mega` ᴛᴏ sᴛᴀʀᴛ ᴀɢᴀɪɴ"
        )

    except Exception as e:
        await message.reply(f"❌ ᴇʀʀᴏʀ: {str(e)}")

# ═══════════════════════════════════════════════════════════════════════════════════
# 🧹 ᴄʟᴇᴀɴᴜᴘ ᴀɴᴅ ᴍᴀɪɴᴛᴇɴᴀɴᴄᴇ
# ═══════════════════════════════════════════════════════════════════════════════════

async def cleanup_inactive_operations():
    """Cleanup operations that have been running too long"""
    try:
        current_time = time.time()
        to_remove = []

        for user_id, operation in active_operations.items():
            if operation.get('active', False):
                start_time = operation.get('start_time', current_time)
                # If operation is running for more than 2 hours, mark as inactive
                if current_time - start_time > 7200:  # 2 hours
                    operation['active'] = False
                    to_remove.append(user_id)
                    logger.warning(f"Cleaned up long-running operation for user {user_id}")

        # Remove cleaned up operations
        for user_id in to_remove:
            if user_id in active_operations:
                del active_operations[user_id]

        return len(to_remove)

    except Exception as e:
        logger.error(f"Error in cleanup_inactive_operations: {e}")
        return 0

# Schedule cleanup task
async def periodic_cleanup():
    """Periodic cleanup task"""
    while True:
        try:
            await asyncio.sleep(3600)  # Run every hour
            cleaned = await cleanup_inactive_operations()
            if cleaned > 0:
                logger.info(f"Cleaned up {cleaned} inactive operations")
        except Exception as e:
            logger.error(f"Error in periodic cleanup: {e}")

# Start cleanup task when module loads
asyncio.create_task(periodic_cleanup())

# ═══════════════════════════════════════════════════════════════════════════════════
# 📊 ᴀᴅᴍɪɴ ᴄᴏᴍᴍᴀɴᴅs
# ═══════════════════════════════════════════════════════════════════════════════════

@Client.on_message(filters.private & filters.command("active") & filters.user(ADMINS))
async def show_active_operations(client, message):
    """Show active operations (admin only)"""
    try:
        if not active_operations:
            await message.reply("📭 **ɴᴏ ᴀᴄᴛɪᴠᴇ ᴏᴘᴇʀᴀᴛɪᴏɴs**")
            return

        text = "🔄 **ᴀᴄᴛɪᴠᴇ ᴏᴘᴇʀᴀᴛɪᴏɴs:**\n\n"
        current_time = time.time()

        for user_id, operation in active_operations.items():
            if operation.get('active', False):
                start_time = operation.get('start_time', current_time)
                elapsed = current_time - start_time
                text += f"👤 **ᴜsᴇʀ:** `{user_id}`\n"
                text += f"⏱️ **ʀᴜɴɴɪɴɢ:** {elapsed/60:.1f} ᴍɪɴᴜᴛᴇs\n"
                text += f"🏷️ **ᴘʀᴇғɪx:** `{user_prefixes.get(user_id, 'ɴᴏᴛ sᴇᴛ')}`\n\n"

        if text == "🔄 **ᴀᴄᴛɪᴠᴇ ᴏᴘᴇʀᴀᴛɪᴏɴs:**\n\n":
            text = "📭 **ɴᴏ ᴀᴄᴛɪᴠᴇ ᴏᴘᴇʀᴀᴛɪᴏɴs**"

        await message.reply(text)

    except Exception as e:
        await message.reply(f"❌ ᴇʀʀᴏʀ: {str(e)}")

@Client.on_message(filters.private & filters.command("killall") & filters.user(ADMINS))
async def kill_all_operations(client, message):
    """Kill all active operations (admin only)"""
    try:
        killed_count = 0
        for user_id, operation in active_operations.items():
            if operation.get('active', False):
                operation['active'] = False
                killed_count += 1

        # Clear all active operations
        active_operations.clear()

        await message.reply(
            f"🛑 **ᴀʟʟ ᴏᴘᴇʀᴀᴛɪᴏɴs ᴋɪʟʟᴇᴅ!**\n\n"
            f"✅ **ᴋɪʟʟᴇᴅ:** {killed_count} ᴀᴄᴛɪᴠᴇ ᴏᴘᴇʀᴀᴛɪᴏɴs\n"
            f"✅ **sᴛᴀᴛᴜs:** ᴀʟʟ ᴜsᴇʀs ᴄᴀɴ sᴛᴀʀᴛ ɴᴇᴡ ᴏᴘᴇʀᴀᴛɪᴏɴs"
        )

    except Exception as e:
        await message.reply(f"❌ ᴇʀʀᴏʀ: {str(e)}")

@Client.on_message(filters.private & filters.command("sessions") & filters.user(ADMINS))
async def show_mega_sessions(client, message):
    """Show active mega sessions (admin only)"""
    try:
        if not mega_sessions:
            await message.reply("📭 **ɴᴏ ᴀᴄᴛɪᴠᴇ ᴍᴇɢᴀ sᴇssɪᴏɴs**")
            return

        text = f"🔐 **ᴀᴄᴛɪᴠᴇ ᴍᴇɢᴀ sᴇssɪᴏɴs:** {len(mega_sessions)}\n\n"

        for i, user_id in enumerate(mega_sessions.keys(), 1):
            prefix = user_prefixes.get(user_id, 'ɴᴏᴛ sᴇᴛ')
            is_active = user_id in active_operations and active_operations[user_id].get('active', False)
            status_emoji = "🔄" if is_active else "💤"

            text += f"{status_emoji} **{i}.** ᴜsᴇʀ: `{user_id}` | ᴘʀᴇғɪx: `{prefix}`\n"

        await message.reply(text)

    except Exception as e:
        await message.reply(f"❌ ᴇʀʀᴏʀ: {str(e)}")


# ═══════════════════════════════════════════════════════════════════════════════════
# 📊 Stats Command
# ═══════════════════════════════════════════════════════════════════════════════════

@Client.on_message(filters.private & filters.command("stats") & filters.user(ADMINS))
async def stats_command(client: Client, message: Message):
    """Show bot statistics"""
    try:
        # Get database stats
        total_users = await db.total_users_count()
        premium_users = await db.premium_users_count()
        free_users = total_users - premium_users

        # Get today's stats
        today = datetime.now(IST).date()
        today_users = await db.get_users_joined_today(today)

        # Get files renamed stats
        total_files_renamed = await db.get_total_files_renamed()

        # Get mega sessions
        active_sessions = await db.get_active_mega_sessions_count()

        # System stats
        uptime = datetime.now(IST) - bot_start_time if 'bot_start_time' in globals() else "Unknown"

        stats_text = (
            f"📊 **ᴍᴇɢᴀ ʀᴇɴᴀᴍᴇʀ ʙᴏᴛ sᴛᴀᴛs**\n\n"
            f"👥 **ᴜsᴇʀs:**\n"
            f"├ ᴛᴏᴛᴀʟ: `{total_users:,}`\n"
            f"├ ᴘʀᴇᴍɪᴜᴍ: `{premium_users:,}`\n"
            f"├ ғʀᴇᴇ: `{free_users:,}`\n"
            f"└ ᴛᴏᴅᴀʏ: `{today_users:,}`\n\n"
            f"📁 **ғɪʟᴇs:**\n"
            f"└ ᴛᴏᴛᴀʟ ʀᴇɴᴀᴍᴇᴅ: `{total_files_renamed:,}`\n\n"
            f"🔗 **ᴍᴇɢᴀ sᴇssɪᴏɴs:**\n"
            f"└ ᴀᴄᴛɪᴠᴇ: `{active_sessions:,}`\n\n"
            f"⏰ **ᴜᴘᴛɪᴍᴇ:** `{str(uptime).split('.')[0] if uptime != 'Unknown' else uptime}`\n"
            f"🕒 **ᴄᴜʀʀᴇɴᴛ ᴛɪᴍᴇ:** `{datetime.now(IST).strftime('%d/%m/%Y %H:%M:%S')}`"
        )

        await message.reply(stats_text)

    except Exception as e:
        logger.error(f"Stats command error: {e}")
        await message.reply(f"❌ **ᴇʀʀᴏʀ:** {str(e)}")

@Client.on_message(filters.private & filters.command("broadcast") & filters.user(ADMINS))
async def broadcast_message(client: Client, message: Message):
    """Broadcast message to all users"""
    try:
        # Check if message is a reply
        if not message.reply_to_message:
            await message.reply("📝 **ᴘʟᴇᴀsᴇ ʀᴇᴘʟʏ ᴛᴏ ᴀ ᴍᴇssᴀɢᴇ ᴛᴏ ʙʀᴏᴀᴅᴄᴀsᴛ**")
            return

        # Get all users
        all_users = await db.get_all_users()
        total_users = len(all_users)

        # Confirmation message
        confirmation_text = (
            f"📢 **ᴄᴏɴғɪʀᴍ ʙʀᴏᴀᴅᴄᴀsᴛ**\n\n"
            f"**ᴍᴇssᴀɢᴇ:** ᴡɪʟʟ ʙᴇ sᴇɴᴛ ᴛᴏ `{total_users:,}` ᴜsᴇʀs\n"
            f"**ᴛʏᴘᴇ:** `{message.reply_to_message.media or 'ᴛᴇxᴛ'}`\n\n"
            f"⚠️ **ᴛʜɪs ᴀᴄᴛɪᴏɴ ɪs ɪʀʀᴇᴠᴇʀsɪʙʟᴇ!**"
        )

        # Store broadcast data
        broadcast_data[message.id] = {
            "users": all_users,
            "message": message.reply_to_message,
            "text": message.reply_to_message.text
        }

        # Confirmation buttons
        buttons = [
            [
                InlineKeyboardButton("✅ ᴄᴏɴғɪʀᴍ", callback_data=f"broadcast_confirm_{message.id}"),
                InlineKeyboardButton("❌ ᴄᴀɴᴄᴇʟ", callback_data="broadcast_cancel")
            ]
        ]

        await message.reply(
            confirmation_text,
            reply_markup=InlineKeyboardMarkup(buttons)
        )

    except Exception as e:
        logger.error(f"Broadcast command error: {e}")
        await message.reply(f"❌ **ᴇʀʀᴏʀ:** {str(e)}")


broadcast_data = {}

@Client.on_callback_query(filters.regex("broadcast_"))
async def broadcast_callbacks(client: Client, callback_query):
    """Handle broadcast callback queries"""
    try:
        if callback_query.from_user.id not in ADMINS:
            return await callback_query.answer("❌ ᴜɴᴀᴜᴛʜᴏʀɪᴢᴇᴅ!", show_alert=True)

        data = callback_query.data

        if data == "broadcast_cancel":
            await callback_query.message.edit_text("❌ **ʙʀᴏᴀᴅᴄᴀsᴛ ᴄᴀɴᴄᴇʟʟᴇᴅ!**")
            await callback_query.answer()

        elif data.startswith("broadcast_confirm_"):
            msg_id = int(data.split("_")[2])

            if msg_id not in broadcast_data:
                return await callback_query.answer("❌ ʙʀᴏᴀᴅᴄᴀsᴛ ᴅᴀᴛᴀ ɴᴏᴛ ғᴏᴜɴᴅ!", show_alert=True)

            broadcast_info = broadcast_data[msg_id]
            users = broadcast_info['users']
            broadcast_msg = broadcast_info['message']
            broadcast_text = broadcast_info['text']

            # Start broadcasting
            await callback_query.message.edit_text("🚀 **ʙʀᴏᴀᴅᴄᴀsᴛɪɴɢ sᴛᴀʀᴛᴇᴅ...**")
            await callback_query.answer()

            # Broadcast process
            success_count = 0
            failed_count = 0
            blocked_count = 0

            start_time = time.time()

            for i, user_id in enumerate(users, 1):
                try:
                    if broadcast_msg:
                        # Copy the replied message
                        await broadcast_msg.copy(user_id)
                    else:
                        # Send text message
                        await client.send_message(user_id, broadcast_text)

                    success_count += 1

                except Exception as e:
                    error_str = str(e).lower()
                    if "blocked" in error_str or "user is deactivated" in error_str or "chat not found" in error_str:
                        blocked_count += 1
                        # Remove blocked users from database
                        await db.delete_user(user_id)
                    else:
                        failed_count += 1

                # Update progress every 50 users
                if i % 50 == 0 or i == len(users):
                    try:
                        elapsed_time = time.time() - start_time
                        remaining_users = len(users) - i

                        if i > 0 and elapsed_time > 0:
                            users_per_second = i / elapsed_time
                            eta_seconds = remaining_users / users_per_second if users_per_second > 0 else 0
                            eta_minutes = eta_seconds / 60
                        else:
                            eta_minutes = 0

                        progress_percent = (i / len(users)) * 100

                        progress_text = (
                            f"📢 **ʙʀᴏᴀᴅᴄᴀsᴛɪɴɢ... ({i}/{len(users)})**\n\n"
                            f"✅ **sᴜᴄᴄᴇss:** `{success_count:,}`\n"
                            f"❌ **ғᴀɪʟᴇᴅ:** `{failed_count:,}`\n"
                            f"🚫 **ʙʟᴏᴄᴋᴇᴅ:** `{blocked_count:,}`\n"
                            f"📊 **ᴘʀᴏɢʀᴇss:** `{progress_percent:.1f}%`\n"
                            f"⏱️ **ᴇᴛᴀ:** `~{eta_minutes:.1f}ᴍɪɴ`"
                        )

                        await callback_query.message.edit_text(progress_text)
                    except:
                        pass

                # Small delay to avoid flood limits
                await asyncio.sleep(0.05)

            # Final result
            total_time = time.time() - start_time

            result_text = (
                f"📢 **ʙʀᴏᴀᴅᴄᴀsᴛ ᴄᴏᴍᴘʟᴇᴛᴇᴅ!**\n\n"
                f"👥 **ᴛᴏᴛᴀʟ ᴜsᴇʀs:** `{len(users):,}`\n"
                f"✅ **sᴜᴄᴄᴇssғᴜʟ:** `{success_count:,}`\n"
                f"❌ **ғᴀɪʟᴇᴅ:** `{failed_count:,}`\n"
                f"🚫 **ʙʟᴏᴄᴋᴇᴅ/ᴅᴇʟᴇᴛᴇᴅ:** `{blocked_count:,}`\n"
                f"📊 **sᴜᴄᴄᴇss ʀᴀᴛᴇ:** `{(success_count/len(users)*100):.1f}%`\n"
                f"⏱️ **ᴛᴏᴛᴀʟ ᴛɪᴍᴇ:** `{total_time:.1f}s`\n"
                f"🕒 **ᴄᴏᴍᴘʟᴇᴛᴇᴅ:** `{datetime.now(IST).strftime('%H:%M:%S')}`"
            )

            await callback_query.message.edit_text(result_text)

            # Clean up broadcast data
            if msg_id in broadcast_data:
                del broadcast_data[msg_id]

    except Exception as e:
        logger.error(f"Broadcast callback error: {e}")
        await callback_query.answer(f"❌ ᴇʀʀᴏʀ: {str(e)}", show_alert=True)
