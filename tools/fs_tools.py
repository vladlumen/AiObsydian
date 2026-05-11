import os
import tempfile
import re
from typing import List, Dict

class NoteValidationError(Exception):
    """Исключение для ошибок валидации схемы заметки."""
    pass

class NoteValidator:
    """Проверка структуры заметки Obsidian (Frontmatter + Теги)."""
    @staticmethod
    def validate(content: str):
        # Простая проверка наличия YAML Frontmatter (--- в начале и конце блока)
        if not re.match(r"^---\n(.*\n)*---\n", content):
            raise NoteValidationError("Отсутствует или неверно оформлен YAML Frontmatter (---).")
        
        # Проверка наличия хотя бы одного тега (например, #tag)
        if not re.search(r"#\w+", content):
            raise NoteValidationError("В заметке должен быть хотя бы один тег (#example).")
        return True

def atomic_write(filepath: str, content: str):
    """Запись файла через временный файл для предотвращения повреждений."""
    dir_name = os.path.dirname(filepath)
    # Создаем временный файл в той же директории
    with tempfile.NamedTemporaryFile('w', dir=dir_name, delete=False) as tf:
        tf.write(content)
        temp_name = tf.name
    
    # Атомарная замена (в POSIX системах это гарантирует целостность)
    os.replace(temp_name, filepath)
