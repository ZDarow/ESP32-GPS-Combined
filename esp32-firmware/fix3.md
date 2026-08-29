
# Техническое задание: Модуль 2 — BLE Nordic UART Service (NUS)

**Проект:** `C:\Users\Mi\Ublox\esp32s3-gnss-ESP-IDF`
**Плата:** ESP32-S3 DevKitC-1
**Цель модуля:** Транслировать NMEA-данные с NEO-7M на смартфон по Bluetooth Low Energy через стандартный профиль Nordic UART Service. Добавить симулятор координат для тестирования до получения реального GPS-фикса.

---

## 1. Стек технологий

| Компонент | Технология | Примечание |
| :--- | :--- | :--- |
| BLE-стек | **NimBLE** | Включить в `menuconfig`: Component config → Bluetooth → NimBLE |
| Профиль | **Nordic UART Service (NUS)** | Стандартный, поддерживается готовыми Android-приложениями |
| Имя устройства | `ESP32S3-GPS` | Для обнаружения смартфоном |

---

## 2. UUID-схема Nordic UART Service

Использовать стандартные UUID от Nordic Semiconductor:

```c
// Сервис
#define NUS_SERVICE_UUID        "6E400001-B5A3-F393-E0A9-E50E24DCCA9E"

// Характеристики
#define NUS_TX_CHAR_UUID        "6E400003-B5A3-F393-E0A9-E50E24DCCA9E"  // Notify (ESP32 → смартфон)
#define NUS_RX_CHAR_UUID        "6E400002-B5A3-F393-E0A9-E50E24DCCA9E"  // Write (смартфон → ESP32)
```

---

## 3. API модуля `ble_nus`

Создать `main/ble_nus.h`:

```c
#pragma once
#include "esp_err.h"
#include "nmea_parser.h"

// Инициализация BLE-сервера
esp_err_t ble_nus_init(void);

// Запуск рекламмирования (чтобы смартфон увидел устройство)
esp_err_t ble_nus_start_advertising(void);

// Отправка NMEA-строки на подключённый смартфон
// Возвращает ESP_OK если данные отправлены, ESP_FAIL если нет подключения
esp_err_t ble_nus_send_nmea(const char *nmea_str, int len);

// Проверка: есть ли активное BLE-подключение?
bool ble_nus_is_connected(void);
```

---

## 4. Логика работы (критично!)

### 4.1. Реальный фикс vs Симулятор

В `main/main.c` реализовать логику:

```c
static bool s_real_fix_available = false;  // флаг реального фикса
static int64_t s_last_sim_time = 0;        // время последней симуляции

static void on_gps_line(const char *line, int len) {
    gnss_fix_t fix;
    if (nmea_parser_feed(line, len, &fix)) {
        if (fix.valid) {
            // === РЕАЛЬНЫЙ ФИКС: отправляем настоящие данные ===
            s_real_fix_available = true;
            ble_nus_send_nmea(line, len);
            ESP_LOGI(TAG, ">>> REAL FIX sent via BLE: lat=%.6f lon=%.6f",
                     fix.latitude, fix.longitude);
        }
    }
}

// Периодическая задача: если нет реального фикса — шлём симулятор
static void simulator_task(void *arg) {
    while (1) {
        vTaskDelay(pdMS_TO_TICKS(2000));  // каждые 2 секунды
        
        if (!s_real_fix_available && ble_nus_is_connected()) {
            // Генерируем фейковую NMEA-строку
            char fake_nmea[128];
            snprintf(fake_nmea, sizeof(fake_nmea),
                     "$GPRMC,120000,A,4807.038,N,01131.000,E,0.0,0.0,010124,,,A*XX");
            // TODO: пересчитать контрольную сумму XX
            ble_nus_send_nmea(fake_nmea, strlen(fake_nmea));
            ESP_LOGI(TAG, "SIM: sent fake NMEA (no real fix yet)");
        }
    }
}
```

### 4.2. Автоматическое переключение
- При запуске `s_real_fix_available = false` → работает симулятор.
- Как только парсер вернул `fix.valid == true` → симулятор отключается, идут реальные данные.
- Если фикс потерян (статус V) → симулятор снова включается.

---

## 5. Чанкинг (разбиение длинных строк)

BLE MTU по умолчанию = 23 байта (полезных 20). NMEA-строка ~80 байт. Нужно резать на куски.

В `main/ble_nus.c` реализовать:

```c
#define BLE_MTU_CHUNK_SIZE 20

esp_err_t ble_nus_send_nmea(const char *nmea_str, int len) {
    if (!s_connected) return ESP_FAIL;
    
    int offset = 0;
    while (offset < len) {
        int chunk_len = (len - offset) > BLE_MTU_CHUNK_SIZE 
                        ? BLE_MTU_CHUNK_SIZE 
                        : (len - offset);
        
        // Отправляем кусок через NimBLE
        esp_err_t ret = ble_gatts_notify_custom(
            s_conn_handle,
            s_tx_char_handle,
            os_msys_get_pkthdr(chunk_len, 0),
            (uint8_t*)(nmea_str + offset),
            chunk_len
        );
        
        if (ret != ESP_OK) {
            ESP_LOGE(TAG, "BLE send failed at offset %d", offset);
            return ret;
        }
        
        offset += chunk_len;
        vTaskDelay(pdMS_TO_TICKS(10));  // маленькая пауза между чанками
    }
    
    return ESP_OK;
}
```

---

## 6. Интеграция в `main/main.c`

