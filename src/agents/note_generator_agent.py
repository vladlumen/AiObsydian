import asyncio
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

        props_match = re.search(
            r"PROPERTIES:\s*(.*?)(?=\nTITLE:|\Z)",
            raw,
            re.DOTALL | re.IGNORECASE,
        )
        title_match = re.search(
            r"TITLE:\s*(.*?)(?=\nCONTENT:|\Z)",
            raw,
            re.DOTALL | re.IGNORECASE,
        )
        content_match = re.search(
            r"CONTENT:\s*(.*)\Z",
            raw,
            re.DOTALL | re.IGNORECASE,
        )

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
        if not chunks:
            return "<OLD_CONTEXT>\n(Связанных заметок в базе не найдено)\n</OLD_CONTEXT>"

        formatted_chunks = []
        for chunk in chunks:
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

    async def process_text(self, event: TextReceivedEvent):
        """LLM-структурирование входящего текста и запись заметки в Obsidian Vault."""
        raw_text = event.text.strip()
        from src.core.orchestrator import is_rag_query

        if not raw_text or is_rag_query(raw_text):
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

            context_query = raw_text[:500]
            old_context_block = "<OLD_CONTEXT>\n(пусто)\n</OLD_CONTEXT>"
            async with telemetry.track(f"Note_Retrieve_Context_{event.user_id}"):
                chunks = await memory.retrieve_context(context_query, limit=3)
                old_context_block = self._format_old_context_block(chunks)

            url = self._extract_url(raw_text)
            llm_response = ""

            if url:
                user_comment = URL_PATTERN.sub("", raw_text).strip() or "—"
                async with telemetry.track(f"Note_URL_Fetch_{event.user_id}"):
                    article_text = await asyncio.to_thread(
                        url_parser.extract_text, url
                    )

                system_prompt = prompt_loader.get(
                    "generate_web_note_prompt",
                    old_context_block=old_context_block,
                    current_date=current_date,
                    user_comment=user_comment,
                    url=url,
                )
                user_payload = (
                    f"<ARTICLE_TEXT>\n{article_text.strip()}\n</ARTICLE_TEXT>"
                )
            else:
                system_prompt = prompt_loader.get(
                    "generate_note_prompt",
                    old_context_block=old_context_block,
                    current_date=current_date,
                )
                user_payload = f"<NEW_DATA>\n{raw_text}\n</NEW_DATA>"

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
                await bot.send_message(
                    chat_id=event.user_id,
                    text="⚠️ Модель не смогла сформировать заметку.",
                )
                return

            properties, title, content = self._parse_llm_response(llm_response)

            if title:
                title = title.strip().replace('"', '').replace("'", "")
                title = f"{current_date} {title}"
            else:
                title = f"{current_date} Заметка"

            if not content:
                content = llm_response.strip()

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
                logger.warning(
                    f"[NoteGeneratorAgent] Заметка сохранена, но индексация RAG не удалась: {index_err!r}"
                )

            logger.info(f"[NoteGeneratorAgent] Заметка записана: {note_path.name}")
            await bot.send_message(
                chat_id=event.user_id,
                text=f"✅ Заметка сохранена в Obsidian:\n`{note_path.name}`",
            )

        except ValueError as e:
            logger.warning(f"[NoteGeneratorAgent] Ошибка обработки: {e}")
            try:
                await bot.send_message(chat_id=event.user_id, text=f"⚠️ {e}")
            except Exception:
                pass

        except Exception as e:
            logger.error(f"[NoteGeneratorAgent ❌ Ошибка выполнения пайплайна]: {repr(e)}")
            try:
                await bot.send_message(
                    chat_id=event.user_id,
                    text="❌ Произошла ошибка при создании заметки.",
                )
            except Exception:
                pass


note_generator = NoteGeneratorAgent()
