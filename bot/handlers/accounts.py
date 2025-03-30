import os
import re
import asyncio
import logging
from datetime import datetime
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from database import db
from telegram_client import client_manager
from config import SESSIONS_DIR
from bot.keyboards import (
    accounts_menu_keyboard, 
    account_settings_keyboard, 
    back_button,
    back_to_menu_button,
    main_menu_keyboard,
    skip_button,
    proxy_settings_keyboard
)

logger = logging.getLogger(__name__)

router = Router()

os.makedirs(SESSIONS_DIR, exist_ok=True)

class AccountStates(StatesGroup):
    waiting_for_session = State()
    waiting_for_first_name = State()
    waiting_for_last_name = State()
    waiting_for_status = State()
    waiting_for_username = State()
    waiting_for_proxy = State()


@router.callback_query(F.data == "accounts")
async def callback_accounts(callback: CallbackQuery, state: FSMContext):
    # Сохраняем текущее меню в состоянии
    await state.update_data(previous_menu='accounts')
    await state.clear()
    
    accounts = db.get_accounts()
    
    if not accounts:
        try:
            await callback.message.edit_text(
                "<b>👤 АККАУНТЫ</b>\n\n"
                "<b>У вас пока нет добавленных аккаунтов.</b>\n"
                "<b>Нажмите кнопку ниже, чтобы добавить аккаунт.</b>",
                reply_markup=accounts_menu_keyboard(),
                parse_mode="HTML"
            )
        except Exception as e:
            if "message is not modified" not in str(e):
                raise
    else:
        text = "<b>👤 АККАУНТЫ</b>\n\n"
        text += "<b>Ваши аккаунты:</b>\n\n"
        
        for acc in accounts:
            status_emoji = "✅" if acc['status'] == 'active' else "❌"
            added_date = datetime.fromtimestamp(acc['added_date']).strftime('%d.%m.%y')
            last_used = datetime.fromtimestamp(acc['last_used']).strftime('%d.%m.%y')
            
            name = f"{acc['first_name']} {acc['last_name']}".strip()
            if not name:
                name = f"Аккаунт {acc['phone']}"
            
            text += f"<b>{name} | рег {added_date}</b>\n"
            text += f"<b>{last_used} (в работе \"от\")</b>\n"
            text += f"<b>{acc['invites_sent']} ✅ | {acc['invites_failed']} ❌</b>\n"
            text += f"<b>Статус: {acc['status']}</b>\n\n"
        
        try:
            await callback.message.edit_text(
                text,
                reply_markup=accounts_menu_keyboard(accounts),
                parse_mode="HTML"
            )
        except Exception as e:
            if "message is not modified" not in str(e):
                raise
    
    await callback.answer()


@router.callback_query(F.data == "add_accounts")
async def callback_add_accounts(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AccountStates.waiting_for_session)
    await callback.message.edit_text(
        "<b>📤 Пришлите .session файл для добавления аккаунта.\n\n"
        "Вы можете отправить один или несколько файлов сразу.</b>",
        reply_markup=back_button()
    )
    await callback.answer()


@router.message(AccountStates.waiting_for_session, F.document)
async def handle_session_file(message: Message, state: FSMContext):
    document = message.document
    if not document.file_name.endswith('.session'):
        await message.answer(
            "<b>❌ Файл должен иметь расширение .session\n"
            "Пожалуйста, пришлите правильный файл.</b>",
            reply_markup=back_button()
        )
        return
    
    os.makedirs(SESSIONS_DIR, exist_ok=True)
    
    file = await message.bot.get_file(document.file_id)
    file_name = document.file_name
    file_path = os.path.join(SESSIONS_DIR, file_name)
    
    await message.bot.download_file(file.file_path, file_path)
    
    status_msg = await message.answer(f"<b>⏳ Проверяю аккаунт {file_name}...</b>")
    
    success = await client_manager.add_client(file_name)
    
    if success:
        kb = InlineKeyboardBuilder()
        kb.button(text="✅ Да", callback_data=f"use_proxy:{file_name}")
        kb.button(text="❌ Нет", callback_data=f"no_proxy:{file_name}")
        kb.adjust(2)
        kb.row()
        kb.button(text="🔙 Назад", callback_data="add_accounts")
        
        await status_msg.edit_text(
            f"<b>✅ Аккаунт {file_name} успешно добавлен!\n\n"
            f"Использовать прокси при работе с аккаунтом?</b>",
            reply_markup=kb.as_markup()
        )
    else:
        await status_msg.edit_text(f"<b>❌ Не удалось добавить аккаунт {file_name}.</b>")
        try:
            os.remove(file_path)
        except:
            pass
        
        await message.answer(
            "<b>Вы можете отправить еще один файл сессии или вернуться в меню.</b>",
            reply_markup=back_to_menu_button()
        )


