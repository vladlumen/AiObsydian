import asyncio
from aiogram import Bot, Dispatcher, types
from src.core.config import BOT_TOKEN, ALLOWED_USER_ID
from src.interfaces.telegram.handlers import router

# Инициализируем бота
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# --- MIDDLEWARE БЕЗОПАСНОСТИ ---
@dp.message.outer_middleware()
async def access_control_middleware(handler, event: types.Message, data: dict):
    if event.from_user and event.from_user.id == ALLOWED_USER_ID:
        return await handler(event, data)
    
    print(f"⚠️ [Security] Игнорируем запрос от неизвестного ID: {event.from_user.id if event.from_user else 'Unknown'}")
    return

async def start_telegram_bot():
    """Запускает прослушку Telegram."""
    dp.include_router(router)
    print("🤖 [TelegramBot] Бот запущен. Слушаю сообщения...")
    await bot.delete_webhook(drop_pending_updates=False)
    await dp.start_polling(bot)