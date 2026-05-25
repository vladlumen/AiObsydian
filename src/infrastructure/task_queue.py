import asyncio
from typing import Any, Callable, Coroutine

class TaskQueue:
    def __init__(self):
        # Классическая асинхронная очередь
        self._queue: asyncio.Queue = asyncio.Queue()
        self._worker_task: asyncio.Task | None = None
        self._processor: Callable[[Any], Coroutine] | None = None
        self.is_processing: bool = False

    def set_processor(self, processor_func: Callable[[Any], Coroutine]):
        """Регистрируем оркестратор как главный обработчик тасков."""
        self._processor = processor_func

    def put(self, task_data: Any):
        """Инжект задачи из EventBus (не блокирует поток).
        
        task_data: tuple(task_name, coro_factory) where coro_factory is either:
          - a coroutine object (legacy, executes immediately at put time - DANGEROUS)
          - a callable that returns a coroutine (recommended, executes at worker time)
          - a tuple (callable, args_tuple) for deferred execution
        """
        self._queue.put_nowait(task_data)
        print(f"[TaskQueue] 📥 Задача добавлена в очередь. (Всего в очереди: {self._queue.qsize()})")

    async def start_workers(self):
        """Запуск ОДНОГО воркера. Строго последовательный разбор."""
        print("[TaskQueue] ⏳ Запущено 1 воркеров. Очередь переведена в последовательный режим.")
        
        while True:
            # Блокирующее ожидание новой задачи из очереди
            task = await self._queue.get()
            self.is_processing = True
            
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
                self.is_processing = False
                self._queue.task_done()

    async def wait_until_empty(self):
        """Блокирует выполнение (используется в автотестах), пока очередь не опустеет."""
        print("[TaskQueue] ⏳ Синхронизация очереди: ожидание завершения всех процессов...")
        await self._queue.join()
        print("[TaskQueue] 🎉 Все задачи из очереди успешно обработаны.")

    def is_empty(self) -> bool:
        """Возвращает True, если в очереди нет задач."""
        return self._queue.empty()

    def has_active_tasks(self) -> bool:
        """Возвращает True, если воркер сейчас выполняет активную задачу."""
        return self.is_processing


# Глобальный экземпляр для использования в других модулях
task_manager = TaskQueue()