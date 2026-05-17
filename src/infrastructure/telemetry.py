import time
import logging
from contextlib import asynccontextmanager
from src.infrastructure.vram_scheduler import vram_manager

# --- ИСПРАВЛЕННЫЙ БЛОК НАСТРОЙКИ ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%H:%M:%S',
    force=True  # <-- Этот флаг сносит чужие настройки и активирует наш вывод
)
# ----------------------------------
logger = logging.getLogger("AI_OS")

class TelemetryManager:
    def __init__(self):
        self.logger = logger

    @asynccontextmanager
    async def track(self, phase_name: str):
        """Контекстный менеджер для замера времени выполнения и состояния VRAM."""
        start_time = time.perf_counter()
        vram_before = vram_manager.used_vram_mb
        
        self.logger.info(
            f"[📊 {phase_name}] Старт. Свободно VRAM: {vram_manager.total_vram_mb - vram_before} MB"
        )
        
        try:
            yield
        except Exception as e:
            self.logger.error(f"[❌ {phase_name}] Сбой через {time.perf_counter() - start_time:.2f} сек: {e}")
            raise e
        else:
            duration = time.perf_counter() - start_time
            vram_after = vram_manager.used_vram_mb
            self.logger.info(
                f"[📈 {phase_name}] Успешно за {duration:.2f} сек. "
                f"VRAM на финише: {vram_after}/{vram_manager.total_vram_mb} MB"
            )

telemetry = TelemetryManager()