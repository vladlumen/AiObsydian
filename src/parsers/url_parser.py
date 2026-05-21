import re
import requests
import trafilatura

class URLParser:
    def __init__(self):
        self.max_chars = 25000

    def extract_text(self, url: str) -> str:
        """Скачивает чистый текст статьи. Поддерживает Web и публичные Google Docs."""
        
        # Обработка Google Docs
        if "docs.google.com/document/d/" in url:
            match = re.search(r"/d/([a-zA-Z0-9-_]+)", url)
            if not match:
                raise ValueError("❌ Неверный формат ссылки Google Docs.")
            
            doc_id = match.group(1)
            export_url = f"https://docs.google.com/document/d/{doc_id}/export?format=txt"
            
            response = requests.get(export_url, timeout=15)
            if response.status_code != 200:
                raise ValueError("❌ Нет доступа к Google Doc. Документ закрыт.")
            
            text = response.text

        # Обработка обычных веб-страниц (умный парсинг)
        else:
            downloaded = trafilatura.fetch_url(url)
            if not downloaded:
                raise ValueError("❌ Не удалось скачать страницу. Сайт недоступен или блокирует ботов.")
            
            # Извлекаем только контент статьи, игнорируя меню и футеры
            text = trafilatura.extract(downloaded, include_links=False, include_formatting=True)
            
            if not text:
                raise ValueError("❌ Не удалось найти значимый текст статьи на этой странице.")

        if len(text) > self.max_chars:
            # Отрезаем лишнее, оставляя первые 25к символов, чтобы не было ошибки OOM
            text = text[:self.max_chars] + "\n\n[Текст обрезан из-за лимита токенов]"

        return text

url_parser = URLParser()