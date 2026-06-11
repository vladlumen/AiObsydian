import os
import logging
from src.storage.sqlite_manager import SQLiteManager
from src.core.config import DATA_DIR

# Настройка логирования для вывода в консоль
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("TestSQLiteMemory")

def test_pipeline():
    logger.info("=== Запуск интеграционного теста памяти OpenViking (Шаг 3.1) ===")
    
    # 1. Инициализация менеджера
    db_path = str(DATA_DIR / "test_state.db")
    # Удаляем старую тестовую БД, если она осталась от предыдущих запусков
    if os.path.exists(db_path):
        os.remove(db_path)
        
    db = SQLiteManager(db_path=db_path)
    
    # 2. Проверка режимов PRAGMA (WAL и Foreign Keys) через соединение менеджера
    with db._get_connection() as conn:
        cursor = conn.cursor()
        
        cursor.execute("PRAGMA journal_mode;")
        wal_mode = cursor.fetchone()[0]
        logger.info(f"Проверка WAL: {wal_mode} (Ожидается: wal)")
        assert wal_mode.lower() == "wal", "Критическая ошибка: режим WAL не включен!"
        
        cursor.execute("PRAGMA foreign_keys;")
        fk_mode = cursor.fetchone()[0]
        logger.info(f"Проверка Foreign Keys: {fk_mode} (Ожидается: 1)")
        assert fk_mode == 1, "Критическая ошибка: Внешние ключи выключены в SQLite!"

    # 3. Тестирование CRUD для сессий и сообщений
    test_chat_id = 999999
    
    logger.info("Добавление сообщений в слой L2...")
    db.add_session_message(test_chat_id, "user", "Привет, как дела?")
    db.add_session_message(test_chat_id, "assistant", "Отлично! Чем могу помочь?")
    db.add_session_message(test_chat_id, "user", "Расскажи про архитектуру памяти.")
    
    # Проверяем, что сообщения физически записались
    messages = db.get_session_messages(test_chat_id)
    logger.info(f"Извлечено сообщений из L2: {len(messages)} (Ожидается: 3)")
    assert len(messages) == 3, "Ошибка: Количество записанных сообщений не совпадает!"
    assert messages[0][0] == "user" and messages[1][0] == "assistant"

    # 4. Тестирование обновления абстракций (Сжатие сессии)
    logger.info("Тестирование коммита сессии (Перенос L2 -> L0/L1)...")
    l0_test = "Пользователь интересовался делами и архитектурой памяти."
    l1_test = "Обсуждение базовых вопросов и структуры слоев контекста."
    
    db.update_session_abstractions(test_chat_id, l0_abstract=l0_test, l1_overview=l1_test)
    
    # Проверяем, что слои L0 и L1 обновились
    l0_res, l1_res = db.get_session_abstracts(test_chat_id)
    logger.info(f"Проверка L0: '{l0_res}'")
    logger.info(f"Проверка L1: '{l1_res}'")
    assert l0_res == l0_test, "Ошибка: Данные L0 повреждены или не записались!"
    assert l1_res == l1_test, "Ошибка: Данные L1 повреждены или не записались!"
    
    # Проверяем, что слой L2 автоматически очистился после коммита
    messages_after_commit = db.get_session_messages(test_chat_id)
    logger.info(f"Количество сообщений L2 после коммита: {len(messages_after_commit)} (Ожидается: 0)")
    assert len(messages_after_commit) == 0, "Критическая ошибка: Слой L2 не очистился после обновления абстракций!"
    
    # 5. Тестирование каскадного удаления (ON DELETE CASCADE)
    logger.info("Тестирование каскадного удаления...")
    db.add_session_message(test_chat_id, "user", "Проверка каскада")
    
    with db._get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM ai_sessions WHERE chat_id = ?", (test_chat_id,))
        conn.commit()
        
        cursor.execute("SELECT COUNT(*) FROM ai_session_messages WHERE chat_id = ?", (test_chat_id,))
        count = cursor.fetchone()[0]
        logger.info(f"Осталось дочерних сообщений после удаления сессии: {count} (Ожидается: 0)")
        assert count == 0, "Критическая ошибка: Каскадное удаление ON DELETE CASCADE не сработало!"

    # Чистим за собой тестовый файл
    if os.path.exists(db_path):
        os.remove(db_path)
        
    logger.info("=== ТЕСТ УСПЕШНО ПРОЙДЕН. Ошибок не обнаружено. ===")

if __name__ == "__main__":
    test_pipeline()