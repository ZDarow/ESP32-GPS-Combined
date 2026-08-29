# ESP32-S3 GNSS Tracker

Прошивка для GNSS-трекера на ESP32-S3 с передачей NMEA-данных по BLE.

## Оборудование

- **Плата:** ESP32-S3 DevKitC-1 (Rev 2, 16MB QIO, без PSRAM)
- **GPS:** NEO-7M (UART1, 9600 бод)
- **Питание:** 18650 + DC-DC
- **Интерфейс:** BLE Nordic UART Service (NUS)

## Подключение

### NEO-7M GPS

| NEO-7M | ESP32-S3 | Функция |
| :--- | :--- | :--- |
| TX | GPIO18 (RX) | Данные GPS → ESP32 |
| RX | GPIO17 (TX) | Данные ESP32 → GPS |
| VCC | 3.3V | Питание |
| GND | GND | Общий |

### OLED SSD1306 (I2C)

| OLED | ESP32-S3 | Функция |
| :--- | :--- | :--- |
| GND | GND | Общий |
| VDD | 3.3V | Питание |
| SCK | GPIO9 (SCL) | I2C Clock |
| SDA | GPIO8 (SDA) | I2C Data |

Адрес устройства: `0x3C` (по умолчанию для 128×64).

## Структура проекта

```
main/
├── app_config.h       # Конфигурация пинов, таймаутов, BLE
├── main.c             # Точка входа, интеграция модулей
├── gps_uart.c/h       # UART-драйвер для NEO-7M
├── nmea_parser.c/h    # Парсер NMEA-строк (GGA, RMC, GSV, GSA, VTG, GLL)
├── ble_nus.c/h        # BLE Nordic UART Service
├── battery_adc.c/h    # Измерение напряжения батареи
└── power_manager.c/h  # Управление питанием, deep sleep

components/
└── nmea_parser/       # Компонент парсера NMEA
    ├── include/
    └── src/
```

## Модули

### Модуль 1: UART NMEA-парсер

- UART1 (GPIO17/18) на 9600 бод
- Кольцевой буфер 2048 байт
- Парсинг NMEA с проверкой контрольной суммы
- Поддерживаемые предложения: `$GPGGA`, `$GPRMC`, `$GPGSA`, `$GPGSV`, `$GPVTG`, `$GPGLL` и их мульти-системные аналоги `$GNGGA`, `$GNRMC`, `$GNGSA`, `$GNGSV`, `$GNVTG`, `$GNGLL`
- Callback на каждую полную строку
- Таймаут 5 секунд при отсутствии данных
- Диагностика: счётчики байт/строк/NMEA, периодическая статистика раз в 5 сек, RAW-отладка байт (конфигурируется через `GPS_RAW_DEBUG`)

### Модуль 2: BLE Nordic UART Service

- NimBLE-стек
- UUID сервиса: `6E400001-B5A3-F393-E0A9-E50E24DCCA9E`
- TX характеристика (Notify): `6E400003-B5A3-F393-E0A9-E50E24DCCA9E`
- RX характеристика (Write): `6E400002-B5A3-F393-E0A9-E50E24DCCA9E`
- Имя устройства: `ESP32S3-GPS`
- Чанкинг данных по 20 байт (BLE MTU)
- Автоматическое возобновление рекламы при отключении

### Симулятор

При отсутствии реального GPS-фикса и активном BLE-подключении генерирует тестовую NMEA-строку каждые 2 секунды.

## Сборка и прошивка

```powershell
# Активация окружения ESP-IDF
powershell -ExecutionPolicy Bypass -File C:\Users\Mi\esp-idf-v5.5.5\export.ps1 -ForDesktop

# Сборка
cd C:\Users\Mi\Ublox\esp32s3-gnss-ESP-IDF
idf.py build

# Прошивка и монитор
idf.py -p COM5 flash monitor
```

## Тестирование

1. Подключить NEO-7M к ESP32-S3
2. Вынести антенну к окну
3. В мониторе порта дождаться появления NMEA-строк
4. Подключиться к `ESP32S3-GPS` через nRF Connect
5. Подписаться на Notify характеристики TX

## Критерии приёмки

- [x] Проект собирается без ошибок
- [x] В мониторе появляются сырые NMEA-строки
- [x] BLE-устройство видно как `ESP32S3-GPS`
- [x] При подключении идут NMEA-уведомления
- [x] Симулятор работает при отсутствии фикса

## Типичные проблемы

| Проблема | Решение |
| :--- | :--- |
| Нет данных GPS | Проверить TX/RX (GPS_TX → GPIO18, GPS_RX → GPIO17) |
| Кракозябры в логе | Неверный baud rate, проверьте настройки GPS |
| BLE не видно | Проверить `ble_nus_start_advertising()` в логе |
| Нет уведомлений | Включить Notify в nRF Connect на TX-характеристике |
