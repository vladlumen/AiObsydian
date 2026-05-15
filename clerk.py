import os
import shutil
from pathlib import Path
from ollama import AsyncClient
from config import BASE_VAULT_PATH, INBOX_PATH

CATEGORIES = ["work", "sport", "trips", "task", "diary"]

async def analyze_note(content: str) -> dict:
    """Анализирует текст заметки и возвращает решение."""
    prompt = f"""
    Проанализируй текст заметки и выбери одно из действий:
    1. Если текст подходит под существующие категории {CATEGORIES}, верни ТОЛЬКО имя категории.
    2. Если текст НЕ подходит, но есть четкая новая тема, верни: NEW: имя_новой_папки (на английском, в нижнем регистре, без пробелов).
    3. Если тема размыта, верни: INBOX
    
    Ответ должен состоять строго из одного слова или связки 'NEW: имя'. Без точек и объяснений.
    
    Текст:
    {content}
    """
    
    client = AsyncClient()
    response = await client.chat(model='hermes3:8b', messages=[{'role': 'user', 'content': prompt}])
    result = response['message']['content'].strip().lower()
    
    if result in CATEGORIES:
        return {"action": "move", "category": result}
    elif result.startswith("new:"):
        new_cat = result.replace("new:", "").strip()
        return {"action": "suggest", "category": new_cat}
    else:
        return {"action": "skip", "category": "00_Inbox"}