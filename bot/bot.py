import asyncio
import logging
import sys
import os
from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.client.default import DefaultBotProperties

from config import BOT_TOKEN, ADMIN_ID, SESSIONS_DIR
from bot.handlers import routers
from telegram_client import client_manager
from database import db

logging.basicConfig(level=logging.INFO, stream=sys.stdout)

async def run_bot():
    os.makedirs(SESSIONS_DIR, exist_ok=True)
    
    accounts = db.get_accounts()
    if accounts:
        for account in accounts:
            session_file = account['session_file']
            await client_manager.add_client(session_file)
    
    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    
    dp = Dispatcher(storage=MemoryStorage())
    
    for router in routers:
        dp.include_router(router)
    
    commands = [
        {"command": "start", "description": "Запустить бота"},
        {"command": "menu", "description": "Открыть главное меню"}
    ]
    await bot.set_my_commands(commands)
    
    logging.info("Starting bot")
    await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())


if __name__ == "__main__":
    asyncio.run(run_bot())
 