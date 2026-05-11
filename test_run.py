import sqlite3
from logger import agent_logger

DB_NAME = "state.db"

def test_dod():
    source_name = "CoreBootstrapping"
    agent_logger.info(source_name, "Запуск теста Definition of Done...")

    # 1. Запись пустой задачи в БД
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO tasks (title, description) VALUES (?, ?)",
            ("Пустая инициализирующая задача", "Создана в рамках теста DoD.")
        )
        task_id = cursor.lastrowid
        conn.commit()
        agent_logger.step(source_name, f"Задача создана в 'tasks' с ID: {task_id}")
    except Exception as e:
        agent_logger.error(source_name, f"Ошибка при записи задачи: {e}")
        return
    finally:
        if conn:
            conn.close()

    # 2. Проверка логирования в БД
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM agent_log ORDER BY id DESC LIMIT 1")
        last_log = cursor.fetchone()
        conn.close()

        if last_log:
            log_id, timestamp, level, source, message, meta = last_log
            agent_logger.step(source_name, f"Успешная проверка логов в БД. Последняя запись: [{level}] {message}")
            print("\n" + "="*50)
            print("ТЕСТ DOD ПРОЙДЕН УСПЕШНО:")
            print(f"ID лога в БД: {log_id}")
            print(f"Уровень: {level} | Источник: {source}")
            print(f"Сообщение: {message}")
            print("="*50)
        else:
            print("Ошибка: Запись лога не найдена в БД!")
    except Exception as e:
         agent_logger.error(source_name, f"Ошибка при чтении логов: {e}")

if __name__ == "__main__":
    test_dod()
