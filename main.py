import os
import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart
from aiogram.types import Message, BotCommand
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.storage.memory import MemoryStorage

from config import BOT_TOKEN
from database import db
from telegram_client import client_manager
from bot.handlers import accounts, source_chats, target_chats, parsing, inviting, invite_settings as settings, lzt_autobuying as lzt
from bot.keyboards import main_menu_keyboard

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

async def set_commands(bot: Bot):
    commands = [
        BotCommand(command="/start", description="Запустить бота"),
        BotCommand(command="/menu", description="Главное меню"),
    ]
    await bot.set_my_commands(commands)

async def on_startup(bot):
    """Настройка бота при запуске"""
    await set_commands(bot)
    # Создание таблиц БД если их нет
    db._create_tables()
    # Клиенты уже проверены при запуске в main()

async def on_shutdown(bot):
    """Действия при выключении бота"""
    await client_manager.close_all_clients()

async def check_session_files():
    """Проверка файлов сессий и их добавление в базу данных"""
    session_dir = "sessions"
    # Создаем папку если ее нет
    os.makedirs(session_dir, exist_ok=True)
    
    # Проверяем файлы в папке сессий
    for filename in os.listdir(session_dir):
        if filename.endswith(".session"):
            phone = filename.replace(".session", "")
            # Проверяем, есть ли уже такой аккаунт в базе
            if not db.check_account_exists(phone):
                logging.info(f"Найден новый файл сессии: {filename}, добавляем аккаунт с номером {phone}")
                # Добавляем аккаунт в базу данных
                account_id = db.add_account(phone)
                # Отправляем оповещение через бота
                if account_id:
                    # Сообщение будет отправлено в главное меню при первом запуске
                    logging.info(f"Аккаунт успешно добавлен с ID: {account_id}")

async def main():
    logging.info("Validating database structure and accounts...")
    db._check_and_update_schema()
    
    valid_count, invalid_count = await client_manager.validate_all_accounts()
    logging.info(f"Account validation complete. Valid: {valid_count}, Invalid: {invalid_count}")
    
    # Создание и настройка диспетчера
    storage = MemoryStorage()
    dp = Dispatcher(storage=storage)
    
    # Регистрация обработчиков
    dp.include_router(accounts.router)
    dp.include_router(source_chats.router)
    dp.include_router(target_chats.router)
    dp.include_router(parsing.router)
    dp.include_router(inviting.router)
    dp.include_router(settings.router)
    dp.include_router(lzt.router)
    
    # Создание экземпляра бота
    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    
    # Установка обработчиков запуска и остановки
    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)
    
    # Проверка сессионных файлов при запуске
    await check_session_files()
    
    @dp.message(CommandStart())
    async def command_start_handler(message: Message):
        await message.answer(
            f"<b>👋 Привет, {message.from_user.first_name}!\n\n"
            "Это бот для управления аккаунтами Telegram и приглашения пользователей в чаты.\n"
            "Используйте меню ниже для управления.</b>",
            reply_markup=main_menu_keyboard()
        )
    
    logging.info("Starting bot")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main()) 