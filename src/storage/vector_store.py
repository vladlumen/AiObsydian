import os
import json
import asyncio
import lancedb
import pyarrow as pa
from typing import List, Dict, Any, Optional
from src.infrastructure.logger import agent_logger
from src.core.config import LANCEDB_DIR


class VectorStore:
    """
    Класс управления векторным хранилищем LanceDB.
    Поддерживает иерархическое обновление данных по путям файлов.
    """
    def __init__(self, db_dir: str = str(LANCEDB_DIR)):
        self.db_dir = db_dir
        os.makedirs(self.db_dir, exist_ok=True)
        self.db = lancedb.connect(self.db_dir)
        self.table_name = "semantic_memory"
        self.table = self._get_or_create_table()

    def _get_or_create_table(self):
        if self.table_name in self.db.table_names():
            return self.db.open_table(self.table_name)
        
        schema = pa.schema([
            pa.field("id", pa.string()),
            pa.field("file_path", pa.string()),
            pa.field("text", pa.string()),
            pa.field("vector", pa.list_(pa.float32(), 768)),
            pa.field("metadata", pa.string())
        ])
        return self.db.create_table(self.table_name, schema=schema)

    async def delete_chunks_by_file(self, file_path: str) -> None:
        return self._delete_chunks_sync(file_path)

    def _delete_chunks_sync(self, file_path: str) -> None:
        try:
            escaped_path = file_path.replace("'", "''")
            self.table.delete(f"file_path = '{escaped_path}'")
            agent_logger.info("VectorStore", f"Успешно удалены старые чанки для файла: {file_path}")
        except Exception as e:
            agent_logger.error("VectorStore", f"Не удалось очистить чанки для {file_path}: {e}")

    async def embed_and_save_chunks(self, chunks: List[Dict[str, Any]], embedding_service) -> None:
        if not chunks:
            return

        vectors = []
        for chunk in chunks:
            vector = await embedding_service.get_embedding(chunk["text"])
            vectors.append(vector)

        prepared_data = []
        for i, chunk in enumerate(chunks):
            metadata_str = json.dumps(chunk["metadata"], ensure_ascii=False)
            prepared_data.append({
                "id": chunk["id"],
                "file_path": chunk["file_path"],
                "text": chunk["text"],
                "vector": vectors[i],
                "metadata": metadata_str
            })

        try:
            self.table.add(prepared_data)
            self.table.create_fts_index("text", replace=True)
            agent_logger.info("VectorStore", f"Чанки успешно добавлены. FTS-индекс перестроен.")
        except Exception as e:
            agent_logger.error("VectorStore", f"Ошибка записи или индексации FTS: {e}")

    async def save_chunks(self, chunks: List[Dict[str, Any]]) -> None:
        return self._save_chunks_sync(chunks)

    def _save_chunks_sync(self, chunks: List[Dict[str, Any]]) -> None:
        if not chunks:
            return
        prepared_data = []
        for chunk in chunks:
            metadata_str = json.dumps(chunk["metadata"], ensure_ascii=False)
            prepared_data.append({
                "id": chunk["id"],
                "file_path": chunk["file_path"],
                "text": chunk["text"],
                "vector": chunk["vector"],
                "metadata": metadata_str
            })
        try:
            self.table.add(prepared_data)
            agent_logger.info("VectorStore", f"Успешно записано чанков: {len(prepared_data)}")
        except Exception as e:
            agent_logger.error("VectorStore", f"Ошибка записи: {e}")

    async def search(self, query_vector: list, limit: int = 5) -> List[Dict[str, Any]]:
        return self.table.search(query_vector).limit(limit).to_arrow().to_pylist()

    async def search_hybrid(self, query_text: str, query_vector: List[float], limit: int = 5) -> List[Dict[str, Any]]:
        """
        Выполняет гибридный поиск (Векторы + BM25) с применением линейного реранкинга.
        """
        try:
            from lancedb.rerankers import LinearCombinationReranker
            
            reranker = LinearCombinationReranker(weight=0.3)

            results = (
                self.table.search(query_type="hybrid")
                .vector(query_vector)
                .text(query_text)
                .rerank(reranker=reranker)
                .limit(limit)
                .to_list()
            )
            
            formatted_results = []
            for doc in results:
                formatted_results.append({
                    "id": doc.get("id"),
                    "file_path": doc.get("file_path"),
                    "text": doc.get("text"),
                    "score": doc.get("_score"),
                    "metadata": json.loads(doc.get("metadata", "{}"))
                })
                
            return formatted_results

        except Exception as e:
            agent_logger.error("VectorStore", f"Ошибка гибридного поиска: {e}")
            try:
                results = self.table.search(query_vector).limit(limit).to_list()
                return [{
                    "id": d.get("id"),
                    "file_path": d.get("file_path"),
                    "text": d.get("text"),
                    "score": d.get("_distance"),
                    "metadata": json.loads(d.get("metadata", "{}"))
                } for d in results]
            except Exception as backup_error:
                agent_logger.error("VectorStore", f"Критическая ошибка: {backup_error}")
                return []