@router.callback_query(F.data.startswith("use_proxy:"))
async def callback_use_proxy(callback: CallbackQuery, state: FSMContext):
    """Обработчик для кнопки 'Да' при выборе использования прокси"""
    file_name = callback.data.split(':')[1]
    
    account = None
    for acc in db.get_accounts():
        if acc['session_file'] == os.path.splitext(file_name)[0]:
            account = acc
            break
    
    if not account:
        await callback.message.edit_text(
            "<b>❌ Аккаунт не найден.</b>",
            reply_markup=back_button()
        )
        await callback.answer()
        return
    
    await state.update_data(account_id=account['id'])
    await state.set_state(AccountStates.waiting_for_proxy)
    
    await callback.message.edit_text(
        "<b>🔒 Введите строку прокси в формате:\n"
        "login:password:ip:port\n"
        "или\n"
        "login:password@ip:port</b>",
        reply_markup=back_button()
    )
    await callback.answer()


@router.callback_query(F.data.startswith("no_proxy:"))
async def callback_no_proxy(callback: CallbackQuery, state: FSMContext):
    """Обработчик для кнопки 'Нет' при выборе использования прокси"""
    await callback.message.edit_text(
        "<b>✅ Аккаунт будет использоваться без прокси.\n"
        "Вы можете отправить еще один файл сессии или вернуться в меню.</b>",
        reply_markup=back_to_menu_button()
    )
    await callback.answer()


@router.message(AccountStates.waiting_for_proxy)
async def handle_proxy(message: Message, state: FSMContext):
    """Обработчик для ввода строки прокси"""
    data = await state.get_data()
    account_id = data.get('account_id')
    
    if not account_id:
        await message.answer(
            "<b>❌ Ошибка: ID аккаунта не найден.</b>",
            reply_markup=main_menu_keyboard()
        )
        await state.clear()
        return
    
    proxy_str = message.text.strip()
    
    valid_format = False
    if '@' in proxy_str:
        pattern = r'^[^:]+:[^@]+@[^:]+:\d+$'
        valid_format = bool(re.match(pattern, proxy_str))
    else:
        pattern = r'^[^:]+:[^:]+:[^:]+:\d+$'
        valid_format = bool(re.match(pattern, proxy_str))
    
    if not valid_format:
        await message.answer(
            "<b>❌ Неверный формат прокси.\n"
            "Пожалуйста, введите в формате login:password:ip:port или login:password@ip:port</b>",
            reply_markup=back_button()
        )
        return
    
    account = db.get_account(account_id)
    phone = account['phone']
    
    success, msg = await client_manager.update_client_proxy(phone, proxy_str)
    
    if success:
        await message.answer(
            f"<b>✅ Прокси успешно установлен для аккаунта {phone}.\n"
            "Вы можете отправить еще один файл сессии или вернуться в меню.</b>",
            reply_markup=back_to_menu_button()
        )
    else:
        await message.answer(
            f"<b>❌ Ошибка при установке прокси: {msg}\n"
            "Возможно, прокси недоступен или имеет неверный формат.</b>",
            reply_markup=back_to_menu_button()
        )
    
    await state.clear()


