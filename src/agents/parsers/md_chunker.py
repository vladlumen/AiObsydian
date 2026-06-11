import os
import re
import uuid
from typing import List, Dict, Any, Optional, Tuple

class MarkdownChunker:
    """
    Иерархический парсер Markdown-файлов.
    Разбивает текст на чанки по заголовкам (##, ###) и задачам (- [ ]).
    Обеспечивает наследование метаданных, иерархии заголовков и контекста директорий.
    """
    
    def __init__(self):
        self.header_regex = re.compile(r'^(#{1,6})\s+(.+?)\s*$')
        self.todo_regex = re.compile(r'^\s*-\s*\[([ xX])\]\s+(.+)$')
        self.yaml_regex = re.compile(r'^---\s*\n(.*?)\n---\s*\n', re.DOTALL)
        self.code_block_regex = re.compile(r'(?s)```.*?```|`.*?`')
        self.wikilink_regex = re.compile(r'\[\[([^|#\]]+)(?:#([^|\]]+))?(?:\|([^\]]+))?\]\]')
        self.tag_regex = re.compile(r'#([a-zA-Zа-яА-Я0-9_\-/]+)')

    def parse_file(self, file_path: str, content: str) -> List[Dict[str, Any]]:
        """
        Главный метод парсинга файла. Возвращает список словарей-чанков для базы данных.
        """
        # Шаг 2.1 & 2.4: Ленивый импорт конфигурации директорий
        from src.core.config import VAULT_DIRECTORY_CONTEXT
        
        chunks = []
        yaml_metadata = self._extract_yaml(content)
        clean_content = self._strip_yaml(content)
        
        # Извлечение контекста директории
        directory_context = "Общий контекст базы знаний"
        is_sensitive = False
        
        normalized_path = file_path.replace("\\", "/")
        matched_folder = None
        longest_match = 0
        
        # Находим наиболее точное совпадение пути по нашей карте
        for folder, data in VAULT_DIRECTORY_CONTEXT.items():
            if folder in normalized_path and len(folder) > longest_match:
                matched_folder = folder
                longest_match = len(folder)
                
        if matched_folder:
            directory_context = VAULT_DIRECTORY_CONTEXT[matched_folder]["context"]
            is_sensitive = VAULT_DIRECTORY_CONTEXT[matched_folder]["is_sensitive"]

        
        # Маскирование кода
        masked_content, code_placeholders = self._mask_code_blocks(clean_content)
        lines = masked_content.splitlines()
        original_lines = clean_content.splitlines()
        
        current_headers = {1: None, 2: None, 3: None, 4: None, 5: None, 6: None}
        current_chunk_lines = []
        current_original_lines = []
        
        idx = 0
        while idx < len(lines):
            line = lines[idx]
            original_line = original_lines[idx] if idx < len(original_lines) else line
            cleaned_line = line.strip()
            header_match = self.header_regex.match(cleaned_line)
            todo_match = self.todo_regex.match(cleaned_line)
            
            if header_match:
                if current_chunk_lines:
                    # Шаг 2.2: Извлечение текущей цепочки заголовков из стека до обновления текущего уровня
                    header_chain = [current_headers[i] for i in sorted(current_headers.keys()) if current_headers[i] is not None]
                    chunk = self._build_chunk(
                        lines=current_chunk_lines,
                        file_path=file_path,
                        yaml_meta=yaml_metadata,
                        header_chain=header_chain,
                        directory_context=directory_context,
                        code_placeholders=code_placeholders,
                        is_sensitive=is_sensitive
                    )
                    if chunk:
                        chunks.append(chunk)
                    current_chunk_lines = []
                    current_original_lines = []
                
                level = len(header_match.group(1))
                title = header_match.group(2).strip()
                title = self._unmask_code_blocks(title, code_placeholders)
                current_headers[level] = title
                
                for l in range(level + 1, 7):
                    current_headers[l] = None
                    
                current_chunk_lines.append(cleaned_line)
                current_original_lines.append(original_line.strip())
                idx += 1
                
            elif todo_match:
                # Собираем многострочный TODO (включая строки с отступом)
                todo_masked_lines = [cleaned_line]
                todo_original_lines = [original_line.strip()]
                idx += 1
                
                # Собираем продолжение TODO - строки с отступом
                while idx < len(lines):
                    next_line = lines[idx]
                    next_original = original_lines[idx] if idx < len(original_lines) else next_line
                    
                    # Если строка имеет отступ в начале, это продолжение TODO
                    if next_line and next_line[0] in (' ', '\t') and next_line.strip():
                        todo_masked_lines.append(next_line.strip())
                        todo_original_lines.append(next_original.strip())
                        idx += 1
                    else:
                        break
                
                # Собираем весь TODO в одну строку для парсинга
                full_todo_masked = " ".join(todo_masked_lines)
                full_todo_original = " ".join(todo_original_lines)
                
                # Шаг 2.2: Сбор контекста для Todo-микрочанка
                header_chain = [current_headers[i] for i in sorted(current_headers.keys()) if current_headers[i] is not None]
                todo_chunk = self._build_todo_chunk(
                    line=full_todo_masked,
                    file_path=file_path,
                    yaml_meta=yaml_metadata,
                    header_chain=header_chain,
                    directory_context=directory_context,
                    code_placeholders=code_placeholders,
                    is_sensitive=is_sensitive,
                    original_line=full_todo_original
                )
                chunks.append(todo_chunk)
                current_chunk_lines.append(full_todo_masked)
                current_original_lines.append(full_todo_original)
                
            else:
                current_chunk_lines.append(cleaned_line)
                current_original_lines.append(original_line.strip())
                idx += 1
                
        if current_chunk_lines:
            header_chain = [current_headers[i] for i in sorted(current_headers.keys()) if current_headers[i] is not None]
            chunk = self._build_chunk(
                lines=current_chunk_lines,
                file_path=file_path,
                yaml_meta=yaml_metadata,
                header_chain=header_chain,
                directory_context=directory_context,
                code_placeholders=code_placeholders,
                is_sensitive=is_sensitive
            )
            if chunk:
                chunks.append(chunk)
                
        return chunks

    def _extract_yaml(self, content: str) -> Dict[str, Any]:
        """Извлекает сырой YAML Frontmatter."""
        match = self.yaml_regex.match(content)
        if not match:
            return {}
        yaml_dict = {}
        yaml_lines = match.group(1).splitlines()
        for line in yaml_lines:
            if ':' in line:
                k, v = line.split(':', 1)
                yaml_dict[k.strip()] = v.strip().strip('"').strip("'")
        return yaml_dict

    def _strip_yaml(self, content: str) -> str:
        """Удаляет YAML Frontmatter из текста."""
        return self.yaml_regex.sub('', content)

    def _mask_code_blocks(self, text: str) -> Tuple[str, List[str]]:
        """Изолирует блоки кода временными плейсхолдерами."""
        placeholders = []
        def replace_match(match):
            placeholder = f"__CODE_BLOCK_{len(placeholders)}__"
            placeholders.append(match.group(0))
            return placeholder
        return self.code_block_regex.sub(replace_match, text), placeholders

    def _unmask_code_blocks(self, text: str, placeholders: List[str]) -> str:
        """Возвращает оригинальный код на место."""
        for i, original in enumerate(placeholders):
            text = text.replace(f"__CODE_BLOCK_{i}__", original)
        return text

    def _extract_metadata_from_masked(self, masked_text: str) -> Tuple[List[Dict[str, Any]], List[str]]:
        """Извлекает Wikilinks и теги из замаскированного текста."""
        links = []
        for match in self.wikilink_regex.finditer(masked_text):
            links.append({
                "target": match.group(1).strip(),
                "anchor": match.group(2).strip() if match.group(2) else None,
                "alias": match.group(3).strip() if match.group(3) else None
            })
        tags = [m.group(1).strip() for m in self.tag_regex.finditer(masked_text) if not m.group(1).strip().isdigit()]
        return links, list(set(tags))

    def _build_chunk(self, lines: List[str], file_path: str, yaml_meta: Dict[str, Any], header_chain: List[str], directory_context: str, code_placeholders: List[str], is_sensitive: bool) -> Optional[Dict[str, Any]]:
        """Формирует стандартный текстовый чанк с префиксной инжекцией Khoj-контекста."""
        masked_raw_text = "\n".join(lines).strip()
        if not masked_raw_text:
            return None
            
        links, tags = self._extract_metadata_from_masked(masked_raw_text)
        raw_text = self._unmask_code_blocks(masked_raw_text, code_placeholders)
        
        # Шаг 2.3: Префиксная инжекция Khoj-шаблона
        header_path_str = " > ".join(header_chain)
        if header_path_str:
            context_prefix = f"[Папка: {directory_context} | Путь: {header_path_str}]\n\n"
        else:
            context_prefix = f"[Папка: {directory_context}]\n\n"
            
        full_payload = f"{context_prefix}{raw_text}"
        
        return {
            "id": str(uuid.uuid4()),
            "file_path": file_path,
            "text": full_payload,
            "metadata": {
                "file_name": os.path.basename(file_path),
                "header_path": header_path_str,         # Сохранено для совместимости с нормализатором VectorStore
                "header_chain": header_chain,           # Шаг 2.2: Массив иерархии
                "directory_context": directory_context, # Шаг 2.4: Описание папки
                "is_sensitive": is_sensitive, # Новый флаг для защиты личных данных
                "frontmatter": yaml_meta,
                "type": "content_block",
                "links": links,
                "tags": tags
            }
        }

    def _build_todo_chunk(self, line: str, file_path: str, yaml_meta: Dict[str, Any], header_chain: List[str], directory_context: str, code_placeholders: List[str], is_sensitive: bool, original_line: str = None) -> Dict[str, Any]:
        """Формирует специализированный микро-чанк для задачи (- [ ]) с Khoj-контекстом."""
        links, tags = self._extract_metadata_from_masked(line)
        # Используем оригинальную строку для содержимого, если она предоставлена
        display_line = original_line if original_line else line
        display_line = self._unmask_code_blocks(display_line, code_placeholders)
        
        header_path_str = " > ".join(header_chain)
        if header_path_str:
            context_prefix = f"[Папка: {directory_context} | Путь: {header_path_str}]\n\n"
        else:
            context_prefix = f"[Папка: {directory_context}]\n\n"
            
        full_payload = f"{context_prefix}{display_line.strip()}"
        
        return {
            "id": str(uuid.uuid4()),
            "file_path": file_path,
            "text": full_payload,
            "metadata": {
                "file_name": os.path.basename(file_path),
                "header_path": header_path_str,         # Сохранено для совместимости
                "header_chain": header_chain,           # Шаг 2.2
                "directory_context": directory_context, # Шаг 2.4
                "is_sensitive": is_sensitive,
                "frontmatter": yaml_meta,
                "type": "todo_item",
                "links": links,
                "tags": tags
            }
        }