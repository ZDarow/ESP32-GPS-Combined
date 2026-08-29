# Техническое задание: Модуль 1 — UART-драйвер NEO-7M + NMEA-парсер

**Проект:** `C:\Users\Mi\Ublox\esp32s3-gnss-ESP-IDF`
**Плата:** ESP32-S3 DevKitC-1 (Rev 2, 16MB QIO, без PSRAM)
**Цель модуля:** Стабильно читать NMEA-поток с NEO-7M по UART и преобразовывать его в структурированные координаты для дальнейшего использования (BLE, логгер, сон).

---

## 1. Конфигурация пинов и UART

| Параметр | Значение |
| :--- | :--- |
| UART | **UART_NUM_1** (UART0 занят под лог) |
| GPS TX → ESP32 RX | **GPIO18** |
| ESP32 TX → GPS RX | **GPIO17** |
| Baud rate | **9600** |
| Формат | 8N1 (8 бит, без чётности, 1 стоп) |
| RX buffer | 2048 байт (кольцевой) |
| TX buffer | 0 (не нужен, GPS только слушаем) |

### 1.1. Определения в `main/app_config.h`
```c
#pragma once

// GPS UART
#define GPS_UART_NUM        UART_NUM_1
#define GPS_UART_TX_PIN     17
#define GPS_UART_RX_PIN     18
#define GPS_UART_BAUD       9600
#define GPS_UART_RX_BUF     2048

// Таймауты
#define GPS_DATA_TIMEOUT_MS 5000   // нет данных 5 сек -> нет фикса
```

---

## 2. Структура данных фикса

Создать в `components/nmea_parser/include/nmea_parser.h`:

```c
typedef enum {
    GNSS_FIX_NONE = 0,     // Нет данных / нет сигнала
    GNSS_FIX_2D,           // Фикс без высоты
    GNSS_FIX_3D            // Полный фикс с высотой
} gnss_fix_type_t;

typedef struct {
    gnss_fix_type_t type;      // Тип фикса
    bool valid;                // Данные валидны (по RMC статус A)
    double latitude;           // Широта в градусах (+N, -S)
    double longitude;          // Долгота в градусах (+E, -W)
    double altitude_m;         // Высота над уровнем моря, метры (GGA)
    double speed_kmh;          // Скорость, км/ч (RMC, узлы * 1.852)
    double course_deg;         // Курс, градусы (RMC)
    uint8_t satellites_used;   // Кол-во спутников (GGA)
    uint8_t fix_quality;       // 0=нет, 1=GPS, 2=DGPS (GGA)
    double hdop;               // Точность по горизонтали (GGA)
    int64_t last_update_ms;    // esp_timer_get_time()/1000 последнего фикса
} gnss_fix_t;
```

---

## 3. API модулей

### 3.1. `main/gps_uart.h` — UART-драйвер
```c
#include "esp_err.h"

typedef void (*gps_line_callback_t)(const char *line, int len);

esp_err_t gps_uart_init(void);              // Инициализация UART1
esp_err_t gps_uart_register_callback(gps_line_callback_t cb);  // Колбэк на полную строку
esp_err_t gps_uart_task_start(void);        // Запуск задачи чтения (FreeRTOS)
```

**Логика задачи чтения:**
- Читать байты через `uart_read_bytes()` в цикле.
- Собирать в накопительный буфер до символа `\n`.
- При получении полной строки (завершается `\r\n`) — вызвать колбэк с этой строкой.
- Отбрасывать строки длиннее 120 байт (защита от мусора).

### 3.2. `components/nmea_parser/include/nmea_parser.h` — парсер
```c
#include "nmea_parser.h"

void nmea_parser_init(void);
bool nmea_parser_feed(const char *sentence, int len, gnss_fix_t *out_fix);
```

**Требования к парсеру:**
- Проверять контрольную сумму NMEA (`$...*XX`, где XX = XOR всех байт между `$` и `*`). При несовпадении — игнорировать строку.
- Парсить **$GPGGA** → высота, спутники, качество фикса, HDOP.
- Парсить **$GPRMC** → валидность (A/V), широта, долгота, скорость, курс, дата/время.
- Поддерживать также префиксы `$GNGGA` / `$GNRMC` (мульти-системные сообщения от NEO-7M).
- Конвертация координат NMEA → градусы: `DDMM.MMMM` → `DD + MM.MMMM/60`.
- Парсер должен быть **потокобезопасным** (использовать mutex или делать stateless на одну строку).

---

## 4. Интеграция в `main/main.c`

