import sys
from pathlib import Path
from typing import List, Dict, Any
from src.storage.vector_store import VectorStore
from src.core import config

class SemanticMemory:
    def __init__(self):
        # Инициализируем техническое хранилище, указывая путь к LanceDB
        db_path = Path(__file__).resolve().parent.parent.parent.parent / "data" / "lancedb_store"
        self.store = VectorStore(db_path)
        self.table_name = "obsidian_notes"
        print("🧠 [SemanticMemory] Высокоуровневая память связана с LanceDB.")

    async def sync_obsidian_vault(self, vault_path: Path):
        """
        Сканирует markdown-файлы в Obsidian Vault,
        генерирует эмбеддинги и делает Upsert в LanceDB.
        """
        print(f"🔄 [SemanticMemory] Сканирование хранилища Obsidian: {vault_path}")
        
        if not vault_path.exists():
            print(f"⚠️ [SemanticMemory] Путь {vault_path} не найден! Синхронизация пропущена.")
            return

        # TODO: Реализовать чтение .md файлов, генерацию векторов (768) и вызов:
        # records = [{"id": ..., "vector": [...], "text": ..., "metadata": ...}]
        # await self.store.add_records(self.table_name, records)
        print("✅ [SemanticMemory] Синхронизация с Obsidian временно в режиме заглушки.")

    async def search(self, query_text: str, top_k: int = 5) -> List[Dict[str, Any]]:
        """Конвертирует текст в вектор и ищет в LanceDB."""
        fake_query_vector = [0.0] * 768 
        # Внутри низкоуровневого store метод принимает limit, так что пробрасываем туда top_k
        return await self.store.search(self.table_name, fake_query_vector, limit=top_k)

    async def memorize_note(self, note_id: str, content: str, metadata: dict = None):
        """Заглушка для запоминания заметки в семантической памяти."""
        print(f"🧠 [SemanticMemory] Запоминание заметки: {note_id}")
        if metadata:
            print(f"   Метаданные: {metadata}")
        # TODO: Реализовать реальное сохранение в LanceDB или другую систему
        # Пример: await self.store.add_record(...)

# Экземпляр для импорта в orchestrator и test_run
memory = SemanticMemory()