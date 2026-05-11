import lancedb
import os
import pandas as pd
from sentence_transformers import SentenceTransformer
from logger import agent_logger

DB_PATH = ".lancedb"
TABLE_NAME = "obsidian_notes"

class VectorMemory:
    def __init__(self, model_name='BAAI/bge-m3'):
        # Соединяемся с базой в папке проекта
        self.db = lancedb.connect(DB_PATH)
        # Загружаем модель (она скачается один раз и будет работать локально)
        self.model = SentenceTransformer(model_name)
        self.table = None
        self._init_table()

    def _init_table(self):
        """Открывает существующую таблицу."""
        if TABLE_NAME in self.db.table_names():
            self.table = self.db.open_table(TABLE_NAME)
        else:
            # Если таблицы нет, она создастся при первой синхронизации
            pass

    def index_notes(self, notes_dir: str):
        """Индексация всех .md файлов."""
        data = []
        for root, _, files in os.walk(notes_dir):
            for file in files:
                if file.endswith(".md"):
                    path = os.path.join(root, file)
                    try:
                        with open(path, 'r', encoding='utf-8') as f:
                            text = f.read()
                            if not text.strip(): continue
                            
                            vector = self.model.encode(text).tolist()
                            data.append({
                                "vector": vector,
                                "text": text,
                                "path": path,
                                "filename": file
                            })
                    except Exception as e:
                        agent_logger.error("VectorMemory", f"Ошибка чтения {file}: {e}")

        if data:
            self.table = self.db.create_table(TABLE_NAME, data=data, mode="overwrite")
            agent_logger.info("VectorMemory", f"Индексация завершена. Файлов: {len(data)}")

    def search(self, query: str, limit: int = 3):
        """Поиск похожих заметок."""
        if self.table is None:
            # Пытаемся открыть таблицу, если она уже создана синхронизатором
            if TABLE_NAME in self.db.table_names():
                self.table = self.db.open_table(TABLE_NAME)
            else:
                return []
        
        query_vector = self.model.encode(query).tolist()
        results = self.table.search(query_vector).limit(limit).to_pandas()
        return results.to_dict('records')

vector_mem = VectorMemory()
