# Архитектура и Структура Проекта (v2.2)

**Правила Хранения Данных:**
- ВЕСЬ код, базы данных (LanceDB, SQLite) и временные медиа (аудио, фото из TG) живут в Linux `/home/vladislav/projects/agent_project/`.
- ТОЛЬКО финальные `.md` файлы пишутся в Windows `/mnt/c/Users/.../ObsidianVault/`.

## Дерево файлов
/home/vladislav/projects/agent_project/
├── 📄 run.sh                   # (В Linux) Убивает зомби-процессы, линкует драйверы CUDA, запускает ядро
├── 📄 test_run.py              # Точка входа в приложение / тестовый прогон
├── 📄 run_auto_tests.py        # Автоматические интеграционные тесты
├── 📄 run_sync.py              # Запуск синхронизации Obsidian
├── 📄 start_agent.sh           # Скрипт запуска агента
├── 📄 test_memory.py           # Тесты памяти
├── 📄 requirements.txt
├── 📄 .env 
├── 📄 state.db                 # База данных SQLite для стейтов (локально)
├── 📁 _old_drafts/             # Черновики и архивные модули (brain.py)
├── 📁 data/                    # Временные файлы и БД (Игнорируется Git)
│   ├── 📁 lancedb_store/       # Хранилище векторной базы LanceDB
│   └── 📁 temp_media/          # Загруженные фото и аудио из TG
├── 📁 tools/                   # Вспомогательные скрипты автоматизации
├── 📁 tests/                   # Тесты и фикстуры
├── 📁 docs/                    # Документация проекта
└── 📁 src/                     # Исходный код (Clean Architecture)
    ├── 📁 agents/                 # Агенты (Поведение)
    │   ├── 📄 clerk_agent.py       # Сортировщик входящих заметок
    │   ├── 📄 obsidian_writer.py   # Запись атомарных заметок в Obsidian
    │   └── 📁 parsers/             # Извлекатели текста из медиафайлов
    │       ├── 📄 document_parser.py
    │       ├── 📄 docx_parser.py
    │       ├── 📄 pdf_parser.py
    │       ├── 📄 url_parser.py    
    │       └── 📄 video_parser.py  
    ├── 📁 cognitive/              # AI-навыки (Stateless Services)
    │   ├── 📄 llm_service.py       # Текст (Ollama)
    │   ├── 📄 stt_service.py       # Аудио в текст (Faster-Whisper)
    │   ├── 📄 vision_service.py    # Зрение (Ollama Vision)
    │   └── 📁 memory/              # Модуль памяти агента
    │       ├── 📄 conversation.py  # Краткосрочный контекст
    │       └── 📄 semantic.py      # Долгосрочная семантическая память
    ├── 📁 core/                   # Управляющий узел (Оркестрация)
    │   ├── 📄 orchestrator.py      # Главный дирижер пайплайнов
    │   ├── 📄 config.py            # Единый конфиг проекта (Токены, пути)
    │   ├── 📄 prompt_loader.py     # Загрузчик системных промптов
    │   └── 📄 prompts.yaml         # Промпты для LLM
    ├── 📁 infrastructure/         # Низкоуровневые системные сервисы
    │   ├── 📄 event_bus.py         # Асинхронная шина событий
    │   ├── 📄 logger.py            # Централизованное логирование
    │   ├── 📄 task_queue.py        # Очередь задач
    │   ├── 📄 telemetry.py         # Метрики (Загрузка VRAM, тайминги)
    │   └── 📄 vram_scheduler.py    # Распределитель видеопамяти для моделей
    ├── 📁 interfaces/             # Внешние интерфейсы ввода-вывода
    │   └── 📁 telegram/
    │       ├── 📄 bot.py           # Инициализация Aiogram
    │       ├── 📄 handlers.py      # Обработчики сообщений (В шину событий)
    │       └── 📄 keyboards.py     # Инлайн-меню
    ├── 📁 models/                 # Управление ИИ-моделями
    │   ├── 📄 registry.py          # Реестр требований к памяти
    │   └── 📄 loaders.py           # Загрузка/выгрузка весов в GPU
    └── 📁 storage/                # Работа с физическими базами данных
        ├── 📄 db_init.py           # Первичная инициализация таблиц
        ├── 📄 sqlite_manager.py    # Менеджер состояний процессов
        └── 📄 vector_store.py      # Коннектор к LanceDB