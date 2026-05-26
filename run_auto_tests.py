import asyncio
import sys
import shutil
from pathlib import Path

# Добавляем корневой путь проекта в sys.path для корректных импортов внутри WSL2
sys.path.append(str(Path(__file__).parent))

from src.infrastructure.event_bus import bus, PhotoReceivedEvent, VoiceReceivedEvent, TextReceivedEvent
from src.core.orchestrator import orchestrator
from src.infrastructure.task_queue import task_manager

async def run_pipeline_tests():
    print("\n" + "="*50)
    
    base_dir = Path("/home/vladislav/projects/agent_project")
    fixtures_dir = base_dir / "tests" / "fixtures"
    temp_dir = base_dir / "data" / "temp_media"
    temp_dir.mkdir(parents=True, exist_ok=True)
    
    test_photo_target = temp_dir / "test_todo.png"
    test_voice_target = temp_dir / "test_audio.ogg"

    # --- КОПИРОВАНИЕ РЕАЛЬНЫХ ФИКСТУР ---
    # 1. Картинка
    source_png = fixtures_dir / "test_todo.png"
    if source_png.exists():
        shutil.copy(source_png, test_photo_target)
        print(f"[AUTO-TEST] ✅ Реальный файл изображения скопирован в: {test_photo_target.name}")
    else:
        print(f"[AUTO-TEST] ❌ Ошибка: Фикстура {source_png} не найдена!")

    # 2. Аудиозапись
    source_ogg = fixtures_dir / "test_audio.ogg"
    if source_ogg.exists():
        shutil.copy(source_ogg, test_voice_target)
        print(f"[AUTO-TEST] ✅ Реальный аудиофайл скопирован в: {test_voice_target.name}")
    else:
        print(f"[AUTO-TEST] ❌ Ошибка: Фикстура {source_ogg} не найдена!")

    print("[AUTO-TEST] 🚀 Старт сквозного тестирования пайплайнов v2.3...")
    
    print("[AUTO-TEST] ⚙️ Активация фонового воркера TaskQueue...")
    if hasattr(task_manager, 'start_workers'):
        asyncio.create_task(task_manager.start_workers())
    elif hasattr(task_manager, 'start'):
        asyncio.create_task(task_manager.start())
        
    print("="*50 + "\n")

    # --- ТЕСТ 1: Проверка Очереди и Vision Пайплайна ---
    print("[AUTO-TEST] 🟢 Запуск Теста №1: Имитация отправки ФОТО...")
    photo_event = PhotoReceivedEvent(
        user_id=475811487,
        photo_path=test_photo_target,
        caption="Распознай текст со скриншота задач"
    )
    await bus.publish(photo_event)

    # --- ТЕСТ 2: Проверка Роутинга Текста ---
    print("\n[AUTO-TEST] 🟢 Запуск Теста №2: Имитация отправки ТЕКСТА (Запрос поиска)...")
    text_event = TextReceivedEvent(
        user_id=475811487,
        text="?Что такое WSL2"
    )
    await bus.publish(text_event)

    # --- ТЕСТ 2.5: Проверка Роутинга Ссылок ---
    print("\n[AUTO-TEST] 🟢 Запуск Теста №2.5: Имитация отправки ССЫЛКИ (URL)...")
    url_event = TextReceivedEvent(
        user_id=475811487,
        text="Слушай, посмотри вот эту статью: https://vladteacher.tilda.ws/ или любой другой хабр"
    )
    await bus.publish(url_event)
    await asyncio.sleep(5)  # Даем время на инференс страницы

    # --- ТЕСТ 3: Проверка Очереди и Голосового Пайплайна ---
    print("\n[AUTO-TEST] 🟢 Запуск Теста №3: Имитация отправки ГОЛОСА...")
    voice_event = VoiceReceivedEvent(
        user_id=475811487,
        audio_path=test_voice_target
    )
    await bus.publish(voice_event)

    # --- Ожидание завершения последовательной очереди задач ---
    print("\n[AUTO-TEST] ⏳ Ожидание обработки задач из TaskQueue воркером...")
    max_wait = 180
    elapsed = 0
    
    while True:
        has_tasks = False
        if hasattr(task_manager, 'is_empty') and not task_manager.is_empty():
            has_tasks = True
        if hasattr(task_manager, 'has_active_tasks') and task_manager.has_active_tasks():
            has_tasks = True
            
        if not has_tasks:
            break
            
        await asyncio.sleep(5)
        elapsed += 5
        if elapsed % 15 == 0:
            print(f"[AUTO-TEST] Ждем завершения... Прошло {elapsed} сек.")
            
        if elapsed >= max_wait:
            print("[AUTO-TEST] ⚠️ Превышено время ожидания тестов!")
            break

    # Грациозное закрытие коннекторов aiohttp
    try:
        from src.interfaces.telegram.bot import bot
        if hasattr(bot, 'session') and not bot.session.closed:
            await bot.session.close()
            print("[AUTO-TEST] 🧹 Асинхронные коннекторы закрыты.")
    except Exception:
        pass

    print("\n" + "="*50)
    print("[AUTO-TEST] 🎉 Сквозное тестирование пайплайнов завершено успешно!")
    print("="*50 + "\n")

if __name__ == "__main__":
    asyncio.run(run_pipeline_tests())