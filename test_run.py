import sys
from pathlib import Path

# Добавляем корень проекта в пути поиска модулей Python
BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

import asyncio
from src.infrastructure.task_queue import task_manager
from src.core.orchestrator import orchestrator
from src.interfaces.telegram.bot import start_telegram_bot
from src.cognitive.memory.semantic import memory

OBSIDIAN_VAULT_PATH = Path("/mnt/c/Users/vladislav/Documents/ObsidianVault")

async def main():
    print("🚀 Запуск Системы v2.0...")
    
    # 0. Синхронизация с Obsidian Vault при старте
    await memory.sync_obsidian_vault(OBSIDIAN_VAULT_PATH)
    
    # 1. Запускаем воркера очереди (в фоне)
    await task_manager.start()
    
    # 2. Запускаем Telegram-бота (блокирующий вызов)
    await start_telegram_bot()

if __name__ == "__main__":
    asyncio.run(main())
