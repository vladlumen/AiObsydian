import logging
import sys
import sqlite3
import json
from datetime import datetime

# 1. Настраиваем базовый формат вывода (стандартный Python логгер)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)

# 2. СОЗДАЕМ ЕДИНЫЙ ОБЪЕКТ ЛОГГЕРА, КОТОРЫЙ ИЩУТ ОРКЕСТРАТОР И ДРУГИЕ МОДУЛИ
logger = logging.getLogger("AgentCore")

# Сохраняем существующую функциональность LiteFlightRecorder для обратной совместимости
DB_NAME = "state.db"

class LiteFlightRecorder:
    def __init__(self, db_name=DB_NAME):
        self.db_name = db_name

    def _write_to_db(self, level: str, source: str, message: str, meta: dict = None):
        meta_json = json.dumps(meta, ensure_ascii=False) if meta else None
        try:
            conn = sqlite3.connect(self.db_name)
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO agent_log (level, source, message, meta) VALUES (?, ?, ?, ?)",
                (level, source, message, meta_json)
            )
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"[CRITICAL ERROR] Failed to write log to DB: {e}", file=sys.stderr)

    def _console_print(self, level: str, source: str, message: str):
        colors = {
            "INFO": "\033[94m",    # Синий
            "WARNING": "\033[93m", # Желтый
            "ERROR": "\033[91m",   # Красный
            "STEP": "\033[92m",    # Зеленый
            "RESET": "\033[0m"
        }
        color = colors.get(level, colors["RESET"])
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"{color}[{timestamp}] [{level}] [{source}] {message}{colors['RESET']}")

    def log(self, level: str, source: str, message: str, meta: dict = None):
        self._console_print(level, source, message)
        self._write_to_db(level, source, message, meta)

    def info(self, source: str, message: str, meta: dict = None):
        self.log("INFO", source, message, meta)

    def warning(self, source: str, message: str, meta: dict = None):
        self.log("WARNING", source, message, meta)

    def error(self, source: str, message: str, meta: dict = None):
        self.log("ERROR", source, message, meta)

    def step(self, source: str, message: str, meta: dict = None):
        self.log("STEP", source, message, meta)

agent_logger = LiteFlightRecorder()