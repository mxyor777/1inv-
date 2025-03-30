import os
import asyncio
import random
import logging
import time
from datetime import datetime, timedelta

from config import PARSED_USERS_DIR
from database import db
from telegram_client import client_manager

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class Inviter:
    def __init__(self):
        self.running_tasks = {}
        self.stop_flags = {}
    
    async def parse_chat(self, account_phone, chat_id, parse_type="members"):
        try:
            chat = db.get_source_chat(chat_id)
            if not chat:
                return False, "Chat not found in database"
            
            timestamp = int(time.time())
            safe_title = ''.join(c if c.isalnum() or c in ['_', '-'] else '_' for c in chat['title'])
            filename = f"{safe_title}_{timestamp}.txt"
            file_path = os.path.join(PARSED_USERS_DIR, filename)
            
            os.makedirs(PARSED_USERS_DIR, exist_ok=True)
            
            if parse_type == "members":
                users, error = await client_manager.parse_chat_members(account_phone, chat['chat_id'])
            elif parse_type == "active":
                users, error = await client_manager.parse_active_users(account_phone, chat['chat_id'], days=90)
            else:
                return False, "Invalid parse type"
            
            if error:
                logger.error(f"Error during parsing: {error}")
                return False, error
            
            if not users or len(users) == 0:
                logger.warning(f"No users were parsed from chat {chat_id}")
                return False, "No users were found in the chat"
            
            valid_users_count = 0
            with open(file_path, 'w', encoding='utf-8') as f:
                for user in users:
                    try:
                        user_id = user['id']
                        if not isinstance(user_id, int) or user_id <= 0:
                            continue
                            
                        f.write(f"{user['id']},{user.get('username', '')},{user.get('first_name', '')},{user.get('last_name', '')}\n")
                        valid_users_count += 1
                    except Exception as e:
                        logger.warning(f"Error processing user data: {e}")
                        continue
            
            if valid_users_count == 0:
                logger.warning(f"No valid users were saved to file")
                if os.path.exists(file_path):
                    os.remove(file_path)
                return False, "No valid users were found to save"
            
            db.add_parsed_file(
                file_name=filename,
                source_chat_id=chat_id,
                total_users=valid_users_count,
                parse_type=parse_type
            )
            
            db.update_source_chat_stats(
                chat_id=chat_id,
                total_members=valid_users_count if parse_type == "members" else None,
                parsed_members=valid_users_count
            )
            
            return True, {
                "filename": filename,
                "total_users": valid_users_count,
                "chat_title": chat['title']
            }
        except Exception as e:
            logger.error(f"Error parsing chat {chat_id}: {e}")
            return False, str(e)
    
    def _load_users_from_file(self, file_path):
        users = []
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    
                    parts = line.split(',', 3)
                    if len(parts) >= 1:
                        user_id = parts[0]
                        username = parts[1] if len(parts) > 1 else ""
                        first_name = parts[2] if len(parts) > 2 else ""
                        last_name = parts[3] if len(parts) > 3 else ""
                        
                        users.append({
                            'id': user_id,
                            'username': username,
                            'first_name': first_name,
                            'last_name': last_name
                        })
            
            return users
        except Exception as e:
            logger.error(f"Error loading users from file {file_path}: {e}")
            return []
    
    async def start_inviting(self, account_id, target_chat_id, source_file_id, task_id=None):
        try:
            if task_id is None:
                task_id = f"invite_{account_id}_{target_chat_id}_{source_file_id}_{int(time.time())}"
            
            self.stop_flags[task_id] = False
            
            account = db.get_account(account_id)
            if not account:
                return False, "Account not found"
            
            target_chat = db.get_target_chat(target_chat_id)
            if not target_chat:
                return False, "Target chat not found"
            
            source_file = db.get_parsed_file(source_file_id)
            if not source_file:
                return False, "Source file not found"
            
            invite_settings = db.get_invite_settings()
            max_invites_per_12h = invite_settings['max_invites_per_12h']
            max_invites_per_24h = invite_settings['max_invites_per_24h']
            invite_interval_min = invite_settings['invite_interval_min']
            invite_interval_max = invite_settings['invite_interval_max']
            
            file_path = os.path.join(PARSED_USERS_DIR, source_file['file_name'])
            users = self._load_users_from_file(file_path)
            if not users:
                return False, "No users found in source file"
            
            progress = db.get_invite_progress(account_id, target_chat_id, source_file_id)
            start_position = progress['last_position'] if progress else 0
            
            current_time = int(time.time())
            time_12h_ago = current_time - (12 * 60 * 60)
            time_24h_ago = current_time - (24 * 60 * 60)
            
            invites_12h = account['invites_sent'] // 2
            invites_24h = account['invites_sent']
            
            remaining_invites_12h = max(0, max_invites_per_12h - invites_12h)
            remaining_invites_24h = max(0, max_invites_per_24h - invites_24h)
            remaining_invites = min(remaining_invites_12h, remaining_invites_24h)
            
            logger.info(f"Starting inviting task {task_id} for account {account['phone']}")
            logger.info(f"Target chat: {target_chat['title']}, Source file: {source_file['file_name']}")
            logger.info(f"Starting from position {start_position}, remaining invites: {remaining_invites}")
            
            inviting_task = asyncio.create_task(
                self._invite_users_task(
                    task_id=task_id,
                    account_phone=account['phone'],
                    target_chat_id=target_chat['chat_id'],
                    users=users,
                    start_position=start_position,
                    max_invites=remaining_invites,
                    invite_interval_min=invite_interval_min,
                    invite_interval_max=invite_interval_max,
                    account_id=account_id,
                    target_chat_db_id=target_chat_id,
                    source_file_id=source_file_id
                )
            )
            
            self.running_tasks[task_id] = {
                'task': inviting_task,
                'account_id': account_id,
                'target_chat_id': target_chat_id,
                'source_file_id': source_file_id,
                'start_time': current_time
            }
            
            return True, {
                'task_id': task_id,
                'account': account['phone'],
                'target_chat': target_chat['title'],
                'source_file': source_file['file_name'],
                'remaining_invites': remaining_invites
            }
        except Exception as e:
            logger.error(f"Error starting inviting task: {e}")
            return False, str(e)
    
    async def _invite_users_task(self, task_id, account_phone, target_chat_id, users, start_position,
                                max_invites, invite_interval_min, invite_interval_max,
                                account_id, target_chat_db_id, source_file_id):
        successful_invites = 0
        failed_invites = 0
        current_position = start_position
        
        try:
            while (current_position < len(users) and 
                  successful_invites < max_invites and
                  not self.stop_flags.get(task_id, False)):
                
                user = users[current_position]
                user_id = user['id']
                
                success, error = await client_manager.invite_user(account_phone, target_chat_id, user_id)
                
                if success:
                    successful_invites += 1
                    logger.info(f"Successfully invited user {user_id} to chat {target_chat_id}")
                else:
                    failed_invites += 1
                    logger.warning(f"Failed to invite user {user_id} to chat {target_chat_id}: {error}")
                    
                if "FloodWaitError" in error:
                    wait_time = int(error.split(" ")[-2])
                    logger.warning(f"Need to wait for {wait_time} seconds due to FloodWaitError")
                    
                    db.update_invite_progress(account_id, target_chat_db_id, source_file_id, current_position)
                    db.update_account_invite_stats(account_id, successful_invites, failed_invites)
                    db.update_target_chat_invites(target_chat_db_id, successful_invites)
                    
                    await asyncio.sleep(min(wait_time, 3600))
                
                current_position += 1
                
                if (successful_invites + failed_invites) % 5 == 0:
                    db.update_invite_progress(account_id, target_chat_db_id, source_file_id, current_position)
                    db.update_account_invite_stats(account_id, successful_invites, failed_invites)
                    db.update_target_chat_invites(target_chat_db_id, successful_invites)
                    
                    successful_invites = 0
                    failed_invites = 0
                
                wait_time = random.randint(invite_interval_min, invite_interval_max)
                await asyncio.sleep(wait_time)
            
            db.update_invite_progress(account_id, target_chat_db_id, source_file_id, current_position)
            db.update_account_invite_stats(account_id, successful_invites, failed_invites)
            db.update_target_chat_invites(target_chat_db_id, successful_invites)
            
            logger.info(f"Inviting task {task_id} completed")
            return True
            
        except Exception as e:
            logger.error(f"Error in inviting task {task_id}: {e}")
            
            db.update_invite_progress(account_id, target_chat_db_id, source_file_id, current_position)
            db.update_account_invite_stats(account_id, successful_invites, failed_invites)
            db.update_target_chat_invites(target_chat_db_id, successful_invites)
            
            return False
        finally:
            if task_id in self.running_tasks:
                del self.running_tasks[task_id]
            if task_id in self.stop_flags:
                del self.stop_flags[task_id]
    
    def stop_inviting(self, task_id):
        if task_id in self.running_tasks:
            self.stop_flags[task_id] = True
            return True, f"Stopping task {task_id}"
        else:
            return False, f"Task {task_id} not found or already stopped"
    
    def get_running_tasks(self):
        tasks = []
        for task_id, task_info in self.running_tasks.items():
            account = db.get_account(task_info['account_id'])
            target_chat = db.get_target_chat(task_info['target_chat_id'])
            source_file = db.get_parsed_file(task_info['source_file_id'])
            
            tasks.append({
                'task_id': task_id,
                'account': account['phone'] if account else "Unknown",
                'target_chat': target_chat['title'] if target_chat else "Unknown",
                'source_file': source_file['file_name'] if source_file else "Unknown",
                'running_for': int(time.time()) - task_info['start_time']
            })
        
        return tasks


inviter = Inviter() 