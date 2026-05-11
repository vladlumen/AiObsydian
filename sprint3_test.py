import time
import os
from tools.vector_storage import vector_mem
from logger import agent_logger

NOTES_PATH = "/mnt/c/Users/vladislav/Documents/ObsidianVault"
def test_search_speed():
    source = "RAG_Test"
    
    # 1. Индексация
    agent_logger.info(source, "Начало индексации...")
    vector_mem.index_notes(NOTES_PATH)
    
    # 2. Замер скорости поиска
    query = "безопасность записи"
    start_time = time.time()
    results = vector_mem.search(query)
    end_time = time.time()
    
    duration_ms = (end_time - start_time) * 1000
    
    print("\n" + "="*50)
    if results:
        print(f"НАЙДЕНО: {results[0]['filename']}")
        print(f"ВРЕМЯ ПОИСКА: {duration_ms:.2f} ms")
    
    if duration_ms < 200:
        print("DOD SPRINT 3 ПРОЙДЕН: Поиск быстрее 200мс.")
    else:
        print(f"DOD ПРОВАЛЕН: Поиск занял {duration_ms:.2f} мс (лимит 200мс).")
    print("="*50)

if __name__ == "__main__":
    test_search_speed()
