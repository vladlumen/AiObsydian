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
├── 📄 bot.py                   # Основной файл бота (aiogram)
├── 📄 brain.py                 # Основной модуль ИИ (планируется?)
├── 📄 clerk.py                 # Агент сортировщика (планируется?)
├── 📄 config.py                # Токены, пути (BASE_DIR, VAULT_DIR), константы (дублирует src/core/config.py?)
├── 📄 db_init.py               # Инициализация базы данных
├── 📄 logger.py                # Настройка логирования
├── 📄 run_sync.py              # Запуск синхронизации Obsidian
├── 📄 start_agent.sh           # Скрипт запуска агента
├── 📄 state.db                 # База данных SQLite для стейтов
├── 📄 test_memory.py           # Тесты памяти
├── 📁 tools/                   # Вспомогательные скрипты
├── 📁 docs/
│   ├── 📄 AI_CONTEXT.md           # Контекст для LLM
│   ├── 📄 ARCHITECTURE.md         # Структура (этот файл)
│   └── 📄 ROADMAP.md              # План разработки
├── 📁 src/
│   ├── 📁 agents/                 # Агенты (поведение)
│   │   ├── 📄 clerk_agent.py       # Сортировщик 00_Inbox
│   │   ├── 📄 obsidian_writer.py   # Очистка имен файлов и атомарная запись в базу (Windows)
│   │   └── 📁 parsers/             # Извлекатели текста
│   │       ├── 📄 url_parser.py    # Веб-страницы
│   │       ├── 📄 pdf_parser.py    # PDF-файлы
│   │       └── 📄 docx_parser.py   # DOCX-файлы
│   ├── 📁 cognitive/              # LEVEL 2: AI-навыки (Stateless Services)
│   │   ├── 📁 memory/           # Модуль памяти
│   │   │   ├── 📄 conversation.py  # Краткосрочная память (планируется)
│   │   │   └── 📄 semantic.py      # Долгосрочная память (LanceDB) — активно используется
│   │   ├── 📄 llm_service.py       # Генерация текста (Ollama)
│   │   ├── 📄 vision_service.py    # Анализ изображений (Ollama Vision) — планируется
│   │   └── 📄 stt_service.py       # Транскрибация (Faster-Whisper) — активно используется
│   ├── 📁 core/                   # Управляющий узел (Главный дирижер)
│   │   ├── 📄 orchestrator.py      # 🔴 ТОЛЬКО ОН вызывает сервисы. Каскадная обработка пайплайнов.
│   │   └── 📄 config.py            # Токены, пути (BASE_DIR, VAULT_DIR), константы
│   │
│   ├── 📁 infrastructure/       # LEVEL 1: Железо и Транспорт
│   │   ├── 📄 event_bus.py         # Шина и Typed Events (@dataclass)
│   │   ├── 📄 task_queue.py        # Асинхронная очередь задач
│   │   ├── 📄 vram_scheduler.py    # Планировщик VRAM и Семафор (asyncio.Semaphore(1))
│   │   └── 📄 telemetry.py         # Observability (Тайминги, загрузка VRAM, декораторы)
│   │
│   ├── 📁 models/               # Управление "мозгами"
│   │   ├── 📄 registry.py          # MODEL_REGISTRY (vram_required для hermes, whisper, llama-vision)
│   │   └── 📄 loaders.py           # Физическая загрузка весов в GPU
│   │
│   ├── 📁 interfaces/           # Внешний мир
│   │   └── 📁 telegram/
│   │       ├── 📄 bot.py           # Aiogram setup
│   │       └── 📄 handlers.py      # Ловит text/voice/photo -> публикует в EventBus
│   │
│   └── 📁 storage/              # Физическая работа с диском
│       ├── 📄 vector_store.py      # LanceDB wrapper (активно используется)
│       └── 📄 sqlite_manager.py    # Сохранение стейтов (планируется)
└── 📁 data/                     # Временные файлы и БД (Игнорируется Git)