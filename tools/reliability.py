import time
import functools
from logger import agent_logger

# Типы ошибок
RECOVERABLE_ERRORS = (BlockingIOError, PermissionError) # PermissionError иногда бывает временным при синхронизации
NON_RECOVERABLE_ERRORS = (FileNotFoundError, IsADirectoryError, MemoryError)

def retry_on_failure(max_retries=3, initial_delay=1):
    """Декоратор для экспоненциального отката (Exponential Backoff)."""
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            retries = 0
            delay = initial_delay
            while retries < max_retries:
                try:
                    return func(*args, **kwargs)
                except RECOVERABLE_ERRORS as e:
                    retries += 1
                    if retries == max_retries:
                        agent_logger.error("Reliability", f"Исчерпаны попытки восстановления после: {e}")
                        raise
                    agent_logger.warning("Reliability", f"Восстановимая ошибка: {e}. Попытка {retries}/{max_retries} через {delay}с.")
                    time.sleep(delay)
                    delay *= 2 # Экспоненциальное увеличение задержки
                except NON_RECOVERABLE_ERRORS as e:
                    agent_logger.error("Reliability", f"Критическая ошибка (невосстановимая): {e}")
                    raise
            return None
        return wrapper
    return decorator

