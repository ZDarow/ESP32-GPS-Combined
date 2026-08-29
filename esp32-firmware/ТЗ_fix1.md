# Техническое задание: Диагностика и перепрошивка ESP32-S3 для работы с NEO-7M

**Проект:** `C:\Users\Mi\Ublox\esp32s3-gnss-ESP-IDF`
**Плата:** ESP32-S3 DevKitC-1, порт `COM3`
**Условия:** Модуль NEO-7M стационарен, перемещение невозможно. Сигнал средний (12 спутников, SNR 16–27), фикс может появляться с задержкой.

---

## 1. Цель

1. **Подтвердить**, что ESP32-S3 физически получает данные с NEO-7M по UART.
2. **Добавить детальную диагностику** в прошивку: счётчики байт, строк, NMEA-сообщений.
3. **Обеспечить корректную работу** в режиме «нет фикса»: прошивка должна показывать, что данные идут, даже если координат ещё нет.
4. **Подготовить базу** для автоматического захвата фикса, как только он станет доступен.

---

## 2. Часть А: Аппаратная проверка (до перепрошивки)

⚠️ Раз ранее данные не шли через ESP32, но шли через PuTTY — **с вероятностью 90% проблема в разводке**. Перед перепрошивкой проверь:

| Проверка | Что сделать |
| :--- | :--- |
| **TX/RX крест-накрест** | `GPS TXD` → `ESP32 GPIO18` (RX), `GPS RXD` → `ESP32 GPIO17` (TX) |
| **Общая земля** | `GPS GND` соединён с `ESP32 GND` |
| **Питание** | `GPS VCC` → `3.3V` ESP32 (не 5V!) |
| **Провода** | Короткие, без скруток; TX/RX не перепутаны на самом модуле |

💡 *Проактивно:* если модуль зафиксирован и ты не можешь его двигать, убедись, что провода до ESP32 надёжны. Плохой контакт GND — частая причина «тишины» в UART.

---

## 3. Часть Б: Перепрошивка с расширенной диагностикой

### 3.1. Обновление `main/app_config.h`

Добавь флаг включения сырой отладки:

```c
#pragma once

// GPS UART
#define GPS_UART_NUM        UART_NUM_1
#define GPS_UART_TX_PIN     17
#define GPS_UART_RX_PIN     18
#define GPS_UART_BAUD       9600
#define GPS_UART_RX_BUF     2048

// Диагностика
#define GPS_DATA_TIMEOUT_MS 5000    // таймаут отсутствия данных
#define GPS_RAW_DEBUG       1       // 1 = печатать каждый байт, 0 = выключить
#define GPS_RAW_DEBUG_LIMIT 200     // макс. байт для RAW-вывода (защита от спама)
```

### 3.2. Замена `main/gps_uart.c` на диагностическую версию

