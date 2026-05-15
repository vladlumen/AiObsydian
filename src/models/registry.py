from dataclasses import dataclass
from typing import Dict

@dataclass
class ModelProfile:
    name: str
    type: str              # "llm", "stt", "vision"
    backend: str           # "ollama", "faster-whisper"
    vram_required_mb: int  # Сколько памяти жрет при работе
    load_strategy: str     # "persistent" (держать всегда) или "on_demand" (выгружать)

MODEL_REGISTRY: Dict[str, ModelProfile] = {
    "hermes3:8b": ModelProfile(
        name="hermes3:8b",
        type="llm",
        backend="ollama",
        vram_required_mb=8500,
        load_strategy="persistent"
    ),
    "whisper-large-v3": ModelProfile(
        name="whisper-large-v3",
        type="stt",
        backend="faster-whisper",
        vram_required_mb=3500,
        load_strategy="on_demand" 
    ),
    "llava:7b": ModelProfile(
        name="llava:7b",
        type="vision",
        backend="ollama",
        vram_required_mb=7000,
        load_strategy="on_demand"
    )
}