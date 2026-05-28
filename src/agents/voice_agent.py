import asyncio

from src.infrastructure.logger import logger
from src.infrastructure.telemetry import telemetry
from src.infrastructure.event_bus import VoiceReceivedEvent, TextReceivedEvent, bus


class VoiceAgent:
    def __init__(self):
        pass

    async def process_voice(self, event: VoiceReceivedEvent):
        """STT на CPU (faster-whisper) и публикация результата в шину как текст."""
        audio_path = event.audio_path
        if not audio_path or not audio_path.exists():
            logger.error(f"[VoiceAgent] Аудиофайл не найден: {audio_path}")
            return

        from src.cognitive.stt_service import stt
        from src.interfaces.telegram.bot import bot

        try:
            await bot.send_chat_action(chat_id=event.user_id, action="typing")

            transcribed_text = ""
            async with telemetry.track(f"STT_Transcribe_{event.user_id}"):
                transcribed_text = await asyncio.to_thread(stt.transcribe, audio_path)

            if transcribed_text and transcribed_text.strip():
                logger.info(
                    f"[VoiceAgent] STT завершён. Длина текста: {len(transcribed_text)} символов."
                )
                text_to_publish = f"Голосовое сообщение:\n\n{transcribed_text.strip()}"
                await bus.publish(
                    TextReceivedEvent(user_id=event.user_id, text=text_to_publish)
                )
            else:
                logger.warning("[VoiceAgent] STT вернул пустой текст.")
                await bot.send_message(
                    chat_id=event.user_id,
                    text="⚠️ Не удалось распознать речь в голосовом сообщении.",
                )

        except Exception as e:
            logger.error(f"[VoiceAgent ❌ Ошибка выполнения пайплайна]: {repr(e)}")
            try:
                await bot.send_message(
                    chat_id=event.user_id,
                    text="❌ Произошла ошибка при распознавании голосового сообщения.",
                )
            except Exception:
                pass


voice_agent = VoiceAgent()