```c
#include "gps_uart.h"
#include "app_config.h"
#include "driver/uart.h"
#include "driver/gpio.h"
#include "esp_log.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include <string.h>

static const char *TAG = "GPS_UART";

// === Диагностика: счётчики ===
static uint32_t s_bytes_total   = 0;   // всего байт принято
static uint32_t s_lines_total   = 0;   // всего строк
static uint32_t s_nmea_total    = 0;   // валидных NMEA-строк
static uint32_t s_raw_printed   = 0;   // сколько байт выведено в RAW

static char s_line_buf[128];
static int  s_line_pos = 0;
static gps_line_callback_t s_callback = NULL;

static void gps_uart_task(void *arg) {
    uint8_t rx_byte;
    int64_t last_data_time = esp_timer_get_time();
    int64_t last_stats_time = esp_timer_get_time();

    ESP_LOGI(TAG, "Diagnostic task started. Waiting for GPS data...");

    while (1) {
        int len = uart_read_bytes(GPS_UART_NUM, &rx_byte, 1, pdMS_TO_TICKS(100));

        if (len > 0) {
            s_bytes_total++;
            last_data_time = esp_timer_get_time();

            // === RAW-вывод байта (для диагностики) ===
            #if GPS_RAW_DEBUG
            if (s_raw_printed < GPS_RAW_DEBUG_LIMIT) {
                ESP_LOGI(TAG, "RAW[%u]: 0x%02X '%c'",
                         s_raw_printed, rx_byte,
                         (rx_byte >= 32 && rx_byte < 127) ? rx_byte : '.');
                s_raw_printed++;
                if (s_raw_printed == GPS_RAW_DEBUG_LIMIT) {
                    ESP_LOGW(TAG, "RAW debug limit reached. Further bytes not printed.");
                }
            }
            #endif

            // === Накопление строки ===
            if (rx_byte == '\n' || s_line_pos >= (int)sizeof(s_line_buf) - 1) {
                s_line_buf[s_line_pos] = '\0';
                if (s_line_pos > 0 && s_line_buf[s_line_pos - 1] == '\r') {
                    s_line_buf[s_line_pos - 1] = '\0';
                }
                s_lines_total++;

                // Проверяем, что это NMEA-строка
                if (s_line_buf[0] == '$') {
                    s_nmea_total++;
                    // Печатаем первые 10 NMEA-строк для контроля
                    if (s_nmea_total <= 10) {
                        ESP_LOGI(TAG, "NMEA[%u]: %s", s_nmea_total, s_line_buf);
                    }
                }

                // Передаём в парсер
                if (s_callback && s_line_pos > 0) {
                    s_callback(s_line_buf, s_line_pos);
                }
                s_line_pos = 0;

            } else if (rx_byte != '\r') {
                s_line_buf[s_line_pos++] = rx_byte;
            }

        } else {
            // === Нет данных: проверяем таймаут ===
            int64_t now = esp_timer_get_time();
            if ((now - last_data_time) > (int64_t)GPS_DATA_TIMEOUT_MS * 1000) {
                ESP_LOGW(TAG, "*** NO DATA for %d ms! Total bytes: %u. "
                              "CHECK WIRING: TX/RX/GND! ***",
                         GPS_DATA_TIMEOUT_MS, s_bytes_total);
                last_data_time = now;  // не спамим
            }
        }

        // === Периодическая статистика раз в 5 сек ===
        int64_t now = esp_timer_get_time();
        if ((now - last_stats_time) > 5000000) {
            ESP_LOGI(TAG, "=== STATS: bytes=%u | lines=%u | nmea=%u ===",
                     s_bytes_total, s_lines_total, s_nmea_total);
            last_stats_time = now;
        }
    }
}

esp_err_t gps_uart_init(void) {
    uart_config_t cfg = {
        .baud_rate  = GPS_UART_BAUD,
        .data_bits  = UART_DATA_8_BITS,
        .parity     = UART_PARITY_DISABLE,
        .stop_bits  = UART_STOP_BITS_1,
        .flow_ctrl  = UART_HW_FLOWCTRL_DISABLE,
        .source_clk = UART_SCLK_DEFAULT,
    };
    ESP_ERROR_CHECK(uart_driver_install(GPS_UART_NUM, GPS_UART_RX_BUF, 0, 0, NULL, 0));
    ESP_ERROR_CHECK(uart_param_config(GPS_UART_NUM, &cfg));
    ESP_ERROR_CHECK(uart_set_pin(GPS_UART_NUM, GPS_UART_TX_PIN, GPS_UART_RX_PIN,
                                 UART_PIN_NO_CHANGE, UART_PIN_NO_CHANGE));
    ESP_LOGI(TAG, "UART1 init: TX=%d RX=%d baud=%d", GPS_UART_TX_PIN, GPS_UART_RX_PIN, GPS_UART_BAUD);
    return ESP_OK;
}

esp_err_t gps_uart_register_callback(gps_line_callback_t cb) {
    s_callback = cb;
    return ESP_OK;
}

esp_err_t gps_uart_task_start(void) {
    xTaskCreate(gps_uart_task, "gps_uart_task", 4096, NULL, 5, NULL);
    ESP_LOGI(TAG, "GPS UART task started");
    return ESP_OK;
}
```

### 3.3. Обновление `main/main.c` (вывод статуса при отсутствии фикса)

