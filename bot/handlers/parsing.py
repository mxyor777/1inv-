from datetime import datetime
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder
import logging
import asyncio

from database import db
from telegram_client import client_manager
from inviter import inviter
from bot.keyboards import (
    parsing_keyboard, 
    parsed_file_actions_keyboard,
    back_button,
    main_menu_keyboard,
    yes_no_keyboard,
    choose_account_keyboard,
    parsing_menu_keyboard
)

router = Router()

class ParsingStates(StatesGroup):
    waiting_for_chat_selection = State()
    waiting_for_account_selection = State()
    waiting_for_parse_type = State()


@router.callback_query(F.data == "parsing")
async def callback_parsing(callback: CallbackQuery, state: FSMContext):
    """Handle parsing menu callback"""
    # Сохраняем текущее меню в состоянии
    await state.update_data(previous_menu='parsing')
    await state.clear()
    
    # Используем новое меню парсинга
    try:
        await callback.message.edit_text(
            "📊 ПАРСИНГ\n\n"
            "Выберите действие:",
            reply_markup=parsing_menu_keyboard(),
            parse_mode="HTML"
        )
    except Exception as e:
        if "message is not modified" not in str(e):
            raise
    
    await callback.answer()


@router.callback_query(F.data == "parsing_results")
async def callback_parsing_results(callback: CallbackQuery, state: FSMContext):
    """Handle parsing results menu callback"""
    # Сохраняем текущее меню в состоянии
    await state.update_data(previous_menu='parsing')
    
    parsed_files = db.get_parsed_files()
    
    if not parsed_files:
        try:
            await callback.message.edit_text(
                "📊 РЕЗУЛЬТАТЫ ПАРСИНГА\n\n"
                "Нет сохраненных результатов парсинга.\n"
                "Выберите чат для парсинга через раздел \"Чаты для парсинга\".",
                reply_markup=parsing_keyboard(),
                parse_mode="HTML"
            )
        except Exception as e:
            if "message is not modified" not in str(e):
                raise
    else:
        text = "📊 РЕЗУЛЬТАТЫ ПАРСИНГА\n\n"
        text += "Сохраненные результаты парсинга:"
        
        try:
            await callback.message.edit_text(
                text,
                reply_markup=parsing_keyboard(parsed_files),
                parse_mode="HTML"
            )
        except Exception as e:
            if "message is not modified" not in str(e):
                raise
    
    await callback.answer()


@router.callback_query(F.data == "view_parsed_files")
async def callback_view_parsed_files(callback: CallbackQuery, state: FSMContext):
    """Handle view parsed files menu callback"""
    # Сохраняем текущее меню в состоянии
    await state.update_data(previous_menu='parsing')
    
    parsed_files = db.get_parsed_files()
    
    if not parsed_files:
        try:
            await callback.message.edit_text(
                "📂 ПРОСМОТР ФАЙЛОВ\n\n"
                "Нет сохраненных файлов парсинга.\n"
                "Сначала выполните парсинг через раздел \"Чаты для парсинга\".",
                reply_markup=back_button("parsing"),
                parse_mode="HTML"
            )
        except Exception as e:
            if "message is not modified" not in str(e):
                raise
    else:
        text = "📂 ПРОСМОТР ФАЙЛОВ\n\n"
        text += "Доступные файлы с результатами парсинга:"
        
        # Создаем клавиатуру с файлами
        kb = InlineKeyboardBuilder()
        for file in parsed_files:
            name = file['file_name'].split('_')[0]
            count = file['total_users']
            kb.button(text=f"{name} ({count})", callback_data=f"download_file:{file['id']}")
        
        kb.button(text="🔙 НАЗАД", callback_data="parsing")
        kb.button(text="🔙 ГЛАВНОЕ МЕНЮ", callback_data="main_menu")
        kb.adjust(1)
        
        try:
            await callback.message.edit_text(
                text,
                reply_markup=kb.as_markup(),
                parse_mode="HTML"
            )
        except Exception as e:
            if "message is not modified" not in str(e):
                raise
    
    await callback.answer()


