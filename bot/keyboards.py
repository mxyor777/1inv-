from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from database import db


def main_menu_keyboard():
    """Create main menu keyboard"""
    kb = InlineKeyboardBuilder()
    kb.button(text="👤 АККАУНТЫ", callback_data="accounts")
    kb.button(text="📊 ПАРСИНГ", callback_data="parsing")
    kb.button(text="🔄 ИНВАЙТИНГ", callback_data="inviting")
    kb.button(text="⚙️ НАСТРОЙКИ ИНВАЙТИНГА", callback_data="invite_settings")
    kb.button(text="🛒 LZT MARKET", callback_data="lzt_market")
    kb.adjust(2, 2, 1)
    return kb.as_markup()


def accounts_menu_keyboard(accounts=None):
    """Create accounts menu keyboard"""
    kb = InlineKeyboardBuilder()
    
    if accounts:
        for acc in accounts:
            phone = acc['phone']
            status = "✅" if acc['status'] == 'active' else "❌"
            kb.button(text=f"{acc['first_name']} {acc['last_name']} {status}", callback_data=f"account:{acc['id']}")
    
    kb.button(text="➕ Добавить аккаунты", callback_data="add_accounts")
    kb.button(text="🔙 В главное меню", callback_data="main_menu")
    kb.adjust(1)
    return kb.as_markup()

def lzt_menu_keyboard():
    """Create lzt menu keyboard"""
    kb = InlineKeyboardBuilder()
    kb.button(text="Запустить автопокупку", callback_data="lzt_autobuying")
    kb.button(text="Последние купленные аккаунты", callback_data="show_last_bought_accounts")
    kb.button(text="Изменить токен", callback_data="change_lzt_token")
    kb.button(text="🔙 В главное меню", callback_data="main_menu")
    kb.adjust(2, 1, 1)
    return kb.as_markup()

def accounts_origin_keyboard():
    """Create origins keyboard"""
    kb = InlineKeyboardBuilder()
    kb.button(text="Фишинг", callback_data="pick_acc_origin:fishing")
    kb.button(text="Брут", callback_data="pick_acc_origin:brute")
    kb.button(text="Стилер", callback_data="pick_acc_origin:stealer")
    kb.adjust(1, 1, 1)
    return kb.as_markup()

def autobuy_finally_step_keyboard():
    kb = InlineKeyboardBuilder()
    kb.button(text="Запустить автобай", callback_data="start_lzt_autobuying")
    kb.button(text="Заполнить заново", callback_data="lzt_autobuying")
    kb.adjust(1, 1)
    return kb.as_markup()

def account_settings_keyboard(account_id):
    """Create account settings keyboard"""
    kb = InlineKeyboardBuilder()
    kb.button(text="✏️ Изменить имя", callback_data=f"edit_name:{account_id}")
    kb.button(text="🔤 Изменить юзернейм", callback_data=f"edit_username:{account_id}")
    kb.button(text="💬 Изменить описание (био)", callback_data=f"set_status:{account_id}")
    kb.button(text="🔐 Настройка прокси", callback_data=f"proxy_settings:{account_id}")
    kb.button(text="🗑️ Удалить аккаунт", callback_data=f"delete_account:{account_id}")
    kb.button(text="🔙 Назад", callback_data="accounts")
    kb.button(text="🔙 В главное меню", callback_data="main_menu")
    kb.adjust(1)
    return kb.as_markup()


def proxy_settings_keyboard(account_id):
    """Create proxy settings keyboard"""
    kb = InlineKeyboardBuilder()
    kb.button(text="➕ Добавить/изменить прокси", callback_data=f"add_proxy:{account_id}")
    kb.button(text="❌ Удалить прокси", callback_data=f"remove_proxy:{account_id}")
    kb.button(text="🔙 Назад", callback_data=f"account:{account_id}")
    kb.adjust(1)
    return kb.as_markup()


