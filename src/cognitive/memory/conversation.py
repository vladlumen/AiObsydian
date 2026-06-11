import logging
from typing import List, Tuple
from src.storage.sqlite_manager import SQLiteManager

logger = logging.getLogger("ConversationMemory")

class ConversationMemory:
    def __init__(self, db_manager: SQLiteManager):
        """
        Инициализация управления рабочей памятью OpenViking.
        :param db_manager: Инстанс инициализированного SQLiteManager
        """
        self.db = db_manager

    def append_message(self, chat_id: int, role: str, content: str):
        """
        Добавляет новое сообщение (user/assistant) в оперативную память сессии (L2).
        """
        if not content:
            return
        self.db.add_session_message(chat_id, role, content.strip())
        logger.debug(f"[Memory L2] Добавлено сообщение {role} в чат {chat_id}")

    def get_active_context(self, chat_id: int, max_tokens: int = 3000) -> str:
        """
        Собирает виртуальное окно контекста (Working Memory) на базе OpenViking-pattern.
        Гарантирует включение L1 Overview + заполняет остаток бюджета свежими сообщениями L2.
        
        :param chat_id: ID чата Telegram
        :param max_tokens: Максимальный размер выделенного бюджета токенов для истории
        :return: Отформатированная строка контекста для промпта
        """
        # Приближенный расчет символьного бюджета (1 токен ~ 2.5 символа)
        max_chars = int(max_tokens * 2.5)
        
        # 1. Извлекаем долгосрочный обзор сессии (L1)
        _, l1_overview = self.db.get_session_abstracts(chat_id)
        
        final_sections = []
        current_length = 0
        
        # Базово формируем заголовок L1, если он есть
        l1_string = ""
        if l1_overview and l1_overview.strip():
            l1_string = f"=== Краткий обзор предыдущего разговора (L1 Overview) ===\n{l1_overview.strip()}\n\n"
            current_length += len(l1_string)

        # Вычисляем доступный остаток символов для сырых сообщений L2
        remaining_chars = max_chars - current_length
        if remaining_chars < 0:
            # Если даже L1 превысил лимит (редчайший случай), режем сам L1
            return l1_string[:max_chars]

        # 2. Извлекаем все сырые реплики текущей сессии (L2)
        raw_messages = self.db.get_session_messages(chat_id)
        
        formatted_messages = []
        l2_length = 0
        
        # Перебираем историю с конца (от свежих к старым)
        for role, content in reversed(raw_messages):
            prefix = "Пользователь: " if role == "user" else "Ассистент: "
            msg_str = f"{prefix}{content.strip()}\n"
            
            # Проверяем, укладывается ли сообщение в оставшийся бюджет
            if l2_length + len(msg_str) > remaining_chars:
                logger.warning(f"[Memory] Достигнут лимит бюджета рабочей памяти для chat_id {chat_id}. Часть старых сообщений L2 скрыта.")
                break
                
            l2_length += len(msg_str)
            formatted_messages.append(msg_str)

        # Сборка финального промпта
        if l1_string:
            final_sections.append(l1_string)
            
        if formatted_messages:
            final_sections.append("=== Текущий активный диалог (Working Memory L2) ===\n")
            # Разворачиваем сообщения обратно в хронологический порядок
            final_sections.extend(reversed(formatted_messages))

        return "".join(final_sections)

    def clear_session_manually(self, chat_id: int):
        """
        Ручной сброс активного окна. 
        Используется принудительно, если нужно очистить L2 без ожидания таймаута.
        """
        try:
            with self.db._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM ai_session_messages WHERE chat_id = ?", (chat_id,))
                conn.commit()
            logger.info(f"[Memory] Слой рабочей памяти L2 для чата {chat_id} принудительно очищен.")
        except Exception as e:
            logger.error(f"[Memory Ошибка] Не удалось очистить L2 для чата {chat_id}: {e}")