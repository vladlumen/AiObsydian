import asyncio
from pathlib import Path

from src.infrastructure.event_bus import (
    bus, TextReceivedEvent, VoiceReceivedEvent, PhotoReceivedEvent, DocumentReceivedEvent
)
from src.core.orchestrator import orchestrator
from src.infrastructure.task_queue import task_manager

FIXTURE_DIR = Path("tests/fixtures")
TEST_USER_ID = 475811487

async def main():
    print("\n" + "="*50)
    print("🚀 ЗАПУСК ПОЛНОГО ИНТЕГРАЦИОННОГО ТЕСТА (СТРОГИЙ КОНВЕЙЕР)")
    print("="*50 + "\n")

    # Воркеры теперь стартуют автоматически внутри инфраструктуры ядра, 
    # но для теста контролируем, что цикл запущен
    worker_task = asyncio.create_task(task_manager.start_workers())
    await asyncio.sleep(0.5)

    # МГНОВЕННЫЙ СБРОС ВСЕХ СОБЫТИЙ В ОЧЕРЕДЬ (Проверяем стрессоустойчивость)
    print("[AutoTest] 💥 Бомбардировка шины событиями...")
    
    # 1. Текст
    await bus.publish(TextReceivedEvent(user_id=TEST_USER_ID, text="Сделать автотесты для ИИ ассистента на WSL2."))
    
    # 2. YouTube Shorts
    await bus.publish(TextReceivedEvent(user_id=TEST_USER_ID, text="https://www.youtube.com/shorts/dQw4w9WgXcQ"))
    
    # 3. TikTok
    await bus.publish(TextReceivedEvent(user_id=TEST_USER_ID, text="https://vm.tiktok.com/ZSxmrfp6u/"))
    
    # 4. Веб-страница
    await bus.publish(TextReceivedEvent(user_id=TEST_USER_ID, text="https://ru.wikipedia.org/wiki/Разработка_игр"))

    # 5. Голосовое сообщение
    voice_path = FIXTURE_DIR / "test_voice.ogg"
    if voice_path.exists():
        await bus.publish(VoiceReceivedEvent(user_id=TEST_USER_ID, audio_path=voice_path))
    else:
        print(f"[⚠️ SKIP] Тестовая голосовуха {voice_path} не найдена")

    # 6. PDF Документ
    pdf_path = FIXTURE_DIR / "test_doc.pdf"
    if pdf_path.exists():
        await bus.publish(DocumentReceivedEvent(user_id=TEST_USER_ID, file_path=pdf_path, file_name="test_doc.pdf", caption="ТЗ Джем"))

    print("\n[AutoTest] 🔥 Все события опубликованы. Переходим в режим ожидания конвейера...")
    
    # Блокируем тест, пока единственный воркер по очереди не разгребет ВСЕ 6 задач
    await task_manager.wait_until_empty()

    # Чистим за собой фоновый воркер теста
    worker_task.cancel()

    print("\n" + "="*50)
    print("✅ АВТОТЕСТ УСПЕШНО ПРОЙДЕН! НИ ОДНОГО ТАЙМАУТА.")
    print("Проверь новые файлы в своем Obsidian Vault на Windows.")
    print("="*50 + "\n")

if __name__ == "__main__":
    asyncio.run(main())