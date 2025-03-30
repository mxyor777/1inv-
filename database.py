import sqlite3
import json
import os
import time
from datetime import datetime
from config import DB_FILE

class Database:
    def __init__(self):
        self.conn = None
        self.cursor = None
        self.initialize()
        
    def initialize(self):
        os.makedirs(os.path.dirname(DB_FILE), exist_ok=True)
        self.conn = sqlite3.connect(DB_FILE)
        self.conn.row_factory = sqlite3.Row
        self.cursor = self.conn.cursor()
        self._create_tables()
        self._check_and_update_schema()
        
    def _create_tables(self):
        self.cursor.execute('''
        CREATE TABLE IF NOT EXISTS accounts (
            id INTEGER PRIMARY KEY,
            phone TEXT UNIQUE,
            session_file TEXT,
            first_name TEXT,
            last_name TEXT,
            username TEXT,
            added_date INTEGER,
            last_used INTEGER,
            status TEXT DEFAULT 'active',
            ban_info TEXT,
            invites_sent INTEGER DEFAULT 0,
            invites_failed INTEGER DEFAULT 0,
            settings TEXT,
            about TEXT,
            proxy TEXT
        )
        ''')
        
        self.cursor.execute('''
        CREATE TABLE IF NOT EXISTS source_chats (
            id INTEGER PRIMARY KEY,
            chat_id INTEGER,
            username TEXT,
            title TEXT,
            link TEXT,
            added_date INTEGER,
            total_members INTEGER DEFAULT 0,
            parsed_members INTEGER DEFAULT 0,
            account_id INTEGER,
            FOREIGN KEY (account_id) REFERENCES accounts (id)
        )
        ''')
        
        self.cursor.execute('''
        CREATE TABLE IF NOT EXISTS target_chats (
            id INTEGER PRIMARY KEY,
            chat_id INTEGER,
            username TEXT,
            title TEXT,
            link TEXT,
            added_date INTEGER,
            invites_sent INTEGER DEFAULT 0,
            file_name TEXT,
            account_id INTEGER,
            FOREIGN KEY (account_id) REFERENCES accounts (id)
        )
        ''')
        
        self.cursor.execute('''
        CREATE TABLE IF NOT EXISTS parsed_files (
            id INTEGER PRIMARY KEY,
            file_name TEXT UNIQUE,
            source_chat_id INTEGER,
            total_users INTEGER DEFAULT 0,
            parse_type TEXT,
            added_date INTEGER,
            FOREIGN KEY (source_chat_id) REFERENCES source_chats (id)
        )
        ''')
        
        self.cursor.execute('''
        CREATE TABLE IF NOT EXISTS invite_progress (
            id INTEGER PRIMARY KEY,
            account_id INTEGER,
            target_chat_id INTEGER,
            source_file_id INTEGER,
            last_position INTEGER DEFAULT 0,
            last_invite_time INTEGER,
            FOREIGN KEY (account_id) REFERENCES accounts (id),
            FOREIGN KEY (target_chat_id) REFERENCES target_chats (id),
            FOREIGN KEY (source_file_id) REFERENCES parsed_files (id)
        )
        ''')
        
        self.cursor.execute('''
        CREATE TABLE IF NOT EXISTS invite_settings (
            id INTEGER PRIMARY KEY,
            max_invites_per_12h INTEGER DEFAULT 35,
            max_invites_per_24h INTEGER DEFAULT 50,
            invite_interval_min INTEGER DEFAULT 30,
            invite_interval_max INTEGER DEFAULT 120,
            last_updated INTEGER
        )
        ''')
        
        self.cursor.execute('SELECT COUNT(*) FROM invite_settings')
        if self.cursor.fetchone()[0] == 0:
            self.cursor.execute('''
            INSERT INTO invite_settings 
            (max_invites_per_12h, max_invites_per_24h, invite_interval_min, invite_interval_max, last_updated)
            VALUES (?, ?, ?, ?, ?)
            ''', (35, 50, 30, 120, int(time.time())))
        
        self.cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY,
            register_date INTEGER,
            last_active INTEGER,
            settings TEXT
        )
        ''')
        
        self.cursor.execute('''
        CREATE TABLE IF NOT EXISTS invite_logs (
            id INTEGER PRIMARY KEY,
            account_id INTEGER,
            target_chat_id INTEGER,
            user_id INTEGER,
            status TEXT,
            error_message TEXT,
            invite_time INTEGER,
            FOREIGN KEY (account_id) REFERENCES accounts (id),
            FOREIGN KEY (target_chat_id) REFERENCES target_chats (id)
        )
        ''')
        
        self.cursor.execute('''
        CREATE TABLE IF NOT EXISTS invite_summary_logs (
            id INTEGER PRIMARY KEY,
            account_id INTEGER,
            target_chat_id INTEGER,
            account_phone TEXT,
            target_chat_title TEXT,
            invited_count INTEGER,
            errors_count INTEGER,
            date TEXT,
            log_time INTEGER,
            FOREIGN KEY (account_id) REFERENCES accounts (id),
            FOREIGN KEY (target_chat_id) REFERENCES target_chats (id)
        )
        ''')
        
        self.cursor.execute('''
        CREATE TABLE IF NOT EXISTS invites (
            id INTEGER PRIMARY KEY,
            account_id INTEGER,
            target_chat_id INTEGER,
            parsed_file_id INTEGER,
            total_users INTEGER,
            current_invited INTEGER DEFAULT 0,
            active BOOLEAN DEFAULT 1,
            completed BOOLEAN DEFAULT 0,
            created_time INTEGER,
            last_update INTEGER,
            FOREIGN KEY (account_id) REFERENCES accounts (id),
            FOREIGN KEY (target_chat_id) REFERENCES target_chats (id),
            FOREIGN KEY (parsed_file_id) REFERENCES parsed_files (id)
        )
        ''')

        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS bought_accounts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                phone TEXT,
                session_filename TEXT,
                item_id INTEGER,
                added_time INTEGER
            )
            ''')
        
        self.conn.commit()
    
    def _check_and_update_schema(self):
        """Check if the database schema is up to date and update if needed"""
        self.cursor.execute("PRAGMA table_info(accounts)")
        columns = [column[1] for column in self.cursor.fetchall()]
        
        if 'about' not in columns:
            print("Adding 'about' column to accounts table")
            self.cursor.execute("ALTER TABLE accounts ADD COLUMN about TEXT")
            self.conn.commit()
        
        self.cursor.execute("PRAGMA table_info(accounts)")
        columns = [column[1] for column in self.cursor.fetchall()]
        if 'birthday' not in columns:
            print("Adding 'birthday' column to accounts table")
            self.cursor.execute("ALTER TABLE accounts ADD COLUMN birthday TEXT")
            self.conn.commit()
            print("Birthday column added successfully")
        
        self.cursor.execute("PRAGMA table_info(accounts)")
        columns = [column[1] for column in self.cursor.fetchall()]
        if 'proxy' not in columns:
            print("Adding 'proxy' column to accounts table")
            self.cursor.execute("ALTER TABLE accounts ADD COLUMN proxy TEXT")
            self.conn.commit()
            print("Proxy column added successfully")
        
        self.cursor.execute("PRAGMA table_info(source_chats)")
        columns = [column[1] for column in self.cursor.fetchall()]
        
        if 'account_id' not in columns:
            print("Adding 'account_id' column to source_chats table")
            self.cursor.execute("ALTER TABLE source_chats ADD COLUMN account_id INTEGER REFERENCES accounts(id)")
            self.conn.commit()
        
        self.cursor.execute("PRAGMA table_info(target_chats)")
        columns = [column[1] for column in self.cursor.fetchall()]
        
        if 'account_id' not in columns:
            print("Adding 'account_id' column to target_chats table")
            self.cursor.execute("ALTER TABLE target_chats ADD COLUMN account_id INTEGER REFERENCES accounts(id)")
            self.conn.commit()

    def validate_accounts(self):
        """Check all accounts in the database and return valid ones as dictionaries"""
        valid_accounts = []
        
        try:
            self.cursor.execute('SELECT * FROM accounts')
            accounts = self.cursor.fetchall()
            
            for account in accounts:
                account_dict = dict(zip(account.keys(), account))
                valid_accounts.append(account_dict)
            
            return valid_accounts
        except Exception as e:
            print(f"Error validating accounts: {e}")
            return []

    def add_account(self, phone, session_file, first_name="", last_name="", username="", about="", proxy=None):
        current_time = int(time.time())
        self.cursor.execute('''
        INSERT OR REPLACE INTO accounts 
        (phone, session_file, first_name, last_name, username, added_date, last_used, about, proxy)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (phone, session_file, first_name, last_name, username, current_time, current_time, about, proxy))
        self.conn.commit()
        return self.cursor.lastrowid

    
    def get_accounts(self, status=None):
        """Get accounts, optionally filtered by status"""
        if status:
            self.cursor.execute('SELECT * FROM accounts WHERE status = ? ORDER BY added_date DESC', (status,))
        else:
            self.cursor.execute('SELECT * FROM accounts ORDER BY added_date DESC')
        accounts = self.cursor.fetchall()
        return [dict(zip(account.keys(), account)) for account in accounts]
    
    def get_account(self, account_id):
        self.cursor.execute('SELECT * FROM accounts WHERE id = ?', (account_id,))
        account = self.cursor.fetchone()
        if account:
            return dict(zip(account.keys(), account))
        return None
    
    def update_account_status(self, account_id, status, ban_info=None):
        self.cursor.execute('''
        UPDATE accounts 
        SET status = ?, ban_info = ?
        WHERE id = ?
        ''', (status, json.dumps(ban_info) if ban_info else None, account_id))
        self.conn.commit()

    def update_account_about(self, account_id, about_text):
        """Update account about/bio text without changing account status"""
        self.cursor.execute('''
        UPDATE accounts 
        SET about = ?, last_used = ?
        WHERE id = ?
        ''', (about_text, int(time.time()), account_id))
        self.conn.commit()

    def update_account_birthday(self, account_id, birthday):
        """Update account birthday without changing account status"""
        self._check_and_update_schema()
        
        try:
            self.cursor.execute('''
            UPDATE accounts 
            SET birthday = ?, last_used = ?
            WHERE id = ?
            ''', (birthday, int(time.time()), account_id))
            self.conn.commit()
            
            self.cursor.execute('SELECT birthday FROM accounts WHERE id = ?', (account_id,))
            saved_birthday = self.cursor.fetchone()
            print(f"Updated birthday for account {account_id}. Saved value: {saved_birthday['birthday'] if saved_birthday else 'Not found'}")
            
            return True
        except Exception as e:
            print(f"Error updating birthday: {e}")
            return False

    def update_account_info(self, account_id, first_name=None, last_name=None, username=None):
        query = 'UPDATE accounts SET '
        params = []
        
        if first_name is not None:
            query += 'first_name = ?, '
            params.append(first_name)
        
        if last_name is not None:
            query += 'last_name = ?, '
            params.append(last_name)
        
        if username is not None:
            query += 'username = ?, '
            params.append(username)
        
        query += 'last_used = ? WHERE id = ?'
        params.extend([int(time.time()), account_id])
        
        self.cursor.execute(query, params)
        self.conn.commit()
    
    def update_account_invite_stats(self, account_id, success=0, failed=0):
        self.cursor.execute('''
        UPDATE accounts 
        SET invites_sent = invites_sent + ?, 
            invites_failed = invites_failed + ?,
            last_used = ?
        WHERE id = ?
        ''', (success, failed, int(time.time()), account_id))
        self.conn.commit()
    
    def delete_account(self, account_id):
        self.cursor.execute('DELETE FROM accounts WHERE id = ?', (account_id,))
        self.conn.commit()

    def add_bought_account(self, phone: str, session_filename: str, item_id: int):
        current_time = int(time.time())
        self.cursor.execute('''
        INSERT OR REPLACE INTO bought_accounts
        (phone, session_filename, item_id, added_time)
        VALUES (?, ?, ?, ?)
        ''', (phone, session_filename, item_id, current_time))
        self.conn.commit()

    def get_bought_accounts(self):
        self.cursor.execute('SELECT * FROM bought_accounts')
        return self.cursor.fetchall()

    def add_source_chat(self, chat_id, username, title, link=None, account_id=None):
        current_time = int(time.time())
        self.cursor.execute('''
        INSERT OR REPLACE INTO source_chats 
        (chat_id, username, title, link, added_date, account_id)
        VALUES (?, ?, ?, ?, ?, ?)
        ''', (chat_id, username, title, link, current_time, account_id))
        self.conn.commit()
        return self.cursor.lastrowid
    
    def get_source_chats(self):
        self.cursor.execute('''
        SELECT sc.*, 
               a.first_name as account_first_name, 
               a.last_name as account_last_name,
               a.phone as account_phone
        FROM source_chats sc
        LEFT JOIN accounts a ON sc.account_id = a.id
        ORDER BY sc.added_date DESC
        ''')
        return self.cursor.fetchall()
    
    def get_source_chat(self, chat_id):
        self.cursor.execute('SELECT * FROM source_chats WHERE id = ?', (chat_id,))
        return self.cursor.fetchone()
    
    def delete_source_chat(self, chat_id):
        self.cursor.execute('DELETE FROM source_chats WHERE id = ?', (chat_id,))
        self.conn.commit()
    
    def update_source_chat_stats(self, chat_id, total_members=None, parsed_members=None):
        if total_members is None and parsed_members is None:
            return
        
        query_parts = []
        params = []
        
        if total_members is not None:
            query_parts.append('total_members = ?')
            params.append(total_members)
        
        if parsed_members is not None:
            query_parts.append('parsed_members = ?')
            params.append(parsed_members)
        
        if not query_parts:
            return
        
        query = f'UPDATE source_chats SET {", ".join(query_parts)} WHERE id = ?'
        params.append(chat_id)
        
        self.cursor.execute(query, params)
        self.conn.commit()
    
    def add_target_chat(self, chat_id, username, title, link=None, file_name=None, account_id=None):
        current_time = int(time.time())
        self.cursor.execute('''
        INSERT OR REPLACE INTO target_chats 
        (chat_id, username, title, link, added_date, file_name, account_id)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (chat_id, username, title, link, current_time, file_name, account_id))
        self.conn.commit()
        return self.cursor.lastrowid
    
    def get_target_chats(self):
        self.cursor.execute('''
        SELECT tc.*, 
               a.first_name as account_first_name, 
               a.last_name as account_last_name,
               a.phone as account_phone
        FROM target_chats tc
        LEFT JOIN accounts a ON tc.account_id = a.id  
        ORDER BY tc.added_date DESC
        ''')
        return self.cursor.fetchall()
    
    def get_target_chat(self, chat_id):
        self.cursor.execute('SELECT * FROM target_chats WHERE id = ?', (chat_id,))
        return self.cursor.fetchone()
    
    def delete_target_chat(self, chat_id):
        self.cursor.execute('DELETE FROM target_chats WHERE id = ?', (chat_id,))
        self.conn.commit()
    
    def update_target_chat_invites(self, chat_id, invites_sent):
        self.cursor.execute('''
        UPDATE target_chats 
        SET invites_sent = invites_sent + ?
        WHERE id = ?
        ''', (invites_sent, chat_id))
        self.conn.commit()
    
    def add_parsed_file(self, file_name, source_chat_id, total_users, parse_type):
        current_time = int(time.time())
        self.cursor.execute('''
        INSERT OR REPLACE INTO parsed_files 
        (file_name, source_chat_id, total_users, parse_type, added_date)
        VALUES (?, ?, ?, ?, ?)
        ''', (file_name, source_chat_id, total_users, parse_type, current_time))
        self.conn.commit()
        return self.cursor.lastrowid
    
    def get_parsed_files(self):
        self.cursor.execute('''
        SELECT pf.*, sc.title as chat_title 
        FROM parsed_files pf 
        JOIN source_chats sc ON pf.source_chat_id = sc.id 
        ORDER BY pf.added_date DESC
        ''')
        return self.cursor.fetchall()
    
    def get_parsed_file(self, file_id):
        self.cursor.execute('SELECT * FROM parsed_files WHERE id = ?', (file_id,))
        return self.cursor.fetchone()
    
    def delete_parsed_file(self, file_id):
        self.cursor.execute('DELETE FROM parsed_files WHERE id = ?', (file_id,))
        self.conn.commit()
    
    def update_invite_progress(self, account_id, target_chat_id, source_file_id, position):
        current_time = int(time.time())
        self.cursor.execute('''
        INSERT OR REPLACE INTO invite_progress 
        (account_id, target_chat_id, source_file_id, last_position, last_invite_time)
        VALUES (?, ?, ?, ?, ?)
        ''', (account_id, target_chat_id, source_file_id, position, current_time))
        self.conn.commit()
    
    def get_invite_progress(self, account_id, target_chat_id, source_file_id):
        self.cursor.execute('''
        SELECT * FROM invite_progress 
        WHERE account_id = ? AND target_chat_id = ? AND source_file_id = ?
        ''', (account_id, target_chat_id, source_file_id))
        return self.cursor.fetchone()
    
    def get_invite_settings(self):
        self.cursor.execute('SELECT * FROM invite_settings ORDER BY id DESC LIMIT 1')
        return self.cursor.fetchone()
    
    def update_invite_settings(self, max_invites_per_12h=None, max_invites_per_24h=None, 
                              invite_interval_min=None, invite_interval_max=None):
        settings = self.get_invite_settings()
        
        max_invites_per_12h = max_invites_per_12h if max_invites_per_12h is not None else settings['max_invites_per_12h']
        max_invites_per_24h = max_invites_per_24h if max_invites_per_24h is not None else settings['max_invites_per_24h']
        invite_interval_min = invite_interval_min if invite_interval_min is not None else settings['invite_interval_min']
        invite_interval_max = invite_interval_max if invite_interval_max is not None else settings['invite_interval_max']
        
        self.cursor.execute('''
        UPDATE invite_settings 
        SET max_invites_per_12h = ?, 
            max_invites_per_24h = ?, 
            invite_interval_min = ?, 
            invite_interval_max = ?,
            last_updated = ?
        WHERE id = ?
        ''', (max_invites_per_12h, max_invites_per_24h, invite_interval_min, 
              invite_interval_max, int(time.time()), settings['id']))
        self.conn.commit()
    
    def close(self):
        if self.conn:
            self.conn.close()

    def get_user(self, user_id):
        self.cursor.execute('SELECT * FROM users WHERE id = ?', (user_id,))
        user = self.cursor.fetchone()
        
        if not user:
            current_time = int(time.time())
            self.cursor.execute('''
            INSERT INTO users (id, register_date, last_active)
            VALUES (?, ?, ?)
            ''', (user_id, current_time, current_time))
            self.conn.commit()
            
            self.cursor.execute('SELECT * FROM users WHERE id = ?', (user_id,))
            user = self.cursor.fetchone()
            
        return user
    
    def get_accounts_count(self):
        self.cursor.execute('SELECT COUNT(*) FROM accounts')
        return self.cursor.fetchone()[0]
    
    def get_source_chats_count(self):
        self.cursor.execute('SELECT COUNT(*) FROM source_chats')
        return self.cursor.fetchone()[0]
    
    def get_target_chats_count(self):
        self.cursor.execute('SELECT COUNT(*) FROM target_chats')
        return self.cursor.fetchone()[0]
    
    def add_invite_log(self, account_id, target_chat_id, user_id, status, error_message=None):
        current_time = int(time.time())
        self.cursor.execute('''
        INSERT INTO invite_logs 
        (account_id, target_chat_id, user_id, status, error_message, invite_time)
        VALUES (?, ?, ?, ?, ?, ?)
        ''', (account_id, target_chat_id, user_id, status, error_message, current_time))
        self.conn.commit()
    
    def add_invite_summary_log(self, account_id, target_chat_id, invited_count, errors_count):
        current_time = int(time.time())
        date_str = datetime.fromtimestamp(current_time).strftime('%Y-%m-%d %H:%M:%S')
        
        self.cursor.execute('SELECT phone FROM accounts WHERE id = ?', (account_id,))
        account = self.cursor.fetchone()
        account_phone = account['phone'] if account else "Unknown"
        
        self.cursor.execute('SELECT title FROM target_chats WHERE id = ?', (target_chat_id,))
        target_chat = self.cursor.fetchone()
        target_chat_title = target_chat['title'] if target_chat else "Unknown"
        
        self.cursor.execute('''
        INSERT INTO invite_summary_logs 
        (account_id, target_chat_id, account_phone, target_chat_title, invited_count, errors_count, date, log_time)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (account_id, target_chat_id, account_phone, target_chat_title, invited_count, errors_count, date_str, current_time))
        self.conn.commit()
    
    def get_invite_logs(self, limit=20):
        self.cursor.execute('''
        SELECT * FROM invite_summary_logs
        ORDER BY log_time DESC
        LIMIT ?
        ''', (limit,))
        return self.cursor.fetchall()
    
    def get_invite_stats(self, period_hours=24):
        current_time = int(time.time())
        period_start = current_time - (period_hours * 3600)
        
        self.cursor.execute('''
        SELECT COUNT(*) as total_count,
               SUM(CASE WHEN status = 'success' THEN 1 ELSE 0 END) as success_count,
               SUM(CASE WHEN status = 'error' THEN 1 ELSE 0 END) as error_count
        FROM invite_logs
        WHERE invite_time >= ?
        ''', (period_start,))
        
        result = self.cursor.fetchone()
        return {
            'total_count': result['total_count'] or 0,
            'success_count': result['success_count'] or 0,
            'error_count': result['error_count'] or 0
        }
    
    def get_invites_count_for_period(self, period_hours=24):
        current_time = int(time.time())
        period_start = current_time - (period_hours * 3600)
        
        self.cursor.execute('''
        SELECT COUNT(*) FROM invite_logs
        WHERE status = 'success' AND invite_time >= ?
        ''', (period_start,))
        
        return self.cursor.fetchone()[0]
    
    def create_invite(self, account_id, target_chat_id, parsed_file_id, total_users):
        current_time = int(time.time())
        self.cursor.execute('''
        INSERT INTO invites
        (account_id, target_chat_id, parsed_file_id, total_users, current_invited, active, created_time, last_update)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (account_id, target_chat_id, parsed_file_id, total_users, 0, True, current_time, current_time))
        self.conn.commit()
        return self.cursor.lastrowid
    
    def get_invite(self, invite_id):
        self.cursor.execute('SELECT * FROM invites WHERE id = ?', (invite_id,))
        return self.cursor.fetchone()
    
    def get_active_invites(self):
        self.cursor.execute('SELECT * FROM invites WHERE active = 1 OR (active = 0 AND completed = 0)')
        return self.cursor.fetchall()
    
    def get_invite_by_components(self, account_id, target_chat_id, parsed_file_id):
        self.cursor.execute('''
        SELECT * FROM invites 
        WHERE account_id = ? AND target_chat_id = ? AND parsed_file_id = ? AND completed = 0
        ''', (account_id, target_chat_id, parsed_file_id))
        return self.cursor.fetchone()
    
    def update_invite_status(self, invite_id, active):
        current_time = int(time.time())
        self.cursor.execute('''
        UPDATE invites
        SET active = ?, last_update = ?
        WHERE id = ?
        ''', (active, current_time, invite_id))
        self.conn.commit()
    
    def update_invite_progress(self, invite_id, current_position):
        current_time = int(time.time())
        self.cursor.execute('''
        UPDATE invites
        SET current_invited = ?, last_update = ?
        WHERE id = ?
        ''', (current_position, current_time, invite_id))
        self.conn.commit()
    
    def complete_invite(self, invite_id):
        current_time = int(time.time())
        self.cursor.execute('''
        UPDATE invites
        SET completed = 1, active = 0, last_update = ?
        WHERE id = ?
        ''', (current_time, invite_id))
        self.conn.commit()
    
    def delete_invite(self, invite_id):
        self.cursor.execute('DELETE FROM invites WHERE id = ?', (invite_id,))
        self.conn.commit()
    
    def get_parsed_users(self, file_id):
        self.cursor.execute('SELECT file_name FROM parsed_files WHERE id = ?', (file_id,))
        file_info = self.cursor.fetchone()
        
        if not file_info or not file_info['file_name']:
            return []
        
        file_path = os.path.join('data', 'parsed_users', file_info['file_name'])
        
        if not os.path.exists(file_path):
            return []
        
        try:
            users = []
            with open(file_path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    
                    parts = line.split(',', 3)
                    if len(parts) >= 1:
                        user_id = int(parts[0]) if parts[0].isdigit() else 0
                        username = parts[1] if len(parts) > 1 else ""
                        first_name = parts[2] if len(parts) > 2 else ""
                        last_name = parts[3] if len(parts) > 3 else ""
                        
                        if user_id > 0:
                            users.append({
                                'user_id': user_id,
                                'username': username,
                                'first_name': first_name,
                                'last_name': last_name
                            })
            
            return users
        except Exception as e:
            print(f"Error loading users from file: {e}")
            return []

    def update_target_chat_account(self, chat_id, account_id):
        """Update the account associated with a target chat"""
        try:
            self.cursor.execute(
                "UPDATE target_chats SET account_id = ? WHERE id = ?",
                (account_id, chat_id)
            )
            self.conn.commit()
            return True
        except Exception as e:
            print(f"Error updating target chat account: {e}")
            return False

    def update_account_proxy(self, account_id, proxy_str):
        """Update the proxy for an account"""
        self.cursor.execute('''
        UPDATE accounts SET proxy = ? WHERE id = ?
        ''', (proxy_str, account_id))
        self.conn.commit()
        return self.cursor.rowcount > 0

    def get_account_proxy(self, account_id):
        """Get proxy for an account"""
        self.cursor.execute('SELECT proxy FROM accounts WHERE id = ?', (account_id,))
        result = self.cursor.fetchone()
        if result and result[0]:
            return result[0]
        return None

db = Database() 