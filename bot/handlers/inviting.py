import asyncio
import random
import time
import logging
from datetime import datetime
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from telethon.errors import UserPrivacyRestrictedError, FloodWaitError, ChatAdminRequiredError
from telethon.tl.functions.channels import InviteToChannelRequest
from telethon.tl.functions.messages import AddChatUserRequest
from telethon.tl.types import Channel, Chat

from database import db
from telegram_client import client_manager
from bot.keyboards import (
    inviting_keyboard,
    active_invites_keyboard,
    back_button,
    main_menu_keyboard,
    yes_no_keyboard,
    choose_account_keyboard,
    choose_target_chat_keyboard,
    create_chat_keyboard
)

router = Router()

ACTIVE_INVITES = {}

class InvitingStates(StatesGroup):
    waiting_for_target_chat = State()
    waiting_for_account = State()
    waiting_for_parsed_file = State()
    waiting_for_chat_title = State()
    waiting_for_chat_creation = State()


@router.callback_query(F.data == "inviting")
async def callback_inviting(callback: CallbackQuery, state: FSMContext):
    """Handle inviting menu callback"""
    # Сохраняем текущее меню в состоянии
    await state.update_data(previous_menu='inviting')
    await state.clear()
    
    invites = db.get_active_invites()
    
    text = "🔄 ИНВАЙТИНГ\n\n"
    
    if invites:
        for inv in invites:
            # Безопасно получаем информацию о пользователе с учетом возможного отсутствия ключей
            if 'account_name' in inv:
                account_name = inv['account_name']
            elif 'account_id' in inv:
                account = db.get_account(inv['account_id'])
                if account:
                    phone = account['phone'] if 'phone' in account else 'Неизвестный'
                    account_name = f"Аккаунт {phone}"
                else:
                    account_name = "Неизвестный аккаунт"
            else:
                account_name = "Неизвестный аккаунт"
                
            target_chat = inv['target_chat_title'] if 'target_chat_title' in inv else 'Неизвестный чат'
            progress = f"{inv['current_invited']}/{inv['total_users']}"
            
            text += f"👤 {account_name} → 📣 {target_chat}\n"
            text += f"Прогресс: {progress}\n\n"
        
        try:
            await callback.message.edit_text(
                text,
                reply_markup=inviting_menu_keyboard(invites),
                parse_mode="HTML"
            )
        except Exception as e:
            if "message is not modified" not in str(e):
                raise
    else:
        text += "У вас нет активных процессов инвайтинга.\n\n"
        text += "Нажмите кнопку ниже, чтобы начать новый процесс инвайтинга."
        
        try:
            await callback.message.edit_text(
                text,
                reply_markup=inviting_menu_keyboard(),
                parse_mode="HTML"
            )
        except Exception as e:
            if "message is not modified" not in str(e):
                raise
    
    await callback.answer()


def inviting_menu_keyboard(invites=None):
    """Create inviting menu keyboard"""
    kb = InlineKeyboardBuilder()
    
    if invites:
        for invite in invites:
            invite_id = invite['id']
            
            account = db.get_account(invite['account_id'])
            target_chat = db.get_target_chat(invite['target_chat_id'])
            
            account_phone = account['phone'] if account else "Unknown"
            target_chat_title = target_chat['title'] if target_chat else "Unknown"
            
            progress = f"{invite['current_invited']}/{invite['total_users']}"
            
            kb.button(
                text=f"{target_chat_title} | {account_phone} ({progress})", 
                callback_data=f"invite_details:{invite_id}"
            )
    
    kb.button(text="➕ Начать новый инвайтинг", callback_data="start_new_inviting")
    kb.button(text="🔙 В главное меню", callback_data="main_menu")
    kb.adjust(1)
    return kb.as_markup()


