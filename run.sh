#!/bin/bash

# Очищаем консоль для чистых логов
clear
echo "========================================="
echo "   ЗАПУСК СИСТЕМЫ И ИНДЕКСАЦИИ (WSL2)    "
echo "========================================="

# 0. ЗАЩИТА: Убиваем старые зависшие процессы бота и синхронизации
pkill -f "python3 test_run.py" 2>/dev/null || true
pkill -f "python3 run_sync.py" 2>/dev/null || true

# 1. Активируем виртуальное окружение
source venv/bin/activate

# 2. Надежный поиск путей к CUDA через sysconfig
export LD_LIBRARY_PATH=$(python3 -c "import sysconfig; sp=sysconfig.get_path('purelib'); print(f'{sp}/nvidia/cublas/lib:{sp}/nvidia/cudnn/lib')"):$LD_LIBRARY_PATH

# Добавляем стандартный путь к библиотекам CUDA в WSL2
export LD_LIBRARY_PATH="/usr/local/cuda/lib64:$LD_LIBRARY_PATH"

# 3. ЭТАП СИНХРОНИЗАЦИИ: Запуск инкрементального RAG перед стартом интерфейса
python3 run_sync.py

# 4. ЭТАП ИНТЕРФЕЙСА: Запуск основного Оркестратора Telegram
echo "🚀 Запуск Telegram-интерфейса ассистента..."
python3 test_run.py