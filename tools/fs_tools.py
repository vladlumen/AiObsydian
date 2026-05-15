import os
import tempfile
import re

class NoteValidationError(Exception):
    """Исключение для ошибок валидации схемы заметки."""
    pass

class NoteValidator:
    """Проверка структуры заметки Obsidian (Frontmatter + Теги)."""
    @staticmethod
    def validate(content: str):
        # Проверка наличия YAML Frontmatter (--- в начале и конце блока)
        if not re.match(r"^---\n(.*\n)*---\n", content):
            raise NoteValidationError("Отсутствует или неверно оформлен YAML Frontmatter (---).")
        
        # Проверка наличия хотя бы одного тега
        if not re.search(r"#\w+", content):
            raise NoteValidationError("В заметке должен быть хотя бы один тег (#example).")
        return True

def atomic_write(filepath: str, content: str):
    """Запись файла через временный файл для предотвращения повреждений."""
    # Перед записью всегда проверяем схему заметки
    NoteValidator.validate(content)
    
    dir_name = os.path.dirname(filepath)
    if dir_name and not os.path.exists(dir_name):
        os.makedirs(dir_name, exist_ok=True)
        
    # Создаем временный файл в той же директории с поддержкой UTF-8
    with tempfile.NamedTemporaryFile('w', dir=dir_name, delete=False, encoding='utf-8') as tf:
        tf.write(content)
        temp_name = tf.name
    
    # Атомарная замена