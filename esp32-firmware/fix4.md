```text
# ТЗ: Исправление отправки данных по BLE NUS (NimBLE) на ESP32-S3

## 1. Контекст проблемы
Стек BLE NimBLE на ESP32-S3 инициализирован корректно. Смартфон (nRF Connect) успешно подключается, обнаруживает Nordic UART Service (NUS) и успешно записывает `0x0100` в CCCD дескриптор (0x2902) для включения Notifications. 
ОДНАКО, ESP32 не отправляет никакие данные в эфир после включения уведомлений.

## 2. Root Cause (выявлено)
Проблема была в **тайминге инициализации** хендлов характеристик:

1. `ble_gatts_add_svcs()` регистрирует сервисы асинхронно — колбэк `ble_nus_gatts_register_cb` вызывается позже
2. Переменные `s_tx_val_handle`/`s_rx_val_handle` заполняются внутри этого колбэка
3. Но строки `s_tx_char_handle = s_tx_val_handle;` выполнялись **сразу** после `ble_gatts_add_svcs()`, когда `s_tx_val_handle` ещё был 0
4. В результате `s_tx_char_handle` оставался 0, и `ble_gatts_notify_custom()` падал с `rc=3` (invalid handle)

## 3. Исправление
Убраны промежуточные переменные `s_tx_char_handle`/`s_rx_char_handle`. Теперь используется напрямую `s_tx_val_handle`/`s_rx_val_handle`, которые корректно заполняются в `ble_nus_gatts_register_cb` через сравнение UUID.

### Ключевые изменения в `main/ble_nus.c`:
- Удалены `s_tx_char_handle` и `s_rx_char_handle`
- В `ble_nus_gatts_register_cb` используется `memcmp` по UUID вместо флагов
- В `ble_nus_send_nmea()` и `ble_nus_gap_event()` используется `s_tx_val_handle` напрямую

## 2. Задачи для агента (Исправить `main/ble_nus.c` и `main/main.c`)

### Задача 2.1: Обработка события SUBSCRIBE в GAP Event Handler
В функции-обработчике событий GAP (обычно `ble_gap_event` или `gap_event_handler`) необходимо добавить явную обработку `BLE_GAP_EVENT_SUBSCRIBE`.
```c
case BLE_GAP_EVENT_SUBSCRIBE:
    ESP_LOGI(TAG, "SUBSCRIBE event: conn_handle=%d, attr_handle=%d, cur_notify=%d", 
             event->subscribe.conn_handle, 
             event->subscribe.attr_handle, 
             event->subscribe.cur_notify);
    
    // Сравниваем attr_handle с хендлом нашей TX характеристики
    if (event->subscribe.attr_handle == gatt_svr_chr_tx_val_handle) { // (имя переменной хендла уточнить в коде)
        s_is_subscribed = (event->subscribe.cur_notify != 0);
        ESP_LOGI(TAG, ">>> Client notifications %s!", s_is_subscribed ? "ENABLED" : "DISABLED");
    }
    break;
```

### Задача 2.2: "Грязный хак" для гарантии отправки (Временно)
Чтобы исключить проблему с флагами, в функции `ble_nus_send_nmea()` временно убрать жесткую проверку `s_is_subscribed` и отправлять данные просто по факту наличия `conn_handle`.
```c
esp_err_t ble_nus_send_nmea(const char *nmea_str, int len) {
    if (s_conn_handle == BLE_HS_CONN_HANDLE_NONE) {
        ESP_LOGW(TAG, "Send failed: not connected");
        return ESP_FAIL;
    }

    // ВРЕМЕННО: игнорируем s_is_subscribed для диагностики
    // if (!s_is_subscribed) return ESP_OK; 

    ESP_LOGI(TAG, "Sending NMEA: len=%d, conn=%d", len, s_conn_handle);
    
    // ... логика чанкинга ...
```

### Задача 2.3: Детальное логирование отправки и чанкинга
Внутри цикла чанкинга (разбиения строки на куски по MTU) добавить логирование каждого вызова NimBLE API:
```c
int mtu = ble_att_mtu(s_conn_handle);
int chunk_size = (mtu > 23) ? (mtu - 3) : 20; // Стандартный расчет payload

for (int offset = 0; offset < len; offset += chunk_size) {
    int current_chunk = (len - offset > chunk_size) ? chunk_size : (len - offset);
    
    struct os_mbuf *om = ble_hs_mbuf_from_flat((uint8_t*)(nmea_str + offset), current_chunk);
    if (!om) {
        ESP_LOGE(TAG, "Failed to allocate mbuf!");
        return ESP_FAIL;
    }

    int rc = ble_gatts_notify_custom(s_conn_handle, gatt_svr_chr_tx_val_handle, om);
    if (rc != 0) {
        ESP_LOGE(TAG, "ble_gatts_notify_custom FAILED! rc=%d", rc);
    } else {
        ESP_LOGI(TAG, "Chunk sent OK: %d bytes", current_chunk);
    }
    vTaskDelay(pdMS_TO_TICKS(10)); // Пауза, чтобы не забить буфер контроллера
}
```

### Задача 2.4: Диагностика задачи-симулятора в `main.c`
Убедиться, что `simulator_task` реально выполняется и вызывает `ble_nus_send_nmea`.
```c
void simulator_task(void *arg) {
    ESP_LOGI(TAG, "Simulator task started");
    while (1) {
        vTaskDelay(pdMS_TO_TICKS(1000)); // Уменьшить до 1 сек для теста
        
        ESP_LOGI(TAG, "Simulator tick: connected=%d", ble_nus_is_connected());
        
        if (ble_nus_is_connected()) {
            const char *fake_nmea = "$GPRMC,120000,A,4807.038,N,01131.000,E,0.0,0.0,010124,,,A*77\r\n";
            esp_err_t ret = ble_nus_send_nmea(fake_nmea, strlen(fake_nmea));
            ESP_LOGI(TAG, "Simulator send result: %s", esp_err_to_name(ret));
        }
    }
}
```

## 3. Критерии приёмки кода от агента
1. В `ble_nus.c` добавлен `case BLE_GAP_EVENT_SUBSCRIBE`.
2. В `ble_nus.c` используется `ble_hs_mbuf_from_flat` и `ble_gatts_notify_custom` с обязательным логированием кода возврата `rc`.
3. В `main.c` симулятор выводит `Simulator tick` каждую секунду.
4. Код компилируется без предупреждений (warnings) со стороны NimBLE API.

## 4. Инструкции по генерации
- Выдай полный обновленный код файлов `main/ble_nus.c` и `main/main.c`.
- Не меняй архитектуру, только добавь недостающие обработчики событий NimBLE и отладочные логи.
- Убедись, что хендл TX характеристики (который сравнивается в SUBSCRIBE) корректно сохраняется при регистрации сервиса (в `gatt_svr_chr_access` или при инициализации).
```

***

### 💡 Что делать дальше:
1. Скинь это ТЗ агенту.
2. Залей полученный код на плату.
3. Открой монитор (`idf.py monitor`) **и** nRF Connect на телефоне.
4. Подключись и нажми Enable Notifications.

**Смотри в монитор ESP32:**
* Если появится `>>> Client notifications ENABLED!` — значит мы поймали событие.
* Если появится `Simulator tick`, а затем `ble_gatts_notify_custom FAILED! rc=X` — скопируй мне код ошибки `rc`, я мгновенно скажу, что не так (обычно это `rc=3` (нет подключения) или `rc=7` (нет памяти mbuf)).
* Если появится `Chunk sent OK` — смотри в телефон, данные **100% придут**.

Жду результатов теста! 😉