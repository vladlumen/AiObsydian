import asyncio
from typing import Coroutine, Any

class TaskQueue:
    def __init__(self, concurrency: int = 1):
        # queue хранит сами задачи
        self.queue: asyncio.Queue = asyncio.Queue()
        # concurrency - сколько задач мы разрешаем делать одновременно (нам нужна 1)
        self.concurrency = concurrency
        self.workers: list[asyncio.Task] = []

    async def start(self):
        """Запускает фоновых рабочих (воркеров), которые будут разгребать очередь."""
        for i in range(self.concurrency):
            worker = asyncio.create_task(self._worker(i))
            self.workers.append(worker)
        print(f"[TaskQueue] Запущено {self.concurrency} воркеров. Очередь готова к приему.")

    async def put(self, task_name: str, coro: Coroutine[Any, Any, Any]):
        """Кладет новую задачу в конец очереди."""
        await self.queue.put((task_name, coro))
        print(f"[TaskQueue] 📥 '{task_name}' добавлена в очередь. (Всего ждет: {self.queue.qsize()})")

    async def _worker(self, worker_id: int):
        """Фоновый процесс, который бесконечно берет задачи и выполняет их."""
        while True:
            task_name, coro = await self.queue.get()
            print(f"\n[Worker-{worker_id}] ⚙️ Взял в работу: {task_name}")
            try:
                await coro  # Выполняем саму задачу
            except Exception as e:
                print(f"[Worker-{worker_id}] ❌ Ошибка в {task_name}: {e}")
            finally:
                # Сообщаем очереди, что задача завершена
                self.queue.task_done()
                print(f"[Worker-{worker_id}] ✅ Завершил: {task_name}")

# Создаем глобальную очередь с 1 воркером (строгая последовательность)
task_manager = TaskQueue(concurrency=1)