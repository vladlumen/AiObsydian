import os
from tools.vector_storage import vector_mem
from src.infrastructure import logger

class Deduplicator:
    THRESHOLD = 0.8  # Порог семантической схожести

    @staticmethod
    def find_duplicate(title: str, content: str, notes_path: str):
        # Этап 1: Title Match (Прямое совпадение имени файла)
        file_path = os.path.join(notes_path, f"{title}.md")
        if os.path.exists(file_path):
            return "EXACT_TITLE", file_path

        # Этап 2: Semantic Match (Поиск через LanceDB)
        results = vector_mem.search(content, limit=1)
        if results:
            score = results[0].get('_distance', 1.0) # В LanceDB это L2 distance
            # Переводим в подобие уверенности (упрощенно)
            if score < 0.4:  # Чем меньше дистанция, тем выше схожесть
                return "SEMANTIC_MATCH", results[0]['path']

        return None, None
