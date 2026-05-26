import sqlite3
import hashlib
import logging  # Перешли на стандартный логгер
from typing import Dict, Optional, List, Tuple

# Настраиваем локальный логгер для модуля
logger = logging.getLogger("SQLiteManager")

class SQLiteManager:
    def __init__(self, db_path: str = "state.db"):
        self.db_path = db_path
        self.init_db()

    def init_db(self):
        """Инициализация всех необходимых таблиц SQLite."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # Таблица реестра файлов для инкрементального RAG (Khoj-паттерн)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS file_registry (
                    file_path TEXT PRIMARY KEY,
                    last_modified REAL NOT NULL,
                    hash TEXT NOT NULL
                )
            """)
            
            # Индекс для ускорения выборки путей
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_file_path ON file_registry(file_path)")
            conn.commit()
            print("[SQLite] Таблица file_registry успешно инициализирована.")

    def get_file_state(self, file_path: str) -> Optional[Tuple[float, str]]:
        """Получить сохраненное время модификации и хэш файла."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT last_modified, hash FROM file_registry WHERE file_path = ?", 
                    (file_path,)
                )
                row = cursor.fetchone()
                return row if row else None
        except sqlite3.Error as e:
            print(f"[SQLite Ошибка] Не удалось получить состояние файла {file_path}: {e}")
            return None

    def update_file_state(self, file_path: str, last_modified: float, file_hash: str):
        """Добавить или обновить запись о файле в реестре."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT OR REPLACE INTO file_registry (file_path, last_modified, hash)
                    VALUES (?, ?, ?)
                """, (file_path, last_modified, file_hash))
                conn.commit()
        except sqlite3.Error as e:
            print(f"[SQLite Ошибка] Не удалось обновить состояние файла {file_path}: {e}")

    def delete_file_state(self, file_path: str):
        """Удалить файл из реестра (если он был удален из Obsidian)."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM file_registry WHERE file_path = ?", (file_path,))
                conn.commit()
                print(f"[SQLite] Файл {file_path} удален из реестра.")
        except sqlite3.Error as e:
            print(f"[SQLite Ошибка] Не удалось удалить файл {file_path} из реестра: {e}")

    def get_all_registered_files(self) -> Dict[str, Tuple[float, str]]:
        """Получить весь реестр для сверки удалений на диске."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT file_path, last_modified, hash FROM file_registry")
                rows = cursor.fetchall()
                return {row[0]: (row[1], row[2]) for row in rows}
        except sqlite3.Error as e:
            print(f"[SQLite Ошибка] Не удалось выгрузить реестр файлов: {e}")
            return {}