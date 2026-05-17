import asyncio
import re
import json
from src.infrastructure.event_bus import bus, VoiceReceivedEvent, TextReceivedEvent, PhotoReceivedEvent
from src.infrastructure.task_queue import task_manager
from src.infrastructure.vram_scheduler import vram_manager
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
        """Реакция на текст: ставим в очередь."""
        task_name = f"Text_{event.user_id}"
        await task_manager.put(task_name, self._process_text(event))

    async def _process_text(self, event: TextReceivedEvent):
        """Пайплайн: Поиск в памяти -> Формирование промпта -> LLM -> Сохранение."""
        print(f"[Orchestrator] 📝 Запуск текстового пайплайна от {event.user_id}")
        await bot.send_chat_action(chat_id=event.user_id, action="typing")

        # 1. RAG: Поиск релевантного контекста в базе
        found_context = await memory.search_relevant_context(event.text, top_k=3)
        
        context_prompt = ""
        if found_context:
            context_prompt = f"\n\nИСТОРИЧЕСКИЙ КОНТЕКСТ ИЗ БАЗЫ ЗНАНИЙ:\n{found_context}\nИспользуй эти данные, если они помогают ответить на запрос."

        sys_prompt = (
            "Ты — аналитик базы знаний. Твоя задача — превратить поток мыслей пользователя в структурированную заметку "
            "или ответить на его вопрос, опираясь на исторический контекст (если он предоставлен).\n"
            "ПРАВИЛО 1: Обязательно оборачивай ключевые имена и технологии в двойные квадратные скобки: [[Имя]], [[Технология]].\n"
            "ПРАВИЛО 2: Заметка ДОЛЖНА БЫТЬ НАПИСАНА СТРОГО НА РУССКОМ ЯЗЫКЕ.\n"
            "Отвечай в формате Markdown."
            + context_prompt
        )

        async with telemetry.track(f"Text_Pipeline_{event.user_id}"):
            async with vram_manager.inference_lock:
                await vram_manager.request_model("hermes3:8b")
                try:
                    # Передаем запрос пользователя и найденный контекст в LLM
                    response_text = await llm.generate_text(
                        prompt=event.text,
                        system_prompt=sys_prompt,
                        model_name="hermes3:8b"
                    )
                except Exception as e:
                    print(f"[Orchestrator] ❌ Ошибка LLM: {repr(e)}")
                    await bot.send_message(chat_id=event.user_id, text="❌ Ошибка генерации текста.")
                    return
                finally:
                    # Не выгружаем Hermes сразу, если ожидается диалог, либо выгружаем по стратегии
                    pass 

        # ... (здесь остается твой код отправки сообщения в Telegram и сохранения файла через ObsidianWriter) ...
        await bot.send_message(chat_id=event.user_id, text=response_text, parse_mode="Markdown")

    async def _run_clerk(self, event: TextReceivedEvent):
        """Запускает сортировщика с замером телеметрии."""
        print("[Orchestrator] 🧹 Выбран маршрут: Сортировка (Clerk)")
        await bot.send_message(chat_id=event.user_id, text="⏳ Запускаю Clerk Agent. Анализирую Inbox...")
        
        # Оборачиваем работу агента в трекер
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

        # Очистка от markdown-блоков, если LLM их все же добавит
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

    async def _generate_note(self, event: TextReceivedEvent):
        """Пайплайн создания заметки с замером телеметрии."""
        
        # Оборачиваем весь жизненный цикл в один большой трек
        async with telemetry.track(f"Generate_Note_Pipeline_{event.user_id}"):
            
            sys_prompt = (
                "Ты — аналитик базы знаний Ideaverse. Твоя задача — превратить поток мыслей пользователя в структурированную заметку.\n"
                "Заметка ДОЛЖНА БЫТЬ НАПИСАНА СТРОГО НА РУССКОМ ЯЗЫКЕ, даже если исходные данные на другом.\n\n"
                "Выдай ответ СТРОГО в следующем формате:\n\n"
                "PROPERTIES: краткие теги через запятую (без #)\n"
                "TITLE: Краткое название заметки\n"
                "CONTENT:\n"
                "> [!abstract] Резюме\n"
                "(краткая суть одним абзацем)\n\n"
                "## Ключевые тезисы\n"
                "- (список важных мыслей с [[вики-ссылками]])\n\n"
                "## Сущности (Things)\n"
                "- (список упомянутых [[Людей]] или [[Проекта]])"
            )

            # Отдельно замерим, сколько времени модель тратит на загрузку и инференс
            async with telemetry.track("LLM_Inference_and_Load"):
                async with vram_manager.inference_lock:
                    await vram_manager.request_model("hermes3:8b")
                    raw_response = await llm.generate_text(event.text, system_prompt=sys_prompt)

            # Парсинг и исправление синтаксиса
            title = "Новая идея"
            properties = ""
            content = raw_response
            
            # Ищем PROPERTIES (всё до TITLE или CONTENT)
            prop_match = re.search(r'PROPERTIES:(.*?)(TITLE:|CONTENT:|$)', raw_response, re.IGNORECASE | re.DOTALL)
            if prop_match: properties = prop_match.group(1).strip()
                
            # Ищем TITLE строго до конца строки (без DOTALL), чтобы не захватить лишнее
            title_match = re.search(r'TITLE:\s*([^\n]+)', raw_response, re.IGNORECASE)
            if title_match: title = title_match.group(1).strip()
                
            # Ищем CONTENT
            content_match = re.search(r'CONTENT:\s*(.*)', raw_response, re.IGNORECASE | re.DOTALL)
            if content_match: 
                content = content_match.group(1).strip()
            elif title_match: 
                # Если CONTENT нет, берем всё, что после TITLE
                content = raw_response.replace(title_match.group(0), "").strip()

            # Очищаем content от слова PROPERTIES, если модель всё смешала
            content = re.sub(r'PROPERTIES:.*?\n', '', content, flags=re.IGNORECASE).strip()

            # Жесткий фикс Callout
            content = content.replace("> !abstract", "> [!abstract]")

            # Запись в файл
            async with telemetry.track("Obsidian_File_Write"):
                file_path = writer.create_note(title=title, content=content, custom_properties=properties)
                
            reply = f"✅ Структурированная заметка создана!\n\n📌 *{title}*\n📂 `00_Inbox`"
            await bot.send_message(chat_id=event.user_id, text=reply, parse_mode="Markdown")

    async def handle_voice_event(self, event: VoiceReceivedEvent):
        # ... (здесь остался старый код из предыдущего шага)
        task_name = f"Voice_{event.user_id}_{event.audio_path.name}"
        await task_manager.put(task_name, self._process_voice_pipeline(event))

    async def _process_photo_pipeline(self, event: PhotoReceivedEvent):
        """Пайплайн: Фото -> Llama Vision -> Текст -> LLM (Hermes) -> Obsidian."""
        print(f"[Orchestrator] 👁️ Запуск анализа фото от {event.user_id}")
        await bot.send_message(chat_id=event.user_id, text="👀 Изучаю изображение...")

        # Жестко требуем русский язык от Llama
        user_caption = event.caption if event.caption else "Сделай из этого заметку."
        user_prompt = f"Извлеки весь текст с картинки и опиши её суть. ОТВЕЧАЙ СТРОГО НА РУССКОМ ЯЗЫКЕ. Запрос пользователя: {user_caption}"
        sys_prompt = "Ты — AI-ассистент. Анализируй изображения и выдавай ответ только на русском языке."

        async with telemetry.track("Vision_Llama_Pipeline"):
            async with vram_manager.inference_lock:
                # Llama Vision требует около 6GB VRAM
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
                    # Сразу выгружаем модель, чтобы освободить место для Hermes 3
                    await vram_manager.unload_model("llama3.2-vision")

        # Укорачиваем текст для Телеграма (показываем только первые 150 символов)
        short_preview = recognized_text[:150] + "..." if len(recognized_text) > 150 else recognized_text
        await bot.send_message(chat_id=event.user_id, text=f"👁️ *Я увидел:*\n_{short_preview}_", parse_mode="Markdown")

        # Композиция: передаем распознанный текст в текстовый пайплайн для создания заметки
        final_text = f"Контекст: Фотография. Подпись пользователя: {event.caption}\n\nЧто увидел AI: {recognized_text}"
        
        text_event = TextReceivedEvent(user_id=event.user_id, text=final_text)
        await self._process_text(text_event)
        
        # Удаляем временное фото
        if event.photo_path.exists():
            event.photo_path.unlink()

orchestrator = Orchestrator()