def start_parsing_keyboard(parsed_files=None):
    """Create start parsing keyboard"""
    kb = InlineKeyboardBuilder()
    
    if parsed_files:
        for file in parsed_files:
            name = file['chat_title']
            count = file['total_users']
            parse_type = "Участники" if file['parse_type'] == "members" else "Активность в чате (90 дней)"
            kb.button(text=f"{name} | {parse_type} ({count})", callback_data=f"parsed_file:{file['id']}")
    
    kb.button(text="➕ Начать новый парсинг", callback_data="start_new_parsing")
    kb.button(text="🔙 В главное меню", callback_data="main_menu")
    kb.adjust(1)
    return kb.as_markup()


@router.callback_query(F.data == "start_new_parsing")
async def callback_start_new_parsing(callback: CallbackQuery, state: FSMContext):
    """Handle start new parsing callback"""
    source_chats = db.get_source_chats()
    
    if not source_chats:
        try:
            await callback.message.edit_text(
                "❌ У вас нет добавленных исходных чатов.\n"
                "Пожалуйста, сначала добавьте чат в разделе 'Чаты для парсинга'.",
                reply_markup=back_button("parsing")
            )
        except Exception as e:
            if "message is not modified" not in str(e):
                raise
        await callback.answer()
        return
    
    await state.set_state(ParsingStates.waiting_for_chat_selection)
    
    text = "🔍 Выберите чат для парсинга:\n\n"
    
    kb = InlineKeyboardBuilder()
    for chat in source_chats:
        kb.button(
            text=f"{chat['title']} ({chat['total_members']} участников)", 
            callback_data=f"parse_chat:{chat['id']}"
        )
    
    kb.button(text="🔙 Отмена", callback_data="parsing")
    kb.adjust(1)
    
    try:
        await callback.message.edit_text(text, reply_markup=kb.as_markup())
    except Exception as e:
        if "message is not modified" not in str(e):
            raise
    await callback.answer()


@router.callback_query(ParsingStates.waiting_for_chat_selection, F.data.startswith("parse_chat:"))
async def callback_select_chat_for_parsing(callback: CallbackQuery, state: FSMContext):
    """Handle chat selection for parsing"""
    logger = logging.getLogger(__name__)
    logger.info(f"PARSING HANDLER: Callback data: {callback.data}, Current state: {await state.get_state()}")
    
    chat_id = int(callback.data.split(':')[1])
    chat = db.get_source_chat(chat_id)
    
    if not chat:
        try:
            await callback.message.edit_text(
                "❌ Чат не найден.",
                reply_markup=back_button("parsing")
            )
        except Exception as e:
            if "message is not modified" not in str(e):
                raise
        await callback.answer()
        return
    
    await state.update_data(chat_id=chat_id)
    
    await state.set_state(ParsingStates.waiting_for_parse_type)
    
    kb = InlineKeyboardBuilder()
    kb.button(text="👥 Все участники", callback_data="parse_type:members")
    kb.button(text="💬 Активность в чате (90 дней)", callback_data="parse_type:active")
    kb.button(text="🔙 Отмена", callback_data="parsing")
    kb.adjust(1)
    
    try:
        await callback.message.edit_text(
            "📊 Выберите тип парсинга для чата {chat['title']}:",
            reply_markup=kb.as_markup()
        )
    except Exception as e:
        if "message is not modified" not in str(e):
            raise
    await callback.answer()


@router.callback_query(ParsingStates.waiting_for_parse_type, F.data.startswith("parse_type:"))
async def callback_select_parse_type(callback: CallbackQuery, state: FSMContext):
    """Handle parse type selection"""
    parse_type = callback.data.split(':')[1]
    
    await state.update_data(parse_type=parse_type)
    
    accounts = db.get_accounts()
    if not accounts:
        try:
            await callback.message.edit_text(
                "❌ Для парсинга необходимо сначала добавить хотя бы один аккаунт.",
                reply_markup=back_button("parsing")
            )
        except Exception as e:
            if "message is not modified" not in str(e):
                raise
        await callback.answer()
        return
    
    await state.set_state(ParsingStates.waiting_for_account_selection)
    
    try:
        await callback.message.edit_text(
            "👤 Выберите аккаунт для парсинга:",
            reply_markup=choose_account_keyboard(accounts)
        )
    except Exception as e:
        if "message is not modified" not in str(e):
            raise
    await callback.answer()


