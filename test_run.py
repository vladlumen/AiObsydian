import sys
from pathlib import Path
import shutil

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
TEMP_MEDIA_DIR = BASE_DIR / "data"  # Папка, куда бот сохраняет медиа из TG

def clear_temp_media():
    """Полностью очищает временные медиа-файлы в папке data/ перед стартом ядра."""
    print("[System] 🧹 Запуск автоочистки временных медиафайлов...")
    
    # Расширения файлов, которые подлежат удалению (чтобы случайно не снести .db)
    media_extensions = {'.ogg', '.mp3', '.wav', '.jpg', '.jpeg', '.png', '.pdf', '.docx'}
    
    if TEMP_MEDIA_DIR.exists():
        counter = 0
        try:
            # Обходим только файлы в корне папки data/
            for item in TEMP_MEDIA_DIR.iterdir():
                if item.is_file() and item.suffix.lower() in media_extensions:
                    item.unlink()
                    counter += 1
            print(f"[System] 🗑️ Автоочистка завершена. Удалено файлов: {counter}")
        except Exception as e:
            print(f"[System] ⚠️ Ошибка при очистке медиа: {e}")
    else:
        print("[System] 📁 Папка data/ не найдена. Пропускаем очистку.")

async def main():
    print("🚀 Запуск Системы v2.0...")
    
    # Автоматическая зачистка мусора на старте
    clear_temp_media()
    
    # 0. Синхронизация с Obsidian Vault при старте
    await memory.sync_obsidian_vault(OBSIDIAN_VAULT_PATH)
    
    # 1. Запускаем воркера очереди (в фоне)
    await task_manager.start()
    
    # 2. Запускаем Telegram-бота (блокирующий вызов)
    await start_telegram_bot()

if __name__ == "__main__":
    asyncio.run(main())