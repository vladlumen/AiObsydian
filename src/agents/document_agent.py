import asyncio

from src.infrastructure.logger import logger
from src.infrastructure.telemetry import telemetry
from src.infrastructure.event_bus import DocumentReceivedEvent, TextReceivedEvent, bus


class DocumentAgent:
    def __init__(self):
        pass

    async def process_document(self, event: DocumentReceivedEvent):
        """Парсинг PDF/DOCX и публикация извлечённого текста в шину."""
        file_path = event.file_path
        if not file_path or not file_path.exists():
            logger.error(f"[DocumentAgent] Файл документа не найден: {file_path}")
            return

        from src.agents.parsers.document_parser import document_parser
        from src.interfaces.telegram.bot import bot

        try:
            await bot.send_chat_action(chat_id=event.user_id, action="typing")

            extracted_text = ""
            async with telemetry.track(f"Document_Parse_{event.user_id}"):
                extracted_text = await asyncio.to_thread(
                    document_parser.extract_text, file_path
                )

            if extracted_text and extracted_text.strip():
                logger.info(
                    f"[DocumentAgent] Парсинг завершён ({event.file_name}). "
                    f"Длина текста: {len(extracted_text)} символов."
                )
                header = f"Документ {event.file_name}:"
                body = extracted_text.strip()
                if event.caption and event.caption.strip():
                    body = f"Комментарий пользователя: {event.caption.strip()}\n\n{body}"
                text_to_publish = f"{header}\n\n{body}"
                await bus.publish(
                    TextReceivedEvent(user_id=event.user_id, text=text_to_publish)
                )
            else:
                logger.warning(f"[DocumentAgent] Пустой текст после парсинга: {event.file_name}")
                await bot.send_message(
                    chat_id=event.user_id,
                    text="⚠️ Документ не содержит распознаваемого текста.",
                )

        except ValueError as e:
            logger.warning(f"[DocumentAgent] Ошибка парсинга {event.file_name}: {e}")
            try:
                await bot.send_message(
                    chat_id=event.user_id,
                    text=f"⚠️ {e}",
                )
            except Exception:
                pass

        except Exception as e:
            logger.error(f"[DocumentAgent ❌ Ошибка выполнения пайплайна]: {repr(e)}")
            try:
                await bot.send_message(
                    chat_id=event.user_id,
                    text="❌ Произошла ошибка при обработке документа.",
                )
            except Exception:
                pass


document_agent = DocumentAgent()
