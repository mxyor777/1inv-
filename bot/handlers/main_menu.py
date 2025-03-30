from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext

from ..keyboards import main_menu_keyboard, parsing_menu_keyboard, inviting_menu_keyboard
from autobuyer import LolzApi

router = Router()

@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    # lolz_api = LolzApi(token='eyJ0eXAiOiJKV1QiLCJhbGciOiJSUzUxMiJ9.eyJzdWIiOjQ0NTI1NTUsImlzcyI6Imx6dCIsImV4cCI6MCwiaWF0IjoxNzQzMTUwNjgzLCJqdGkiOjc1ODk1Nywic2NvcGUiOiJiYXNpYyByZWFkIHBvc3QgY29udmVyc2F0ZSBwYXltZW50IGludm9pY2UgbWFya2V0In0.hLP2Br55iHixzWMvV482vII5nDzNdyVouL1XNTlymGCLnKAI1E0jRLXmMwOpZbMYVzjCXoN7fHgkYXAAyjmSFEp2qvw9xSYvZ7wdU6bR4-gXC8jpZ3yX06q48uiPbWFheEs6LRUZxJ96Bp0tmySIZ17gSw8pVLVGoPj3kmmNscI')
    # await lolz_api.search_telegram(pmin = 0, pmax = 30, origin = ['fishing'], country = ['ru'])

    await state.clear()
    await message.answer(
        "👋 Добро пожаловать в лучший инвайтер/парсер для Telegram!",
        reply_markup=main_menu_keyboard()
    )

@router.message(Command("menu"))
async def cmd_menu(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "📋 Главное меню:",
        reply_markup=main_menu_keyboard()
    )

@router.callback_query(F.data == "main_menu")
async def callback_main_menu(callback: CallbackQuery, state: FSMContext):
    await state.clear()

    try:
        await callback.message.edit_text(
            "📋 Главное меню:",
            reply_markup=main_menu_keyboard()
        )
    except Exception as e:
        if "message is not modified" not in str(e):
            raise

    await callback.answer()

@router.callback_query(F.data == "cancel")
async def callback_cancel(callback: CallbackQuery, state: FSMContext):
    current_state = await state.get_state()
    stored_data = await state.get_data()
    
    # Получаем информацию о предыдущем меню, если она была сохранена
    previous_menu = stored_data.get('previous_menu', 'main_menu')
    
    await state.clear()
    
    # В зависимости от предыдущего меню, возвращаемся туда
    if previous_menu == 'accounts':
        try:
            await callback.message.edit_text(
                "👤 АККАУНТЫ",
                reply_markup=main_menu_keyboard(),
                parse_mode="HTML"
            )
        except Exception as e:
            if "message is not modified" not in str(e):
                raise
    elif previous_menu == 'parsing':
        try:
            await callback.message.edit_text(
                "📊 ПАРСИНГ\n\nВыберите действие:",
                reply_markup=parsing_menu_keyboard(),
                parse_mode="HTML"
            )
        except Exception as e:
            if "message is not modified" not in str(e):
                raise
    elif previous_menu == 'inviting':
        try:
            await callback.message.edit_text(
                "🔄 ИНВАЙТИНГ\n\nВыберите действие:",
                reply_markup=inviting_menu_keyboard(),
                parse_mode="HTML"
            )
        except Exception as e:
            if "message is not modified" not in str(e):
                raise
    else:
        # По умолчанию возвращаемся в главное меню
        try:
            await callback.message.edit_text(
                "❌ Операция отменена.\n\n📋 ГЛАВНОЕ МЕНЮ:",
                reply_markup=main_menu_keyboard(),
                parse_mode="HTML"
            )
        except Exception as e:
            if "message is not modified" not in str(e):
                raise
    
    await callback.answer() 