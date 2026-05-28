from src.infrastructure.logger import logger
from src.infrastructure.vram_scheduler import vram_manager
from src.infrastructure.telemetry import telemetry
from src.infrastructure.event_bus import PhotoReceivedEvent, TextReceivedEvent, bus
from src.core import config

class VisionAgent:
    def __init__(self):
        pass

    async def process_photo(self, event: PhotoReceivedEvent):
        """Анализ изображения (OCR) и отправка результата в шину событий."""
        photo_path = event.photo_path
        if not photo_path or not photo_path.exists():
            logger.error(f"[VisionAgent] Файл изображения не найден: {photo_path}")
            return

        # Ленивые импорты тяжелых зависимостей для предотвращения циклических импортов
        from src.cognitive.vision_service import vision_service
        from src.interfaces.telegram.bot import bot

        try:
            # Уведомляем пользователя о начале анализа
            await bot.send_chat_action(chat_id=event.user_id, action="typing")
            
            prompt = event.caption.strip() if event.caption else (
                "Распознай текст на изображении (если есть) и подробно опиши, что на нём показано. "
                "Если это код или таблица, выведи их полностью."
            )

            ocr_result = ""
            model_name = "llama3.2-vision"
            
            # Инференс на GPU с захватом семафора VRAM
            async with telemetry.track(f"Vision_Inference_{event.user_id}"):
                async with vram_manager.inference_lock:
                    await vram_manager.request_model(model_name)
                    try:
                        ocr_result = await vision_service.analyze_image(photo_path, prompt)
                    finally:
                        await vram_manager.unload_model(model_name)

            if ocr_result and ocr_result.strip():
                logger.info(f"[VisionAgent] OCR завершено успешно. Длина результата: {len(ocr_result)}")
                
                # Добавляем поясняющий заголовок для результирующего сообщения
                text_to_publish = f"Результат распознавания изображения:\n\n{ocr_result}"
                
                # Публикуем результат в виде TextReceivedEvent для дальнейшей обработки текстовым RAG / Note конвейером
                text_event = TextReceivedEvent(
                    user_id=event.user_id,
                    text=text_to_publish
                )
                await bus.publish(text_event)
            else:
                logger.warning("[VisionAgent] Модель вернула пустой результат OCR.")
                await bot.send_message(chat_id=event.user_id, text="⚠️ Не удалось распознать текст на изображении.")

        except Exception as e:
            logger.error(f"[VisionAgent ❌ Ошибка выполнения пайплайна]: {repr(e)}")
            try:
                await bot.send_message(chat_id=event.user_id, text="❌ Произошла ошибка при обработке изображения.")
            except:
                pass

vision_agent = VisionAgent()
