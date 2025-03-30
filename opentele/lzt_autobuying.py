from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from ..keyboards import lzt_menu_keyboard, back_button, accounts_origin_keyboard, autobuy_finally_step_keyboard, countries_keyboard
from autobuyer import process_buying, LolzApi, validate_account
from database import db
from config import API_ID, API_HASH
import asyncio
import time

router = Router()

class StartLztAutobuyingStates(StatesGroup):
    lzt_token = State()
    price_limits = State()
    expectation_days = State()
    count = State()
    origin = State()
    country = State()


@router.callback_query(F.data == 'lzt_market')
async def open_lzt_market_menu(call: CallbackQuery, state: FSMContext):
    # Получаем сохраненные фильтры
    filters = db.get_lzt_filters() or {
        'price_min': 0,
        'price_max': 30,
        'origin': ['fishing'],
        'country': ['ru'],
        'expectation_days': 30,
        'spam_block': 'no'
    }
    
    text = '<b>🛒 LZT MARKET</b>\n\n'
    text += '<b>Текущие фильтры:</b>\n'
    text += f'- Цена: <b>{filters["price_min"]}-{filters["price_max"]}</b> руб.\n'
    text += f'- Происхождение: <b>{", ".join(filters["origin"])}</b>\n'
    text += f'- Страна: <b>{", ".join(filters["country"])}</b>\n'
    text += f'- Отлёжка: <b>{filters["expectation_days"]}</b> дней\n'
    text += f'- Спам-блок: <b>{"Да" if filters["spam_block"] == "yes" else "Нет"}</b>\n'
    
    await call.message.edit_text(
        text=text,
        reply_markup=lzt_menu_keyboard()
    )
    await state.clear()

@router.callback_query(F.data == 'change_lzt_filters')
async def change_lzt_filters(call: CallbackQuery, state: FSMContext):
    kb = InlineKeyboardBuilder()
    kb.button(text="💲 Изменить диапазон цен", callback_data="change_lzt_price")
    kb.button(text="🔍 Изменить происхождение", callback_data="change_lzt_origin")
    kb.button(text="🌍 Изменить страну", callback_data="change_lzt_country")
    kb.button(text="⏳ Изменить отлёжку", callback_data="change_lzt_expectation")
    kb.button(text="🚫 Изменить спам-блок", callback_data="change_lzt_spam")
    kb.button(text="🔙 Назад", callback_data="lzt_market")
    kb.adjust(1)
    
    await call.message.edit_text(
        '<b>🛠️ Выберите фильтр для изменения:</b>',
        reply_markup=kb.as_markup()
    )

@router.callback_query(F.data == 'change_lzt_price')
async def change_lzt_price(call: CallbackQuery, state: FSMContext):
    await call.message.edit_text(
        '<b>💲 Введите через пробел минимальную и максимальную цену (руб.):</b>',
        reply_markup=back_button('change_lzt_filters')
    )
    await state.set_state(StartLztAutobuyingStates.price_limits)

@router.callback_query(F.data == 'change_lzt_origin')
async def change_lzt_origin(call: CallbackQuery, state: FSMContext):
    kb = InlineKeyboardBuilder()
    kb.button(text="Фишинг", callback_data="set_lzt_origin:fishing")
    kb.button(text="Брут", callback_data="set_lzt_origin:brute")
    kb.button(text="Стилер", callback_data="set_lzt_origin:stealer")
    kb.button(text="🔙 Назад", callback_data="change_lzt_filters")
    kb.adjust(1)
    
    await call.message.edit_text(
        '<b>🔍 Выберите происхождение аккаунтов:</b>',
        reply_markup=kb.as_markup()
    )

@router.callback_query(F.data.startswith('set_lzt_origin:'))
async def set_lzt_origin(call: CallbackQuery, state: FSMContext):
    origin = call.data.split(':')[1]
    
    # Сохраняем в базу данных
    filters = db.get_lzt_filters() or {}
    filters['origin'] = [origin]
    db.save_lzt_filters(filters)
    
    await call.answer(f"Происхождение установлено: {origin}")
    await change_lzt_filters(call, state)

@router.callback_query(F.data == 'change_lzt_country')
async def change_lzt_country(call: CallbackQuery, state: FSMContext):
    await call.message.edit_text(
        '<b>🌍 Выберите страну аккаунтов:</b>',
        reply_markup=countries_keyboard()
    )
    await state.set_state(StartLztAutobuyingStates.country)

