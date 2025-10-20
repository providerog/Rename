import motor.motor_asyncio
from datetime import datetime, timedelta
import logging
from config import DB_URL, DB_NAME

logger = logging.getLogger(__name__)

class Database:
    def __init__(self):
        self.client = motor.motor_asyncio.AsyncIOMotorClient(DB_URL)
        self.db = self.client[DB_NAME]
        self.users = self.db.users
        self.mega_sessions = self.db.mega_sessions
        self.premium_users = self.db.premium_users
        self.settings = self.db.settings
        self.channels = self.db.channels  # For force sub channels
        self.req_channels = self.db.req_channels  # For request channels
        self.invite_links = self.db.invite_links  # For storing invite links
        self.join_requests = self.db.join_requests  # For storing join requests

    # Add these methods to your Database class
    async def store_join_request(self, user_id, channel_id):
        """Store a user's join request in the database"""
        try:
            await self.join_requests.update_one(
                {"user_id": user_id, "channel_id": channel_id},
                {"$set": {"timestamp": datetime.now()}},
                upsert=True
            )
            logger.info(f"✅ Stored join request for user {user_id} in channel {channel_id}")
            return True
        except Exception as e:
            logger.error(f"❌ Error storing join request: {e}")
            return False

    async def has_pending_request(self, user_id, channel_id):
        """Check if a user has a pending join request for a channel"""
        try:
            request = await self.join_requests.find_one({"user_id": user_id, "channel_id": channel_id})
            result = request is not None
            logger.info(f"🔍 Checking pending request for user {user_id} in channel {channel_id}: {result}")
            return result
        except Exception as e:
            logger.error(f"❌ Error checking pending request: {e}")
            return False

    async def remove_join_request(self, user_id, channel_id):
        """Remove join request when user actually joins"""
        try:
            await self.join_requests.delete_one({"user_id": user_id, "channel_id": channel_id})
            logger.info(f"🗑️ Removed join request for user {user_id} in channel {channel_id}")
            return True
        except Exception as e:
            logger.error(f"❌ Error removing join request: {e}")
            return False
        
    async def get_all_pending_requests(self):
        try:
            cursor = self.join_requests.find({})
            return await cursor.to_list(length=None)
        except Exception as e:
            logger.error(f"Error getting pending requests: {e}")
            return []
        
    async def clear_all_requests(self):
        try:
            result = await self.join_requests.delete_many({})
            return result.deleted_count
        except Exception as e:
            logger.error(f"Error clearing requests: {e}")
            return 0


    # ═══════════════════════════════════════════════════════════════════════════════════
    # 👤 ᴜsᴇʀ ᴍᴀɴᴀɢᴇᴍᴇɴᴛ
    # ═══════════════════════════════════════════════════════════════════════════════════

    async def add_user(self, user_id, username=None):
        """Add new user to database"""
        try:
            user_data = {
                "_id": user_id,  # Using _id for compatibility with present_user method
                "user_id": user_id,
                "username": username,
                "joined_date": datetime.now(),
                "files_renamed": 0,
                "last_active": datetime.now()
            }
            await self.users.update_one(
                {"_id": user_id},
                {"$setOnInsert": user_data},
                upsert=True
            )
            return True
        except Exception as e:
            logger.error(f"Error adding user: {e}")
            return False

    # Add these methods to your existing Database class

    async def get_all_users(self):
        """Get all user IDs"""
        try:
            cursor = self.users.find({}, {"_id": 1})
            users = await cursor.to_list(length=None)
            return [user["_id"] for user in users]
        except Exception as e:
            logger.error(f"Error getting all users: {e}")
            return []

    async def total_users_count(self):
        """Get total users count (alias for get_total_users)"""
        return await self.get_total_users()

    async def premium_users_count(self):
        """Get premium users count"""
        try:
            return await self.premium_users.count_documents({
                "is_active": True,
                "end_date": {"$gt": datetime.now()}
            })
        except Exception as e:
            logger.error(f"Error getting premium users count: {e}")
            return 0

    async def get_users_joined_today(self, today_date):
        """Get users joined today"""
        try:
            start_of_day = datetime.combine(today_date, datetime.min.time())
            end_of_day = datetime.combine(today_date, datetime.max.time())
            
            return await self.users.count_documents({
                "joined_date": {
                    "$gte": start_of_day,
                    "$lte": end_of_day
                }
            })
        except Exception as e:
            logger.error(f"Error getting users joined today: {e}")
            return 0

    async def get_total_files_renamed(self):
        """Get total files renamed by all users"""
        try:
            pipeline = [
                {"$group": {"_id": None, "total": {"$sum": "$files_renamed"}}}
            ]
            result = await self.users.aggregate(pipeline).to_list(length=1)
            return result[0]["total"] if result else 0
        except Exception as e:
            logger.error(f"Error getting total files renamed: {e}")
            return 0

    async def get_active_mega_sessions_count(self):
        """Get active mega sessions count"""
        try:
            cutoff_date = datetime.now() - timedelta(days=7)  # Active in last 7 days
            return await self.mega_sessions.count_documents({
                "last_used": {"$gte": cutoff_date}
            })
        except Exception as e:
            logger.error(f"Error getting active mega sessions count: {e}")
            return 0

    async def delete_user(self, user_id):
        """Delete user from database"""
        try:
            await self.users.delete_one({"_id": user_id})
            return True
        except Exception as e:
            logger.error(f"Error deleting user: {e}")
            return False


    async def get_user(self, user_id):
        """Get user data"""
        try:
            return await self.users.find_one({"_id": user_id})
        except Exception as e:
            logger.error(f"Error getting user: {e}")
            return None

    async def present_user(self, user_id: int):
        """Check if user exists in database"""
        try:
            found = await self.users.find_one({'_id': user_id})
            return bool(found)
        except Exception as e:
            logger.error(f"Error checking user presence: {e}")
            return False

    async def update_user_activity(self, user_id):
        """Update user last activity"""
        try:
            await self.users.update_one(
                {"_id": user_id},
                {"$set": {"last_active": datetime.now()}}
            )
            return True
        except Exception as e:
            logger.error(f"Error updating user activity: {e}")
            return False

    async def increment_files_renamed(self, user_id, count=1):
        """Increment user's renamed files count"""
        try:
            await self.users.update_one(
                {"_id": user_id},
                {"$inc": {"files_renamed": count}}
            )
            return True
        except Exception as e:
            logger.error(f"Error incrementing files count: {e}")
            return False

    async def get_total_users(self):
        """Get total users count"""
        try:
            return await self.users.count_documents({})
        except Exception as e:
            logger.error(f"Error getting total users: {e}")
            return 0

    # ═══════════════════════════════════════════════════════════════════════════════════
    # 📢 ᴄʜᴀɴɴᴇʟ ᴍᴀɴᴀɢᴇᴍᴇɴᴛ (ғᴏʀᴄᴇ sᴜʙ)
    # ═══════════════════════════════════════════════════════════════════════════════════

    async def get_all_channels(self):
        """Get all force sub channels"""
        try:
            cursor = self.channels.find({})
            channels = await cursor.to_list(length=None)
            return [channel["chat_id"] for channel in channels]
        except Exception as e:
            logger.error(f"Error getting all channels: {e}")
            return []

    async def add_channel(self, chat_id):
        """Add force sub channel"""
        try:
            await self.channels.update_one(
                {"chat_id": chat_id},
                {"$set": {"chat_id": chat_id, "added_date": datetime.now()}},
                upsert=True
            )
            return True
        except Exception as e:
            logger.error(f"Error adding channel: {e}")
            return False

    async def remove_channel(self, chat_id):
        """Remove force sub channel"""
        try:
            await self.channels.delete_one({"chat_id": chat_id})
            return True
        except Exception as e:
            logger.error(f"Error removing channel: {e}")
            return False

    async def get_request_forcesub(self):
        """Get request force sub setting"""
        try:
            settings = await self.get_settings()
            return settings.get("REQUEST_FORCESUB", False)
        except Exception as e:
            logger.error(f"Error getting request forcesub setting: {e}")
            return False

    async def set_request_forcesub(self, value: bool):
        """Set request force sub setting"""
        try:
            return await self.update_settings("REQUEST_FORCESUB", value)
        except Exception as e:
            logger.error(f"Error setting request forcesub: {e}")
            return False

    # ═══════════════════════════════════════════════════════════════════════════════════
    # 🔗 ɪɴᴠɪᴛᴇ ʟɪɴᴋ ᴍᴀɴᴀɢᴇᴍᴇɴᴛ
    # ═══════════════════════════════════════════════════════════════════════════════════

    async def store_reqLink(self, chat_id, invite_link):
        """Store request invite link for a channel"""
        try:
            await self.invite_links.update_one(
                {"chat_id": chat_id},
                {"$set": {
                    "chat_id": chat_id,
                    "invite_link": invite_link,
                    "created_date": datetime.now(),
                    "updated_date": datetime.now()
                }},
                upsert=True
            )
            return True
        except Exception as e:
            logger.error(f"Error storing invite link: {e}")
            return False

    async def get_stored_reqLink(self, chat_id):
        """Get stored request invite link for a channel"""
        try:
            link_data = await self.invite_links.find_one({"chat_id": chat_id})
            return link_data["invite_link"] if link_data else None
        except Exception as e:
            logger.error(f"Error getting stored invite link: {e}")
            return None

    async def add_reqChannel(self, chat_id):
        """Add channel to request channels list"""
        try:
            await self.req_channels.update_one(
                {"chat_id": chat_id},
                {"$set": {
                    "chat_id": chat_id,
                    "added_date": datetime.now(),
                    "is_request_channel": True
                }},
                upsert=True
            )
            return True
        except Exception as e:
            logger.error(f"Error adding request channel: {e}")
            return False

    async def get_req_channels(self):
        """Get all request channels"""
        try:
            cursor = self.req_channels.find({"is_request_channel": True})
            channels = await cursor.to_list(length=None)
            return [channel["chat_id"] for channel in channels]
        except Exception as e:
            logger.error(f"Error getting request channels: {e}")
            return []

    # ═══════════════════════════════════════════════════════════════════════════════════
    # 🔧 ᴍᴇɢᴀ sᴇssɪᴏɴ ᴍᴀɴᴀɢᴇᴍᴇɴᴛ
    # ═══════════════════════════════════════════════════════════════════════════════════

    async def save_mega_session(self, user_id, email, password):
        """Save mega login credentials"""
        try:
            session_data = {
                "user_id": user_id,
                "email": email,
                "password": password,
                "created_date": datetime.now(),
                "last_used": datetime.now()
            }
            await self.mega_sessions.update_one(
                {"user_id": user_id},
                {"$set": session_data},
                upsert=True
            )
            return True
        except Exception as e:
            logger.error(f"Error saving mega session: {e}")
            return False

    async def get_mega_session(self, user_id):
        """Get mega session credentials"""
        try:
            return await self.mega_sessions.find_one({"user_id": user_id})
        except Exception as e:
            logger.error(f"Error getting mega session: {e}")
            return None

    async def delete_mega_session(self, user_id):
        """Delete mega session"""
        try:
            await self.mega_sessions.delete_one({"user_id": user_id})
            return True
        except Exception as e:
            logger.error(f"Error deleting mega session: {e}")
            return False

    async def update_mega_session_usage(self, user_id):
        """Update mega session last used time"""
        try:
            await self.mega_sessions.update_one(
                {"user_id": user_id},
                {"$set": {"last_used": datetime.now()}}
            )
            return True
        except Exception as e:
            logger.error(f"Error updating mega session usage: {e}")
            return False

    # ═══════════════════════════════════════════════════════════════════════════════════
    # 💎 ᴘʀᴇᴍɪᴜᴍ ᴍᴀɴᴀɢᴇᴍᴇɴᴛ
    # ═══════════════════════════════════════════════════════════════════════════════════

    async def add_premium_user(self, user_id, plan_type, duration_days):
        """Add premium user"""
        try:
            premium_data = {
                "user_id": user_id,
                "plan_type": plan_type,
                "start_date": datetime.now(),
                "end_date": datetime.now() + timedelta(days=duration_days),
                "is_active": True,
                "added_by": "admin",
                "created_at": datetime.now()
            }
            await self.premium_users.update_one(
                {"user_id": user_id},
                {"$set": premium_data},
                upsert=True
            )
            return True
        except Exception as e:
            logger.error(f"Error adding premium user: {e}")
            return False

    async def remove_premium_user(self, user_id):
        """Remove premium user"""
        try:
            await self.premium_users.update_one(
                {"user_id": user_id},
                {"$set": {"is_active": False, "end_date": datetime.now()}}
            )
            return True
        except Exception as e:
            logger.error(f"Error removing premium user: {e}")
            return False

    async def is_premium_user(self, user_id):
        """Check if user is premium"""
        try:
            premium_data = await self.premium_users.find_one({
                "user_id": user_id,
                "is_active": True,
                "end_date": {"$gt": datetime.now()}
            })
            return premium_data is not None
        except Exception as e:
            logger.error(f"Error checking premium status: {e}")
            return False

    async def get_premium_users(self):
        """Get all active premium users"""
        try:
            cursor = self.premium_users.find({
                "is_active": True,
                "end_date": {"$gt": datetime.now()}
            })
            return await cursor.to_list(length=None)
        except Exception as e:
            logger.error(f"Error getting premium users: {e}")
            return []

    async def get_user_premium_info(self, user_id):
        """Get user premium information"""
        try:
            return await self.premium_users.find_one({
                "user_id": user_id,
                "is_active": True,
                "end_date": {"$gt": datetime.now()}
            })
        except Exception as e:
            logger.error(f"Error getting premium info: {e}")
            return None

    async def get_expired_premium_users(self):
        """Get expired premium users"""
        try:
            cursor = self.premium_users.find({
                "is_active": True,
                "end_date": {"$lt": datetime.now()}
            })
            expired_users = await cursor.to_list(length=None)
            return [user["user_id"] for user in expired_users]
        except Exception as e:
            logger.error(f"Error getting expired premium users: {e}")
            return []

    async def cleanup_expired_premium(self):
        """Cleanup expired premium users"""
        try:
            result = await self.premium_users.update_many(
                {"end_date": {"$lt": datetime.now()}},
                {"$set": {"is_active": False}}
            )
            return result.modified_count
        except Exception as e:
            logger.error(f"Error cleaning up expired premium: {e}")
            return 0

    # ═══════════════════════════════════════════════════════════════════════════════════
    # ⚙️ sᴇᴛᴛɪɴɢs ᴍᴀɴᴀɢᴇᴍᴇɴᴛ
    # ═══════════════════════════════════════════════════════════════════════════════════

    async def get_settings(self):
        """Get bot settings"""
        try:
            settings = await self.settings.find_one({"_id": "bot_settings"})
            if not settings:
                # Create default settings
                default_settings = {
                    "_id": "bot_settings",
                    "FORCE_SUB_CHANNELS": [],
                    "REQUEST_SUB_CHANNELS": [],
                    "REQUEST_FORCESUB": False,
                    "created_at": datetime.now(),
                    "updated_at": datetime.now()
                }
                await self.settings.insert_one(default_settings)
                return default_settings
            return settings
        except Exception as e:
            logger.error(f"Error getting settings: {e}")
            return {}

    async def update_settings(self, key, value):
        """Update specific setting"""
        try:
            await self.settings.update_one(
                {"_id": "bot_settings"},
                {
                    "$set": {
                        key: value,
                        "updated_at": datetime.now()
                    }
                },
                upsert=True
            )
            return True
        except Exception as e:
            logger.error(f"Error updating settings: {e}")
            return False

    async def get_setting(self, key, default=None):
        """Get specific setting value"""
        try:
            settings = await self.get_settings()
            return settings.get(key, default)
        except Exception as e:
            logger.error(f"Error getting setting {key}: {e}")
            return default

    # ═══════════════════════════════════════════════════════════════════════════════════
    # 📊 sᴛᴀᴛɪsᴛɪᴄs
    # ═══════════════════════════════════════════════════════════════════════════════════

    async def get_user_stats(self):
        """Get user statistics"""
        try:
            total_users = await self.users.count_documents({})
            active_users = await self.users.count_documents({
                "last_active": {"$gte": datetime.now() - timedelta(days=7)}
            })
            premium_users = len(await self.get_premium_users())
            
            return {
                "total_users": total_users,
                "active_users": active_users,
                "premium_users": premium_users,
                "free_users": total_users - premium_users
            }
        except Exception as e:
            logger.error(f"Error getting user stats: {e}")
            return {
                "total_users": 0,
                "active_users": 0,
                "premium_users": 0,
                "free_users": 0
            }

    async def get_mega_session_stats(self):
        """Get mega session statistics"""
        try:
            total_sessions = await self.mega_sessions.count_documents({})
            active_sessions = await self.mega_sessions.count_documents({
                "last_used": {"$gte": datetime.now() - timedelta(days=1)}
            })
            
            return {
                "total_sessions": total_sessions,
                "active_sessions": active_sessions
            }
        except Exception as e:
            logger.error(f"Error getting mega session stats: {e}")
            return {
                "total_sessions": 0,
                "active_sessions": 0
            }

    # ═══════════════════════════════════════════════════════════════════════════════════
    # 🧹 ᴄʟᴇᴀɴᴜᴘ ᴜᴛɪʟɪᴛɪᴇs
    # ═══════════════════════════════════════════════════════════════════════════════════

    async def cleanup_old_sessions(self, days=30):
        """Cleanup old mega sessions"""
        try:
            cutoff_date = datetime.now() - timedelta(days=days)
            result = await self.mega_sessions.delete_many({
                "last_used": {"$lt": cutoff_date}
            })
            return result.deleted_count
        except Exception as e:
            logger.error(f"Error cleaning up old sessions: {e}")
            return 0

    async def cleanup_inactive_users(self, days=90):
        """Cleanup inactive users (optional)"""
        try:
            cutoff_date = datetime.now() - timedelta(days=days)
            result = await self.users.delete_many({
                "last_active": {"$lt": cutoff_date},
                "files_renamed": 0  # Only delete users who never used the bot
            })
            return result.deleted_count
        except Exception as e:
            logger.error(f"Error cleaning up inactive users: {e}")
            return 0


# Initialize database
db = Database()
