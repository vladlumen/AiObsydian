import asyncio
from pathlib import Path
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