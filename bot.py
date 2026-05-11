import asyncio
import os
from aiogram import Bot, Dispatcher, types
from aiogram.filters import CommandStart
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from brain import agent_brain
from logger import agent_logger

# --- НАСТРОЙКИ БЕЗОПАСНОСТИ ---
BOT_TOKEN = "8674649133:AAFSfJegPBdGI-lhY2oVT0qFjqEv693wx8U"  # Вставьте сюда токен от BotFather
ALLOWED_USER_ID = 475811487  # Вставьте сюда ваш численный Telegram ID (без кавычек)

# Инициализируем бота с поддержкой MarkdownV2 по умолчанию
bot = Bot(
    token=BOT_TOKEN, 
    default=DefaultBotProperties(parse_mode=ParseMode.MARKDOWN_V2)
)
dp = Dispatcher()

# --- MIDDLEWARE БЕЗОПАСНОСТИ ---
@dp.message.outer_middleware()
async def access_control_middleware(handler, event: types.Message, data: dict):
    if event.from_user and event.from_user.id == ALLOWED_USER_ID:
        return await handler(event, data)
    
    # Логируем попытку взлома/чужого доступа
    if event.from_user:
        agent_logger.warning("BotSecurity", f"Игнорируем запрос от неизвестного ID: {event.from_user.id}")
    return

def escape_markdown(text: str) -> str:
    """Экранирование спецсимволов для корректного отображения MarkdownV2 в Telegram."""
    escape_chars = r'_*[]()~`>#+-=|{}.!'
    return ''.join('\\' + char if char in escape_chars else char for char in text)


@dp.message(CommandStart())
async def cmd_start(message: types.Message):
    welcome_text = escape_markdown(
        "Привет, Архитектор! Личный ассистент базы знаний Obsidian запущен.\n\n"
        "Доступные команды:\n"
        "• Найди [запрос] — поиск по векторам в Vault\n"
        "• Запиши [текст] — создание новой заметки"
    )
    await message.answer(welcome_text)

@dp.message()
async def handle_user_query(message: types.Message):
    user_query = message.text
    if not user_query:
        return

    # Отправляем статус "Печатает...", визуально показывая начало работы
    await message.bot.send_chat_action(chat_id=message.chat.id, action="typing")
    
    # Отправляем промежуточный статус
    status_msg = await message.answer(escape_markdown("⏳ Обрабатываю запрос..."))

    try:
        # Запускаем тяжелую логику синхронного мозга в отдельном потоке (Async Bridge)
        response_text = await asyncio.to_thread(agent_brain.process_query, user_query)
        
        # Экранируем ответ для MarkdownV2
        safe_response = escape_markdown(response_text)
        
        # Обновляем сообщение статуса на финальный ответ
        await status_msg.edit_text(safe_response)
        
    except Exception as e:
        agent_logger.error("TelegramBot", f"Ошибка обработки: {e}")
        await status_msg.edit_text(escape_markdown("❌ Произошла ошибка при обработке запроса."))

async def main():
    agent_logger.info("TelegramBot", "Запуск бота...")
    # Удаляем только старые вебхуки, но НЕ удаляем накопившиеся сообщения (False)
    await bot.delete_webhook(drop_pending_updates=False) 
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
