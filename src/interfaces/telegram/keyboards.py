from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardMarkup

def get_model_selection_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    
    # Кнопки отправляют callback_data, которую поймает специальный хендлер
    builder.button(text="🏆 Hermes (8B)", callback_data="set_model_hermes")
    builder.button(text="🧠 Qwen (Light)", callback_data="set_model_qwen")
    builder.button(text="📊 Режим сравнения (Обе)", callback_data="set_model_compare")
    
    # Выстраиваем кнопки вертикально (по одной в ряд)
    builder.adjust(1)
    return builder.as_markup()