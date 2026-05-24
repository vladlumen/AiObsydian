from pathlib import Path
from pypdf import PdfReader

class PDFParser:
    @staticmethod
    def parse(file_path: Path) -> str:
        """Извлекает чистый текст из PDF-файла."""
        try:
            reader = PdfReader(file_path)
            text_parts = []
            for page in reader.pages:
                page_text = page.extract_text()
                if page_text:
                    text_parts.append(page_text)
            return "\n".join(text_parts).strip()
        except Exception as e:
            print(f"[PDFParser] ❌ Ошибка чтения PDF {file_path.name}: {e}")
            return ""

pdf_parser = PDFParser()