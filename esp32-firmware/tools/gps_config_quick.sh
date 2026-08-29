#!/bin/bash
# Быстрая адаптивная конфигурация GPS модуля для Центральной России
# Использование: ./gps_config_quick.sh [COM_PORT]

set -e

PORT="${1:-/dev/ttyACM0}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIGURATOR="$SCRIPT_DIR/gps_configurator.py"

echo "========================================"
echo "GPS Конфигурация для Центральной России"
echo "========================================"
echo ""
echo "Порт: $PORT"
echo ""

# Проверка наличия скрипта
if [ ! -f "$CONFIGURATOR" ]; then
    echo "Ошибка: $CONFIGURATOR не найден"
    exit 1
fi

# Проверка наличия Python
if ! command -v python3 &> /dev/null; then
    echo "Ошибка: python3 не найден. Установите Python 3."
    exit 1
fi

# Проверка наличия pyserial
if ! python3 -c "import serial" 2>/dev/null; then
    echo "Установка pyserial..."
    pip3 install pyserial
fi

# Запуск конфигурации
echo "Запуск конфигурации..."
echo ""

python3 "$CONFIGURATOR" "$PORT" \
    --final-baudrate 9600 \
    --rate 1000 \
    --read \
    --read-duration 10

echo ""
echo "========================================"
echo "Готово!"
echo "========================================"
echo ""
echo "Проверьте работу модуля:"
echo "  timeout 5 cat $PORT | grep -E '^\\$G'"
echo ""
