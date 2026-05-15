import re
import shutil
from pathlib import Path
from src.core.config import VAULT_DIR, INBOX_PATH
from src.cognitive.llm_service import llm
from src.infrastructure.vram_scheduler import vram_manager

class ClerkAgent:
    def __init__(self):
        self.inbox = INBOX_PATH
        self.vault = VAULT_DIR
        # Жестко заданные директории для сортировки
        self.categories = ["Work", "Sport", "Home", "Games", "Diary", "Tasks", "Archive"]

    async def run_sorting(self) -> str:
        """Сканирует Инбокс и раскидывает файлы по папкам с помощью LLM."""
        files = list(self.inbox.glob("*.md")) + list(self.inbox.glob("*.canvas"))
        
        if not files:
            return "📭 В `00_Inbox` нет файлов для сортировки."

        results = ["🧹 **Отчет о сортировке:**\n"]

        # Захватываем видеокарту один раз для всей пачки файлов
        async with vram_manager.inference_lock:
            await vram_manager.request_model("hermes3:8b")
            
            for file_path in files:
                try:
                    content = file_path.read_text(encoding="utf-8")
                    
                    # Промпт для классификации
                    sys_prompt = (
                        "Ты — автоматический сортировщик файлов. "
                        f"Выбери ОДНУ наиболее подходящую категорию из списка: {', '.join(self.categories)}. "
                        "Верни СТРОГО одно слово (название категории), без точек и пояснений."
                    )
                    
                    # Читаем только первую 1000 символов для экономии времени и токенов
                    text_to_analyze = content[:1000]
                    
                    print(f"[Clerk] 🤔 Анализирую: {file_path.name}")
                    raw_category = await llm.generate_text(text_to_analyze, system_prompt=sys_prompt)
                    category = raw_category.strip()
                    
                    # Защита от галлюцинаций LLM
                    if category not in self.categories:
                        print(f"[Clerk] ⚠️ LLM выдала дичь ('{category}'), отправляю в Archive.")
                        category = "Archive"

                    # Создаем папку, если ее нет
                    target_dir = self.vault / category
                    target_dir.mkdir(exist_ok=True)
                    new_path = target_dir / file_path.name

                    # Если это Markdown - обновляем YAML перед переносом
                    if file_path.suffix == ".md":
                        # Меняем type: inbox на type: category
                        content = re.sub(r'type:\s*inbox', f'type: {category.lower()}', content, flags=re.IGNORECASE)
                        # Удаляем тег status/new
                        content = re.sub(r'\s*-\s*status/new\n', '\n', content, flags=re.IGNORECASE)
                        
                        new_path.write_text(content, encoding="utf-8")
                        file_path.unlink() # Удаляем оригинал из инбокса
                    else:
                        # Если это .canvas - просто перемещаем
                        shutil.move(str(file_path), str(new_path))

                    results.append(f"✅ `{file_path.name}` ➡️ 📂 **{category}**")
                    
                except Exception as e:
                    print(f"[Clerk] ❌ Ошибка с файлом {file_path.name}: {e}")
                    results.append(f"❌ `{file_path.name}` — Ошибка")

        return "\n".join(results)

clerk = ClerkAgent()