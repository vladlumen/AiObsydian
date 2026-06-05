import sys
from pathlib import Path
import asyncio

# === ИСПРАВЛЕНИЕ БЕЗОПАСНОСТИ: Загружаем скрытые ключи из .env файла ===
from dotenv import load_dotenv
load_dotenv()  
# ======================================================================

# Добавляем корень проекта в пути поиска модулей Python
BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

# Импортируем конфиг и проверяем пути (теперь они безопасно подтянутся из .env)
from src.core.config import BOT_TOKEN, ALLOWED_USER_ID, VAULT_DIR, TEMP_MEDIA_DIR
from src.infrastructure.task_queue import task_manager
from src.core.orchestrator import orchestrator
from src.interfaces.telegram.bot import start_telegram_bot
from src.cognitive.memory.semantic import memory

# Теперь не нужно хардкодить пути вручную, они берутся из вашего config.py
OBSIDIAN_VAULT_PATH = VAULT_DIR
# TEMP_MEDIA_DIR уже импортирован из конфига и указывает строго на data/temp_media

def clear_temp_media():
    """Полностью очищает временные медиа-файлы в папке data/temp_media/ перед стартом."""
    print("[System] 🧹 Запуск автоочистки временных медиафайлов...")
    
    media_extensions = {'.ogg', '.mp3', '.wav', '.jpg', '.jpeg', '.png', '.pdf', '.docx'}
    
    if TEMP_MEDIA_DIR.exists():
        counter = 0
        try:
            for item in TEMP_MEDIA_DIR.iterdir():
                if item.is_file() and item.suffix.lower() in media_extensions:
                    item.unlink()
                    counter += 1
            print(f"[System] 🗑️ Автоочистка завершена. Удалено файлов из temp_media: {counter}")
        except Exception as e:
            print(f"[System] ⚠️ Ошибка при очистке медиа: {e}")
    else:
        # Если папки нет, создаем её, чтобы боту было куда качать файлы
        TEMP_MEDIA_DIR.mkdir(parents=True, exist_ok=True)
        print("[System] 📁 Папка data/temp_media/ не найдена. Создана пустая папка.")

async def main():
    print("🚀 Запуск Системы v2.0...")
    
    # Изолированная зачистка мусора
    clear_temp_media()
    
    # 0. Синхронизация с Obsidian Vault при старте
    print("[System] 🔄 Синхронизация с Obsidian Vault...")
    await memory.sync_obsidian_vault(OBSIDIAN_VAULT_PATH)
    
    # 1. Запускаем воркера очереди в ФОНЕ (через asyncio.create_task), 
    # чтобы код пошел дальше к запуску бота
    print("[System] ⚙️ Запуск фоновых воркеров очереди задач...")
    worker_task = asyncio.create_task(task_manager.start())
    
    # 2. Запускаем Telegram-бота (блокирующий вызов, держит скрипт запущенным)
    await start_telegram_bot()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n🛑 Система остановлена пользователем.")