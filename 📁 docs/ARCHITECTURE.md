/home/vladislav/projects/agent_project/brain.py 
├── 📁 docs/
│   ├── AI_CONTEXT.md
│   ├── ARCHITECTURE.md
│   └── ROADMAP.md               # План: 1. Инфраструктура -> 2. Ядро -> 3. Агенты
│
├── 📁 src/
│   │
│   ├── 📁 core/                 # Управляющий узел (Главный дирижер)
│   │   ├── orchestrator.py      # 🔴 ТОЛЬКО ОН вызывает сервисы. Никаких прямых связей между сервисами!
│   │   └── config.py            # Токены, пути, константы
│   │
│   ├── 📁 infrastructure/       # LEVEL 1: Железо и Транспорт
│   │   ├── event_bus.py         # Шина и Typed Events (@dataclass VoiceReceivedEvent)
│   │   ├── task_queue.py        # Асинхронная очередь задач (asyncio.Queue)
│   │   ├── vram_scheduler.py    # Lifecycle (LOADING, READY) и Семафор (asyncio.Semaphore(1))
│   │   └── telemetry.py         # Observability (Тайминги, загрузка VRAM, логи)
│   │
│   ├── 📁 models/               # Управление "мозгами"
│   │   ├── registry.py          # MODEL_REGISTRY (vram_required, backend, type)
│   │   └── loaders.py           # Физическая загрузка весов в GPU
│   │
│   ├── 📁 cognitive/            # LEVEL 2: AI-навыки и Память (Stateless Services)
│   │   ├── 📁 memory/           # 
│   │   │   ├── conversation.py  # Краткосрочная память (окно контекста)
│   │   │   └── semantic.py      # Долгосрочная память (векторный поиск)
│   │   ├── llm_service.py       # Генерация текста
│   │   ├── stt_service.py       # Транскрибация
│   │   └── vision_service.py    # Анализ картинок
│   │
│   ├── 📁 agents/               # LEVEL 3: Бизнес-логика (Поведение)
│   │   ├── clerk_agent.py       # Сортировщик 00_Inbox
│   │   └── obsidian_writer.py   # Форматирование и атомарная запись в базу
│   │
│   ├── 📁 interfaces/           # Внешний мир
│   │   └── telegram/
│   │       ├── bot.py           # Запуск поллинга
│   │       └── handlers.py      # Принимает войс -> публикует VoiceReceivedEvent
│   │
│   ├── 📁 parsers/              # "Тупые" извлекатели текста
│   │   ├── pdf_parser.py
│   │   └── docx_parser.py
│   │
│   └── 📁 storage/              # Физическая работа с диском
│       ├── vector_store.py      # LanceDB (вызывается из semantic.py)
│       └── sqlite_manager.py    # Сохранение стейтов
│
├── 📁 data/                     # Игнорируется Git
├── requirements.txt
└── .env