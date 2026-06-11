import os
import logging
import asyncio
from src.storage.sqlite_manager import SQLiteManager
from src.cognitive.memory.conversation import ConversationMemory
from src.cognitive.memory.commit_pipeline import MemoryCommitPipeline
from src.cognitive.memory.semantic import memory as semantic_memory  # Импортируем 'memory' как 'semantic_memory'
from src.core.config import DATA_DIR

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("TestVikingIntegration")

# Класс-заглушка для имитации ответов Hermes 3
class MockLLMService:
    async def generate(self, prompt: str, system_prompt: str = None) -> str:
        logger.info("[MockLLM] Получен промпт на сжатие сессии. Генерируем валидный OpenViking JSON...")
        # Модель должна вернуть строго определенный JSON
        mock_response = {
            "preferences": ["Использует WSL2 и RTX 3090", "Предпочитает кофе cold brew без сахара"],
            "entities": ["Проект lumen_brain_bot", " easycode"],
            "plans": ["Внедрить архитектуру памяти OpenViking", "Купить турник"],
            "l0_abstract": "Разработчик настраивает многоуровневую систему памяти для локального ИИ-агента.",
            "l1_overview": "В ходе сессии была успешно модифицирована SQLite база данных, настроены режимы WAL и Foreign Keys. Начата работа над интеграцией векторов в LanceDB."
        }
        import json
        return json.dumps(mock_response, ensure_ascii=False)

async def test_full_pipeline_async():
    db_path = str(DATA_DIR / "test_viking_integration.db")
    if os.path.exists(db_path): 
        os.remove(db_path)
    
    # 1. Инициализация компонентов
    db = SQLiteManager(db_path=db_path)
    conversation_memory = ConversationMemory(db)
    mock_llm = MockLLMService()
    
    # Передаем синглтон семантической памяти из твоего скрипта
    pipeline = MemoryCommitPipeline(db_manager=db, llm_service=mock_llm, semantic_memory=semantic_memory)
    
    chat_id = 55555
    
    logger.info("--- Шаг 1: Наполнение рабочей памяти L2 репликами диалога ---")
    conversation_memory.append_message(chat_id, "user", "Привет! Я работаю в WSL2 на RTX 3090, пишу проект lumen_brain_bot.")
    conversation_memory.append_message(chat_id, "assistant", "Отличная связка железа для локальных LLM. Какой следующий шаг?")
    conversation_memory.append_message(chat_id, "user", "Нужно срочно внедрить архитектуру памяти OpenViking и не забыть купить турник домой.")
    
    # Проверяем, что в L2 сейчас 3 сообщения
    messages = db.get_session_messages(chat_id)
    assert len(messages) == 3, f"Ошибка: В L2 должно быть 3 сообщения, обнаружено {len(messages)}"
    
    logger.info("--- Шаг 2: Запуск конвейера коммита сессии (Вызов Pipeline) ---")
    # Запускаем асинхронный коммит
    success = await pipeline.commit_session(chat_id)
    assert success is True, "Критическая ошибка: Пайплайн коммита завершился неудачей!"
    
    logger.info("--- Шаг 3: Проверка результатов сжатия в SQLite (L0/L1) ---")
    l0_res, l1_res = db.get_session_abstracts(chat_id)
    logger.info(f"Проверка записанного L0: {l0_res}")
    logger.info(f"Проверка записанного L1: {l1_res}")
    
    assert "Разработчик настраивает" in l0_res, "Ошибка: Неверный L0 abstract!"
    assert "модифицирована SQLite" in l1_res, "Ошибка: Неверный L1 overview!"
    
    # Проверяем, что слой L2 очистился
    messages_after = db.get_session_messages(chat_id)
    assert len(messages_after) == 0, f"Ошибка: Слой L2 не очистился! Найдено сообщений: {len(messages_after)}"
    
    logger.info("--- Шаг 4: Проверка извлечения контекста после коммита ---")
    # Теперь при запросе контекста мы должны получить только L1 Overview, так как L2 пуст
    active_context = conversation_memory.get_active_context(chat_id)
    logger.info(f"Сгенерированный контекст для нового промпта:\n{active_context}")
    assert "Краткий обзор предыдущего разговора (L1 Overview)" in active_context
    assert "модифицирована SQLite" in active_context
    assert "Working Memory L2" not in active_context  # Слой L2 должен отсутствовать в строке
    
    # Чистим временную БД
    if os.path.exists(db_path): 
        os.remove(db_path)
        
    logger.info("=== ИНТЕГРАЦИОННЫЙ ТЕСТ СВЯЗКИ ПАМЯТИ УСПЕШНО ПРОЙДЕН ===")

def main():
    asyncio.run(test_full_pipeline_async())

if __name__ == "__main__":
    main()