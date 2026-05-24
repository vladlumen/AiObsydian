import asyncio
import re
import json
from src.infrastructure.event_bus import bus, VoiceReceivedEvent, TextReceivedEvent, PhotoReceivedEvent, DocumentReceivedEvent
from src.infrastructure.task_queue import task_manager
from src.infrastructure.vram_scheduler import vram_manager
from src.infrastructure.telemetry import telemetry
from src.agents.obsidian_writer import writer
from src.agents.clerk_agent import clerk
from src.agents.parsers.url_parser import url_parser
from src.agents.parsers.pdf_parser import pdf_parser
from src.agents.parsers.docx_parser import docx_parser
from src.agents.parsers.video_parser import video_parser
# СТРОКА ИМПОРТА BOT УДАЛЕНА ОТСЮДА, ЧТОБЫ РАЗОРВАТЬ ЦИКЛИЧЕСКИЙ КРУГ
from src.cognitive.llm_service import llm
from src.cognitive.stt_service import stt
from src.cognitive.memory.semantic import memory
from src.core.prompt_loader import prompt_loader
from src.core import config

URL_REGEX = re.compile(r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F])+)+')

class Orchestrator:
    def __init__(self):
        bus.subscribe(VoiceReceivedEvent, self.handle_voice_event)
        bus.subscribe(TextReceivedEvent, self.handle_text_event)
        bus.subscribe(PhotoReceivedEvent, self._process_photo_pipeline)
        bus.subscribe(DocumentReceivedEvent, self._process_document_pipeline)
        print("[Orchestrator] Поднялся и слушает шину событий.")
        
        # Регистрируем внутренний обработчик в менеджере задач
        task_manager.set_processor(self._process_pipeline_task)

    async def _process_pipeline_task(self, task_data):
        """Единая точка входа для последовательного воркера."""
        task_name, coro = task_data
        await coro

    async def handle_text_event(self, event: TextReceivedEvent):
        """Роутер текста: Поиск, Схемы, Сортировка, Видео, Ссылки или Инжест заметки."""
        text_lower = event.text.lower().strip()
        urls = URL_REGEX.findall(event.text)
        
        if text_lower.startswith("?") or text_lower.endswith("?"):
            if text_lower.startswith("?"):
                event.text = event.text[1:].strip()
            task_manager.put((f"Search_{event.user_id}", self._process_text(event)))
        
        elif text_lower.startswith("!схема"):
            event.text = event.text.replace("!схема", "", 1).strip()
            task_manager.put((f"Canvas_{event.user_id}", self._generate_canvas(event)))
            
        elif text_lower == "!сортировка":
            task_manager.put((f"Clerk_{event.user_id}", self._run_clerk(event)))
            
        elif urls:
            target_url = urls[0].lower()
            if "tiktok.com" in target_url or "youtube.com/shorts" in target_url or "youtu.be" in target_url:
                task_manager.put((f"Video_{event.user_id}", self._process_video_pipeline(event, urls[0])))
            else:
                task_manager.put((f"URL_{event.user_id}", self._process_url_pipeline(event, urls[0])))
            
        else:
            task_manager.put((f"Note_{event.user_id}", self._generate_note(event)))

    async def _process_text(self, event: TextReceivedEvent):
        """Пайплайн: Поиск в векторной памяти -> Формирование промпта -> LLM -> Ответ."""
        from src.interfaces.telegram.bot import bot # Локальный импорт
        print(f"[Orchestrator] 🔍 Запуск поиска по базе для {event.user_id}")
        await bot.send_chat_action(chat_id=event.user_id, action="typing")

        found_context = await memory.search(event.text, top_k=5)
        print(f"\n[DEBUG RAG] База нашла следующий контекст:\n{found_context}\n")
        
        if not found_context:
            await bot.send_message(chat_id=event.user_id, text="В локальном архиве ничего не найдено по этому запросу.")
            return

        sys_prompt = prompt_loader.get("search_prompt", context=found_context)

        if config.COMPARE_MODE:
            for model_alias, model_name in config.AVAILABLE_MODELS.items():
                print(f"[Orchestrator] 📊 Бенчмарк: Запуск {model_name}...")
                response_text = ""
                async with telemetry.track(f"Compare_{model_alias}_{event.user_id}"):
                    async with vram_manager.inference_lock:
                        await vram_manager.request_model(model_name)
                        try:
                            response_text = await llm.generate_text(event.text, system_prompt=sys_prompt, model=model_name)
                        except Exception as e:
                            print(f"[Orchestrator] ❌ Ошибка LLM ({model_name}): {repr(e)}")
                            response_text = "❌ Ошибка генерации ответа."
                        finally:
                            await vram_manager.unload_model(model_name)
                await bot.send_message(
                    chat_id=event.user_id,
                    text=f"🧠 **Ответ от {model_alias.upper()} ({model_name}):**\n\n{response_text}"
                )
        else:
            response_text = ""
            async with telemetry.track(f"Search_Pipeline_{event.user_id}"):
                async with vram_manager.inference_lock:
                    await vram_manager.request_model(config.CURRENT_LLM_MODEL)
                    try:
                        response_text = await llm.generate_text(event.text, system_prompt=sys_prompt, model=config.CURRENT_LLM_MODEL)
                    except Exception as e:
                        print(f"[Orchestrator] ❌ Ошибка LLM: {repr(e)}")
                        response_text = "❌ Ошибка генерации ответа."
                    finally:
                        await vram_manager.unload_model(config.CURRENT_LLM_MODEL)
            await bot.send_message(chat_id=event.user_id, text=response_text)

    async def _execute_llm_inference(self, user_id: int, model_name: str, prompt: str, sys_prompt: str) -> str:
        """Инфраструктурный хелпер для безопасного вызова одиночной LLM через планировщик VRAM."""
        async with vram_manager.inference_lock:
            await vram_manager.request_model(model_name)
            try:
                return await llm.generate_text(prompt, system_prompt=sys_prompt, model=model_name)
            except Exception as e:
                print(f"[Orchestrator] ❌ Ошибка генерации на модели {model_name}: {e}")
                return ""
            finally:
                await vram_manager.unload_model(model_name)

    async def _run_clerk(self, event: TextReceivedEvent):
        """Запускает сортировщика с замером телеметрии."""
        from src.interfaces.telegram.bot import bot # Локальный импорт
        print("[Orchestrator] 🧹 Выбран маршрут: Сортировка (Clerk)")
        await bot.send_message(chat_id=event.user_id, text="⏳ Запускаю Clerk Agent. Анализирую Inbox...")

        async with telemetry.track("Clerk_Sorting_Pipeline"):
            report = await clerk.run_sorting()

        await bot.send_message(chat_id=event.user_id, text=report, parse_mode="Markdown")

    async def _generate_note(self, event: TextReceivedEvent):
        """Пайплайн создания структурированной заметки с поддержкой режима сравнения (Бенчмарк)."""
        from src.interfaces.telegram.bot import bot # Локальный импорт
        print(f"[Orchestrator] 📂 Запуск генерации заметки Ideaverse для {event.user_id}")
        found_context = await memory.search(event.text, top_k=3)
        old_context_block = f"<OLD_CONTEXT>\n{found_context}\n</OLD_CONTEXT>\n\n" if found_context else ""
        sys_prompt = prompt_loader.get("generate_note_prompt", old_context_block=old_context_block)
        safe_prompt = f"<NEW_DATA>\n{event.text}\n</NEW_DATA>"

        models_to_run = config.AVAILABLE_MODELS.items() if config.COMPARE_MODE else [("CURRENT", config.CURRENT_LLM_MODEL)]

        for model_alias, model_name in models_to_run:
            print(f"[Orchestrator] ⚙️ Генерация заметки на модели: {model_name}")
            raw_response = ""
            async with telemetry.track(f"LLM_Inference_{model_alias}"):
                raw_response = await self._execute_llm_inference(event.user_id, model_name, safe_prompt, sys_prompt)

            if not raw_response:
                continue

            title = f"Новая идея ({model_alias.upper()})"
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
                file_path = writer.create_note(title=title, content=content, custom_properties=properties, model_name=model_name)

            await memory.memorize_note(note_id=title, content=content, metadata={"source": f"Telegram_Benchmark_{model_alias}", "title": title})

            reply = f"📊 **Заметка от модели {model_alias.upper()} ({model_name}):**\n✅ Создана и добавлена в индекс памяти!\n\n📌 *{title}*\n📂 `00_Inbox`"
            await bot.send_message(chat_id=event.user_id, text=reply, parse_mode="Markdown")

    async def _generate_web_note(self, user_id: int, user_comment: str, url: str, extracted_text: str):
        """Пайплайн экстракции фактов из статей и документов с поддержкой Бенчмарка."""
        from src.interfaces.telegram.bot import bot # Локальный импорт
        print(f"[Orchestrator] 📂 Запуск генерации WEB-заметки для {user_id}")
        found_context = await memory.search(user_comment + "\n" + extracted_text[:1000], top_k=3)
        old_context_block = f"<OLD_CONTEXT>\n{found_context}\n</OLD_CONTEXT>\n\n" if found_context else ""
        
        sys_prompt = prompt_loader.get(
            "generate_web_note_prompt", 
            old_context_block=old_context_block,
            user_comment=user_comment,
            url=url
        )
        safe_prompt = f"<ARTICLE_TEXT>\n{extracted_text}\n</ARTICLE_TEXT>"

        models_to_run = config.AVAILABLE_MODELS.items() if config.COMPARE_MODE else [("CURRENT", config.CURRENT_LLM_MODEL)]

        for model_alias, model_name in models_to_run:
            print(f"[Orchestrator] ⚙️ Извлечение фактов на модели: {model_name}")
            raw_response = ""
            async with telemetry.track(f"LLM_Web_Inference_{model_alias}"):
                raw_response = await self._execute_llm_inference(user_id, model_name, safe_prompt, sys_prompt)

            if not raw_response:
                continue

            title = f"Web_Clip_{model_alias.upper()}"
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
                file_path = writer.create_note(title=title, content=content, custom_properties=properties, model_name=model_name)

            await memory.memorize_note(
                note_id=title, 
                content=content, 
                metadata={"source": f"Web_Benchmark_{model_alias}", "url": url, "title": title, "folder": "00_Inbox"}
            )

            reply = f"📊 **Выжимка от модели {model_alias.upper()} ({model_name}):**\n✅ Сохранена в Obsidian!\n\n📌 *{title}*\n📂 `00_Inbox`"
            await bot.send_message(chat_id=user_id, text=reply, parse_mode="Markdown")

    async def _process_url_pipeline(self, event: TextReceivedEvent, target_url: str):
        """Пайплайн: Извлечение ссылки -> Парсинг текста -> Пайплайн WEB-заметок."""
        from src.interfaces.telegram.bot import bot # Локальный импорт
        print(f"[Orchestrator] 🌐 Запуск анализа веб-страницы от {event.user_id}")
        await bot.send_message(chat_id=event.user_id, text=f"🔗 Ижучаю содержимое по ссылке:\n{target_url}...")

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
        from src.interfaces.telegram.bot import bot # Локальный импорт
        print(f"[Orchestrator] 📄 Запуск анализа документа от {event.user_id}")
        await bot.send_message(chat_id=event.user_id, text=f"📄 Изучаю документ: {event.file_name}...")

        try:
            suffix = event.file_path.suffix.lower()
            extracted_text = ""

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

    def handle_voice_event(self, event: VoiceReceivedEvent):
        task_name = f"Voice_{event.user_id}_{event.audio_path.name}"
        task_manager.put((task_name, self._process_voice_pipeline(event)))

    async def _process_voice_pipeline(self, event: VoiceReceivedEvent):
        """Пайплайн: Голос -> STT -> Текст -> Автоматическое построение заметки."""
        from src.interfaces.telegram.bot import bot # Локальный импорт
        print(f"[Orchestrator] 🎤 Запуск обработки голоса от {event.user_id}")
        await bot.send_message(chat_id=event.user_id, text="⏳ Перевожу голос в текст...")

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
        from src.interfaces.telegram.bot import bot # Локальный импорт
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

    async def _process_video_pipeline(self, event: TextReceivedEvent, target_url: str):
        """Пайплайн: Ссылка на видео -> Вытягивание аудио -> STT -> Создание заметки."""
        from src.interfaces.telegram.bot import bot # Локальный импорт
        print(f"[Orchestrator] 🎬 Запуск анализа медиа-ссылки от {event.user_id}")
        await bot.send_message(chat_id=event.user_id, text="🎬 Обнаружил ссылку на видео. Выкачиваю аудиодорожку...")

        try:
            audio_path = await video_parser.extract_audio(target_url)
            await bot.send_message(chat_id=event.user_id, text="📥 Звук извлечен. Расшифровываю речь через Whisper...")

            print(f"[Orchestrator] 🎙️ Аудиодорожка скачана in {audio_path}. Передаю в STT...")

            recognized_text = await asyncio.to_thread(stt.transcribe, audio_path)
            print(f"[Orchestrator] 🗣️ Видео распознано: {recognized_text}")

            if not recognized_text.strip():
                await bot.send_message(chat_id=event.user_id, text="⚠️ Не удалось разобрать речь в этом видео.")
                return

            await bot.send_message(chat_id=event.user_id, text=f"🗣️ *Текст из видео расшифрован!*\nФормирую структурированную заметку...")

            final_text = f"Контекст: Выжимка видео по ссылке {target_url}.\n\nТекст из видео:\n{recognized_text}"
            text_event = TextReceivedEvent(user_id=event.user_id, text=final_text)
            await self._generate_note(text_event)

        except Exception as e:
            print(f"[Orchestrator] ❌ Ошибка Video Pipeline: {repr(e)}")
            await bot.send_message(chat_id=event.user_id, text=f"❌ Не удалось обработать видео: {repr(e)}")
        finally:
            if 'audio_path' in locals() and audio_path.exists():
                audio_path.unlink()
                print(f"[Orchestrator] 🧹 Удален временный аудиофайл видео: {audio_path.name}")

orchestrator = Orchestrator()