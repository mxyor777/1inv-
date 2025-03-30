from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
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
async def open_lzt_market_menu(call: CallbackQuery):
    await call.message.edit_text(
        text='<b>Это меню для управления автопокупкой на LZT MARKET:</b>',
        reply_markup=lzt_menu_keyboard()
    )

@router.callback_query(F.data == 'change_lzt_token')
async def change_lzt_token(call: CallbackQuery, state: FSMContext):
    await call.message.edit_text('<b>Введите токен LZT:</b>', reply_markup=back_button('lzt_market'))
    await state.set_state(StartLztAutobuyingStates.lzt_token)

@router.message(StartLztAutobuyingStates.lzt_token)
async def get_lzt_token(message: Message, state: FSMContext):
    token = message.text

    lolz_api = LolzApi(token)
    token_validated = await lolz_api.validate_token()

    if not token_validated:
        return await message.answer(
            '<b>Токен неверный или у Вас недостаточно привилегий!</b>',
            reply_markup=back_button('main_menu')
        )

    await message.delete()

    with open('data/lzt_token.txt', 'w', encoding='utf-8') as f:
        f.write(token)

    await message.answer('<b>Токен успешно сменен!</b>', reply_markup=back_button('lzt_market'))

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
    await call.message.edit_text('<b>Напишите через пробел минимальную сумму и максимальную:</b>', reply_markup=back_button('lzt_market'))
    await state.set_state(StartLztAutobuyingStates.price_limits)

@router.message(StartLztAutobuyingStates.price_limits)
async def get_price_limits(message: Message, state: FSMContext):
    price_limits = message.text.split()

    if not all([part.isnumeric() for part in price_limits]):
        return await message.answer(
            '<b>Вы неправильно указали границы прайса!</b>',
            reply_markup=back_button('lzt_market')
        )

    await state.update_data(price_limits=price_limits)

    await message.answer('<b>Напишите кол-во дней отлеги:</b>')
    await state.set_state(StartLztAutobuyingStates.expectation_days)

@router.message(StartLztAutobuyingStates.expectation_days)
async def get_expectation_days(message: Message, state: FSMContext):
    expectation_days = message.text

    if not expectation_days.isnumeric():
        return await message.answer(
            '<b>Вы неправильно указали кол-во дней!</b>',
            reply_markup=back_button('lzt_market')
        )

    await state.update_data(expectation_days=expectation_days)

    await message.answer('<b>Напишите кол-во покупаемых аккаунтов:</b>')
    await state.set_state(StartLztAutobuyingStates.count)

@router.message(StartLztAutobuyingStates.count)
async def get_count(message: Message, state: FSMContext):
    accs_count = message.text

    if not accs_count.isnumeric():
        return await message.answer(
            '<b>Вы неправильно указали кол-во!</b>',
            reply_markup=back_button('lzt_market')
        )

    await state.update_data(count=accs_count)

    await message.answer('<b>Выберите происхождение аккаунтов:</b>', reply_markup=accounts_origin_keyboard())
    await state.set_state(StartLztAutobuyingStates.origin)

@router.callback_query(F.data.startswith('pick_acc_origin:'), StartLztAutobuyingStates.origin)
async def get_origin(call: CallbackQuery, state: FSMContext):
    origin = call.data.split(':')[1]
    await state.update_data(origin=origin)

    await call.message.edit_text('<b>Выберите страну аккаунта:</b>', reply_markup=countries_keyboard())
    await state.set_state(StartLztAutobuyingStates.country)

@router.callback_query(F.data.startswith('country_page:'), StartLztAutobuyingStates.country)
async def handle_country_pagination(call: CallbackQuery, state: FSMContext):
    page = int(call.data.split(':')[1])
    await call.message.edit_text('<b>Выберите страну аккаунта:</b>', reply_markup=countries_keyboard(page))

@router.callback_query(F.data.startswith('select_country:'), StartLztAutobuyingStates.country)
async def select_country(call: CallbackQuery, state: FSMContext):
    country_code = call.data.split(':')[1]
    await state.update_data(country=country_code)

    state_data = await state.get_data()

    finally_text = f"""<b>
Вот вся заполненная информация:

TOKEN: скрыто
Лимиты прайса: {state_data['price_limits'][0]}₽ - {state_data['price_limits'][1]}₽
Кол-во: {state_data['count']}
Отлега: {state_data['expectation_days']} дня(дней)
Происхождение аккаунтов: {state_data['origin']}
Страна аккаунтов: {state_data['country']}
</b>"""

    await call.message.edit_text(
        text=finally_text,
        reply_markup=autobuy_finally_step_keyboard()
    )

@router.message(StartLztAutobuyingStates.country)
async def get_country_fallback(message: Message, state: FSMContext):
    """Legacy handler for text input of country, redirects to keyboard selection"""
    await message.answer('<b>Пожалуйста, выберите страну из списка:</b>', reply_markup=countries_keyboard())

@router.callback_query(F.data == 'start_lzt_autobuying')
async def start_lzt_autobuying(call: CallbackQuery, state: FSMContext):
    state_data = await state.get_data()

    with open('data/lzt_token.txt', 'r', encoding='utf-8') as f:
        token = f.read()

    asyncio.create_task(
        process_buying(
            call.message, token, int(state_data['price_limits'][0]), int(state_data['price_limits'][1]),
            int(state_data['count']), state_data['origin'], state_data['country'], state_data['expectation_days']
        )
    )

    await call.message.edit_text('<b>Автобай запущен!</b>')
    await state.clear()