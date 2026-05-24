# Personal AI Assistant (Obsidian + Telegram) — Context Map for LLM

**Project Goal**
Telegram-based personal AI assistant for autonomous knowledge management.
Runs inside WSL2 (Ubuntu) but manipulates markdown files in a Windows Obsidian Vault via `/mnt/c/`.
Processes multimodal inputs (Text, Voice, Images, Documents) using local models.

**Hardware & Environment**
- Environment: WSL2 (Ubuntu) bridged to Windows 11 host. Windows bat-scripts automate `ollama serve` lifecycle and clean up background processes via `taskkill`.
- GPU: Single RTX 3090 24GB VRAM.
- Storage Target: `C:\Users\vladislav\Documents\ObsidianVault` (accessed via `/mnt/c/...`).

**Core Constraints & Architecture (v2.3 — May 2026)**
- **VRAM Optimization (Sequential Processing):** To eliminate GPU bottlenecks and prevent `CUDA Out of Memory`, the system uses a strict **sequential task execution architecture via `TaskQueue` (1 active worker)**. Simultaneous inference of text, voice, and vision models is programmatically blocked.
- **Circular Imports Solution:** Lazy local imports are implemented inside the `Orchestrator` handlers to completely decouple the AI core from the `aiogram` Telegram interface during the system boot sequence.
- **Event-Driven Composition:** Strict decoupling. Handlers publish typed events (`VoiceReceivedEvent`, `PhotoReceivedEvent`). The Orchestrator processes them (e.g., Audio -> STT -> Text) and re-publishes as a `TextReceivedEvent` to reuse the core Note Generation pipeline.
- **Fail-Safes:** Hard timeouts, image compression before inference (Pillow limit 800px), filename sanitization (max 60 chars), and strict regular expressions to clean up and enforce standard Obsidian Markdown structures.
- **Zombie Process Protection:** Native bash and batch automated routines kill old Python and Ollama processes before execution to prevent dual-instance and lock conflicts.

**Features Implemented**
- Telegram bot polling setup with safe reactions and Voice/Photo downloading.
- Cross-OS file system bridge: WSL2 successfully writes to Windows NTFS.
- Integrated automated end-to-end testing pipeline (`run_auto_tests.py`) and explicit isolated model quality benchmarker (`run_benchmark_test.py`).
- STT Pipeline using `faster-whisper` (`large-v3`, float16).
- Vision Pipeline using `llama3.2-vision:latest` (Ollama base64 injection) for advanced OCR on charts and code interfaces.
- Text/Structuring Pipeline using `qwen3.5:9b` (optimized with `think=False` parameter to bypass internal reasoning overhead and output clean markdown notes under 35 seconds).

**Engineering Manifesto Principles**
1. **Research & Design First:** Architecture and hardware limits dictate code.
2. **Single Source of Truth:** This file and ARCHITECTURE.md guide all LLM generations.
3. **Decoupling:** Components communicate ONLY via EventBus.
4. **Double Fail-Safes:** System prompts + Python regex/fallbacks protect against LLM hallucinations.