import os
import tempfile
import re
import json
import uuid
from pathlib import Path
from datetime import datetime
from src.core.config import INBOX_PATH

class ObsidianWriter:
    def __init__(self, inbox_path: Path):
        self.inbox_path = inbox_path
        self.inbox_path.mkdir(parents=True, exist_ok=True)

    def _sanitize_filename(self, filename: str) -> str:
        """Очистка имени файла от запрещенных символов и ограничение длины."""
        # Удаляем спецсимволы и переносы строк (\n, \r)
        clean = re.sub(r'[\\/*?:"<>|\[\]\n\r]', "", filename).strip()
        # Жестко ограничиваем длину имени файла (120 символов)
        clean = clean[:120].strip()
        return clean if clean else f"Idea_{datetime.now().strftime('%Y%m%d_%H%M')}"

    def create_note(self, title: str, content: str, custom_properties: str = "", model_name: str = "hermes3:8b") -> Path:
        """Создает заметку с жестко заданным системным YAML и контентом."""
        clean_title = self._sanitize_filename(title)
        
        # Словарь тегов для моделей
        model_tags = {
            "hermes3:8b": "hermes3-8b",
            "qwen3.5:latest": "qwen35-8b"
        }
        model_tag = model_tags.get(model_name, "unknown-model")

        # Собираем железобетонный YAML Frontmatter
        # Даже если LLM ошибется, структура файла не сломается
        yaml_block = (
            "---\n"
            f"title: \"{clean_title}\"\n"
            f"created: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n"
            "type: inbox\n"
            f"llm_model: \"{model_name}\"\n"
            "ai_generated: true\n"
            "tags:\n"
            "  - status/new\n"
            f"  - {model_tag}\n"
            "  - ai_note\n"
        )
        
        # Если LLM прислала свои свойства, пытаемся их аккуратно добавить
        if custom_properties:
            yaml_block += f"# LLM Properties:\n# {custom_properties}\n"
            
        yaml_block += "---\n\n"

        # Финальный текст
        full_content = yaml_block + content

        # Атомарная запись
        file_path = self.inbox_path / f"{clean_title}.md"
        fd, temp_path = tempfile.mkstemp(dir=self.inbox_path, suffix=".tmp")
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as f:
                f.write(full_content)
            os.replace(temp_path, file_path)
            print(f"[ObsidianWriter] ✅ Заметка создана: {file_path.name}")
            return file_path
        except Exception as e:
            if os.path.exists(temp_path):
                os.remove(temp_path)
            raise e

    def create_canvas(self, title: str, structure: dict) -> Path:
        """Создает JSON Canvas, автоматически высчитывая координаты."""
        clean_title = self._sanitize_filename(title)
        if not clean_title:
            clean_title = f"Canvas_{datetime.now().strftime('%Y%m%d_%H%M')}"

        canvas_nodes = []
        canvas_edges = []

        y_offset = 0
        x_offset = 0

        # Обработка узлов (карточек)
        for node in structure.get("nodes", []):
            node_id = str(node.get("id", uuid.uuid4().hex[:8]))
            text = node.get("text", "")

            canvas_nodes.append({
                "id": node_id,
                "type": "text",
                "text": text,
                "x": x_offset,
                "y": y_offset,
                "width": 400,
                "height": max(120, len(text) // 2)
            })
            y_offset += 250

        # Обработка связей (стрелок)
        for edge in structure.get("edges", []):
            canvas_edges.append({
                "id": uuid.uuid4().hex[:8],
                "fromNode": str(edge.get("from")),
                "fromSide": "bottom",
                "toNode": str(edge.get("to")),
                "toSide": "top"
            })

        canvas_data = {"nodes": canvas_nodes, "edges": canvas_edges}

        file_path = self.inbox_path / f"{clean_title}.canvas"
        fd, temp_path = tempfile.mkstemp(dir=self.inbox_path, suffix=".tmp")

        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as f:
                json.dump(canvas_data, f, indent=4, ensure_ascii=False)
            os.replace(temp_path, file_path)
            print(f"[ObsidianWriter] ✅ Canvas создан: {file_path.name}")
            return file_path
        except Exception as e:
            if os.path.exists(temp_path):
                os.remove(temp_path)
            raise e

writer = ObsidianWriter(INBOX_PATH)