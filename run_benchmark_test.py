import asyncio
from pathlib import Path

from src.infrastructure.event_bus import bus, TextReceivedEvent
from src.infrastructure.task_queue import task_manager
from src.core import config
from src.core.orchestrator import orchestrator  # Import to ensure handlers are registered

TEST_USER_ID = 475811487

async def main():
    print("\n" + "="*50)
    print("📊 ЗАПУСК СРАВНИТЕЛЬНОГО БЕНЧМАРКА МОДЕЛЕЙ (HERMES VS QWEN)")
    print("="*50 + "\n")

    # Жестко включаем режим сравнения на время этого теста
    config.COMPARE_MODE = True
    print(f"[Benchmark] Режим сравнения АКТИВИРОВАН.")
    print(f"[Benchmark] Тестируемые модели: {list(config.AVAILABLE_MODELS.values())}\n")

    # Инициализация воркера очереди
    worker_task = asyncio.create_task(task_manager.start_workers())
    await asyncio.sleep(0.5)

    # Отправляем один сложный концептуальный запрос для сравнения логики
    print("[Benchmark] Отправка тестового запроса в шину...")
    await bus.publish(TextReceivedEvent(
        user_id=TEST_USER_ID,
        text="Различие между синхронным и асинхронным кодом в геймдеве на примере Unity C#. Плюсы и минусы для производительности."
    ))

    print("\n[Benchmark] Ожидание завершения генерации обеими моделями...")
    await task_manager.wait_until_empty()

    # Выключаем воркер
    worker_task.cancel()

    print("\n" + "="*50)
    print("✅ БЕНЧМАРК ЗАВЕРШЕН!")
    print("Открой Obsidian и сравни файлы:")
    print("1. Новая идея (HERMES)...md")
    print("2. Новая идея (QWEN)...md")
    print("="*50 + "\n")

if __name__ == "__main__":
    asyncio.run(main())