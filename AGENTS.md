# AGENTS.md — ESP32-GPS-Tracker

Трёхcomponentный проект: **ESP32-S3 прошивка (C / ESP-IDF)** + **Android-приложение (Kotlin / Compose)** + **Python-утилиты**. Корневой репозиторий, подпроекты — в `esp32-firmware/` и `android-app/`.

## Архитектура и entrypoints

- **Прошивка**: `esp32-firmware/main/main.c` → `app_main()` — единственная точка входа. Инициализация строго в порядке: `gps_uart_init` → `nmea_parser_init` → `gps_uart_register_callback(on_gps_line)` → `gps_uart_task_start` → `power_manager_init` → `battery_adc_init` → `oled_display_init` → `ble_nus_init` → задачи `ble_nus_status_task` / `ble_nus_send_task` / `simulator_task` / `idle_task`.
- **Android**: `android-app/app/src/main/java/com/example/esp32gps/` — `GpsApplication.kt` (инициализация OSMDroid user-agent), `MainActivity.kt` (Compose UI + BLE-сканер), `GpsBleManager.kt` (Nordic `BleManager`), `NmeaParser.kt`, `GpxLogger.kt`, `GpsTrackerViewModel.kt` (StateFlow, AndroidViewModel).
- **Python**: `esp32-firmware/tools/ble_receiver/` — BLE-клиент для тестов (Windows/WinRT), `nmea_parser.py`, `track_logger.py`. Тесты: `esp32-firmware/tests/test_nmea_parser.py`.

## Технологический стек (зафиксирован в конфигах, не предположения)

| Подпроект | Стек |
|---|---|
| Прошивка | C, ESP-IDF **v6.0.2** (CI: `espressif/idf:v6.0.2`), CMake, FreeRTOS, NimBLE |
| Android | Kotlin **1.9.24**, Gradle **8.7** / AGP **8.5.2**, Jetpack Compose **1.6.0** + Material3, ViewModel + Coroutines 1.8.1, Nordic Android-BLE **2.7.5**, osmdroid **6.1.18** |
| Python | Python **3.11**, **ruff** (lint+format), **pytest**, **markdownlint** |

## Команды разработки

### Прошивка
```bash
cd esp32-firmware
source ~/esp/esp-idf-v6.0.2/export.sh   # активировать окружение IDF
idf.py menuconfig                       # конфигурация (только один раз, при необходимости)
idf.py build                            # сборка
idf.py -p /dev/ttyACM0 flash monitor    # прошивка + монитор
idf.py monitor                          # только монитор
idf.py -p /dev/ttyACM0 flash            # только прошивка
```

### Android
```bash
cd android-app
./gradlew assembleDebug                # сборка APK
./gradlew detekt                        # статический анализ (CI запускает это же)
./gradlew ktlint                        # форматирование
```

### Python
```bash
cd esp32-firmware
ruff check tools/ble_receiver/          # линтер (требует ruff в PATH)
python -m pytest tests/test_nmea_parser.py -v   #单元-тесты NMEA-парсера
markdownlint '**/*.md' || true         # линтер markdown (CI)
```

## CI (.github/workflows/)

- `ci.yml`: `ruff check .` + `markdownlint '**/*.md'` (Python 3.11).
- `build.yml`: три job — `build-esp32` (IDF v6.0.2, `idf.py build`), `build-android` (JDK 17 Temurin, `./gradlew assembleDebug`, APK артефакт), `lint` (ruff + detekt).
- **Порядок проверок**: `ruff` → `detekt` → `idf.py build` → `./gradlew assembleDebug`. CI не запускает pytest.

## Важные особенности и подводные камни

- **`main.c` повреждается при неаккуратных правках** (stray braces, скобки). Перед любым изменением проверяй синтаксис — сборка мгновенно падает с неясными ошибками.
- **Симулятор NMEA** (`simulator_task` в `main.c`) генерит `$GPRMC` только когда BLE подключён и нет реального фикса (`!s_real_fix`). Используй для тестов без GPS-модуля.
- **BLE Battery Level** (UUID `00002A19`): notify отправляется только при изменении >=5%. Используй `ble_nus_set_battery_level()` / `ble_nus_get_battery_level()`, не пиши напрямую.
- **GPIO0 ≠ кнопка сна.** В `app_config.h` кнопка глубокого сна — **GPIO5**, не GPIO0 (в `esp32-firmware/AGENTS.md` и `DOCUMENTATION.ru.md` указан устаревший GPIO0).
- **Реальные пины** (источник — `main/app_config.h`): GPS UART1 TX=GPIO10, RX=GPIO9, 9600 бод; батарея ADC1_CH3 = GPIO4, делитель 2.0, 3.0–4.2 В; OLED SSD1306 I2C0 SDA=GPIO41, SCL=GPIO42, адрес 0x3C; таймаут сна 300 с.
- **Конфликт версий IDF**: CI и `esp32-firmware/AGENTS.md` — v6.0.2, но `DOCUMENTATION.ru.md` и `build/compile_commands.json` упоминают v5.5.5. Доверяй **CI (`build.yml`)**: v6.0.2. Файл `esp32-firmware/AGENTS.md` содержит устаревшие модули (`wifi_manager`, `ntrip_client`, `ubx_commands`, `gnss_queues`) — их нет в `main/`. Не копируй оттуда структуру, проверяй `main/` и `components/`.
- **Flash**: 8MB, mode dio, freq 80m (из `build/flasher_args.json`). Partition table в `partitions.csv`: factory 2M, nvs 24K.
- **ESP-IDF окружение** — одноразово: `source ~/esp/esp-idf-v6.0.2/export.sh`. Без него `idf.py` не найдёт toolchain и компоненты.
- **Python-тесты** импортируют `nmea_parser` из `tools/ble_receiver/` через `sys.path.insert` (см. `tests/test_nmea_parser.py`). Запускай из корня `esp32-firmware`, иначе ImportError.
- **Android-разрешения**: `BLUETOOTH_SCAN`, `BLUETOOTH_CONNECT`, `ACCESS_FINE_LOCATION` — runtime, минимум API 26, target API 35.
- **Секреты**: Wi-Fi SSID/пароль и NTRIP учётные данные — в `app_config.h` как макросы (заменяй `YOUR_WIFI_SSID` и т.п.), не коммить реальные значения. `.env`, `credentials.json`, `secrets.*` уже в `.gitignore`.
- **Git**: push и синхронизация с remote — только с явного указания. Коммиты — на русском, повелительном наклонении; ветки — `kebab-case` (например, `fix/ble-notify-throttle`).