@router.callback_query(F.data.startswith('country_page:'))
async def handle_country_pagination(call: CallbackQuery, state: FSMContext):
    page = int(call.data.split(':')[1])
    current_state = await state.get_state()
    
    # Проверяем состояние, чтобы правильно вернуться в меню
    if current_state == StartLztAutobuyingStates.country.state:
        await call.message.edit_text(
            '<b>🌍 Выберите страну аккаунта:</b>', 
            reply_markup=countries_keyboard(page)
        )
    else:
        # Если состояние не установлено (при изменении фильтров)
        await call.message.edit_text(
            '<b>🌍 Выберите страну аккаунтов:</b>',
            reply_markup=countries_keyboard(page)
        )
        
@router.callback_query(F.data.startswith('select_country:'))
async def select_country(call: CallbackQuery, state: FSMContext):
    country_code = call.data.split(':')[1]
    current_state = await state.get_state()
    
    # Сохраняем выбранную страну
    await state.update_data(country=country_code.lower())
    
    # Проверяем, находимся ли мы в процессе автопокупки или просто меняем фильтры
    if current_state == StartLztAutobuyingStates.country.state:
        # Процесс автопокупки
        state_data = await state.get_data()
        
        # Используем безопасное получение значений с значениями по умолчанию
        price_min = state_data.get('price_limits', [0, 30])[0] if 'price_limits' in state_data else 0
        price_max = state_data.get('price_limits', [0, 30])[1] if 'price_limits' in state_data else 30
        count = state_data.get('count', '0')
        expectation_days = state_data.get('expectation_days', 30)
        origin = state_data.get('origin', ['fishing'])
        
        finally_text = f"""<b>
Вот вся заполненная информация:

TOKEN: скрыто
Лимиты прайса: {price_min}₽ - {price_max}₽
Кол-во: {count}
Отлега: {expectation_days} дня(дней)
Происхождение аккаунтов: {origin}
Страна аккаунтов: {country_code.upper()}
</b>"""

        await call.message.edit_text(
            text=finally_text,
            reply_markup=autobuy_finally_step_keyboard()
        )
    else:
        # Изменение фильтров
        filters = db.get_lzt_filters() or {}
        filters['country'] = [country_code.lower()]
        db.save_lzt_filters(filters)
        
        await call.answer(f"Страна установлена: {country_code.upper()}")
        await change_lzt_filters(call, state)

@router.callback_query(F.data == 'change_lzt_expectation')
async def change_lzt_expectation(call: CallbackQuery, state: FSMContext):
    await call.message.edit_text(
        '<b>⏳ Введите минимальное количество дней отлёжки аккаунта:</b>',
        reply_markup=back_button('change_lzt_filters')
    )
    await state.set_state(StartLztAutobuyingStates.expectation_days)

@router.callback_query(F.data == 'change_lzt_spam')
async def change_lzt_spam(call: CallbackQuery, state: FSMContext):
    kb = InlineKeyboardBuilder()
    kb.button(text="С спам-блоком", callback_data="set_lzt_spam:yes")
    kb.button(text="Без спам-блока", callback_data="set_lzt_spam:no")
    kb.button(text="🔙 Назад", callback_data="change_lzt_filters")
    kb.adjust(1)
    
    await call.message.edit_text(
        '<b>🚫 Выберите параметр спам-блока:</b>',
        reply_markup=kb.as_markup()
    )

@router.callback_query(F.data.startswith('set_lzt_spam:'))
async def set_lzt_spam(call: CallbackQuery, state: FSMContext):
    spam = call.data.split(':')[1]
    
    # Сохраняем в базу данных
    filters = db.get_lzt_filters() or {}
    filters['spam_block'] = spam
    db.save_lzt_filters(filters)
    
    await call.answer(f"Параметр спам-блока установлен: {'Да' if spam == 'yes' else 'Нет'}")
    await change_lzt_filters(call, state)

@router.callback_query(F.data == 'show_last_bought_accounts')
async def show_last_bought_accounts(call: CallbackQuery, state: FSMContext):
    all_bought = db.get_bought_accounts()
    last_mounth_accounts = [account for account in all_bought if int(time.time() - account['added_time']) <= 2629746]

    if not last_mounth_accounts:
        return await call.message.edit_text('<b>У вас нет последних купленных аккаунтов за месяц!</b>')

    date_text = '<b>' + '\n'.join([f'{account["phone"]}(https://lzt.market/{account["item_id"]}/) - {"✅" if (await validate_account(account["phone"])) else "❌"}' for account in last_mounth_accounts]) + '</b>'
    await call.message.edit_text(date_text, reply_markup=back_button('lzt_market'))

