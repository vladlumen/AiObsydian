import asyncio
import os
import shutil
import logging
from pathlib import Path
from typing import Callable, Any, Coroutine, Optional

logger = logging.getLogger("TaskQueue")

class TaskQueue:
    def __init__(self):
        self.queue: asyncio.Queue = asyncio.Queue()
        self.is_running = False
        self.worker_task: Optional[asyncio.Task] = None
        self.processor: Optional[Callable[..., Coroutine[Any, Any, Any]]] = None
        self.temp_media_dir = Path(__file__).parent.parent.parent / "data" / "temp_media"

    def set_processor(self, processor_func: Callable[..., Coroutine[Any, Any, Any]]):
        """Устанавливает главный процессор для обработки задач из очереди."""
        self.processor = processor_func
        print("[TaskQueue] 🎯 Процессор задач успешно привязан к Оркестратору.")

    def clear_temp_media(self):
        """Очищает папку temp_media от остаточных бинарных файлов."""
        try:
            if not self.temp_media_dir.exists():
                self.temp_media_dir.mkdir(parents=True, exist_ok=True)
                return

            extensions = ('.ogg', '.mp3', '.wav', '.jpg', '.jpeg', '.png', '.pdf', '.docx')
            deleted_count = 0

            for item in self.temp_media_dir.iterdir():
                if item.is_file() and item.suffix.lower() in extensions:
                    os.remove(item)
                    deleted_count += 1

            if deleted_count > 0:
                print(f"[TaskQueue] 🧹 Авто-очистка: удалено {deleted_count} временных медиа-файлов.")
        except Exception as e:
            print(f"[TaskQueue ⚠️ Ошибка очистки мусора]: {e}")

    def add_task(self, task_func: Callable[..., Coroutine[Any, Any, Any]], *args, **kwargs):
        """Добавляет асинхронную задачу в очередь."""
        self.queue.put_nowait((task_func, args, kwargs))
        print(f"[TaskQueue] 📥 Задача добавлена в очередь. (Всего в очереди: {self.queue.qsize()})")

    async def start(self):
        """Запускает фоновый последовательный воркер."""
        if self.is_running:
            return
        self.is_running = True
        self.worker_task = asyncio.create_task(self._worker_loop())
        print("[TaskQueue] 🟢 Фоновый воркер успешно запущен в последовательном режиме.")

    async def stop(self):
        """Останавливает воркер очереди."""
        self.is_running = False
        if self.worker_task:
            self.worker_task.cancel()
            try:
                await self.worker_task
            except asyncio.CancelledError:
                pass
        print("[TaskQueue] 🛑 Фоновый воркер остановлен.")

    async def _worker_loop(self):
        """Бесконечный цикл последовательного выполнения задач."""
        while self.is_running:
            try:
                # Ожидаем задачу из очереди
                task_func, args, kwargs = await self.queue.get()
                
                # Запускаем выполнение задачи
                await task_func(*args, **kwargs)
                
                # Фиксируем выполнение в asyncio.Queue
                self.queue.task_done()
                
                # СТРОГО ПОСЛЕ выполнения задачи вызываем очистку папки temp_media
                self.clear_temp_media()

            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"[TaskQueue ❌ Критическая ошибка воркера]: {e}")
                self.clear_temp_media()
                await asyncio.sleep(1)

task_manager = TaskQueue()