#!/bin/bash

# 1. Переходим в папку проекта
cd ~/projects/agent_project

# 2. ПРИНУДИТЕЛЬНО лечим ошибку протокола Ollama
export OLLAMA_HOST="http://127.0.0.1:11434"

# 3. Безопасный построчный импорт .env с очисткой от пробелов, комментариев и \r
if [ -f .env ]; then
    while IFS= read -r line || [ -n "$line" ]; do
        # Удаляем символы \r (Windows) и пробелы на концах
        line=$(echo "$line" | tr -d '\r' | xargs)
        # Игнорируем пустые строки и комментарии
        if [ -z "$line" ] || [[ "$line" == \#* ]]; then
            continue
        fi
        # Извлекаем ключ и значение, отрезая inline-комментарии
        key=$(echo "$line" | cut -d= -f1 | xargs)
        val=$(echo "$line" | cut -d= -f2- | cut -d# -f1 | xargs)
        export "$key=$val"
    done < .env
else
    echo "⚠️ Внимание: Файл .env не найден в папке проекта!"
fi

# 4. Активируем виртуальное окружение, которое лежит уровнем выше
source ../.venv/bin/activate

# 5. Чистим старые "зависшие" процессы синхронизации
pkill -f run_sync.py || true

# 6. Запускаем синхронизатор в фоне
python3 run_sync.py &

# 7. Запускаем бота как модуль из корня проекта
python3 -m src.interfaces.telegram.bot
