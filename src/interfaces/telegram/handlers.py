from pathlib import Path
import os
from aiogram import Router, F, Bot
from aiogram.types import Message
from src.infrastructure.event_bus import bus, TextReceivedEvent, VoiceReceivedEvent, PhotoReceivedEvent, DocumentReceivedEvent
from src.core.config import TEMP_MEDIA_DIR

router = Router()

@router.message(F.text)
async def handle_text(message: Message):
    """Ловим обычный текст."""
    # Отправляем быстрое подтверждение, чтобы ты видел, что бот жив
    try:
        await message.react(reaction=[{"type": "emoji", "emoji": "👀"}])
    except Exception as e:
        print(f"[Telegram] ⚠️ Не удалось поставить реакцию: {e}")
     
    # Создаем событие и бросаем в шину
    event = TextReceivedEvent(
        user_id=message.from_user.id,
        text=message.text
    )
    await bus.publish(event)

@router.message(F.voice)
async def handle_voice(message: Message, bot: Bot):
    """Ловим голосовые сообщения и скачиваем их."""
    
    # Пытаемся поставить разрешенную реакцию (например, молнию или ручку)
    try:
        await message.react(reaction=[{"type": "emoji", "emoji": "⚡"}])
    except Exception as e:
        print(f"[Telegram] ⚠️ Не удалось поставить реакцию: {e}")
    
    # Формируем путь для сохранения файла
    file_id = message.voice.file_id
    file_name = f"voice_{message.message_id}.ogg"
    file_path = TEMP_MEDIA_DIR / file_name
    
    # Скачиваем файл с серверов Telegram
    await bot.download(file_id, destination=file_path)
    print(f"[Telegram] 📥 Сохранил голос: {file_name}")
    
    # Бросаем событие в шину
    event = VoiceReceivedEvent(
        user_id=message.from_user.id,
        audio_path=file_path
    )
    await bus.publish(event)


@router.message(F.photo)
async def handle_photo(message: Message, bot: Bot):
    """Ловим фотографии и скачиваем их."""
    try:
        await message.react(reaction=[{"type": "emoji", "emoji": "👀"}])
    except Exception as e:
        print(f"[Telegram] ⚠️ Не удалось поставить реакцию: {e}")
    
    # Telegram отправляет массив разных размеров фото. Брем последнее (самое большое)
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