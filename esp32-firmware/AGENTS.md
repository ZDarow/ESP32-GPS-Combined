# AGENTS.md — Инструкция для Kilo в проекте ESP32-S3 GNSS Tracker

## Основные команды разработки

### Сборка и прошивка (ESP-IDF v6.0.2)
```bash
# Активация окружения ESP-IDF (создайте скрипт export.sh)
source ~/esp/esp-idf-v6.0.2/export.sh

# Сборка
cd /media/mi/CC3CD24C3CD230E61/Ublox/esp32s3-gnss-ESP-IDF
idf.py build

# Прошивка и монитор (COM5 — ваш порт)
idf.py -p COM5 flash monitor
```

### Тестирование BLE (Python)
```bash
cd tools/ble_receiver
python -m pytest ble_test.py -v
```

### Linting и форматирование
```bash
# Проверка Python кода (tools/ble_receiver)
ruff check tools/ble_receiver/

# Проверка Markdown
markdownlint '**/*.md' || true
```

## Структура проекта и entrypoint

### Основные модули (main/)
- **main.c** — точка входа, интеграция всех компонентов
- **gps_uart.c/h** — UART-драйвер для GPS NEO-7M (UART1, GPIO17/18, 9600 бод)
- **nmea_parser.c/h** — парсер NMEA-строк с поддержкой нескольких констелляций
- **ble_nus.c/h** — BLE Nordic UART Service (NimBLE)
- **battery_adc.c/h** — измерение напряжения батареи (ADC1_CH2, делитель 2.0)
- **power_manager.c/h** — deep sleep, GPIO0 кнопка, light sleep
- **oled_display.c/h** — OLED SSD1306 I2C (GPIO20/21, адрес 0x3C)
- **wifi_manager.c/h** — WiFi STA клиент с reconnection
- **ntrip_client.c/h** — NTRIP клиент для RTK-GPS коррекций
- **ubx_commands.c/h** — UBX команды для конфигурации GPS
- **gps_ring_buffer.c/h** — thread-safe ring buffer (16KB)
- **gnss_queues.c/h** — FreeRTOS queue adapter (зарезервирован для Phase 5)

### Компоненты (components/nmea_parser/)
- **include/nmea_parser.h** — API парсера, структура gnss_fix_t
- **src/nmea_parser.c** — реализация парсера с extended fields (UTC, DOP, satellites)

### Конфигурация (main/app_config.h)
Основные макросы:
- GPS_UART_NUM=1, TX=GPIO17, RX=GPIO18, BAUD=9600
- BATTERY_ADC_PIN=2, MIN=3.0V, MAX=4.2V
- DEEP_SLEEP_BTN_PIN=0 (active low)
- OLED_I2C_SDA_PIN=20, SCL_PIN=21, ADDR=0x3C
- BLE_DEVICE_NAME="ESP32S3-GPS"
- WiFi/NTRIP параметры (замените YOUR_WIFI_SSID, ntrip.example.com)

## Рабочие процессы и очередность

### 1. Сборка и тестирование
```bash
# Шаг 1: Linting
ruff check tools/ble_receiver/

# Шаг 2: Сборка
idf.py build

# Шаг 3: Python тесты (если нужны)
cd tools/ble_receiver && python -m pytest ble_test.py -v
```

### 2. Прошивка и отладка
```bash
# Прошивка и монитор IDF
idf.py -p COM5 flash monitor
```

### 3. Основной рабочий процесс
1. **Инициализация**: `gps_uart_init()`, `ble_nus_init()`, `wifi_manager_init()`
2. **Запуск задач**: `gps_uart_task_start()`, `xTaskCreate(ble_nus_status_task, ...)`, `xTaskCreate(wifi_ntrip_task, ...)`
3. **Обработка событий**: NMEA через callback, BLE notifications, WiFi reconnect, NTRIP RTCM3 forwarding
4. **Power management**: Автоматический deep sleep при низком заряде батареи (<3.0V)

## Ключевые архитектурные особенности

### Ring buffer (gps_ring_buffer.c/h)
- Размер: 16384 байта (GPS_RING_BUFFER_SIZE)
- Thread-safe через `portMUX_TYPE`
- Overflow флаг при заполнении
- Использует `ble_nus_send_from_ring_buffer()` для BLE передачи

### BLE Battery Level characteristic
- UUID: 00002A19
- Notify только при изменении >=5%
- Thread-safe через `portMUX_TYPE`

### Power manager
- GPIO0 debounce (50ms)
- EXT0 wakeup (active low)
- Light sleep с CPU/APB locks
- Автоматический deep sleep при battery_is_low() (3 consecutive readings)

### NMEA parser extended fields
- Поддержка нескольких констелляций (GPS, Galileo, BeiDou)
- UTC time/date parsing, DOP fields, satellites in view
- Callback `on_gps_line()` в main.c

### WiFi/NTRIP integration
- WiFi STA клиент с automatic reconnection
- NTRIP RTCM3 parsing и forwarding к GPS UART
- Heartbeat и reconnection logic в `wifi_ntrip_task()`

## Important gotchas and quirks

### 1. Коррупция main.c (важно!)
- **Симптом**: Странные компиляционные ошибки, stray braces
- **Ситуация**: main.c был поврежден ранее, что привело к неработоспособности сборки
- **Меры**: Всегда проверяйте main.c на лишние скобки, перед началом изменений

