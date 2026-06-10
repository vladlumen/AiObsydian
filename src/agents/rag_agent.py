from src.infrastructure.logger import logger
from src.infrastructure.vram_scheduler import vram_manager
from src.infrastructure.telemetry import telemetry
from src.infrastructure.event_bus import TextReceivedEvent
from src.core import config

class RAGAgent:
    def __init__(self):
        pass

    async def process_query(self, event: TextReceivedEvent):
        """Выполнение гибридного RAG-поиска и генерация ответа через Hermes 3."""
        query = event.text.strip().lstrip('?').rstrip('?').strip()
        if not query:
            return

        from src.cognitive.memory.semantic import memory
        from src.cognitive.llm_service import llm
        from src.interfaces.telegram.bot import bot

        try:
            await bot.send_chat_action(chat_id=event.user_id, action="typing")
            
            # --- 0. CHECK CACHE (L1/L2) ---
            cached_response = await memory.get_cached_response(query)
            if cached_response:
                await bot.send_message(chat_id=event.user_id, text=f"✨ **[Cache Hit]**\n\n{cached_response}")
                return

            # 1. Сбор контекста
            formatted_context_chunks = []
            async with telemetry.track(f"RAG_Retrieve_Context_{event.user_id}"):
                chunks = await memory.retrieve_context(query, limit=3)

                for chunk in chunks:
                    meta = chunk.get("metadata") or {}
                    file_path = chunk.get("file_path", "Unknown")
                    header_path = chunk.get("header_path", "")
                    text_content = chunk.get("text", "").strip()

                    if not text_content:
                        continue

                    # Извлекаем оригинальное имя файла без путей
                    import os
                    clean_filename = os.path.basename(file_path)
                    
                    header_info = f" -> {header_path}" if header_path else ""
                    
                    # Инъецируем имя файла прямо в текст контекста, чтобы поиск по названию работал железно
                    formatted_chunk = (
                        f"--- Заметка: {clean_filename}{header_info} ---\n"
                        f"{text_content}"
                    )
                    formatted_context_chunks.append(formatted_chunk)
            
            context_block = "\n\n".join(formatted_context_chunks)

            # 2. Системный промпт без лишней агрессии (Hermes разрешено думать и сопоставлять)
            system_instruction = (
                "Ты — опытный персональный ассистент. Твоя задача — ответить на вопрос пользователя, "
                "используя предоставленный контекст из базы знаний Obsidian внутри тегов <context>.\n"
                "Отвечай кратко, емко, структурированно и строго по делу.\n"
                "Если контекст содержит ответ или связан с темой вопроса, перескажи ключевые факты.\n"
                "Если контекст абсолютно не релевантен и не содержит никаких намеков на ответ, "
                "ответь: 'Данных в базе знаний нет'.\n"
                "Строго используй Obsidian Markdown для оформления ответа."
            )

            if context_block:
                full_prompt = f"<context>\n{context_block}\n</context>\n\nВопрос: {query}"
            else:
                full_prompt = query

            # 3. Инференс
            response_text = ""
            async with telemetry.track(f"RAG_LLM_Inference_{event.user_id}"):
                async with vram_manager.inference_lock:
                    await vram_manager.request_model(config.CURRENT_LLM_MODEL)
                    try:
                        response_text = await llm.generate_text(
                            full_prompt, 
                            system_prompt=system_instruction, 
                            model=config.CURRENT_LLM_MODEL
                        )
                    finally:
                        await vram_manager.unload_model(config.CURRENT_LLM_MODEL)

            # 4. Отправка и сохранение
            if response_text and response_text.strip():
                await bot.send_message(chat_id=event.user_id, text=response_text)
                # Сохраняем в кэш для следующего раза
                await memory.save_to_cache(query, response_text)
            else:
                await bot.send_message(chat_id=event.user_id, text="⚠️ Локальная модель вернула пустой ответ.")
                
        except Exception as e:
            print(f"[RAGAgent ❌ Ошибка пайплайна]: {repr(e)}")
            try:
                await bot.send_message(chat_id=event.user_id, text="❌ Ошибка при обработке запроса.")
            except:
                pass

rag_agent = RAGAgent()
