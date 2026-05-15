from pathlib import Path
from aiogram import Router, F, Bot
from aiogram.types import Message
from src.infrastructure.event_bus import bus, TextReceivedEvent, VoiceReceivedEvent
from src.core.config import TEMP_MEDIA_DIR

router = Router()

@router.message(F.text)
async def handle_text(message: Message):
    """Ловим обычный текст."""
    # Отправляем быстрое подтверждение, чтобы ты видел, что бот жив
    await message.react(reaction=[{"type": "emoji", "emoji": "👀"}])
    
    # Создаем событие и бросаем в шину
    event = TextReceivedEvent(
        user_id=message.from_user.id,
        text=message.text
    )
    await bus.publish(event)

@router.message(F.voice)
async def handle_voice(message: Message, bot: Bot):
    """Ловим голосовые сообщения и скачиваем их."""
    await message.react(reaction=[{"type": "emoji", "emoji": "🎧"}])
    
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