import os
from tools.fs_tools import atomic_write, NoteValidator, NoteValidationError
from tools.reliability import retry_on_failure
from logger import agent_logger

NOTES_PATH = os.path.expanduser("~/notes/")

@retry_on_failure(max_retries=3)
def create_obsidian_note(filename: str, title: str, content: str, tags: list):
    source = "FileAgent"
    full_path = os.path.join(NOTES_PATH, filename)
    
    # Формируем контент по схеме
    tags_str = " ".join([f"#{t}" for t in tags])
    note_body = f"---\ntitle: {title}\nstatus: active\n---\n\n{content}\n\n{tags_str}"
    
    # 1. Валидация
    try:
        NoteValidator.validate(note_body)
    except NoteValidationError as e:
        agent_logger.error(source, f"Ошибка валидации схемы: {e}")
        raise # Невосстановимо, ошибка в логике формирования
        
    # 2. Атомарная запись
    atomic_write(full_path, note_body)
    agent_logger.step(source, f"Заметка успешно сохранена: {filename}")

if __name__ == "__main__":
    if not os.path.exists(NOTES_PATH):
        os.makedirs(NOTES_PATH)
        
    try:
        # Тестовый запуск
        create_obsidian_note(
            filename="Sprint2_Test.md",
            title="Проверка безопасности записи",
            content="Данные записаны атомарно с проверкой схемы.",
            tags=["test", "safety", "wsl2"]
        )
        print("\n" + "="*50)
        print("DOD SPRINT 2 ПРОЙДЕН: Заметка создана и проверена.")
        print("="*50)
    except Exception as e:
        print(f"Тест провален: {e}")
