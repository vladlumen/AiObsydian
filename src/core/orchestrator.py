import re
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

    async def handle_text_event(self, event):
        """Маршрутизация текстовых запросов через TaskQueue."""
        raw_text = event.text.strip()
        
        if is_rag_query(raw_text):
            from src.agents.rag_agent import rag_agent
            print(f"[Orchestrator] Поисковый RAG-запрос от {event.user_id} отправлен в очередь.")
            task_manager.add_task(rag_agent.process_query, event)
        else:
            from src.agents.note_generator_agent import note_generator
            print(f"[Orchestrator] Заметка от {event.user_id} отправлена в очередь.")
            task_manager.add_task(note_generator.process_text, event)

    async def handle_photo_event(self, event):
        """Обработка события получения фото внутри Оркестратора."""
        logger.info(f"[Orchestrator] Получено фото от пользователя {event.user_id}")
        
        # Ленивый импорт класса
        from src.agents.vision_agent import VisionAgent
        
        print(f"[Orchestrator] Фото-запрос от {event.user_id} отправлен в очередь.")
        agent_instance = VisionAgent()
        task_manager.add_task(agent_instance.process_photo, event)

    async def handle_voice_event(self, event):
        print(f"[Orchestrator] Аудио-запрос от {event.user_id} отправлен в очереди.")
        from src.agents.voice_agent import voice_agent
        task_manager.add_task(voice_agent.process_voice, event)

    async def handle_document_event(self, event):
        print(f"[Orchestrator] Документ от {event.user_id} отправлен в очередь.")
        from src.agents.document_agent import document_agent
        task_manager.add_task(document_agent.process_document, event)


# Синглтон инициализируется без побочных эффектов для sys.modules
orchestrator = Orchestrator()