# AI_CONTEXT.md
# Personal AI Assistant (Obsidian + Telegram) — Context Map for LLM

**Project Goal**
Telegram-based personal AI assistant for autonomous knowledge management.
Runs inside WSL2 (Ubuntu) but manipulates markdown files in a Windows Obsidian Vault via `/mnt/c/`.
Processes multimodal inputs (Text, Voice, Images, Documents) using local models.

**Hardware & Environment**
- Environment: WSL2 (Ubuntu) bridged to Windows 11 host.
- GPU: Single RTX 3090 24GB VRAM.
- Storage Target: `C:\Users\vladislav\Documents\ObsidianVault` (accessed via `/mnt/c/...`).

**Core Constraints & Architecture (May 2026 Refactoring)**
- **VRAM Bottleneck:** Total models (Hermes 3 8B + Whisper + LLaVA) exceed 24GB VRAM. 
- **Solution:** `vram_scheduler.py` uses dynamic model swapping (load/unload) and `asyncio.Semaphore(1)` to lock GPU inference and prevent `CUDA Out of Memory`.
- **Event-Driven:** Strict decoupling. Telegram handlers do NOT call LLMs directly. They publish typed dataclass events (e.g., `VoiceReceivedEvent`) to `event_bus.py`.
- **3-Tier Separation:** 1. Infrastructure (Queue, VRAM Scheduler, EventBus)
  2. Cognitive Layer (LLM, STT, Vision, Memory)
  3. Agent Behaviors (Clerk Agent, Obsidian Writer)

**Features Implemented (May 2026)**
- Telegram bot polling setup (Admin ID locked).
- Cross-OS file system bridge: WSL2 successfully writes to Windows NTFS via atomic writes (`tempfile` + `os.replace`).
- Note Validation: Strict enforcement of YAML Frontmatter and `#tags`.
- Clerk Agent: Auto-categorizes `00_Inbox` notes into `work`, `sport`, `trips`, `task`, `diary` using local LLM. Fallback to inline-keyboard suggestions for unknown categories.

**Folder Structure (src/)**
├── core/
│   ├── orchestrator.py      # Subscribes to events, coordinates cognitive services
│   ├── config.py            # Holds BASE_DIR (Linux) and VAULT_DIR (Windows)
│   └── session_manager.py   # User context and session routing
├── infrastructure/
│   ├── event_bus.py         # Pub/Sub system + Typed Events (@dataclass)
│   ├── task_queue.py        # Async task queue to handle spam
│   ├── vram_scheduler.py    # GPU Lifecycle (LOADING, READY, BUSY) & Locks
│   └── telemetry.py         # VRAM monitoring and structured logging
├── models/
│   ├── registry.py          # MODEL_REGISTRY with vram_required & backend type
│   └── loaders.py           # Physical load/unload logic to VRAM
├── cognitive/
│   ├── memory/              # conversation.py (short), semantic.py (LanceDB)
│   ├── llm_service.py       # Text-to-Text (Hermes 3 / Ollama)
│   ├── stt_service.py       # Audio-to-Text (Whisper)
│   └── vision_service.py    # Image-to-Text (LLaVA / Llama-Vision)
├── agents/
│   ├── clerk_agent.py       # Sorting logic for 00_Inbox
│   └── obsidian_writer.py   # Atomic writes and markdown formatting
├── interfaces/
│   └── telegram/
│       ├── bot.py           # Aiogram setup
│       └── handlers.py      # Catches inputs -> publishes Events
├── parsers/
│   ├── pdf_parser.py        # Text extraction
│   └── docx_parser.py       # Text extraction
└── storage/
    ├── vector_store.py      # LanceDB wrapper (stored in Linux data/ dir)
    └── sqlite_manager.py    # SQLite for logs/tasks

**Data Storage Rules**
- ALL code, databases (LanceDB, SQLite), and temp files live in Linux `/home/vladislav/projects/agent_project/`.
- ONLY final `.md` files are written to Windows `/mnt/c/Users/.../ObsidianVault/`.