@router.callback_query(F.data == "start_new_inviting")
async def callback_start_new_inviting(callback: CallbackQuery, state: FSMContext):
    """Handle start new inviting callback"""
    # Сохраняем текущее меню в состоянии
    await state.update_data(previous_menu='inviting')
    await state.set_state(InvitingStates.waiting_for_target_chat)
    
    # Получаем целевые чаты
    target_chats = db.get_target_chats()
    
    if not target_chats:
        await callback.message.edit_text(
            "❌ У вас нет добавленных целевых чатов.\n\n"
            "Сначала добавьте чат для инвайтинга через раздел \"Чаты для инвайта\".",
            reply_markup=back_button("inviting"),
            parse_mode="HTML"
        )
        await callback.answer()
        return
    
    # Проверяем, есть ли файлы с пользователями
    parsed_files = db.get_parsed_files()
    if not parsed_files:
        await callback.message.edit_text(
            "❌ У вас нет файлов с пользователями для инвайтинга.\n\n"
            "Сначала выполните парсинг пользователей через раздел \"Парсинг\".",
            reply_markup=back_button("inviting"),
            parse_mode="HTML"
        )
        await callback.answer()
        return
    
    await callback.message.edit_text(
        "📣 Выберите чат для инвайтинга:",
        reply_markup=choose_target_chat_keyboard(target_chats),
        parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(InvitingStates.waiting_for_target_chat, F.data.startswith("select_target_chat:"))
async def callback_select_target_chat(callback: CallbackQuery, state: FSMContext):
    """Handle target chat selection for inviting"""
    target_chat_id = int(callback.data.split(':')[1])
    target_chat = db.get_target_chat(target_chat_id)
    
    if not target_chat:
        try:
            await callback.message.edit_text(
                "❌ Целевой чат не найден.",
                reply_markup=back_button("inviting")
            )
        except Exception as e:
            if "message is not modified" not in str(e):
                raise
        await callback.answer()
        return
    
    await state.update_data(target_chat_id=target_chat_id)
    
    accounts = db.get_accounts()
    await state.set_state(InvitingStates.waiting_for_account)
    
    try:
        await callback.message.edit_text(
            f"👤 Выберите аккаунт для инвайтинга в чат {target_chat['title']}:",
            reply_markup=choose_account_keyboard(accounts)
        )
    except Exception as e:
        if "message is not modified" not in str(e):
            raise
    await callback.answer()


@router.callback_query(InvitingStates.waiting_for_account, F.data.startswith("select_account:"))
async def callback_select_account(callback: CallbackQuery, state: FSMContext):
    """Handle account selection for inviting"""
    account_id = int(callback.data.split(':')[1])
    account = db.get_account(account_id)
    
    if not account:
        try:
            await callback.message.edit_text(
                "❌ Аккаунт не найден.",
                reply_markup=back_button("inviting")
            )
        except Exception as e:
            if "message is not modified" not in str(e):
                raise
        await callback.answer()
        return
    
    await state.update_data(account_id=account_id)
    
    state_data = await state.get_data()
    if state_data.get('creating_new_chat'):
        try:
            await callback.message.edit_text(
                "📝 Введите название нового чата:",
                reply_markup=back_button("start_new_inviting")
            )
        except Exception as e:
            if "message is not modified" not in str(e):
                raise
        await state.set_state(InvitingStates.waiting_for_chat_title)
        await callback.answer()
        return
    
    parsed_files = db.get_parsed_files()
    await state.set_state(InvitingStates.waiting_for_parsed_file)
    
    kb = InlineKeyboardBuilder()
    
    for file in parsed_files:
        kb.button(
            text=f"{file['file_name']} ({file['total_users']} пользователей)", 
            callback_data=f"select_parsed_file:{file['id']}"
        )
    
    kb.button(text="🔙 Отмена", callback_data="cancel")
    kb.adjust(1)
    
    try:
        await callback.message.edit_text(
            "📁 Выберите файл с пользователями для инвайтинга:",
            reply_markup=kb.as_markup()
        )
    except Exception as e:
        if "message is not modified" not in str(e):
            raise
    await callback.answer()


@router.callback_query(InvitingStates.waiting_for_parsed_file, F.data.startswith("select_parsed_file:"))
async def callback_select_parsed_file(callback: CallbackQuery, state: FSMContext):
    """Handle parsed file selection for inviting"""
    parsed_file_id = int(callback.data.split(':')[1])
    parsed_file = db.get_parsed_file(parsed_file_id)
    
    if not parsed_file:
        try:
            await callback.message.edit_text(
                "❌ Файл не найден.",
                reply_markup=back_button("inviting")
            )
        except Exception as e:
            if "message is not modified" not in str(e):
                raise
        await callback.answer()
        return
    
    state_data = await state.get_data()
    
    target_chat_id = state_data.get('target_chat_id')
    account_id = state_data.get('account_id')
    
    target_chat = db.get_target_chat(target_chat_id)
    account = db.get_account(account_id)
    
    if not target_chat or not account:
        try:
            await callback.message.edit_text(
                "❌ Ошибка: Не найден чат или аккаунт.",
                reply_markup=back_button("inviting")
            )
        except Exception as e:
            if "message is not modified" not in str(e):
                raise
        await callback.answer()
        return
    
    users = db.get_parsed_users(parsed_file['id'])
    
    if not users:
        try:
            await callback.message.edit_text(
                "❌ В файле нет пользователей для инвайтинга.",
                reply_markup=back_button("inviting")
            )
        except Exception as e:
            if "message is not modified" not in str(e):
                raise
        await callback.answer()
        return
    
    invite_id = db.create_invite(
        account_id=account_id,
        target_chat_id=target_chat_id,
        parsed_file_id=parsed_file_id,
        total_users=len(users)
    )
    
    try:
        await callback.message.edit_text(
            "✅ Процесс инвайтинга успешно создан!\n\n"
            "📱 Аккаунт: {account['phone']}\n"
            "💬 Чат: {target_chat['title']}\n"
            "📊 Всего пользователей: {len(users)}\n\n"
            "▶️ Начинаю процесс инвайтинга...",
            reply_markup=back_button("inviting")
        )
    except Exception as e:
        if "message is not modified" not in str(e):
            raise
    
    ACTIVE_INVITES[invite_id] = True
    asyncio.create_task(process_invite(invite_id))
    
    await callback.answer()


@router.callback_query(F.data == "create_new_chat")
async def callback_create_new_chat(callback: CallbackQuery, state: FSMContext):
    """Handle creating a new chat option"""
    accounts = db.get_accounts()
    
    if not accounts:
        try:
            await callback.message.edit_text(
                "❌ У вас нет добавленных аккаунтов.\n"
                "Пожалуйста, сначала добавьте аккаунт в разделе 'Аккаунты'.",
                reply_markup=back_button("inviting")
            )
        except Exception as e:
            if "message is not modified" not in str(e):
                raise
        await callback.answer()
        return
    
    try:
        await callback.message.edit_text(
            "👤 Выберите аккаунт, с которого будет создан новый чат:",
            reply_markup=choose_account_keyboard(accounts)
        )
    except Exception as e:
        if "message is not modified" not in str(e):
            raise
            
    await state.set_state(InvitingStates.waiting_for_account)
    await state.update_data(creating_new_chat=True)
    await callback.answer()

@router.message(InvitingStates.waiting_for_chat_title)
async def handle_chat_title(message: Message, state: FSMContext):
    """Handle chat title input for creating a new chat"""
    chat_title = message.text.strip()
    
    if not chat_title:
        await message.answer(
            "❌ Название чата не может быть пустым. Пожалуйста, введите название:",
            reply_markup=back_button("start_new_inviting")
        )
        return
    
    await state.update_data(chat_title=chat_title)
    
    await message.answer(
        f"📝 Будет создан новый чат с названием: {chat_title}\n\n"
        "Создать чат?",
        reply_markup=create_chat_keyboard()
    )
    await state.set_state(InvitingStates.waiting_for_chat_creation)

@router.callback_query(F.data == "confirm_create_chat", InvitingStates.waiting_for_chat_creation)
async def callback_confirm_create_chat(callback: CallbackQuery, state: FSMContext):
    """Handle confirmation of chat creation"""
    state_data = await state.get_data()
    
    account_id = state_data.get('account_id')
    chat_title = state_data.get('chat_title')
    
    if not account_id or not chat_title:
        try:
            await callback.message.edit_text(
                "❌ Недостаточно данных для создания чата.",
                reply_markup=back_button("inviting")
            )
        except Exception as e:
            if "message is not modified" not in str(e):
                raise
        await callback.answer()
        return
    
    account = db.get_account(account_id)
    if not account:
        try:
            await callback.message.edit_text(
                "❌ Аккаунт не найден.",
                reply_markup=back_button("inviting")
            )
        except Exception as e:
            if "message is not modified" not in str(e):
                raise
        await callback.answer()
        return
    
    try:
        await callback.message.edit_text(
            "⏳ Создаю новый чат '{chat_title}'..."
        )
    except Exception as e:
        if "message is not modified" not in str(e):
            raise
    
    chat_info, error = await client_manager.create_group_chat(account['phone'], chat_title)
    
    if not chat_info:
        try:
            await callback.message.edit_text(
                f"❌ Ошибка при создании чата: {error}",
                reply_markup=back_button("inviting")
            )
        except Exception as e:
            if "message is not modified" not in str(e):
                raise
        await callback.answer()
        return
    
    target_chat_id = db.add_target_chat(
        chat_id=chat_info['id'],
        username=chat_info['username'],
        title=chat_info['title'],
        link=chat_info['link']
    )
    
    await state.update_data(target_chat_id=target_chat_id)
    
    parsed_files = db.get_parsed_files()
    await state.set_state(InvitingStates.waiting_for_parsed_file)
    
    kb = InlineKeyboardBuilder()
    
    for file in parsed_files:
        kb.button(
            text=f"{file['file_name']} ({file['total_users']} пользователей)", 
            callback_data=f"select_parsed_file:{file['id']}"
        )
    
    kb.button(text="🔙 Отмена", callback_data="cancel")
    kb.adjust(1)
    
    try:
        await callback.message.edit_text(
            "✅ Чат '{chat_title}' успешно создан!\n\n"
            "📁 Выберите файл с пользователями для инвайтинга:",
            reply_markup=kb.as_markup()
        )
    except Exception as e:
        if "message is not modified" not in str(e):
            raise
    await callback.answer()


@router.callback_query(F.data.startswith("invite_details:"))
async def callback_invite_details(callback: CallbackQuery, state: FSMContext):
    """Handle invite details callback"""
    invite_id = int(callback.data.split(':')[1])
    invite = db.get_invite(invite_id)
    
    if not invite:
        try:
            await callback.message.edit_text(
                "❌ Процесс инвайтинга не найден.",
                reply_markup=back_button("inviting")
            )
        except Exception as e:
            if "message is not modified" not in str(e):
                raise
        await callback.answer()
        return
    
    account = db.get_account(invite['account_id'])
    target_chat = db.get_target_chat(invite['target_chat_id'])
    parsed_file = db.get_parsed_file(invite['parsed_file_id'])
    
    account_phone = account['phone'] if account else "Неизвестный аккаунт"
    target_chat_title = target_chat['title'] if target_chat else "Неизвестный чат"
    file_name = parsed_file['file_name'] if parsed_file else "Неизвестный файл"
    
    status = "✅ Активен" if invite['active'] else "⏸ Приостановлен"
    progress = f"{invite['current_invited']}/{invite['total_users']}"
    created_time = datetime.fromtimestamp(invite['created_time']).strftime('%d.%m.%y %H:%M')
    
    text = "🔄 Детали инвайтинга\n\n"
    text += f"📱 Аккаунт: {account_phone}\n"
    text += f"💬 Целевой чат: {target_chat_title}\n"
    text += f"📂 Файл: {file_name}\n"
    text += f"📊 Прогресс: {progress}\n"
    text += f"📡 Статус: {status}\n"
    text += f"⏱️ Запущен: {created_time}"
    
    kb = InlineKeyboardBuilder()
    
    if invite['active']:
        kb.button(text="⏸ Приостановить", callback_data=f"pause_invite:{invite_id}")
    else:
        kb.button(text="▶️ Возобновить", callback_data=f"resume_invite:{invite_id}")
    
    kb.button(text="🗑️ Удалить", callback_data=f"delete_invite:{invite_id}")
    kb.button(text="🔙 Назад", callback_data="inviting")
    kb.button(text="🔙 В главное меню", callback_data="main_menu")
    kb.adjust(1)
    
    try:
        await callback.message.edit_text(
            text,
            reply_markup=kb.as_markup()
        )
    except Exception as e:
        if "message is not modified" not in str(e):
            raise
    await callback.answer()


@router.callback_query(F.data.startswith("pause_invite:"))
async def callback_pause_invite(callback: CallbackQuery, state: FSMContext):
    """Handle pause invite callback"""
    invite_id = int(callback.data.split(':')[1])
    invite = db.get_invite(invite_id)
    
    if not invite:
        try:
            await callback.message.edit_text(
                "❌ Процесс инвайтинга не найден.",
                reply_markup=back_button("inviting")
            )
        except Exception as e:
            if "message is not modified" not in str(e):
                raise
        await callback.answer()
        return
    
    account = db.get_account(invite['account_id'])
    target_chat = db.get_target_chat(invite['target_chat_id'])
    
    account_phone = account['phone'] if account else "Неизвестный аккаунт"
    target_chat_title = target_chat['title'] if target_chat else "Неизвестный чат"
    
    db.update_invite_status(invite_id, active=False)
    
    ACTIVE_INVITES[invite_id] = False
    logging.info(f"Marked invite {invite_id} for stopping in global registry")
    
    try:
        await callback.message.edit_text(
            "⏸ Инвайтинг приостановлен\n\n"
            f"📱 Аккаунт: {account_phone}\n"
            f"💬 Чат: {target_chat_title}\n"
            f"📊 Прогресс: {invite['current_invited']}/{invite['total_users']}",
            reply_markup=back_button("inviting")
        )
    except Exception as e:
        if "message is not modified" not in str(e):
            raise
    await callback.answer()


@router.callback_query(F.data.startswith("resume_invite:"))
async def callback_resume_invite(callback: CallbackQuery, state: FSMContext):
    """Handle resume invite callback"""
    invite_id = int(callback.data.split(':')[1])
    invite = db.get_invite(invite_id)
    
    if not invite:
        try:
            await callback.message.edit_text(
                "❌ Процесс инвайтинга не найден.",
                reply_markup=back_button("inviting")
            )
        except Exception as e:
            if "message is not modified" not in str(e):
                raise
        await callback.answer()
        return
    
    account = db.get_account(invite['account_id'])
    target_chat = db.get_target_chat(invite['target_chat_id'])
    
    account_phone = account['phone'] if account else "Неизвестный аккаунт"
    target_chat_title = target_chat['title'] if target_chat else "Неизвестный чат"
    
    db.update_invite_status(invite_id, active=True)
    
    ACTIVE_INVITES[invite_id] = True
    logging.info(f"Marked invite {invite_id} as active in global registry")
    
    try:
        await callback.message.edit_text(
            "▶️ Инвайтинг возобновлен\n\n"
            f"📱 Аккаунт: {account_phone}\n"
            f"💬 Чат: {target_chat_title}\n"
            f"📊 Прогресс: {invite['current_invited']}/{invite['total_users']}",
            reply_markup=back_button("inviting")
        )
    except Exception as e:
        if "message is not modified" not in str(e):
            raise
    
    asyncio.create_task(process_invite(invite_id))
    
    await callback.answer()


@router.callback_query(F.data.startswith("delete_invite:"))
async def callback_delete_invite(callback: CallbackQuery, state: FSMContext):
    """Handle delete invite callback"""
    invite_id = int(callback.data.split(':')[1])
    invite = db.get_invite(invite_id)
    
    if not invite:
        try:
            await callback.message.edit_text(
                "❌ Процесс инвайтинга не найден.",
                reply_markup=back_button("inviting")
            )
        except Exception as e:
            if "message is not modified" not in str(e):
                raise
        await callback.answer()
        return
    
    account = db.get_account(invite['account_id'])
    target_chat = db.get_target_chat(invite['target_chat_id'])
    
    account_phone = account['phone'] if account else "Неизвестный аккаунт"
    target_chat_title = target_chat['title'] if target_chat else "Неизвестный чат"
    
    ACTIVE_INVITES[invite_id] = False
    logging.info(f"Marked invite {invite_id} for stopping before deletion in global registry")
    
    try:
        await callback.message.edit_text(
            "🗑️ Вы уверены, что хотите удалить процесс инвайтинга?\n\n"
            f"📱 Аккаунт: {account_phone}\n"
            f"💬 Чат: {target_chat_title}\n"
            f"📊 Прогресс: {invite['current_invited']}/{invite['total_users']}",
            reply_markup=yes_no_keyboard("delete_invite", invite_id)
        )
    except Exception as e:
        if "message is not modified" not in str(e):
            raise
    await callback.answer()


@router.callback_query(F.data.startswith("confirm_delete_invite:"))
async def callback_confirm_delete_invite(callback: CallbackQuery, state: FSMContext):
    """Handle delete invite confirmation"""
    invite_id = int(callback.data.split(':')[1])
    
    db.delete_invite(invite_id)
    
    if invite_id in ACTIVE_INVITES:
        del ACTIVE_INVITES[invite_id]
        logging.info(f"Removed invite {invite_id} from global registry")
    
    try:
        await callback.message.edit_text(
            "✅ Процесс инвайтинга успешно удален.",
            reply_markup=back_button("inviting")
        )
    except Exception as e:
        if "message is not modified" not in str(e):
            raise
    await callback.answer()


async def process_invite(invite_id):
    """Process invite in background"""
    logging.info(f"Starting invite process for invite_id={invite_id}")
    
    ACTIVE_INVITES[invite_id] = True
    
    invite = db.get_invite(invite_id)
    if not invite:
        logging.error(f"Invite with id={invite_id} not found")
        if invite_id in ACTIVE_INVITES:
            del ACTIVE_INVITES[invite_id]
        return
    
    account = db.get_account(invite['account_id'])
    target_chat = db.get_target_chat(invite['target_chat_id'])
    parsed_file = db.get_parsed_file(invite['parsed_file_id'])
    
    if not all([account, target_chat, parsed_file]):
        logging.error(f"Missing required data for invite_id={invite_id}. Account: {bool(account)}, Target chat: {bool(target_chat)}, Parsed file: {bool(parsed_file)}")
        db.update_invite_status(invite_id, active=False)
        if invite_id in ACTIVE_INVITES:
            del ACTIVE_INVITES[invite_id]
        return
    
    settings = db.get_invite_settings()
    min_interval = settings['invite_interval_min']
    max_interval = settings['invite_interval_max']
    max_invites_12h = settings['max_invites_per_12h']
    max_invites_24h = settings['max_invites_per_24h']
    
    logging.info(f"Invite settings: min_interval={min_interval}, max_interval={max_interval}, max_invites_12h={max_invites_12h}, max_invites_24h={max_invites_24h}")
    
    parsed_users = db.get_parsed_users(parsed_file['id'])
    
    start_index = invite['current_invited']
    filtered_users = []
    for user in parsed_users[start_index:]:
        if user['user_id'] != 123456789 and isinstance(user['user_id'], int) and user['user_id'] > 0:
            filtered_users.append(user)
        else:
            logging.warning(f"Skipping invalid user ID: {user['user_id']}")
            db.update_invite_progress(invite_id, start_index + 1)
            start_index += 1
    
    users_to_invite = filtered_users
    
    logging.info(f"Starting inviting from index {start_index}, total users to invite: {len(users_to_invite)}")
    
    client = client_manager.get_client(account['phone'])
    if not client:
        logging.error(f"Failed to get client for phone {account['phone']}")
        db.update_invite_status(invite_id, active=False)
        if invite_id in ACTIVE_INVITES:
            del ACTIVE_INVITES[invite_id]
        return
    
    if not client.is_connected() or not client._authorized:
        logging.error(f"Client is not connected or not authorized. Connected: {client.is_connected()}, Authorized: {client._authorized}")
        db.update_invite_status(invite_id, active=False)
        if invite_id in ACTIVE_INVITES:
            del ACTIVE_INVITES[invite_id]
        return
    
    invite_count = 0
    error_count = 0
    
    try:
        chat_entity = await client.get_entity(target_chat['chat_id'])
        logging.info(f"Successfully got entity for target chat {target_chat['title']} (ID: {target_chat['chat_id']})")
    except Exception as e:
        logging.error(f"Error getting target chat entity: {str(e)}")
        db.update_invite_status(invite_id, active=False)
        if invite_id in ACTIVE_INVITES:
            del ACTIVE_INVITES[invite_id]
        return
    
    for i, user in enumerate(users_to_invite):
        if invite_id in ACTIVE_INVITES and not ACTIVE_INVITES[invite_id]:
            logging.info(f"Invite {invite_id} stopped via global registry")
            break
        
        if i % 5 == 0:
            invite = db.get_invite(invite_id)
            if not invite or not invite['active']:
                logging.info(f"Invite is no longer active, stopping process")
                break
        
        invites_12h = db.get_invites_count_for_period(period_hours=12)
        invites_24h = db.get_invites_count_for_period(period_hours=24)
        
        logging.info(f"Current invite counts: 12h={invites_12h}/{max_invites_12h}, 24h={invites_24h}/{max_invites_24h}")
        
        if invites_12h >= max_invites_12h or invites_24h >= max_invites_24h:
            logging.warning(f"Invite limits reached: 12h={invites_12h}/{max_invites_12h}, 24h={invites_24h}/{max_invites_24h}")
            db.update_invite_status(invite_id, active=False)
            ACTIVE_INVITES[invite_id] = False
            break
        
        try:
            user_entity = await client.get_entity(user['user_id'])
            logging.info(f"Adding user {user['user_id']} to chat {target_chat['title']}")
            
            if isinstance(chat_entity, Channel):
                await client(InviteToChannelRequest(
                    channel=chat_entity,
                    users=[user_entity]
                ))
            else:
                await client(AddChatUserRequest(
                    chat_id=chat_entity.id,
                    user_id=user_entity,
                    fwd_limit=100
                ))
            
            db.update_invite_progress(invite_id, start_index + i + 1)
            db.add_invite_log(
                account_id=account['id'],
                target_chat_id=target_chat['id'],
                user_id=user['user_id'],
                status="success"
            )
            invite_count += 1
            logging.info(f"Successfully invited user {user['user_id']} ({invite_count} total)")
            
        except (UserPrivacyRestrictedError, FloodWaitError, ChatAdminRequiredError) as e:
            error_count += 1
            error_type = type(e).__name__
            logging.error(f"Error inviting user {user['user_id']}: {error_type} - {str(e)}")
            
            db.add_invite_log(
                account_id=account['id'],
                target_chat_id=target_chat['id'],
                user_id=user['user_id'],
                status="error",
                error_message=str(e)
            )
            
            db.update_invite_progress(invite_id, start_index + i + 1)
            
            if isinstance(e, FloodWaitError):
                logging.warning(f"FloodWaitError detected, pausing invite process")
                db.update_invite_status(invite_id, active=False)
                ACTIVE_INVITES[invite_id] = False
                break
                
        except Exception as e:
            error_count += 1
            logging.error(f"Unexpected error inviting user {user['user_id']}: {type(e).__name__} - {str(e)}")
            
            db.update_invite_progress(invite_id, start_index + i + 1)
            
            db.add_invite_log(
                account_id=account['id'],
                target_chat_id=target_chat['id'],
                user_id=user['user_id'],
                status="error",
                error_message=str(e)
            )
            
            if "authorized" in str(e).lower() or "connection" in str(e).lower():
                logging.warning("Critical error detected, pausing invite process")
                db.update_invite_status(invite_id, active=False)
                ACTIVE_INVITES[invite_id] = False
                break
        
        if invite_id in ACTIVE_INVITES and not ACTIVE_INVITES[invite_id]:
            logging.info(f"Invite {invite_id} stopped during processing")
            break
            
        interval = random.randint(min_interval, max_interval)
        logging.info(f"Waiting {interval} seconds before next invite")
        
        for _ in range(interval):
            if invite_id in ACTIVE_INVITES and not ACTIVE_INVITES[invite_id]:
                logging.info(f"Invite {invite_id} stopped during wait interval")
                break
            await asyncio.sleep(1)
    
    if invite_count > 0 or error_count > 0:
        logging.info(f"Invite process summary: invited={invite_count}, errors={error_count}")
        db.add_invite_summary_log(
            account_id=account['id'],
            target_chat_id=target_chat['id'],
            invited_count=invite_count,
            errors_count=error_count
        )
    
    invite = db.get_invite(invite_id)
    if invite and invite['current_invited'] >= invite['total_users']:
        logging.info(f"All users invited, marking invite as completed")
        db.complete_invite(invite_id)
        if invite_id in ACTIVE_INVITES:
            del ACTIVE_INVITES[invite_id]
    elif invite_id in ACTIVE_INVITES and not ACTIVE_INVITES[invite_id]:
        logging.info(f"Invite {invite_id} marked as stopped at the end of process")
    
    if invite_id in ACTIVE_INVITES:
        del ACTIVE_INVITES[invite_id] 

async def update_inviting_progress(message, invite_id, current, total):
    """Обновление сообщения с прогрессом инвайтинга динамически"""
    invite = db.get_invite(invite_id)
    if not invite:
        return
    
    account = db.get_account(invite['account_id'])
    target_chat = db.get_target_chat(invite['target_chat_id'])
    
    account_name = "Неизвестный аккаунт"
    if account:
        account_name = f"{account['first_name']} {account['last_name']}".strip()
        if not account_name:
            account_name = account['phone']
    
    target_name = "Неизвестный чат"
    if target_chat:
        target_name = target_chat['title']
    
    text = f"🔄 ПРОГРЕСС ИНВАЙТИНГА\n\n"
    text += f"👤 Аккаунт: {account_name}\n"
    text += f"📣 Чат: {target_name}\n\n"
    
    # Расчет процента выполнения
    percent = int((current / total) * 100) if total > 0 else 0
    progress_bar = "▓" * (percent // 5) + "░" * (20 - (percent // 5))
    
    text += f"Прогресс: [{progress_bar}] {percent}%\n"
    text += f"Приглашено {current} из {total} пользователей\n"
    
    kb = InlineKeyboardBuilder()
    kb.button(text="⏸ ПРИОСТАНОВИТЬ", callback_data=f"pause_invite:{invite_id}")
    kb.button(text="🔙 НАЗАД", callback_data="inviting")
    kb.button(text="🔙 ГЛАВНОЕ МЕНЮ", callback_data="main_menu")
    kb.adjust(1)
    
    try:
        await message.edit_text(text, reply_markup=kb.as_markup(), parse_mode="HTML")
    except Exception as e:
        if "message is not modified" not in str(e):
            logging.error(f"Error updating inviting progress: {e}")

# Обновляем функцию start_inviting, чтобы использовать обновление прогресса
async def start_inviting(message, invite_id):
    """Start inviting process"""
    invite = db.get_invite(invite_id)
    if not invite:
        return "❌ Процесс инвайтинга не найден."
    
    account_id = invite['account_id']
    target_chat_id = invite['target_chat_id']
    parsed_file_id = invite['parsed_file_id']
    
    account = db.get_account(account_id)
    target_chat = db.get_target_chat(target_chat_id)
    parsed_file = db.get_parsed_file(parsed_file_id)
    
    if not account or not target_chat or not parsed_file:
        return "❌ Не найдены все необходимые данные для инвайтинга."
    
    client = client_manager.get_client(account['phone'])
    if not client:
        return f"❌ Не удалось подключиться к аккаунту {account['phone']}."
    
    invite_settings = db.get_invite_settings()
    min_interval = invite_settings.get('min_interval_seconds', 30)
    max_interval = invite_settings.get('max_interval_seconds', 60)
    max_invites_12h = invite_settings.get('max_invites_12h', 25)
    max_invites_24h = invite_settings.get('max_invites_24h', 40)
    
    # Получаем пользователей для инвайтинга
    users = db.get_parsed_users(parsed_file_id, limit=1000, offset=invite['current_invited'])
    
    if not users:
        return "✅ Все пользователи уже были приглашены или в файле нет пользователей."
    
    # Обновляем сообщение с прогрессом перед началом
    await update_inviting_progress(message, invite_id, invite['current_invited'], invite['total_users'])
    
    # Устанавливаем флаг активного инвайтинга
    db.update_invite(invite_id, {'active': True})
    ACTIVE_INVITES[invite_id] = True
    
    # Запускаем процесс инвайтинга
    try:
        for user in users:
            if not ACTIVE_INVITES.get(invite_id, False):
                break
                
            # Проверяем лимиты
            invites_12h = db.count_user_invites_period(account_id, hours=12)
            invites_24h = db.count_user_invites_period(account_id, hours=24)
            
            if invites_12h >= max_invites_12h:
                await update_inviting_progress(message, invite_id, invite['current_invited'], invite['total_users'])
                return f"⚠️ Достигнут лимит приглашений за 12 часов ({max_invites_12h})."
                
            if invites_24h >= max_invites_24h:
                await update_inviting_progress(message, invite_id, invite['current_invited'], invite['total_users'])
                return f"⚠️ Достигнут лимит приглашений за 24 часа ({max_invites_24h})."
                
            user_id = user['user_id']
            username = user.get('username', None)
            
            success = False
            error_msg = ""
            
            try:
                if target_chat['is_channel'] or target_chat['is_group']:
                    await client(InviteToChannelRequest(
                        channel=target_chat['chat_id'],
                        users=[user_id if isinstance(user_id, str) else int(user_id)]
                    ))
                else:
                    await client(AddChatUserRequest(
                        chat_id=target_chat['chat_id'],
                        user_id=user_id if isinstance(user_id, str) else int(user_id),
                        fwd_limit=100
                    ))
                success = True
            except UserPrivacyRestrictedError:
                error_msg = "Пользователь запретил добавление в группы"
            except FloodWaitError as e:
                error_msg = f"Flood wait: {e.seconds} seconds"
                # Остановка процесса при флуд-вейте
                db.update_invite(invite_id, {'active': False})
                ACTIVE_INVITES[invite_id] = False
                return f"⚠️ Flood wait: Необходимо подождать {e.seconds} секунд перед продолжением."
            except ChatAdminRequiredError:
                error_msg = "Требуются права администратора"
            except Exception as e:
                error_msg = f"Ошибка: {str(e)}"
            
            # Обновляем базу данных
            current_invited = invite['current_invited'] + 1
            db.update_invite(invite_id, {'current_invited': current_invited})
            
            if success:
                db.add_invite_log(invite_id, user_id, success=True)
            else:
                db.add_invite_log(invite_id, user_id, success=False, error=error_msg)
            
            # Обновляем сообщение с прогрессом каждые 5 пользователей
            if current_invited % 5 == 0 or current_invited == invite['total_users']:
                await update_inviting_progress(message, invite_id, current_invited, invite['total_users'])
            
            # Случайная пауза между приглашениями
            await asyncio.sleep(random.randint(min_interval, max_interval))
            
            # Проверяем, не остановлен ли процесс
            invite_check = db.get_invite(invite_id)
            if not invite_check['active']:
                break
        
        # Финальное обновление прогресса
        invite = db.get_invite(invite_id)
        await update_inviting_progress(message, invite_id, invite['current_invited'], invite['total_users'])
        
        if invite['current_invited'] >= invite['total_users']:
            return "✅ Инвайтинг завершен! Все пользователи были приглашены."
        else:
            return f"✅ Инвайтинг приостановлен. Приглашено {invite['current_invited']} из {invite['total_users']} пользователей."
    
    except Exception as e:
        logging.error(f"Error in inviting process: {e}")
        return f"❌ Ошибка в процессе инвайтинга: {str(e)}"
    finally:
        # Убеждаемся, что инвайтинг отмечен как неактивный
        if invite_id in ACTIVE_INVITES:
            ACTIVE_INVITES[invite_id] = False 