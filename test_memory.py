import asyncio
import sys
from pathlib import Path

# Добавляем корень проекта в пути, чтобы импорты src.* работали корректно
sys.path.append(str(Path(__file__).parent))

from src.cognitive.memory.semantic import memory

async def main():
    print("=== ТЕСТИРОВАНИЕ СЕМАНТИЧЕСКОЙ ПАМЯТИ (LanceDB) ===")
    
    # 1. Текст для запоминания
    note_id = "test_roblox_note"
    content = """
    # Архитектура проектов в Roblox
    При обучении студентов важно делать упор на модульность скриптов.
    Leaderboard (таблица лидеров) должен обновляться асинхронно, чтобы не тормозить сервер.
    Для связи UI (интерфейса) и игровой логики лучше всего использовать паттерн Observer и события (RemoteEvents).
    Обязательно напоминать Эмилю про домашку по этим темам.
    """
    metadata = {
        "source": "test_memory.py", 
        "category": "work",
        "tags": ["roblox", "gamedev", "education"]
    }
    
    print("\n[Шаг 1] Запись текста в векторную базу...")
    await memory.memorize_note(note_id, content, metadata)
    
    # 2. Тестовый поиск по смыслу (а не по точным словам)
    query = "Как правильно обновлять таблицу лидеров и интерфейс?"
    print(f"\n[Шаг 2] Векторный поиск по запросу: '{query}'")
    
    results = await memory.search_relevant_context(query, top_k=2)
    
    print("\n=== НАЙДЕННЫЙ КОНТЕКСТ ===")
    if results:
        print(results)
    else:
        print("❌ Ничего не найдено.")

if __name__ == "__main__":
    asyncio.run(main())