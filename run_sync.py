import asyncio
import sys
from pathlib import Path

# Гарантируем правильное разрешение путей внутри WSL2
sys.path.append(str(Path(__file__).parent))

from src.agents.sync_worker import sync_worker

async def main():
    print("\n" + "="*50)
    print("🔄 [OBSIDIAN RAG SYNC] Старт фоновой индексации...")
    print("="*50)
    
    try:
        # Запуск воркера инкрементального считывания
        report = await sync_worker.sync_vault()
        
        print("\n" + "="*50)
        print(f"🎉 {report}")
        print("="*50 + "\n")
        
    except Exception as e:
        print(f"\n❌ Критическая ошибка во время синхронизации: {repr(e)}\n")

if __name__ == "__main__":
    asyncio.run(main())