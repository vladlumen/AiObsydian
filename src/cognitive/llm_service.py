import base64
import httpx
from io import BytesIO
from PIL import Image
from ollama import AsyncClient

class LLMService:
    def __init__(self, default_model: str = "hermes3:8b"):
        self.default_model = default_model
        self.client = AsyncClient()
        self.base_url = "http://localhost:11434" # Стандартный адрес Ollama

    async def is_alive(self) -> bool:
        """Проверяет, запущена ли Ollama (быстрый пинг)."""
        try:
            async with httpx.AsyncClient() as http_client:
                response = await http_client.get(self.base_url, timeout=1.0)
                return response.status_code == 200
        except Exception:
            return False

    async def generate_text(self, user_text: str, system_prompt: str = "") -> str:
        """Отправляет запрос в локальную Ollama."""
        # 1. Сначала проверяем пульс
        if not await self.is_alive():
            print("[LLMService] ❌ Ollama не отвечает!")
            return "⚠️ Система: Сервер Ollama отключен. Пожалуйста, запустите его."

        # 2. Если жива - формируем промпт
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
             
        messages.append({"role": "user", "content": user_text})

        try:
            response = await self.client.chat(
                model=self.default_model,
                messages=messages
            )
            return response['message']['content'].strip()
        except Exception as e:
            print(f"[LLMService] ❌ Ошибка генерации: {e}")
            return "Произошла ошибка при генерации ответа."

    async def analyze_image(self, image_path: Path, prompt: str, system_prompt: str = "", model_name: str = "llava") -> str:
        """Сжимает фото, кодирует в base64 и отправляет в Vision модель."""
        print(f"[LLMService] 👁️ Подготовка изображения {image_path.name}...")
        
        # Оптимизация изображения: сжимаем до 800px по большей стороне
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
            "prompt": prompt,
            "system": system_prompt,
            "images": [base64_image],
            "stream": False
        }

        async with httpx.AsyncClient() as client:
            response = await client.post(f"{self.base_url}/api/generate", json=payload, timeout=300.0)
            response.raise_for_status()
            return response.json().get("response", "").strip()

    async def get_embedding(self, text: str, model_name: str = "nomic-embed-text") -> list[float]:
        """Получает векторное представление (эмбеддинг) текста от Ollama."""
        # Для nomic-embed-text рекомендуется добавлять префикс для документов и запросов,
        # но пока для простоты шлем как есть.
        payload = {
            "model": model_name,
            "prompt": text
        }
        
        # Эмбеддинги считаются быстро, таймаут можно сделать небольшим
        async with httpx.AsyncClient() as client:
            response = await client.post(f"{self.base_url}/api/embeddings", json=payload, timeout=30.0)
            response.raise_for_status()
            return response.json().get("embedding", [])

llm = LLMService()