import sys
import asyncio
from pathlib import Path
from typing import List, Dict, Any
from src.storage.vector_store import VectorStore
from src.cognitive.llm_service import llm
from src.core.config import LANCEDB_DIR
from src.infrastructure.logger import agent_logger

class SemanticMemory:
    def __init__(self):
        self.store = VectorStore(db_dir=str(LANCEDB_DIR))
        self.table_name = "obsidian_notes"
        print("🧠 [SemanticMemory] Высокоуровневая память связана с LanceDB.")

    async def sync_obsidian_vault(self, vault_path: Path):
        print(f"🔄 [SemanticMemory] Сканирование хранилища Obsidian: {vault_path}")
        if not vault_path.exists():
            print(f"⚠️ [SemanticMemory] Путь {vault_path} не найден! Синхронизация пропущена.")
            return
        print("✅ [SemanticMemory] Синхронизация с Obsidian временно в режиме заглушки.")

    async def search(self, query_text: str, top_k: int = 5) -> List[Dict[str, Any]]:
        return []

    async def memorize_note(self, note_id: str, content: str, metadata: dict = None):
        print(f"🧠 [SemanticMemory] Запоминание заметки: {note_id}")
        if metadata:
            print(f"   Метаданные: {metadata}")

    async def update_file_memory(self, file_path: str, parsed_chunks: List[Dict[str, Any]]) -> None:
        await self.store.delete_chunks_by_file(file_path)
        await self.store.embed_and_save_chunks(parsed_chunks, llm)

    async def delete_file_chunks(self, file_path: str) -> None:
        await self.store.delete_chunks_by_file(file_path)

    async def _get_embedding(self, text: str) -> list[float]:
        try:
            return await llm.get_embedding(text)
        except Exception as e:
            agent_logger.error("SemanticMemory", f"Ollama Embedding ❌ Ошибка: Не удалось получить вектор для текста: {e}")
            return []

    async def retrieve_context(self, query: str, limit: int = 3) -> List[Dict[str, Any]]:
        query_vector = await self._get_embedding(query)
        if not query_vector:
            return []
        chunks = await self.store.search_hybrid(
            query_text=query,
            query_vector=query_vector,
            limit=limit
        )
        return chunks

memory = SemanticMemory()