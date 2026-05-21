import time
from pathlib import Path
from faster_whisper import WhisperModel

class STTService:
    def __init__(self, model_size: str = "large-v3"):
        self.model_size = model_size
        # Whisper инициализируется здесь, но загружается в GPU только при вызове transcribe
        self.model = None

    def _load_model(self):
        """Ленивая загрузка модели в память при первом обращении."""
        if self.model is None:
            print(f"[STTService] ⏳ Инициализация модели Whisper ({self.model_size})...")
            # compute_type="float16" сильно экономит видеопамять без потери качества
            self.model = WhisperModel(self.model_size, device="cpu", compute_type="int8")

    def transcribe(self, audio_path: Path) -> str:
        """Переводит аудио в текст."""
        self._load_model()
        
        print(f"[STTService] 🎙️ Распознаю аудио: {audio_path.name}...")
        
        # Запускаем транскрибацию (beam_size=5 дает отличный баланс скорости/качества)
        segments, info = self.model.transcribe(str(audio_path), beam_size=5, language="ru")
        
        print(f"[STTService] ℹ️ Язык определен: {info.language} (вероятность {info.language_probability:.2f})")
        
        # Собираем все сегменты в один текст
        full_text = []
        for segment in segments:
            full_text.append(segment.text)
            
        return " ".join(full_text).strip()

# Экземпляр для импорта
stt = STTService()