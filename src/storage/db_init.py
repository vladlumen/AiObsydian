import sqlite3
from src.core.config import DATA_DIR

# Формируем абсолютный путь к единой базе данных
DB_PATH = DATA_DIR / "state.db"

def init_db():
    # Гарантируем, что папка data/ существует перед созданием sqlite подключения
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    
    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()

    # Включаем режим WAL для предотвращения блокировок БД
    cursor.execute("PRAGMA journal_mode=WAL;")

    # Таблица задач
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS tasks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        description TEXT,
        status TEXT DEFAULT 'pending',
        priority INTEGER DEFAULT 1,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    """)

    # Таблица логов
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS agent_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
        level TEXT NOT NULL,
        source TEXT NOT NULL,
        message TEXT NOT NULL,
        meta TEXT
    )
    """)

    # Триггер для автообновления времени изменения задачи
    cursor.execute("""
    CREATE TRIGGER IF NOT EXISTS update_task_timestamp 
    AFTER UPDATE ON tasks
    BEGIN
        UPDATE tasks SET updated_at = CURRENT_TIMESTAMP WHERE id = old.id;
    END;
    """)

    conn.commit()
    conn.close()
    print(f"✅ База данных {DB_PATH} успешно инициализирована в режиме WAL.")

if __name__ == "__main__":
    init_db()