### 2. BLE Battery Level
- **Особенность**: Notify только при изменении >=5%
- **API**: `ble_nus_set_battery_level()`, `ble_nus_get_battery_level()`
- **Меры**: Используйте эти функции вместо прямого изменения

### 3. Power manager GPIO0
- **Особенность**: GPIO0 с pull-up, active low для deep sleep
- **API**: `power_enter_deep_sleep()` (не возвращается)
- **Меры**: Не используйте GPIO0 как обычный input

### 4. NMEA parser callback
- **Особенность**: Парсер вызывает callback с каждой полной строкой
- **API**: `nmea_parser_feed()` возвращает fix_t с valid флагом
- **Меры**: Обработайте как реальные fix, так и V (no fix) состояния

### 5. Ring buffer integration
- **Особенность**: GPS UART пишет в ring buffer, BLE task читает из него
- **API**: `gps_uart_get_ring_buffer()`, `ble_nus_send_from_ring_buffer()`
- **Меры**: Всегда проверяйте overflow флаг

### 6. Stack monitoring
- **Особенность**: Все основные задачи имеют stack 6144 байта (кроме stack_monitor)
- **API**: `stack_monitor_task()` печатает high-water marks каждые 30 сек
- **Меры**: Следите за stack usage при добавлении новых задач

### 7. Симулятор
- **Особенность**: `simulator_task()` генерирует fake NMEA при BLE connected
- **Местоположение**: main.c, lines 53-69
- **Меры**: Используйте для testing при отсутствии GPS

### 8. Диагностика GPS raw bytes
- **Особенность**: `GPS_RAW_DEBUG` в app_config.h (0=выкл, 1=вкл)
- **Меры**: Включайте только для short debugging sessions

## Типичные проблемы и решения

| Проблема | Быстрый fix |
|---------|----------|
| Нет данных GPS | Проверить TX/RX (GPS_TX → GPIO18, GPS_RX → GPIO17) |
| Кракозябры в логе | Неверный baud rate, проверьте настройки GPS (9600 бод) |
| BLE не видно | Проверить `ble_nus_start_advertising()` в логе |
| Нет уведомлений | Включить Notify в nRF Connect на TX-характеристике |
| Критически низкий заряд батареи | Калибруйте ADC: `battery_set_calibration(3.0f, 4.2f)` |
| WiFi не подключается | Замените YOUR_WIFI_SSID/YOUR_WIFI_PASSWORD в app_config.h |
| NTRIP не работает | Замените NTRIP_HOST, MOUNTPOINT, USER, PASSWORD |

## CI/CD

### GitHub Actions (.github/workflows/ci.yml)
- **lint**: ruff check + markdownlint
- **build**: idf.py build (ESP-IDF v6.0.2, esp32s3 target)
- **test**: Python pytest для tools/ble_receiver/

### Типичные команды CI
```bash
# Запустить только lint
ruff check tools/ble_receiver/

# Запустить только сборку
idf.py build

# Запустить Python тесты
python -m pytest tools/ble_receiver/ble_test.py -v
```

## Рекомендации по разработке

### Новая задача
1. **Добавьте task stack** >= 4096 (используйте 6144 как стандарт)
2. **Используйте thread-safe API** (ring buffer, power locks)
3. **Добавьте error handling** и logging через ESP_LOGE/LOGI
4. **Проверьте stack usage** после реализации

### Модификация существующего модуля
1. **Проверьте main.c** на stray braces
2. **Обновите stack_monitor_task** с новым task name
3. **Добавьте logging** для нового функционала

### Отладка
1. **Включите GPS_RAW_DEBUG** на короткое время
2. **Проверьте OLED** после каждого major change
3. **Мониторьте battery voltage** через `battery_read_voltage()`
4. **Используйте stack_monitor_task** output

## Критерии приёмки (из README.md)

- [x] Проект собирается без ошибок
- [x] В мониторе появляются сырые NMEA-строки
- [x] BLE-устройство видно как `ESP32S3-GPS`
- [x] При подключении идут NMEA-уведомления
- [x] Симулятор работает при отсутствии фикса

## Ссылки

- **README.md** — руководство по подключению и сборке
- **DOCUMENTATION.md** — comprehensive documentation
- **components/nmea_parser/** — исходный код парсера
- **tools/ble_receiver/** — Python инструменты для testing BLE
- **sdkconfig** — конфигурации ESP-IDF (flash size corrected to 8MB)
- **partitions.csv** — разделение flash (app 2MB)

## Следующие шаги (Phase 5)

1. **Queue-based pipeline** — заменить ring buffer на gnss_queues
2. **Unit tests** — добавить тесты для nmea_parser, gps_ring_buffer
3. **SD card logging** — persistent NMEA logging
4. **OLED optimization** — line-based rendering
5. **GPS baud rate auto-detection** — адаптация к разным модулям

## Примечания

- Проект разработан для **ESP32-S3 DevKitC-1 Rev 2** (16MB QIO, без PSRAM)
- **Flash size mismatch** исправлен в sdkconfig (8MB actual)
- **Stack overflow hook** настроен (`vApplicationStackOverflowHook`)
- **Deep sleep button** — GPIO0, debounce 50ms
- **Battery ADC** — ADC1_CH2, 12-bit, 3.3V reference, divider 2.0
- **BLE MTU** — chunk size 20 байт (`BLE_MTU_CHUNK_SIZE`)
- **NTRIP** — RTCM3 parsing, buffer 512 байт (`NTRIP_RTCM_BUFFER_SIZE`)