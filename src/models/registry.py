from dataclasses import dataclass

@dataclass
class ModelProfile:
    vram_required_mb: int

MODEL_REGISTRY = {
    "nomic-embed-text": ModelProfile(vram_required_mb=300),
    "hermes3:8b": ModelProfile(vram_required_mb=8500),
    "qwen3.5:latest": ModelProfile(vram_required_mb=6500),
    "qwen3.5:9b": ModelProfile(vram_required_mb=6500),
    "llama3.2-vision": ModelProfile(vram_required_mb=10000)
}