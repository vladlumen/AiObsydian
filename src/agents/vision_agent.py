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

        # Ленивые импорты для исключения циклических зависимостей при старте ядра
        from src.cognitive.vision_service import vision_service
        from src.interfaces.telegram.bot import bot
        from src.core.prompt_loader import prompt_loader

        try:
            await bot.send_chat_action(chat_id=event.user_id, action="typing")
            
            # Подгружаем изолированный, строгий vision-промпт из prompts.yaml.
            # Если пользователь передал текстовый комментарий к фото — добавляем его как контекст.
            base_prompt = prompt_loader.get("vision_prompt")
            if event.caption and event.caption.strip():
                prompt = f"{base_prompt}\n\nДополнительное указание от пользователя: {event.caption.strip()}"
            else:
                prompt = base_prompt

            ocr_result = ""
            model_name = "llama3.2-vision"
            
            # Фоновый инференс на GPU с блокировкой семафора VRAM
            async with telemetry.track(f"Vision_Inference_{event.user_id}"):
                async with vram_manager.inference_lock:
                    await vram_manager.request_model(model_name)
                    try:
                        ocr_result = await vision_service.analyze_image(photo_path, prompt)
                    finally:
                        await vram_manager.unload_model(model_name)

            if ocr_result and ocr_result.strip():
                clean_ocr = ocr_result.strip()
                logger.info(f"[VisionAgent] OCR завершено успешно. Длина результата: {len(clean_ocr)}")
                
                # КРИТИЧЕСКИЙ ФИКС: Публикуем СТРОГО чистый текст OCR без префиксов,
                # чтобы NoteGeneratorAgent мог корректно замерить длину строки на входе.
                text_event = TextReceivedEvent(
                    user_id=event.user_id,
                    text=clean_ocr
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