@router.callback_query(ParsingStates.waiting_for_account_selection, F.data.startswith("select_account:"))
async def callback_select_account_for_parsing(callback: CallbackQuery, state: FSMContext):
    """Handle account selection for parsing"""
    account_id = int(callback.data.split(':')[1])
    account = db.get_account(account_id)
    
    if not account:
        try:
            await callback.message.edit_text(
                "❌ Аккаунт не найден.",
                reply_markup=back_button("parsing")
            )
        except Exception as e:
            if "message is not modified" not in str(e):
                raise
        await callback.answer()
        return
    
    data = await state.get_data()
    chat_id = data.get('chat_id')
    parse_type = data.get('parse_type')
    
    if not chat_id or not parse_type:
        try:
            await callback.message.edit_text(
                "❌ Ошибка: Данные для парсинга не найдены.",
                reply_markup=back_button("parsing")
            )
        except Exception as e:
            if "message is not modified" not in str(e):
                raise
        await callback.answer()
        await state.clear()
        return
    
    chat = db.get_source_chat(chat_id)
    if not chat:
        try:
            await callback.message.edit_text(
                "❌ Чат не найден.",
                reply_markup=back_button("parsing")
            )
        except Exception as e:
            if "message is not modified" not in str(e):
                raise
        await callback.answer()
        await state.clear()
        return
    
    parse_type_text = "участников" if parse_type == "members" else "активных пользователей"
    
    try:
        await callback.message.edit_text(
            f"⏳ Начинаю парсинг {parse_type_text} чата {chat['title']}...\n"
            f"Это может занять некоторое время в зависимости от размера чата."
        )
    except Exception as e:
        if "message is not modified" not in str(e):
            raise
    
    success, result = await inviter.parse_chat(account['phone'], chat_id, parse_type)
    
    if success:
        filename = result['filename']
        total_users = result['total_users']
        chat_title = result['chat_title']
        
        try:
            await callback.message.edit_text(
                f"✅ Парсинг {parse_type_text} чата {chat_title} успешно завершен!\n\n"
                f"Файл: {filename}\n"
                f"Всего пользователей: {total_users}\n",
                reply_markup=back_button("parsing")
            )
        except Exception as e:
            if "message is not modified" not in str(e):
                raise
    else:
        try:
            await callback.message.edit_text(
                f"❌ Ошибка при парсинге {parse_type_text}:\n{result}",
                reply_markup=back_button("parsing")
            )
        except Exception as e:
            if "message is not modified" not in str(e):
                raise
    
    await state.clear()


@router.callback_query(F.data.startswith("parsed_file:"))
async def callback_parsed_file_details(callback: CallbackQuery, state: FSMContext):
    """Handle parsed file details callback"""
    file_id = int(callback.data.split(':')[1])
    parsed_file = db.get_parsed_file(file_id)
    
    if not parsed_file:
        try:
            await callback.message.edit_text(
                "❌ Файл не найден.",
                reply_markup=parsing_keyboard()
            )
        except Exception as e:
            if "message is not modified" not in str(e):
                raise
        await callback.answer()
        return
    
    source_chat = db.get_source_chat(parsed_file['source_chat_id'])
    chat_title = source_chat['title'] if source_chat else "Неизвестный чат"
    
    file_name = parsed_file['file_name']
    total_users = parsed_file['total_users']
    parse_type = "Участники" if parsed_file['parse_type'] == "members" else "Активность в чате (90 дней)"
    added_date = datetime.fromtimestamp(parsed_file['added_date']).strftime('%d.%m.%y')
    
    text = f"📊 Файл с пользователями\n\n"
    text += f"Чат: {chat_title}\n"
    text += f"Тип парсинга: {parse_type}\n"
    text += f"Пользователей: {total_users}\n"
    text += f"Дата создания: {added_date}\n"
    text += f"Файл: {file_name}\n"
    
    try:
        await callback.message.edit_text(
            text,
            reply_markup=parsed_file_actions_keyboard(file_id)
        )
    except Exception as e:
        if "message is not modified" not in str(e):
            raise
    await callback.answer()