@router.callback_query(F.data.startswith("account:"))
async def callback_account_details(callback: CallbackQuery, state: FSMContext):
    account_id = int(callback.data.split(':')[1])
    account = db.get_account(account_id)
    
    db._check_and_update_schema()
    
    if not account:
        await callback.message.edit_text(
            "<b>❌ Аккаунт не найден.</b>",
            reply_markup=accounts_menu_keyboard()
        )
        await callback.answer()
        return
    
    status_emoji = "✅" if account['status'] == 'active' else "❌"
    name = f"{account['first_name']} {account['last_name']}".strip()
    if not name:
        name = f"Аккаунт {account['phone']}"
    
    added_date = datetime.fromtimestamp(account['added_date']).strftime('%d.%m.%y')
    last_used = datetime.fromtimestamp(account['last_used']).strftime('%d.%m.%y')
    
    text = f"<b>📱 Аккаунт: {name}\n\n"
    text += f"Телефон: {account['phone']}\n"
    text += f"Имя: {account['first_name'] or 'Не задано'}\n"
    text += f"Фамилия: {account['last_name'] or 'Не задано'}\n"
    text += f"Юзернейм: @{account['username'] or 'Не задано'}\n"
    text += f"Дата добавления: {added_date}\n"
    text += f"Последняя активность: {last_used}\n"
    text += f"Статус: {status_emoji} {account['status']}\n"
    text += f"Приглашено успешно: {account['invites_sent']}\n"
    text += f"Неудачных приглашений: {account['invites_failed']}\n"
    
    if account.get('about'):
        text += f"\nОписание (био): {account['about']}\n"
    
    if account.get('proxy'):
        text += f"\nИспользуется прокси: ✅\n"
    else:
        text += f"\nИспользуется прокси: ❌\n"
    text += "</b>"
    
    await callback.message.edit_text(
        text,
        reply_markup=account_settings_keyboard(account_id)
    )
    await callback.answer()


@router.callback_query(F.data.startswith("edit_name:"))
async def callback_edit_name(callback: CallbackQuery, state: FSMContext):
    account_id = int(callback.data.split(':')[1])
    await state.update_data(account_id=account_id)
    await state.set_state(AccountStates.waiting_for_first_name)
    
    kb = InlineKeyboardBuilder()
    kb.button(text="🔙 Назад", callback_data=f"back_to_account:{account_id}")
    
    await callback.message.edit_text(
        "<b>✏️ Введите новое имя для аккаунта:</b>",
        reply_markup=kb.as_markup()
    )
    await callback.answer()


@router.callback_query(F.data.startswith("back_to_account:"))
async def callback_back_to_account(callback: CallbackQuery, state: FSMContext):
    """Handler for back button that returns to account details"""
    account_id = int(callback.data.split(':')[1])
    account = db.get_account(account_id)
    
    if not account:
        await callback.message.edit_text(
            "<b>❌ Аккаунт не найден.</b>",
            reply_markup=accounts_menu_keyboard()
        )
    else:
        await show_account_details(callback.message, account)
    
    await state.clear()
    await callback.answer()


@router.message(AccountStates.waiting_for_first_name)
async def handle_first_name(message: Message, state: FSMContext):
    data = await state.get_data()
    account_id = data.get('account_id')
    
    if not account_id:
        await message.answer(
            "<b>❌ Ошибка: ID аккаунта не найден.</b>",
            reply_markup=main_menu_keyboard()
        )
        await state.clear()
        return
    
    first_name = message.text.strip()
    await state.update_data(first_name=first_name)
    await state.set_state(AccountStates.waiting_for_last_name)
    
    await message.answer(
        "<b>✏️ Теперь введите фамилию (или отправьте пустое сообщение, если не нужна фамилия):</b>",
        reply_markup=skip_button()
    )