@router.callback_query(F.data == 'lzt_autobuying')
async def lzt_autobuying(call: CallbackQuery, state: FSMContext):
    # Получаем текущие фильтры из базы данных
    filters = db.get_lzt_filters() or {
        'price_min': 0,
        'price_max': 30,
        'origin': ['fishing'],
        'country': ['ru'],
        'expectation_days': 30,
        'spam_block': 'no'
    }
    
    # Сохраняем фильтры в состоянии
    filters_dict = dict(filters) if filters else {}
    await state.update_data({
        'price_limits': [filters_dict.get('price_min', 0), filters_dict.get('price_max', 30)],
        'origin': filters_dict.get('origin', ['fishing']),
        'country': filters_dict.get('country', ['ru']),
        'expectation_days': filters_dict.get('expectation_days', 30),
    })
    
    # Строим текст с текущими фильтрами
    text = "<b>🚀 Запуск автопокупки</b>\n\n"
    text += "<b>Текущие фильтры:</b>\n"
    text += f"- Цена: <b>{filters_dict.get('price_min', 0)}-{filters_dict.get('price_max', 30)}</b> руб.\n"
    text += f"- Происхождение: <b>{', '.join(filters_dict.get('origin', ['fishing']))}</b>\n"
    text += f"- Страна: <b>{', '.join(filters_dict.get('country', ['ru']))}</b>\n"
    text += f"- Отлёжка: <b>{filters_dict.get('expectation_days', 30)}</b> дней\n"
    text += f"- Спам-блок: <b>{'Да' if filters_dict.get('spam_block') == 'yes' else 'Нет'}</b>\n\n"
    
    text += "<b>Введите количество аккаунтов для покупки:</b>"
    
    await call.message.edit_text(
        text,
        reply_markup=back_button('lzt_market')
    )
    await state.set_state(StartLztAutobuyingStates.count)

@router.message(StartLztAutobuyingStates.count)
async def get_count(message: Message, state: FSMContext):
    try:
        accs_count = int(message.text.strip())
        
        if accs_count <= 0:
            return await message.answer(
                '<b>❌ Количество аккаунтов должно быть положительным числом!</b>',
                reply_markup=back_button('lzt_market')
            )
        
        await state.update_data(count=accs_count)
        state_data = await state.get_data()
        
        # Формируем сообщение с информацией для подтверждения
        finally_text = f"""<b>
Информация для автопокупки:

TOKEN: скрыто
Лимиты цены: {state_data['price_limits'][0]}₽ - {state_data['price_limits'][1]}₽
Кол-во аккаунтов: {accs_count}
Отлёжка: {state_data['expectation_days']} дня(дней)
Происхождение: {', '.join(state_data['origin'])}
Страна: {', '.join([country.upper() for country in state_data['country']])}
</b>"""

        await message.answer(
            finally_text,
            reply_markup=autobuy_finally_step_keyboard()
        )
    
    except ValueError:
        await message.answer(
            '<b>❌ Пожалуйста, введите число!</b>',
            reply_markup=back_button('lzt_market')
        )

@router.callback_query(F.data.startswith('pick_acc_origin:'), StartLztAutobuyingStates.origin)
async def get_origin(call: CallbackQuery, state: FSMContext):
    origin = call.data.split(':')[1]
    await state.update_data(origin=origin)

    await call.message.edit_text('<b>Выберите страну аккаунта:</b>', reply_markup=countries_keyboard())
    await state.set_state(StartLztAutobuyingStates.country)

@router.message(StartLztAutobuyingStates.country)
async def get_country_fallback(message: Message, state: FSMContext):
    """Legacy handler for text input of country, redirects to keyboard selection"""
    await message.answer('<b>Пожалуйста, выберите страну из списка:</b>', reply_markup=countries_keyboard())

@router.callback_query(F.data == 'start_lzt_autobuying')
async def start_lzt_autobuying(call: CallbackQuery, state: FSMContext):
    state_data = await state.get_data()
    
    # Получаем текущие фильтры
    filters = db.get_lzt_filters() or {}
    
    with open('data/lzt_token.txt', 'r', encoding='utf-8') as f:
        token = f.read()
    
    # Используем данные из состояния, которые были загружены при запуске автопокупки
    price_min = state_data.get('price_limits', [0, 30])[0]
    price_max = state_data.get('price_limits', [0, 30])[1]
    origin = state_data.get('origin', ['fishing'])
    country = state_data.get('country', ['ru'])
    expectation_days = state_data.get('expectation_days', 30)
    count = state_data.get('count')
    
    # Проверка на None и установка значения по умолчанию
    if count is None:
        count = 1
        await call.answer("Количество аккаунтов не указано, будет куплен 1 аккаунт")
    
    asyncio.create_task(
        process_buying(
            call.message, token, price_min, price_max,
            int(count), origin, country, expectation_days
        )
    )
    
    await call.message.edit_text('<b>✅ Автобай запущен!</b>')
    await state.clear()