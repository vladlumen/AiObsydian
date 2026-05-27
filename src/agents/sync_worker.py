import os
import hashlib
import logging
from pathlib import Path
from src.core.config import VAULT_DIR
from src.storage.sqlite_manager import SQLiteManager
from src.cognitive.memory.semantic import memory
from src.agents.parsers.md_chunker import MarkdownChunker
from src.infrastructure.logger import agent_logger

class SyncWorker:
    def __init__(self, db_path: str = "state.db"):
        self.db = SQLiteManager(db_path)
        self.vault_path = Path(VAULT_DIR)
        self.chunker = MarkdownChunker()

    def _calculate_md5(self, file_path: Path) -> str:
        """Вычисляет MD5-хэш контента файла для детекции изменений текста."""
        hasher = hashlib.md5()
        try:
            with open(file_path, 'rb') as f:
                buf = f.read(65536)
                while len(buf) > 0:
                    hasher.update(buf)
                    buf = f.read(65536)
                return hasher.hexdigest()
        except Exception as e:
            print(f"[SyncWorker Ошибка] Хэширование файла {file_path.name}: {e}")
            return ""

    async def _sync_file(self, file_path: Path) -> None:
        """Обработка и индексация одного изменившегося файла Obsidian"""
        try:
            content = file_path.read_text(encoding='utf-8', errors='ignore')
            parsed_chunks = self.chunker.parse_file(file_path=str(file_path.resolve()), content=content)
            await memory.update_file_memory(file_path=str(file_path.resolve()), parsed_chunks=parsed_chunks)
        except Exception as e:
            agent_logger.error("SyncWorker", f"❌ Ошибка индексации файла {file_path}: {e}")

    async def sync_vault(self) -> str:
        agent_logger.info("SyncWorker", "Старт инкрементальной синхронизации базы знаний...")
        
        if not self.vault_path.exists():
            return f"❌ Ошибка: Директория Vault {self.vault_path} не найдена."

        current_files = list(self.vault_path.glob("**/*.md"))
        registered_files = self.db.get_all_registered_files()

        added_count = 0
        updated_count = 0
        deleted_count = 0
        current_paths_str = set()

        for file_path in current_files:
            if ".obsidian" in file_path.parts:
                continue

            str_path = str(file_path.resolve())
            current_paths_str.add(str_path)
            
            mtime = file_path.stat().st_mtime
            stored_state = registered_files.get(str_path)

            if not stored_state:
                file_hash = self._calculate_md5(file_path)
                await self._sync_file(file_path)
                self.db.update_file_state(str_path, mtime, file_hash)
                added_count += 1
                agent_logger.info("SyncWorker", f"✅ Новая заметка добавлена в индекс: {file_path.name}")

            else:
                stored_mtime, stored_hash = stored_state
                if mtime != stored_mtime:
                    current_hash = self._calculate_md5(file_path)
                    
                    if current_hash != stored_hash:
                        await self._sync_file(file_path)
                        self.db.update_file_state(str_path, mtime, current_hash)
                        updated_count += 1
                        agent_logger.info("SyncWorker", f"🔄 Обновлены векторы для: {file_path.name}")
                    else:
                        self.db.update_file_state(str_path, mtime, stored_hash)

        for registered_path in registered_files.keys():
            if registered_path not in current_paths_str:
                filename = os.path.basename(registered_path)
                
                if hasattr(memory, 'delete_file_chunks'):
                    await memory.delete_file_chunks(registered_path)
                
                self.db.delete_file_state(registered_path)
                deleted_count += 1
                agent_logger.info("SyncWorker", f"🗑️ Удалена из индекса стертая заметка: {filename}")

        report = f"Синхронизация завершена: +{added_count} новых, ~{updated_count} измененных, -{deleted_count} удаленных."
        return report

sync_worker = SyncWorker()