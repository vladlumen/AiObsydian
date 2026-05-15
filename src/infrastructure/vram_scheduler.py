import asyncio
from enum import Enum
from src.models.registry import MODEL_REGISTRY

class ModelState(Enum):
    UNLOADED = "unloaded"
    LOADING = "loading"
    READY = "ready"
    BUSY = "busy"
    FAILED = "failed"

class VRAMScheduler:
    def __init__(self, total_vram_mb: int = 24000):
        self.total_vram_mb = total_vram_mb
        self.used_vram_mb = 0
        self.active_models: dict[str, ModelState] = {}
        
        # 🔒 ГЛАВНЫЙ СЕМАФОР: Только один процесс может делать inference одновременно
        self.inference_lock = asyncio.Semaphore(1)
        
        # Лок на изменение состояния VRAM
        self._state_lock = asyncio.Lock()

    async def request_model(self, model_name: str):
        """Запрашивает доступ к модели, загружая ее при необходимости."""
        if model_name not in MODEL_REGISTRY:
            raise ValueError(f"Модель {model_name} не найдена в реестре!")
            
        profile = MODEL_REGISTRY[model_name]
        
        async with self._state_lock:
            current_state = self.active_models.get(model_name, ModelState.UNLOADED)
            
            if current_state == ModelState.READY:
                return  # Уже в памяти, можно использовать
                
            print(f"[VRAM] Запрос на загрузку {model_name} (Требуется {profile.vram_required_mb} MB)")
            
            # Проверяем, влезет ли. Если нет - тут позже добавим логику выгрузки других моделей
            if self.used_vram_mb + profile.vram_required_mb > self.total_vram_mb:
                print(f"[VRAM] ⚠️ ВНИМАНИЕ: Возможен OOM! Занято: {self.used_vram_mb}/{self.total_vram_mb}")
                # TODO: Вызвать unload_model() для наименее нужной модели
            
            self.active_models[model_name] = ModelState.LOADING
            
        # Симулируем процесс физической загрузки весов в видеокарту
        print(f"[VRAM] ⏳ Загрузка весов {model_name} в GPU...")
        await asyncio.sleep(1) # Здесь позже будет реальный вызов Ollama/Whisper API
        
        async with self._state_lock:
            self.used_vram_mb += profile.vram_required_mb
            self.active_models[model_name] = ModelState.READY
            print(f"[VRAM] ✅ {model_name} готова. VRAM занято: {self.used_vram_mb}/{self.total_vram_mb} MB")

    async def unload_model(self, model_name: str):
        """Выгружает модель из VRAM."""
        async with self._state_lock:
            if self.active_models.get(model_name) in [ModelState.READY, ModelState.BUSY]:
                profile = MODEL_REGISTRY[model_name]
                print(f"[VRAM] 🧹 Выгрузка {model_name} из GPU...")
                
                # Симуляция выгрузки
                await asyncio.sleep(0.5) 
                
                self.used_vram_mb -= profile.vram_required_mb
                self.active_models[model_name] = ModelState.UNLOADED
                print(f"[VRAM] 🗑️ {model_name} выгружена. Свободно VRAM: {self.total_vram_mb - self.used_vram_mb} MB")

# Глобальный инстанс планировщика для всей системы
vram_manager = VRAMScheduler(total_vram_mb=24000) # Указываем твои 24GB RTX 3090