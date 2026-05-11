import os
import time
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from tools.vector_storage import vector_mem
from logger import agent_logger

class NotesHandler(FileSystemEventHandler):
    def on_modified(self, event):
        if not event.is_directory and event.src_path.endswith(".md"):
            agent_logger.info("SyncWorker", f"Файл изменен: {event.src_path}. Переиндексация...")
            # В реальном проекте лучше обновлять только один файл, 
            # но для начала обновим всё для простоты.
            vector_mem.index_notes(os.path.expanduser("~/notes"))

def start_sync(path):
    event_handler = NotesHandler()
    observer = Observer()
    observer.schedule(event_handler, path, recursive=True)
    observer.start()
    agent_logger.info("SyncWorker", f"Мониторинг папки {path} запущен.")
    return observer