def source_chats_keyboard(chats=None):
    """Create source chats menu keyboard"""
    kb = InlineKeyboardBuilder()
    
    if chats:
        for chat in chats:
            title = chat['title']
            members = f"{chat['parsed_members']}/{chat['total_members']}"
            
            account_info = ""
            if 'account_first_name' in chat or 'account_last_name' in chat:
                first_name = chat['account_first_name'] if 'account_first_name' in chat else ''
                last_name = chat['account_last_name'] if 'account_last_name' in chat else ''
                name = f"{first_name} {last_name}".strip()
                if name:
                    account_info = f"👤 {name} - "
                elif 'account_phone' in chat:
                    account_info = f"👤 {chat['account_phone']} - "
            
            kb.button(
                text=f"{account_info}{title} ({members})", 
                callback_data=f"source_chat:{chat['id']}"
            )
    
    kb.button(text="➕ Добавить чат", callback_data="add_source_chat")
    kb.button(text="🔙 В главное меню", callback_data="main_menu")
    kb.adjust(1)
    return kb.as_markup()


def source_chat_actions_keyboard(chat_id):
    """Create source chat actions keyboard"""
    kb = InlineKeyboardBuilder()
    kb.button(text="🗑️ Удалить чат", callback_data=f"delete_source_chat:{chat_id}")
    kb.button(text="🔙 Назад", callback_data="source_chats")
    kb.button(text="🔙 В главное меню", callback_data="main_menu")
    kb.adjust(1)
    return kb.as_markup()


def target_chats_keyboard(chats=None):
    """Create target chats menu keyboard"""
    kb = InlineKeyboardBuilder()
    
    if chats:
        for chat in chats:
            title = chat['title']
            
            account_info = ""
            if 'account_first_name' in chat or 'account_last_name' in chat:
                first_name = chat['account_first_name'] if 'account_first_name' in chat else ''
                last_name = chat['account_last_name'] if 'account_last_name' in chat else ''
                name = f"{first_name} {last_name}".strip()
                if name:
                    account_info = f"👤 {name} - "
                elif 'account_phone' in chat:
                    account_info = f"👤 {chat['account_phone']} - "
            
            kb.button(
                text=f"{account_info}{title}", 
                callback_data=f"target_chat:{chat['id']}"
            )
    
    kb.button(text="➕ Добавить чат", callback_data="add_target_chat")
    kb.button(text="🔙 В главное меню", callback_data="main_menu")
    kb.adjust(1)
    return kb.as_markup()


def target_chat_actions_keyboard(chat_id, chat_type="invite"):
    """Create target chat actions keyboard"""
    kb = InlineKeyboardBuilder()
    
    # В зависимости от типа чата показываем соответствующую кнопку
    if chat_type == "invite":
        kb.button(text="🚀 НАЧАТЬ/ПРОДОЛЖИТЬ ИНВАЙТИНГ", callback_data=f"add_users_to_chat:{chat_id}")
    elif chat_type == "parse":
        kb.button(text="🚀 НАЧАТЬ/ПРОДОЛЖИТЬ ПАРСИНГ", callback_data=f"start_parse_chat:{chat_id}")
        
    kb.button(text="🗑️ УДАЛИТЬ ЧАТ", callback_data=f"delete_target_chat:{chat_id}")
    kb.button(text="🔙 НАЗАД", callback_data="target_chats")
    kb.button(text="🔙 ГЛАВНОЕ МЕНЮ", callback_data="main_menu")
    kb.adjust(1)
    return kb.as_markup()


def parsing_keyboard(parsed_files=None):
    """Create parsing menu keyboard"""
    kb = InlineKeyboardBuilder()
    
    if parsed_files:
        for file in parsed_files:
            name = file['file_name'].split('_')[0]
            count = file['total_users']
            kb.button(text=f"{name} ({count})", callback_data=f"parsed_file:{file['id']}")
    
    kb.button(text="🔙 В главное меню", callback_data="main_menu")
    kb.adjust(1)
    return kb.as_markup()


def parsed_file_actions_keyboard(file_id):
    """Create parsed file actions keyboard"""
    kb = InlineKeyboardBuilder()
    kb.button(text="📣 Использовать для инвайтинга", callback_data=f"use_for_inviting:{file_id}")
    kb.button(text="🗑️ Удалить файл", callback_data=f"delete_parsed_file:{file_id}")
    kb.button(text="🔙 Назад", callback_data="parsing")
    kb.button(text="🔙 В главное меню", callback_data="main_menu")
    kb.adjust(1)
    return kb.as_markup()