@router.callback_query(F.data.startswith("use_for_inviting:"))
async def callback_use_for_inviting(callback: CallbackQuery, state: FSMContext):
    """Handle use for inviting callback"""
    file_id = int(callback.data.split(':')[1])
    parsed_file = db.get_parsed_file(file_id)
    
    if not parsed_file:
        try:
            await callback.message.edit_text(
                "❌ Файл не найден.",
                reply_markup=parsing_keyboard()
            )
        except Exception as e:
            if "message is not modified" not in str(e):
                raise
        await callback.answer()
        return
    
    try:
        await callback.message.edit_text(
            "📣 Выберите целевой чат для инвайтинга\n\n"
            f"Будет использован файл: {parsed_file['file_name']}\n"
            f"Количество пользователей: {parsed_file['total_users']}\n\n"
            "Перенаправление в раздел 'Чаты для инвайта'..."
        )
    except Exception as e:
        if "message is not modified" not in str(e):
            raise
    
    await callback.bot.callback_query(callback.message.chat.id, callback.message.message_id, data="target_chats")
    await callback.answer()


@router.callback_query(F.data.startswith("delete_parsed_file:"))
async def callback_delete_parsed_file(callback: CallbackQuery, state: FSMContext):
    """Handle delete parsed file callback"""
    file_id = int(callback.data.split(':')[1])
    parsed_file = db.get_parsed_file(file_id)
    
    if not parsed_file:
        try:
            await callback.message.edit_text(
                "❌ Файл не найден.",
                reply_markup=parsing_keyboard()
            )
        except Exception as e:
            if "message is not modified" not in str(e):
                raise
        await callback.answer()
        return
    
    try:
        await callback.message.edit_text(
            f"🗑️ Вы уверены, что хотите удалить файл {parsed_file['file_name']}?",
            reply_markup=yes_no_keyboard("delete_parsed_file", file_id)
        )
    except Exception as e:
        if "message is not modified" not in str(e):
            raise
    await callback.answer()


@router.callback_query(F.data.startswith("confirm_delete_parsed_file:"))
async def callback_confirm_delete_parsed_file(callback: CallbackQuery, state: FSMContext):
    """Handle delete parsed file confirmation"""
    file_id = int(callback.data.split(':')[1])
    parsed_file = db.get_parsed_file(file_id)
    
    if not parsed_file:
        try:
            await callback.message.edit_text(
                "❌ Файл не найден.",
                reply_markup=parsing_keyboard()
            )
        except Exception as e:
            if "message is not modified" not in str(e):
                raise
        await callback.answer()
        return
    
    file_name = parsed_file['file_name']
    db.delete_parsed_file(file_id)
    
    try:
        await callback.message.edit_text(
            f"✅ Файл {file_name} успешно удален.",
            reply_markup=back_button("parsing")
        )
    except Exception as e:
        if "message is not modified" not in str(e):
            raise
    await callback.answer()


