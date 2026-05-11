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

class AgentBrain:
    def process_query(self, user_query: str):
        intent = TaskRouter.classify_intent(user_query)
        agent_logger.info("Brain", f"Принято решение: {intent}")

        if intent == "SEARCH":
            results = vector_mem.search(user_query)
            if not results: return "В базе знаний ничего не нашлось."
            return f"Вот что я нашел:\n\n{results[0]['text']}"

        elif intent == "WRITE":
            agent_logger.info("Brain", "Поиск контекста для связей...")
            
            related_links = []
            try:
                # Ищем похожие заметки для создания [[связей]]
                search_results = vector_mem.search(user_query, limit=3)
                for res in search_results:
                    # Извлекаем чистое имя файла из пути
                    fname = os.path.basename(res['path']).replace(".md", "")
                    related_links.append(f"[[{fname}]]")
            except Exception as e:
                agent_logger.warning("Brain", f"Связи не найдены: {e}")

            agent_logger.info("Brain", "Генерация атомарной заметки...")
            now = datetime.now().strftime("%Y-%m-%d %H:%M")

            prompt = f"""Ты — ИИ-ассистент, создающий заметки для Obsidian. 
            ПИШИ СТРОГО НА РУССКОМ ЯЗЫКЕ (включая заголовок и теги).
            
            ЗАПРОС: "{user_query}"
            СВЯЗИ: {", ".join(related_links)}

            ШАБЛОН ВЫХОДА (СТРОГО):
            ---
            date: {now}
            tags: [минимум 3 тега на русском]
            source: "Telegram-Bot"
            ---
            # [Заголовок на русском]

            [Краткое описание идеи в 2-3 предложениях]

            ## Детали
            - [Первый пункт]
            - [Второй пункт]

            ## Связи
            {", ".join(related_links) if related_links else "Пока нет связей."}

            ВЕРНИ JSON:
            {{"title": "Название_на_русском", "content": "Весь текст по шаблону выше"}}"""
            try:
                response = client.generate(model="hermes3:8b", prompt=prompt, format="json")
                data = json.loads(response['response'])

                # Чистим заголовок от даты и мусора
                raw_title = data.get("title", "New_Note")
                clean_title = re.sub(r'\d{4}-\d{2}-\d{2}.*', '', raw_title) # Убираем дату если она есть
                clean_title = re.sub(r'[^\w\s-]', '', clean_title).strip().replace(" ", "_")[:30]
                
                content = data.get("content", "").strip()
                # Гарантируем, что ``` не попадут в файл
                content = re.sub(r'^```[a-z]*\n|```$', '', content, flags=re.MULTILINE)

                full_path = os.path.join(NOTES_PATH, f"{clean_title}.md")
                atomic_write(full_path, content)
                
                msg = f"✅ Заметка: [[{clean_title}]]"
                if related_links:
                    msg += f"\n🔗 Связано с: {', '.join(related_links)}"
                return msg

            except Exception as e:
                agent_logger.error("Brain", f"Ошибка: {e}")
                return "❌ Ошибка при создании. Попробуй еще раз."

        return "Запрос принят."

agent_brain = AgentBrain()
