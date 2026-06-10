# src/cognitive/vision_service.py

import os
import base64
import httpx
from io import BytesIO
from pathlib import Path
from PIL import Image

class VisionService:
    def __init__(self):
        self.model_name = "qwen3-vl:8b"
        self.max_side_single = 1600
        self.max_side_batch = 1024

    def _prepare_image_base64(self, image_path: Path, max_side: int, quality: int) -> str:
        with Image.open(image_path) as img:
            if img.mode in ("RGBA", "P"):
                img = img.convert('RGB')
            
            width, height = img.size
            if width > max_side or height > max_side:
                img.thumbnail((max_side, max_side), Image.Resampling.LANCZOS)
            
            buffer = BytesIO()
            img.save(buffer, format="JPEG", quality=quality)
            return base64.b64encode(buffer.getvalue()).decode('utf-8')

    async def analyze_image(self, image_path: os.PathLike, prompt: str) -> str:
        """ОДНОРОДНЫЙ OCR: Анализ одного скриншота с подавлением мыслей."""
        from src.cognitive.llm_service import llm
        
        path_obj = Path(image_path)
        if not path_obj.exists():
            raise FileNotFoundError(f"Файл не найден: {path_obj}")

        encoded_image = self._prepare_image_base64(path_obj, max_side=self.max_side_single, quality=90)

        # 1. ОБЯЗАТЕЛЬНО ЖЕСТКИЙ СИСТЕМНЫЙ ПРОМПТ ПРОТИВ REASONING LEAKAGE
        ocr_prompt = (
            "Return ONLY the final extracted text.\n"
            "Do not show reasoning.\n"
            "Do not use internal analysis.\n\n"
            f"Task: {prompt}"
        )

        # 4. КРИТИЧЕСКИЙ ТЕСТ: Раскомментируй строку ниже, чтобы проверить чистый пайплайн
        # ocr_prompt = "Return ONLY one word: OK"

        payload = {
            "model": self.model_name,
            "prompt": ocr_prompt,
            "images": [encoded_image],
            "stream": False,
            "options": {
                "num_ctx": 4096,
                "num_predict": 4096,     # 2. УВЕЛИЧЕНО до максимума
                "temperature": 0.0,
                "num_gpu": 99,
                "think": False,          # 3. СПЕЦ-РЕЖИМ для отключения рассуждений Ollama
                "reasoning": False       # Альтернативный флаг для старых/кастомных сборок
            }
        }

        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(llm.base_url + "/api/generate", json=payload)
            response.raise_for_status()
            
            json_data = response.json()
            result_text = json_data.get("response", "").strip()
            
            # Фоллбэк на случай, если модель проигнорировала флаги и записала текст в thinking
            if not result_text and json_data.get("thinking"):
                result_text = json_data.get("thinking", "").strip()
                
            return result_text

    async def analyze_image_batch(self, image_paths: list, prompt: str) -> str:
        """ПАКЕТНЫЙ OCR: Анализ раскадровки видео с оптимизацией веса кадров."""
        from src.cognitive.llm_service import llm
        
        images_encoded = []
        for img_path in image_paths:
            path_obj = Path(img_path)
            if path_obj.exists():
                try:
                    encoded = self._prepare_image_base64(path_obj, max_side=self.max_side_batch, quality=85)
                    images_encoded.append(encoded)
                except Exception as e:
                    print(f"[VisionService] Не удалось обработать кадр {img_path}: {e}")
                    
        if not images_encoded:
            return "Текст на экране не обнаружен (нет кадров для анализа)."

        payload = {
            "model": self.model_name,
            "prompt": prompt,
            "images": images_encoded,
            "stream": False,
            "options": {
                "num_ctx": 4096,
                "num_predict": 2048,
                "temperature": 0.0,
                "num_gpu": 99,
                "think": False,
                "reasoning": False
            }
        }
        
        async with httpx.AsyncClient(timeout=300.0) as client:
            try:
                response = await client.post(llm.base_url + "/api/generate", json=payload)
                response.raise_for_status()
                return response.json().get("response", "").strip()
            except Exception as e:
                print(f"[VisionService] ❌ Ошибка пакетного Vision API: {e}")
                return ""

# Экспортируем синглтон
vision_service = VisionService()