from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from database import db
from bot.keyboards import (
    invite_settings_keyboard,
    back_button,
    main_menu_keyboard
)

router = Router()

class InviteSettingsStates(StatesGroup):
    waiting_for_interval_min = State()
    waiting_for_interval_max = State()
    waiting_for_max_12h = State()
    waiting_for_max_24h = State()


@router.callback_query(F.data == "invite_settings")
async def callback_invite_settings(callback: CallbackQuery, state: FSMContext):
    await state.update_data(previous_menu='invite_settings')
    await state.clear()
    
    settings = db.get_invite_settings()
    
    min_interval = settings['min_interval_seconds'] if 'min_interval_seconds' in settings else 30
    max_interval = settings['max_interval_seconds'] if 'max_interval_seconds' in settings else 60
    max_invites_12h = settings['max_invites_12h'] if 'max_invites_12h' in settings else 25
    max_invites_24h = settings['max_invites_24h'] if 'max_invites_24h' in settings else 40
    
    text = "⚙️ НАСТРОЙКИ ИНВАЙТИНГА\n\n"
    text += "Текущие настройки:\n"
    text += f"⏱️ Интервал между приглашениями: {min_interval} - {max_interval} сек.\n"
    text += f"📊 Максимум приглашений за 12ч: {max_invites_12h}\n"
    text += f"📊 Максимум приглашений за 24ч: {max_invites_24h}\n\n"
    
    text += "⚠️ РЕКОМЕНДУЕМЫЕ БЕЗОПАСНЫЕ НАСТРОЙКИ:\n"
    text += "⏱️ Интервал: 35-70 сек.\n"
    text += "📊 12ч макс.: 25 приглашений\n"
    text += "📊 24ч макс.: 40 приглашений\n\n"
    text += "Эти настройки помогут избежать блокировок аккаунтов и обеспечат максимально безопасную работу."
    
    try:
        await callback.message.edit_text(
            text,
            reply_markup=invite_settings_keyboard(),
            parse_mode="HTML"
        )
    except Exception as e:
        if "message is not modified" not in str(e):
            raise
    
    await callback.answer()


@router.callback_query(F.data == "set_invite_interval")
async def callback_set_invite_interval(callback: CallbackQuery, state: FSMContext):
    await state.set_state(InviteSettingsStates.waiting_for_interval_min)
    
    await callback.message.edit_text(
        "⏱️ Настройка интервала между приглашениями\n\n"
        "Введите минимальное значение интервала в секундах (рекомендуется не менее 30):",
        reply_markup=back_button()
    )
    await callback.answer()


@router.message(InviteSettingsStates.waiting_for_interval_min)
async def handle_interval_min(message: Message, state: FSMContext):
    try:
        interval_min = int(message.text.strip())
        if interval_min < 1:
            await message.answer(
                "⚠️ Значение слишком маленькое. Минимальный интервал должен быть не менее 1 секунды."
            )
            return
        
        await state.update_data(interval_min=interval_min)
        await state.set_state(InviteSettingsStates.waiting_for_interval_max)
        
        await message.answer(
            f"✅ Установлено минимальное значение интервала: {interval_min} секунд\n\n"
            f"Теперь введите максимальное значение интервала в секундах (должно быть больше {interval_min}):",
            reply_markup=back_button()
        )
    except ValueError:
        await message.answer(
            "❌ Пожалуйста, введите число."
        )


@router.message(InviteSettingsStates.waiting_for_interval_max)
async def handle_interval_max(message: Message, state: FSMContext):
    try:
        data = await state.get_data()
        interval_min = data.get('interval_min')
        
        interval_max = int(message.text.strip())
        if interval_max <= interval_min:
            await message.answer(
                f"⚠️ Максимальное значение должно быть больше минимального ({interval_min})."
            )
            return
        
        db.update_invite_settings(
            invite_interval_min=interval_min,
            invite_interval_max=interval_max
        )
        
        settings = db.get_invite_settings()
        
        text = "✅ Настройки интервала обновлены!\n\n"
        text += "⚙️ Настройки инвайтинга\n\n"
        text += f"Интервал между приглашениями: {settings['invite_interval_min']}-{settings['invite_interval_max']} секунд\n"
        text += f"Максимум приглашений за 12ч: {settings['max_invites_per_12h']}\n"
        text += f"Максимум приглашений за 24ч: {settings['max_invites_per_24h']}\n\n"
        text += "Выберите параметр для изменения:"
        
        await message.answer(
            text,
            reply_markup=invite_settings_keyboard()
        )
        await state.clear()
    except ValueError:
        await message.answer(
            "❌ Пожалуйста, введите число."
        )


