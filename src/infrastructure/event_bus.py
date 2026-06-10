import asyncio
import inspect
from dataclasses import dataclass
from typing import Callable, Dict, List, Any
from pathlib import Path

# --- Определяем типы событий (Typed Events) ---

@dataclass
class VoiceReceivedEvent:
    user_id: int
    audio_path: Path

@dataclass
class TextReceivedEvent:
    user_id: int
    text: str
    is_ocr: bool = False  # ИСПРАВЛЕНО: Маркер происхождения текста для защиты от коллизий RAG

@dataclass
class ModelReadyEvent:
    model_name: str

@dataclass
class SystemErrorEvent:
    component: str
    error_msg: str

@dataclass
class PhotoReceivedEvent:
    user_id: int
    photo_path: Path
    caption: str = ""

@dataclass
class DocumentReceivedEvent:
    user_id: int
    file_path: Path
    file_name: str
    caption: str = ""

# --- Сама Шина Событий (Pub/Sub) ---

class EventBus:
    def __init__(self):
        # Словарь: Тип события -> Список функций-обработчиков
        self._subscribers: Dict[type, List[Callable]] = {}

    def subscribe(self, event_type: type, handler: Callable):
        """Подписка на конкретное событие."""
        if event_type not in self._subscribers:
            self._subscribers[event_type] = []
        self._subscribers[event_type].append(handler)
        print(f"[EventBus] Подписан обработчик {handler.__name__} на {event_type.__name__}")

    async def publish(self, event: Any):
        """Публикация события. Подписчики-корутины запускаются асинхронно."""
        event_type = type(event)
        if event_type in self._subscribers:
            print(f"[EventBus] Улетело событие: {event_type.__name__}")
            
            tasks = []
            for handler in self._subscribers[event_type]:
                res = handler(event)
                # Fail-safe проверка: добавляем в gather только то, что можно завеймить
                if inspect.iscoroutine(res) or inspect.isawaitable(res):
                    tasks.append(res)
                else:
                    # Если функция была синхронной, она уже выполнилась, аварии нет
                    print(f"[EventBus] ⚠️ Обработчик {handler.__name__} выполнился синхронно.")
                    
            if tasks:
                await asyncio.gather(*tasks)
        else:
            print(f"[EventBus] ⚠️ Событие {event_type.__name__} улетело в пустоту (нет подписчиков).")

# Глобальный экземпляр шины
bus = EventBus()