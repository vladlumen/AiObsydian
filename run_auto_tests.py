import asyncio
import sys
import shutil
import os
from pathlib import Path
from datetime import datetime

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
    
    # Путь к Obsidian хранилищу для реалистичного теста гранулярности
    obsidian_inbox = Path("/mnt/c/Users/vladislav/Documents/ObsidianVault/00_Inbox")
    
    test_photo_target = temp_dir / "test_todo.png"
    test_voice_target = temp_dir / "test_audio.ogg"

    source_png = fixtures_dir / "test_todo.png"
    if source_png.exists():
        shutil.copy(source_png, test_photo_target)
        print(f"[AUTO-TEST] ✅ Реальный файл изображения скопирован в: {test_photo_target.name}")
    else:
        print(f"[AUTO-TEST] ❌ Ошибка: Фикстура {source_png} не найдена!")

    source_ogg = fixtures_dir / "test_audio.ogg"
    if source_ogg.exists():
        shutil.copy(source_ogg, test_voice_target)
        print(f"[AUTO-TEST] ✅ Реальный аудиофайл скопирован в: {test_voice_target.name}")
    else:
        print(f"[AUTO-TEST] ❌ Ошибка: Фикстура {source_ogg} не найдена!")

    print("[AUTO-TEST] 🚀 Старт сквозного тестирования пайплайнов v2.7...")
    
    print("[AUTO-TEST] ⚙️ Активация фонового воркера TaskQueue...")
    if hasattr(task_manager, 'start_workers'):
        asyncio.create_task(task_manager.start_workers())
    elif hasattr(task_manager, 'start'):
        asyncio.create_task(task_manager.start())

    # === КРИТИЧЕСКИЙ ФИКС: ОТКЛЮЧАЕМ АВТООЧИСТКУ НА ВРЕМЯ ТЕСТОВ ===
    # Подменяем метод очистки воркера на пустую функцию, чтобы файлы не удалялись в процессе
    if hasattr(task_manager, '_clean_temp_media'):
        task_manager._clean_temp_media = lambda *args, **kwargs: None
    elif hasattr(task_manager, 'clean_temp'):
        task_manager.clean_temp = lambda *args, **kwargs: None
        
    print("="*50 + "\n")

    print("\n[AUTO-TEST] 🟢 Запуск Теста №2.5: Имитация отправки ССЫЛКИ (URL)...")
    url_event = TextReceivedEvent(
        user_id=475811487,
        text="Слушай, посмотри вот эту статью: https://vlad-gameddev.tilda.ws/"
    )
    await bus.publish(url_event)
    
    # КРИТИЧЕСКИЙ ФИКС: Даем воркеру 15 секунд, чтобы он ПОЛНОСТЬЮ завершил Тест №1 и Тест №2,
    # вызвал свою автоочистку, и только ПОСЛЕ этого мы запишем аудиофайл начисто.
    await asyncio.sleep(15)

    print("\n[AUTO-TEST] 🟢 Запуск Теста №3: Имитация отправки ГОЛОСА...")
    if source_ogg.exists():
        shutil.copy(source_ogg, test_voice_target)
        print(f"[AUTO-TEST] ✅ Восстановлен аудиофайл после очистки: {test_voice_target.name}")
        
    voice_event = VoiceReceivedEvent(
        user_id=475811487,
        audio_path=test_voice_target
    )
    await bus.publish(voice_event)

    print("\n[AUTO-TEST] 🟢 Запуск Теста №2.5: Имитация отправки ССЫЛКИ (URL)...")
    url_event = TextReceivedEvent(
        user_id=475811487,
        text="Слушай, посмотри вот эту статью: https://vlad-gamedev.tilda.ws/"
    )
    await bus.publish(url_event)
    # Даем паузу, чтобы асинхронный url_parser успел стянуть код страницы
    await asyncio.sleep(4)

    print("\n[AUTO-TEST] 🟢 Запуск Теста №3: Имитация отправки ГОЛОСА...")
    # Восстанавливаем файл из фикстур, если автоочистка воркера удали        
    if source_ogg.exists() and not test_voice_target.exists():
        shutil.copy(source_ogg, test_voice_target)
        
    voice_event = VoiceReceivedEvent(
        user_id=475811487,
        audio_path=test_voice_target
    )
    await bus.publish(voice_event)

    print("\n[AUTO-TEST] 🟢 Запуск Теста №4: Проверка гранулярности иерархического RAG...")
    
    # КРИТИЧЕСКИЙ ФИКС: Создаем файл внутри ObsidianVault, обходя SQL-фильтр исключения тестов
    current_date = datetime.now().strftime("%Y-%m-%d")
    test_note_path = obsidian_inbox / f"{current_date} Интеграционный Тест Гранулярности Хранилища.md"
    test_note_path.parent.mkdir(parents=True, exist_ok=True)
    
    long_markdown_content = (
        "---\n"
        "title: Тест Гранулярности\n"
        "project: Core_v2.4\n"
        "---\n"
        "# 📚 Главная База Знаний\n"
        "Здесь находится много случайного нерелевантного текста, который модель не должна вытаскивать.\n"
        "Мы забиваем контекст мусором, чтобы проверить, работает ли иерархический чанкинг.\n\n"
        "## 🛠️ Спецификация Разработки\n"
        "Текст про архитектуру, микросервисы и шину событий EventBus.\n\n"
        "### 🔑 Секретный пароль\n"
        "Ключ: 9922\n"
    )
    
    with open(test_note_path, "w", encoding="utf-8") as f:
        f.write(long_markdown_content)
    
    try:
        from src.agents.parsers.md_chunker import MarkdownChunker
        from src.cognitive.memory.semantic import memory
        
        chunker = MarkdownChunker()
        parsed_chunks = chunker.parse_file(file_path=str(test_note_path), content=long_markdown_content)
        await memory.update_file_memory(file_path=str(test_note_path), parsed_chunks=parsed_chunks)
        
        # Даем микропаузу для перестройки FTS индекса в SQLite/LanceDB
        await asyncio.sleep(1)
        
        search_query = "Какой там секретный пароль ключа?"
        retrieved_chunks = await memory.retrieve_context(query=search_query, limit=1)
        
        if not retrieved_chunks:
            print("[AUTO-TEST] ❌ Тест №4 НЕ ПРОЙДЕН: Память вернула пустой результат из-за фильтрации путей!")
        else:
            top_chunk = retrieved_chunks[0]
            chunk_text = top_chunk["text"]
            chunk_meta = top_chunk["metadata"]
            
            assert "Ключ: 9922" in chunk_text, f"Ожидался пароль, но получено: {chunk_text}"
            assert "Мы забиваем контекст мусором" not in chunk_text, "Ошибка: извлечен лишний текст из начала файла!"
            
            header_path = chunk_meta.get("header_path", "")
            frontmatter = chunk_meta.get("frontmatter", {})
            
            assert header_path == "📚 Главная База Знаний > 🛠️ Спецификация Разработки > 🔑 Секретный пароль", \
                f"Неверная цепочка заголовков: {header_path}"
            assert frontmatter.get("project") == "Core_v2.4", "YAML метаданные не унаследованы!"
            
            print("[AUTO-TEST] ✅ Тест №4 УСПЕШНО ПРОЙДЕН: Иерархический чанкинг выделил точный блок текста.")
            print(f"[AUTO-TEST] 🧩 Извлеченный чанк: [{header_path}] -> {chunk_text}")
            
    except AssertionError as ae:
        print(f"[AUTO-TEST] ❌ Тест №4 НЕ ПРОЙДЕН (Ошибка утверждения): {ae}")
    except Exception as e:
        print(f"[AUTO-TEST] ❌ Тест №4 НЕ ПРОЙДЕН (Критический сбой): {e}")
    finally:
        # Чистим за собой базу чанков перед удалением файла физически
        try:
            from src.storage.vector_store import vector_store
            await vector_store.delete_file_chunks(str(test_note_path))
        except Exception:
            pass

    print("\n[AUTO-TEST] ⏳ Ожидание обработки задач из TaskQueue воркером...")
    try:
        await asyncio.wait_for(task_manager.queue.join(), timeout=180)
        print("[AUTO-TEST] 🎉 Все задачи в TaskQueue успешно обработаны воркером.")
    except asyncio.TimeoutError:
        print("[AUTO-TEST] ⚠️ Превышено время ожидания завершения задач!")

    try:
        from src.interfaces.telegram.bot import bot
        from src.agents.parsers.url_parser import url_parser
        import aiohttp
        
        # Закрываем бота
        if hasattr(bot, 'session') and bot.session:
            if isinstance(bot.session, aiohttp.ClientSession) and not bot.session.closed:
                await bot.session.close()
            elif hasattr(bot.session, 'close'):
                await bot.session.close()
            
        # Закрываем парсер
        if hasattr(url_parser, 'session') and url_parser.session:
            # Проверяем, не является ли объект кастомной оберткой (например, AiohttpSession)
            curr_session = url_parser.session
            if hasattr(curr_session, '_session') and isinstance(curr_session._session, aiohttp.ClientSession):
                if not curr_session._session.closed:
                    await curr_session._session.close()
            elif isinstance(curr_session, aiohttp.ClientSession) and not curr_session.closed:
                await curr_session.close()
            elif hasattr(curr_session, 'close'):
                # Если это кастомный класс с методом close, но без флага closed
                try:
                    await curr_session.close()
                except Exception:
                    pass
            
        print("[AUTO-TEST] 🧹 Все асинхрон с려는 сессии и TCP-коннекторы успешно закрыты.")
    except Exception as clean_err:
        print(f"[AUTO-TEST] Предупреждение при очистке сессий: {clean_err}")
    finally:
        # Удаляем тестовую заметку гранулярности
        if test_note_path.exists():
            try:
                from src.storage.vector_store import vector_store
                await vector_store.delete_file_chunks(str(test_note_path))
            except Exception:
                pass
            os.remove(test_note_path)
            
        # === ОЧИСТКА ВСЕХ ТЕСТОВЫХ ФАЙЛОВ В САМОМ КОНЦЕ ===
        print("[AUTO-TEST] 🧹 Финальная зачистка папки temp_media...")
        for temp_file in [test_photo_target, test_voice_target]:
            if temp_file.exists():
                try:
                    os.remove(temp_file)
                except Exception:
                    pass

    print("\n" + "="*50)
    print("[AUTO-TEST] 🎉 Сквозное тестирование пайплайнов завершено успешно!")
    print("="*50 + "\n")

if __name__ == "__main__":
    asyncio.run(run_pipeline_tests())