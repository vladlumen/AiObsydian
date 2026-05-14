import os
import json
import ollama
import re
from datetime import datetime
from tools.router import TaskRouter
from tools.deduplicator import Deduplicator
from tools.fs_tools import atomic_write
from tools.vector_storage import vector_mem
from logger import agent_logger

NOTES_PATH = "/mnt/c/Users/vladislav/Documents/ObsidianVault"
OLLAMA_URL = "http://127.0.0.1:11434"
client = ollama.Client(host=OLLAMA_URL)

# На твоей RTX 3090 модель gemma2:27b будет работать идеально. 
# Если еще не скачал, напиши в терминале: ollama pull gemma2:27b
MODEL = "hermes3:8b" 

class AgentBrain:
    def process_query(self, user_query: str):
        intent = TaskRouter.classify_intent(user_query)
        agent_logger.info("Brain", f"Принято решение: {intent}")

        if intent == "SEARCH":
            return self._handle_search(user_query)
        elif intent == "WRITE":
            return self._handle_write(user_query)
        elif intent == "APPEND":
            return self._handle_append(user_query)
        
        return "Я понял запрос, но не определил действие."

    def _handle_search(self, user_query: str):
        results = vector_mem.search(user_query, limit=3)
        if not results: return "В архивах Ideaverse ничего не найдено."
        
        out = "🔍 Вот что я вспомнил:\n\n"
        for r in results:
            title = os.path.basename(r['path']).replace(".md", "")
            out += f"📍 [[{title}]]\n{r['text'][:200]}...\n\n"
        return out

    def _handle_write(self, user_query: str):
        agent_logger.info("Brain", "Этап 1: Анализ и структурирование...")
        
        # Поиск контекста для связей
        context_files = []
        try:
            res = vector_mem.search(user_query, limit=5)
            # Берем только уникальные и не пустые названия
            context_files = list(set([os.path.basename(r['path']).replace(".md", "") for r in res]))
        except: pass

        now = datetime.now().strftime("%Y-%m-%d %H:%M")

        prompt = f"""Ты — эксперт по PKM и методу LYT. Пиши СТРОГО на русском.
        Запрос пользователя: "{user_query}"
        
        Твоя задача — выделить суть и вернуть JSON:
        - title: (2-3 слова, главная тема)
        - summary: (суть одной фразой)
        - thoughts: (развернутый текст заметки, 2-3 абзаца)
        - tags: [минимум 3 тега]
        - entities: [важные имена, места или понятия]
        - related: [выбери из существующих: {", ".join(context_files) if context_files else "нет"}]
        """

        try:
            response = client.generate(model=MODEL, prompt=prompt, format="json", options={"temperature": 0.2})
            data = json.loads(response['response'])

            # --- ПОСТ-ОБРАБОТКА (Чистим "косяки" ИИ) ---
            # 1. Название файла без мусора
            title_raw = data.get("title", "Новая_заметка")
            title_clean = re.sub(r'[^\w\s-]', '', title_raw).strip().replace(" ", "_")[:40]
            
            # 2. ТЕГИ: Заменяем пробелы на подчеркивания (чтобы Obsidian их понимал)
            tags_list = data.get("tags", [])
            clean_tags = [t.strip().replace(" ", "_") for t in tags_list if t.strip()]
            
            # 3. СУЩНОСТИ: Убираем пустые или однобуквенные связи
            entities = [e.strip() for e in data.get("entities", []) if len(e.strip()) > 1]
            related = [r.strip() for r in data.get("related", []) if r in context_files]

            # --- СБОРКА ЗАМЕТКИ (Python Template) ---
            content = f"""---
type: knowledge_note
status: seed
ai_generated: true
date: {now}
tags: {clean_tags}
---

# {title_raw}

> [!abstract] AI Summary
> {data.get('summary', 'Резюме не сформировано.')}

## 📌 Ключевые тезисы
- {data.get('summary', '')}
- Темы: {", ".join(['[['+e+']]' for e in entities]) if entities else "Общие концепции"}

## 🏙️ Детальный обзор
{data.get('thoughts', 'Контент отсутствует.')}

## 🔍 Сущности (Things)
- **Концепции:** {", ".join(['[['+e+']]' for e in entities]) if entities else "Не выделены"}
- **Связанные файлы:** {", ".join(['[['+r+']]' for r in related]) if related else "Связи не найдены"}

## Ссылки
- [[Центральный_MOC]]
- [[{now.split()[0]}]]
"""
            # Атомарная запись
            atomic_write(os.path.join(NOTES_PATH, f"{title_clean}.md"), content)
            
            # Формируем ответ для Telegram
            msg = f"✅ Заметка [[{title_clean}]] создана."
            if related:
                msg += f"\n🔗 Установлены связи с: {', '.join(['[['+r+']]' for r in related])}"
            
            return msg

        except Exception as e:
            agent_logger.error("Brain", f"Ошибка WRITE: {e}")
            return "❌ Произошла ошибка при сборке заметки. Попробуй еще раз."

    def _handle_append(self, user_query: str):
        agent_logger.info("Brain", "Поиск заметки для дополнения...")
        try:
            results = vector_mem.search(user_query, limit=1)
            if not results: return "❌ Не нашел подходящую заметку для дополнения."
            
            path = results[0]['path']
            title = os.path.basename(path).replace(".md", "")
            
            with open(path, 'r', encoding='utf-8') as f:
                old_text = f.read()

            now = datetime.now().strftime("%Y-%m-%d %H:%M")
            prompt = f"Пользователь хочет добавить это: '{user_query}' в контекст темы '{title}'. Напиши только текст дополнения (1-2 абзаца) на русском."
            
            res = client.generate(model=MODEL, prompt=prompt)
            new_block = f"\n\n### Дополнение ({now})\n{res['response'].strip()}"
            
            atomic_write(path, old_text + new_block)
            return f"✅ Информация добавлена в заметку [[{title}]]."
        except Exception as e:
            agent_logger.error("Brain", f"Ошибка APPEND: {e}")
            return "❌ Ошибка при дозаписи."

agent_brain = AgentBrain()
