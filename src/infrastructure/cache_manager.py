import sqlite3
import hashlib
import lancedb
import pandas as pd
import numpy as np
from pathlib import Path
from typing import Optional, Callable, Any
from src.core.config import LANCEDB_DIR
from src.infrastructure.logger import agent_logger

class CacheManager:
    def __init__(self, embedding_func: Optional[Callable[[str], Any]] = None):
        """
        L1: SQLite (Exact Match)
        L2: LanceDB (Semantic Match)
        """
        self.embedding_func = embedding_func
        self.db_path = str(LANCEDB_DIR)
        self.sqlite_path = f"{self.db_path}/cache_l1.db"
        self.l2_table_name = "cache_l1_l2"
        
        Path(self.db_path).mkdir(parents=True, exist_ok=True)
        self._init_l1()
        self._init_l2()
        
        agent_logger.info("CacheManager", "L1 (SQLite) and L2 (LanceDB) caches initialized successfully.")

    def _init_l1(self):
        try:
            conn = sqlite3.connect(self.sqlite_path)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS cache_l1 (
                    query_hash TEXT PRIMARY KEY,
                    query_text TEXT,
                    response TEXT
                )
            """)
            conn.commit()
            conn.close()
        except Exception as e:
            agent_logger.error("CacheManager", f"L1 Init Error: {e}")

    def _init_l2(self):
        try:
            self.db = lancedb.connect(self.db_path)
        except Exception as e:
            agent_logger.error("CacheManager", f"L2 Init Error: {e}")

    def _clean_query(self, text: str) -> str:
        """Очищает текст от управляющих хвостов middleware для изоляции логики кэша."""
        if "Инструкция по обработке:" in text:
            parts = text.split("Инструкция по обработке:")
            cleaned = parts[0].strip()
            return cleaned if cleaned else text
        return text

    def _get_hash(self, text: str) -> str:
        cleaned_text = self._clean_query(text)
        return hashlib.sha256(cleaned_text.encode()).hexdigest()

    async def get_cached_response(self, query: str) -> Optional[str]:
        """Поиск ответа: сначала L1 (строгое совпадение), затем L2 (семантика)."""
        # Чистим запрос перед вычислением хэша и эмбеддинга
        cleaned_query = self._clean_query(query)
        query_hash = self._get_hash(cleaned_query)
        
        # --- 1. Проверка L1 (SQLite) ---
        try:
            conn = sqlite3.connect(self.sqlite_path)
            cursor = conn.execute("SELECT response FROM cache_l1 WHERE query_hash = ?", (query_hash,))
            row = cursor.fetchone()
            conn.close()
            if row:
                agent_logger.info("CacheManager", f"L1 Hit (Exact)! Входящий хэш совпал.")
                return row[0]
        except Exception as e:
            agent_logger.error("CacheManager", f"L1 Error: {e}")

        # --- 2. Проверка L2 (LanceDB) ---
        if not self.embedding_func:
            return None

        try:
            if self.l2_table_name not in self.db.table_names():
                return None

            # Эмбеддинг берется только от контентной части
            query_vector = await self.embedding_func(cleaned_query)
            if not query_vector:
                return None

            table = self.db.open_table(self.l2_table_name)
            results = table.search(query_vector).limit(1).to_pandas()
            
            if not results.empty:
                distance = results.iloc[0].get('_distance', 1.0)
                if distance < 0.15:  # Жесткий порог точности > 95% сходства
                    agent_logger.info(f"CacheManager", f"L2 Hit (Semantic)! Дистанция: {distance:.4f}")
                    return results.iloc[0]['response']
                else:
                    agent_logger.info(f"CacheManager", f"L2 Miss. Ближайший vector слишком далеко (дистанция: {distance:.4f})")
        except Exception as e:
            agent_logger.error("CacheManager", f"L2 Search Error: {e}")
            
        return None

    async def save_to_cache(self, query: str, response: str) -> None:
        """Сохранение ответа в L1 и L2."""
        cleaned_query = self._clean_query(query)
        query_hash = self._get_hash(cleaned_query)
        
        # --- Сохранение в L1 (SQLite) ---
        try:
            conn = sqlite3.connect(self.sqlite_path)
            conn.execute(
                "INSERT OR REPLACE INTO cache_l1 (query_hash, query_text, response) VALUES (?, ?, ?)",
                (query_hash, cleaned_query, response)
            )
            conn.commit()
            conn.close()
        except Exception as e:
            agent_logger.error("CacheManager", f"L1 Save Error: {e}")

        # --- Сохранение в L2 (LanceDB) ---
        if self.embedding_func:
            try:
                query_vector = await self.embedding_func(cleaned_query)
                if query_vector:
                    new_data = pd.DataFrame([{
                        "vector": query_vector,
                        "query_text": cleaned_query,
                        "response": response
                    }])
                    
                    if self.l2_table_name not in self.db.table_names():
                        self.db.create_table(self.l2_table_name, data=new_data)
                    else:
                        table = self.db.open_table(self.l2_table_name)
                        table.add(new_data)
            except Exception as e:
                agent_logger.error("CacheManager", f"L2 Save Error: {e}")


# Инициализируем синглтон
from src.cognitive.llm_service import llm
cache_manager = CacheManager(embedding_func=llm.get_embedding)