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

# Установка Python-зависимостей
echo "[3/3] Установка Python-пакетов..."
pip install -r requirements.txt -q

echo ""
echo "=== Готово! ==="
echo "Запуск:  python3 app.py"
echo "Откройте: http://localhost:5000"
