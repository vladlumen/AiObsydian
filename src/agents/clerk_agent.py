import os
import shutil
from pathlib import Path
from src.core.config import INBOX_PATH, VAULT_DIR
from src.infrastructure.vram_scheduler import vram_manager
from src.cognitive.llm_service import llm

class ClerkAgent:
    def __init__(self):
        self.categories = ["work", "sport", "trips", "task", "diary"]

    async def run_sorting(self) -> str:
        """Сканирует Inbox и физически раскидывает файлы по папкам."""
        files = list(INBOX_PATH.glob("*.md"))
        if not files:
            return "📭 Папка `00_Inbox` пуста. Сортировать нечего."

        report = ["🧹 **Отчет сортировки:**"]
        moved_count = 0

        # Блокируем VRAM один раз для всей партии файлов, чтобы не дергать модель туда-сюда
        async with vram_manager.inference_lock:
            await vram_manager.request_model("hermes3:8b")
            
            for file_path in files:
                try:
                    content = file_path.read_text(encoding='utf-8')
                    
                    # Защита от переполнения контекста: берем только первые 1500 символов для анализа темы
                    snippet = content[:1500] 
                    
                    prompt = f"""
                    Проанализируй текст заметки и выбери ТОЛЬКО ОДНО действие:
                    1. Распредели в базовые категории: {self.categories} (верни только имя).
                    2. Если базовые не подходят, ОБЯЗАТЕЛЬНО создай новую категорию (верни: NEW: имя_папки_на_английском_без_пробелов).
                    
                    ЗАПРЕЩЕНО возвращать INBOX, кроме случаев, когда текст — это полностью нечитаемый мусор.
                    Ответ — строго одно слово.
                    Текст: {snippet}
                    """
                    
                    result = await llm.generate_text(prompt, system_prompt="Ты - сортировщик файлов. Отвечай только одним словом.")
                    result = result.strip().lower()

                    # Определение целевой директории
                    target_dir_name = "00_Inbox"
                    if result in self.categories:
                        target_dir_name = result
                    elif result.startswith("new:"):
                        target_dir_name = result.replace("new:", "").strip()

                    if target_dir_name == "00_Inbox" or target_dir_name == "inbox":
                        report.append(f"⏩ Пропущен: `{file_path.name}` (Неясно)")
                        continue

                    # Создаем папку, если ее нет
                    target_dir_path = VAULT_DIR / target_dir_name
                    target_dir_path.mkdir(parents=True, exist_ok=True)

                    # Физическое перемещение файла
                    target_file_path = target_dir_path / file_path.name
                    shutil.move(str(file_path), str(target_file_path))
                    
                    report.append(f"✅ `{file_path.name}` ➡️ `/{target_dir_name}`")
                    moved_count += 1

                except Exception as e:
                    report.append(f"❌ Ошибка с `{file_path.name}`: {repr(e)}")
                    
            # Модель Hermes выгрузится автоматически блоком finally в Оркестраторе или останется до тайм-аута

        report.append(f"\n**Итого перемещено:** {moved_count} файлов.")
        return "\n".join(report)

clerk = ClerkAgent()