import os
import json
import asyncio
import lancedb
import pyarrow as pa
from typing import List, Dict, Any, Optional, Union
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
        
        # Единое SQL-условие для жесткой фильтрации технического мусора, инбокса и тестов
        self.exclude_condition = (
            "NOT ("
            "file_path LIKE '%Test%' OR "
            "file_path LIKE '%test_%' OR "
            "file_path LIKE '%tests/%' OR "
            "file_path LIKE '%Template%' OR "
            "file_path LIKE '%00_Inbox%'"
            ")"
        )

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
            if not vectors[i]:
                agent_logger.warning(
                    "VectorStore",
                    f"Пропущен чанк без эмбеддинга: {chunk.get('id', i)}",
                )
                continue
            metadata_str = json.dumps(chunk["metadata"], ensure_ascii=False)
            prepared_data.append({
                "id": chunk["id"],
                "file_path": chunk["file_path"],
                "text": chunk["text"],
                "vector": vectors[i],
                "metadata": metadata_str
            })

        if not prepared_data:
            agent_logger.error("VectorStore", "Ни один чанк не получил эмбеддинг (проверьте Ollama nomic-embed-text).")
            return

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

    def _rows_to_dicts(self, raw: Any) -> List[Dict[str, Any]]:
        """LanceDB может вернуть list[dict], PyArrow Table или columnar pydict."""
        if raw is None:
            return []
        if isinstance(raw, list):
            return [r for r in raw if isinstance(r, dict)]
        if hasattr(raw, "to_pylist"):
            return [r for r in raw.to_pylist() if isinstance(r, dict)]
        if hasattr(raw, "to_pydict"):
            columnar = raw.to_pydict()
            if not columnar:
                return []
            length = len(next(iter(columnar.values())))
            return [
                {col: columnar[col][i] for col in columnar}
                for i in range(length)
            ]
        return []

    def _parse_metadata_field(self, meta: Any) -> Dict[str, Any]:
        if isinstance(meta, dict):
            return meta
        if isinstance(meta, str) and meta.strip():
            try:
                return json.loads(meta)
            except json.JSONDecodeError:
                return {}
        return {}

    def _normalize_hit(self, doc: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Единый контракт для RAG: text и header_path всегда на верхнем уровне."""
        meta = self._parse_metadata_field(doc.get("metadata"))

        text = doc.get("text")
        if text is None:
            text = meta.get("text", "")
        text = str(text).strip() if text is not None else ""
        if not text:
            return None

        header_path = doc.get("header_path") or meta.get("header_path", "")

        return {
            "id": doc.get("id"),
            "file_path": doc.get("file_path") or meta.get("file_name", "Unknown"),
            "text": text,
            "header_path": header_path,
            "score": doc.get("_score") or doc.get("_distance") or doc.get("score"),
            "metadata": meta,
        }

    def _normalize_search_results(self, raw: Any) -> List[Dict[str, Any]]:
        normalized: List[Dict[str, Any]] = []
        for doc in self._rows_to_dicts(raw):
            hit = self._normalize_hit(doc)
            if hit:
                normalized.append(hit)
        return normalized

    async def search(self, query_vector: list, limit: int = 5) -> List[Dict[str, Any]]:
        # Добавлен .where() для фильтрации фолбэк/базового поиска
        arrow = (
            self.table.search(query_vector)
            .where(self.exclude_condition)
            .limit(limit)
            .to_arrow()
        )
        return self._normalize_search_results(arrow)

    async def _vector_search_raw(self, query_vector: List[float], limit: int) -> Any:
        # Добавлен .where() во внутренний сырой метод для консистентности результатов
        return (
            self.table.search(query_vector)
            .where(self.exclude_condition)
            .limit(limit)
            .to_arrow()
        )

    async def search_hybrid(self, query_text: str, query_vector: List[float], limit: int = 5) -> List[Dict[str, Any]]:
        """
        Гибридный поиск (вектор + BM25). Результат всегда List[dict] с полем text.
        """
        formatted: List[Dict[str, Any]] = []

        try:
            from lancedb.rerankers import LinearCombinationReranker

            reranker = LinearCombinationReranker(weight=0.3)
            query = (
                self.table.search(query_type="hybrid")
                .vector(query_vector)
                .text(query_text)
                .where(self.exclude_condition) # Применение расширенной SQL-фильтрации путей
                .rerank(reranker=reranker)
                .limit(limit)
            )
            raw = query.to_arrow()
            formatted = self._normalize_search_results(raw)
            if formatted:
                agent_logger.info("VectorStore", f"Гибридный поиск: {len(formatted)} чанков.")
                return formatted
        except Exception as e:
            agent_logger.error("VectorStore", f"Ошибка гибридного поиска: {e}")

        try:
            raw = await self._vector_search_raw(query_vector, limit)
            formatted = self._normalize_search_results(raw)
            if formatted:
                agent_logger.info(
                    "VectorStore",
                    f"Fallback векторный поиск: {len(formatted)} чанков.",
                )
            return formatted
        except Exception as backup_error:
            agent_logger.error("VectorStore", f"Критическая ошибка поиска: {backup_error}")
            return []