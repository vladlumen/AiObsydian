import sqlite3
import hashlib
import logging  # Перешли на стандартный логгер
from typing import Dict, Optional, List, Tuple

# Настраиваем локальный логгер для модуля
logger = logging.getLogger("SQLiteManager")

from src.core.config import DB_PATH
DEFAULT_DB_PATH = DB_PATH

class SQLiteManager:
    def __init__(self, db_path: str = DEFAULT_DB_PATH):
        self.db_path = db_path
        self.init_db()

    def _get_connection(self) -> sqlite3.Connection:
        """Вспомогательный метод для создания подключения с поддержкой WAL и Foreign Keys."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        # Включение режима WAL для безопасной параллельной работы фонового коммитера и основного бота
        cursor.execute("PRAGMA journal_mode=WAL;")
        # Активация каскадного удаления на уровне SQLite (по умолчанию выключена)
        cursor.execute("PRAGMA foreign_keys = ON;")
        return conn

    def init_db(self):
        """Инициализация всех необходимых таблиц SQLite."""
        try:
            with self._get_connection() as conn:
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
                
                # OpenViking-pattern: Таблица сессий (многоуровневый контекст L0/L1)
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS ai_sessions (
                        chat_id INTEGER PRIMARY KEY,
                        l0_abstract TEXT DEFAULT '',
                        l1_overview TEXT DEFAULT '',
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                
                # OpenViking-pattern: Таблица сырых сообщений текущей рабочей памяти (L2 контекст)
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS ai_session_messages (
                        message_id INTEGER PRIMARY KEY AUTOINCREMENT,
                        chat_id INTEGER NOT NULL,
                        role TEXT NOT NULL,
                        content TEXT NOT NULL,
                        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (chat_id) REFERENCES ai_sessions(chat_id) ON DELETE CASCADE
                    )
                """)
                
                # Индекс для мгновенной сборки рабочей памяти L2 по конкретному чату
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_messages_chat_id 
                    ON ai_session_messages(chat_id)
                """)
                
                conn.commit()
                logger.info("[SQLite] Все таблицы (file_registry, ai_sessions, ai_session_messages) успешно инициализированы.")
        except sqlite3.Error as e:
            logger.critical(f"[SQLite Критическая ошибка] Не удалось инициализировать базу данных: {e}")

    def get_file_state(self, file_path: str) -> Optional[Tuple[float, str]]:
        """Получить сохраненное время модификации и хэш файла."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT last_modified, hash FROM file_registry WHERE file_path = ?", 
                    (file_path,)
                )
                row = cursor.fetchone()
                return row if row else None
        except sqlite3.Error as e:
            logger.error(f"[SQLite Ошибка] Не удалось получить состояние файла {file_path}: {e}")
            return None

    def update_file_state(self, file_path: str, last_modified: float, file_hash: str):
        """Добавить или обновить запись о файле в реестре."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT OR REPLACE INTO file_registry (file_path, last_modified, hash)
                    VALUES (?, ?, ?)
                """, (file_path, last_modified, file_hash))
                conn.commit()
        except sqlite3.Error as e:
            logger.error(f"[SQLite Ошибка] Не удалось обновить состояние файла {file_path}: {e}")

    def delete_file_state(self, file_path: str):
        """Удалить файл из реестра (если он был удален из Obsidian)."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM file_registry WHERE file_path = ?", (file_path,))
                conn.commit()
                logger.info(f"[SQLite] Файл {file_path} удален из реестра.")
        except sqlite3.Error as e:
            logger.error(f"[SQLite Ошибка] Не удалось удалить файл {file_path} из реестра: {e}")

    def get_all_registered_files(self) -> Dict[str, Tuple[float, str]]:
        """Получить весь реестр для сверки удалений на диске."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT file_path, last_modified, hash FROM file_registry")
                rows = cursor.fetchall()
                return {row[0]: (row[1], row[2]) for row in rows}
        except sqlite3.Error as e:
            logger.error(f"[SQLite Ошибка] Не удалось выгрузить реестр файлов: {e}")
            return {}

    # --- МЕТОДЫ ПОДДЕРЖКИ АРХИТЕКТУРЫ ПАМЯТИ (OpenViking) ---

    def ensure_session(self, chat_id: int):
        """Гарантирует наличие записи сессии для chat_id, если её не существовало."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT OR IGNORE INTO ai_sessions (chat_id, l0_abstract, l1_overview)
                    VALUES (?, '', '')
                """, (chat_id,))
                conn.commit()
        except sqlite3.Error as e:
            logger.error(f"[SQLite Ошибка] Не удалось инициализировать сессию для chat_id {chat_id}: {e}")

    def add_session_message(self, chat_id: int, role: str, content: str):
        """Добавляет сырое сообщение (L2) в историю текущей сессии."""
        self.ensure_session(chat_id)
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO ai_session_messages (chat_id, role, content)
                    VALUES (?, ?, ?)
                """, (chat_id, role, content))
                
                # Обновляем таймштамп активности сессии
                cursor.execute("""
                    UPDATE ai_sessions 
                    SET updated_at = CURRENT_TIMESTAMP 
                    WHERE chat_id = ?
                """, (chat_id,))
                conn.commit()
        except sqlite3.Error as e:
            logger.error(f"[SQLite Ошибка] Не удалось добавить сообщение для chat_id {chat_id}: {e}")

    def get_session_messages(self, chat_id: int) -> List[Tuple[str, str]]:
        """Возвращает все сырые сообщения L2 текущей сессии отсортированные по времени."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT role, content FROM ai_session_messages 
                    WHERE chat_id = ? 
                    ORDER BY message_id ASC
                """, (chat_id,))
                return cursor.fetchall()
        except sqlite3.Error as e:
            logger.error(f"[SQLite Ошибка] Не удалось получить сообщения для chat_id {chat_id}: {e}")
            return []

    def get_session_abstracts(self, chat_id: int) -> Tuple[str, str]:
        """Возвращает уровни абстракции памяти (l0_abstract, l1_overview) для чата."""
        self.ensure_session(chat_id)
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT l0_abstract, l1_overview FROM ai_sessions WHERE chat_id = ?", (chat_id,))
                row = cursor.fetchone()
                return row if row else ("", "")
        except sqlite3.Error as e:
            logger.error(f"[SQLite Ошибка] Не удалось получить абстракции для chat_id {chat_id}: {e}")
            return ("", "")

    def update_session_abstractions(self, chat_id: int, l0_abstract: str, l1_overview: str):
        """Обновляет сжатые уровни контекста (L0 и L1) и очищает временную память L2."""
        # Гарантируем, что строка с chat_id существует перед UPDATE
        self.ensure_session(chat_id)
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                # 1. Записываем новые абстракции
                cursor.execute("""
                    UPDATE ai_sessions 
                    SET l0_abstract = ?, l1_overview = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE chat_id = ?
                """, (l0_abstract, l1_overview, chat_id))
                
                # 2. Очищаем слой L2
                cursor.execute("DELETE FROM ai_session_messages WHERE chat_id = ?", (chat_id,))
                conn.commit()
                logger.info(f"[SQLite] Сессия чата {chat_id} успешно сагрегирована. Слой L2 очищен.")
        except sqlite3.Error as e:
            logger.error(f"[SQLite Ошибка] Не удалось обновить abstraction сессии {chat_id}: {e}")