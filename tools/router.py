import re
import ollama
from src.infrastructure import logger

class TaskRouter:
    # Расширенный список ключевых слов
    INTENT_PATTERNS = {
        "SEARCH": r"(найди|вспомни|поиск|что известно|архив|расскажи|кто такой|что такое)",
        "WRITE": r"(запиши|создай|напиши|сделай заметку|новый файл|сохрани|зафиксируй|заметка)",
        "APPEND": r"(дополни|добавь в|обнови|впиши в)"
    }

    @staticmethod
    def classify_intent(query: str) -> str:
        query_lc = query.lower()
        
        # 1. Regex Stage
        for intent, pattern in TaskRouter.INTENT_PATTERNS.items():
            if re.search(pattern, query_lc):
                logger.agent_logger.info("Router", f"Regex match: {intent}")
                return intent

        # 2. LLM Stage с усиленным промптом
            logger.agent_logger.info("Router", "Regex не сработал. Запрос к LLM...")
        try:
            temp_client = ollama.Client(host="http://127.0.0.1:11434")
            system_prompt = (
                "Ты — диспетчер команд. Твоя задача выбрать один из трех типов действий:\n"
                "WRITE: если пользователь просит что-то СОЗДАТЬ, НАПИСАТЬ или ЗАПИСАТЬ новую информацию.\n"
                "SEARCH: если пользователь ЗАДАЕТ ВОПРОС или просит НАЙТИ информацию в памяти.\n"
                "APPEND: если просят ДОБАВИТЬ информацию в уже существующий файл.\n"
                "Ответь только одним словом."
            )
            
            res = temp_client.generate(
                model="hermes3:8b", 
                system=system_prompt,
                prompt=f"Запрос пользователя: '{query}'\nИнтент:",
                options={"temperature": 0} # Максимальная точность без фантазий
            )
            intent = res['response'].strip().upper().replace(".", "")
            
            if intent in ["SEARCH", "WRITE", "APPEND"]:
                return intent
            return "SEARCH"
        except Exception as e:
            agent_logger.error("Router", f"Ошибка LLM роутера: {e}")
            return "SEARCH"
