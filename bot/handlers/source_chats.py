import os
import re
import logging
from datetime import datetime
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from database import db
from telegram_client import client_manager
from inviter import inviter
from bot.keyboards import (
    source_chats_keyboard,
    source_chat_actions_keyboard,
    choose_account_keyboard,
    back_button,
    yes_no_keyboard,
    main_menu_keyboard,
)
from bot.handlers.parsing import ParsingStates

router = Router()


class SourceChatStates(StatesGroup):
    waiting_for_chat_link = State()
    waiting_for_account_selection = State()
    waiting_for_parse_type = State()


@router.callback_query(F.data == "source_chats")
async def callback_source_chats(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    chats = db.get_source_chats()

    if not chats:
        try:
            await callback.message.edit_text(
                "<b>🔍 Чаты для парсинга\n\n"
                "У вас пока нет добавленных чатов.\n"
                "Нажмите кнопку ниже, чтобы добавить чат.</b>",
                reply_markup=source_chats_keyboard(),
            )
        except Exception as e:
            if "message is not modified" not in str(e):
                raise
    else:
        text = "<b>🔍 Чаты для парсинга\n\n"
        for chat in chats:
            username = f"@{chat['username']}" if chat["username"] else "Без юзернейма"
            chat_id = f"ID: {chat['chat_id']}"
            link = f"<a href='{chat['link']}'>Ссылка</a>" if chat["link"] else "Без ссылки"
            added_date = datetime.fromtimestamp(chat["added_date"]).strftime("%d.%m.%y")
            members = f"{chat['parsed_members']}/{chat['total_members']} пользователей"

            text += f"{chat['title']} | {username} | {chat_id}\n"
            text += f"{link} | {added_date} | {members}\n\n"
        text += "</b>"

        try:
            await callback.message.edit_text(
                text, reply_markup=source_chats_keyboard(chats)
            )
        except Exception as e:
            if "message is not modified" not in str(e):
                raise

    await callback.answer()


@router.callback_query(F.data == "add_source_chat")
async def callback_add_source_chat(callback: CallbackQuery, state: FSMContext):
    accounts = db.get_accounts()
    if not accounts:
        await callback.message.edit_text(
            "<b>❌ Для добавления чата необходимо сначала добавить хотя бы один аккаунт.</b>",
            reply_markup=main_menu_keyboard(),
        )
        await callback.answer()
        return

    await state.set_state(SourceChatStates.waiting_for_account_selection)
    await callback.message.edit_text(
        "<b>👤 Выберите аккаунт, с которого будет добавлен чат:</b>",
        reply_markup=choose_account_keyboard(accounts),
    )
    await callback.answer()


@router.callback_query(
    SourceChatStates.waiting_for_account_selection, F.data.startswith("select_account:")
)
async def callback_select_account_for_chat(callback: CallbackQuery, state: FSMContext):
    account_id = int(callback.data.split(":")[1])
    account = db.get_account(account_id)

    if not account:
        await callback.message.edit_text("<b>❌ Аккаунт не найден.</b>", reply_markup=main_menu_keyboard())
        await callback.answer()
        return

    await state.update_data(account_id=account_id, account_phone=account["phone"])
    await state.set_state(SourceChatStates.waiting_for_chat_link)

    await callback.message.edit_text(
        "<b>🔗 Введите ссылку на чат или его юзернейм (например, @username или https://t.me/username):</b>",
        reply_markup=back_button(),
    )
    await callback.answer()


@router.message(SourceChatStates.waiting_for_chat_link)
async def handle_chat_link(message: Message, state: FSMContext):
    data = await state.get_data()
    account_phone = data.get("account_phone")
    account_id = data.get("account_id")

    if not account_phone:
        await message.answer(
            "<b>❌ Ошибка: Телефон аккаунта не найден.</b>", reply_markup=main_menu_keyboard()
        )
        await state.clear()
        return

    chat_link = message.text.strip()

    if chat_link.startswith("@"):
        chat_link = chat_link[1:]
    elif "t.me/" in chat_link:
        chat_link = chat_link.split("t.me/", 1)[1]

    status_msg = await message.answer(f"<b>⏳ Получаю информацию о чате {chat_link}...</b>")

    join_success, join_error = await client_manager.join_chat(account_phone, chat_link)
    if not join_success:
        await status_msg.edit_text(f"<b>❌ Не удалось присоединиться к чату: {join_error}</b>")
        return

    chat_info, error = await client_manager.get_chat_info(account_phone, chat_link)

    if not chat_info:
        await status_msg.edit_text(f"<b>❌ Не удалось получить информацию о чате: {error}</b>")
        return

    chat_db_id = db.add_source_chat(
        chat_id=chat_info["id"],
        username=chat_info["username"],
        title=chat_info["title"],
        link=chat_info["link"],
        account_id=account_id,
    )

    db.update_source_chat_stats(chat_db_id, total_members=chat_info["participants_count"])

    await status_msg.edit_text(
        f"<b>✅ Чат {chat_info['title']} успешно добавлен!\n\n"
        f"ID: {chat_info['id']}\n"
        f"Юзернейм: {'@' + chat_info['username'] if chat_info['username'] else 'Нет'}\n"
        f"Участников: {chat_info['participants_count']}</b>"
    )

    chats = db.get_source_chats()
    text = "<b>🔍 Чаты для парсинга\n\n"
    for chat in chats:
        username = f"@{chat['username']}" if chat["username"] else "Без юзернейма"
        chat_id = f"ID: {chat['chat_id']}"
        link = f"<a href='{chat['link']}'>Ссылка</a>" if chat["link"] else "Без ссылки"
        added_date = datetime.fromtimestamp(chat["added_date"]).strftime("%d.%m.%y")
        members = f"{chat['parsed_members']}/{chat['total_members']} пользователей"

        text += f"{chat['title']} | {username} | {chat_id}\n"
        text += f"{link} | {added_date} | {members}\n\n"
    text += "</b>"

    await message.answer(text, reply_markup=source_chats_keyboard(chats))
    await state.clear()


@router.callback_query(F.data.startswith("source_chat:"))
async def callback_source_chat_details(callback: CallbackQuery, state: FSMContext):
    chat_id = int(callback.data.split(':')[1])
    chat = db.get_source_chat(chat_id)
    
    if not chat:
        try:
            await callback.message.edit_text(
                "<b>❌ Чат не найден.</b>", reply_markup=source_chats_keyboard()
            )
        except Exception as e:
            if "message is not modified" not in str(e):
                raise
        await callback.answer()
        return
    
    username = f"@{chat['username']}" if chat['username'] else "Без юзернейма"
    chat_id_text = f"ID: {chat['chat_id']}"
    link = f"<a href='{chat['link']}'>Ссылка</a>" if chat['link'] else "Без ссылки"
    added_date = datetime.fromtimestamp(chat['added_date']).strftime('%d.%m.%y')
    members = f"{chat['parsed_members']}/{chat['total_members']} пользователей"

    account_info = "Владелец: не указан"
    if 'account_first_name' in chat or 'account_last_name' in chat:
        first_name = chat['account_first_name'] if 'account_first_name' in chat else ''
        last_name = chat['account_last_name'] if 'account_last_name' in chat else ''
        name = f"{first_name} {last_name}".strip()
        if name:
            account_info = f"Владелец: 👤 {name}"
        elif 'account_phone' in chat:
            account_info = f"Владелец: 👤 {chat['account_phone']}"
    
    text = f"<b>🔍 Чат: {chat['title']}\n\n"
    text += f"Юзернейм: {username}\n"
    text += f"{chat_id_text}\n"
    text += f"Ссылка: {link}\n"
    text += f"Дата добавления: {added_date}\n"
    text += f"Участники: {members}\n"
    text += f"{account_info}</b>"

    # Создаем инлайн клавиатуру для действий с чатом
    kb = InlineKeyboardBuilder()
    kb.button(text="👥 Спарсить участников", callback_data=f"source_parse_members:{chat['chat_id']}")
    kb.button(text="🗑️ Удалить чат", callback_data=f"delete_source_chat:{chat_id}")
    kb.button(text="🔙 Назад", callback_data="source_chats")
    kb.button(text="🔙 В главное меню", callback_data="main_menu")
    kb.adjust(1)
    
    try:
        await callback.message.edit_text(text, reply_markup=kb.as_markup())
    except Exception as e:
        if "message is not modified" not in str(e):
            raise
    
    await callback.answer()


@router.callback_query(F.data.startswith("delete_source_chat:"))
async def callback_delete_source_chat(callback: CallbackQuery, state: FSMContext):
    chat_id = int(callback.data.split(":")[1])
    chat = db.get_source_chat(chat_id)

    if not chat:
        try:
            await callback.message.edit_text(
                "<b>❌ Чат не найден.</b>", reply_markup=source_chats_keyboard()
            )
        except Exception as e:
            if "message is not modified" not in str(e):
                raise
        await callback.answer()
        return

    try:
        await callback.message.edit_text(
            f"<b>🗑️ Вы уверены, что хотите удалить чат {chat['title']}?</b>",
            reply_markup=yes_no_keyboard("delete_source_chat", chat_id),
        )
    except Exception as e:
        if "message is not modified" not in str(e):
            raise
    await callback.answer()


@router.callback_query(F.data.startswith("confirm_delete_source_chat:"))
async def callback_confirm_delete_source_chat(callback: CallbackQuery, state: FSMContext):
    chat_id = int(callback.data.split(":")[1])
    chat = db.get_source_chat(chat_id)

    if not chat:
        await callback.message.edit_text("<b>❌ Чат не найден.</b>", reply_markup=source_chats_keyboard())
        await callback.answer()
        return

    title = chat["title"]
    db.delete_source_chat(chat_id)

    await callback.message.edit_text(
        f"<b>✅ Чат {title} успешно удален.</b>", reply_markup=source_chats_keyboard()
    )
    await callback.answer()


@router.callback_query(F.data.startswith("source_parse_members:"))
async def callback_parse_chat_members(callback: CallbackQuery, state: FSMContext):
    logger = logging.getLogger(__name__)
    logger.info(f"SOURCE PARSE HANDLER: Callback data: {callback.data}, Current state: {await state.get_state()}")
    
    chat_id = int(callback.data.split(':')[1])
    chat = db.get_source_chat(chat_id)
    
    if not chat:
        await callback.message.edit_text(
            "<b>❌ Чат не найден.</b>", 
            reply_markup=source_chats_keyboard()
        )
        await callback.answer()
        return
    
    if 'account_id' not in chat or not chat['account_id']:
        await callback.message.edit_text(
            "<b>❌ Для этого чата не задан аккаунт.</b>",
            reply_markup=back_button(f"source_chat:{chat_id}")
        )
        await callback.answer()
        return
    
    account = db.get_account(chat['account_id'])
    if not account:
        await callback.message.edit_text(
            "<b>❌ Связанный аккаунт не найден.</b>",
            reply_markup=back_button(f"source_chat:{chat_id}")
        )
        await callback.answer()
        return
    
    await state.update_data(chat_id=chat_id)
    await state.set_state(SourceChatStates.waiting_for_parse_type)
    
    kb = InlineKeyboardBuilder()
    kb.button(text="👥 Все участники", callback_data="source_parse_type:members")
    kb.button(text="💬 Активность в чате (90 дней)", callback_data="source_parse_type:active")
    kb.button(text="🔙 Отмена", callback_data=f"source_chat:{chat_id}")
    kb.adjust(1)
    
    await callback.message.edit_text(
        f"<b>📊 Выберите тип парсинга для чата {chat['title']}:</b>",
        reply_markup=kb.as_markup()
    )
    await callback.answer()


@router.callback_query(SourceChatStates.waiting_for_parse_type, F.data.startswith("source_parse_type:"))
async def callback_start_parsing(callback: CallbackQuery, state: FSMContext):
    parse_type = callback.data.split(':')[1]
    data = await state.get_data()
    chat_id = data.get('chat_id')
    
    if not chat_id:
        await callback.message.edit_text(
            "<b>❌ Ошибка: ID чата не найден.</b>",
            reply_markup=source_chats_keyboard()
        )
        await callback.answer()
        await state.clear()
        return
    
    chat = db.get_source_chat(chat_id)
    if not chat:
        await callback.message.edit_text(
            "<b>❌ Чат не найден.</b>",
            reply_markup=source_chats_keyboard()
        )
        await callback.answer()
        await state.clear()
        return
    
    account = db.get_account(chat['account_id'])
    if not account:
        await callback.message.edit_text(
            "<b>❌ Связанный аккаунт не найден.</b>",
            reply_markup=source_chats_keyboard()
        )
        await callback.answer()
        await state.clear()
        return
    
    await callback.message.edit_text(
        f"<b>⏳ Начинаю парсинг чата {chat['title']}...</b>\n"
        f"Тип парсинга: {'Все участники' if parse_type == 'members' else 'Активные пользователи (90 дней)'}\n"
        f"Используемый аккаунт: {account['first_name']} {account['last_name']} ({account['phone']})",
        reply_markup=None
    )
    await callback.answer()
    
    success, result = await inviter.parse_chat(account['phone'], chat_id, parse_type)
    
    if success:
        await callback.message.edit_text(
            f"<b>✅ Парсинг завершен успешно!\n\n"
            f"Чат: {chat['title']}\n"
            f"Тип: {'Все участники' if parse_type == 'members' else 'Активные пользователи'}\n"
            f"Файл: {result['filename']}\n"
            f"Пользователей: {result['total_users']}</b>",
            reply_markup=back_button(f"source_chat:{chat_id}")
        )
    else:
        await callback.message.edit_text(
            f"<b>❌ Ошибка при парсинге чата: {result}</b>",
            reply_markup=back_button(f"source_chat:{chat_id}")
        )
    
    await state.clear()
