import asyncio
from pathlib import Path
from yt_dlp import YoutubeDL

class VideoAudioParser:
    def __init__(self, download_dir: str = "temp_media"):
        self.download_dir = Path(download_dir)
        self.download_dir.mkdir(exist_ok=True)

    async def extract_audio(self, url: str) -> Path:
        """
        Выкачивает аудиодорожку из TikTok, YouTube Shorts или обычного YT.
        Возвращает путь к созданному .mp3 файлу.
        """
        # Шаблон имени файла: temp_media/ID_ВИДЕО.mp3
        out_tmpl = str(self.download_dir / "%(id)s.%(ext)s")
        
        ydl_opts = {
            'format': 'bestaudio/best',
            'outtmpl': out_tmpl,
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
            'quiet': True,
            'no_warnings': True,
            # ВРЕЗКА МАСКИРОВКИ:
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.5',
                'Sec-Fetch-Mode': 'navigate',
            }
        }

        def _download():
            with YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                # Возвращаем точный путь к сконвертированному mp3
                return self.download_dir / f"{info['id']}.mp3"

        # Запускаем синхронный yt-dlp в отдельном потоке, чтобы не вешать асинхронное ядро
        return await asyncio.to_thread(_download)

video_parser = VideoAudioParser()