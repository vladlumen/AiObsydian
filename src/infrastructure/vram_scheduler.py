import asyncio
from enum import Enum
import httpx  # Добавлен импорт для API-запросов к Ollama
from src.models.registry import MODEL_REGISTRY
from src.infrastructure.logger import logger

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

    def _log_status(self, icon: str, model_name: str, message: str, is_warning: bool = False):
        """
        ЦЕНТРАЛЬНАЯ СИТУАЦИОННАЯ ТОЧКА ЛОГИРОВАНИЯ.
        Изменение формата лога или имени модели управляется отсюда.
        """
        log_text = f"[VRAM] {icon} {message.format(model=model_name)}"
        if is_warning:
            logger.warning(log_text)
        else:
            logger.info(log_text)

    async def request_model(self, model_name: str):
        """Запрашивает доступ к модели, загружая ее при необходимости."""
        if model_name not in MODEL_REGISTRY:
            raise ValueError(f"Модель {model_name} не найдена в реестре!")
            
        profile = MODEL_REGISTRY[model_name]
        
        if isinstance(profile, dict):
            vram_required = profile.get("vram_required_mb") or profile.get("vram_required", 0)
        else:
            vram_required = getattr(profile, "vram_required_mb", 0) or getattr(profile, "vram_required", 0)
        
        async with self._state_lock:
            current_state = self.active_models.get(model_name, ModelState.UNLOADED)
            
            if current_state == ModelState.READY:
                return  
                
            self._log_status("📋", model_name, "Запрос на загрузку {model} (Требуется " + str(vram_required) + " MB)")
            
            if self.used_vram_mb + vram_required > self.total_vram_mb:
                self._log_status(
                    "⚠️", 
                    model_name, 
                    f"ВНИМАНИЕ: Возможен OOM! Занято: {self.used_vram_mb}/{self.total_vram_mb} MB при запросе {{model}}", 
                    is_warning=True
                )
            
            self.active_models[model_name] = ModelState.LOADING
            
        self._log_status("⏳", model_name, "Загрузка весов {model} в GPU...")
        await asyncio.sleep(1) 
        
        async with self._state_lock:
            self.used_vram_mb += vram_required
            self.active_models[model_name] = ModelState.READY
            self._log_status(
                "✅", 
                model_name, 
                f"{{model}} готова. VRAM занято: {self.used_vram_mb}/{self.total_vram_mb} MB"
            )

    async def unload_model(self, model_name: str):
        """Выгружает модель из VRAM и принудительно очищает память Ollama."""
        async with self._state_lock:
            if self.active_models.get(model_name) in [ModelState.READY, ModelState.BUSY]:
                profile = MODEL_REGISTRY[model_name]
                if isinstance(profile, dict):
                    vram_required = profile.get("vram_required_mb") or profile.get("vram_required", 0)
                else:
                    vram_required = getattr(profile, "vram_required_mb", 0) or getattr(profile, "vram_required", 0)

                self._log_status("🧹", model_name, "Выгрузка {model} из GPU...")
                
                # --- ВЫБРОС МОДЕЛИ ИЗ КЭША OLLAMA ---
                try:
                    async with httpx.AsyncClient(timeout=10.0) as client:
                        # keep_alive: 0 заставляет Ollama сбросить модель сразу после запроса
                        await client.post(
                            "http://127.0.0.1:11434/api/generate",
                            json={"model": model_name, "keep_alive": 0}
                        )
                except Exception as api_err:
                    self._log_status("⚠️", model_name, f"Ошибка принудительной выгрузки через API: {api_err}", is_warning=True)
                # ------------------------------------
                
                self.used_vram_mb -= vram_required
                self.active_models[model_name] = ModelState.UNLOADED
                
                self._log_status(
                    "🗑️", 
                    model_name, 
                    f"{{model}} выгружена. Свободно VRAM: {self.total_vram_mb - self.used_vram_mb} MB"
                )

vram_manager = VRAMScheduler(total_vram_mb=24000)