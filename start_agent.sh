#!/bin/bash

# 1. Переходим в папку проекта
cd ~/projects/agent_project

# 2. ПРИНУДИТЕЛЬНО лечим ошибку протокола (которая была раньше)
export OLLAMA_HOST="http://127.0.0.1:11434"

# 3. Активируем виртуальное окружение
source venv/bin/activate

# 4. Чистим старые "зависшие" процессы синхронизации (чтобы не копились)
pkill -f run_sync.py || true

# 5. Запускаем синхронизатор в фоне
python3 run_sync.py &

# 6. Запускаем бота
python3 bot.py
