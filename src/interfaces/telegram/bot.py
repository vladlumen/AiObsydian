import asyncio
from typing import Dict, Any, List
from aiogram import Bot, Dispatcher, types, BaseMiddleware
from src.core.config import BOT_TOKEN, ALLOWED_USER_ID
from src.interfaces.telegram.handlers import router

# 1. Инициализируем бота и диспетчер
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()


# 2. Middleware контроля доступа (Оставляем без изменений)
async def access_control_middleware(handler, event: types.Message, data: dict):
    if event.from_user and event.from_user.id == ALLOWED_USER_ID:
        return await handler(event, data)
    
    print(f"⚠️ [Security] Игнорируем запрос от неизвестного ID: {event.from_user.id if event.from_user else 'Unknown'}")
    return


# 3. Middleware для буферизации и склейки сообщений (Атомарная сборка пачек)
class MessageBulkMiddleware(BaseMiddleware):
    def __init__(self, latency: float = 1.5):
        self.latency = latency
        self.storage: Dict[int, List[types.Message]] = {}
        self.locks: Dict[int, asyncio.Lock] = {}
        super().__init__()

    async def __call__(self, handler, event: types.Message, data: Dict[str, Any]):
        if not event.from_user:
            return await handler(event, data)

        user_id = event.from_user.id
        
        # Защищаем инициализацию структуры данных для пользователя
        if user_id not in self.storage:
            self.storage[user_id] = []
            self.locks[user_id] = asyncio.Lock()

        # Шаг 1: Атомарно добавляем сообщение в очередь
        async with self.locks[user_id]:
            self.storage[user_id].append(event)
            
        # Даем время на досылку медиагрупп или пачки сообщений
        await asyncio.sleep(self.latency)

        # Шаг 2: Проверяем, является ли текущая задача последней в пачке
        async with self.locks[user_id]:
            if user_id not in self.storage or not self.storage[user_id]:
                return  # Пачка уже обработана параллельным таском

            if self.storage[user_id][-1] != event:
                return  # Пришли новые сообщения, текущий таск уступает им дорогу

            # Если мы последние в списке — забираем всю накопленную пачку
            bulk = self.storage.pop(user_id, [])
            self.locks.pop(user_id, None)

        if not bulk:
            return

        forwarded_texts = []
        user_commands = []

        for msg in bulk:
            text = msg.text or msg.caption or ""
            if msg.forward_date or msg.forward_from or msg.forward_from_chat:
                forwarded_texts.append(text)
            else:
                user_commands.append(text)

        final_parts = []
        if forwarded_texts:
            final_parts.append("\n".join(forwarded_texts))
        if user_commands:
            final_parts.append(f"Инструкция по обработке:\n" + "\n".join(user_commands))

        combined_text = "\n\n".join(final_parts).strip()
        
        if not combined_text:
            return await handler(event, data)

        # Передаем склеенный текст в data. Хэндлер заберет его отсюда.
        data["combined_text"] = combined_text
        
        return await handler(event, data)


# 4. Запуск бота
async def start_telegram_bot():
    """Запускает прослушку Telegram."""
    dp.message.outer_middleware(access_control_middleware)
    dp.message.outer_middleware(MessageBulkMiddleware(latency=1.5))
    
    dp.include_router(router)
    
    print("🤖 [TelegramBot] Бот запущен. Слушаю сообщения...")
    await bot.delete_webhook(drop_pending_updates=False)
    await dp.start_polling(bot)


# Точка входа для запуска бота из консоли/скрипта
if __name__ == "__main__":
    try:
        asyncio.run(start_telegram_bot())
    except (KeyboardInterrupt, SystemExit):
        print("\n🤖 [TelegramBot] Бот остановлен вручную.")