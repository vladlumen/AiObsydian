import io
import os
import asyncio
from pathlib import Path
from PIL import Image
from src.infrastructure.logger import logger
from src.cognitive.llm_service import llm

class VisionService:
    def __init__(self):
        pass
    
    def _resize_image_for_ocr(self, image_path: Path) -> Path:
        """
        Адаптивное сжатие до 1600px.
        Если это вертикальный скриншот с телефона, сохраняет читаемость шрифтов.
        Возвращает путь к оптимизированному временному файлу.
        """
        try:
            with Image.open(image_path) as img:
                max_size = 1600
                width, height = img.size
                
                # Если изображение уже проходит по лимитам, не трогаем его
                if width <= max_size and height <= max_size:
                    return image_path
                
                # Рассчитываем новые пропорции (LANCZOS сохраняет контрастность букв)
                img.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)
                
                # Создаем временный файл рядом с оригиналом
                temp_path = image_path.parent / f"ocr_prep_{image_path.name}"
                
                # Сохраняем с высоким качеством (92), чтобы не размывать кириллицу
                img.convert("RGB").save(temp_path, format="JPEG", quality=92)
                logger.info(f"[VisionService] 🖼️ Картинка оптимизирована: {width}x{height} -> {img.size[0]}x{img.size[1]}")
                return temp_path
                
        except Exception as e:
            logger.error(f"[VisionService] Ошибка при подготовке изображения: {e!r}")
            return image_path

    async def analyze_image(self, image_path: Path, prompt: str) -> str:
        """Analyze image using vision model with pre-optimizations for high-quality OCR."""
        
        # 1. Запускаем адаптивный ресайз в отдельном потоке (чтобы не блокировать асинхронный луп)
        optimized_path = await asyncio.to_thread(self._resize_image_for_ocr, image_path)
        
        try:
            # 2. Отправляем оптимизированную картинку в Ollama
            result = await llm.analyze_image(
                image_path=optimized_path,
                prompt=prompt,
                system_prompt="",  # No system prompt needed for basic OCR
                model_name="llama3.2-vision"
            )
            return result
            
        finally:
            # 3. Удаляем временный файл, если он был создан, во избежание утечки памяти
            if optimized_path != image_path and optimized_path.exists():
                try:
                    os.remove(optimized_path)
                except Exception:
                    pass

vision_service = VisionService()