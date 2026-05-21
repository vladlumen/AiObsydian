import uuid
import json
import re
from pathlib import Path
from typing import List, Dict, Any
from src.cognitive.llm_service import llm
from src.storage.vector_store import VectorStore
from src.core.config import DATA_DIR
from src.infrastructure.vram_scheduler import vram_manager

class SemanticMemory:
    def __init__(self):
        self.db_path = DATA_DIR / "lancedb_store"
        self.store = VectorStore(self.db_path)
        self.table_name = "obsidian_notes"
        self.chunk_size = 400

    def _clean_text(self, text: str) -> str:
        """Безопасно отрезает фронтматтер Obsidian без риска сожрать статью целиком."""
        lines = text.splitlines()
        if lines and lines[0].strip() == "---":
            end_index = -1
            for i in range(1, len(lines)):
                if lines[i].strip() == "---":
                    end_index = i
                    break
            if end_index != -1:
                lines = lines[end_index+1:]
        
        cleaned_text = "\n".join(lines)
        # Убираем только квадратные скобки ссылок, оставляя текст
        cleaned_text = re.sub(r'\[\[(.*?)\]\]', r'\1', cleaned_text)
        return cleaned_text.strip()

    def _chunk_text(self, text: str, note_id: str, folder: str) -> List[str]:
        cleaned = self._clean_text(text)
        words = cleaned.split()
        chunks = []
        overlap = 30
        
        # Если текст совсем короткий, создаем хотя бы один чанк
        if len(words) <= self.chunk_size:
            chunks.append(cleaned)
        else:
            for i in range(0, len(words), self.chunk_size - overlap):
                chunk = " ".join(words[i:i + self.chunk_size])
                if chunk.strip():
                    chunks.append(chunk)
        
        # Инъекция контекста: внедряем метаданные прямо в текст чанка для nomic-embed
        contextual_chunks = []
        for c in chunks:
            prefix = f"Документ: {note_id}. Категория: {folder}.\nКонтент:\n"
            contextual_chunks.append(prefix + c)
            
        return contextual_chunks

    async def memorize_note(self, note_id: str, content: str, metadata: Dict[str, Any] = None):
        if not metadata: metadata = {}
        folder = metadata.get("folder", "00_Inbox")
        chunks = self._chunk_text(content, note_id, folder)
        records = []

        async with vram_manager.inference_lock:
            await vram_manager.request_model("nomic-embed-text")
            try:
                for i, chunk in enumerate(chunks):
                    vector = await llm.get_embedding(chunk)
                    records.append({
                        "id": f"{note_id}_chunk_{i}_{uuid.uuid4().hex[:4]}",
                        "vector": vector,
                        "text": chunk,
                        "metadata": json.dumps(metadata)
                    })
            finally:
                await vram_manager.unload_model("nomic-embed-text")

        if records:
            await self.store.add_records(self.table_name, records)

    async def sync_obsidian_vault(self, vault_path: Path):
        print(f"[Memory] 🔄 Полное сканирование: {vault_path}")
        if not vault_path.exists(): return

        md_files = list(vault_path.glob("**/*.md"))
        print(f"[Memory] 📂 Найдено файлов для проверки: {len(md_files)}")

        try:
            if hasattr(self.store, 'db') and self.table_name in self.store.db.table_names():
                self.store.db.drop_table(self.table_name)
                print(f"[Memory] 🗑️ Старая таблица {self.table_name} удалена.")
        except Exception as e:
            print(f"[Memory] ⚠️ Не удалось сбросить таблицу: {e}")

        async with vram_manager.inference_lock:
            await vram_manager.request_model("nomic-embed-text")
            try:
                for file_path in md_files:
                    note_id = file_path.stem
                    try:
                        with open(file_path, "r", encoding="utf-8") as f:
                            content = f.read().strip()
                    except: continue

                    if not content: continue

                    relative_folder = file_path.parent.relative_to(vault_path)
                    chunks = self._chunk_text(content, note_id, str(relative_folder))
                    records = []
                    
                    metadata = {
                        "source": "Obsidian_Sync",
                        "title": note_id,
                        "folder": str(relative_folder),
                        "file_name": file_path.name
                    }

                    for i, chunk in enumerate(chunks):
                        vector = await llm.get_embedding(chunk)
                        records.append({
                            "id": f"{note_id}_chunk_{i}_{uuid.uuid4().hex[:4]}",
                            "vector": vector,
                            "text": chunk,
                            "metadata": json.dumps(metadata)
                        })

                    if records:
                        await self.store.add_records(self.table_name, records)
                        print(f"[Memory] 📥 Проиндексирован: [{relative_folder}]/{file_path.name}")
            finally:
                await vram_manager.unload_model("nomic-embed-text")
        print("[Memory] ✅ Чистая синхронизация завершена.")

    async def search_relevant_context(self, query: str, top_k: int = 5) -> str:
        async with vram_manager.inference_lock:
            await vram_manager.request_model("nomic-embed-text")
            try:
                query_vector = await llm.get_embedding(query)
            finally:
                await vram_manager.unload_model("nomic-embed-text")

        results = await self.store.search(self.table_name, query_vector, limit=top_k)
        if not results: return ""

        context_parts = []
        for i, res in enumerate(results, 1):
            meta_str = res.get("metadata", "{}")
            try: meta = json.loads(meta_str)
            except: meta = {}
                
            source = meta.get("source", "Unknown")
            folder = meta.get("folder", "")
            title = meta.get("title", "Без названия")
            
            context_parts.append(f"--- Фрагмент {i} (Файл: [[{title}]], Папка: {folder}, Источник: {source}) ---\n{res['text']}\n")

        return "\n".join(context_parts)

memory = SemanticMemory()