```c
#include "gps_uart.h"
#include "nmea_parser.h"
#include "esp_log.h"

static const char *TAG = "MAIN";

static void on_gps_line(const char *line, int len) {
    gnss_fix_t fix;
    if (nmea_parser_feed(line, len, &fix) && fix.valid) {
        ESP_LOGI(TAG, "FIX: lat=%.6f lon=%.6f alt=%.1fm sat=%u spd=%.1fkm/h",
                 fix.latitude, fix.longitude, fix.altitude_m,
                 fix.satellites_used, fix.speed_kmh);
    }
}

void app_main(void) {
    ESP_ERROR_CHECK(gps_uart_init());
    nmea_parser_init();
    ESP_ERROR_CHECK(gps_uart_register_callback(on_gps_line));
    ESP_ERROR_CHECK(gps_uart_task_start());
    ESP_LOGI(TAG, "GNSS tracker module 1 started");
}
```

---

## 5. Обработка ошибок и таймаут

- Если в течение `GPS_DATA_TIMEOUT_MS` не пришло ни одной валидной строки — вывести `ESP_LOGW(TAG, "GPS timeout: no data")`.
- Если приходят данные, но `RMC` статус `V` (нет фикса) — периодически (раз в 5 сек) логировать `"Waiting for fix..."`.
- Не блокировать `app_main()` — вся работа в отдельной FreeRTOS-задаче.

---

## 6. CMakeLists для компонента

`components/nmea_parser/CMakeLists.txt`:
```cmake
idf_component_register(
    SRCS "src/nmea_parser.c"
    INCLUDE_DIRS "include"
)
```

---

## 7. Критерии приёмки

Модуль считается готовым, если:

- [ ] Проект собирается без ошибок и предупреждений (`idf.py build`).
- [ ] При подключённом NEO-7M в мониторе появляются сырые NMEA-строки в логе.
- [ ] После выхода на открытое пространство через 1–3 минуты появляются строки `FIX: lat=... lon=...`.
- [ ] Координаты совпадают с реальным местоположением (проверить по карте с точностью до квартала).
- [ ] Парсер корректно отбрасывает строки с битой контрольной суммой.
- [ ] При отключении GPS через 5 секунд появляется `GPS timeout: no data`.
- [ ] Нет утечек памяти (свободный heap стабилен в течение 5 минут работы).

---

## 8. Тестирование

### 8.1. Сборка и прошивка
```powershell
cd C:\Users\Mi\Ublox\esp32s3-gnss-ESP-IDF
idf.py -p COM3 build flash monitor
```

### 8.2. Проверка без GPS (имитация)
Если GPS-модуль ещё не подключён, можно временно подавать в UART1 тестовые строки с другого USB-UART адаптера:
```
$GPRMC,123519,A,4807.038,N,01131.000,E,022.4,084.4,230394,003.1,W*6A
$GPGGA,123519,4807.038,N,01131.000,E,1,08,0.9,545.4,M,46.9,M,,*47
```

### 8.3. Проверка с реальным GPS
1. Подключить NEO-7M: `GPS_TX → GPIO18`, `GPS_RX → GPIO17`, питание 3.3V.
2. Вынести антенну к окну.
3. В мониторе ожидать появления `FIX: ...`.

---

## 9. Типичные проблемы

| Проблема | Решение |
| :--- | :--- |
| В мониторе тишина | Перепроверить подключение TX/RX (GPS_TX → ESP32_RX). Это самая частая ошибка |
| Кракозябры в логе | Несоответствие baud rate. Проверить, что GPS точно на 9600 (u-center) |
| Строки есть, но парсер молчит | Проверить контрольную сумму и префиксы (GPGGA vs GNGGA) |
| Фикс не появляется | GPS нужен вид на небо. Вынести к окну, дать 3-5 минут на холодный старт |
| `uart_read_bytes` блокирует надолго | Уменьшить `portTICK_PERIOD_MS` таймаут в `uart_read_bytes` до 100 мс |

---

## 10. Проактивные рекомендации

1. **Не хардкодить GPIO** — все пины только через `app_config.h`.
2. **Использовать `ESP_LOGx`**, а не `printf` — для единообразия и фильтрации.
3. **Сделать парсер stateless** — одна строка на входе, один фикс на выходе. Это упростит тестирование.
4. **Добавить модульный тест** для парсера в `components/nmea_parser/test/` с фиксированными NMEA-строками (Unity-тесты ESP-IDF).
5. **После успешного фикса** — залогировать полный дамп всех полей один раз для отладки.
