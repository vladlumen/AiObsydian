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
    ),
    "llava": ModelProfile(
        name="llava",
        type="vision",
        backend="ollama",
        vram_required_mb=5500,
        load_strategy="on_demand"
    ),
    "llama3.2-vision": ModelProfile(
        name="llama3.2-vision",
        type="vision",
        backend="ollama",
        vram_required_mb=6000,
        load_strategy="on_demand"
    ),
    "nomic-embed-text": ModelProfile(
        name="nomic-embed-text",
        type="llm",  # или, возможно, "embedding", но в текущих типах только llm, stt, vision. Поскольку это эмбеддинговая модель, но в реестре используется для распределения VRAM, тип можно указать как "llm" или, если есть другой тип, но в данном случае только эти три. Оставим как "llm".
        backend="ollama",
        vram_required_mb=300,
        load_strategy="on_demand"
    )
}