# 🏛️ Архитектура и Структура Проекта (v3.2 — Июнь 2026)

## 📌 Обзор системы
Проект представляет собой высокопроизводительную агентную платформу на базе LLM, предназначенную для автоматизации работы с базами знаний (Obsidian) и обработки мультимольного контента (текст, PDF, видео, аудио).

**Среда выполнения:** Изолированный Linux-контейнер (WSL2)
**Путь к проекту:** `/home/vladislav/projects/agent_project/`
**Интеграция:** Синхронизация с Windows/Obsidian через мост WSL.

## 🛠 Стек технологий
* **LLM Core:** **Hermes 3 (8b)** & **Llama 3.2 Vision** (через Olllama).
* **RAG & Memory:** 
    * **L1 (Exact):** SQLite (`cache_l1.db`) — быстрый поиск по `hash(query)`.
    * **L2 (Semantic):** **LanceDB** (`semantic_memory.lance`) — векторный поиск по эмбеддингам.
* **Audio/STT:** **Faster-Whisper (large-v3)**.
* **Embeddings:** **Nomic Embed Text**.
* **Parsing:** Python-стек (PyMM, python-docx, BeautifulSoup, OpenCV).
* **Infrastructure:** Python-based orchestrator, VRAM Scheduler, Task Queue.

## 🚀 Ключевые механизмы
* **Многоуровневое кэширование (L1/L2/L3):** От прямого совпадения хеша до полного цикла RAG.
* **VRAM Scheduler:** Управление ресурсами GPU (RTX 3090) для предотвращения конфликтов при одновременном использовании тяжелых моделей.
* **Task Queue:** Очередь задач для управления нагрузкой и обеспечения детерминизма.
* **Data Cleanup:** Автоматический жизненный цикл временных медиа в `data/temp_media/`.

## 📁 Полная структура проекта
```text
/home/vladislav/projects/agent_project/
├── 📄 run.sh, run_sync.py, run_auto_tests.py, run_benchmark_test.py, start_agent.sh, test_memory.py  # Запуск и тесты
├── 📄 requirements.txt, .env, state.db                                                            # Окружение и глобальное состояние
├── 📁 data/                    # Изменяемые данные (Игнорируются Git)
│   ├── 📁 lancedb_store/       # LanceDB: semantic_memory, obsidian_notes, cache_l1
│   ├── 📁 temp_media/          # Временные медиа (аудио, фото, видео) с авто-очисткой
│   └── 📄 state.db             # Реестр состояний и хэшей (SQLite)
├── 📁 docs/                    # Документация (Architecture, Roadmap, Context)
├── 📁 tools/                   # Вспомогательные утилиты (deduplication, routing, etc.)
│   ├── 📄 deduplicator.py
│   ├── 📄 reliability.py
│   ├── 📄 router.py
│   └── 📄 fs_tools.py
├── 📁 src/                     # Исходный код ядра (Clean Architecture)
│   ├── 📁 agents/              # Агенты и фоновые воркеры бизнес-логики
│   │   ├── 📄 clerk_agent.py    # Сортировщик и анализатор входящих данных
│   │   ├── 📄 document_agent.py # Агент парсинга бинарных документов
│   │   ├── 📄 note_generator_agent.py # Агент генерации заметок для Obsidian
│   │   ├── 📄 rag_agent.py      # Агент семантического поиска и RAG
│   │   ├── 📄 obsidian_writer.py # Мост записи заметок в Windows-диск
│   │   ├── 📄 vision_agent.py   # Агент анализа изображений и OCR
│   │   ├── 📄 voice_agent.py    # Агент обработки голоса и STST
│   │   └── 📁 parsers/          # Парсеры извлечения контента
│   │       ├── 📄 document_parser.py # Диспетчер маршрутирования документов
│   │       ├── 📄 pdf_parser.py      # Парсинг PDF через pypdf
│   │       ├── 📄 md_chunker.py      # Иерархический парсер Markdown
│   │       ├── 📄 url_parser.py      # Сканирование веб-страниц
│   │       └── 📄 video_parser.py    # Парсинг метаданных и субтитров видео
│   ├── 📁 cognitive/           # Когнитивный слой (Stateless Сервисы)
│   │   ├── 📄 llm_service.py    # Инференс текста через API (Hermes/Llama)
│   │   ├── 📄 stt_service.py    # Распознавание речи через faster-whisper
│   │   ├── 📄 vision_service.py # Обработка изображений через Llama Vision
│   │   └── 📁 memory/           # Управление долгосрочной памятью
│   │       ├── 📄 conversation.py # Краткосрочная история сессии
│   │       └── 📄 semantic.py     # RAG-интеграция и LanceDB (BM25 + Vector)
│   ├── 📁 core/                # Управляющий слой (Orchestration)
│   │   ├── 📄 orchestrator.py   # Главный дирижер событий и связей сервисов
│   │   ├── 📄 config.py         # Центральный конфигуратор путей и моделей
│   │   ├── 📄 prompt_loader.py  # Безокругная загрузка системных промптов
│   │   └── 📄 prompts.yaml      # База системных инструкций
│   ├── 📁 infrastructure/      # Системные сервисы (I/O, Monitoring)
│   │   ├── 📄 event_bus.py      # Асинхронная шина событий (Pub/async)
│   │   ├── 📄 task_queue.py     # Очередь задач и управление очисткой
│   │   ├── 📄 vram_scheduler.py # Менеджер загрузки моделей в GPU (RTX 3090)
│   │   ├── 📄 cache_manager.py  # Управление L1/L2 кэшами
│   │   ├── 📄 logger.py         # Централизованное логирование
│   │   └── 📄 telemetry.py      # Мониториting утилизации GPU и инференса
│   ├── 📁 interfaces/          # Интерфейсы взаимодействия
│   │   └── 📁 telegram/         # Telegram Bot (bot.py, handlers.py, keyboards.py)
│   ├── 📁 models/              # Режим и загрузчики моделей (registry, loaders)
│   └── 📁 storage/             # Низкоуровневые интерфейсы БД
│       ├── 📄 sqlite_manager.py
│       └── 📄 vector_store.py
```
