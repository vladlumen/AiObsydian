# 🗺️ Роадмап разработки Personal AI Assistant (v2.3 — Май 2026)

**Текущий статус:** Ядро v2.3 успешно стабилизировано. Сквозные автотесты (`run_auto_tests.py`) на реальных медиа-фикстурах проходят без ошибок. Память GPU под контролем, диск автоматически очищается от временных файлов.

---

## 🏗️ Phase 1: Foundation (Инфраструктура) — [ВЫПОЛНЕНО]
- [x] Создать `event_bus.py` (Шина сообщений + Typed Events: Text, Photo, Voice, Document).
- [x] Оптимизировать утилизацию VRAM: перевод `task_queue.py` в строго последовательный однопоточный режим.
- [x] Создать `orchestrator.py` (Центральная диспетчеризация без циклических импортов через ленивую загрузку).
- [x] Написать native bash/batch скрипты очистки зомби-процессов перед стартом.

## 🧠 Phase 2: Cognitive Layer (Органы чувств) — [ВЫПОЛНЕНО]
- [x] Интеграция `stt_service.py` (`faster-whisper` large-v3 с инференсом на CPU/GPU, фикс импортов объекта `stt`).
- [x] Миграция на `hermes3:8b` через плоский эндпоинт `/api/generate` (стабильный MD-формат за 10–12 секунд).
- [x] Интеграция `vision_service.py` (`llama3.2-vision` для точного OCR кода и скриншотов).
- [x] Подключение Telegram: `handlers.py` (прием voice/text/photo).
- [x] Добавить `telemetry.py` (замер времени ответа и утилизации VRAM).

## 💾 Phase 3: The "Second Brain" (Хранилище и Память) — [ВЫПОЛНЕНО]
- [x] Реализовать `obsidian_writer.py` (атомарная запись `.md` по WSL-мосту в `/mnt/c/...`).
- [x] Создать `storage/vector_store.py` (локальная база LanceDB в Linux).
- [x] Создать `cognitive/memory/semantic.py` (индексация векторов через Nomic Embed).
- [x] Создать `cognitive/memory/conversation.py` (краткосрочная память сессии).

## 🤖 Phase 4: Autonomous Behaviors (Агенты и Парсеры) — [ВЫПОЛНЕНО]
- [x] Написать каркас `agents/clerk_agent.py` (сортировщик входящего `00_Inbox`).
- [x] Реализовать `agents/sync_worker.py` и `run_sync.py` (инкрементальный трекер Obsidian на базе SQLite, фикс SQL-синтаксиса `3 columns`).
- [x] Реализовать и протестировать парсеры документов: `parsers/pdf_parser.py` и `parsers/docx_parser.py`.
- [x] Реализовать специализированные парсеры контента: `parsers/url_parser.py` и `parsers/video_parser.py`.

## 🧼 Phase 5: Polish & Observability (Стабилизация и Релиз) — [ВЫПОЛНЕНО]
- [x] Рефакторинг промптов: вынос в изолированный `src/core/prompts.yaml` через `prompt_loader.py` (без ломающего `.format()`).
- [x] Создать автоматические пайплайны сквозного тестирования: `run_auto_tests.py` и бенчмарки.
- [x] Написать автоматическую зачистку временных медиафайлов из папки `data/temp_media/` через воркер `TaskQueue` (блоки `finally` + метод `clear_temp_media`).
- [x] Устранить все критические `ImportError` (унификация кастомного `logger` во всех модулях ядра).

---

## 🚀 В СЛЕДУЮЩИХ СПРИНТАХ: Phase 6 (Khoj-Модернизация RAG)
- [ ] **Hierarchical Chunking:** Переписать парсеры заметок на разбиение текста по заголовкам `##` вместо индексации файлов целиком.
- [ ] **Гибридный поиск:** Включить встроенный полнотекстовый поиск (FTS/BM25) в LanceDB для точного нахождения логов ошибок и технического кода.