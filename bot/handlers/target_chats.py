import re
from datetime import datetime
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from database import db
from telegram_client import client_manager
from bot.keyboards import (
    target_chats_keyboard,
    target_chat_actions_keyboard,
    choose_account_keyboard,
    back_button,
    yes_no_keyboard,
    main_menu_keyboard,
)

router = Router()


class TargetChatStates(StatesGroup):
    waiting_for_chat_link = State()
    waiting_for_account_selection = State()
    waiting_for_chat_name = State()


@router.callback_query(F.data == "target_chats")
async def callback_target_chats(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    chats = db.get_target_chats()
    
    if not chats:
        try:
            await callback.message.edit_text(
                "<b>📣 Чаты для инвайта\n\n"
                "У вас пока нет добавленных целевых чатов.\n"
                "Нажмите кнопку ниже, чтобы добавить чат.</b>",
                reply_markup=target_chats_keyboard(),
            )
        except Exception as e:
            if "message is not modified" not in str(e):
                raise
    else:
        text = "<b>📣 Чаты для инвайта\n\n"
        for chat in chats:
            username = f"@{chat['username']}" if chat["username"] else "Без юзернейма"
            chat_id = f"ID: {chat['chat_id']}"
            link = f"<a href='{chat['link']}'>Ссылка</a>" if chat["link"] else "Без ссылки"
            added_date = datetime.fromtimestamp(chat["added_date"]).strftime("%d.%m.%y")
            
            account_info = ""
            if 'account_first_name' in chat or 'account_last_name' in chat:
                first_name = chat['account_first_name'] if 'account_first_name' in chat else ''
                last_name = chat['account_last_name'] if 'account_last_name' in chat else ''
                name = f"{first_name} {last_name}".strip()
                if name:
                    account_info = f"👤 {name} | "
                elif 'account_phone' in chat:
                    account_info = f"👤 {chat['account_phone']} | "
            
            text += f"{account_info}{chat['title']} | {username} | {chat_id}\n"
            text += f"{link} | {added_date}\n\n"
        text += "</b>"
        
        try:
            await callback.message.edit_text(
                text, reply_markup=target_chats_keyboard(chats)
            )
        except Exception as e:
            if "message is not modified" not in str(e):
                raise
    
    await callback.answer()


@router.callback_query(F.data == "add_target_chat")
async def callback_add_target_chat(callback: CallbackQuery, state: FSMContext):
    accounts = db.get_accounts()
    if not accounts:
        try:
            await callback.message.edit_text(
                "❌ Для добавления чата необходимо сначала добавить хотя бы один аккаунт.",
                reply_markup=main_menu_keyboard(),
            )
        except Exception as e:
            if "message is not modified" not in str(e):
                raise
        await callback.answer()
        return

    await state.set_state(TargetChatStates.waiting_for_account_selection)
    try:
        await callback.message.edit_text(
            "👤 Выберите аккаунт, с которого будет добавлен чат:",
            reply_markup=choose_account_keyboard(accounts),
        )
    except Exception as e:
        if "message is not modified" not in str(e):
            raise
    await callback.answer()


@router.callback_query(
    TargetChatStates.waiting_for_account_selection, 
    F.data.startswith("select_account:")
)
async def callback_select_account_for_target_chat(callback: CallbackQuery, state: FSMContext):
    account_id = int(callback.data.split(":")[1])
    account = db.get_account(account_id)
    data = await state.get_data()
    
    if "invite_link_chat_id" in data:
        chat_id = data["invite_link_chat_id"]
        chat = db.get_target_chat(chat_id)
        
        if not account:
            await callback.message.edit_text(
                "❌ Аккаунт не найден.", 
                reply_markup=main_menu_keyboard()
            )
            await callback.answer()
            return
            
        await callback.message.edit_text(
            f"⏳ Запрашиваю инвайт-ссылку для чата {chat['title']}..."
        )
        
        invite_link, error = await client_manager.get_chat_invite_link(account['phone'], chat['chat_id'])
        
        if not invite_link:
            await callback.message.edit_text(
                f"❌ Не удалось получить инвайт-ссылку: {error}",
                reply_markup=target_chat_actions_keyboard(chat_id)
            )
            await callback.answer()
            return
        
        kb = InlineKeyboardBuilder()
        kb.button(text="🔙 Назад к деталям чата", callback_data=f"target_chat:{chat_id}")
        kb.button(text="🔙 К списку чатов", callback_data="target_chats")
        kb.button(text="🔙 В главное меню", callback_data="main_menu")
        kb.adjust(1)
        
        await callback.message.edit_text(
            f"✅ Инвайт-ссылка для чата {chat['title']}:\n\n"
            f"{invite_link}\n\n"
            f"Вы можете скопировать эту ссылку и отправить её пользователям.",
            reply_markup=kb.as_markup()
        )
        await callback.answer("Ссылка успешно получена")
        await state.clear()
        return
    
    elif "change_owner_chat_id" in data:
        chat_id = data["change_owner_chat_id"]
        chat = db.get_target_chat(chat_id)
        
        if not account:
            await callback.message.edit_text(
                "❌ Аккаунт не найден.", 
                reply_markup=main_menu_keyboard()
            )
            await callback.answer()
            return
        
        db.update_target_chat_account(chat_id, account_id)
        
        updated_chat = db.get_target_chat(chat_id)
        
        await callback.message.edit_text(
            f"✅ Владелец чата {chat['title']} успешно изменен на {account['phone']}!",
            reply_markup=target_chats_keyboard()
        )
        await callback.answer("Владелец успешно изменен")
        await state.clear()
        return
        
    if not account:
        try:
            await callback.message.edit_text(
                "❌ Аккаунт не найден.", 
                reply_markup=main_menu_keyboard()
            )
        except Exception as e:
            if "message is not modified" not in str(e):
                raise
        await callback.answer()
        return

    await state.update_data(account_id=account_id, account_phone=account["phone"])
    await state.set_state(TargetChatStates.waiting_for_chat_link)

    kb = InlineKeyboardBuilder()
    kb.button(text="➕ Создать чат", callback_data="create_chat_for_invite")
    kb.button(text="🔙 Назад", callback_data="back_to_account_selection")
    kb.adjust(1)

    try:
        await callback.message.edit_text(
            "🔗 Введите ссылку на чат или его юзернейм (например, @username или https://t.me/username):\n"
            "Или нажмите кнопку ниже, чтобы создать новый чат для инвайтинга.",
            reply_markup=kb.as_markup(),
        )
    except Exception as e:
        if "message is not modified" not in str(e):
            raise
    await callback.answer()


@router.callback_query(F.data == "back_to_account_selection")
async def callback_back_to_account_selection(callback: CallbackQuery, state: FSMContext):
    """Handler for back button in chat link input - goes back to account selection"""
    accounts = db.get_accounts()
    await state.set_state(TargetChatStates.waiting_for_account_selection)

    try:
        await callback.message.edit_text(
            "👤 Выберите аккаунт, с которого будет добавлен чат:",
            reply_markup=choose_account_keyboard(accounts),
        )
    except Exception as e:
        if "message is not modified" not in str(e):
            raise

    await callback.answer()


@router.callback_query(F.data == "create_chat_for_invite")
async def callback_create_chat_for_invite(callback: CallbackQuery, state: FSMContext):
    """Handler to start creating a new chat for inviting"""
    data = await state.get_data()
    account_phone = data.get("account_phone")
    account_id = data.get("account_id")

    if not account_phone:
        await callback.message.edit_text(
            "❌ Ошибка: Телефон аккаунта не найден.", reply_markup=main_menu_keyboard()
        )
        await callback.answer()
        await state.clear()
        return

    kb = InlineKeyboardBuilder()
    kb.button(text="📝 Использовать стандартное название", callback_data="use_default_chat_name")
    kb.button(text="🔙 Назад", callback_data="back_to_account_selection")
    kb.adjust(1)

    await callback.message.edit_text(
        "✏️ Введите название для нового чата или выберите стандартное:", reply_markup=kb.as_markup()
    )

    await state.set_state(TargetChatStates.waiting_for_chat_name)
    await state.update_data(account_id=account_id)
    await callback.answer()


@router.callback_query(F.data == "use_default_chat_name", TargetChatStates.waiting_for_chat_name)
async def callback_use_default_chat_name(callback: CallbackQuery, state: FSMContext):
    """Use default chat name and create the chat"""
    data = await state.get_data()
    account_phone = data.get("account_phone")
    account_id = data.get("account_id")

    if not account_phone:
        await callback.message.edit_text(
            "❌ Ошибка: Телефон аккаунта не найден.", reply_markup=main_menu_keyboard()
        )
        await callback.answer()
        await state.clear()
        return

    account = None
    for acc in db.get_accounts():
        if acc["phone"] == account_phone:
            account = acc
            break

    chat_name = f"Чат для инвайтинга"
    if account:
        name = f"{account['first_name']} {account['last_name']}".strip()
        if name:
            chat_name = f"Чат {name} {datetime.now().strftime('%d.%m.%y')}"
        else:
            chat_name = f"Чат {account_phone} {datetime.now().strftime('%d.%m.%y')}"

    status_msg = await callback.message.edit_text(f'⏳ Создаю новый чат "{chat_name}"...')

    result, error = await client_manager.create_group_chat(
        account_phone, title=chat_name, description=f""
    )

    if not result:
        await status_msg.edit_text(
            f"❌ Не удалось создать чат: {error}",
            reply_markup=back_button("back_to_account_selection"),
        )
        await callback.answer()
        return

    db.add_target_chat(
        chat_id=result["id"],
        username=result.get("username", ""),
        title=result["title"],
        link=result.get("link", ""),
        account_id=account_id,
    )

    await status_msg.edit_text(
        f"<b>✅ Новый чат \"{result['title']}\" успешно создан!\n\n"
        f"ID: {result['id']}\n"
        f"Юзернейм: {'@' + result.get('username', '') if result.get('username') else 'Нет'}\n</b>",
        reply_markup=target_chats_keyboard(db.get_target_chats()),
    )

    await callback.answer()
    await state.clear()


@router.message(TargetChatStates.waiting_for_chat_name)
async def handle_chat_name(message: Message, state: FSMContext):
    """Handle the chat name input and create a new chat"""
    data = await state.get_data()
    account_phone = data.get("account_phone")
    account_id = data.get("account_id")

    if not account_phone:
        await message.answer(
            "❌ Ошибка: Телефон аккаунта не найден.", reply_markup=main_menu_keyboard()
        )
        await state.clear()
        return

    chat_name = message.text.strip()

    if not chat_name:
        await message.answer(
            "❌ Название чата не может быть пустым. Пожалуйста, введите название:",
            reply_markup=back_button("back_to_account_selection"),
        )
        return

    status_msg = await message.answer("⏳ Создаю новый чат...")

    result, error = await client_manager.create_group_chat(
        account_phone,
        title=chat_name,
        description=f"Чат для приглашения пользователей: {chat_name}",
    )

    if not result:
        await status_msg.edit_text(
            f"❌ Не удалось создать чат: {error}",
            reply_markup=back_button("back_to_account_selection"),
        )
        return

    db.add_target_chat(
        chat_id=result["id"],
        username=result.get("username", ""),
        title=result["title"],
        link=result.get("link", ""),
        account_id=account_id,
    )

    await status_msg.edit_text(
        f"<b>✅ Новый чат \"{result['title']}\" успешно создан!\n\n"
        f"ID: {result['id']}\n"
        f"Юзернейм: {'@' + result.get('username', '') if result.get('username') else 'Нет'}\n</b>",
        reply_markup=target_chats_keyboard(db.get_target_chats()),
    )

    await state.clear()


@router.message(TargetChatStates.waiting_for_chat_link)
async def handle_target_chat_link(message: Message, state: FSMContext):
    data = await state.get_data()
    account_phone = data.get("account_phone")
    account_id = data.get("account_id")

    if not account_phone:
        await message.answer(
            "❌ Ошибка: Телефон аккаунта не найден.", reply_markup=main_menu_keyboard()
        )
        await state.clear()
        return

    chat_link = message.text.strip()

    if chat_link.startswith("@"):
        chat_link = chat_link[1:]
    elif "t.me/" in chat_link:
        chat_link = chat_link.split("t.me/", 1)[1]

    status_msg = await message.answer(f"⏳ Получаю информацию о чате {chat_link}...")

    join_success, join_error = await client_manager.join_chat(account_phone, chat_link)
    if not join_success:
        await status_msg.edit_text(f"❌ Не удалось присоединиться к чату: {join_error}")
        return

    chat_info, error = await client_manager.get_chat_info(account_phone, chat_link)

    if not chat_info:
        await status_msg.edit_text(f"❌ Не удалось получить информацию о чате: {error}")
        return

    db.add_target_chat(
        chat_id=chat_info["id"],
        username=chat_info["username"],
        title=chat_info["title"],
        link=chat_info["link"],
        account_id=account_id,
    )

    await status_msg.edit_text(
        f"✅ Целевой чат {chat_info['title']} успешно добавлен!\n\n"
        f"ID: {chat_info['id']}\n"
        f"Юзернейм: {'@' + chat_info['username'] if chat_info['username'] else 'Нет'}\n"
    )

    chats = db.get_target_chats()
    text = "📣 Чаты для инвайта\n\n"
    for chat in chats:
        username = f"@{chat['username']}" if chat["username"] else "Без юзернейма"
        chat_id = f"ID: {chat['chat_id']}"
        link = f"<a href='{chat['link']}'>Ссылка</a>" if chat["link"] else "Без ссылки"
        added_date = datetime.fromtimestamp(chat["added_date"]).strftime("%d.%m.%y")

        text += f"{chat['title']} | {username} | {chat_id}\n"
        text += f"{link} | {added_date}\n\n"

    await message.answer(text, reply_markup=target_chats_keyboard(chats), parse_mode="HTML")
    await state.clear()


@router.callback_query(F.data.startswith("target_chat:"))
async def callback_target_chat_details(callback: CallbackQuery, state: FSMContext):
    chat_id = int(callback.data.split(':')[1])
    chat = db.get_target_chat(chat_id)
    
    if not chat:
        await callback.message.edit_text(
            "<b>❌ Чат не найден.</b>",
            reply_markup=target_chats_keyboard(),
            parse_mode="HTML"
        )
        await callback.answer()
        return
    
    username = f"@{chat['username']}" if chat['username'] else "Без юзернейма"
    
    chat_id_text = f"ID: {chat['chat_id']}"
    link = f"<a href='{chat['link']}'>Ссылка</a>" if chat['link'] else "Без ссылки"
    added_date = datetime.fromtimestamp(chat['added_date']).strftime('%d.%m.%y')

    account_info = "Владелец: не указан"
    if 'account_id' in chat and chat['account_id']:
        if 'account_first_name' in chat or 'account_last_name' in chat:
            first_name = chat['account_first_name'] if 'account_first_name' in chat else ''
            last_name = chat['account_last_name'] if 'account_last_name' in chat else ''
            name = f"{first_name} {last_name}".strip()
            if name:
                account_info = f"Владелец: 👤 {name}"
            elif 'account_phone' in chat:
                account_info = f"Владелец: 👤 {chat['account_phone']}"

    text = f"<b>✅ Чат: {chat['title']}</b>\n\n"
    text += f"<b>Юзернейм:</b> {username}\n"
    text += f"<b>{chat_id_text}</b>\n"
    text += f"<b>Ссылка:</b> {link}\n"
    text += f"<b>Дата добавления:</b> {added_date}\n"
    text += f"<b>{account_info}</b>\n"

    # Определяем тип чата (для инвайта или для парсинга)
    chat_type = "invite"  # По умолчанию считаем, что чат для инвайтинга

    try:
        await callback.message.edit_text(
            text, 
            reply_markup=target_chat_actions_keyboard(chat_id, chat_type), 
            parse_mode="HTML"
        )
    except Exception as e:
        if "message is not modified" not in str(e):
            raise

    await callback.answer()


@router.callback_query(F.data.startswith("delete_target_chat:"))
async def callback_delete_target_chat(callback: CallbackQuery, state: FSMContext):
    chat_id = int(callback.data.split(":")[1])
    chat = db.get_target_chat(chat_id)

    if not chat:
        try:
            await callback.message.edit_text(
                "❌ Чат не найден.", reply_markup=target_chats_keyboard()
            )
        except Exception as e:
            if "message is not modified" not in str(e):
                raise
        await callback.answer()
        return

    try:
        await callback.message.edit_text(
            f"🗑️ Вы уверены, что хотите удалить чат {chat['title']}?",
            reply_markup=yes_no_keyboard("delete_target_chat", chat_id),
        )
    except Exception as e:
        if "message is not modified" not in str(e):
            raise
    await callback.answer()


@router.callback_query(F.data.startswith("confirm_delete_target_chat:"))
async def callback_confirm_delete_target_chat(callback: CallbackQuery, state: FSMContext):
    chat_id = int(callback.data.split(":")[1])
    chat = db.get_target_chat(chat_id)

    if not chat:
        try:
            await callback.message.edit_text(
                "❌ Чат не найден.", reply_markup=target_chats_keyboard()
            )
        except Exception as e:
            if "message is not modified" not in str(e):
                raise
        await callback.answer()
        return

    title = chat["title"]
    db.delete_target_chat(chat_id)

    try:
        await callback.message.edit_text(
            f"✅ Чат {title} успешно удален.", reply_markup=target_chats_keyboard()
        )
    except Exception as e:
        if "message is not modified" not in str(e):
            raise
    await callback.answer()


@router.callback_query(F.data == "main_menu")
async def callback_to_main_menu_from_targets(callback: CallbackQuery, state: FSMContext):
    await state.clear()

    try:
        await callback.message.edit_text("📋 Главное меню:", reply_markup=main_menu_keyboard())
    except Exception as e:
        if "message is not modified" not in str(e):
            raise

    await callback.answer()


@router.callback_query(F.data == "cancel")
async def callback_cancel_in_target_chats(callback: CallbackQuery, state: FSMContext):
    current_state = await state.get_state()

    if current_state in [
        TargetChatStates.waiting_for_chat_link.state,
        TargetChatStates.waiting_for_chat_name.state,
    ]:
        await state.set_state(TargetChatStates.waiting_for_account_selection)
        accounts = db.get_accounts()
        await callback.message.edit_text(
            "👤 Выберите аккаунт, с которого будет добавлен чат:",
            reply_markup=choose_account_keyboard(accounts),
        )
    elif current_state in [TargetChatStates.waiting_for_account_selection.state]:
        await state.clear()
        chats = db.get_target_chats()
        await show_target_chats_list(callback.message, chats)
    else:
        await state.clear()
        chats = db.get_target_chats()
        await show_target_chats_list(callback.message, chats)

    await callback.answer()


async def show_target_chats_list(message, chats):
    """Helper function to show target chats list"""
    if not chats:
        try:
            await message.edit_text(
                "📣 Чаты для инвайта\n\n"
                "У вас пока нет добавленных целевых чатов.\n"
                "Нажмите кнопку ниже, чтобы добавить чат.",
                reply_markup=target_chats_keyboard(),
            )
        except Exception as e:
            if "message is not modified" not in str(e):
                raise
    else:
        text = "📣 Чаты для инвайта\n\n"
        for chat in chats:
            username = f"@{chat['username']}" if chat["username"] else "Без юзернейма"
            chat_id = f"ID: {chat['chat_id']}"
            link = f"<a href='{chat['link']}'>Ссылка</a>" if chat["link"] else "Без ссылки"
            added_date = datetime.fromtimestamp(chat["added_date"]).strftime("%d.%m.%y")

            account_info = ""
            if 'account_first_name' in chat or 'account_last_name' in chat:
                first_name = chat['account_first_name'] if 'account_first_name' in chat else ''
                last_name = chat['account_last_name'] if 'account_last_name' in chat else ''
                name = f"{first_name} {last_name}".strip()
                if name:
                    account_info = f"👤 {name} | "
                elif 'account_phone' in chat:
                    account_info = f"👤 {chat['account_phone']} | "

            text += f"{account_info}{chat['title']} | {username} | {chat_id}\n"
            text += f"{link} | {added_date}\n\n"

        try:
            await message.edit_text(
                text, reply_markup=target_chats_keyboard(chats), parse_mode="HTML"
            )
        except Exception as e:
            if "message is not modified" not in str(e):
                raise


@router.callback_query(F.data.startswith("get_chat_invite_link:"))
async def callback_get_chat_invite_link(callback: CallbackQuery, state: FSMContext):
    """Handler for getting an invite link for a chat"""
    chat_id = int(callback.data.split(':')[1])
    chat = db.get_target_chat(chat_id)
    
    if not chat:
        await callback.message.edit_text(
            "❌ Чат не найден.",
            reply_markup=target_chats_keyboard()
        )
        await callback.answer()
        return
    
    account = None
    if 'account_id' in chat and chat['account_id']:
        account = db.get_account(chat['account_id'])
    
    if not account:
        accounts = db.get_accounts(status='active')
        if not accounts:
            await callback.message.edit_text(
                "❌ Нет доступных аккаунтов для получения инвайт-ссылки.\n"
                "Добавьте хотя бы один активный аккаунт.",
                reply_markup=target_chat_actions_keyboard(chat_id)
            )
            await callback.answer()
            return
        
        if len(accounts) == 1:
            account = accounts[0]
            await callback.message.edit_text(
                f"ℹ️ Используем аккаунт {account['phone']} для получения ссылки...",
            )
        else:
            await state.set_state(TargetChatStates.waiting_for_account_selection)
            await state.update_data(invite_link_chat_id=chat_id)
            
            await callback.message.edit_text(
                f"👤 Выберите аккаунт для получения инвайт-ссылки для чата {chat['title']}:",
                reply_markup=choose_account_keyboard(accounts)
            )
            await callback.answer()
            return
    
    await callback.message.edit_text(
        f"⏳ Запрашиваю инвайт-ссылку для чата {chat['title']}..."
    )
    
    invite_link, error = await client_manager.get_chat_invite_link(account['phone'], chat['chat_id'])
    
    if not invite_link:
        await callback.message.edit_text(
            f"❌ Не удалось получить инвайт-ссылку: {error}",
            reply_markup=target_chat_actions_keyboard(chat_id)
        )
        await callback.answer()
        return
    
    kb = InlineKeyboardBuilder()
    kb.button(text="🔙 Назад к деталям чата", callback_data=f"target_chat:{chat_id}")
    kb.button(text="🔙 К списку чатов", callback_data="target_chats")
    kb.button(text="🔙 В главное меню", callback_data="main_menu")
    kb.adjust(1)
    
    await callback.message.edit_text(
        f"✅ Инвайт-ссылка для чата {chat['title']}:\n\n"
        f"{invite_link}\n\n"
        f"Вы можете скопировать эту ссылку и отправить её пользователям.",
        reply_markup=kb.as_markup()
    )
    await callback.answer("Ссылка успешно получена")


@router.callback_query(F.data.startswith("change_chat_owner:"))
async def callback_change_chat_owner(callback: CallbackQuery, state: FSMContext):
    """Handler for changing the owner of a chat"""
    chat_id = int(callback.data.split(':')[1])
    chat = db.get_target_chat(chat_id)
    
    if not chat:
        await callback.message.edit_text(
            "❌ Чат не найден.",
            reply_markup=target_chats_keyboard()
        )
        await callback.answer()
        return
    
    accounts = db.get_accounts(status='active')
    if not accounts:
        await callback.message.edit_text(
            "❌ Нет доступных аккаунтов.\n"
            "Добавьте хотя бы один активный аккаунт.",
            reply_markup=target_chat_actions_keyboard(chat_id)
        )
        await callback.answer()
        return
    
    await state.set_state(TargetChatStates.waiting_for_account_selection)
    await state.update_data(change_owner_chat_id=chat_id)
    
    await callback.message.edit_text(
        f"👤 Выберите нового владельца для чата {chat['title']}:",
        reply_markup=choose_account_keyboard(accounts)
    )
    await callback.answer()
