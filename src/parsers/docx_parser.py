from pathlib import Path
import docx

class DOCXParser:
    @staticmethod
    def parse(file_path: Path) -> str:
        """Извлекает чистый текст из DOCX-файла."""
        try:
            doc = docx.Document(file_path)
            text_parts = [p.text for p in doc.paragraphs if p.text.strip()]
            return "\n".join(text_parts).strip()
        except Exception as e:
            print(f"[DOCXParser] ❌ Ошибка чтения DOCX {file_path.name}: {e}")
            return ""

docx_parser = DOCXParser()