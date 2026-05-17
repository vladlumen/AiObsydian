import os
from pathlib import Path

# --- ОСНОВНЫЕ ПУТИ ---
# Корень проекта (Linux)
BASE_DIR = Path(__file__).resolve().parent.parent.parent

# Папка для данных (векторы, временные файлы и т.д.)
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

# Временная папка для загрузки аудио и картинок из Telegram
TEMP_MEDIA_DIR = BASE_DIR / "data" / "temp_media"
TEMP_MEDIA_DIR.mkdir(parents=True, exist_ok=True)

# Путь к Obsidian Vault на Windows (Через мост /mnt/c/)
# ЗАМЕНИ НА СВОЙ РЕАЛЬНЫЙ ПУТЬ!
VAULT_DIR = Path("/mnt/c/Users/vladislav/Documents/ObsidianVault")
INBOX_PATH = VAULT_DIR / "00_Inbox"

# --- ТЕЛЕГРАМ ---
# По-хорошему, токены надо хранить в .env файле, но для старта оставим тут
BOT_TOKEN = "8674649133:AAFSfJegPBdGI-lhY2oVT0qFjqEv693wx8U" 
ALLOWED_USER_ID = 475811487