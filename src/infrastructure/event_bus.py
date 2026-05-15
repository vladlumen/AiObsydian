import asyncio
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

@dataclass
class ModelReadyEvent:
    model_name: str

@dataclass
class SystemErrorEvent:
    component: str
    error_msg: str

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
        """Публикация события. Все подписчики запускаются асинхронно."""
        event_type = type(event)
        if event_type in self._subscribers:
            print(f"[EventBus] Улетело событие: {event_type.__name__}")
            # Запускаем все обработчики параллельно
            tasks = [handler(event) for handler in self._subscribers[event_type]]
            if tasks:
                await asyncio.gather(*tasks)
        else:
            print(f"[EventBus] ⚠️ Событие {event_type.__name__} улетело в пустоту (нет подписчиков).")

# Глобальный экземпляр шины
bus = EventBus()