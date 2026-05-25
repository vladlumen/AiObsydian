import yaml
from pathlib import Path
from src.core.config import BASE_DIR

class PromptLoader:
    def __init__(self):
        self.yaml_path = Path(BASE_DIR) / "src" / "core" / "prompts.yaml"
        self._prompts = {}
        self.load_prompts()

    def load_prompts(self):
        """Загружает или перезагружает промпты из файла."""
        try:
            with open(self.yaml_path, "r", encoding="utf-8") as f:
                self._prompts = yaml.safe_load(f) or {}
            print("[PromptLoader] 📝 Системные промпты успешно загружены.")
        except Exception as e:
            print(f"[PromptLoader] ❌ Ошибка загрузки промптов: {e}")

    def get(self, key: str, **kwargs) -> str:
        """Возвращает отформатированный промпт без использования опасного .format()."""
        template = self._prompts.get(key, "")
        if not template:
            print(f"[PromptLoader] ⚠️ Промпт для ключа '{key}' не найден.")
            return ""
        
        # Безопасная замена переменных по словарю kwargs
        # Заменяет строго '{переменная}', не ломая одиночные или квадратные скобки Obsidian
        result = template
        for k, v in kwargs.items():
            target_placeholder = "{" + str(k) + "}"
            result = result.replace(target_placeholder, str(v))
            
        return result

prompt_loader = PromptLoader()