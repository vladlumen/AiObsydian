import asyncio
import os
import re
from pathlib import Path
from curl_cffi import requests as curl_requests
import trafilatura
from yt_dlp import YoutubeDL
import cv2

VIDEO_DOMAINS = re.compile(
    r"(tiktok\.com|instagram\.com|youtube\.com|youtu\.be|vimeo\.com)", 
    re.IGNORECASE
)


class SmartURLParser:
    def __init__(self, download_dir: str = "temp_media"):
        self.max_chars = 25000
        self.download_dir = Path(download_dir)
        self.download_dir.mkdir(exist_ok=True)

    def _is_video_platform(self, url: str) -> bool:
        return bool(VIDEO_DOMAINS.search(url))

    async def extract_text(self, url: str) -> str:
        if self._is_video_platform(url):
            return await self._extract_text_from_video(url)

        if "docs.google.com/document/d/" in url:
            return await self._extract_google_doc(url)

        return await self._extract_web_article(url)

    def _slice_video_to_frames(self, video_path: Path, max_frames: int = 8) -> list[Path]:
        """Нарезает видео на редкие ключевые кадры (оптимизировано под гибридный режим)."""
        frame_paths = []
        cap = cv2.MalformedVideoCapture if not cv2.VideoCapture(str(video_path)) else cv2.VideoCapture(str(video_path))
        if not cap.isOpened():
            return []

        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        fps = cap.get(cv2.CAP_PROP_FPS)
        if total_frames <= 0 or fps <= 0:
            cap.release()
            return []

        # Берем кадр каждые 3-4 секунды, чтобы не перегружать контекст Llama
        interval = max(int(fps * 3.5), 1)
        
        frame_idx = 0
        saved_count = 0

        while cap.isOpened() and saved_count < max_frames:
            ret, frame = cap.read()
            if not ret:
                break
            
            if frame_idx % interval == 0:
                frame_name = f"frame_{video_path.stem}_{saved_count}.jpg"
                frame_path = self.download_dir / frame_name
                cv2.imwrite(str(frame_path), frame, [int(cv2.IMWRITE_JPEG_QUALITY), 75])
                frame_paths.append(frame_path)
                saved_count += 1
            
            frame_idx += 1

        cap.release()
        return frame_paths

    async def _extract_text_from_video(self, url: str) -> str:
        """Гибридный параллельно-последовательный парсинг: Звук (Whisper) + Видеоряд (Llama Vision)."""
        out_tmpl = str(self.download_dir / "%(id)s.%(ext)s")
        
        ydl_opts = {
            # Скачиваем видео с вертикальным разрешением не выше 480-720p для четкого OCR текста
            'format': 'bestvideo[height<=720][ext=mp4]+bestaudio/best[ext=m4a]/best[height<=720][ext=mp4]/best',
            'outtmpl': out_tmpl,
            'quiet': True,
            'no_warnings': True,
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            }
        }

        def _download():
            with YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                ext = info.get('ext', 'mp4')
                return self.download_dir / f"{info['id']}.{ext}", info.get('title', 'Медиа-видео')

        # 1. Скачивание видеофайла
        video_path, video_title = await asyncio.to_thread(_download)

        # 2. Извлечение аудиодорожки через ffmpeg
        audio_path = video_path.with_suffix(".mp3")
        os.system(f"ffmpeg -y -i \"{video_path}\" -vn -ar 16000 -ac 1 -ab 64k \"{audio_path}\" > /dev/null 2>&1")

        # 3. Запуск транскрипции аудио (Whisper)
        transcript = "Речевой поток отсутствует или не распознан."
        if audio_path.exists() and audio_path.stat().st_size > 1000:
            try:
                from src.cognitive.stt_service import voice_service
                res_stt = await voice_service.transcribe(audio_path)
                if res_stt and len(res_stt.strip()) > 5:
                    transcript = res_stt.strip()
            except Exception as e:
                print(f"[SmartURLParser] ⚠️ Сбой STT: {e}")
            finally:
                if audio_path.exists():
                    audio_path.unlink()

        # 4. Запуск OCR видеоряда (Llama 3.2 Vision)
        print(f"[SmartURLParser] 🎬 Сбор кадров для оптического распознавания текста...")
        frames = await asyncio.to_thread(self._slice_video_to_frames, video_path)
        
        # Видеофайл больше не нужен, удаляем
        if video_path.exists():
            video_path.unlink()
        vision_text = "Текст на экране не обнаружен."
        if frames:
            try:
                from src.cognitive.vision_service import vision_service
                from src.infrastructure.vram_scheduler import vram_manager
                from src.infrastructure.telemetry import telemetry

                model_name = "llava"
                
                # Делаем промпт жестко ориентированным на сквозной анализ всей раскадровки
                vision_prompt = (
                    "Перед тобой раскадровка (последовательные кадры) из одного видеоролика. "
                    "Внимательно изучи все изображения вместе. Твоя задача — извлечь текстовые субтитры, "
                    "ингредиенты рецепта и шаги приготовления, которые появляются на экране по ходу видео. "
                    "Собери их в один связный, логичный текст рецепта. Игнорируй интерфейс приложения, лайки и водяные знаки."
                )
                
                async with telemetry.track(f"URL_Video_Vision_Inference"):
                    async with vram_manager.inference_lock:
                        await vram_manager.request_model(model_name)
                        try:
                            # КРИТИЧЕСКИЙ ФИКС: Передаем ВЕСЬ массив путей к кадрам в ОДИН вызов.
                            res = await vision_service.analyze_image_batch(frames, vision_prompt)
                            if res and res.strip():
                                vision_text = res.strip()
                        except AttributeError:
                            # Фолбэк, если метод batch еще не написан — собираем под единым локом, 
                            # но с жестким требованием не писать отказ
                            ocr_results = []
                            for frame_p in frames:
                                res = await vision_service.analyze_image(frame_p, "Что написано на экране? Пиши только текст, без рассуждений. Если текста нет — пиши 'Пропуск'.")
                                if res and "технически я не могу" not in res.lower() and "пропуск" not in res.lower():
                                    ocr_results.append(res.strip())
                            if ocr_results:
                                vision_text = "\n".join(ocr_results)
                        finally:
                            await vram_manager.unload_model(model_name)

                # Зачистка временных картинок
                for frame_p in frames:
                    if frame_p.exists():
                        frame_p.unlink()

            except Exception as vision_err:
                for frame_p in frames:
                    if frame_p.exists():
                        frame_p.unlink()
                print(f"[SmartURLParser] ⚠️ Сбой слоев Vision: {vision_err}")
                for frame_p in frames:
                    if frame_p.exists():
                        frame_p.unlink()
                print(f"[SmartURLParser] ⚠️ Сбой слоев Vision: {vision_err}")

        # 5. Сборка гибридного payload для NoteGeneratorAgent
        combined_payload = (
            f"Данные видеофайла \"{video_title}\":\n\n"
            f"=== РАСШИФРОВКА АУДИОДОРОЖКИ (ЧТО ГОВОРЯТ) ===\n{transcript}\n\n"
            f"=== ТЕКСТ С ЭКРАНА ВИДЕО (ЧТО НАПИСАНО) ===\n{vision_text}"
        )
        
        return combined_payload

    async def _extract_google_doc(self, url: str) -> str:
        match = re.search(r"/d/([a-zA-Z0-9-_]+)", url)
        if not match:
            raise ValueError("❌ Неверный формат ссылки Google Docs.")
        
        doc_id = match.group(1)
        export_url = f"https://docs.google.com/document/d/{doc_id}/export?format=txt"
        
        def _fetch_doc():
            r = curl_requests.get(export_url, timeout=15)
            if r.status_code != 200:
                raise ValueError("❌ Нет доступа к Google Doc. Документ закрыт.")
            return r.text

        text = await asyncio.to_thread(_fetch_doc)
        return self._truncate_text(text)

    async def _extract_web_article(self, url: str) -> str:
        def _fetch_web():
            response = curl_requests.get(url, impersonate="chrome", timeout=15)
            if response.status_code != 200:
                return None
            return response.content

        html_content = await asyncio.to_thread(_fetch_web)
        if not html_content:
            raise ValueError("❌ Сайт недоступен или заблокировал запрос (код ответа не 200).")
        
        text = trafilatura.extract(html_content, include_links=False, include_formatting=True)
        if not text:
            raise ValueError("❌ Не удалось найти значимый текст статьи на этой странице.")

        return self._truncate_text(text)

    def _truncate_text(self, text: str) -> str:
        if len(text) > self.max_chars:
            return text[:self.max_chars] + "\n\n[Текст обрезан из-за лимита токенов]"
        return text


url_parser = SmartURLParser()