async def update_parsing_progress(message, chat_id, current, total, parse_type):
    """Обновление сообщения с прогрессом парсинга динамически"""
    chat = db.get_source_chat(chat_id)
    if not chat:
        return
    
    account = db.get_account(chat.get('account_id'))
    
    account_name = "Неизвестный аккаунт"
    if account:
        account_name = f"{account['first_name']} {account['last_name']}".strip()
        if not account_name:
            account_name = account['phone']
    
    chat_name = chat.get('title', "Неизвестный чат")
    
    text = f"📊 ПРОГРЕСС ПАРСИНГА\n\n"
    text += f"👤 Аккаунт: {account_name}\n"
    text += f"🔍 Чат: {chat_name}\n"
    text += f"Тип парсинга: {'Активность в чате' if parse_type == 'active' else 'Все участники'}\n\n"
    
    # Расчет процента выполнения
    percent = int((current / total) * 100) if total > 0 else 0
    progress_bar = "▓" * (percent // 5) + "░" * (20 - (percent // 5))
    
    text += f"Прогресс: [{progress_bar}] {percent}%\n"
    text += f"Обработано {current} из {total} участников\n"
    
    kb = InlineKeyboardBuilder()
    kb.button(text="⏸ ПРИОСТАНОВИТЬ", callback_data=f"pause_parsing:{chat_id}")
    kb.button(text="🔙 НАЗАД", callback_data="parsing")
    kb.button(text="🔙 ГЛАВНОЕ МЕНЮ", callback_data="main_menu")
    kb.adjust(1)
    
    try:
        await message.edit_text(text, reply_markup=kb.as_markup(), parse_mode="HTML")
    except Exception as e:
        if "message is not modified" not in str(e):
            logging.error(f"Error updating parsing progress: {e}")


@router.callback_query(F.data.startswith("start_parse_chat:"))
async def callback_start_parse_chat(callback: CallbackQuery, state: FSMContext):
    """Начать парсинг чата"""
    chat_id = int(callback.data.split(':')[1])
    chat = db.get_source_chat(chat_id)
    
    if not chat:
        await callback.message.edit_text(
            "❌ Чат не найден.",
            reply_markup=back_button("source_chats"),
            parse_mode="HTML"
        )
        await callback.answer()
        return
    
    # Запрашиваем выбор типа парсинга
    kb = InlineKeyboardBuilder()
    kb.button(text="👥 ВСЕ УЧАСТНИКИ", callback_data=f"parse_type:{chat_id}:members")
    kb.button(text="💬 АКТИВНОСТЬ В ЧАТЕ (90 ДНЕЙ)", callback_data=f"parse_type:{chat_id}:active")
    kb.button(text="🔙 НАЗАД", callback_data=f"source_chat:{chat_id}")
    kb.adjust(1)
    
    await callback.message.edit_text(
        "📊 Выберите тип парсинга для чата {chat['title']}:",
        reply_markup=kb.as_markup(),
        parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data.startswith("parse_type:"))
async def callback_parse_type(callback: CallbackQuery, state: FSMContext):
    """Обработка выбора типа парсинга"""
    parts = callback.data.split(':')
    chat_id = int(parts[1])
    parse_type = parts[2]
    
    chat = db.get_source_chat(chat_id)
    if not chat:
        await callback.message.edit_text(
            "❌ Чат не найден.",
            reply_markup=back_button("source_chats"),
            parse_mode="HTML"
        )
        await callback.answer()
        return
    
    # Получаем информацию об аккаунте для парсинга
    account_id = chat.get('account_id')
    if not account_id:
        # Если аккаунт не привязан к чату, предлагаем выбрать
        accounts = db.get_accounts()
        if not accounts:
            await callback.message.edit_text(
                "❌ Нет доступных аккаунтов для парсинга.",
                reply_markup=back_button("source_chats"),
                parse_mode="HTML"
            )
            await callback.answer()
            return
        
        # Сохраняем выбранный тип парсинга
        await state.update_data(chat_id=chat_id, parse_type=parse_type)
        await state.set_state(ParsingStates.waiting_for_account_selection)
        
        await callback.message.edit_text(
            "👤 Выберите аккаунт для парсинга:",
            reply_markup=choose_account_keyboard(accounts),
            parse_mode="HTML"
        )
        await callback.answer()
        return
    
    # Если аккаунт уже привязан, начинаем парсинг
    await callback.message.edit_text(
        "⏳ Начинаем парсинг чата {chat['title']}...",
        parse_mode="HTML"
    )
    
    # Запускаем парсинг в отдельной корутине
    asyncio.create_task(start_parsing(callback.message, chat_id, account_id, parse_type))
    await callback.answer()


async def start_parsing(message, chat_id, account_id, parse_type):
    """Запуск процесса парсинга"""
    chat = db.get_source_chat(chat_id)
    account = db.get_account(account_id)
    
    if not chat or not account:
        await message.edit_text(
            "❌ Не найдены все необходимые данные для парсинга.",
            reply_markup=back_button("source_chats"),
            parse_mode="HTML"
        )
        return
    
    client = client_manager.get_client(account['phone'])
    if not client:
        await message.edit_text(
            f"❌ Не удалось подключиться к аккаунту {account['phone']}.",
            reply_markup=back_button("source_chats"),
            parse_mode="HTML"
        )
        return
    
    # Проверяем, является ли чат каналом или группой
    try:
        entity = await client.get_entity(chat['chat_id'])
        total_members = 0
        
        if hasattr(entity, 'participants_count'):
            total_members = entity.participants_count
        else:
            # Если счетчик участников недоступен, оцениваем примерно
            total_members = 100
        
        # Инициализируем прогресс
        await update_parsing_progress(message, chat_id, 0, total_members, parse_type)
        
        # Запускаем парсинг
        parsed_users = []
        current_count = 0
        
        if parse_type == 'members':
            # Парсинг всех участников
            async for user in client.iter_participants(entity):
                current_count += 1
                if current_count % 10 == 0:  # Обновляем прогресс каждые 10 пользователей
                    await update_parsing_progress(message, chat_id, current_count, total_members, parse_type)
                
                if user.bot:
                    continue  # Пропускаем ботов
                
                user_data = {
                    'user_id': user.id,
                    'access_hash': user.access_hash,
                    'username': user.username,
                    'first_name': user.first_name if hasattr(user, 'first_name') else None,
                    'last_name': user.last_name if hasattr(user, 'last_name') else None,
                    'phone': user.phone if hasattr(user, 'phone') else None,
                    'bot': user.bot if hasattr(user, 'bot') else False
                }
                parsed_users.append(user_data)
        
        elif parse_type == 'active':
            # Парсинг активных пользователей (за последние 90 дней)
            async for message in client.iter_messages(entity, limit=1000):
                if message.sender_id and message.sender_id > 0:  # Проверяем, что отправитель - пользователь
                    # Проверяем, нет ли уже этого пользователя в списке
                    if not any(u['user_id'] == message.sender_id for u in parsed_users):
                        try:
                            user = await client.get_entity(message.sender_id)
                            current_count += 1
                            
                            if current_count % 5 == 0:  # Обновляем прогресс каждые 5 пользователей
                                await update_parsing_progress(message, chat_id, current_count, total_members, parse_type)
                            
                            if user.bot:
                                continue  # Пропускаем ботов
                            
                            user_data = {
                                'user_id': user.id,
                                'access_hash': user.access_hash,
                                'username': user.username,
                                'first_name': user.first_name if hasattr(user, 'first_name') else None,
                                'last_name': user.last_name if hasattr(user, 'last_name') else None,
                                'phone': user.phone if hasattr(user, 'phone') else None,
                                'bot': user.bot if hasattr(user, 'bot') else False
                            }
                            parsed_users.append(user_data)
                        except Exception as e:
                            logging.error(f"Error parsing active user: {e}")
        
        # Сохраняем результаты парсинга
        file_name = f"{chat['title']}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        file_id = db.save_parsed_file(
            file_name=file_name,
            source_chat_id=chat_id,
            total_users=len(parsed_users),
            parse_type=parse_type
        )
        
        if file_id:
            for user_data in parsed_users:
                db.add_parsed_user(file_id, user_data)
            
            # Обновляем данные чата о количестве участников
            db.update_source_chat(chat_id, {
                'total_members': total_members,
                'parsed_members': len(parsed_users)
            })
            
            # Финальное обновление прогресса
            await update_parsing_progress(message, chat_id, len(parsed_users), total_members, parse_type)
            
            # Отправляем сообщение о завершении
            kb = InlineKeyboardBuilder()
            kb.button(text="�� ПРОСМОТРЕТЬ РЕЗУЛЬТАТЫ", callback_data=f"parsed_file:{file_id}")
            kb.button(text="🔙 НАЗАД", callback_data="parsing")
            kb.button(text="🔙 ГЛАВНОЕ МЕНЮ", callback_data="main_menu")
            kb.adjust(1)
            
            await message.edit_text(
                "✅ Парсинг завершен!\n\n"
                "Чат: {chat['title']}\n"
                "Тип парсинга: {'Активность в чате' if parse_type == 'active' else 'Все участники'}\n"
                "Собрано пользователей: {len(parsed_users)}\n",
                reply_markup=kb.as_markup(),
                parse_mode="HTML"
            )
        else:
            await message.edit_text(
                "❌ Ошибка при сохранении результатов парсинга.",
                reply_markup=back_button("parsing"),
                parse_mode="HTML"
            )
    
    except Exception as e:
        logging.error(f"Error in parsing process: {e}")
        await message.edit_text(
            "❌ Ошибка при парсинге: {str(e)}",
            reply_markup=back_button("parsing"),
            parse_mode="HTML"
        )