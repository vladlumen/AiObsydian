import logging
import json
from datetime import datetime
from typing import Optional
from src.storage.sqlite_manager import SQLiteManager
# Предполагаем, что импорт вашего LLM-сервиса и семантической памяти выглядит так:
# из src.infrastructure.llm_service import llm_service
# из src.cognitive.memory.semantic import semantic_memory

logger = logging.getLogger("MemoryCommitPipeline")

OPENVIKING_COMMIT_PROMPT = """Ты — фоновый модуль стратегической памяти агента OpenViking.
Твоя задача — проанализировать лог текущей сессии диалога и извлечь три категории данных в формате JSON:
1. "preferences" — предпочтения пользователя, привычки, стек технологий, конфигурации железа.
2. "entities" — важные сущности, проекты, имена людей, локации, программные продукты.
3. "plans" — долгосрочные или краткосрочные планы, задачи, шаги реализации, которые наметил пользователь.

Дополнительно сформируй две текстовые абстракции:
- "l0_abstract": Ультра-компактная выжимка сути всей сессии (1-2 предложения) для глобального архива.
- "l1_overview": Детальный обзор контекста, который заменит текущую историю сообщений и будет подаваться на вход модели в следующем диалоге как бэкграунд.

Выведи строго валидный JSON без лишнего текста и без markdown-оберток (```json).
Структура ответа:
{
  "preferences": ["предпочтение 1", "предпочтение 2"],
  "entities": ["сущность 1", "сущность 2"],
  "plans": ["план 1", "план 2"],
  "l0_abstract": "текст",
  "l1_overview": "текст"
}

Лог сессии для анализа:
"""

class MemoryCommitPipeline:
    def __init__(self, db_manager: SQLiteManager, llm_service, semantic_memory):
        """
        :param db_manager: Инстанс SQLiteManager
        :param llm_service: Сервис для инференса локальной LLM (Hermes 3)
        :param semantic_memory: Инстанс долговременной семантической памяти (LanceDB)
        """
        self.db = db_manager
        self.llm = llm_service
        self.semantic = semantic_memory

    async def commit_session(self, chat_id: int) -> bool:
        """
        Выполняет асинхронное сжатие сессии диалога.
        Вызывается строго внутри TaskQueue / Orchestrator во избежание коллизий VRAM.
        """
        logger.info(f"[Pipeline] Начало коммита сессии для chat_id {chat_id}")
        
        # 1. Извлекаем сырые сообщения L2, которые нужно сжать
        raw_messages = self.db.get_session_messages(chat_id)
        if not raw_messages:
            logger.info(f"[Pipeline] Сессия чата {chat_id} пуста. Коммит отменен.")
            return False

        # Формируем текстовый лог для промпта
        session_log = ""
        for role, content in raw_messages:
            prefix = "User: " if role == "user" else "Assistant: "
            session_log += f"{prefix}{content}\n"

        full_prompt = OPENVIKING_COMMIT_PROMPT + session_log

        try:
            # 2. Вызов LLM (Предполагается асинхронный вызов, адаптируйте под ваш llm_service.generate)
            # Если ваш llm_service строго синхронный, вызов должен быть обернут в asyncio.to_thread
            response_text = await self.llm.generate(full_prompt, system_prompt="You are a data extraction sub-routine.")
            
            # Очищаем возможные маркеры markdown, если модель их вернула
            clean_json = response_text.replace("```json", "").replace("```", "").strip()
            data = json.loads(clean_json)
            
            l0_abstract = data.get("l0_abstract", "")
            l1_overview = data.get("l1_overview", "")
            
            # 3. Сохранение извлеченных семантических данных в долговременную память (LanceDB)
            # Формируем семантические заметки для отправки в semantic.py
            extracted_facts = []
            for pref in data.get("preferences", []):
                extracted_facts.append(f"Предпочтение пользователя: {pref}")
            for entity in data.get("entities", []):
                extracted_facts.append(f"Выявленная сущность/проект: {entity}")
            for plan in data.get("plans", []):
                extracted_facts.append(f"Намеченный план/задача: {plan}")

            if extracted_facts:
                # Отправляем факты в LanceDB семантической памяти
                # Метод сохранения адаптируйте под сигнатуру вашего src/cognitive/memory/semantic.py
                for fact in extracted_facts:
                    await self.semantic.add_fact(chat_id=chat_id, text=fact, metadata={"source": "viking_commit"})
                logger.info(f"[Pipeline] Успешно сохранено {len(extracted_facts)} фактов в LanceDB для chat_id {chat_id}")

            # 4. Обновление абстракций в SQLite и очистка L2
            self.db.update_session_abstractions(chat_id, l0_abstract, l1_overview)
            logger.info(f"[Pipeline] Коммит сессии {chat_id} успешно завершен.")
            return True

        except json.JSONDecodeError:
            logger.error(f"[Pipeline] Ошибка парсинга JSON от модели. Сырой ответ: {response_text}")
            return False
        except Exception as e:
            logger.error(f"[Pipeline] Ошибка при выполнении коммита сессии {chat_id}: {e}")
            return False