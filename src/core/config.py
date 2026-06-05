import os
from pathlib import Path

# --- ОСНОВНЫЕ ПУТИ ---
BASE_DIR = Path(__file__).resolve().parent.parent.parent

# Папка для данных (векторы, временные файлы и т.д.)
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

# Путь к LanceDB хранилищу
LANCEDB_DIR = DATA_DIR / "lancedb_store"

# Временная папка для загрузки аудио и картинок из Telegram
TEMP_MEDIA_DIR = BASE_DIR / "data" / "temp_media"
TEMP_MEDIA_DIR.mkdir(parents=True, exist_ok=True)

# Путь к Obsidian Vault (берем из .env, если его нет — ставим дефолтный путь)
VAULT_PATH_STR = os.getenv("OBSIDIAN_VAULT_PATH", "/mnt/c/Users/vladislav/Documents/ObsidianVault")
VAULT_DIR = Path(VAULT_PATH_STR)
INBOX_PATH = VAULT_DIR / "00_Inbox"

# --- ТЕЛЕГРАМ (Берем из переменных окружения) ---
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")

# Превращаем ID пользователя в число, если он задан
ALLOWED_USER_ID_STR = os.getenv("ALLOWED_USER_ID", "475811487")
ALLOWED_USER_ID = int(ALLOWED_USER_ID_STR) if ALLOWED_USER_ID_STR.isdigit() else 0

from src.models.registry import MODEL_REGISTRY

AVAILABLE_MODELS = {
    "hermes": "hermes3:8b",
    "qwen": "qwen3.5:9b"
}

CURRENT_LLM_MODEL = AVAILABLE_MODELS["hermes"]

# --- НАСТРОЙКИ LLM ---
THINKING_BUDGET = 0
COMPARE_MODE = False

def clear_temp_media():
    media_extensions = {'.ogg', '.mp3', '.wav', '.jpg', '.jpeg', '.png', '.pdf', '.docx'}
    
    if TEMP_MEDIA_DIR.exists():
        counter = 0
        try:
            for item in TEMP_MEDIA_DIR.iterdir():
                if item.is_file() and item.suffix.lower() in media_extensions:
                    item.unlink()
                    counter += 1
            if counter > 0:
                print(f"[System] 🗑️ Автоочистка temp_media: удалено {counter} файлов")
        except Exception as e:
            print(f"[System] ⚠️ Ошибка при очистке медиа: {e}")
    else:
        TEMP_MEDIA_DIR.mkdir(parents=True, exist_ok=True)