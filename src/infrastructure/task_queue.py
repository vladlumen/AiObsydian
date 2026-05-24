import asyncio
from typing import Any, Callable, Coroutine

class TaskQueue:
    def __init__(self):
        # Классическая асинхронная очередь
        self._queue: asyncio.Queue = asyncio.Queue()
        self._worker_task: asyncio.Task | None = None
        self._processor: Callable[[Any], Coroutine] | None = None

    def set_processor(self, processor_func: Callable[[Any], Coroutine]):
        """Регистрируем оркестратор как главный обработчик тасков."""
        self._processor = processor_func

    def put(self, task_data: Any):
        """Инжект задачи из EventBus (не блокирует поток)."""
        self._queue.put_nowait(task_data)
        print(f"[TaskQueue] 📥 Задача добавлена в очередь. (Всего в очереди: {self._queue.qsize()})")

    async def start_workers(self):
        """Запуск ОДНОГО воркера. Строго последовательный разбор."""
        print("[TaskQueue] ⏳ Запущено 1 воркеров. Очередь переведена в последовательный режим.")
        
        while True:
            # Блокирующее ожидание новой задачи из очереди
            task = await self._queue.get()
            
            try:
                if self._processor:
                    # КРИТИЧЕСКИЙ МЕНЕДЖМЕНТ: Жесткий await. 
                    # Следующая задача не начнется, пока оркестратор полностью не запишет MD-файл
                    await self._processor(task)
                else:
                    print("[TaskQueue] ⚠️ Ошибка: Обработчик задач не зарегистрирован!")
            except Exception as e:
                print(f"[TaskQueue] ❌ Критическая ошибка при обработке таска: {e}")
            finally:
                # Фиксируем закрытие таска для метода join()
                self._queue.task_done()

    async def wait_until_empty(self):
        """Блокирует выполнение (используется в автотестах), пока очередь не опустеет."""
        print("[TaskQueue] ⏳ Синхронизация очереди: ожидание завершения всех процессов...")
        await self._queue.join()
        print("[TaskQueue] 🎉 Все задачи из очереди успешно обработаны.")


# Глобальный экземпляр для использования в других модулях
task_manager = TaskQueue()