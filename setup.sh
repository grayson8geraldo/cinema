#!/usr/bin/env bash
set -e

echo "=== Cinema Composer — установка ==="

# Проверка Python
if ! command -v python3 &>/dev/null; then
    echo "ОШИБКА: Python 3 не найден. Установите python3."
    exit 1
fi

echo "[1/3] Python: $(python3 --version)"

# Проверка FFmpeg
if ! command -v ffmpeg &>/dev/null; then
    echo ""
    echo "ОШИБКА: FFmpeg не найден."
    echo "Установите:"
    echo "  Ubuntu/Debian:  sudo apt install ffmpeg"
    echo "  macOS:          brew install ffmpeg"
    echo "  Windows:        https://ffmpeg.org/download.html"
    exit 1
fi

echo "[2/3] FFmpeg: $(ffmpeg -version | head -1)"

# Создание виртуального окружения и установка зависимостей
echo "[3/3] Установка Python-пакетов..."

if [ ! -d "venv" ]; then
    python3 -m venv venv
    echo "  Виртуальное окружение создано: venv/"
fi

source venv/bin/activate
pip install -r requirements.txt -q

echo ""
echo "=== Готово! ==="
echo ""
echo "Запуск:"
echo "  source venv/bin/activate"
echo "  python3 app.py"
echo ""
echo "Откройте: http://localhost:5000"
