import os
import hashlib
import logging  # Перешли на стандартный логгер
from pathlib import Path
from src.core.config import VAULT_DIR
from src.storage.sqlite_manager import SQLiteManager
from src.cognitive.memory.semantic import memory

class SyncWorker:
    def __init__(self, db_path: str = "state.db"):
        self.db = SQLiteManager(db_path)
        self.vault_path = Path(VAULT_DIR)

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

    async def sync_vault(self) -> str:
        print("[SyncWorker] Старт инкрементальной синхронизации базы знаний...")
        
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
                content = file_path.read_text(encoding='utf-8', errors='ignore')
                
                await memory.memorize_note(
                    note_id=file_path.name,
                    content=content,
                    metadata={"source": "SyncWorker_New", "title": file_path.stem}
                )
                
                self.db.update_file_state(str_path, mtime, file_hash)
                added_count += 1
                print(f"[SyncWorker] ✅ Новая заметка добавлена в индекс: {file_path.name}")

            else:
                stored_mtime, stored_hash = stored_state
                if mtime != stored_mtime:
                    current_hash = self._calculate_md5(file_path)
                    
                    if current_hash != stored_hash:
                        content = file_path.read_text(encoding='utf-8', errors='ignore')
                        
                        await memory.memorize_note(
                            note_id=file_path.name,
                            content=content,
                            metadata={"source": "SyncWorker_Update", "title": file_path.stem}
                        )
                        
                        self.db.update_file_state(str_path, mtime, current_hash)
                        updated_count += 1
                        print(f"[SyncWorker] 🔄 Обновлены векторы для: {file_path.name}")
                    else:
                        self.db.update_file_state(str_path, mtime, stored_hash)

        for registered_path in registered_files.keys():
            if registered_path not in current_paths_str:
                filename = os.path.basename(registered_path)
                
                if hasattr(memory, 'delete_note'):
                    await memory.delete_note(filename)
                
                self.db.delete_file_state(registered_path)
                deleted_count += 1
                print(f"[SyncWorker] 🗑️ Удалена из индекса стертая заметка: {filename}")

        report = f"Синхронизация завершена: +{added_count} новых, ~{updated_count} измененных, -{deleted_count} удаленных."
        return report

sync_worker = SyncWorker()