import sqlite3

DB_NAME = "state.db"

def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    # Включаем режим WAL для предотвращения блокировок БД
    cursor.execute("PRAGMA journal_mode=WAL;")

    # Таблица задач (должна содержать title)
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

    # Таблица логов (должна содержать level, source, message, meta)
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
    print(f"✅ База данных {DB_NAME} успешно инициализирована в режиме WAL.")

if __name__ == "__main__":
    init_db()
