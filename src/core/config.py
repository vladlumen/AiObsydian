import os
from pathlib import Path

# --- ОСНОВНЫЕ ПУТИ ---
BASE_DIR = Path(__file__).resolve().parent.parent.parent
PROJECT_ROOT = BASE_DIR
DB_PATH = os.path.join(PROJECT_ROOT, "data", "state.db")
SESSION_TIMEOUT_MINUTES = 30

# Папка для данных (векторы, временные файлы и т.д.)
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

# Путь к LanceDB хранилищу
LANCEDB_DIR = DATA_DIR / "lancedb_store"

# Временная папка для загрузки аудио и картинок из Telegram
TEMP_MEDIA_DIR = BASE_DIR / "data" / "temp_media"
TEMP_MEDIA_DIR.mkdir(parents=True, exist_ok=True)

# Путь к Obsidian Vault
VAULT_PATH_STR = os.getenv("OBSIDIAN_VAULT_PATH", "/mnt/c/Users/vladislav/Documents/ObsidianVault")
VAULT_DIR = Path(VAULT_PATH_STR)
INBOX_PATH = VAULT_DIR / "00_Inbox"

# --- СЕМАНТИЧЕСКАЯ КАРТА ОБСИДИАНА (KHOJ & PARA CONTEXT) ---
# Используется чанкером для инжекции контекста и сортировщиком для создания папок
VAULT_DIRECTORY_CONTEXT = {
    # Входящие / Логи
    "00_Inbox": {"context": "Входящие незавершенные задачи и сырые лог-заметки", "is_sensitive": False},
    "Дневник": {"context": "Личный дневник, хроника событий, рефлексия по дням и месяцам", "is_sensitive": False},
    
    # Работа и Обучение (Проекты / Сферы)
    "Работа/Школы": {"context": "Преподавательская деятельность, учебные курсы, EasyCode, Rocket Tech, Rebotica", "is_sensitive": False},
    "Работа/Проекты": {"context": "Разработка ПО, Senior Roblox Developer, архитектура игровых систем, LobbyCore, Lumen_brain_bot", "is_sensitive": False},
    "Обучение": {"context": "Изучение новых технологий, screenwriting, курсы повышения квалификации", "is_sensitive": False},
    "Языки/Английский": {"context": "Материалы по изучению английского языка, грамматика, лексика", "is_sensitive": False},
    "Языки/Сербский": {"context": "Материалы по изучению сербского языка, локальная интеграция в Белграде", "is_sensitive": False},
    
    # Тайм-менеджмент (Задачи)
    "Задачи/День": {"context": "Оперативные задачи, фокус и расписание на текущий день", "is_sensitive": False},
    "Задачи/Неделя": {"context": "Тактическое планирование и приоритеты на неделю", "is_sensitive": False},
    "Задачи/Месяц": {"context": "Планы и ключевые результаты (OKR) на месяц", "is_sensitive": False},
    "Задачи/Квартал": {"context": "Среднесрочные цели на 3 месяца и полгода", "is_sensitive": False},
    "Задачи/Год": {"context": "Стратегические жизненные и профессиональные цели на год", "is_sensitive": False},
    "Задачи/Архив": {"context": "Исторические выполненные задачи и закрытые спринты планирования", "is_sensitive": False},
    
    # Интересы / Гео / Хобби
    "Места/Страны и Города": {"context": "Путеводители, география поездок, релокация, Белград, Сербия", "is_sensitive": False},
    "Места/Локации": {"context": "Списки и обзоры заведений: бары, кафе, рестораны, музеи для посещения", "is_sensitive": False},
    "Люди": {"context": "Профайлы, контакты, менторство, Даниил, Эмиль, социальный граф", "is_sensitive": False},
    "Спорт": {"context": "Физическая культура, тренировки, бег, Romanian deadlifts, Z-bar rows, выносливость", "is_sensitive": False},
    "Медиа/Кино": {"context": "Списки к просмотру, рецензии на фильмы, сценарии, драматургия", "is_sensitive": False},
    "Медиа/YouTube": {"context": "План контента, аналитика каналов, видеопроизводство", "is_sensitive": False},
    "Технологии/Нейросети": {"context": "Локальные LLM, оптимизация RTX 3090, промт-инжиниринг, ИИ-агенты", "is_sensitive": False},
    "Финансы/Инвестиции": {"context": "Управление капиталом, криптобиржи Gate.io, OKX, Bybit, TON, недвижимость в Белграде", "is_sensitive": False},
    
    # Конфиденциальные личные данные (Доступ по спец-команде)
    "Личные": {"context": "Глубокие личные воспоминания, архивы приватных событий", "is_sensitive": True}
}

# --- ТЕЛЕГРАМ ---
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")
ALLOWED_USER_ID_STR = os.getenv("ALLOWED_USER_ID", "475811487")
ALLOWED_USER_ID = int(ALLOWED_USER_ID_STR) if ALLOWED_USER_ID_STR.isdigit() else 0

# --- МОДЕЛИ ---
AVAILABLE_MODELS = {
    "hermes": "hermes3:8b",
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