```c
#include "ble_nus.h"

void app_main(void) {
    // Инициализация GPS (Модуль 1)
    ESP_ERROR_CHECK(gps_uart_init());
    nmea_parser_init();
    ESP_ERROR_CHECK(gps_uart_register_callback(on_gps_line));
    ESP_ERROR_CHECK(gps_uart_task_start());
    
    // Инициализация BLE (Модуль 2)
    ESP_ERROR_CHECK(ble_nus_init());
    ESP_ERROR_CHECK(ble_nus_start_advertising());
    
    // Запуск симулятора
    xTaskCreate(simulator_task, "simulator_task", 4096, NULL, 5, NULL);
    
    ESP_LOGI(TAG, "GNSS tracker with BLE started. Waiting for connection...");
}
```

---

## 7. Структура файлов

Добавить в проект:
```
main/
├── ble_nus.c          # BLE-сервер NimBLE + NUS профиль
├── ble_nus.h
├── gps_uart.c         # (уже есть)
├── gps_uart.h         # (уже есть)
├── main.c             # обновить: добавить BLE и симулятор
└── app_config.h       # добавить BLE-константы
```

### Обновление `main/app_config.h`:
```c
// BLE
#define BLE_DEVICE_NAME         "ESP32S3-GPS"
#define BLE_ADV_INTERVAL_MS     500      // интервал рекламмирования
#define BLE_MTU_CHUNK_SIZE      20       // размер чанка для отправки
```

---

## 8. Критерии приёмки

Модуль считается готовым, если:

- [ ] Проект собирается без ошибок (`idf.py build`).
- [ ] После прошивки в мониторе появляется `BLE advertising started`.
- [ ] Смартфон (Redmi Note 9 Pro) видит устройство `ESP32S3-GPS` через приложение **nRF Connect**.
- [ ] При подключении по BLE в nRF Connect видны сервисы `6E400001...` и характеристики.
- [ ] **До получения реального фикса** смартфон получает фейковые NMEA-строки каждые 2 секунды.
- [ ] **После получения реального фикса** симулятор отключается, идут настоящие координаты.
- [ ] Длинные NMEA-строки корректно разбиваются на чанки по 20 байт.
- [ ] При разрыве BLE-соединения рекламмирование возобновляется автоматически.
- [ ] Нет утечек памяти (heap стабилен в течение 10 минут работы).

---

## 9. Тестирование со смартфоном

### 9.1. Установка приложения
На Redmi Note 9 Pro (LineageOS 15) установить из Play Store:
- **nRF Connect** (для тестирования BLE)
- **Bluetooth GNSS** или **SW Maps** (для использования как внешний GPS)

### 9.2. Проверка через nRF Connect
1. Открыть nRF Connect → **Scan**.
2. Найти `ESP32S3-GPS` → **Connect**.
3. Раскрыть сервис `6E400001...`.
4. Подписаться на Notify для характеристики `6E400003...` (TX).
5. В логе должны появиться NMEA-строки (сначала фейковые, потом реальные).

### 9.3. Проверка как внешний GPS
1. В Bluetooth GNSS выбрать устройство `ESP32S3-GPS`.
2. Включить **Mock Location** в настройках разработчика.
3. Открыть OsmAnd или Яндекс.Карты — должна появиться точка (сначала фейковая, потом реальная).

---

## 10. Типичные проблемы

| Проблема | Решение |
| :--- | :--- |
| Смартфон не видит устройство | Проверить, что `ble_nus_start_advertising()` вызван. В nRF Connect нажать Scan заново |
| Подключение есть, но данных нет | Проверить, что подписка на Notify включена в nRF Connect |
| Данные приходят битыми | Проблема с чанкингом. Увеличить паузу между чанками до 20 мс |
| `ble_gatts_notify_custom` возвращает ошибку | Проверить, что `s_conn_handle` валиден (подключение активно) |
| Симулятор не отключается при фиксе | Проверить флаг `s_real_fix_available` в `on_gps_line` |
| NimBLE не компилируется | Включить в `menuconfig`: Component config → Bluetooth → Enable Bluetooth → NimBLE |

---

## 11. Проактивные рекомендации

1. **Контрольная сумма NMEA.** В симуляторе нужно пересчитывать контрольную сумму (XX после `*`). Иначе парсер на смартфоне отбросит строку. Реализовать функцию:
   ```c
   uint8_t nmea_checksum(const char *str) {
       uint8_t sum = 0;
       while (*str && *str != '*') sum ^= *str++;
       return sum;
   }
   ```

2. **Энергосбережение BLE.** После успешного подключения увеличить интервал Connection Interval до 100-200 мс (в NimBLE через `ble_gap_conn_params`).

3. **Индикация подключения.** Добавить светодиод (например, встроенный на ESP32-S3), который мигает при рекламмировании и горит постоянно при подключении.

4. **Логирование BLE-событий.** Добавить колбэки на connect/disconnect:
   ```c
   static int ble_gap_event(struct ble_gap_event *event, void *arg) {
       switch (event->type) {
           case BLE_GAP_EVENT_CONNECT:
               ESP_LOGI(TAG, "BLE connected");
               s_connected = true;
               break;
           case BLE_GAP_EVENT_DISCONNECT:
               ESP_LOGI(TAG, "BLE disconnected");
               s_connected = false;
               ble_nus_start_advertising();  // возобновить рекламу
               break;
       }
       return 0;
   }
   ```

---

## 12. Следующие шаги

После успешной реализации Модуля 2:
1. Протестировать связку ESP32-S3 + Redmi Note 9 Pro.
2. Убедиться, что симулятор работает, а при появлении реального фикса данные переключаются.
3. Переходить к **Модулю 3: Power Manager** (Deep Sleep, экономия заряда 18650).
