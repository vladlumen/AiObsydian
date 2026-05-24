import asyncio
from aiogram import Bot, Dispatcher, types
from src.core.config import BOT_TOKEN, ALLOWED_USER_ID
from src.interfaces.telegram.handlers import router

# 1. Инициализируем бота и диспетчер
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# 2. Переписываем middleware в виде класса или чистой функции (без декоратора)
async def access_control_middleware(handler, event: types.Message, data: dict):
    if event.from_user and event.from_user.id == ALLOWED_USER_ID:
        return await handler(event, data)
    
    print(f"⚠️ [Security] Игнорируем запрос от неизвестного ID: {event.from_user.id if event.from_user else 'Unknown'}")
    return

async def start_telegram_bot():
    """Запускает прослушку Telegram."""
    # Регистрируем middleware принудительно перед запуском
    dp.message.outer_middleware(access_control_middleware)
    
    # Подключаем роутеры с хэндлерами
    dp.include_router(router)
    
    print("🤖 [TelegramBot] Бот запущен. Слушаю сообщения...")
    await bot.delete_webhook(drop_pending_updates=False)
    await dp.start_polling(bot)