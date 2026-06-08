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
        pass

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

            # ШАГ 1: ОЧИСТКА ПОИСКОВОГО ЗАПРОСА
            clean_query = raw_text
            # Удаляем технические маркеры интерфейса Instagram/TikTok, которые ломают векторный поиск
            noise_words = [
                "stillvasilisa", "itsretych", "Войдите, чтобы", "Нравится", 
                "прокомментировать", "Посмотреть все", "комментарии", "3 939", "270", "1 дн."
            ]
            for word in noise_words:
                clean_query = clean_query.replace(word, "")
            
            # Берем первые 300 чистых символов OCR для контекстного поиска в LanceDB
            context_query = clean_query.strip()[:300]
            old_context_block = "<OLD_CONTEXT>\n(пусто)\n</OLD_CONTEXT>"
            available_links = "Связанных заметок не найдено."

            async with telemetry.track(f"Note_Retrieve_Context_{event.user_id}"):
                chunks = await memory.retrieve_context(context_query, limit=3)
                old_context_block = self._format_old_context_block(chunks)
                available_links = self._extract_clean_titles(chunks, current_title=raw_text[:30])

            system_prompt = prompt_loader.get(
                "generate_note_prompt",
                old_context_block=old_context_block,
                available_links=available_links,
                current_date=current_date,
            )
            user_payload = f"<NEW_DATA>\n{raw_text}\n</NEW_DATA>"

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
                    user_payload = f"<NEW_DATA>\nСсылка: {url}\nКомментарий пользователя: {user_comment}\n(Примечание: контент страницы недоступен для парсера, обработай только комментарий и ссылку)\n</NEW_DATA>"

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
                # Очищаем от кавычек, двоеточий, точек и троеточий
                title = title.strip()
                title = re.sub(r'[\'":\.]', '', title)
                title = title.replace('...', '').strip()
                
                # Принудительное ограничение длины по символам (не длиннее 55 знаков для лаконичности)
                if len(title) > 55:
                    title = title[:52].strip() + "..."
                
                title = f"{current_date} {title}"
            else:
                title = f"{current_date} Заметка"
            # --- ФИКС ЗАГОЛОВКА КОНЕЦ ---

            if not content:
                content = llm_response.strip()

            # Слой нормализации разметки
            if "![abstract]" in content or "!abstract" in content:
                content = content.replace("> ![abstract] Резюме", "").replace("!abstract Резюме", "").strip()
                content = content.lstrip(">").lstrip("!").replace("abstract]", "").strip()
            
            # Формируем гарантированный Callout-блок Obsidian
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