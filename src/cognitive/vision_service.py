import os
import base64
import httpx

class VisionService:
    def __init__(self):
        # Оставляем стандартный локальный порт Windows
        self.ollama_url = "http://127.0.0.1:11434/api/generate"
        
        self.model_name = "llava"

    async def analyze_image(self, image_path: os.PathLike, prompt: str) -> str:
        """ОДНОРОДНЫЙ OCR: Анализ одного скриншота из Телеграма."""
        if not os.path.exists(image_path):
            raise FileNotFoundError(f"Файл не найден: {image_path}")

        with open(image_path, "rb") as image_file:
            image_encoded = base64.b64encode(image_file.read()).decode('utf-8')

        payload = {
            "model": self.model_name,
            "prompt": prompt,
            "images": [image_encoded],  # Передаем картинку в массиве
            "stream": False,
            "options": {
                "temperature": 0.2
            }
        }

        # Таймаут 120 секунд, чтобы тяжелая модель успела обработать картинку на RTX 3090
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(self.ollama_url, json=payload)
            if response.status_code == 200:
                return response.json().get("response", "")
            else:
                raise RuntimeError(f"Ollama error: {response.status_code} - {response.text}")

    async def analyze_image_batch(self, image_paths: list, prompt: str) -> str:
        """ПАКЕТНЫЙ OCR: Анализ раскадровки видео."""
        images_encoded = []
        for img_path in image_paths:
            if os.path.exists(img_path):
                with open(img_path, "rb") as image_file:
                    images_encoded.append(base64.b64encode(image_file.read()).decode('utf-8'))
                    
        if not images_encoded:
            return "Текст на экране не обнаружен (нет кадров для анализа)."

        # ПРИМЕЧАНИЕ: Если используешь llava, пакетный режим может сбоить. 
        # Если будет падать, лучше передавать по одному кадру в цикле.
        payload = {
            "model": self.model_name,
            "prompt": prompt,
            "images": images_encoded,
            "stream": False,
            "options": {
                "temperature": 0.2
            }
        }
        
        async with httpx.AsyncClient(timeout=180.0) as client:
            response = await client.post(self.ollama_url, json=payload)
            if response.status_code == 200:
                return response.json().get("response", "")
            else:
                raise RuntimeError(f"Ollama Batch error: {response.status_code}")

# Экспортируем синглтон
vision_service = VisionService()