import asyncio
import re
import inspect
import os
from pathlib import Path
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
from src.cognitive.llm_service import llm
from src.cognitive.stt_service import stt
from src.cognitive.vision_service import vision_service
from src.cognitive.memory.semantic import memory
from src.core.prompt_loader import prompt_loader
from src.core import config
from src.infrastructure.logger import logger

URL_REGEX = re.compile(r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F])+)+')

class Orchestrator:
    def __init__(self):
        bus.subscribe(VoiceReceivedEvent, self.handle_voice_event)
        bus.subscribe(TextReceivedEvent, self.handle_text_event)
        bus.subscribe(PhotoReceivedEvent, self.handle_photo_event)
        bus.subscribe(DocumentReceivedEvent, self.handle_document_event)
        print("[Orchestrator] Поднялся и слушает шину событий.")
        task_manager.set_processor(self._process_pipeline_task)

    async def _process_pipeline_task(self, task_data):
        """Единая точка входа для последовательного воркера."""
        task_name, target_callable = task_data
        res = target_callable()
        if asyncio.iscoroutine(res) or inspect.isawaitable(res):
            await res

    async def handle_text_event(self, event: TextReceivedEvent):
        """Роутер текста: Поиск, Схемы, Сортировка, Видео, Ссылки или Инжест заметки."""
        text_lower = event.text.lower().strip()
        urls = URL_REGEX.findall(event.text)
        
        if text_lower.startswith("?") or text_lower.endswith("?"):
            if text_lower.startswith("?"):
                event.text = event.text[1:].strip()
            task_manager.add_task(self._process_text, event)
        elif text_lower.startswith("!схема"):
            event.text = event.text.replace("!схема", "", 1).strip()
            task_manager.add_task(self._generate_canvas, event)
        elif text_lower == "!сортировка":
            task_manager.add_task(self._run_clerk, event)
        elif urls:
            target_url = urls[0].lower()
            if "tiktok.com" in target_url or "youtube.com/shorts" in target_url or "youtu.be" in target_url:
                task_manager.add_task(self._process_video_pipeline, event, urls[0])
            else:
                task_manager.add_task(self._process_url_pipeline, event, urls[0])
        else:
            task_manager.add_task(self._generate_note, event)

    async def handle_photo_event(self, event: PhotoReceivedEvent):
        """Пайплайн обработки изображений с автоматической зачисткой."""
        print(f"[Orchestrator] 👁️ Запуск анализа фото от {event.user_id}")
        
        # Строгое соответствие датаклассу из EventBus
        image_path = Path(event.photo_path)
        
        try:
            ocr_text = await vision_service.analyze_image(
                image_path=image_path,
                prompt="Распознай текст со скриншота задач"
            )
            
            if ocr_text.strip():
                enriched_text = f"Контекст: Фотография.\nЧто увидел AI:\n{ocr_text}"
                # Меняем event_bus.publish на bus.publish (согласно твоему импорту)
                from src.infrastructure.event_bus import bus, TextReceivedEvent
                await bus.publish(TextReceivedEvent(user_id=event.user_id, text=enriched_text))
                
        except Exception as e:
            print(f"[Orchestrator ❌ Ошибка пайплайна фото]: {repr(e)}")
            
        finally:
            if image_path.exists():
                try:
                    os.remove(image_path)
                    print(f"[Orchestrator] 🧹 Удален временный файл изображения: {image_path.name}")
                except Exception as clear_e:
                    print(f"⚠️ Не удалось удалить файл {image_path.name}: {clear_e}")

    async def handle_voice_event(self, event: VoiceReceivedEvent):
        """Пайплайн обработки голосовых сообщений с автоматической зачисткой."""
        print(f"[Orchestrator] 🎤 Запуск обработки голоса от {event.user_id}")
        
        # Импортируем именно 'stt', как прописано в твоем сервисе
        from src.cognitive.stt_service import stt
        
        audio_path = Path(event.audio_path)
        
        try:
            # Вызываем метод у правильного объекта (синхронный вызов)
            transcribed_text = stt.transcribe(audio_path)
            
            if transcribed_text.strip():
                from src.infrastructure.event_bus import bus, TextReceivedEvent
                await bus.publish(TextReceivedEvent(user_id=event.user_id, text=transcribed_text))
                
        except Exception as e:
            print(f"[Orchestrator ❌ Ошибка пайплайна голоса]: {repr(e)}")
            
        finally:
            if audio_path.exists():
                try:
                    os.remove(audio_path)
                    print(f"[Orchestrator] 🧹 Удален временный аудиофайл: {audio_path.name}")
                except Exception as clear_e:
                    print(f"⚠️ Не удалось удалить файл {audio_path.name}: {clear_e}")

    async def handle_document_event(self, event: DocumentReceivedEvent):
        """Пайплайн обработки документов (PDF/Docx) с извлечением текста и авто-зачисткой."""
        print(f"[Orchestrator] 📄 Запуск парсинга документа от {event.user_id}")
        
        # Строго берем file_path из датакласса DocumentReceivedEvent
        file_path = Path(event.file_path)
        
        try:
            # Ленивый импорт диспетчера парсеров для защиты от циклов
            from src.agents.parsers.document_parser import document_parser
            
            # Извлекаем чистый текст из PDF или DOCX
            extracted_text = await document_parser.extract_text(file_path)
            
            if extracted_text and extracted_text.strip():
                print(f"[Orchestrator] ✅ Текст успешно извлечен ({len(extracted_text)} симв.). Отправляю в Hermes 3...")
                enriched_text = f"Контекст: Документ {event.file_name}.\nСодержимое:\n{extracted_text}"
                
                # Публикуем текстовое событие для генерации итоговой заметки в Obsidian
                from src.infrastructure.event_bus import bus, TextReceivedEvent
                await bus.publish(TextReceivedEvent(user_id=event.user_id, text=enriched_text))
            else:
                print(f"[Orchestrator] ⚠️ Из файла {event.file_name} не удалось извлечь текст.")
                
        except Exception as e:
            print(f"[Orchestrator ❌ Ошибка пайплайна документов]: {repr(e)}")
            
        finally:
            # Гарантированная зачистка бинарника с диска WSL2 (Шаг 2 нашего плана)
            if file_path.exists():
                try:
                    os.remove(file_path)
                    print(f"[Orchestrator] 🧹 Удален временный документ: {file_path.name}")
                except Exception as clear_e:
                    print(f"⚠️ Не удалось удалить файл {file_path.name}: {clear_e}")

    async def _process_text(self, event: TextReceivedEvent):
        from src.interfaces.telegram.bot import bot
        print(f"[Orchestrator] 🔍 Запуск поиска по базе для {event.user_id}")
        await bot.send_chat_action(chat_id=event.user_id, action="typing")
        found_context = await memory.search(event.text, top_k=5)
        
        if not found_context:
            await bot.send_message(chat_id=event.user_id, text="В локальном архиве ничего не найдено по этому запросу.")
            return

        sys_prompt = prompt_loader.get("search_prompt", context=found_context)

        if config.COMPARE_MODE:
            for model_alias, model_name in config.AVAILABLE_MODELS.items():
                response_text = ""
                async with telemetry.track(f"Compare_{model_alias}_{event.user_id}"):
                    response_text = await self._execute_llm_inference(event.user_id, model_name, event.text, sys_prompt)
                
                # Защита от отправки пустого текста
                if not response_text or not response_text.strip():
                    response_text = f"⚠️ Модель {model_alias.upper()} вернула пустой ответ."
                    
                await bot.send_message(
                    chat_id=event.user_id,
                    text=f"🧠 **Ответ от {model_alias.upper()} ({model_name}):**\n\n{response_text}"
                )
        else:
            response_text = ""
            async with telemetry.track(f"Search_Pipeline_{event.user_id}"):
                response_text = await self._execute_llm_inference(event.user_id, config.CURRENT_LLM_MODEL, event.text, sys_prompt)
            
            # Защита от отправки пустого текста
            if not response_text or not response_text.strip():
                response_text = "⚠️ Локальная модель вернула пустой ответ при поиске."
                
            await bot.send_message(chat_id=event.user_id, text=response_text)

    async def _execute_llm_inference(self, user_id: int, model_name: str, prompt: str, sys_prompt: str) -> str:
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
        from src.interfaces.telegram.bot import bot
        print("[Orchestrator] 🧹 Выбран маршрут: Сортировка (Clerk)")
        await bot.send_message(chat_id=event.user_id, text="⏳ Запускаю Clerk Agent. Анализирую Inbox...")
        async with telemetry.track("Clerk_Sorting_Pipeline"):
            report = await clerk.run_sorting()
        await bot.send_message(chat_id=event.user_id, text=report, parse_mode="Markdown")

    async def _generate_note(self, event: TextReceivedEvent):
        from src.interfaces.telegram.bot import bot
        print(f"[Orchestrator] 📂 Запуск генерации заметки Ideaverse для {event.user_id}")
        
        import datetime
        current_date_str = datetime.datetime.now().strftime("%Y-%m-%d")
        
        found_context = await memory.search(event.text, top_k=3)
        old_context_block = f"<OLD_CONTEXT>\n{found_context}\n</OLD_CONTEXT>\n\n" if found_context else ""
        
        # Передаем готовую дату в промпт
        sys_prompt = prompt_loader.get("generate_note_prompt", old_context_block=old_context_block, current_date=current_date_str)
        safe_prompt = f"<NEW_DATA>\n{event.text}\n</NEW_DATA>"

        models_to_run = config.AVAILABLE_MODELS.items() if config.COMPARE_MODE else [("CURRENT", config.CURRENT_LLM_MODEL)]

        for model_alias, model_name in models_to_run:
            raw_response = ""
            async with telemetry.track(f"LLM_Inference_{model_alias}"):
                raw_response = await self._execute_llm_inference(event.user_id, model_name, safe_prompt, sys_prompt)

            if not raw_response or not raw_response.strip():
                print(f"[Orchestrator] ⚠️ Модель {model_name} вернула пустой ответ.")
                continue

            print(f"\n[ORCHESTRATOR DEBUG] ОТВЕТ МОДЕЛИ {model_alias}:\n{raw_response}\n[DEBUG END]\n")

            try:
                title = f"{current_date_str} Новая заметка ({model_alias.upper()})"
                properties = ""
                content = raw_response

                prop_match = re.search(r'PROPERTIES:\s*(.*?)\s*(TITLE:|CONTENT:|$)', raw_response, re.IGNORECASE | re.DOTALL)
                if prop_match: properties = prop_match.group(1).strip()

                title_match = re.search(r'TITLE:\s*([^\n\r]+)', raw_response, re.IGNORECASE)
                if title_match: 
                    candidate_title = title_match.group(1).strip().replace("`", "").replace("*", "")
                    if len(candidate_title) > 3:
                        title = candidate_title

                content_match = re.search(r'CONTENT:\s*(.*)', raw_response, re.IGNORECASE | re.DOTALL)
                if content_match:
                    content = content_match.group(1).strip()

                content = content.replace("[!abstract]", "> [!abstract]")
                content = re.sub(r'PROPERTIES:\s*.*?\n', '', content, flags=re.IGNORECASE).strip()

                print(f"[Orchestrator] [📊 Obsidian_File_Write] Старт записи для: \"{title}\"")
                async with telemetry.track("Obsidian_File_Write"):
                    file_path = writer.create_note(title=title, content=content, custom_properties=properties, model_name=model_name)

                await memory.memorize_note(note_id=title, content=content, metadata={"source": f"Telegram_Benchmark_{model_alias}", "title": title})
                print(f"[Orchestrator] ✅ Заметка \"{title}\" успешно добавлена в индекс памяти.")

            except Exception as inner_e:
                print(f"[Orchestrator] ❌ Сбой обработки парсинга заметки: {repr(inner_e)}")

    async def _generate_web_note(self, user_id: int, user_comment: str, url: str, extracted_text: str):
        from src.interfaces.telegram.bot import bot
        import datetime
        current_date = datetime.datetime.now().strftime("%Y-%m-%d")
        print(f"[Orchestrator] 📂 Запуск генерации WEB-заметки для {user_id}")
        found_context = await memory.search(user_comment + "\n" + extracted_text[:1000], top_k=3)
        old_context_block = f"<OLD_CONTEXT>\n{found_context}\n</OLD_CONTEXT>\n\n" if found_context else ""
        
        sys_prompt = prompt_loader.get(
            "generate_web_note_prompt", 
            old_context_block=old_context_block,
            user_comment=user_comment,
            url=url,
            current_date=current_date
        )
        safe_prompt = f"<ARTICLE_TEXT>\n{extracted_text}\n</ARTICLE_TEXT>"

        models_to_run = config.AVAILABLE_MODELS.items() if config.COMPARE_MODE else [("CURRENT", config.CURRENT_LLM_MODEL)]

        for model_alias, model_name in models_to_run:
            raw_response = ""
            async with telemetry.track(f"LLM_Web_Inference_{model_alias}"):
                raw_response = await self._execute_llm_inference(user_id, model_name, safe_prompt, sys_prompt)

            if not raw_response:
                continue

            try:
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

                # Корректно восстанавливаем callout-блок Obsidian перед записью на диск
                content = content.replace("[!abstract]", "> [!abstract]")
                content = re.sub(r'PROPERTIES:.*?\n', '', content, flags=re.IGNORECASE).strip()

                async with telemetry.track("Obsidian_File_Write"):
                    file_path = writer.create_note(title=title, content=content, custom_properties=properties, model_name=model_name)

                await memory.memorize_note(
                    note_id=title, 
                    content=content, 
                    metadata={"source": f"Web_Benchmark_{model_alias}", "url": url, "title": title, "folder": "00_Inbox"}
                )

                reply = f"📊 **Выжимка от модели {model_alias.upper()} ({model_name}):**\n✅ Сохранена в Obsidian!\n\n📌 *{title}*\n📂 `00_Inbox`"
                await bot.send_message(chat_id=user_id, text=reply, parse_mode="Markdown")
            except Exception as e:
                print(f"[Orchestrator] ❌ Ошибка сборки веб-заметки: {e}")

    async def _process_url_pipeline(self, event: TextReceivedEvent, target_url: str):
        from src.interfaces.telegram.bot import bot
        print(f"[Orchestrator] 🌐 Запуск анализа веб-страницы от {event.user_id}")
        await bot.send_message(chat_id=event.user_id, text=f"🔗 Изучаю содержимое по ссылке:\n{target_url}...")

        try:
            extracted_text = await asyncio.to_thread(url_parser.extract_text, target_url)
            await bot.send_message(chat_id=event.user_id, text=f"✅ Текст скачан ({len(extracted_text)} символов). Извлекаю факты...")
            await self._generate_web_note(event.user_id, event.text, target_url, extracted_text)
        except Exception as e:
            print(f"[Orchestrator] ❌ Ошибка скачивания страницы: {repr(e)}")
            await bot.send_message(chat_id=event.user_id, text="❌ Не удалось открыть ссылку.")

    async def _process_document_pipeline(self, event: DocumentReceivedEvent):
        from src.interfaces.telegram.bot import bot
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
                await bot.send_message(chat_id=event.user_id, text="❌ Неподдерживаемый формат.")
                return

            if not extracted_text:
                await bot.send_message(chat_id=event.user_id, text="⚠️ Не удалось извлечь текст.")
                return

            await bot.send_message(chat_id=event.user_id, text=f"✅ Текст извлечен ({len(extracted_text)} символов). Формирую выжимку...")
            user_comment = f"Документ: {event.file_name}. " + (event.caption if event.caption else "")
            await self._generate_web_note(event.user_id, user_comment, event.file_name, extracted_text)
        except Exception as e:
            print(f"[Orchestrator] ❌ Ошибка обработки документа: {repr(e)}")
        finally:
            if event.file_path.exists():
                event.file_path.unlink()

    async def _process_voice_pipeline(self, event: VoiceReceivedEvent):
        from src.interfaces.telegram.bot import bot
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
        finally:
            if event.audio_path.exists():
                event.audio_path.unlink()

    async def _process_photo_pipeline(self, event: PhotoReceivedEvent):
        from src.interfaces.telegram.bot import bot
        print(f"[Orchestrator] 👁️ Запуск анализа фото от {event.user_id}")
        await bot.send_message(chat_id=event.user_id, text="👀 Изучаю изображение...")

        user_caption = event.caption if event.caption else "Сделай из этого заметку."
        user_prompt = f"Извлеки весь текст с картинки. Опиши только факты. БЕЗ вступлений. Запрос: {user_caption}"
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
        from src.interfaces.telegram.bot import bot
        print(f"[Orchestrator] 🎬 Запуск анализа медиа-ссылки от {event.user_id}")
        await bot.send_message(chat_id=event.user_id, text="🎬 Обнаружил ссылку на видео. Выкачиваю аудиодорожку...")

        try:
            audio_path = await video_parser.extract_audio(target_url)
            await bot.send_message(chat_id=event.user_id, text="📥 Звук извлечен. Расшифровываю речь...")
            recognized_text = await asyncio.to_thread(stt.transcribe, audio_path)

            if not recognized_text.strip():
                await bot.send_message(chat_id=event.user_id, text="⚠️ Не удалось разобрать речь.")
                return

            await bot.send_message(chat_id=event.user_id, text=f"🗣️ *Текст из видео расшифрован!*\nФормирую заметку...")
            final_text = f"Контекст: Выжимка видео по ссылке {target_url}.\n\nТекст из видео:\n{recognized_text}"
            text_event = TextReceivedEvent(user_id=event.user_id, text=final_text)
            await self._generate_note(text_event)
        except Exception as e:
            print(f"[Orchestrator] ❌ Ошибка Video Pipeline: {repr(e)}")
        finally:
            if 'audio_path' in locals() and audio_path.exists():
                audio_path.unlink()

orchestrator = Orchestrator()