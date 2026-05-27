import os
import re
import uuid
from typing import List, Dict, Any, Optional

class MarkdownChunker:
    """
    Иерархический парсер Markdown-файлов.
    Разбивает текст на чанки по заголовкам (##, ###) и задачам (- [ ]).
    Обеспечивает наследование метаданных и иерархии заголовков.
    """
    
    def __init__(self):
        self.header_regex = re.compile(r'^(#{1,6})\s+(.+?)\s*$')
        self.todo_regex = re.compile(r'^\s*-\s*\[([ xX])\]\s+(.+)$')
        self.yaml_regex = re.compile(r'^---\s*\n(.*?)\n---\s*\n', re.DOTALL)

    def parse_file(self, file_path: str, content: str) -> List[Dict[str, Any]]:
        """
        Главный метод парсинга файла. Возвращает список словарей-чанков для базы данных.
        """
        chunks = []
        yaml_metadata = self._extract_yaml(content)
        clean_content = self._strip_yaml(content)
        
        lines = clean_content.splitlines()
        
        current_headers = {1: None, 2: None, 3: None, 4: None, 5: None, 6: None}
        current_chunk_lines = []
        
        for line in lines:
            cleaned_line = line.strip()
            header_match = self.header_regex.match(cleaned_line)
            todo_match = self.todo_regex.match(line)
            
            if header_match:
                if current_chunk_lines:
                    chunk = self._build_chunk(
                        lines=current_chunk_lines,
                        file_path=file_path,
                        yaml_meta=yaml_metadata,
                        headers=current_headers
                    )
                    if chunk:
                        chunks.append(chunk)
                    current_chunk_lines = []
                
                level = len(header_match.group(1))
                title = header_match.group(2).strip()
                current_headers[level] = title
                
                for l in range(level + 1, 7):
                    current_headers[l] = None
                    
                current_chunk_lines.append(cleaned_line)
                
            elif todo_match:
                todo_chunk = self._build_todo_chunk(
                    line=cleaned_line,
                    file_path=file_path,
                    yaml_meta=yaml_metadata,
                    headers=current_headers
                )
                chunks.append(todo_chunk)
                current_chunk_lines.append(cleaned_line)
                
            else:
                current_chunk_lines.append(cleaned_line)
                
        if current_chunk_lines:
            chunk = self._build_chunk(
                lines=current_chunk_lines,
                file_path=file_path,
                yaml_meta=yaml_metadata,
                headers=current_headers
            )
            if chunk:
                chunks.append(chunk)
                
        return chunks

    def _extract_yaml(self, content: str) -> Dict[str, Any]:
        """Извлекает сырой YAML Frontmatter (простой парсинг ключ-значение без внешних завимостей)."""
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
        """Удаляет YAML Frontmatter из текста для предотвращения дублирования в эмбеддингах."""
        return self.yaml_regex.sub('', content)

    def _build_header_path(self, headers: Dict[int, Optional[str]]) -> str:
        """Собирает цепочку родительских заголовков в строку вида: H1 > H2 > H3"""
        path_parts = [headers[i] for i in sorted(headers.keys()) if headers[i] is not None]
        return " > ".join(path_parts) if path_parts else ""

    def _build_chunk(self, lines: List[str], file_path: str, yaml_meta: Dict[str, Any], headers: Dict[int, Optional[str]]) -> Optional[Dict[str, Any]]:
        """Формирует стандартный текстовый чанк с инъекцией контекста в тело текста."""
        raw_text = "\n".join(lines).strip()
        if not raw_text:
            return None
            
        header_path = self._build_header_path(headers)
        
        # Инъецируем путь заголовков прямо в текст чанка для усиления веса при поиске
        full_indexed_text = f"Контекст: {header_path}\n{raw_text}" if header_path else raw_text
        
        return {
            "id": str(uuid.uuid4()),
            "file_path": file_path,
            "text": full_indexed_text,
            "metadata": {
                "file_name": os.path.basename(file_path),
                "header_path": header_path,
                "frontmatter": yaml_meta,
                "type": "content_block"
            }
        }

    def _build_todo_chunk(self, line: str, file_path: str, yaml_meta: Dict[str, Any], headers: Dict[int, Optional[str]]) -> Dict[str, Any]:
        """Формирует специализированный микро-чанк для задачи (- [ ])."""
        header_path = self._build_header_path(headers)
        return {
            "id": str(uuid.uuid4()),
            "file_path": file_path,
            "text": line.strip(),
            "metadata": {
                "file_name": os.path.basename(file_path),
                "header_path": header_path,
                "frontmatter": yaml_meta,
                "type": "todo_item"
            }
        }