def invite_settings_keyboard():
    """Create invite settings menu keyboard"""
    kb = InlineKeyboardBuilder()
    kb.button(text="⏱️ ИНТЕРВАЛ МЕЖДУ ПРИГЛАШЕНИЯМИ", callback_data="set_invite_interval")
    kb.button(text="📊 МАКСИМУМ ПРИГЛАШЕНИЙ ЗА 12Ч", callback_data="set_max_invites_12h")
    kb.button(text="📊 МАКСИМУМ ПРИГЛАШЕНИЙ ЗА 24Ч", callback_data="set_max_invites_24h")
    kb.button(text="🔙 ГЛАВНОЕ МЕНЮ", callback_data="main_menu")
    kb.adjust(1)
    return kb.as_markup()


def back_button(target="cancel"):
    """Create back button keyboard"""
    kb = InlineKeyboardBuilder()
    kb.button(text="🔙 Назад", callback_data=target)
    return kb.as_markup()


def back_to_menu_button():
    """Create back to menu button keyboard"""
    kb = InlineKeyboardBuilder()
    kb.button(text="🔙 В главное меню", callback_data="main_menu")
    return kb.as_markup()


def skip_button():
    """Create skip button keyboard"""
    kb = InlineKeyboardBuilder()
    kb.button(text="⏭️ Пропустить", callback_data="skip")
    kb.button(text="🔙 Назад", callback_data="cancel")
    kb.adjust(1)
    return kb.as_markup()


def choose_account_keyboard(accounts):
    """Create choose account keyboard"""
    kb = InlineKeyboardBuilder()
    
    for acc in accounts:
        name = f"{acc['first_name']} {acc['last_name']}"
        if not name.strip():
            name = acc['phone']
        kb.button(text=name, callback_data=f"select_account:{acc['id']}")
    
    kb.button(text="🔙 Отмена", callback_data="cancel")
    kb.adjust(1)
    return kb.as_markup()


def choose_target_chat_keyboard(chats):
    """Create choose target chat keyboard"""
    kb = InlineKeyboardBuilder()
    
    for chat in chats:
        kb.button(text=chat['title'], callback_data=f"select_target_chat:{chat['id']}")
    
    kb.button(text="➕ Создать новый чат", callback_data="create_new_chat")
    kb.button(text="🔙 Отмена", callback_data="cancel")
    kb.adjust(1)
    return kb.as_markup()


def create_chat_keyboard():
    """Create keyboard for chat creation options"""
    kb = InlineKeyboardBuilder()
    kb.button(text="➕ Создать новый чат для инвайтинга", callback_data="confirm_create_chat")
    kb.button(text="🔙 Назад", callback_data="start_new_inviting")
    kb.adjust(1)
    return kb.as_markup()


def yes_no_keyboard(action, item_id):
    """Create yes/no confirmation keyboard"""
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Да", callback_data=f"confirm_{action}:{item_id}")
    kb.button(text="❌ Нет", callback_data="cancel")
    kb.adjust(2)
    return kb.as_markup()


def inviting_keyboard():
    """Create inviting menu keyboard"""
    kb = InlineKeyboardBuilder()
    kb.button(text="🔙 Назад к инвайтингу", callback_data="inviting")
    kb.button(text="🔙 В главное меню", callback_data="main_menu")
    kb.adjust(1)
    return kb.as_markup()


def active_invites_keyboard(invites=None):
    """Create active invites keyboard"""
    kb = InlineKeyboardBuilder()
    
    if invites:
        for invite in invites:
            invite_id = invite['id']
            
            if invite['active']:
                kb.button(text=f"⏸ Приостановить", callback_data=f"pause_invite:{invite_id}")
            else:
                kb.button(text=f"▶️ Возобновить", callback_data=f"resume_invite:{invite_id}")
                
            kb.button(text=f"🗑️ Удалить", callback_data=f"delete_invite:{invite_id}")
    
    kb.button(text="🔙 В главное меню", callback_data="main_menu")
    kb.adjust(2, 1)
    return kb.as_markup()

