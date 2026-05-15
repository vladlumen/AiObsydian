import httpx
from ollama import AsyncClient

class LLMService:
    def __init__(self, default_model: str = "hermes3:8b"):
        self.default_model = default_model
        self.client = AsyncClient()
        self.api_url = "http://localhost:11434" # Стандартный адрес Ollama

    async def is_alive(self) -> bool:
        """Проверяет, запущена ли Ollama (быстрый пинг)."""
        try:
            async with httpx.AsyncClient() as http_client:
                response = await http_client.get(self.api_url, timeout=1.0)
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

llm = LLMService()