# Конфигурация GPS модуля для Центральной России

## Быстрый старт

### 1. Определите COM порт GPS модуля

```bash
# Linux
ls /dev/ttyACM0 /dev/ttyUSB0

# Или проверьте dmesg
dmesg | grep -i "tty\|usb"
```

### 2. Запустите конфигурацию

```bash
# Базовая конфигурация (9600 бод, 1Hz)
python3 tools/gps_configurator.py /dev/ttyACM0

# С конфигурацией 115200 бод, 5Hz
python3 tools/gps_configurator.py /dev/ttyACM0 --final-baudrate 115200 --rate 200

# Со сбросом к заводским настройкам
python3 tools/gps_configurator.py /dev/ttyACM0 --reset

# С чтением данных после конфигурации
python3 tools/gps_configurator.py /dev/ttyACM0 --read --read-duration 30
```

### 3. Проверьте работу

```bash
# Прочитать NMEA данные
timeout 10 cat /dev/ttyACM0 | grep -E '^\$G'

# Или через screen
screen /dev/ttyACM0 9600
```

## Настройки для Центральной России

### Географические координаты
- **Широта**: 55-60°N (Москва: 55.7558°N)
- **Долгота**: 35-45°E (Москва: 37.6173°E)
- **Регион**: Центральная Россия

### Рекомендуемые настройки

#### Спутниковые системы
- ✅ **GPS** (США) - глобальная система, базовый набор
- ✅ **GLONASS** (Россия) - **приоритетная** для региона, лучшее покрытие
- ✅ **Galileo** (ЕС) - дополнительное покрытие, высокая точность
- ✅ **BeiDou** (Китай) - дополнительное покрытие
- ✅ **SBAS/EGNOS** - система коррекций для улучшения точности

#### Частота обновления
- **1Hz (1000ms)** - стандартный режим, низкое энергопотребление
- **5Hz (200ms)** - для динамических приложений (трекинг в движении)
- **10Hz (100ms)** - для высокоскоростных применений

#### Скорость UART
- **9600 бод** - по умолчанию, надежная связь
- **115200 бод** - для высокоскоростных модулей
- **921600 бод** - только для конфигурации (быстрая загрузка)

## Архитектура конфигурации

### UBX протокол

Конфигуратор использует бинарный протокол UBX от u-blox:

```
[0xB5] [0x62] [CLASS] [ID] [LENGTH_L] [LENGTH_H] [PAYLOAD...] [CK_A] [CK_B]
```

### Поддерживаемые сообщения

| Сообщение | Назначение |
|-----------|-----------|
| UBX-CFG-PRT | Конфигурация портов (UART, USB, I2C) |
| UBX-CFG-GNSS | Включение/выключение GNSS систем |
| UBX-CFG-SBAS | Конфигурация SBAS коррекций |
| UBX-CFG-NAV5 | Навигационные параметры |
| UBX-CFG-RATE | Частота обновления |
| UBX-CFG-MSG | Включение NMEA сообщений |
| UBX-CFG-CFG | Сохранение/загрузка конфигурации |
| UBX-MON-VER | Получение версии прошивки |

## Примеры использования

### Пример 1: Базовая конфигурация

```bash
# Подключение к /dev/ttyACM0, 9600 бод, 1Hz
python3 tools/gps_configurator.py /dev/ttyACM0
```

### Пример 2: Высокоскоростная конфигурация

```bash
# 115200 бод, 5Hz, для трекера
python3 tools/gps_configurator.py /dev/ttyACM0 \
    --final-baudrate 115200 \
    --rate 200
```

### Пример 3: Полный сброс и переконфигурация

```bash
# Сброс к заводским настройкам и полная переконфигурация
python3 tools/gps_configurator.py /dev/ttyACM0 \
    --reset \
    --final-baudrate 9600 \
    --rate 1000 \
    --read --read-duration 30
```

### Пример 4: Программное использование

```python
from tools.gps_configurator import UBXConfigurator

# Создаем конфигуратор
config = UBXConfigurator('/dev/ttyACM0', baudrate=921600)

# Подключаемся
if config.connect():
    # Конфигурируем для Центральной России
    config.configure_for_central_russia(
        baudrate=9600,
        measurement_interval_ms=1000
    )
    
    # Читаем данные
    config.read_nmea(duration=10)
    
    # Отключаемся
    config.disconnect()
```

## Интеграция с ESP32-S3 проектом

### Использование в коде ESP-IDF

В проекте уже реализованы UBX команды в `main/ubx_commands.c`:

```c
// В main.c или отдельной задаче
#include "ubx_commands.h"

// Конфигурация для Центральной России
void configure_gps_for_russia(void) {
    // 1. Настройка порта UART1
    ubx_cfg_prt(GPS_UART_NUM, GPS_UART_BAUD);
    
    // 2. Включение GNSS систем (GPS + GLONASS + Galileo + BeiDou)
    // Требуется реализация в ubx_commands.c
    
    // 3. Настройка частоты 1Hz
    ubx_cfg_rate(1000);
    
    // 4. Включение NMEA сообщений
    // GGA, RMC, GSA, GSV, GLL, VTG
    
    // 5. Сохранение конфигурации
    ubx_cfg_save();
}
```