def countries_keyboard(page=0):
    """Create countries selection keyboard with pagination"""
    kb = InlineKeyboardBuilder()
    
    countries = [
        {"code": "RU", "emoji": "🇷🇺", "name": "Россия"},
        {"code": "IN", "emoji": "🇮🇳", "name": "Индия"},
        {"code": "ID", "emoji": "🇮🇩", "name": "Индонезия"},
        {"code": "CO", "emoji": "🇨🇴", "name": "Колумбия"},
        {"code": "US", "emoji": "🇺🇸", "name": "США"},
        {"code": "ZA", "emoji": "🇿🇦", "name": "Южная Африка"},
        {"code": "MM", "emoji": "🇲🇲", "name": "Мьянма"},
        {"code": "YE", "emoji": "🇾🇪", "name": "Йемен"},
        {"code": "CL", "emoji": "🇨🇱", "name": "Чили"},
        {"code": "BD", "emoji": "🇧🇩", "name": "Бангладеш"},
        {"code": "AR", "emoji": "🇦🇷", "name": "Аргентина"},
        {"code": "ES", "emoji": "🇪🇸", "name": "Испания"},
        {"code": "BR", "emoji": "🇧🇷", "name": "Бразилия"},
        {"code": "CA", "emoji": "🇨🇦", "name": "Канада"},
        {"code": "UZ", "emoji": "🇺🇿", "name": "Узбекистан"},
        {"code": "NG", "emoji": "🇳🇬", "name": "Нигерия"},
        {"code": "BY", "emoji": "🇧🇾", "name": "Беларусь"},
        {"code": "PL", "emoji": "🇵🇱", "name": "Польша"},
        {"code": "PH", "emoji": "🇵🇭", "name": "Филиппины"},
        {"code": "UA", "emoji": "🇺🇦", "name": "Украина"},
        {"code": "EG", "emoji": "🇪🇬", "name": "Египет"},
        {"code": "KE", "emoji": "🇰🇪", "name": "Кения"},
        {"code": "AO", "emoji": "🇦🇴", "name": "Ангола"},
        {"code": "TR", "emoji": "🇹🇷", "name": "Турция"},
        {"code": "MX", "emoji": "🇲🇽", "name": "Мексика"},
        {"code": "KZ", "emoji": "🇰🇿", "name": "Казахстан"},
        {"code": "ET", "emoji": "🇪🇹", "name": "Эфиопия"},
        {"code": "DZ", "emoji": "🇩🇿", "name": "Алжир"},
        {"code": "CM", "emoji": "🇨🇲", "name": "Камерун"},
        {"code": "IR", "emoji": "🇮🇷", "name": "Иран"}
    ]
    
    items_per_page = 9
    total_pages = (len(countries) + items_per_page - 1) // items_per_page
    
    start_idx = page * items_per_page
    end_idx = min(start_idx + items_per_page, len(countries))
    
    for country in countries[start_idx:end_idx]:
        kb.button(
            text=f"{country['emoji']} {country['name']}", 
            callback_data=f"select_country:{country['code']}"
        )
    
    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton(
            text="⬅️ Назад", 
            callback_data=f"country_page:{page-1}"
        ))
    
    if page < total_pages - 1:
        nav_buttons.append(InlineKeyboardButton(
            text="Вперед ➡️", 
            callback_data=f"country_page:{page+1}"
        ))
    
    nav_buttons.append(InlineKeyboardButton(
        text="🔙 Назад", 
        callback_data="lzt_market"
    ))
    
    kb.adjust(3, 3, 3)
    
    if nav_buttons:
        for button in nav_buttons:
            kb.row(button)
    
    return kb.as_markup()

def parsing_menu_keyboard():
    """Create parsing submenu keyboard"""
    kb = InlineKeyboardBuilder()
    kb.button(text="🔍 ЧАТЫ ДЛЯ ПАРСИНГА", callback_data="source_chats")
    kb.button(text="📄 РЕЗУЛЬТАТЫ ПАРСИНГА", callback_data="parsing_results")
    kb.button(text="📂 ПРОСМОТРЕТЬ ФАЙЛЫ", callback_data="view_parsed_files")
    kb.button(text="🔙 ГЛАВНОЕ МЕНЮ", callback_data="main_menu")
    kb.adjust(1)
    return kb.as_markup()

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
    
    kb.button(text="📣 ЧАТЫ ДЛЯ ИНВАЙТА", callback_data="target_chats")
    kb.button(text="➕ НАЧАТЬ НОВЫЙ ИНВАЙТИНГ", callback_data="start_new_inviting")
    kb.button(text="🔙 ГЛАВНОЕ МЕНЮ", callback_data="main_menu")
    kb.adjust(1)
    return kb.as_markup() 