# Personal AI Assistant (Obsidian + Telegram) — Context Map for LLM

**Project Goal**
Telegram-based personal AI assistant for autonomous knowledge management.
Runs inside WSL2 (Ubuntu) but manipulates markdown files in a Windows Obsidian Vault via `/mnt/c/`.
Processes multimodal inputs (Text, Voice, Images, Documents) using local models.

**Hardware & Environment**
- Environment: WSL2 (Ubuntu) bridged to Windows 11 host via `run.sh` (exports CUDA `LD_LIBRARY_PATH`).
- GPU: Single RTX 3090 24GB VRAM.
- Storage Target: `C:\Users\vladislav\Documents\ObsidianVault` (accessed via `/mnt/c/...`).

**Core Constraints & Architecture (May 2026)**
- **VRAM Bottleneck:** Total models (Hermes 3 8B + Whisper + Llama3.2-Vision) exceed 24GB VRAM. 
- **Solution:** `vram_scheduler.py` uses dynamic model swapping, `MODEL_REGISTRY`, and `asyncio.Semaphore(1)` to lock GPU inference and prevent `CUDA Out of Memory`.
- **Event-Driven Composition:** Strict decoupling. Handlers publish typed events (`VoiceReceivedEvent`, `PhotoReceivedEvent`). The Orchestrator processes them (e.g., Audio -> STT -> Text) and re-publishes as a `TextReceivedEvent` to reuse the core Note Generation pipeline.
- **Fail-Safes:** Hard timeouts (e.g., 300s for Vision), image compression before inference (Pillow limit 800px), filename sanitization (max 60 chars), and strict OCR prompts to force Russian language output.
- **Zombie Process Protection:** `run.sh` strictly kills old python processes (`pkill -f`) before starting to prevent Telegram conflict errors.

**Features Implemented**
- Telegram bot polling setup with safe reactions and Voice/Photo downloading.
- Cross-OS file system bridge: WSL2 successfully writes to Windows NTFS.
- VRAM Telemetry & Pipeline Timing (logging to console).
- STT Pipeline using `faster-whisper` (`large-v3`, float16).
- Vision Pipeline using `llama3.2-vision` (Ollama base64 injection).
- Text/Structuring Pipeline using `hermes3:8b`.

**Engineering Manifesto Principles**
1. **Research & Design First:** Architecture and hardware limits dictate code.
2. **Single Source of Truth:** This file, ARCHITECTURE.md, and ROADMAP.md guide all LLM generations.
3. **Decoupling:** Components communicate ONLY via EventBus.
4. **Double Fail-Safes:** System prompts + Python regex/fallbacks protect against LLM hallucinations.