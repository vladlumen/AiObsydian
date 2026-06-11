import re
from datetime import datetime, timedelta
from src.infrastructure.task_queue import task_manager
from src.infrastructure.logger import logger

# ИСПРАВЛЕНО: Глобальный импорт шины и типов событий удален из шапки файла,
# чтобы предотвратить преждевременную блокировку интерпретатора Python.

def is_rag_query(text: str) -> bool:
    """Поисковый RAG-запрос: префикс «?» или вопрос с «?» в конце."""
    t = text.strip()
    if not t:
        return False
    return t.startswith("?") or t.endswith("?")


class Orchestrator:
    def __init__(self):
        pass

    def start(self):
        """Явный запуск прослушивания шины событий после инициализации всех модулей."""
        # Локальный импорт инфраструктуры событий строго в момент запуска рантайма
        from src.infrastructure.event_bus import bus, VoiceReceivedEvent, TextReceivedEvent, PhotoReceivedEvent, DocumentReceivedEvent
        
        bus.subscribe(VoiceReceivedEvent, self.handle_voice_event)
        bus.subscribe(TextReceivedEvent, self.handle_text_event)
        bus.subscribe(PhotoReceivedEvent, self.handle_photo_event)
        bus.subscribe(DocumentReceivedEvent, self.handle_document_event)
        print("[Orchestrator] Успешно запущен и слушает шину событий в легковесном режиме v2.5.")

    async def _check_session_timeout(self, chat_id: int):
        """
        Проверяет таймаут неактивности сессии по OpenViking-pattern.
        Если сессия устарела, отправляет задачу сжатия в TaskQueue.
        """
        from src.core.config import SESSION_TIMEOUT_MINUTES
        from src.storage.sqlite_manager import SQLiteManager
        from src.cognitive.memory.commit_pipeline import MemoryCommitPipeline
        from src.cognitive.memory.semantic import memory as semantic_memory
        from src.cognitive.llm_service import llm  # Твой локальный инференс-сервис
        
        db = SQLiteManager()
        
        # Запрашиваем время последнего обновления сессии
        with db._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT updated_at FROM ai_sessions WHERE chat_id = ?", (chat_id,))
            row = cursor.fetchone()
            
        if row:
            # Преобразуем строку TIMESTAMP из SQLite в объект datetime
            try:
                last_update = datetime.strptime(row[0], "%Y-%m-%d %H:%M:%S")
            except ValueError:
                # На случай если формат штампа в SQLite отличается (например, с миллисекундами)
                last_update = datetime.fromisoformat(row[0].replace("Z", "+00:00"))
                
            # Сверяем разницу с текущим временем UTC
            if datetime.utcnow() - last_update > timedelta(minutes=SESSION_TIMEOUT_MINUTES):
                print(f"[Orchestrator] Сессия чата {chat_id} превысила таймаут неактивности. Ставим коммит в очередь.")
                
                pipeline = MemoryCommitPipeline(db_manager=db, llm_service=llm, semantic_memory=semantic_memory)
                # Передаем асинхронную функцию коммита в синхронный менеджер задач (допуская, что add_task принимает корутины)
                task_manager.add_task(pipeline.commit_session, chat_id)

    async def handle_text_event(self, event):
        """Маршрутизация текстовых запросов через TaskQueue."""
        chat_id = event.user_id  # Один chat_id = одна сессия пользователя
        raw_text = event.text.strip()
        
        # 1. Проверяем таймаут и при необходимости сжимаем предыдущую сессию
        await self._check_session_timeout(chat_id)
        
        # 2. Передаем реплику пользователя в слой рабочей памяти L2
        from src.storage.sqlite_manager import SQLiteManager
        from src.cognitive.memory.conversation import ConversationMemory
        conversation_memory = ConversationMemory(SQLiteManager())
        conversation_memory.append_message(chat_id, "user", raw_text)
        
        # 3. Маршрутизация по типам задач
        if is_rag_query(raw_text):
            from src.agents.rag_agent import rag_agent
            print(f"[Orchestrator] Поисковый RAG-запрос от {chat_id} отправлен в очередь.")
            task_manager.add_task(rag_agent.process_query, event)
        else:
            from src.agents.note_generator_agent import note_generator
            print(f"[Orchestrator] Заметка от {chat_id} отправлена в очередь.")
            task_manager.add_task(note_generator.process_text, event)

    async def handle_photo_event(self, event):
        """Обработка события получения фото внутри Оркестратора."""
        logger.info(f"[Orchestrator] Получено фото от пользователя {event.user_id}")
        
        # Контроль сессии для мультимодального ввода
        await self._check_session_timeout(event.user_id)
        
        # Ленивый импорт класса
        from src.agents.vision_agent import VisionAgent
        
        print(f"[Orchestrator] Фото-запрос от {event.user_id} отправлен в очередь.")
        agent_instance = VisionAgent()
        task_manager.add_task(agent_instance.process_photo, event)

    async def handle_voice_event(self, event):
        print(f"[Orchestrator] Аудио-запрос от {event.user_id} отправлен в очереди.")
        await self._check_session_timeout(event.user_id)
        
        from src.agents.voice_agent import voice_agent
        task_manager.add_task(voice_agent.process_voice, event)

    async def handle_document_event(self, event):
        print(f"[Orchestrator] Документ от {event.user_id} отправлен в очередь.")
        await self._check_session_timeout(event.user_id)
        
        from src.agents.document_agent import document_agent
        task_manager.add_task(document_agent.process_document, event)


# Синглтон инициализируется без побочных эффектов для sys.modules
orchestrator = Orchestrator()