@router.callback_query(F.data == "skip", AccountStates.waiting_for_last_name)
async def skip_last_name(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    account_id = data.get('account_id')
    first_name = data.get('first_name')
    
    if not account_id:
        await callback.message.edit_text(
            "<b>❌ Ошибка: ID аккаунта не найден.</b>",
            reply_markup=main_menu_keyboard()
        )
        await state.clear()
        await callback.answer()
        return
    
    account = db.get_account(account_id)
    if not account:
        await callback.message.edit_text(
            "<b>❌ Аккаунт не найден.</b>",
            reply_markup=main_menu_keyboard()
        )
        await state.clear()
        await callback.answer()
        return
    
    status_msg = await callback.message.edit_text("<b>⏳ Обновляю информацию аккаунта...</b>")
    
    phone = account['phone']
    
    try:
        if phone not in client_manager.clients:
            client_loaded = await client_manager.add_client(account['session_file'])
            if not client_loaded:
                await status_msg.edit_text("<b>❌ Не удалось загрузить клиент для аккаунта.</b>")
                await callback.answer("Ошибка: клиент не загружен")
                return
        
        success = await client_manager.update_profile(phone, first_name=first_name, last_name="")
        
        if success:
            db.update_account_info(account_id, first_name=first_name, last_name="")
            await status_msg.edit_text("<b>✅ Информация аккаунта успешно обновлена!</b>")
        else:
            await status_msg.edit_text("<b>❌ Не удалось обновить информацию аккаунта.</b>")
        
        updated_account = db.get_account(account_id)
        name = f"{updated_account['first_name']} {updated_account['last_name']}".strip()
        if not name:
            name = f"Аккаунт {updated_account['phone']}"
        
        added_date = datetime.fromtimestamp(updated_account['added_date']).strftime('%d.%m.%y')
        last_used = datetime.fromtimestamp(updated_account['last_used']).strftime('%d.%m.%y')
        
        text = f"<b>📱 Аккаунт: {name}\n\n"
        text += f"Телефон: {updated_account['phone']}\n"
        text += f"Имя: {updated_account['first_name'] or 'Не задано'}\n"
        text += f"Фамилия: {updated_account['last_name'] or 'Не задано'}\n"
        text += f"Юзернейм: {updated_account['username'] or 'Не задано'}\n"
        text += f"Дата добавления: {added_date}\n"
        text += f"Последняя активность: {last_used}\n"
        text += f"Статус: {updated_account['status']}\n"
        about_text = updated_account.get('about') or 'Не задано'
        text += f"Описание: {about_text}\n"
        text += f"Приглашено успешно: {updated_account['invites_sent']}\n"
        text += f"Неудачных приглашений: {updated_account['invites_failed']}\n"
        text += "</b>"
        
        await callback.message.edit_text(
            text,
            reply_markup=account_settings_keyboard(account_id)
        )
        await state.clear()
        await callback.answer()
    except Exception as e:
        print(f"Error in skip_last_name: {e}")
        await status_msg.edit_text(f"<b>❌ Произошла ошибка: {str(e)}</b>")
        await callback.answer("Ошибка при обновлении")
        await state.clear()


@router.message(AccountStates.waiting_for_last_name)
async def handle_last_name(message: Message, state: FSMContext):
    data = await state.get_data()
    account_id = data.get('account_id')
    first_name = data.get('first_name')
    
    if not account_id:
        await message.answer(
            "<b>❌ Ошибка: ID аккаунта не найден.</b>",
            reply_markup=main_menu_keyboard()
        )
        await state.clear()
        return
    
    last_name = message.text.strip()
    
    account = db.get_account(account_id)
    if not account:
        await message.answer(
            "<b>❌ Аккаунт не найден.</b>",
            reply_markup=main_menu_keyboard()
        )
        await state.clear()
        return
    
    status_msg = await message.answer("<b>⏳ Обновляю информацию аккаунта...</b>")
    
    phone = account['phone']
    success = await client_manager.update_profile(phone, first_name=first_name, last_name=last_name)
    
    if success:
        db.update_account_info(account_id, first_name=first_name, last_name=last_name)
        
        await status_msg.edit_text("<b>✅ Информация аккаунта успешно обновлена!</b>")
    else:
        await status_msg.edit_text("<b>❌ Не удалось обновить информацию аккаунта.</b>")
    
    updated_account = db.get_account(account_id)
    name = f"{updated_account['first_name']} {updated_account['last_name']}".strip()
    if not name:
        name = f"Аккаунт {updated_account['phone']}"
    
    added_date = datetime.fromtimestamp(updated_account['added_date']).strftime('%d.%m.%y')
    last_used = datetime.fromtimestamp(updated_account['last_used']).strftime('%d.%m.%y')
    
    text = f"<b>📱 Аккаунт: {name}\n\n"
    text += f"Телефон: {updated_account['phone']}\n"
    text += f"Имя: {updated_account['first_name'] or 'Не задано'}\n"
    text += f"Фамилия: {updated_account['last_name'] or 'Не задано'}\n"
    text += f"Юзернейм: {updated_account['username'] or 'Не задано'}\n"
    text += f"Дата добавления: {added_date}\n"
    text += f"Последняя активность: {last_used}\n"
    text += f"Статус: {updated_account['status']}\n"
    about_text = updated_account['about'] if 'about' in updated_account.keys() else 'Не задано'
    text += f"Описание: {about_text}\n"
    text += f"Приглашено успешно: {updated_account['invites_sent']}\n"
    text += f"Неудачных приглашений: {updated_account['invites_failed']}\n"
    text += "</b>"
    
    await message.answer(
        text,
        reply_markup=account_settings_keyboard(account_id)
    )
    await state.clear()


@router.callback_query(F.data.startswith("set_status:"))
async def callback_set_status(callback: CallbackQuery, state: FSMContext):
    account_id = int(callback.data.split(':')[1])
    await state.update_data(account_id=account_id)
    await state.set_state(AccountStates.waiting_for_status)
    
    kb = InlineKeyboardBuilder()
    kb.button(text="🔙 Назад", callback_data=f"back_to_account:{account_id}")
    
    await callback.message.edit_text(
        "<b>💬 Введите новое описание (био) для аккаунта:</b>",
        reply_markup=kb.as_markup()
    )
    await callback.answer()


@router.message(AccountStates.waiting_for_status)
async def handle_status(message: Message, state: FSMContext):
    data = await state.get_data()
    account_id = data.get('account_id')
    
    if not account_id:
        await message.answer(
            "<b>❌ Ошибка: ID аккаунта не найден.</b>",
            reply_markup=main_menu_keyboard()
        )
        await state.clear()
        return
    
    status_text = message.text.strip()
    
    account = db.get_account(account_id)
    if not account:
        await message.answer(
            "<b>❌ Аккаунт не найден.</b>",
            reply_markup=main_menu_keyboard()
        )
        await state.clear()
        return
    
    phone = account['phone']
    success = await client_manager.update_profile(phone, about=status_text)
    
    if success:
        db.update_account_about(account_id, status_text)
        await message.answer("<b>✅ Описание аккаунта обновлено!</b>")
    else:
        await message.answer("<b>❌ Не удалось обновить описание аккаунта.</b>")
    
    account_status = await client_manager.check_client_status(phone)
    if account_status['status'] != 'active':
        db.update_account_status(account_id, account_status['status'], account_status['details'])
    
    updated_account = db.get_account(account_id)
    name = f"{updated_account['first_name']} {updated_account['last_name']}".strip()
    if not name:
        name = f"Аккаунт {updated_account['phone']}"
    
    added_date = datetime.fromtimestamp(updated_account['added_date']).strftime('%d.%m.%y')
    last_used = datetime.fromtimestamp(updated_account['last_used']).strftime('%d.%m.%y')
    
    text = f"<b>📱 Аккаунт: {name}\n\n"
    text += f"Телефон: {updated_account['phone']}\n"
    text += f"Имя: {updated_account['first_name'] or 'Не задано'}\n"
    text += f"Фамилия: {updated_account['last_name'] or 'Не задано'}\n"
    text += f"Юзернейм: {updated_account['username'] or 'Не задано'}\n"
    text += f"Дата добавления: {added_date}\n"
    text += f"Последняя активность: {last_used}\n"
    text += f"Статус: {updated_account['status']}\n"
    about_text = updated_account['about'] if 'about' in updated_account.keys() else 'Не задано'
    text += f"Описание: {about_text}\n"
    text += f"Приглашено успешно: {updated_account['invites_sent']}\n"
    text += f"Неудачных приглашений: {updated_account['invites_failed']}\n"
    text += "</b>"
    
    await message.answer(
        text,
        reply_markup=account_settings_keyboard(account_id)
    )
    await state.clear()


@router.callback_query(F.data.startswith("delete_account:"))
async def callback_delete_account(callback: CallbackQuery, state: FSMContext):
    account_id = int(callback.data.split(':')[1])
    
    account = db.get_account(account_id)
    if not account:
        await callback.message.edit_text(
            "<b>❌ Аккаунт не найден.</b>",
            reply_markup=accounts_menu_keyboard()
        )
        await callback.answer()
        return
    
    name = f"{account['first_name']} {account['last_name']}".strip()
    if not name:
        name = f"Аккаунт {account['phone']}"
    
    db.delete_account(account_id)
    
    session_file = account['session_file']
    session_path = os.path.join(SESSIONS_DIR, session_file)
    try:
        if os.path.exists(session_path):
            os.remove(session_path)
        if os.path.exists(f"{session_path}.session"):
            os.remove(f"{session_path}.session")
    except Exception as e:
        pass
    
    await callback.message.edit_text(
        f"<b>✅ Аккаунт {name} успешно удален.</b>",
        reply_markup=accounts_menu_keyboard()
    )
    await callback.answer()


@router.callback_query(F.data == "main_menu")
async def callback_to_main_menu(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    
    try:
        await callback.message.edit_text(
            "<b>📋 Главное меню:</b>",
            reply_markup=main_menu_keyboard()
        )
    except Exception as e:
        if "message is not modified" not in str(e):
            raise
    
    await callback.answer()


@router.callback_query(F.data == "cancel")
async def callback_cancel_in_accounts(callback: CallbackQuery, state: FSMContext):
    current_state = await state.get_state()
    
    if current_state in [AccountStates.waiting_for_session.state]:
        await state.clear()
        accounts = db.get_accounts()
        await show_accounts_list(callback.message, accounts)
    elif current_state in [AccountStates.waiting_for_first_name.state, AccountStates.waiting_for_status.state, 
                          AccountStates.waiting_for_last_name.state]:
        data = await state.get_data()
        account_id = data.get('account_id')
        await state.clear()
        
        if account_id:
            account = db.get_account(account_id)
            if account:
                await show_account_details(callback.message, account)
            else:
                await callback.message.edit_text(
                    "<b>❌ Аккаунт не найден.</b>",
                    reply_markup=accounts_menu_keyboard()
                )
        else:
            accounts = db.get_accounts()
            await show_accounts_list(callback.message, accounts)
    else:
        await state.clear()
        accounts = db.get_accounts()
        await show_accounts_list(callback.message, accounts)
    
    await callback.answer()


async def show_accounts_list(message, accounts):
    """Helper function to show accounts list"""
    if not accounts:
        try:
            await message.edit_text(
                "<b>📱 Аккаунты\n\n"
                "У вас пока нет добавленных аккаунтов.\n"
                "Нажмите кнопку ниже, чтобы добавить аккаунты.</b>",
                reply_markup=accounts_menu_keyboard()
            )
        except Exception as e:
            if "message is not modified" not in str(e):
                raise
    else:
        text = "<b>📱 Аккаунты\n\n"
        for acc in accounts:
            status_emoji = "✅" if acc['status'] == 'active' else "❌"
            added_date = datetime.fromtimestamp(acc['added_date']).strftime('%d.%m.%y')
            last_used = datetime.fromtimestamp(acc['last_used']).strftime('%d.%m.%y')
            
            name = f"{acc['first_name']} {acc['last_name']}".strip()
            if not name:
                name = f"Аккаунт {acc['phone']}"
            
            text += f"{name} | рег {added_date}\n"
            text += f"{last_used} (в работе \"от\")\n"
            text += f"{acc['invites_sent']} ✅ | {acc['invites_failed']} ❌\n"
            text += f"Статус: {acc['status']}\n\n"
        text += "</b>"
        
        try:
            await message.edit_text(
                text,
                reply_markup=accounts_menu_keyboard(accounts)
            )
        except Exception as e:
            if "message is not modified" not in str(e):
                raise


async def show_account_details(message, account):
    """Helper function to display account details"""
    status_emoji = "✅" if account['status'] == 'active' else "❌"
    name = f"{account['first_name']} {account['last_name']}".strip()
    if not name:
        name = f"Аккаунт {account['phone']}"
    
    added_date = datetime.fromtimestamp(account['added_date']).strftime('%d.%m.%y')
    last_used = datetime.fromtimestamp(account['last_used']).strftime('%d.%m.%y')
    
    text = f"<b>📱 Аккаунт: {name}\n\n"
    text += f"Телефон: {account['phone']}\n"
    text += f"Имя: {account['first_name'] or 'Не задано'}\n"
    text += f"Фамилия: {account['last_name'] or 'Не задано'}\n"
    text += f"Юзернейм: @{account['username'] or 'Не задано'}\n"
    text += f"Дата добавления: {added_date}\n"
    text += f"Последняя активность: {last_used}\n"
    text += f"Статус: {status_emoji} {account['status']}\n"
    text += f"Приглашено успешно: {account['invites_sent']}\n"
    text += f"Неудачных приглашений: {account['invites_failed']}\n"
    
    if account.get('about'):
        text += f"\nОписание (био): {account['about']}\n"
    
    if account.get('proxy'):
        text += f"\nИспользуется прокси: ✅\n"
    else:
        text += f"\nИспользуется прокси: ❌\n"
    
    text += "</b>"
    
    await message.edit_text(
        text,
        reply_markup=account_settings_keyboard(account['id'])
    )


@router.callback_query(F.data.startswith("edit_username:"))
async def callback_edit_username(callback: CallbackQuery, state: FSMContext):
    account_id = int(callback.data.split(':')[1])
    await state.update_data(account_id=account_id)
    await state.set_state(AccountStates.waiting_for_username)
    
    kb = InlineKeyboardBuilder()
    kb.button(text="🔙 Назад", callback_data=f"back_to_account:{account_id}")
    
    await callback.message.edit_text(
        "<b>🔤 Введите новый юзернейм для аккаунта (без символа @):\n\n"
        "❗️ Юзернейм должен быть от 5 до 32 символов и может содержать только латинские буквы, цифры и знак подчеркивания.\n"
        "❗️ Юзернейм может быть занят другим пользователем, в этом случае изменение не произойдет.</b>",
        reply_markup=kb.as_markup()
    )
    await callback.answer()


@router.message(AccountStates.waiting_for_username)
async def handle_username(message: Message, state: FSMContext):
    data = await state.get_data()
    account_id = data.get('account_id')
    
    if not account_id:
        await message.answer(
            "<b>❌ Ошибка: ID аккаунта не найден.</b>",
            reply_markup=main_menu_keyboard()
        )
        await state.clear()
        return
    
    username = message.text.strip()
    
    if not username:
        username = None
    elif not re.match(r'^[a-zA-Z0-9_]{5,32}$', username):
        await message.answer(
            "<b>❌ Некорректный формат юзернейма. Юзернейм должен быть от 5 до 32 символов и может содержать только латинские буквы, цифры и знак подчеркивания.</b>",
            reply_markup=InlineKeyboardBuilder().button(
                text="🔙 Назад к настройкам", callback_data=f"account:{account_id}"
            ).as_markup()
        )
        await state.clear()
        return
    
    account = db.get_account(account_id)
    if not account:
        await message.answer(
            "<b>❌ Аккаунт не найден.</b>",
            reply_markup=main_menu_keyboard()
        )
        await state.clear()
        return
    
    status_msg = await message.answer("<b>⏳ Обновляю юзернейм аккаунта...</b>")
    
    phone = account['phone']
    try:
        success = await client_manager.update_profile(phone, username=username)
        
        if success:
            await asyncio.sleep(1)
            
            updated_account = db.get_account(account_id)
            
            me = await client_manager.clients[phone]['client'].get_me()
            actual_username = me.username
            
            if username == actual_username or (username is None and actual_username is None):
                await status_msg.edit_text("<b>✅ Юзернейм аккаунта успешно обновлен на @{actual_username or 'отсутствует'}!</b>")
            else:
                await status_msg.edit_text(
                    "<b>⚠️ Обновление выполнено, но юзернейм не изменился: @{actual_username or 'отсутствует'}. "
                    "Возможно, этот юзернейм уже занят или не соответствует требованиям Telegram.</b>"
                )
        else:
            await status_msg.edit_text("<b>❌ Не удалось обновить юзернейм аккаунта. Возможно, он уже занят другим пользователем.</b>")
        
        await asyncio.sleep(1)
        updated_account = db.get_account(account_id)
        
        await message.answer(
            "<b>Информация об аккаунте:</b>",
            reply_markup=account_settings_keyboard(account_id)
        )
        await show_account_details(message, updated_account)
        
    except Exception as e:
        await status_msg.edit_text("<b>❌ Ошибка при обновлении юзернейма: {str(e)}</b>")
    
    await state.clear()


@router.callback_query(F.data.startswith("proxy_settings:"))
async def callback_proxy_settings(callback: CallbackQuery, state: FSMContext):
    """Обработчик кнопки настройки прокси"""
    account_id = int(callback.data.split(':')[1])
    account = db.get_account(account_id)
    
    if not account:
        await callback.message.edit_text(
            "<b>❌ Аккаунт не найден.</b>",
            reply_markup=accounts_menu_keyboard()
        )
        await callback.answer()
        return
    
    proxy_status = "✅ Установлен" if account.get('proxy') else "❌ Не используется"
    proxy_value = account.get('proxy') or "Не настроен"
    
    await callback.message.edit_text(
        f"<b>🔐 Настройка прокси для аккаунта\n\n"
        f"Текущий статус: {proxy_status}\n"
        f"Текущее значение: {proxy_value}\n\n"
        f"Выберите действие:</b>",
        reply_markup=proxy_settings_keyboard(account_id)
    )
    await callback.answer()


@router.callback_query(F.data.startswith("add_proxy:"))
async def callback_add_proxy(callback: CallbackQuery, state: FSMContext):
    """Обработчик кнопки добавления/изменения прокси"""
    account_id = int(callback.data.split(':')[1])
    account = db.get_account(account_id)
    
    if not account:
        await callback.message.edit_text(
            "<b>❌ Аккаунт не найден.</b>",
            reply_markup=accounts_menu_keyboard()
        )
        await callback.answer()
        return
    
    await state.update_data(account_id=account_id)
    await state.set_state(AccountStates.waiting_for_proxy)
    
    await callback.message.edit_text(
        "<b>🔒 Введите строку прокси в формате:\n"
        "login:password:ip:port\n"
        "или\n"
        "login:password@ip:port</b>",
        reply_markup=back_button(f"proxy_settings:{account_id}")
    )
    await callback.answer()


@router.callback_query(F.data.startswith("remove_proxy:"))
async def callback_remove_proxy(callback: CallbackQuery, state: FSMContext):
    """Обработчик кнопки удаления прокси"""
    account_id = int(callback.data.split(':')[1])
    account = db.get_account(account_id)
    
    if not account:
        await callback.message.edit_text(
            "<b>❌ Аккаунт не найден.</b>",
            reply_markup=accounts_menu_keyboard()
        )
        await callback.answer()
        return
    
    if not account.get('proxy'):
        await callback.message.edit_text(
            "<b>⚠️ Прокси и так не используется для этого аккаунта.</b>",
            reply_markup=proxy_settings_keyboard(account_id)
        )
        await callback.answer()
        return
    
    phone = account['phone']
    success, msg = await client_manager.remove_client_proxy(phone)
    
    if success:
        await callback.message.edit_text(
            "<b>✅ Прокси успешно удален для аккаунта.\n"
            "Теперь аккаунт будет работать без прокси.</b>",
            reply_markup=proxy_settings_keyboard(account_id)
        )
    else:
        await callback.message.edit_text(
            f"<b>❌ Ошибка при удалении прокси: {msg}</b>",
            reply_markup=proxy_settings_keyboard(account_id)
        )
    
    await callback.answer() 