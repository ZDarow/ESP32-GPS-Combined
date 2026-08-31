# ESP32-GPS-Tracker — Техническая документация проекта

> **Проект:** `esp32s3-gnss` — BLE GNSS-трекер на базе ESP32-S3 и u-blox GNSS
> **Версия документа:** 1.0
> **Дата:** 30.08.2026
> **Лицензия:** MIT
> **Язык документации:** русский (идентификаторы — английские)

---

## Оглавление

1. [Обзор архитектуры и стека](#1-обзор-архитектуры-и-стека)
2. [Структура директорий и ключевые модули](#2-структура-директорий-и-ключевые-модули)
3. [Установка, настройка окружения и запуск](#3-установка-настройка-окружения-и-запуск)
4. [Детальное описание API, классов и функций](#4-детальное-описание-api-классов-и-функций)
5. [Примеры использования](#5-примеры-использования)
6. [Troubleshooting и FAQ](#6-troubleshooting-и-faq)

---

## 1. Обзор архитектуры и стека

### 1.1 Назначение системы

ESP32-GPS-Tracker — это низкопотребляющий BLE-маяк, который:

1. Принимает NMEA-предложения от GNSS-приёмника u-blox по UART.
2. Пересылает их на смартфон/ПК через **Nordic UART Service (NUS)** поверх BLE.
3. При отсутствии реального фикса генерирует синтетические NMEA для тестирования.
4. Обеспечивает **сервисное обслуживание** модулей «на столе»: диагностику
   конфигурации, авто-коррекцию и запись в энергонезависимую память.

### 1.2 Аппаратный стек

| Компонент | Спецификация |
|-----------|--------------|
| **MCU** | ESP32-S3 (Xtensa LX7, двухъядерный, 160 МГц, 16 MB Flash QIO, без PSRAM) |
| **GNSS** | u-blox NEO-7M / M8 / M9 (UART1, 9600–57600 бод, 3.3 В) |
| **Питание** | 18650 Li-ion + понижающий DC-DC |
| **BLE** | NimBLE (Bluetooth 5.0, LE 2M PHY) |
| **АЦП батареи** | ADC1_CH2 (GPIO2) |
| **OLED** | SSD1306 (I²C) |
| **Кнопка сна** | GPIO5 (активный LOW) |

### 1.3 Программный стек

| Слой | Технология | Назначение |
|------|-----------|------------|
| **Firmware** | ESP-IDF v6.0.2, C, FreeRTOS, NimBLE | Прошивка трекера |
| **Android** | Kotlin 1.9.24, Jetpack Compose, Nordic BLE 2.7.0, OSMDroid | Мобильный клиент |
| **Python-инструменты** | Python 3.12, pyserial, pyubx2, pygnssutils, bleak | Диагностика/конфигурация/сервис |
| **Протоколы** | NMEA-0183, UBX (бинарный u-blox) | Обмен с GNSS-модулем |

### 1.4 Поток данных

```
        UART (NMEA)                BLE (NUS)                   USB/Файл
  GNSS ──────────► ESP32 ─────────────────────► Android / PC (ble_receiver)
            ▲            │  │
            │            │  └─ OLED (статус)
            │            └─ глубокий сон (idle)
            │
     Python-инструменты (service_center / configurator / gnss_diag)
     читают и пишут UBX-CFG через тот же UART
```

---

## 2. Структура директорий и ключевые модули

```
ESP32-GPS-Tracker/
├── esp32-firmware/                 # Прошивка трекера (ESP-IDF)
│   ├── main/                       # Исходники firmware (C)
│   │   ├── main.c                  # Точка входа, задачи FreeRTOS
│   │   ├── gps_uart.c/.h           # Драйвер UART-GNSS + NMEA-парсер
│   │   ├── ble_nus.c/.h            # Nordic UART Service (NimBLE)
│   │   ├── oled_display.c/.h       # OLED-рендер (вынесен в задачу)
│   │   ├── power_manager.c/.h      # Глубокий сон, idle-таймаут
│   │   ├── battery_adc.c/.h        # Измерение заряда АКБ
│   │   └── app_config.h            # Конфигурация проекта
│   ├── components/nmea_parser/     # Компонент парсера NMEA
│   ├── tools/                      # Python-инструменты сервиса
│   │   ├── service_center.py       # ★ Оркестратор сервис-центра
│   │   ├── gps_configurator.py     # ★ Запись UBX-CFG (pyubx2)
│   │   ├── gnss_diag.py            # ★ Диагностика GNSS (чтение)
│   │   ├── gps_fix_monitor.py     # Live-монитор фикса по NMEA
│   │   ├── gps_config_quick.sh     # Быстрая конфигурация (обёртка)
│   │   ├── ble_receiver/           # BLE-клиент (bleak) для ПК
│   │   ├── requirements.txt        # Зависимости Python
│   │   └── GPS_CONFIGURATION.md    # Региональная конфигурация
│   ├── sdkconfig                   # Конфигурация ESP-IDF
│   ├── CMakeLists.txt
│   └── DOCUMENTATION.ru.md         # Документация firmware
├── android-app/                    # Мобильный клиент (Kotlin)
│   └── app/src/main/java/com/example/esp32gps/
│       ├── MainActivity.kt         # Compose UI + BLE-сканер + карта
│       ├── GpsBleManager.kt        # Nordic BleManager (NUS, MTU, PHY)
│       ├── NmeaParser.kt           # RMC + GGA → decimal degrees
│       ├── GpsFix.kt               # data-class фикса
│       └── GpxLogger.kt            # Запись трека в GPX 1.1
├── AGENTS.md, CONTRIBUTING.md      # Мета-документация проекта
└── LICENSE
```

### 2.1 Ключевые Python-модули (сервисный контур)

| Файл | Роль | Основные сущности |
|------|------|-------------------|
| `service_center.py` | Полный цикл «диагностика → коррекция → запись» | `service_cycle()`, `detect()`, `apply_fix()`, `detect_baud()` |
| `gps_configurator.py` | Запись конфигурации через UBX-CFG | `UBXConfigurator` |
| `gnss_diag.py` | Низкоуровневое чтение UBX (безопасный `ubx_poll`) | `ubx_poll()`, `_read_with_timeout()` |
| `gps_fix_monitor.py` | Мониторинг фикса по NMEA с реконнектом | `main()` |
| `ble_receiver/` | Приём NMEA по BLE на ПК | `BleNusClient` (bleak) |

---

## 3. Установка, настройка окружения и запуск

### 3.1 Требования

- Python ≥ 3.10
- `pyserial`, `pyubx2`, `pygnssutils` (см. `tools/requirements.txt`)
- Доступ к последовательному порту (`/dev/ttyUSB0`, `COM3`, …)
- Для BLE-клиента: `bleak` (отдельный `requirements.txt` в `ble_receiver/`)

### 3.2 Установка Python-инструментов

```bash
cd ESP32-GPS-Tracker/esp32-firmware/tools
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 3.3 Сборка и прошивка firmware (ESP-IDF)

```bash
cd esp32-firmware
. $IDF_PATH/export.sh            # активация ESP-IDF v6.0.2
idf.py set-target esp32s3
idf.py build
idf.py -p /dev/ttyUSB0 flash monitor
```

### 3.4 Сборка Android-приложения

Открыть `android-app` в Android Studio (Hedgehog/Koala+), Gradle Sync,
Build → Run. На устройстве выдать разрешения
`BLUETOOTH_SCAN` / `BLUETOOTH_CONNECT` / `ACCESS_FINE_LOCATION`.

### 3.5 Быстрый старт сервис-центра

```bash
# Автоопределение скорости + диагностика/коррекция/сохранение
python3 service_center.py --port /dev/ttyUSB0

# Полный сброс к заводским + применение целевого профиля
python3 service_center.py --port /dev/ttyUSB0 --reset
```

---

## 4. Детальное описание API, классов и функций

### 4.1 `gnss_diag.py` — низкоуровневое чтение UBX

#### `ubx_poll(stream, cls, mid, secs=3.0) -> (msgs, port_error)`

Посылает UBX-POLL `(cls, mid)` и собирает ответные сообщения.

- **Параметры:**
  - `stream` — открытый `serial.Serial`.
  - `cls`, `mid` — класс и ID UBX-сообщения (например, `0x0A, 0x04` = MON-VER).
  - `secs` — время ожидания ответа.
- **Возвращает:** кортеж `(список UBXMessage, port_error)`.
  - `port_error=True` — только при реальной ошибке порта (исчез/не открылся).
  - `port_error=False` при тихом отсутствии ответа (модуль жив, но сообщение не поддерживается).
- **Реализация:** использует `UBXReader` (pyubx2) с `protfilter=2` (весь UBX,
  включая класс CFG 0x06). Каждый `read()` обёрнут в жёсткий таймаут
  (`signal.SIGALRM`), т.к. `UBXReader.read()` может блокироваться дольше
  таймаута потока. Свежий `UBXReader` создаётся на каждой итерации, чтобы
  состояние парсера не «спотыкалось» о мусор/NMEA между опросами.

```python
import serial, gnss_diag as g
s = serial.Serial("/dev/ttyUSB0", 57600, timeout=1)
msgs, perr = g.ubx_poll(s, 0x0A, 0x04, 2.5)   # MON-VER
print(msgs[0].swVersion)
```

#### `identify_chipset(stream, baud) -> str`

Определяет чипсет: шлёт `MON-VER`, при отсутствии ответа ловит NMEA-баннер
`u-blox`, затем опрашивает проприетарные запросы (MTK/Quectel/…).
Возвращает `"ublox"` / `"mtk"` / `"unknown"` и т.п.

#### `ublox_hardware(stream)`, `ublox_navsat(stream)`

Чтение `MON-HW` (антенна, AGC, jamming) и `NAV-SAT` (code lock, эфемериды,
используемые в решении). **Важно:** pyubx2 раскрывает битовое поле флагов
`NAV-SAT` на отдельные атрибуты `qualityInd_XX`, `ephAvail_XX`, `svUsed_XX`
(а не `flags_XX`).

### 4.2 `gps_configurator.py` — запись конфигурации

#### `class UBXConfigurator`

Конфигуратор u-blox через pyubx2. Все UBX-CFG собираются библиотекой
(корректные поля и контрольные суммы), отправка и ожидание ACK — через
`pyserial` + `UBXReader`.

**Конструктор:** `UBXConfigurator(port, baudrate=57600, timeout=2.0)`

**Методы:**

| Метод | Назначение |
|-------|-----------|
| `connect()` / `disconnect()` | Открыть/закрыть порт |
| `get_version()` | Версия прошивки (MON-VER) |
| `configure_uart(port_id, baudrate)` | Скорость/протоколы UART1 |
| `configure_gnss(...)` | Вкл/выкл GPS, GLONASS, Galileo, BeiDou, SBAS. Читает текущий `maxTrkCh` и меняет только `enable`-флаг |
| `configure_sbas(enabled, mode)` | SBAS (EGNOS), `mode`: 1=range, 2=diff, 3=range+diff |
| `configure_nav5(dyn_model, fix_mode, pdop, tdop)` | Динамическая модель, режим фикса, пороги DOP |
| `configure_rate(measurement_interval_ms)` | Частота обновления (мс) |
| `configure_messages(...)` | Набор NMEA (GGA/RMC/GSV/GSA/GLL/VTG) на UART1/USB |
| `save_configuration()` | Сохранить в flash/BBR (`CFG-CFG`, mask=0x000FFFFF) |
| `reset_to_defaults()` | Сброс к заводским (clear+load всех битов) |
| `clear_bbr()` | Очистить BBR (эфемериды/альманах/LastPos) → холодный старт |

> **Внимание (M8):** модуль аппаратно NAK-ует **любой** `CFG-GNSS` SET
> (даже с родными значениями) в ряде прошивок. Для «убитого» GNSS —
> единственный надёжный путь `reset_to_defaults()` (заводской профиль
> уже корректен для региона).

### 4.3 `service_center.py` — оркестратор сервис-центра

#### `detect_baud(port, candidates=...) -> int | None`

Автоопределение скорости UART: первый baud, на котором модуль отвечает
на `MON-VER`.

#### `detect(stream) -> list[dict]`

Считывает конфигурацию (CFG-GNSS/SBAS/NAV5/RATE/PRT/MSG) и возвращает
список отклонений от целевого профиля `TARGET` (Центральная Россия:
мульти-GNSS + SBAS, dynModel=Portable, 1 Гц, стандартный NMEA-набор).
Каждое отклонение: `{"area", "issue", "fix"}`, где `fix` — кортеж для
`apply_fix()`.

#### `apply_fix(cfg: UBXConfigurator, fix) -> bool`

Применяет одну коррекцию. `fix[0]` ∈ `{gnss, sbas, nav5, rate, uart, nmea}`.
Возвращает реальный статус (ACK/NAK), не маскирует сбой.

#### `service_cycle(port, baud=None, do_reset=False, do_clear_bbr=True, save=True) -> bool`

Полный цикл:

1. **Автоопределение скорости** (если `baud=None`).
2. **Диагностика** — `detect()`.
3. **Коррекция** — `apply_fix()` для каждого отклонения.
4. **Запись в память** — `save_configuration()` + `clear_bbr()`.
5. **Верификация** — повторный `detect()` (с жёстким таймаутом 60 с,
   чтобы цикл никогда не зависал).

**CLI:** `python3 service_center.py --port <PORT> [--baud N] [--reset]
[--no-bbr-clear] [--no-save]`

#### Целевой профиль `TARGET` (фрагмент)

```python
TARGET = {
    "baud": 57600,
    "gnss": {0: True, 1: True, 2: True, 3: True, 6: True},  # GPS/SBAS/Gal/BD/GLONASS
    "sbas": {"enabled": True, "mode": 3},                    # range+diff
    "nav5": {"dynModel": 0, "fixMode": 3, "pDop": 25, "tDop": 25},  # DOP 25.0 (заводской дефолт; pyubx2 делит raw на 10)
    "rate": {"measRate": 1000, "navRate": 1, "timeRef": 0},  # 1 Гц, UTC
    "nmea": {0x00: {"uart1":1,"usb":1}, ... },               # GLL..GGA
}
```

### 4.4 `gps_fix_monitor.py`

Монитор захвата фикса по NMEA с авто-переподключением. Показывает сводку
GGA/GSA/GSV раз в 5 с. Не падает при кратковременном исчезновении порта.

### 4.5 `ble_receiver/` — приём NMEA по BLE на ПК

`BleNusClient` (на базе `bleak`) подключается к `ESP32S3-GPS`, собирает
фрагментированные NMEA-строки и передаёт их в колбэк `on_line`.
Конфигурация — через `config.py` / переменные окружения
(`ESP32_DEVICE_MAC`, `ESP32_DEVICE_NAME`).

---

## 5. Примеры использования

### 5.1 Сервис-центр: полный цикл на «подозрительном» модуле

```bash
# 1. Автоопределение скорости + диагностика/коррекция/сохранение
python3 service_center.py --port /dev/ttyUSB0

# 2. Если GNSS «убит» (NAK на CFG-GNSS) — сброс к заводским + целевой профиль
python3 service_center.py --port /dev/ttyUSB0 --reset
```

**Вывод (сокращённо):**
```
АВТООПРЕДЕЛЕНИЕ СКОРОСТИ
  обнаружен baud=9600
1. ДИАГНОСТИКА КОНФИГУРАЦИИ
  выявлено отклонений: 11
   - [NAV5] dynModel=4 (ожид. 0)
   - [RATE] timeRef=1 (ожид. 0)
   - [NMEA] GGA не читается
2. КОРРЕКЦИЯ ВЫЯВЛЕННЫХ ПРОБЛЕМ
   применено: ('nav5', 'dynModel', 0) -> OK
   применено: ('nmea', 5, ...) -> OK
3. ЗАПИСЬ В ЭНЕРГОНЕЗАВИСИМУЮ ПАМЯТЬ
  конфигурация сохранена в flash/BBR (ACK получен).
  BBR очищен - модуль сделает холодный старт.
4. ВЕРИФИКАЦИЯ
  все параметры соответствуют целевому профилю. ОК.
```

### 5.2 Точечная диагностика (без записи)

```bash
python3 service_center.py --port /dev/ttyUSB0 --no-save
```

### 5.3 Чтение конкретного CFG вручную

```python
import serial, gnss_diag as g
s = serial.Serial("/dev/ttyUSB0", 57600, timeout=1)
msgs, _ = g.ubx_poll(s, 0x06, 0x24, 2.0)   # CFG-NAV5
print("dynModel =", msgs[0].dynModel)
```

### 5.4 Мониторинг фикса в реальном времени

```bash
python3 gps_fix_monitor.py --port /dev/ttyUSB0 --baud 57600
```

### 5.5 Приём трека по BLE на ПК

```bash
cd esp32-firmware/tools/ble_receiver
pip install -r requirements.txt
export ESP32_DEVICE_MAC="7C:4F:AD:BB:E2:12"
python3 main.py
```

---

## 6. Troubleshooting и FAQ

### 6.1 Модуль не отвечает ни на одной скорости
- Проверьте питание и целостность кабеля (TX/RX не перепутаны?).
- Убедитесь, что адаптер не в режиме только-на-передачу.
- Попробуйте **power-cycle** модуля (отключить/включить питание) — часть
  модулей «зависают» в неконсистентном состоянии UART после множественных
  CFG-записей и требуют аппаратного сброса.

### 6.2 `ubx_poll` возвращает пусто, хотя модуль жив
- Используйте `UBXReader` (pyubx2), а не `GNSSReader` (pygnssutils):
  последний **тихо отбрасывает класс CFG (0x06)**, поэтому чтение
  конфигурации не работает. В `gnss_diag.ubx_poll` это уже исправлено.
- Убедитесь, что на UART1 разрешён вывод UBX (`outProtoMask` включает UBX).

### 6.3 `CFG-GNSS` всегда NAK
- Аппаратное ограничение ряда прошивок M8: модуль не принимает SET для
  GNSS. Решение — `service_center.py --reset` (загрузка заводского профиля)
  или замена модуля.

### 6.4 Верификация показывает «не устранено», хотя правка применена
- Возможна деградация модуля от множественных NMEA/CFG-циклов в тестах.
  Сделайте power-cycle и повторите. Если повторяется — модуль аппаратно
  не принимает CFG (см. 6.3).

### 6.5 `UBXReader.read()` блокируется
- Обёртка `_read_with_timeout()` в `gnss_diag` страхует через `SIGALRM`
  (работает в главном потоке Linux). Не запускайте `ubx_poll` из
  дочерних потоков без альтернативного таймаута.

### 6.6 Нет фикса, но сигнал реальный (C/N0 ~20–31 dBHz)
- Это не ошибка конфигурации, а уровень сигнала. Вывод модуля на открытое
  небо, качественная активная антенна, экран от ESP32/USB-помех. Сама
  конфигурация модуля не влияет на наличие фикса — сервис-центр приводит
  её в корректное состояние «на столе», без необходимости ловить фикс.

### 6.7 FAQ

**Q: Нужно ли бегать с модулем на улицу для обслуживания?**
A: Нет. Сервис-центр (`service_center.py`) диагностирует и исправляет
конфигурацию, сохраняет её в память и очищает BBR для холодного старта —
всё на рабочем столе. Фикс — задача антенны/поля, не конфигурации.

**Q: Поддерживаются ли M6/M7/M9/M10?**
A: Да, через единый протокол UBX. Старые M6/M7 могут не поддерживать
отдельные опции (например, Galileo) — сервис-центр это корректно помечает.

**Q: Можно ли задать свою целевую конфигурацию?**
A: Да — отредактируйте словарь `TARGET` в `service_center.py`.

---

*Документация сгенерирована на основе актуального состояния исходного кода
проекта `ESP32-GPS-Tracker`. По вопросам — см. `CONTRIBUTING.md`.*
