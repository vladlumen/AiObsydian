# Архитектура и Структура Проекта (v2.0)

**Правила Хранения Данных:**
- ВЕСЬ код, базы данных (LanceDB, SQLite) и временные медиа (аудио, фото из TG) живут в Linux `/home/vladislav/projects/agent_project/`.
- ТОЛЬКО финальные `.md` файлы пишутся в Windows `/mnt/c/Users/.../ObsidianVault/`.

## Дерево файлов
/home/vladislav/projects/agent_project/
├── 📄 Start_AI.bat             # (На Windows) Запускает WSL и вызывает run.sh
├── 📄 run.sh                   # (В Linux) Убивает зомби-процессы, линкует драйверы CUDA, запускает ядро
├── 📄 test_run.py              # Точка входа в приложение
├── 📄 requirements.txt
├── 📄 .env 
│
├── 📁 docs/
│   ├── AI_CONTEXT.md           # Контекст для LLM
│   ├── ARCHITECTURE.md         # Структура (этот файл)
│   └── ROADMAP.md              # План разработки
│
├── 📁 src/
│   │
│   ├── 📁 core/                 # Управляющий узел (Главный дирижер)
│   │   ├── orchestrator.py      # 🔴 ТОЛЬКО ОН вызывает сервисы. Каскадная обработка пайплайнов.
│   │   └── config.py            # Токены, пути (BASE_DIR, VAULT_DIR), константы
│   │
│   ├── 📁 infrastructure/       # LEVEL 1: Железо и Транспорт
│   │   ├── event_bus.py         # Шина и Typed Events (@dataclass)
│   │   ├── task_queue.py        # Асинхронная очередь задач
│   │   ├── vram_scheduler.py    # Планировщик VRAM и Семафор (asyncio.Semaphore(1))
│   │   └── telemetry.py         # Observability (Тайминги, загрузка VRAM, декораторы)
│   │
│   ├── 📁 models/               # Управление "мозгами"
│   │   ├── registry.py          # MODEL_REGISTRY (vram_required для hermes, whisper, llama-vision)
│   │   └── loaders.py           # Физическая загрузка весов в GPU
│   │
│   ├── 📁 cognitive/            # LEVEL 2: AI-навыки (Stateless Services)
│   │   ├── 📁 memory/           # (В разработке)
│   │   │   ├── conversation.py  # Краткосрочная память
│   │   │   └── semantic.py      # Долгосрочная память (LanceDB)
│   │   ├── llm_service.py       # Генерация текста и Vision API (Ollama + base64 + Pillow)
│   │   └── stt_service.py       # Транскрибация (Faster-Whisper)
│   │
│   ├── 📁 agents/               # LEVEL 3: Бизнес-логика (Поведение)
│   │   ├── clerk_agent.py       # (В разработке) Сортировщик 00_Inbox
│   │   └── obsidian_writer.py   # Очистка имен файлов и атомарная запись в базу (Windows)
│   │
│   ├── 📁 interfaces/           # Внешний мир
│   │   └── telegram/
│   │       ├── bot.py           # Aiogram setup
│   │       └── handlers.py      # Ловит text/voice/photo -> публикует в EventBus
│   │
│   ├── 📁 parsers/              # (В разработке) Извлекатели текста
│   │   ├── pdf_parser.py
│   │   └── docx_parser.py
│   │
│   └── 📁 storage/              # Физическая работа с диском
│       ├── vector_store.py      # (В разработке) LanceDB
│       └── sqlite_manager.py    # (В разработке) Сохранение стейтов
└── 📁 data/                     # Временные файлы и БД (Игнорируется Git)