```c
#include "gps_uart.h"
#include "nmea_parser.h"
#include "esp_log.h"
#include "esp_timer.h"

static const char *TAG = "MAIN";
static int64_t s_last_fix_time = 0;
static uint32_t s_fix_count = 0;

static void on_gps_line(const char *line, int len) {
    gnss_fix_t fix;
    if (nmea_parser_feed(line, len, &fix)) {
        if (fix.valid) {
            s_fix_count++;
            s_last_fix_time = esp_timer_get_time();
            ESP_LOGI(TAG, ">>> FIX #%u: lat=%.6f lon=%.6f alt=%.1fm sat=%u spd=%.1fkm/h",
                     s_fix_count, fix.latitude, fix.longitude, fix.altitude_m,
                     fix.satellites_used, fix.speed_kmh);
        } else {
            // Данные есть, но фикса нет — сообщаем раз в 10 сек
            static int64_t last_wait_msg = 0;
            int64_t now = esp_timer_get_time();
            if ((now - last_wait_msg) > 10000000) {
                ESP_LOGW(TAG, "Data received but NO FIX yet (status V). Waiting for satellites...");
                last_wait_msg = now;
            }
        }
    }
}

void app_main(void) {
    ESP_ERROR_CHECK(gps_uart_init());
    nmea_parser_init();
    ESP_ERROR_CHECK(gps_uart_register_callback(on_gps_line));
    ESP_ERROR_CHECK(gps_uart_task_start());
    ESP_LOGI(TAG, "GNSS tracker started. Module is stationary — waiting for fix...");
}
```

---

## 4. Часть В: Сборка, прошивка, интерпретация

### 4.1. Сборка и прошивка
```powershell
cd C:\Users\Mi\Ublox\esp32s3-gnss-ESP-IDF
idf.py -p COM3 build flash monitor
```

### 4.2. Таблица интерпретации результата

| Что видно в мониторе | Диагноз | Действие |
| :--- | :--- | :--- |
| `NO DATA ... Total bytes: 0` | ESP32 не получает ни байта | Проверить TX/RX/GND, переподключить |
| `RAW` байты идут, но `nmea=0` | Данные приходят, но не распознаны | Проверить baudrate (9600) |
| `NMEA[1]: $GPGGA...` появились | UART работает, данные идут | ✅ Подключение верное |
| `Data received but NO FIX` | Данные идут, фикса нет | Нормально для стационарного модуля — ждать |
| `>>> FIX #1: lat=... lon=...` | Полная победа | 🎉 Переходим к Модулю 2 (BLE) |

---

## 5. Критерии приёмки

- [ ] Проект собирается без ошибок (`idf.py build`).
- [ ] В мониторе появляется статистика `=== STATS: bytes=... ===`.
- [ ] При корректной разводке `bytes` растёт, появляются строки `NMEA[...]`.
- [ ] При отключённом GPS через 5 секунд выводится `*** NO DATA ... CHECK WIRING ***`.
- [ ] При наличии данных, но отсутствии фикса выводится `NO FIX yet`.
- [ ] При получении фикса выводится `>>> FIX #1: lat=... lon=...`.

---

## 6. Проактивные рекомендации

1. **Активная антенна.** Раз модуль нельзя переместить, а сигнал средний (SNR 16–27), рассмотри **активную GPS-антенну с усилителем** (питается от 3.3V/5V, подключение через разъем U.FL/IPEX на NEO-7M). Это может кардинально улучшить захват в помещении.

2. **Терпение при холодном старте.** В стационарных условиях первый фикс может занять **15–25 минут**. Не прерывай питание в это время.

3. **Отключи RAW-отладку после диагностики.** Когда убедишься, что данные идут, поставь в `app_config.h`:
   ```c
   #define GPS_RAW_DEBUG 0
   ```
   Иначе лог будет заспамлен (9600 бод ≈ 960 байт/сек).

4. **Батарейка V_BCKP.** Как только получишь первый фикс — подключи батарейку/ионистор к `V_BCKP` (мы обсуждали ранее). Тогда каждый следующий старт будет горячим (1–3 сек вместо 15 минут).

---
