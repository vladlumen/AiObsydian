import asyncio
import os
import re
from datetime import datetime

from src.infrastructure.logger import logger
from src.infrastructure.vram_scheduler import vram_manager
from src.infrastructure.telemetry import telemetry
from src.infrastructure.event_bus import TextReceivedEvent
from src.core import config

URL_PATTERN = re.compile(r"https?://[^\s<>\"]+", re.IGNORECASE)


class NoteGeneratorAgent:
    def __init__(self):
        self.max_title_len = 55

    def _parse_llm_response(self, raw: str) -> tuple[str, str, str]:
        """Извлекает PROPERTIES, TITLE и CONTENT из ответа Hermes."""
        properties = ""
        title = ""
        content = ""

        props_match = re.search(r"PROPERTIES:\s*(.*?)(?=\nTITLE:|\Z)", raw, re.DOTALL | re.IGNORECASE)
        title_match = re.search(r"TITLE:\s*(.*?)(?=\nCONTENT:|\Z)", raw, re.DOTALL | re.IGNORECASE)
        content_match = re.search(r"CONTENT:\s*(.*)\Z", raw, re.DOTALL | re.IGNORECASE)

        if props_match:
            properties = props_match.group(1).strip()
        if title_match:
            title = title_match.group(1).strip()
        if content_match:
            content = content_match.group(1).strip()

        return properties, title, content

    def _extract_url(self, text: str) -> str | None:
        match = URL_PATTERN.search(text)
        if not match:
            return None
        return match.group(0).rstrip(".,);]")

    def _format_old_context_block(self, chunks: list) -> str:
        if not chunks or not isinstance(chunks, list):
            return "<OLD_CONTEXT>\n(Связанных заметок в базе не найдено)\n</OLD_CONTEXT>"

        formatted_chunks = []
        for chunk in chunks:
            if not isinstance(chunk, dict):
                continue
            file_path = chunk.get("file_path", "Unknown")
            meta = chunk.get("metadata") or {}
            if not isinstance(meta, dict):
                meta = {}
            header_path = chunk.get("header_path") or meta.get("header_path", "")
            text_content = (chunk.get("text") or "").strip()
            header_info = f" -> {header_path}" if header_path else ""
            formatted_chunks.append(
                f"--- Source: {file_path}{header_info} ---\n{text_content}"
            )

        body = "\n\n".join(formatted_chunks)
        return f"<OLD_CONTEXT>\n{body}\n</OLD_CONTEXT>"

    def _extract_clean_titles(self, chunks: list, current_title: str = "") -> str:
        if not chunks or not isinstance(chunks, list):
            return "Связанных заметок не найдено."
            
        titles = set()
        for chunk in chunks:
            if not isinstance(chunk, dict):
                continue
            file_path = chunk.get("file_path", "")
            if file_path:
                base_name = os.path.basename(file_path).replace(".md", "")
                
                # Исключаем текущую заметку из списка связей
                if current_title and current_title.lower() in base_name.lower():
                    continue
                    
                titles.add(f"[[{base_name}]]")
                
        return ", ".join(titles) if titles else "Связанных заметок не найдено."

    def _detect_dynamic_tags(self, text: str) -> str:
        """Лингвистический анализатор контента для автоматической генерации тегов."""
        normalized = text.lower()
        tags = []

        # Триггеры для киноиндустрии
        if any(w in normalized for w in ["фильм", "кино", "комедия", "боевик", "режиссер", "сериал", "актер", "сценарий"]):
            tags.append("кино")
        
        # Триггеры для IT контента
        if any(w in normalized for w in ["python", "api", "vram", "gpu", "код", "баг", "wsl", "docker", "git"]):
            tags.append("it")

        return ", ".join(tags) if tags else ""

    async def process_text(self, event: TextReceivedEvent):
        """LLM-структурирование входящего текста и запись заметки в Obsidian Vault без кэширования."""
        raw_text = event.text.strip()
        from src.core.orchestrator import is_rag_query

        if not raw_text or is_rag_query(raw_text):
            return

        # === ТОТАЛЬНАЯ ЗАЩИТА НА ВХОДЕ ===
        if len(raw_text) < 150 and any(word in raw_text.lower() for word in ["ты", "задача", "промпт", "архитектор"]):
            logger.warning(f"[NoteGeneratorAgent] 🛑 Входной фильтр отклонил мусорный/битый OCR-текст ({len(raw_text)} симв.). Пайплайн остановлен.")
            return

        from src.cognitive.memory.semantic import memory
        from src.cognitive.llm_service import llm
        from src.core.prompt_loader import prompt_loader
        from src.agents.obsidian_writer import writer
        from src.agents.parsers.url_parser import url_parser
        from src.interfaces.telegram.bot import bot

        current_date = datetime.now().strftime("%Y-%m-%d")

        try:
            await bot.send_chat_action(chat_id=event.user_id, action="typing")

            # ШАГ 1: ОЧИСТКА ПОИСКОВОГО ЗАПРОСА ОТ ШУМА ИНТЕРФЕЙСОВ
            clean_query = raw_text
            noise_words = [
                "stillvasilisa", "itsretych", "Войдите, чтобы", "Нравится", 
                "прокомментировать", "Посмотреть все", "комментарии", "3 939", "270", "1 дн."
            ]
            for word in noise_words:
                clean_query = clean_query.replace(word, "")
            
            # Берем чистые символы для контекстного поиска в LanceDB
            context_query = clean_query.strip()[:300]
            old_context_block = "<OLD_CONTEXT>\n(пусто)\n</OLD_CONTEXT>"
            available_links = "Связанных заметок не найдено."

            # КРИТИЧЕСКИЙ ФИКС: Если это OCR-текст, изолируем контекст RAG,
            # чтобы старые кривые фильмы из базы не ломали генерацию новой карточки.
            if getattr(event, "is_ocr", False):
                old_context_block = "<OLD_CONTEXT>\n(Контекст изолирован во избежание коллизий)\n</OLD_CONTEXT>"
                available_links = "Связанных заметок не найдено."
            else:
                async with telemetry.track(f"Note_Retrieve_Context_{event.user_id}"):
                    chunks = await memory.retrieve_context(context_query, limit=3)
                    old_context_block = self._format_old_context_block(chunks)
                    available_links = self._extract_clean_titles(chunks, current_title=raw_text[:30])

            # Вычисляем динамические теги перед загрузкой промпта
            dynamic_tags = self._detect_dynamic_tags(raw_text)

            # Загружаем базовый системный промпт с передачей dynamic_tags
            system_prompt = prompt_loader.get(
                "generate_note_prompt",
                old_context_block=old_context_block,
                available_links=available_links,
                current_date=current_date,
                dynamic_tags=dynamic_tags,
            )
            
            # КРИТИЧЕСКИЙ ФИКС: Строгое изолирование сырых данных в XML-структуру
            user_payload = (
                f"<DATA_PAYLOAD>\n"
                f"CURRENT_METADATA_DATE: {current_date}\n"
                f"SOURCE_MATERIAL_RAW_TEXT:\n"
                f"\"\"\"\n{raw_text}\n\"\"\"\n"
                f"</DATA_PAYLOAD>"
            )

            url = self._extract_url(raw_text)

            if url:
                user_comment = URL_PATTERN.sub("", raw_text).strip() or "—"
                async with telemetry.track(f"Note_URL_Fetch_{event.user_id}"):
                    try:
                        article_text = await url_parser.extract_text(url)
                    except Exception as url_err:
                        logger.warning(f"[NoteGeneratorAgent] ⚠️ Не удалось спарсить контент по ссылке {url}: {url_err!r}")
                        article_text = None

                if article_text and article_text.strip():
                    system_prompt = prompt_loader.get(
                        "generate_web_note_prompt",
                        old_context_block=old_context_block,
                        available_links=available_links,
                        current_date=current_date,
                        user_comment=user_comment,
                        url=url,
                    )
                    user_payload = f"<ARTICLE_TEXT>\n{article_text.strip()}\n</ARTICLE_TEXT>"
                else:
                    user_payload = (
                        f"<NEW_DATA>\n"
                        f"Ссылка: {url}\n"
                        f"Комментарий пользователя: {user_comment}\n"
                        f"(Примечание: контент страницы недоступен, обработай только этот комментарий)\n"
                        f"</NEW_DATA>"
                    )

            # Прямой инференс на GPU
            async with telemetry.track(f"Note_LLM_Inference_{event.user_id}"):
                async with vram_manager.inference_lock:
                    await vram_manager.request_model(config.CURRENT_LLM_MODEL)
                    try:
                        llm_response = await llm.generate_text(
                            user_payload,
                            system_prompt=system_prompt,
                            model=config.CURRENT_LLM_MODEL,
                        )
                    finally:
                        await vram_manager.unload_model(config.CURRENT_LLM_MODEL)

            if not llm_response or not llm_response.strip():
                await bot.send_message(chat_id=event.user_id, text="⚠️ Модель не смогла сформировать заметку.")
                return

            # Парсинг структурированного ответа
            properties, title, content = self._parse_llm_response(llm_response)

            if title and any(bad_word in title.lower() for bad_word in ["всемирной паутины", "системный архитектор обнаружил"]):
                logger.warning(f"[NoteGeneratorAgent] 🚨 Обнаружен бред модели в ответе! Генерация отклонена.")
                await bot.send_message(
                    chat_id=event.user_id, 
                    text="⚠️ Модель выдала некорректный галлюцинаторный ответ. Отправьте запрос повторно для чистой перегенерации."
                )
                return

            # --- ФИКС ЗАГОЛОВКА СТАРТ ---
            if title:
                title = title.strip()
                # Удаляем мусорные знаки препинания и кавычки
                title = re.sub(r'[\'":\.\«\»\“\”]', '', title)
                title = title.replace('...', '').strip()
                
                # Фильтр описательного шума: убираем слова "фильм", "кино", если модель добавила их в заголовок
                title = re.sub(r'\b(фильм|кино|краткая суть|заметка)\b', '', title, flags=re.IGNORECASE).strip()
                
                # Схлопываем лишние пробелы, если они образовались после чистки
                title = re.sub(r'\s+', ' ', title)

                # Принудительное ограничение длины по символам
                if len(title) > self.max_title_len:
                    title = title[:self.max_title_len - 3].strip() + "..."
                
                title = f"{current_date} {title}"
            else:
                title = f"{current_date} Заметка"
            # --- ФИКС ЗАГОЛОВКА КОНЕЦ ---

            if not content:
                content = llm_response.strip()

            # Слой нормализации разметки Callout-блоков Obsidian
            if "![abstract]" in content or "!abstract" in content:
                content = content.replace("> ![abstract] Резюме", "").replace("!abstract Резюме", "").strip()
                content = content.lstrip(">").lstrip("!").replace("abstract]", "").strip()
            
            target_marker = None
            if "## Извлеченные факты" in content:
                target_marker = "## Извлеченные факты"
            elif "## Детали" in content:
                target_marker = "## Детали"

            if target_marker:
                parts = content.split(target_marker)
                summary_text = parts[0].strip().lstrip(">").strip()
                facts_text = parts[1].strip()
                
                content = (
                    f"> [!abstract] Резюме\n"
                    f"> {summary_text}\n\n"
                    f"{target_marker}\n"
                    f"{facts_text}"
                )

            note_path = writer.create_note(
                title=title,
                content=content,
                custom_properties=properties,
                model_name=config.CURRENT_LLM_MODEL,
            )

            from src.agents.sync_worker import sync_worker
            try:
                await sync_worker.index_single_file(note_path)
            except Exception as index_err:
                logger.warning(f"[NoteGeneratorAgent] Заметка сохранена, но индексация RAG не удалась: {index_err!r}")

            logger.info(f"[NoteGeneratorAgent] Заметка успешно записана: {note_path.name}")
            await bot.send_message(
                chat_id=event.user_id,
                text=f"✅ Заметка сохранена в Obsidian:\n`{note_path.name}`",
            )

        except Exception as e:
            logger.error(f"[NoteGeneratorAgent ❌ Критическая ошибка]: {repr(e)}")
            try:
                await bot.send_message(chat_id=event.user_id, text="❌ Произошла ошибка при создании заметки.")
            except Exception:
                pass


note_generator = NoteGeneratorAgent()