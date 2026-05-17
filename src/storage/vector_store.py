import lancedb
import asyncio
import pyarrow as pa
from pathlib import Path
from typing import List, Dict, Any

class VectorStore:
    def __init__(self, db_path: Path):
        self.db_path = str(db_path)
        self.db = lancedb.connect(self.db_path)
        
        # Строгий контракт данных (Stable Contracts)
        self.schema = pa.schema([
            pa.field("id", pa.string(), nullable=False),
            pa.field("vector", pa.list_(pa.float32(), 768), nullable=False),
            pa.field("text", pa.string(), nullable=False),
            pa.field("metadata", pa.string(), nullable=True)
        ])

    def _get_or_create_table(self, table_name: str):
        """Возвращает таблицу или создает пустую с жесткой схемой."""
        if table_name in self.db.table_names():
            return self.db.open_table(table_name)
        return self.db.create_table(table_name, schema=self.schema)

    async def add_records(self, table_name: str, records: List[Dict[str, Any]]):
        """Атомарный Upsert (mergeInsert) по первичному ключу 'id'."""
        def _upsert():
            table = self._get_or_create_table(table_name)
            
            # Явное приведение типов во избежание багов инференса LanceDB
            pyarrow_table = pa.Table.from_pylist(records, schema=self.schema)
            
            table.merge_insert("id") \
                 .when_matched_update_all() \
                 .when_not_matched_insert_all() \
                 .execute(pyarrow_table)
        
        await asyncio.to_thread(_upsert)

    async def search(self, table_name: str, query_vector: List[float], limit: int = 5) -> List[Dict[str, Any]]:
        """Асинхронный векторный поиск."""
        def _search():
            if table_name not in self.db.table_names():
                return []
            table = self.db.open_table(table_name)
            return table.search(query_vector).limit(limit).to_list()

        return await asyncio.to_thread(_search)