import asyncio
import re
import json
from src.infrastructure.event_bus import bus, VoiceReceivedEvent, TextReceivedEvent, PhotoReceivedEvent, DocumentReceivedEvent
from src.infrastructure.task_queue import task_manager
from src.infrastructure.vram_scheduler import vram_manager
from src.infrastructure.telemetry import telemetry
from src.agents.obsidian_writer import writer
from src.agents.clerk_agent import clerk
from src.parsers.url_parser import url_parser
from src.parsers.pdf_parser import pdf_parser
from src.parsers.docx_parser import docx_parser
from src.interfaces.telegram.bot import bot 
from src.cognitive.llm_service import llm
from src.cognitive.stt_service import stt
from src.cognitive.memory.semantic import memory

URL_REGEX = re.compile(r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F])+)+')

class Orchestrator:
    def __init__(self):
        bus.subscribe(VoiceReceivedEvent, self.handle_voice_event)
        bus.subscribe(TextReceivedEvent, self.handle_text_event)
        bus.subscribe(PhotoReceivedEvent, self._process_photo_pipeline)
        bus.subscribe(DocumentReceivedEvent, self._process_document_pipeline)
        print("[Orchestrator] Поднялся и слушает шину событий.")

    async def handle_text_event(self, event: TextReceivedEvent):
        """Роутер текста: Поиск, Схемы, Сортировка, Ссылки или Инжест заметки."""
        text_lower = event.text.lower().strip()
        urls = URL_REGEX.findall(event.text)
        
        if text_lower.startswith("?") or text_lower.endswith("?"):
            if text_lower.startswith("?"):
                event.text = event.text[1:].strip()
            await task_manager.put(f"Search_{event.user_id}", self._process_text(event))
            
        elif text_lower.startswith("!схема"):
            event.text = event.text.replace("!схема", "", 1).strip()
            await task_manager.put(f"Canvas_{event.user_id}", self._generate_canvas(event))
            
        elif text_lower == "!сортировка":
            await task_manager.put(f"Clerk_{event.user_id}", self._run_clerk(event))
            
        elif urls:
            await task_manager.put(f"URL_{event.user_id}", self._process_url_pipeline(event, urls[0]))
            
        else:
            await task_manager.put(f"Note_{event.user_id}", self._generate_note(event))

    async def _process_text(self, event: TextReceivedEvent):
        """Пайплайн: Поиск в векторной памяти -> Формирование промпта -> LLM -> Ответ."""
        print(f"[Orchestrator] 🔍 Запуск поиска по базе для {event.user_id}")
        await bot.send_chat_action(chat_id=event.user_id, action="typing")

        found_context = await memory.search_relevant_context(event.text, top_k=5)
        print(f"\n[DEBUG RAG] База нашла следующий контекст:\n{found_context}\n")
        
        if not found_context:
            await bot.send_message(chat_id=event.user_id, text="В локальном архиве ничего не найдено по этому запросу.")
            return

        sys_prompt = (
            "Ты — аналитик локальной базы знаний. Твоя задача — дать точный, структурированный и визуально аккуратный ответ на вопрос пользователя.\n"
            "ОТВЕЧАЙ СТРОГО НА РУССКОМ ЯЗЫКЕ. Игнорируй английский язык в метаданных контекста, сам ответ должен быть полностью на русском.\n\n"
            "ПРАВИЛА АНАЛИЗА КОНТЕКСТА:\n"
            "1. Используй ИСКЛЮЧИТЕЛЬНО предоставленные факты из блока <CONTEXT>.\n"
            "2. Если информация в разных фрагментах различается или противоречит друг другу (разные даты, статусы, результаты) — НЕ игнорируй это. Обязательно перечисли все найденные версии фактов.\n"
            "3. Если данные частично совпадают или дополняют друг друга — синтезируй их в один связный вывод.\n"
            "4. Отсутствие идеального совпадения НЕ означает отсутствие информации. Используй любые смежные факты из контекста.\n"
            "5. При конфликте данных отдавай приоритет более новым или подробным фактам.\n"
            "6. Шаблонный отказ 'В базе нет информации' разрешен ТОЛЬКО в том случае, если в контексте вообще нет ни одного упоминания сущностей из запроса.\n\n"
            "ТРЕБОВАНИЯ К ФОРМАТИРОВАНИЮ ОТВЕТА:\n"
            "- Используй списки (буллиты) и жирный шрифт для ключевых показателей (время, скорость, даты, имена, результаты).\n"
            "- Разделяй логические blocks пустой строкой, избегай плотных стен сплошного текста.\n"
            "- Добавляй релевантные эмодзи в начале строк для улучшения читаемости (например, 🏃‍♂️ для спорта, 📅 для дат, 📊 для цифр/статистики).\n"
            "- В самом конце ответа обязательно укажи заголовок файла-источника в формате: `📂 Источник: [[Название_файла]]`.\n\n"
            f"<CONTEXT>\n{found_context}\n</CONTEXT>"
        )

        response_text = ""
        async with telemetry.track(f"Search_Pipeline_{event.user_id}"):
            async with vram_manager.inference_lock:
                await vram_manager.request_model("hermes3:8b", gb_reservation=3)
                try:
                    response_text = await llm.generate_text(event.text, system_prompt=sys_prompt)
                except Exception as e:
                    print(f"[Orchestrator] ❌ Ошибка LLM: {repr(e)}")
                    response_text = "❌ Ошибка генерации ответа."
                finally:
                    await vram_manager.unload_model("hermes3:8b")

        await bot.send_message(chat_id=event.user_id, text=response_text)

    async def _generate_note(self, event: TextReceivedEvent):
        """Пайплайн создания структурированной заметки с учетом контекста RAG."""
        print(f"[Orchestrator] 📂 Запуск генерации заметки Ideaverse для {event.user_id}")

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
                "TITLE: Заголовок строго в формате 'ГГГГ-ММ-ДД Краткая Суть'. Используй СТРОГО текущий 2026 год (сегодня 2026-05-21), а вместо 'Краткая Суть' напиши реальную главную тему на основе <NEW_DATA> (например, '2026-05-21 Результаты пробежки').\n"
                "CONTENT:\n"
                "> [!abstract] Резюме\n"
                "(суть из <NEW_DATA>)\n\n"
                "## Детали\n"
                "- (выпиши ВСЕ конкретные факты, названия инструментов/приложений, списки и важные детали из <NEW_DATA>)\n\n"
                "## Сущности\n"
                "- (сущности из <NEW_DATA>)\n\n"
                "## Связи\n"
                "- (связи с <OLD_CONTEXT>, иначе 'Нет данных')"
            )

            raw_response = ""
            async with telemetry.track("LLM_Inference_and_Load"):
                async with vram_manager.inference_lock:
                    await vram_manager.request_model("hermes3:8b")
                    try:
                        safe_prompt = f"<NEW_DATA>\n{event.text}\n</NEW_DATA>"
                        raw_response = await llm.generate_text(safe_prompt, system_prompt=sys_prompt)
                    except Exception as e:
                        print(f"[Orchestrator] ❌ Ошибка генерации заметки: {e}")
                        return
                    finally:
                        await vram_manager.unload_model("hermes3:8b")

            title = "Новая идея"
            properties = ""
            content = raw_response

            prop_match = re.search(r'PROPERTIES:(.*?)(TITLE:|CONTENT:|$)', raw_response, re.IGNORECASE | re.DOTALL)
            if prop_match: properties = prop_match.group(1).strip()

            title_match = re.search(r'TITLE:\s*([^\n]+)', raw_response, re.IGNORECASE)
            if title_match: title = title_match.group(1).strip()

            content_match = re.search(r'CONTENT:\s*(.*)', raw_response, re.IGNORECASE | re.DOTALL)
            if content_match:
                content = content_match.group(1).strip()
            elif title_match:
                content = raw_response.replace(title_match.group(0), "").strip()

            content = re.sub(r'PROPERTIES:.*?\n', '', content, flags=re.IGNORECASE).strip()
            content = content.replace("> !abstract", "> [!abstract]")

            async with telemetry.track("Obsidian_File_Write"):
                file_path = writer.create_note(title=title, content=content, custom_properties=properties)

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
        print(f"[Orchestrator] 🗺️ Выбран маршрут: Canvas")

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

        raw_response = ""
        async with vram_manager.inference_lock:
            await vram_manager.request_model("hermes3:8b", gb_reservation=3)
            try:
                raw_response = await llm.generate_text(event.text, system_prompt=sys_prompt)
            finally:
                await vram_manager.unload_model("hermes3:8b")

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

    async def _generate_web_note(self, user_id: int, user_comment: str, url: str, extracted_text: str):
        """Специализированный пайплайн для экстракции фактов из статей."""
        print(f"[Orchestrator] 📂 Запуск генерации WEB-заметки для {user_id}")

        found_context = await memory.search_relevant_context(user_comment + "\n" + extracted_text[:1000], top_k=3)

        async with telemetry.track(f"Generate_Web_Note_{user_id}"):
            sys_prompt = (
                "Ты — аналитик данных (Data Miner). Твоя единственная задача — извлекать факты, названия, цифры и списки из <ARTICLE_TEXT>.\n"
                "ЗАПРЕЩЕНО писать общие фразы (например, 'В статье рассказывается о...'). Пиши только конкретику.\n"
                "ОТВЕЧАЙ СТРОГО НА РУССКОМ ЯЗЫКЕ.\n\n"
            )

            if found_context:
                sys_prompt += f"<OLD_CONTEXT>\n{found_context}\n</OLD_CONTEXT>\n\n"

            sys_prompt += (
                "Формат:\n"
                "PROPERTIES: article, web_clip\n"
                "TITLE: Заголовок строго в формате 'ГГГГ-ММ-ДД Краткая Суть'. Используй ТЕКУЩУЮ дату (2026-05-21) или дату публикации статьи, а вместо 'Краткая Суть' напиши реальную главную тему статьи (например, '2026-05-21 Разработка игр в Roblox').\n"
                "CONTENT:\n"
                "> [!abstract] Резюме\n"
                "(О чем статья в 1-2 предложениях. Учти комментарий пользователя: " + user_comment + ")\n\n"
                "## Извлеченные факты и инструменты\n"
                "- (Название инструмента 1 / Факт 1 — конкретное описание из текста)\n"
                "- (Название инструмента 2 / Факт 2 — конкретное описание из текста)\n"
                "- (Продолжай список, выпиши ВСЕ полезное)\n\n"
                "## Связи\n"
                f"- [Источник]({url})\n"
                "- (Связи с <OLD_CONTEXT>, иначе 'Нет данных')"
            )

            raw_response = ""
            async with telemetry.track("LLM_Inference_and_Load"):
                async with vram_manager.inference_lock:
                    await vram_manager.request_model("hermes3:8b", gb_reservation=3)
                    try:
                        safe_prompt = f"<ARTICLE_TEXT>\n{extracted_text}\n</ARTICLE_TEXT>"
                        raw_response = await llm.generate_text(safe_prompt, system_prompt=sys_prompt)
                    finally:
                        await vram_manager.unload_model("hermes3:8b")

            title = "Web_Clip"
            properties = ""
            content = raw_response

            prop_match = re.search(r'PROPERTIES:(.*?)(TITLE:|CONTENT:|$)', raw_response, re.IGNORECASE | re.DOTALL)
            if prop_match: properties = prop_match.group(1).strip()

            title_match = re.search(r'TITLE:\s*([^\n]+)', raw_response, re.IGNORECASE)
            if title_match: title = title_match.group(1).strip()

            content_match = re.search(r'CONTENT:\s*(.*)', raw_response, re.IGNORECASE | re.DOTALL)
            if content_match:
                content = content_match.group(1).strip()
            elif title_match:
                content = raw_response.replace(title_match.group(0), "").strip()

            content = re.sub(r'PROPERTIES:.*?\n', '', content, flags=re.IGNORECASE).strip()
            content = content.replace("> !abstract", "> [!abstract]")

            async with telemetry.track("Obsidian_File_Write"):
                file_path = writer.create_note(title=title, content=content, custom_properties=properties)

            # Передаем реальный вытащенный title, чтобы в RAG-базе не было файлов "Без названия" или "Web_Clip"
            await memory.memorize_note(
                note_id=title, 
                content=content, 
                metadata={"source": "Web", "url": url, "title": title, "folder": "00_Inbox"}
            )

            reply = f"✅ Выжимка из статьи сохранена!\n\n📌 *{title}*\n📂 `00_Inbox`"
            await bot.send_message(chat_id=user_id, text=reply, parse_mode="Markdown")

    async def _process_url_pipeline(self, event: TextReceivedEvent, target_url: str):
        """Пайплайн: Извлечение ссылки -> Парсинг текста -> Пайплайн WEB-заметок."""
        print(f"[Orchestrator] 🌐 Запуск анализа веб-страницы от {event.user_id}")
        await bot.send_message(chat_id=event.user_id, text=f"🔗 Изучаю содержимое по ссылке:\n{target_url}...")

        try:
            extracted_text = await asyncio.to_thread(url_parser.extract_text, target_url)
            await bot.send_message(chat_id=event.user_id, text=f"✅ Текст скачан ({len(extracted_text)} символов). Извлекаю факты...")
            await self._generate_web_note(event.user_id, event.text, target_url, extracted_text)
        except ValueError as ve:
            print(f"[Orchestrator] ⚠️ Отказ парсера: {str(ve)}")
            await bot.send_message(chat_id=event.user_id, text=str(ve))
        except Exception as e:
            print(f"[Orchestrator] ❌ Ошибка скачивания страницы: {repr(e)}")
            await bot.send_message(chat_id=event.user_id, text="❌ Не удалось открыть ссылку. Проверьте доступность сайта.")

    async def _process_document_pipeline(self, event: DocumentReceivedEvent):
        """Пайплайн: Локальный документ -> Парсинг текста -> WEB-заметка (выжимка фактов)."""
        print(f"[Orchestrator] 📄 Запуск анализа документа от {event.user_id}")
        await bot.send_message(chat_id=event.user_id, text=f"📄 Изучаю документ: {event.file_name}...")

        try:
            suffix = event.file_path.suffix.lower()
            extracted_text = ""

            # Роутинг под раздельные парсеры
            if suffix == ".pdf":
                extracted_text = await asyncio.to_thread(pdf_parser.parse, event.file_path)
            elif suffix == ".docx":
                extracted_text = await asyncio.to_thread(docx_parser.parse, event.file_path)
            else:
                await bot.send_message(chat_id=event.user_id, text="❌ Неподдерживаемый формат документа. Используй PDF или DOCX.")
                return

            if not extracted_text:
                await bot.send_message(chat_id=event.user_id, text="⚠️ Не удалось извлечь текст из документа.")
                return

            await bot.send_message(chat_id=event.user_id, text=f"✅ Текст извлечен ({len(extracted_text)} символов). Формирую выжимку...")
            user_comment = f"Документ: {event.file_name}. " + (event.caption if event.caption else "")
            await self._generate_web_note(event.user_id, user_comment, event.file_name, extracted_text)

        except Exception as e:
            print(f"[Orchestrator] ❌ Ошибка обработки документа: {repr(e)}")
            await bot.send_message(chat_id=event.user_id, text="❌ Произошла ошибка при чтении документа.")
        finally:
            if event.file_path.exists():
                event.file_path.unlink()
                print(f"[Orchestrator] 🧹 Удален временный документ: {event.file_name}")

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
            await self._generate_note(text_event)
        except Exception as e:
            print(f"[Orchestrator] ❌ Ошибка Voice Pipeline: {repr(e)}")
            await bot.send_message(chat_id=event.user_id, text=f"❌ Ошибка при обработке голосового сообщения: {repr(e)}")
        finally:
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
        recognized_text = ""

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
                        print(f"[Orchestrator] ❌ Ошибка внутри Llama Vision: {repr(e)}")
                        await bot.send_message(chat_id=event.user_id, text="❌ Ошибка при генерации описания изображения.")
                        return
                    finally:
                        await vram_manager.unload_model("llama3.2-vision")

            if recognized_text:
                final_text = f"Контекст: Фотография. Подпись пользователя: {event.caption}\n\nЧто увидел AI: {recognized_text}"
                text_event = TextReceivedEvent(user_id=event.user_id, text=final_text)
                await self._generate_note(text_event)
            else:
                await bot.send_message(chat_id=event.user_id, text="⚠️ Не удалось распознать текст на фото.")

        except Exception as top_e:
            print(f"[Orchestrator] ❌ Общая ошибка Фото Пайплайна: {repr(top_e)}")
        finally:
            if event.photo_path.exists():
                event.photo_path.unlink()
                print(f"[Orchestrator] 🧹 Удален временный файл изображения: {event.photo_path.name}")

orchestrator = Orchestrator()