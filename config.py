import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", 0))

API_ID = int(os.getenv("API_ID", 123456))
API_HASH = os.getenv("API_HASH", "default_api_hash")

DATA_DIR = "data"
ACCOUNTS_DIR = os.path.join(DATA_DIR, "accounts")
SESSIONS_DIR = os.path.join(ACCOUNTS_DIR, "sessions")
SOURCE_CHATS_DIR = os.path.join(DATA_DIR, "source_chats")
TARGET_CHATS_DIR = os.path.join(DATA_DIR, "target_chats")
PARSED_USERS_DIR = os.path.join(DATA_DIR, "parsed_users")
DB_FILE = os.path.join(DATA_DIR, "database.sqlite")

DEFAULT_INVITE_SETTINGS = {
    "max_invites_per_12h": 35,
    "max_invites_per_24h": 50,
    "invite_interval_min": 30,
    "invite_interval_max": 120,
}

for directory in [DATA_DIR, ACCOUNTS_DIR, SESSIONS_DIR, 
                 SOURCE_CHATS_DIR, TARGET_CHATS_DIR, PARSED_USERS_DIR]:
    os.makedirs(directory, exist_ok=True) 