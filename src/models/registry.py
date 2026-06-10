from dataclasses import dataclass

@dataclass
class ModelProfile:
    vram_required_mb: int

MODEL_REGISTRY = {
    "hermes3:8b": {
        "vram_required_mb": 8500,
    },
    "qwen3-vl:8b": {
        "vram_required_mb": 8000,
    }
}