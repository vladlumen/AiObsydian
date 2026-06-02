# 📑 Personal AI Assistant (Obsidian + Telegram) — Context Map for LLM

**Project Goal**
Telegram-based personal AI assistant for autonomous knowledge management.
Runs inside WSL2 (Ubuntu) but manipulates markdown files in a Windows Obsidian Vault via `/mnt/c/`.
Processes multimodal inputs (Text, Voice, Images, Documents) using local models.

**Hardware & Environment**
- Environment: WSL2 (Ubuntu) bridged to Windows 11 host. Windows bat-scripts automate `ollama serve` lifecycle and clean up background processes via `taskkill`.
- GPU: Single RTX 3090 24GB VRAM.
- Storage Target: `/w/home/vladislav/projects/agent_project/` (accessed via WSL bridge to Obsidian).

**Core Constraints & Architecture (v2.6 — June 2026)**
- **Multi-level Caching (L1/L2/L3):** To minimize latency and GPU load, a three-tier cache is implemented:
    1. **L1 (Exact Match):** SQLite-based. Rapid search via `hash(query)`. Instant response (0.01s) for identical queries.
    2. **L2 (Semantic Match):** LanceDB-based. Vector search using embeddings. If cosine similarity exceeds threshold, returns cached answer without LLM call.
    3. **L3 (Full RAG):** Fallback to the full pipeline: `Retrieval (LanceDB) -> Context Injection -> LLM Inference (Hermes 3) -> Cache Save`.
- **Hierarchical RAG and Hybrid Search (v2.6):** The system uses the L1/L2/L3 caching strategy described above. The `src/agents/parsers/md_chunker.py` module splits markdown by headers and tasks while preserving YAML frontmatter and `header_path`. Search in LanceDB operates in hybrid mode (Nomic Embed vectors + BM25 FTS) with `LinearCombinationReranker` for precise token and log extraction.
- **Изолированный RAG-пайплайн для поисковых запросов (v2.6):** Поисковые запросы с префиксом `?` обрабатываются изолированным RAGAgent, используя многоуровневое кэширование (L1/L2). Чтение файлов целиком замене_но на семантическое извлечение чанков через метод `memory.retrieve_context(query)`. Контекст обертывается в XML-теги `<context>` для жесткого контроля галлюцинаций модели Hermes 3. Температура инференса выставляется в 0.0, а системный промпт разрешает свободный контекстный анализ содержания и сопоставление синонимов, выдавая отказ ('Данных в базе знаний нет') только при полной нерелевантности контекста. Имя исходного файла принудительно инъецируется в тело контекста чанка для сквозной связки.
- **VRAM Optimization (Sequential Processing):** To eliminate GPU bottlenecks and prevent `CUDA Out of Memory`, the system uses a strict **sequential task execution architecture via `TaskQueue` (1 active worker)**. Simultaneous inference of text and vision models inside the GPU is programmatically blocked.
- **Automated Media Cleanup:** To avoid storage leakage inside WSL2, the `TaskQueue` worker automatically sweeps and deletes processed binary files (`.ogg`, `.png`, `.pdf`, `.docx`) from `data/temp_media/` immediately after task completion using try/finally blocks.
- **API Stability (Direct HTTP client):** To prevent connection drops and unexpected token cuts by the official `ollama-python` library, all text and vision requests communicate with Ollala directly via async JSON payloads using `httpx` and the flat text generation endpoint `/api/generate`.
- **Circular Imports Solution:** Lazy local imports are implemented inside the `Orchestrator` handlers to completely decouple the AI core from the `aiogram` Telegram interface during the system boot sequence.
- **Event-Driven Composition:** Strict decoupling. Handlers publish typed events (`VoiceReceivedEvent`, `PhotoReceivedEvent`, `DocumentReceivedEvent`). The Orchestrator processes them (e.g., Audio -> STT -> Text) and re-publishes as a `TextReceivedEvent` to reuse the core Note Generation pipeline.
- **Fail-Safes:** Hard timeouts, image compression before inference (Pillow limit 800px), filename sanitization (max 120 chars to prevent cut-off anomalies), case-insensitive regex parsing (`re.IGNORECASE`), and dynamic datetime extraction to prevent LLM hallucinations or metadata-driven crashes.
- **Zombie Process Protection:** Native bash and batch automated routines kill old Python and Ollama processes before execution to prevent dual-instance and lock conflicts.

**Features Implemented**
- Telegram bot polling setup with safe reactions and Voice/Photo/Document downloading.
- Cross-OS file system bridge: WSL2 successfully writes to Windows NTFS vault.
- Integrated automated end-to-end testing pipeline (`run_auto_tests.py`) using real media files as fixtures to prevent EOF/parsing regressions.
- Incremental Obsidian Vault synchronization (Khoj-pattern) via SQLite-based `mtime` and file hashing registry to prevent redundant embedding calculations.
- **Hierarchical Markdown Chunking (Khoj-pattern):** The `MarkdownChunker` parser splits documents into structured chunks by headers (##, ###) and todo items (- [ ]), preserving header hierarchy and YAML frontmatter for precise retrieval. Context is injected into chunk text for vector model context linking.
- STT Pipeline using `faster-whisper` (`large-v3`) deployed strictly on CPU in `int8` mode to save 100% of GPU VRAM for LLM/Vision inference.
- Vision Pipeline using `llama3.2-vision:latest` (Ollama base64 injection) for advanced OCR on charts and code interfaces.
- Document Parsing Pipeline: Functional parsers for `.pdf` (via `pypdf`) and `.docx` (via `docx2txt`) connected to a central `DocumentParser` router.
- Text/Structuring Pipeline using **`hermes3:8b`** (configured at `temperature: 0.0` for maximum strictness; successfully bypasses internal reasoning overhead, strictly adheres to Obsidian layout constraints, and finishes complex RAG ingestion tasks under 9 seconds).
- **Hybrid Vector Search (BM25 + Embeddings):** `VectorStore` implements `search_hybrid()` combining FTS (BM25) and vector similarity search with `LinearCombinationReranker`. Инференс векторов переведен на выделенный эндпоинт Ollama /api/embed, что снизило время генерации вектора запроса до 0.9–1.4 сек. Automatic FTS index creation on chunk insertion.

**Engineering Manifesto Principles**
 1. **Research & Design First:** Architecture and hardware limits dictate code.
 2. **Single Source of Truth:** This file and ARCHITECTURE.md guide all LLM generations.
 3. **Decoupling:** Components communicate ONLY via EventBus.
 4. **Double Fail-Safes:** System prompts + Python regex/fallbacks protect against LLM hallucinations.
 5. **Lazy Import Rule:** Cognitive services (llm, memory, stt) are strictly forbidden to be imported at module level in dispatchers and orchestrators. Import is performed only inside Agent methods for eliminating circular dependencies during system core initialization.