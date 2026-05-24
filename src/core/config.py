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
from src.models.registry import MODEL_REGISTRY

# СЛОВАРЬ ДОСТУПНЫХ МОДЕЛЕЙ (Единый источник правды)
# Ключ — то, что ты пишешь в ТГ. Значение — точный тег в Ollama.
AVAILABLE_MODELS = {
    "hermes": "hermes3:8b",
    "qwen": "qwen3.5:9b"  # Вот здесь жестко фиксируем твою новую модель
}

# По умолчанию используем Qwen как основную модель
CURRENT_LLM_MODEL = AVAILABLE_MODELS["qwen"]

# --- НАСТРОЙКИ LLM ---
# Контроль скрытых рассуждений (CoT) для моделей, которые это поддерживают
# 0 - отключить скрытые рассуждения, -1 - использовать значение по умолчанию модели
THINKING_BUDGET = 0

# Флаг режима сравнения моделей (активируется в бенчмарках)
COMPARE_MODE = False