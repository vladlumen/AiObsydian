import uuid
import json
from typing import List, Dict, Any
from src.cognitive.llm_service import llm
from src.storage.vector_store import VectorStore
from src.core.config import DATA_DIR
from src.infrastructure.vram_scheduler import vram_manager

class SemanticMemory:
    def __init__(self):
        # База данных будет храниться в папке data в Linux
        self.db_path = DATA_DIR / "lancedb_store"
        self.store = VectorStore(self.db_path)
        self.table_name = "obsidian_notes"
        self.chunk_size = 500 # Оптимальный размер куска текста для поиска

    def _chunk_text(self, text: str) -> List[str]:
        """Разбивает большой текст на куски (чанки) с небольшим нахлестом."""
        words = text.split()
        chunks = []
        overlap = 50 # Нахлест в словах, чтобы не терять контекст на стыках
        
        for i in range(0, len(words), self.chunk_size - overlap):
            chunk = " ".join(words[i:i + self.chunk_size])
            chunks.append(chunk)
            
        return chunks

    async def memorize_note(self, note_id: str, content: str, metadata: Dict[str, Any] = None):
        """Сохраняет заметку в векторную базу."""
        if not metadata:
            metadata = {}
            
        chunks = self._chunk_text(content)
        records = []

        # Блокируем VRAM для работы с эмбеддинг-моделью
        async with vram_manager.inference_lock:
            await vram_manager.request_model("nomic-embed-text")
            
            try:
                for i, chunk in enumerate(chunks):
                    # Получаем вектор
                    vector = await llm.get_embedding(chunk)
                    
                    # Формируем запись для LanceDB
                    records.append({
                        "id": f"{note_id}_chunk_{i}",
                        "vector": vector,
                        "text": chunk,
                        "metadata": json.dumps(metadata) # Сериализуем в JSON-строку
                    })
            finally:
                # Обязательно выгружаем модель после работы
                await vram_manager.unload_model("nomic-embed-text")

        # Асинхронно пишем в БД
        if records:
            await self.store.add_records(self.table_name, records)
            print(f"[Memory] 🧠 Запомнил заметку '{note_id}' (чанков: {len(chunks)})")

    async def search_relevant_context(self, query: str, top_k: int = 3) -> str:
        """Ищет релевантные куски текста по запросу пользователя."""
        print(f"[Memory] 🔍 Ищу в базе по запросу: '{query}'")
        
        async with vram_manager.inference_lock:
            await vram_manager.request_model("nomic-embed-text")
            try:
                query_vector = await llm.get_embedding(query)
            finally:
                await vram_manager.unload_model("nomic-embed-text")

        results = await self.store.search(self.table_name, query_vector, limit=top_k)
        
        if not results:
            return ""

        # Собираем найденные тексты в одну строку контекста
        context_parts = []
        for i, res in enumerate(results, 1):
            # Десериализуем метаданные обратно в словарь
            meta_str = res.get("metadata", "{}")
            try:
                meta = json.loads(meta_str)
            except Exception:
                meta = {}
                
            source = meta.get("source", "Unknown")
            context_parts.append(f"--- Фрагмент {i} (Из: {source}) ---\n{res['text']}\n")

        return "\n".join(context_parts)

# Экземпляр для импорта
memory = SemanticMemory()