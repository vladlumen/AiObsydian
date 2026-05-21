#!/bin/bash

# 0. ЗАЩИТА: Убиваем старые зависшие процессы нашего бота перед новым запуском
pkill -f "python3 test_run.py" 2>/dev/null || true

# 1. Активируем виртуальное окружение
source venv/bin/activate

# 2. Надежный поиск путей через sysconfig
export LD_LIBRARY_PATH=$(python3 -c "import sysconfig; sp=sysconfig.get_path('purelib'); print(f'{sp}/nvidia/cublas/lib:{sp}/nvidia/cudnn/lib')"):$LD_LIBRARY_PATH

# Добавляем стандартный путь к библиотекам CUDA в WSL2
export LD_LIBRARY_PATH="/usr/local/cuda/lib64:$LD_LIBRARY_PATH"

# 3. Запускаем нашего Оркестратора
python3 test_run.py