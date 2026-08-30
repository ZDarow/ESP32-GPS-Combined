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
- **gps_uart.c/h** — UART-драйвер для GPS NEO-7M (UART1, GPIO10/9, 9600 бод)
- **nmea_parser.c/h** — парсер NMEA-строк с поддержкой нескольких констелляций
- **ble_nus.c/h** — BLE Nordic UART Service (NimBLE)
- **battery_adc.c/h** — измерение напряжения батареи (ADC1_CH3 = GPIO4, делитель 2.0)
- **power_manager.c/h** — deep sleep, GPIO5 кнопка, light sleep
- **oled_display.c/h** — OLED SSD1306 I2C (GPIO41/42, адрес 0x3C)

> **Важно:** модули `wifi_manager`, `ntrip_client`, `ubx_commands`, `gps_ring_buffer`, `gnss_queues` отсутствуют в `main/`. Не копируй их структуру из этого файла — они устаревшие. Проверяй реальные файлы в `main/` и `components/`.

### Компоненты (components/nmea_parser/)
- **include/nmea_parser.h** — API парсера, структура gnss_fix_t
- **src/nmea_parser.c** — реализация парсера с extended fields (UTC, DOP, satellites)

### Конфигурация (main/app_config.h)
Основные макросы (источник истины — этот文件):
- GPS_UART_NUM=1, TX=GPIO10, RX=GPIO9, BAUD=9600
- BATTERY_ADC_PIN=4 (ADC1_CH3), MIN=3.0V, MAX=4.2V, делитель 2.0
- DEEP_SLEEP_BTN_PIN=5 (active low), таймаут 300 с
- OLED_I2C_SDA_PIN=41, SCL_PIN=42, I2C_NUM_0, ADDR=0x3C
- BLE_DEVICE_NAME="ESP32S3-GPS"
- GPS_RAW_DEBUG=0 (включайте для отладки), GPS_RAW_DEBUG_LIMIT=50

## Рабочие процессы и очередность

### 1. Сборка и тестирование
```bash
# Шаг 1: Linting
ruff check tools/ble_receiver/

# Шаг 2: Сборка
idf.py build

# Шаг 3: Python тесты (если нужны)
python -m pytest tests/test_nmea_parser.py -v
```

### 2. Прошивка и отладка
```bash
# Прошивка и монитор IDF
idf.py -p /dev/ttyACM0 flash monitor
```

### 3. Основной рабочий процесс
1. **Инициализация**: `gps_uart_init()`, `nmea_parser_init()`, `gps_uart_register_callback(on_gps_line)`, `gps_uart_task_start()`, `power_manager_init()`, `battery_adc_init()`, `oled_display_init()`, `ble_nus_init()`
2. **Запуск задач**: `ble_nus_status_task` (stack 4096), `ble_nus_send_task` (stack 6144, берёт GPS-очередь), `simulator_task` (stack 2048), `idle_task` (stack 2048)
3. **Обработка событий**: NMEA через callback `on_gps_line()`, BLE notify, throttling через `s_ble_queue`
4. **Power management**: автоматический deep sleep при `power_is_idle_timeout()` и отсутствии BLE-соединения

## Ключевые архитектурные особенности

### NMEA parser extended fields
- Поддержка нескольких констелляций (GPS, Galileo, BeiDou)
- UTC time/date parsing, DOP fields, satellites in view
- Callback `on_gps_line()` в main.c

## Important gotchas and quirks

### 1. Коррупция main.c (важно!)
- **Симптом**: Странные компиляционные ошибки, stray braces
- **Ситуация**: main.c был поврежден ранее, что привело к неработоспособности сборки
- **Меры**: Всегда проверяйте main.c на лишние скобки, перед началом изменений

### 2. BLE Battery Level
- **Особенность**: Notify только при изменении >=5%
- **API**: `ble_nus_set_battery_level()`, `ble_nus_get_battery_level()`
- **Меры**: Используйте эти функции вместо прямого изменения

### 3. Power manager GPIO5
- **Особенность**: GPIO5 с pull-up, active low для deep sleep
- **API**: `power_enter_deep_sleep()` (не возвращается)
- **Меры**: Не используйте GPIO5 как обычный input

### 4. NMEA parser callback
- **Особенность**: Парсер вызывает callback с каждой полной строкой
- **API**: `nmea_parser_feed()` возвращает fix_t с valid флагом
- **Меры**: Обработайте как реальные fix, так и V (no fix) состояния

### 5. Симулятор
- **Особенность**: `simulator_task()` генерирует fake NMEA при BLE connected и отсутствии реального фикса (`!s_real_fix`)
- **Местоположение**: main.c, lines 19-31
- **Меры**: Используйте для testing при отсутствии GPS

### 6. Диагностика GPS raw bytes
- **Особенность**: `GPS_RAW_DEBUG` в app_config.h (0=выкл, 1=вкл)
- **Меры**: Включайте только для short debugging sessions

## Типичные проблемы и решения

| Проблема | Быстрый fix |
|---------|----------|
| Нет данных GPS | Проверить TX/RX (GPS_TX → GPIO10, GPS_RX → GPIO9) |
| Кракозябры в логе | Неверный baud rate, проверьте настройки GPS (9600 бод) |
| BLE не видно | Проверить `ble_nus_start_advertising()` в логе |
| Нет уведомлений | Включить Notify в nRF Connect на TX-характеристике |
| Критически низкий заряд батареи | Калибруйте ADC: `battery_set_calibration(3.0f, 4.2f)` |

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
python -m pytest tests/test_nmea_parser.py -v
```

## Рекомендации по разработке

### Новая задача
1. **Добавьте task stack** >= 4096 (используйте 6144 как стандарт)
2. **Используйте thread-safe API** (portMUX_TYPE,FreeRTOS очереди)
3. **Добавьте error handling** и logging через ESP_LOGE/LOGI
4. **Проверьте stack usage** после реализации

### Модификация существующего модуля
1. **Проверьте main.c** на stray braces
2. **Добавьте logging** для нового функционала

### Отладка
1. **Включите GPS_RAW_DEBUG** на короткое время (макрос в app_config.h)
2. **Проверьте OLED** после каждого major change
3. **Мониторьте battery voltage** через `battery_read_voltage()`

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

1. **Queue-based pipeline** — заменить прямой `xQueueSend` на `gnss_queues` (зарезервировано)
2. **Unit tests** — добавить тесты для `nmea_parser`
3. **SD card logging** — persistent NMEA logging
4. **OLED optimization** — line-based rendering
5. **GPS baud rate auto-detection** — адаптация к разным модулям

## Примечания

- Проект разработан для **ESP32-S3 DevKitC-1 Rev 2** (16MB QIO, без PSRAM)
- **Flash size mismatch** исправлен в sdkconfig (8MB actual)
- **Flash**: 8MB, mode dio, freq 80m (из `build/flasher_args.json`)
- **Partition table** в `partitions.csv`: factory 2M, nvs 24K
- **BLE MTU** — chunk size 20 байт (`BLE_MTU_CHUNK_SIZE`)