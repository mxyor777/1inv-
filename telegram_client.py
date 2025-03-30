import os
import asyncio
import logging
import time
import json
import re
from datetime import datetime, timedelta
from telethon import TelegramClient, errors
from telethon.tl.functions.account import UpdateProfileRequest, UpdateUsernameRequest
from telethon.tl.functions.users import GetFullUserRequest
from telethon.tl.functions.channels import GetParticipantsRequest, JoinChannelRequest, GetFullChannelRequest, CreateChannelRequest
from telethon.tl.functions.messages import GetHistoryRequest, AddChatUserRequest, ImportChatInviteRequest, CreateChatRequest
from telethon.tl.types import ChannelParticipantsSearch, PeerChannel, PeerUser, PeerChat, InputPeerUser
from telethon.errors import (
    FloodWaitError, 
    UserChannelsTooMuchError, 
    UserNotMutualContactError,
    UserPrivacyRestrictedError,
    UserAlreadyParticipantError,
    ChatAdminRequiredError
)
from telethon.tl import functions
from telethon import connection

from config import API_ID, API_HASH, SESSIONS_DIR
from database import db

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class TelegramClientManager:
    def __init__(self):
        self.clients = {}
        self.active_sessions = set()
    
    def _parse_proxy_string(self, proxy_str):
        """Parse proxy string in format login:pass:ip:port or login:pass@ip:port"""
        if not proxy_str:
            return None
        
        try:
            if '@' in proxy_str:
                auth, server = proxy_str.split('@')
                login, password = auth.split(':')
                ip, port = server.split(':')
            else:
                parts = proxy_str.split(':')
                if len(parts) != 4:
                    raise ValueError("Invalid proxy format. Expected login:pass:ip:port or login:pass@ip:port")
                login, password, ip, port = parts
            
            port = int(port)
            
            return {
                'proxy_type': 'socks5',
                'addr': ip,
                'port': port,
                'username': login,
                'password': password,
                'rdns': True
            }
        except Exception as e:
            logger.error(f"Error parsing proxy string: {e}")
            return None
    
    async def validate_all_accounts(self):
        """Check validity of all accounts at startup"""
        logger.info("Starting validation of all accounts...")
        db._check_and_update_schema()
        
        accounts = db.validate_accounts()
        valid_count = 0
        invalid_count = 0
        
        for account in accounts:
            phone = account['phone']
            session_file = account['session_file']
            
            logger.info(f"Validating account {phone}...")
            
            if phone not in self.clients:
                success = await self.add_client(session_file, proxy_str=account.get('proxy'))
                if not success:
                    logger.warning(f"Failed to load account {phone}, marking as invalid")
                    db.update_account_status(account['id'], 'invalid', {'reason': 'Failed to load session'})
                    invalid_count += 1
                    continue
            
            status_info = await self.check_client_status(phone)
            if status_info['status'] != 'active':
                logger.warning(f"Account {phone} is not valid: {status_info['details']}")
                db.update_account_status(account['id'], status_info['status'], status_info['details'])
                invalid_count += 1
            else:
                logger.info(f"Account {phone} is valid")
                valid_count += 1
        
        logger.info(f"Account validation complete. Valid: {valid_count}, Invalid: {invalid_count}")
        return valid_count, invalid_count
    
    async def add_client(self, session_file, proxy_str=None):
        """Add a client to the manager using session file"""
        if session_file in self.active_sessions:
            return True
        
        session_filename = os.path.basename(session_file)
        
        full_path = os.path.join(SESSIONS_DIR, session_filename)
        
        if not os.path.exists(full_path) and not os.path.exists(full_path + '.session'):
            logger.error(f"Session file {full_path} not found")
            return False
        
        try:
            session_name = os.path.splitext(session_filename)[0]
            
            proxy_config = None
            if proxy_str:
                proxy_config = self._parse_proxy_string(proxy_str)
                if proxy_config:
                    logger.info(f"Using proxy for session {session_name}: {proxy_str}")
                else:
                    logger.warning(f"Invalid proxy format for session {session_name}: {proxy_str}")
            
            if proxy_config:
                client = TelegramClient(
                    os.path.join(SESSIONS_DIR, session_name), 
                    API_ID, 
                    API_HASH,
                    device_model="B550 Windows", 
                    system_version="14.8.1",
                    app_version="8.4", 
                    lang_code="en",
                    system_lang_code="en-US",
                    proxy=proxy_config
                )
            else:
                client = TelegramClient(
                    os.path.join(SESSIONS_DIR, session_name), 
                    API_ID, 
                    API_HASH,
                    device_model="B550 Windows", 
                    system_version="14.8.1",
                    app_version="8.4", 
                    lang_code="en",
                    system_lang_code="en-US"
                )
            
            await client.connect()
            
            if not await client.is_user_authorized():
                logger.error(f"Session {session_name} is not authorized")
                await client.disconnect()
                return False
            
            me = await client.get_me()
            full_user = await client(GetFullUserRequest(me.id))
            
            phone = me.phone
            about = full_user.full_user.about or ""
            
            try:
                db._check_and_update_schema()
                
                db.add_account(
                    phone=phone,
                    session_file=session_name,
                    first_name=me.first_name or "",
                    last_name=me.last_name or "",
                    username=me.username or "",
                    about=about,
                    proxy=proxy_str
                )
                
                self.clients[phone] = {
                    'client': client,
                    'user_info': me,
                    'full_user': full_user,
                    'proxy': proxy_str
                }
                
                self.active_sessions.add(session_name)
                logger.info(f"Successfully added client {me.first_name} {me.last_name} ({phone})")
                return True
            except Exception as db_error:
                logger.error(f"Database error adding client {session_name}: {db_error}")
                try:
                    await client.disconnect()
                except:
                    pass
                return False
            
        except Exception as e:
            logger.error(f"Error adding client {session_name}: {e}")
            return False
    
    async def update_client_proxy(self, phone, proxy_str):
        """Update proxy settings for an existing client"""
        if phone not in self.clients:
            logger.error(f"Client with phone {phone} not found")
            return False, "Аккаунт не найден"
        
        try:
            current_client = self.clients[phone]['client']
            session_file = None
            
            for acc in db.get_accounts():
                if acc['phone'] == phone:
                    session_file = acc['session_file']
                    account_id = acc['id']
                    break
            
            if not session_file:
                logger.error(f"Session file for phone {phone} not found")
                return False, "Сессия для аккаунта не найдена"
            
            try:
                await current_client.disconnect()
            except Exception as e:
                logger.warning(f"Error disconnecting client {phone}: {e}")
            
            self.clients.pop(phone, None)
            self.active_sessions.discard(session_file)
            
            db.update_account_proxy(account_id, proxy_str)
            
            success = await self.add_client(session_file, proxy_str)
            
            if success:
                logger.info(f"Successfully updated proxy for account {phone}")
                return True, "Прокси успешно обновлен"
            else:
                logger.error(f"Failed to reconnect client {phone} with new proxy")
                return False, "Не удалось подключиться с новыми настройками прокси"
        
        except Exception as e:
            logger.error(f"Error updating proxy for {phone}: {e}")
            return False, str(e)
    
    async def remove_client_proxy(self, phone):
        """Remove proxy settings from an existing client"""
        return await self.update_client_proxy(phone, None)
    
    async def check_client_status(self, phone):
        """Check if client is banned or restricted"""
        if phone not in self.clients:
            return {'status': 'unknown', 'details': 'Client not loaded'}
        
        client = self.clients[phone]['client']
        
        try:
            dialogs = await client.get_dialogs(limit=1)
            
            me = await client.get_me()
            full_user = await client(GetFullUserRequest(me.id))
            
            if hasattr(full_user.full_user, 'restricted') and full_user.full_user.restricted:
                return {
                    'status': 'restricted',
                    'details': 'Account has restrictions',
                    'restriction_reason': getattr(full_user.full_user, 'restriction_reason', 'Unknown')
                }
            
            self.clients[phone]['user_info'] = me
            self.clients[phone]['full_user'] = full_user
            
            return {'status': 'active', 'details': 'Account is active'}
            
        except errors.UserDeactivatedBanError:
            return {'status': 'banned', 'details': 'Account has been banned'}
        except errors.AuthKeyUnregisteredError:
            return {'status': 'deactivated', 'details': 'Session has been revoked'}
        except errors.FloodWaitError as e:
            return {'status': 'flood', 'details': f'Account is restricted for {e.seconds} seconds'}
        except Exception as e:
            return {'status': 'error', 'details': str(e)}
    
    async def update_profile(self, phone, first_name=None, last_name=None, about=None, username=None):
        """Update account profile info"""
        if phone not in self.clients:
            logger.error(f"Client with phone {phone} not found")
            return False
        
        client = self.clients[phone]['client']
        success = True
        
        try:
            params = {}
            if first_name is not None:
                params['first_name'] = first_name
            if last_name is not None:
                params['last_name'] = last_name
            if about is not None:
                params['about'] = about
            
            if params:
                logger.info(f"Updating profile for {phone}: {params}")
                try:
                    await client(UpdateProfileRequest(**params))
                    logger.info(f"Profile update successful")
                except Exception as e:
                    logger.error(f"Error updating profile info: {str(e)}")
                    success = False
            
            if username is not None:
                try:
                    logger.info(f"Attempting to update username to: {username}")
                    result = await client(UpdateUsernameRequest(username))
                    logger.info(f"Username update response: {result}")
                    
                    me = await client.get_me()
                    current_username = me.username
                    
                    if username == current_username or (username == "" and current_username is None):
                        logger.info(f"Username successfully updated to: {current_username}")
                    else:
                        logger.warning(f"Username update may have failed. Expected: {username}, Got: {current_username}")
                        if not username:  
                            success = success and (current_username is None)
                        else:
                            success = success and (username == current_username)
                except Exception as e:
                    logger.error(f"Error updating username for {phone}: {str(e)}")
                    success = False
            
            if success:
                account = None
                for acc in db.get_accounts():
                    if acc['phone'] == phone:
                        account = acc
                        break
                
                if account:
                    db.update_account_info(
                        account_id=account['id'], 
                        first_name=first_name, 
                        last_name=last_name,
                        username=username
                    )
                    logger.info(f"Database updated for account {account['id']}")
                else:
                    logger.warning(f"Account with phone {phone} not found in database")
                
                me = await client.get_me()
                self.clients[phone]['user_info'] = me
                logger.info(f"Client cache updated with new user info")
            
            return success
        except Exception as e:
            logger.error(f"Error updating profile for {phone}: {str(e)}")
            return False
    
    async def update_profile_birthday(self, phone, birthday):
        """Update account birthday
        
        Args:
            phone (str): Account phone number
            birthday (str): Birthday in DD.MM.YYYY format
        
        Returns:
            bool: Success
        """
        if phone not in self.clients:
            logger.error(f"Client {phone} not found")
            return False
        
        client = self.clients[phone]['client']
        
        try:
            day, month, year = map(int, birthday.split('.'))
            birthday_date = datetime(year, month, day)
            
            from telethon.tl.functions.account import UpdateProfileRequest
            
            account = None
            for acc in db.get_accounts():
                if acc['phone'] == phone:
                    account = acc
                    break
            
            if account:
                db.update_account_birthday(account['id'], birthday)
            
            return True
        except Exception as e:
            logger.error(f"Error updating birthday for {phone}: {e}")
            return False
    
    async def join_chat(self, phone, chat_link):
        """Join a chat using invite link or username"""
        if phone not in self.clients:
            return False, "Client not loaded"
        
        client = self.clients[phone]['client']
        
        try:
            if 'joinchat' in chat_link:
                invite_hash = chat_link.split('/')[-1]
                await client(ImportChatInviteRequest(invite_hash))
            else:
                if chat_link.isdigit():
                    chat_entity = await client.get_entity(int(chat_link))
                else:
                    username = chat_link.replace('@', '')
                    chat_entity = await client.get_entity(username)
                
                await client(JoinChannelRequest(chat_entity))
            
            return True, None
        except FloodWaitError as e:
            return False, f"FloodWaitError: need to wait {e.seconds} seconds"
        except Exception as e:
            return False, str(e)
    
    async def get_chat_info(self, phone, chat_link):
        """Get information about a chat"""
        if phone not in self.clients:
            return None, "Client not loaded"
        
        client = self.clients[phone]['client']
        
        try:
            if chat_link.isdigit():
                chat_entity = await client.get_entity(int(chat_link))
            else:
                username = chat_link.replace('@', '')
                chat_entity = await client.get_entity(username)
            
            participants_count = 0
            try:
                if hasattr(chat_entity, 'participants_count'):
                    participants_count = chat_entity.participants_count
                elif hasattr(chat_entity, 'id'):
                    full_chat = await client(GetFullChannelRequest(chat_entity))
                    if hasattr(full_chat, 'full_chat') and hasattr(full_chat.full_chat, 'participants_count'):
                        participants_count = full_chat.full_chat.participants_count
            except Exception as e:
                logger.warning(f"Failed to get participants count: {e}")
            
            chat_info = {
                'id': chat_entity.id,
                'title': getattr(chat_entity, 'title', None),
                'username': getattr(chat_entity, 'username', None),
                'participants_count': participants_count,
                'link': f"https://t.me/{chat_entity.username}" if getattr(chat_entity, 'username', None) else None
            }
            
            return chat_info, None
        except Exception as e:
            return None, str(e)
    
    async def parse_chat_members(self, phone, chat_id, limit=None):
        """Parse members from a chat"""
        if phone not in self.clients:
            return [], "Client not loaded"
        
        client = self.clients[phone]['client']
        
        try:
            if isinstance(chat_id, str) and chat_id.isdigit():
                chat_id = int(chat_id)
            
            logger.info(f"Attempting to get entity for chat ID: {chat_id}")
            
            try:
                if isinstance(chat_id, int):
                    from telethon.tl.types import PeerChannel
                    peer_channel = PeerChannel(chat_id)
                    chat_entity = await client.get_entity(peer_channel)
                    logger.info(f"Successfully fetched entity using PeerChannel")
                else:
                    chat_entity = await client.get_entity(chat_id)
                    logger.info(f"Successfully fetched entity using direct entity look-up")
            except Exception as e:
                logger.warning(f"First attempt to get entity failed: {str(e)}")
                
                if isinstance(chat_id, str):
                    username = chat_id.replace('@', '')
                    logger.info(f"Trying to get entity by username: {username}")
                    chat_entity = await client.get_entity(username)
                else:
                    logger.info("Attempting to find chat in user's dialogs")
                    dialogs = await client.get_dialogs()
                    found = False
                    
                    for dialog in dialogs:
                        if dialog.id == chat_id or (hasattr(dialog, 'entity') and dialog.entity.id == chat_id):
                            chat_entity = dialog.entity
                            found = True
                            logger.info(f"Found entity in dialogs: {dialog.name}")
                            break
                    
                    if not found:
                        raise ValueError(f"Could not find chat with ID {chat_id} in user's dialogs")
            
            logger.info(f"Successfully got chat entity: {getattr(chat_entity, 'title', chat_id)}")
            
            from telethon.tl.types import Channel, Chat, User
            if isinstance(chat_entity, User):
                logger.error(f"Entity with ID {chat_id} is a user, not a channel or chat")
                return [], f"Cannot parse members from a user entity. ID {chat_id} belongs to a user."
            
            all_participants = []
            offset = 0
            search = ''
            limit = limit or 10000
            
            logger.info(f"Starting to fetch participants from chat: {getattr(chat_entity, 'title', chat_id)}")
            
            while True:
                try:
                    participants = await client(GetParticipantsRequest(
                        channel=chat_entity,
                        filter=ChannelParticipantsSearch(search),
                        offset=offset,
                        limit=500,
                        hash=0
                    ))
                    
                    if not participants.users:
                        logger.info(f"No more participants found at offset {offset}")
                        break
                    
                    logger.info(f"Fetched {len(participants.users)} participants at offset {offset}")
                    all_participants.extend(participants.users)
                    offset += len(participants.users)
                    
                    if len(all_participants) >= limit:
                        all_participants = all_participants[:limit]
                        logger.info(f"Reached participant limit: {limit}")
                        break
                    
                except Exception as fetch_error:
                    logger.error(f"Error fetching participants at offset {offset}: {str(fetch_error)}")
                    break
                
                await asyncio.sleep(1)
            
            logger.info(f"Total participants fetched: {len(all_participants)}")
            
            members = []
            skipped_count = 0
            
            batch_size = 100
            for i in range(0, len(all_participants), batch_size):
                user_batch = all_participants[i:i+batch_size]
                
                for user in user_batch:
                    if user.bot:
                        skipped_count += 1
                        continue
                    
                    try:
                        members.append({
                            'id': user.id,
                            'username': user.username,
                            'first_name': user.first_name,
                            'last_name': user.last_name,
                            'phone': user.phone
                        })
                    except Exception as e:
                        logger.warning(f"Error processing user {getattr(user, 'id', 'unknown')}: {str(e)}")
                        skipped_count += 1
                        continue
                
                if i + batch_size < len(all_participants):
                    logger.info(f"Processed {len(members)} members so far, skipped {skipped_count}, continuing...")
                    await asyncio.sleep(0.2)
            
            logger.info(f"Successfully processed {len(members)} members, skipped {skipped_count}")
            return members, None
        except Exception as e:
            logger.error(f"Error parsing chat members from {chat_id}: {str(e)}")
            return [], str(e)
    
    async def parse_active_users(self, phone, chat_id, days=60, limit=None):
        """Parse users who have been active in the chat within the specified number of days"""
        if phone not in self.clients:
            return [], "Client not loaded"
        
        client = self.clients[phone]['client']
        
        try:
            if isinstance(chat_id, str) and chat_id.isdigit():
                chat_id = int(chat_id)
            
            logger.info(f"Attempting to get entity for chat ID: {chat_id}")
            
            try:
                if isinstance(chat_id, int):
                    from telethon.tl.types import PeerChannel
                    peer_channel = PeerChannel(chat_id)
                    chat_entity = await client.get_entity(peer_channel)
                    logger.info(f"Successfully fetched entity using PeerChannel")
                else:
                    chat_entity = await client.get_entity(chat_id)
                    logger.info(f"Successfully fetched entity using direct entity look-up")
            except Exception as e:
                logger.warning(f"First attempt to get entity failed: {str(e)}")
                
                if isinstance(chat_id, str):
                    username = chat_id.replace('@', '')
                    logger.info(f"Trying to get entity by username: {username}")
                    chat_entity = await client.get_entity(username)
                else:
                    logger.info("Attempting to find chat in user's dialogs")
                    dialogs = await client.get_dialogs()
                    found = False
                    
                    for dialog in dialogs:
                        if dialog.id == chat_id or (hasattr(dialog, 'entity') and dialog.entity.id == chat_id):
                            chat_entity = dialog.entity
                            found = True
                            logger.info(f"Found entity in dialogs: {dialog.name}")
                            break
                    
                    if not found:
                        raise ValueError(f"Could not find chat with ID {chat_id} in user's dialogs")
            
            logger.info(f"Successfully got chat entity: {getattr(chat_entity, 'title', chat_id)}")
            
            from telethon.tl.types import Channel, Chat, User
            if isinstance(chat_entity, User):
                logger.error(f"Entity with ID {chat_id} is a user, not a channel or chat")
                return [], f"Cannot parse active users from a user entity. ID {chat_id} belongs to a user."
            
            active_users = set()
            has_more_messages = True
            stop_fetching = False
            
            user_limit = limit or 100000
            
            date_limit = datetime.now() - timedelta(days=days)
            
            date_limit_unix = int(time.mktime(date_limit.timetuple()))
            
            logger.info(f"Fetching messages from the last {days} days (since {date_limit.strftime('%Y-%m-%d')})")
            
            max_batch_size = 100
            messages_processed = 0
            
            initial_offsets = [0]
            
            initial_messages = await client(GetHistoryRequest(
                peer=chat_entity,
                offset_id=0,
                offset_date=None,
                add_offset=0,
                limit=max_batch_size,
                max_id=0,
                min_id=0,
                hash=0
            ))
            
            if not initial_messages.messages:
                logger.info("No messages found in the chat")
                return [], None
            
            for message in initial_messages.messages:
                if message.from_id and isinstance(message.from_id, PeerUser):
                    active_users.add(message.from_id.user_id)
            
            messages_processed += len(initial_messages.messages)
            logger.info(f"Fetched {len(initial_messages.messages)} messages, found {len(active_users)} unique users")
            
            if len(initial_messages.messages) == max_batch_size:
                last_msg_id = initial_messages.messages[-1].id
                
                if len(initial_messages.messages) > 8:
                    step = last_msg_id // 8
                    for i in range(1, 8):
                        initial_offsets.append(step * i)
            
            logger.info(f"Using {len(initial_offsets)} parallel fetching positions: {initial_offsets}")
            
            async def fetch_messages_with_offset(offset_id):
                local_stop = False
                local_messages_processed = 0
                local_active_users = set()
                
                while not local_stop:
                    try:
                        messages = await client(GetHistoryRequest(
                            peer=chat_entity,
                            offset_id=offset_id,
                            offset_date=None,
                            add_offset=0,
                            limit=max_batch_size,
                            max_id=0,
                            min_id=0,
                            hash=0
                        ))
                        
                        if not messages.messages:
                            logger.info(f"No more messages found at offset {offset_id}")
                            break
                        
                        local_messages_processed += len(messages.messages)
                        
                        for message in messages.messages:
                            if message.date.timestamp() < date_limit_unix:
                                local_stop = True
                                break
                            
                            if message.from_id and isinstance(message.from_id, PeerUser):
                                local_active_users.add(message.from_id.user_id)
                        
                        if messages.messages and not local_stop:
                            offset_id = messages.messages[-1].id
                        else:
                            break
                            
                    except Exception as fetch_error:
                        logger.error(f"Error fetching messages at offset {offset_id}: {str(fetch_error)}")
                        break
                    
                    await asyncio.sleep(0.1)
                
                return list(local_active_users), local_messages_processed
            
            fetch_tasks = []
            for offset in initial_offsets:
                fetch_tasks.append(fetch_messages_with_offset(offset))
            
            results = await asyncio.gather(*fetch_tasks)
            
            for user_ids, msg_count in results:
                active_users.update(user_ids)
                messages_processed += msg_count
            
            logger.info(f"Total messages processed: {messages_processed}")
            logger.info(f"Total unique active users found: {len(active_users)}")
            
            users = []
            error_count = 0
            
            user_batch_size = 100
            
            user_ids_list = list(active_users)
            
            for i in range(0, len(user_ids_list), user_batch_size):
                batch_ids = user_ids_list[i:i+user_batch_size]
                batch_users = []
                
                try:
                    batch_entities = await client.get_entity(batch_ids)
                    if not isinstance(batch_entities, list):
                        batch_entities = [batch_entities]
                        
                    for user in batch_entities:
                        if not getattr(user, 'bot', False):
                            batch_users.append({
                                'id': user.id,
                                'username': user.username,
                                'first_name': user.first_name,
                                'last_name': user.last_name,
                                'phone': user.phone
                            })
                except Exception as e:
                    logger.warning(f"Batch fetching failed: {e}, falling back to individual fetching")
                    for user_id in batch_ids:
                        try:
                            user = await client.get_entity(user_id)
                            if not getattr(user, 'bot', False):
                                batch_users.append({
                                    'id': user.id,
                                    'username': user.username,
                                    'first_name': user.first_name,
                                    'last_name': user.last_name,
                                    'phone': user.phone
                                })
                        except Exception as e:
                            logger.warning(f"Error getting user {user_id}: {e}")
                            error_count += 1
                            continue
                
                users.extend(batch_users)
                
                if i + user_batch_size < len(user_ids_list):
                    logger.info(f"Processed {len(users)} users out of {len(active_users)}, continuing...")
                    await asyncio.sleep(0.1)
                
                if len(users) >= user_limit:
                    logger.info(f"Reached user limit: {user_limit}")
                    break
            
            logger.info(f"Successfully collected data for {len(users)} users, failed for {error_count} users")
            return users, None
        except Exception as e:
            logger.error(f"Error parsing active users from {chat_id}: {str(e)}")
            return [], str(e)
    
    async def invite_user(self, phone, chat_id, user_id):
        """Invite a user to a chat"""
        if phone not in self.clients:
            return False, "Client not loaded"
        
        client = self.clients[phone]['client']
        
        try:
            if isinstance(chat_id, str) and chat_id.isdigit():
                chat_id = int(chat_id)
            chat_entity = await client.get_entity(chat_id)
            
            if isinstance(user_id, str) and user_id.isdigit():
                user_id = int(user_id)
            user_entity = await client.get_entity(user_id)
            
            if isinstance(chat_entity, PeerChannel):
                result = await client(
                    JoinChannelRequest(chat_entity)
                )
            else:
                result = await client(
                    AddChatUserRequest(
                        chat_id=chat_entity.id,
                        user_id=user_entity,
                        fwd_limit=300
                    )
                )
            
            return True, None
        except FloodWaitError as e:
            return False, f"FloodWaitError: need to wait {e.seconds} seconds"
        except UserChannelsTooMuchError:
            return False, "User is in too many channels"
        except UserNotMutualContactError:
            return False, "User does not allow inviting them"
        except UserPrivacyRestrictedError:
            return False, "User has restricted privacy settings"
        except Exception as e:
            return False, str(e)
    
    async def create_group_chat(self, phone, title, description=""):
        """Create a new group chat"""
        if phone not in self.clients:
            logger.error(f"Client {phone} not found")
            return None, "Аккаунт не найден"
        
        client = self.clients[phone]['client']
        
        try:
            result = await client(functions.channels.CreateChannelRequest(
                title=title,
                about=description,
                megagroup=True
            ))
            
            channel = result.chats[0]
            
            chat_info = {
                'id': channel.id,
                'title': channel.title,
                'username': getattr(channel, 'username', ''),
                'link': f"https://t.me/{channel.username}" if hasattr(channel, 'username') and channel.username else ""
            }
            
            logger.info(f"Successfully created chat {title}")
            return chat_info, None
        except Exception as e:
            logger.error(f"Error creating chat: {e}")
            return None, str(e)
    
    async def get_chat_invite_link(self, phone, chat_id):
        """Get or generate an invite link for a chat"""
        if phone not in self.clients:
            logger.error(f"Client {phone} not found")
            return None, "Аккаунт не найден"
        
        client = self.clients[phone]['client']
        
        try:
            if isinstance(chat_id, str) and chat_id.isdigit():
                chat_id = int(chat_id)
            
            chat_entity = await client.get_entity(chat_id)
            
            result = await client(functions.messages.ExportChatInviteRequest(
                peer=chat_entity
            ))
            
            return result.link, None
        except ChatAdminRequiredError:
            return None, "Для создания ссылки требуются права администратора"
        except Exception as e:
            logger.error(f"Error getting invite link: {e}")
            return None, str(e)
    
    def get_client(self, phone):
        """Get client instance by phone number"""
        if phone not in self.clients:
            logger.error(f"Client with phone {phone} not found")
            return None
        
        return self.clients[phone]['client']
    
    async def close_all_clients(self):
        """Close all active clients"""
        for phone, client_data in self.clients.items():
            try:
                await client_data['client'].disconnect()
            except Exception as e:
                logger.error(f"Error disconnecting client {phone}: {e}")
        
        self.clients = {}
        self.active_sessions = set()


client_manager = TelegramClientManager() 