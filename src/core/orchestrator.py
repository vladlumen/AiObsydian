import asyncio
import re
import json
from src.infrastructure.event_bus import bus, VoiceReceivedEvent, TextReceivedEvent, PhotoReceivedEvent
from src.infrastructure.task_queue import task_manager
from src.infrastructure.vram_scheduler import vram_manager
from src.infrastructure.telemetry import telemetry  # Добавили явный импорт телеметрии
from src.agents.obsidian_writer import writer
from src.agents.clerk_agent import clerk
# Импортируем инстанс бота, чтобы отправлять сообщения
from src.interfaces.telegram.bot import bot 
from src.cognitive.llm_service import llm
from src.cognitive.stt_service import stt
# Импортируем семантическую память
from src.cognitive.memory.semantic import memory

class Orchestrator:
    def __init__(self):
        bus.subscribe(VoiceReceivedEvent, self.handle_voice_event)
        bus.subscribe(TextReceivedEvent, self.handle_text_event)
        bus.subscribe(PhotoReceivedEvent, self._process_photo_pipeline)
        print("[Orchestrator] Поднялся и слушает шину событий.")

    async def handle_text_event(self, event: TextReceivedEvent):
        """Роутер текста: Поиск, Схемы, Сортировка или Инжест заметки."""
        text_lower = event.text.lower().strip()
        
        if text_lower.startswith("?"):
            # Поиск
            event.text = event.text[1:].strip()
            await task_manager.put(f"Search_{event.user_id}", self._process_text(event))
            
        elif text_lower.startswith("!схема"):
            # Генерация Canvas
            event.text = event.text.replace("!схема", "", 1).strip()
            await task_manager.put(f"Canvas_{event.user_id}", self._generate_canvas(event))
            
        elif text_lower == "!сортировка":
            # Ручной запуск агента-сортировщика
            await task_manager.put(f"Clerk_{event.user_id}", self._run_clerk(event))
            
        else:
            # Обычный инжест (создание Markdown заметки)
            await task_manager.put(f"Note_{event.user_id}", self._generate_note(event))

    async def _process_text(self, event: TextReceivedEvent):
        """Пайплайн: Поиск в памяти -> Формирование промпта -> LLM -> Сохранение."""
        print(f"[Orchestrator] 📝 Запуск текстового пайплайна от {event.user_id}")
        await bot.send_chat_action(chat_id=event.user_id, action="typing")

        # 1. RAG: Поиск релевантного контекста в векторной базе
        found_context = await memory.search_relevant_context(event.text, top_k=3)
        
        context_prompt = ""
        if found_context:
            context_prompt = f"\n\nИСТОРИЧЕСКИЙ КОНТЕКСТ ИЗ БАЗЫ ЗНАНИЙ (Используй эти данные, если они помогают точнее ответить на запрос):\n{found_context}"

        sys_prompt = (
            "Ты — аналитик базы знаний. Твоя задача — превратить поток мыслей пользователя в структурированную заметку "
            "или ответить на его вопрос, опираясь на исторический контекст (если он предоставлен).\n"
            "ПРАЛИЛО 1: Обязательно оборачивай ключевые имена и технологии в двойные квадратные скобки: [[Имя]], [[Технология]].\n"
            "ПРАВИЛО 2: Заметка ДОЛЖНА БЫТЬ НАПИСАНА СТРОГО НА РУССКОМ ЯЗЫКЕ.\n"
            "Отвечай в формате Markdown."
            + context_prompt
        )

        response_text = ""
        async with telemetry.track(f"Text_Pipeline_{event.user_id}"):
            async with vram_manager.inference_lock:
                await vram_manager.request_model("hermes3:8b")
                try:
                    # Передаем запрос пользователя и найденный контекст в LLM
                    response_text = await llm.generate_text(
                        event.text,
                        system_prompt=sys_prompt
                    )
                except Exception as e:
                    print(f"[Orchestrator] ❌ Ошибка LLM: {repr(e)}")
                    response_text = "❌ Ошибка генерации текста."
                finally:
                    await vram_manager.unload_model("hermes3:8b")

        await bot.send_message(chat_id=event.user_id, text=response_text, parse_mode="Markdown")

    async def _generate_note(self, event: TextReceivedEvent):
        """Пайплайн создания структурированной заметки с учетом контекста RAG."""
        print(f"[Orchestrator] 📂 Запуск генерации заметки Ideaverse для {event.user_id}")
        
        # 1. RAG: Извлекаем исторический контекст для обогащения структуры заметки
        found_context = await memory.search_relevant_context(event.text, top_k=3)
        
        async with telemetry.track(f"Generate_Note_Pipeline_{event.user_id}"):
            
            sys_prompt = (
                "Ты — системный архитектор. Структурируй ТОЛЬКО данные из блока <NEW_DATA>.\n"
                "ОТВЕЧАЙ СТРОГО НА РУССКОМ ЯЗЫКЕ.\n\n"
            )
            
            if found_context:
                sys_prompt += f"<OLD_CONTEXT>\n{found_context}\n</OLD_CONTEXT>\n\n"

            sys_prompt += (
                "ПРАВИЛО: ЗАПРЕЩЕНО использовать факты из <OLD_CONTEXT> в заголовке (TITLE), резюме, деталях и сущностях. Используй <OLD_CONTEXT> ИСКЛЮЧИТЕЛЬНО для раздела 'Связи'.\n\n"
                "Формат:\n"
                "PROPERTIES: тег1, тег2\n"
                "TITLE: Заголовок на основе <NEW_DATA>\n"
                "CONTENT:\n"
                "> [!abstract] Резюме\n"
                "(суть из <NEW_DATA>)\n\n"
                "## Детали\n"
                "- (тезисы из <NEW_DATA>)\n\n"
                "## Сущности\n"
                "- (сущности из <NEW_DATA>)\n\n"
                "## Связи\n"
                "- (связи с <OLD_CONTEXT>, иначе 'Нет данных')"
            )

            async with telemetry.track("LLM_Inference_and_Load"):
                async with vram_manager.inference_lock:
                    await vram_manager.request_model("hermes3:8b")
                    # Оборачиваем ввод пользователя в тег <NEW_DATA>
                    safe_prompt = f"<NEW_DATA>\n{event.text}\n</NEW_DATA>"
                    raw_response = await llm.generate_text(safe_prompt, system_prompt=sys_prompt)

            # Парсинг и исправление синтаксиса
            title = "Новая идея"
            properties = ""
            content = raw_response
            
            # Ищем PROPERTIES (всё до TITLE или CONTENT)
            prop_match = re.search(r'PROPERTIES:(.*?)(TITLE:|CONTENT:|$)', raw_response, re.IGNORECASE | re.DOTALL)
            if prop_match: properties = prop_match.group(1).strip()
                
            # Ищем TITLE строго до конца строки
            title_match = re.search(r'TITLE:\s*([^\n]+)', raw_response, re.IGNORECASE)
            if title_match: title = title_match.group(1).strip()
                
            # Ищем CONTENT
            content_match = re.search(r'CONTENT:\s*(.*)', raw_response, re.IGNORECASE | re.DOTALL)
            if content_match: 
                content = content_match.group(1).strip()
            elif title_match: 
                content = raw_response.replace(title_match.group(0), "").strip()

            # Очищаем content от дублирования PROPERTIES
            content = re.sub(r'PROPERTIES:.*?\n', '', content, flags=re.IGNORECASE).strip()

            # Жесткий фикс Callout
            content = content.replace("> !abstract", "> [!abstract]")

            # Запись в файл на жесткий диск Windows через мост
            async with telemetry.track("Obsidian_File_Write"):
                file_path = writer.create_note(title=title, content=content, custom_properties=properties)
                
            # Автоматически отправляем только что созданную заметку на индексацию в нашу векторную базу LanceDB,
            # превращая инжест данных в непрерывный автономный цикл
            await memory.memorize_note(note_id=title, content=content, metadata={"source": "Telegram_Ingest", "title": title})
                
            reply = f"✅ Структурированная заметка создана и добавлена в индекс памяти!\n\n📌 *{title}*\n📂 `00_Inbox`"
            await bot.send_message(chat_id=event.user_id, text=reply, parse_mode="Markdown")

    async def _run_clerk(self, event: TextReceivedEvent):
        """Запускает сортировщика с замером телеметрии."""
        print("[Orchestrator] 🧹 Выбран маршрут: Сортировка (Clerk)")
        await bot.send_message(chat_id=event.user_id, text="⏳ Запускаю Clerk Agent. Анализирую Inbox...")
        
        async with telemetry.track("Clerk_Sorting_Pipeline"):
            report = await clerk.run_sorting()
        
        await bot.send_message(chat_id=event.user_id, text=report, parse_mode="Markdown")

    async def _generate_canvas(self, event: TextReceivedEvent):
        """Пайплайн генерации .canvas майнд-мапы."""
        print("[Orchestrator] 🗺️ Выбран маршрут: Canvas")

        sys_prompt = (
            "Ты — системный архитектор. Преврати запрос в структуру для графа (mind map).\n"
            "Выдай СТРОГО валидный JSON без комментариев и оберток (без ```json).\n"
            "Формат:\n"
            "{\n"
            "  \"title\": \"Название схемы\",\n"
            "  \"nodes\": [\n"
            "    {\"id\": \"1\", \"text\": \"Шаг 1: Описание\"},\n"
            "    {\"id\": \"2\", \"text\": \"Шаг 2: Описание\"}\n"
            "  ],\n"
            "  \"edges\": [\n"
            "    {\"from\": \"1\", \"to\": \"2\"}\n"
            "  ]\n"
            "}"
        )

        async with vram_manager.inference_lock:
            await vram_manager.request_model("hermes3:8b")
            raw_response = await llm.generate_text(event.text, system_prompt=sys_prompt)

        clean_json = re.sub(r'^```json\s*|\s*```$', '', raw_response.strip(), flags=re.MULTILINE)

        try:
            structure = json.loads(clean_json)
            title = structure.get("title", "Новая схема")

            file_path = writer.create_canvas(title=title, structure=structure)
            reply = f"✅ Майнд-мапа создана!\n📌 *{title}*\n📂 `00_Inbox` (.canvas)"
            await bot.send_message(chat_id=event.user_id, text=reply, parse_mode="Markdown")

        except json.JSONDecodeError as e:
            print(f"[Orchestrator] ❌ Ошибка парсинга JSON: {raw_response}")
            await bot.send_message(chat_id=event.user_id, text="❌ Ошибка: LLM выдала неверный формат структуры.")
        except Exception as e:
            await bot.send_message(chat_id=event.user_id, text=f"❌ Ошибка записи Canvas: {e}")

    async def handle_voice_event(self, event: VoiceReceivedEvent):
        task_name = f"Voice_{event.user_id}_{event.audio_path.name}"
        await task_manager.put(task_name, self._process_voice_pipeline(event))

    async def _process_voice_pipeline(self, event: VoiceReceivedEvent):
        """Пайплайн: Голос -> STT -> Текст -> Автоматическое построение заметки."""
        print(f"[Orchestrator] 🎤 Запуск обработки голоса от {event.user_id}")
        await bot.send_message(chat_id=event.user_id, text="🎧 Перевожу голос в текст...")

        try:
            recognized_text = await asyncio.to_thread(stt.transcribe, event.audio_path)

            print(f"[Orchestrator] 🗣️ Распознано: {recognized_text}")
            await bot.send_message(chat_id=event.user_id, text=f"🗣️ *Распознано:*\n_{recognized_text}_", parse_mode="Markdown")

            text_event = TextReceivedEvent(user_id=event.user_id, text=recognized_text)
            # Изменили вызов: пускаем расшифровку через структурирование с RAG
            await self._generate_note(text_event)

        except Exception as e:
            print(f"[Orchestrator] ❌ Ошибка Voice Pipeline: {repr(e)}")
            await bot.send_message(chat_id=event.user_id, text=f"❌ Ошибка при обработке голосового сообщения: {repr(e)}")
        finally:
            # ДЕТОКС-МЕХАНИЗМ: Файл гарантированно стирается при любых раскладах
            if event.audio_path.exists():
                event.audio_path.unlink()
                print(f"[Orchestrator] 🧹 Удален временный аудиофайл: {event.audio_path.name}")

    async def _process_photo_pipeline(self, event: PhotoReceivedEvent):
        """Пайплайн: Фото -> Llama Vision -> Текст -> Смешивание контекста -> Пайплайн заметок."""
        print(f"[Orchestrator] 👁️ Запуск анализа фото от {event.user_id}")
        await bot.send_message(chat_id=event.user_id, text="👀 Изучаю изображение...")

        user_caption = event.caption if event.caption else "Сделай из этого заметку."
        user_prompt = f"Извлеки весь текст с картинки. Опиши только факты. БЕЗ вступлений, БЕЗ фраз вроде 'Я вижу', 'На изображении'. Запрос пользователя: {user_caption}"
        sys_prompt = "Ты — AI-ассистент. Анализируй изображения и выдавай ответ только на русском языке."

        try:
            async with telemetry.track("Vision_Llama_Pipeline"):
                async with vram_manager.inference_lock:
                    await vram_manager.request_model("llama3.2-vision")
                    
                    try:
                        recognized_text = await llm.analyze_image(
                            event.photo_path, 
                            prompt=user_prompt, 
                            system_prompt=sys_prompt,
                            model_name="llama3.2-vision"
                        )
                    except Exception as e:
                        print(f"[Orchestrator] ❌ Ошибка Vision: {repr(e)}")
                        await bot.send_message(chat_id=event.user_id, text=f"❌ Ошибка анализа фото: {repr(e)}")
                        return
                    finally:
                        await vram_manager.unload_model("llama3.2-vision")

            final_text = f"Контекст: Фотография. Подпись пользователя: {event.caption}\n\nЧто увидел AI: {recognized_text}"
            
            text_event = TextReceivedEvent(user_id=event.user_id, text=final_text)
            # Передаем собранную информацию в генератор заметок с поддержкой RAG
            await self._generate_note(text_event)
            
        finally:
            # ДЕТОКС-МЕХАНИЗМ: Фотография гарантированно стирается из data/
            if event.photo_path.exists():
                event.photo_path.unlink()
                print(f"[Orchestrator] 🧹 Удален временный файл изображения: {event.photo_path.name}")

orchestrator = Orchestrator()