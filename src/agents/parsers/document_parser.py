import fitz  # PyMuPDF
import docx
from pathlib import Path

class DocumentParser:
    def __init__(self):
        self.max_chars = 25000

    def extract_text(self, file_path: Path) -> str:
        ext = file_path.suffix.lower()
        text = ""

        if ext == ".pdf":
            try:
                doc = fitz.open(file_path)
                for page in doc:
                    text += page.get_text()
                doc.close()
            except Exception as e:
                raise ValueError(f"Ошибка чтения PDF: {e}")

        elif ext == ".docx":
            try:
                doc = docx.Document(file_path)
                text = "\n".join([para.text for para in doc.paragraphs])
            except Exception as e:
                raise ValueError(f"Ошибка чтения DOCX: {e}")
        else:
            raise ValueError(f"Формат {ext} не поддерживается. Только PDF и DOCX.")

        if not text.strip():
            raise ValueError("Документ пуст или не содержит распознаваемого текста.")

        if len(text) > self.max_chars:
            text = text[:self.max_chars] + "\n\n[Текст обрезан из-за лимита токенов]"

        return text

document_parser = DocumentParser()
