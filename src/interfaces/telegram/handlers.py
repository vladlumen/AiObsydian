from pathlib import Path
import os
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command  # Тот самый недостающий импорт
from src.infrastructure.event_bus import bus, TextReceivedEvent, VoiceReceivedEvent, PhotoReceivedEvent, DocumentReceivedEvent
from src.core.config import TEMP_MEDIA_DIR
from src.core import config 
from src.interfaces.telegram.keyboards import get_model_selection_keyboard

router = Router()

# ==========================================
# КОМАНДЫ УПРАВЛЕНИЯ И НАСТРОЕК
# ==========================================

@router.message(Command("model", "settings"))
async def show_model_settings(message: Message):
    """Вызов инлайн-меню управления моделями."""
    await message.answer(
        "🤖 **Управление мозгами Системы**\n\n"
        "Выберите, какая модель будет обрабатывать входящие заметки, файлы и ссылки:",
        reply_markup=get_model_selection_keyboard(),
        parse_mode="Markdown"
    )

@router.callback_query(F.data.startswith("set_model_"))
async def process_model_selection(callback: CallbackQuery):
    """Обработка нажатий кнопок меню."""
    action = callback.data.replace("set_model_", "")
    
    if action == "compare":
        config.COMPARE_MODE = True
        status_text = "📊 Включен режим сравнения! Запросы пойдут на обе модели последовательно."
        print("[System] 📊 Режим сравнения активирован кнопкой.")
    
    elif action == "hermes":
        config.COMPARE_MODE = False
        config.CURRENT_LLM_MODEL = config.AVAILABLE_MODELS["hermes"]
        status_text = "🏆 Активная модель изменена на: **Hermes 3 (8B)**"
        print(f"[System] Модель изменена кнопкой на: {config.CURRENT_LLM_MODEL}")
        
    elif action == "qwen":
        config.COMPARE_MODE = False
        config.CURRENT_LLM_MODEL = config.AVAILABLE_MODELS["qwen"]
        status_text = "🧠 Активная модель изменена на: **Qwen 3.5 (Light)**"
        print(f"[System] Модель изменена кнопкой на: {config.CURRENT_LLM_MODEL}")

    await callback.answer("Настройки обновлены")
    
    await callback.message.edit_text(
        f"{status_text}\n\nЧтобы изменить режим снова, вызови команду /settings.",
        parse_mode="Markdown"
    )

# ==========================================
# ОБРАБОТЧИКИ ВХОДЯЩЕГО КОНТЕНТА
# ==========================================

@router.message(F.text)
async def handle_text(message: Message):
    """Ловим обычный текст, RAG-запросы и текстовые команды-хвосты."""
    text = message.text.strip()
    
    # ПЕРЕХВАТ ТЕКСТОВОЙ КОМАНДЫ СРАВНЕНИЯ (устаревает, но оставляем для совместимости)
    if text.startswith("!compare"):
        config.COMPARE_MODE = not config.COMPARE_MODE
        status = "ВКЛЮЧЕН (запросы идут на ВСЕ модели)" if config.COMPARE_MODE else "ВЫКЛЮЧЕН (работает одна модель)"
        await message.answer(f"📊 **Режим сравнения моделей:** `{status}`")
        print(f"[System] 📊 Режим сравнения изменен на: {config.COMPARE_MODE}")
        return
    
    # ПЕРЕХВАТ ТЕКСТОВОЙ КОМАНДЫ ПЕРЕКЛЮЧЕНИЯ МОДЕЛЕЙ
    if text.startswith("!model"):
        args = text.split()
        if len(args) < 2:
            options = "\n".join([f"• `!model {k}` — `{v}`" for k, v in config.AVAILABLE_MODELS.items()])
            await message.answer(
                f"🤖 **Текущая текстовая модель:** `{config.CURRENT_LLM_MODEL}`\n\n"
                f"Доступные для переключения:\n{options}"
            )
            return

        target = args[1].lower()
        if target in config.AVAILABLE_MODELS:
            config.CURRENT_LLM_MODEL = config.AVAILABLE_MODELS[target]
            await message.answer(f"✅ Переключил текстовое ядро на: `{config.CURRENT_LLM_MODEL}`")
            print(f"[System] 🧠 Модель успешно изменена на {config.CURRENT_LLM_MODEL}")
        else:
            allowed = ", ".join(config.AVAILABLE_MODELS.keys())
            await message.answer(f"❌ Неизвестная модель. Доступные варианты: {allowed}")
        return

    # ОБЫЧНЫЙ РАБОЧИЙ ТЕКСТ (Запрос к RAG / Инжест заметки)
    try:
        await message.react(reaction=[{"type": "emoji", "emoji": "👀"}])
    except Exception as e:
        print(f"[Telegram] ⚠️ Не удалось поставить реакцию: {e}")
     
    event = TextReceivedEvent(
        user_id=message.from_user.id,
        text=message.text
    )
    await bus.publish(event)

@router.message(F.voice)
async def handle_voice(message: Message, bot: Bot):
    """Ловим голосовые сообщения."""
    try:
        await message.react(reaction=[{"type": "emoji", "emoji": "⚡"}])
    except Exception as e:
        print(f"[Telegram] ⚠️ Не удалось поставить реакцию: {e}")
    
    file_id = message.voice.file_id
    file_name = f"voice_{message.message_id}.ogg"
    file_path = TEMP_MEDIA_DIR / file_name
    
    await bot.download(file_id, destination=file_path)
    print(f"[Telegram] 📥 Сохранил голос: {file_name}")
    
    event = VoiceReceivedEvent(
        user_id=message.from_user.id,
        audio_path=file_path
    )
    await bus.publish(event)

@router.message(F.photo)
async def handle_photo(message: Message, bot: Bot):
    """Ловим фотографии."""
    try:
        await message.react(reaction=[{"type": "emoji", "emoji": "👀"}])
    except Exception as e:
        print(f"[Telegram] ⚠️ Не удалось поставить реакцию: {e}")
    
    photo = message.photo[-1]
    file_id = photo.file_id
    file_name = f"photo_{message.message_id}.jpg"
    file_path = TEMP_MEDIA_DIR / file_name
    
    await bot.download(file_id, destination=file_path)
    print(f"[Telegram] 📥 Сохранил фото: {file_name}")
    
    event = PhotoReceivedEvent(
        user_id=message.from_user.id,
        photo_path=file_path,
        caption=message.caption or ""
    )
    await bus.publish(event)

@router.message(F.document)
async def handle_document(message: Message, bot: Bot):
    """Ловим PDF и DOCX файлы."""
    file_id = message.document.file_id
    file_name = message.document.file_name
    ext = os.path.splitext(file_name)[1].lower()

    if ext not in ['.pdf', '.docx']:
        await message.reply("❌ Поддерживаются только форматы PDF и DOCX.")
        return

    if message.document.file_size > 15 * 1024 * 1024:
        await message.reply("❌ Файл слишком большой. Лимит 15 МБ.")
        return

    file_path = TEMP_MEDIA_DIR / file_name
    await bot.download(file_id, destination=file_path)
    print(f"[Telegram] 📥 Сохранил документ: {file_name}")

    caption = message.caption or ""
    event = DocumentReceivedEvent(
        user_id=message.from_user.id,
        file_path=file_path,
        file_name=file_name,
        caption=caption
    )
    await bus.publish(event)