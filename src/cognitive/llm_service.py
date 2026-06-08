import base64
import httpx
from io import BytesIO
from pathlib import Path
from PIL import Image
from ollama import AsyncClient

class LLMService:
    def __init__(self, default_model: str = "hermes3:8b"):
        self.default_model = default_model
        self.client = AsyncClient()
        self.base_url = "http://localhost:11434"

    async def is_alive(self) -> bool:
        try:
            async with httpx.AsyncClient() as http_client:
                response = await http_client.get(self.base_url, timeout=1.0)
                return response.status_code == 200
        except Exception:
            return False

    async def generate_text(self, user_text: str, system_prompt: str = "", model: str = None) -> str:
        """Отправляет запрос через плоский API /api/generate для жесткого отключения CoT."""
        if not await self.is_alive():
            print("[LLMService] ❌ Ollama не отвечает!")
            return "⚠️ Система: Сервер Ollama отключен."

        model_to_use = model or self.default_model
        
        # Склеиваем системный промпт и пользовательские данные в один монолитный контекст
        full_prompt = ""
        if system_prompt:
            full_prompt += f"Системная инструкция:\n{system_prompt.strip()}\n\n"
        full_prompt += f"Входящие данные:\n{user_text.strip()}\n\nОтвет:"

        payload = {
            "model": model_to_use,
            "prompt": full_prompt,
            "stream": False,
            "options": {
                "temperature": 0.0,
                "num_gpu": 99,
                "low_vram": False,
                "num_ctx": 4096,
                "num_predict": 1024
            }
        }

        try:
            async with httpx.AsyncClient() as http_client:
                response = await http_client.post(
                    f"{self.base_url}/api/generate", 
                    json=payload, 
                    timeout=60.0
                )
                response.raise_for_status()
                result_json = response.json()
                
                # Извлекаем плоский ответ из эндпоинта generate
                output_text = result_json.get("response", "").strip()
                return output_text
                
        except Exception as e:
            print(f"[LLMService] ❌ Ошибка генерации текста через /api/generate: {e}")
            return ""

    async def analyze_image(self, image_path: Path, prompt: str, system_prompt: str = "", model_name: str = "llava") -> str:
        print(f"[LLMService] 👁️ Подготовка изображения {image_path.name}...")
        
        with Image.open(image_path) as img:
            if img.mode != 'RGB':
                img = img.convert('RGB')
            img.thumbnail((800, 800), Image.Resampling.LANCZOS)
            
            buffer = BytesIO()
            img.save(buffer, format="JPEG", quality=85)
            base64_image = base64.b64encode(buffer.getvalue()).decode('utf-8')

        print(f"[LLMService] 🚀 Изображение сжато. Отправляю в {model_name}...")

        payload = {
            "model": model_name,
            "prompt": f"{system_prompt}\n\nЗапрос: {prompt}" if system_prompt else prompt,
            "images": [base64_image],
            "stream": False,
            "options": {
                "num_ctx": 2048,
                "num_predict": 512,
                "temperature": 0.0,
                "num_gpu": 99
            }
        }

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(f"{self.base_url}/api/generate", json=payload, timeout=120.0)
                response.raise_for_status()
                return response.json().get("response", "").strip()
        except Exception as e:
            print(f"[LLMService] ❌ Ошибка Vision API: {e}")
            return ""

    async def get_embedding(self, text: str, model_name: str = "nomic-embed-text") -> list[float]:
        if not text or not text.strip():
            return []

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.base_url}/api/embed",
                    json={"model": model_name, "input": text},
                    timeout=30.0,
                )
                response.raise_for_status()
                data = response.json()
                embeddings = data.get("embeddings")
                if embeddings:
                    return embeddings[0]
                return data.get("embedding", []) or []
        except Exception as e:
            print(f"[LLMService] ⚠️ /api/embed недоступен ({e}), пробую legacy /api/embeddings...")

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.base_url}/api/embeddings",
                    json={"model": model_name, "prompt": text},
                    timeout=30.0,
                )
                response.raise_for_status()
                return response.json().get("embedding", []) or []
        except Exception as e:
            print(f"[LLMService] ❌ Ошибка эмбеддинга: {e}")
            return []

llm = LLMService()