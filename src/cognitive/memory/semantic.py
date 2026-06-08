from pathlib import Path
from typing import List, Dict, Any, Optional

from src.storage.vector_store import VectorStore
from src.cognitive.llm_service import llm
from src.core.config import LANCEDB_DIR
from src.infrastructure.logger import agent_logger
from src.agents.parsers.md_chunker import MarkdownChunker
# CacheManager здесь больше не нужен для генерации заметок

class SemanticMemory:
    def __init__(self):
        self.store = VectorStore(db_dir=str(LANCEDB_DIR))
        self.table_name = "semantic_memory"
        self._chunker = MarkdownChunker()
        print("🧠 [SemanticMemory] Высокоуровневая память связана с LanceDB.")

    async def sync_obsidian_vault(self, vault_path: Path):
        """Полная инкрементальная синхронизация Vault → LanceDB + SQLite реестр."""
        print(f"🔄 [SemanticMemory] Сканирование хранилища Obsidian: {vault_path}")
        if not vault_path.exists():
            print(f"⚠️ [SemanticMemory] Путь {vault_path} не найден! Синхронизация пропущена.")
            return

        from src.agents.sync_worker import sync_worker
        report = await sync_worker.sync_vault()
        print(f"✅ [SemanticMemory] {report}")

    async def index_file(self, file_path: Path) -> None:
        """Индексирует один .md файл в LanceDB (после записи в Obsidian)."""
        if not file_path.exists():
            agent_logger.error("SemanticMemory", f"Файл для индексации не найден: {file_path}")
            return

        content = file_path.read_text(encoding="utf-8", errors="ignore")
        parsed_chunks = self._chunker.parse_file(
            file_path=str(file_path.resolve()),
            content=content,
        )
        await self.update_file_memory(
            file_path=str(file_path.resolve()),
            parsed_chunks=parsed_chunks,
        )
        agent_logger.info("SemanticMemory", f"Проиндексировано чанков: {len(parsed_chunks)} ({file_path.name})")

    async def search(self, query_text: str, top_k: int = 5) -> List[Dict[str, Any]]:
        return await self.retrieve_context(query_text, limit=top_k)

    async def search_relevant_context(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        return await self.retrieve_context(query, limit=top_k)

    async def memorize_note(self, note_id: str, content: str, metadata: dict = None):
        parsed_chunks = self._chunker.parse_file(file_path=note_id, content=content)
        if metadata:
            for chunk in parsed_chunks:
                chunk["metadata"].update(metadata)
        await self.update_file_memory(file_path=note_id, parsed_chunks=parsed_chunks)
        agent_logger.info("SemanticMemory", f"Запомнена заметка: {note_id} ({len(parsed_chunks)} чанков)")

    async def update_file_memory(self, file_path: str, parsed_chunks: List[Dict[str, Any]]) -> None:
        if not parsed_chunks:
            agent_logger.warning("SemanticMemory", f"Нет чанков для индексации: {file_path}")
            return
        await self.store.delete_chunks_by_file(file_path)
        await self.store.embed_and_save_chunks(parsed_chunks, llm)

    async def delete_file_chunks(self, file_path: str) -> None:
        await self.store.delete_chunks_by_file(file_path)

    async def _get_embedding(self, text: str) -> list[float]:
        try:
            return await llm.get_embedding(text)
        except Exception as e:
            agent_logger.error("SemanticMemory", f"Ollama Embedding ❌ Ошибка: {e}")
            return []

    def _clean_text_from_instructions(self, text: str) -> str:
        """Отрезает хвост инструкций, оставляя чистый контент для RAG поиска связей."""
        if "Инструкция по обработке:" in text:
            parts = text.split("Инструкция по обработке:")
            cleaned = parts[0].strip()
            return cleaned if cleaned else text
        return text

    async def retrieve_context(self, query: str, limit: int = 3) -> List[Dict[str, Any]]:
        # ЗАЩИТА RAG: Поиск связей идет строго по контенту поста, без команд middleware
        cleaned_query = self._clean_text_from_instructions(query)
        
        query_vector = await self._get_embedding(cleaned_query)
        if not query_vector:
            return []
        chunks = await self.store.search_hybrid(
            query_text=cleaned_query,
            query_vector=query_vector,
            limit=limit,
        )
        return chunks

    async def get_cached_response(self, query: str) -> Optional[str]:
        """L1/L2 кэш ответов RAG — делегирует в CacheManager."""
        from src.infrastructure.cache_manager import cache_manager
        return await cache_manager.get_cached_response(query)

    async def save_to_cache(self, query: str, response: str) -> None:
        """Сохранение ответа RAG в L1/L2 — делегирует в CacheManager."""
        from src.infrastructure.cache_manager import cache_manager
        await cache_manager.save_to_cache(query, response)

memory = SemanticMemory()