@router.callback_query(F.data == "set_max_invites_12h")
async def callback_set_max_invites_12h(callback: CallbackQuery, state: FSMContext):
    await state.set_state(InviteSettingsStates.waiting_for_max_12h)
    
    settings = db.get_invite_settings()
    max_24h = settings['max_invites_per_24h']
    
    await callback.message.edit_text(
        "📊 Настройка максимального количества приглашений за 12 часов\n\n"
        f"Текущее значение: {settings['max_invites_per_12h']}\n"
        f"Значение для 24 часов: {max_24h}\n\n"
        "Введите новое значение (рекомендуется не более 40):",
        reply_markup=back_button()
    )
    await callback.answer()


@router.message(InviteSettingsStates.waiting_for_max_12h)
async def handle_max_12h(message: Message, state: FSMContext):
    try:
        max_invites_12h = int(message.text.strip())
        if max_invites_12h < 1:
            await message.answer(
                "⚠️ Значение должно быть положительным числом."
            )
            return
        
        settings = db.get_invite_settings()
        if max_invites_12h > settings['max_invites_per_24h']:
            await message.answer(
                f"⚠️ Значение для 12 часов не может быть больше значения для 24 часов ({settings['max_invites_per_24h']})."
            )
            return
        
        db.update_invite_settings(
            max_invites_per_12h=max_invites_12h
        )
        
        updated_settings = db.get_invite_settings()
        
        text = "✅ Настройки максимального количества приглашений за 12 часов обновлены!\n\n"
        text += "⚙️ Настройки инвайтинга\n\n"
        text += f"Интервал между приглашениями: {updated_settings['invite_interval_min']}-{updated_settings['invite_interval_max']} секунд\n"
        text += f"Максимум приглашений за 12ч: {updated_settings['max_invites_per_12h']}\n"
        text += f"Максимум приглашений за 24ч: {updated_settings['max_invites_per_24h']}\n\n"
        text += "Выберите параметр для изменения:"
        
        await message.answer(
            text,
            reply_markup=invite_settings_keyboard()
        )
        await state.clear()
    except ValueError:
        await message.answer(
            "❌ Пожалуйста, введите число."
        )


@router.callback_query(F.data == "set_max_invites_24h")
async def callback_set_max_invites_24h(callback: CallbackQuery, state: FSMContext):
    await state.set_state(InviteSettingsStates.waiting_for_max_24h)
    
    settings = db.get_invite_settings()
    max_12h = settings['max_invites_per_12h']
    
    await callback.message.edit_text(
        "📊 Настройка максимального количества приглашений за 24 часа\n\n"
        f"Текущее значение: {settings['max_invites_per_24h']}\n"
        f"Значение для 12 часов: {max_12h}\n\n"
        "Введите новое значение (рекомендуется не более 50):",
        reply_markup=back_button()
    )
    await callback.answer()


@router.message(InviteSettingsStates.waiting_for_max_24h)
async def handle_max_24h(message: Message, state: FSMContext):
    try:
        max_invites_24h = int(message.text.strip())
        if max_invites_24h < 1:
            await message.answer(
                "⚠️ Значение должно быть положительным числом."
            )
            return
        
        settings = db.get_invite_settings()
        if max_invites_24h < settings['max_invites_per_12h']:
            await message.answer(
                f"⚠️ Значение для 24 часов должно быть не меньше значения для 12 часов ({settings['max_invites_per_12h']})."
            )
            return
        
        db.update_invite_settings(
            max_invites_per_24h=max_invites_24h
        )
        
        updated_settings = db.get_invite_settings()
        
        text = "✅ Настройки максимального количества приглашений за 24 часа обновлены!\n\n"
        text += "⚙️ Настройки инвайтинга\n\n"
        text += f"Интервал между приглашениями: {updated_settings['invite_interval_min']}-{updated_settings['invite_interval_max']} секунд\n"
        text += f"Максимум приглашений за 12ч: {updated_settings['max_invites_per_12h']}\n"
        text += f"Максимум приглашений за 24ч: {updated_settings['max_invites_per_24h']}\n\n"
        text += "Выберите параметр для изменения:"
        
        await message.answer(
            text,
            reply_markup=invite_settings_keyboard()
        )
        await state.clear()
    except ValueError:
        await message.answer(
            "❌ Пожалуйста, введите число."
        ) 