### Рекомендуемые изменения в ubx_commands.c

```c
// Добавить в ubx_commands.h
esp_err_t ubx_cfg_gnss(bool gps, bool glonass, bool galileo, bool beidou, bool sbas);
esp_err_t ubx_cfg_sbas(bool enabled);
esp_err_t ubx_cfg_nav5(uint8_t dyn_model, uint8_t fix_mode);
esp_err_t ubx_cfg_msg(uint8_t msg_class, uint8_t msg_id, uint8_t rate_uart1);

// Добавить в ubx_commands.c
esp_err_t ubx_cfg_gnss(bool gps, bool glonass, bool galileo, bool beidou, bool sbas) {
    // UBX-CFG-GNSS payload
    // ...
}
```

## Проверка конфигурации

### Проверка через NMEA

```bash
# Должны появляться предложения от разных систем
$GNGGA  - GPS + GLONASS + Galileo + BeiDou (G = multi-GNSS)
$GNRMC  - Multi-GNSS RMC
$GNGSA  - Multi-GNSS GSA (спутники от разных систем)
$GNGSV  - Multi-GNSS GSV (видимые спутники)
```

### Проверка через UBX

```python
# Запрос версии
python3 tools/gps_configurator.py /dev/ttyACM0 --read

# Проверка включенных систем
# Должны быть видны спутники GPS (G), GLONASS (R), Galileo (E), BeiDou (B/C)
```

## Устранение проблем

### Проблема: Модуль не отвечает

```bash
# Проверьте подключение
ls -la /dev/ttyACM0

# Попробуйте другой baud rate
python3 tools/gps_configurator.py /dev/ttyACM0 --baudrate 115200

# Проверьте физическое подключение
# TX GPS -> RX ESP32
# RX GPS -> TX ESP32 (опционально)
# GND -> GND
# VCC -> 3.3V или 5V (в зависимости от модуля)
```

### Проблема: Нет спутников

```bash
# 1. Проверьте антенну
#    - Убедитесь, что антенна подключена
#    - Разместите модуль у окна или на открытом воздухе
#    - Ожидание первого фикса: 30-60 секунд

# 2. Проверьте конфигурацию
timeout 5 cat /dev/ttyACM0 | grep -E '^\$GNGGA'

# 3. Проверьте количество спутников
timeout 5 cat /dev/ttyACM0 | grep -E '^\$GNGSA'
```

### Проблема: Низкая точность

```bash
# 1. Убедитесь, что SBAS включен
# 2. Проверьте PDOP значение в GGA
#    - PDOP < 2.0 - отличная точность
#    - PDOP 2.0-5.0 - хорошая точность
#    - PDOP > 5.0 - плохая точность

# 3. Включите все доступные системы
python3 tools/gps_configurator.py /dev/ttyACM0 --reset
```

## Технические детали

### Поддерживаемые модули

- **u-blox NEO-6M** - базовая модель, только GPS
- **u-blox NEO-7M** - GPS + GLONASS
- **u-blox NEO-M8N** - GPS + GLONASS + Galileo (рекомендуется)
- **u-blox NEO-M9N** - GPS + GLONASS + Galileo + BeiDou (лучший выбор)
- **u-blox ZED-F9P** - профессиональный RTK модуль

### Параметры конфигурации

| Параметр | Значение | Описание |
|-----------|----------|----------|
| GPS | Включен | Базовая навигационная система |
| GLONASS | Включен | Российская система, приоритет для региона |
| Galileo | Включен | Европейская система, дополнительное покрытие |
| BeiDou | Включен | Китайская система, дополнительное покрытие |
| SBAS | Включен | EGNOS коррекции для улучшения точности |
| Частота | 1Hz | Стандартный режим, низкое энергопотребление |
| UART | 9600 бод | Надежная скорость передачи |
| Режим фиксации | 3D Auto | Автоматический выбор 2D/3D |

### Энергопотребление

| Режим | Потребление | Примечание |
|-------|-------------|------------|
| 1Hz, все системы | ~25-35mA | Стандартный режим |
| 5Hz, все системы | ~40-50mA | Для трекеров |
| 1Hz, только GPS | ~20-25mA | Энергосберегающий |
| Deep Sleep | ~1-2mA | Между измерениями |

## Дополнительные ресурсы

- [u-blox Protocol Specification](https://www.u-blox.com/sites/default/files/products/documents/u-blox8-M8_ReceiverDescrProtSpec_UBX-13003221.pdf)
- [PyGPSClient Documentation](https://github.com/semuconsulting/PyGPSClient)
- [GPSD Documentation](https://gpsd.io/)
- [ESP32-S3 UART Driver](https://docs.espressif.com/projects/esp-idf/en/stable/esp32s3/api-reference/peripherals/uart.html)

## Автор

Создано для проекта ESP32-S3 GNSS Tracker
Версия: 1.0
Дата: 2026-08-20
