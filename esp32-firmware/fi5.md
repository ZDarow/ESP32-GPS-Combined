# ТЗ: Исправление ble_gatts_notify_custom rc=3 (att_handle=0)

## Корневая проблема (подтверждено логом)
При вызове ble_gatts_notify_custom() передаётся att_handle=0 вместо реального 
val_handle TX характеристики. Ошибка rc=3 (BLE_HS_ENOENT).

Из лога регистрации известно:
- TX характеристика 6e400003 имеет val_handle=16
- RX характеристика 6e400002 имеет val_handle=19

Но в переменной s_tx_char_handle (или аналогичной) хранится 0.

## Задача 1: Сохранить val_handle при регистрации GATT-сервиса

В callback'е регистрации GATT (обычно gatt_svr_register_cb или аналогичном) 
добавить обработку BLE_GATT_REGISTER_OP_CHR:

```c
static int
gatt_svr_register_cb(struct ble_gatt_register_ctxt *ctxt, void *arg)
{
    switch (ctxt->op) {
    case BLE_GATT_REGISTER_OP_SVC:
        ESP_LOGI(TAG, "registered service with handle=%d", ctxt->svc.handle);
        break;

    case BLE_GATT_REGISTER_OP_CHR:
        ESP_LOGI(TAG, "registering characteristic with def_handle=%d val_handle=%d",
                 ctxt->chr.def_handle, ctxt->chr.val_handle);
        
        // === ДОБАВИТЬ ЭТО: сохранить val_handle для TX характеристики ===
        // Сравниваем UUID с UUID TX характеристики NUS
        // Если используется 128-bit UUID, сравниваем байты:
        // 6e400003-b5a3-f393-e0a9-e50e24dcca9e
        if (ctxt->chr.def->uuid.u.type == BLE_UUID_TYPE_128) {
            // Последний 16-bit сегмент UUID: 0xccae для TX, 0xccad для RX
            // Или сравниваем по известным байтам UUID NUS TX
            // Самый надёжный способ - сравнить полное значение UUID
            const ble_uuid128_t nus_tx_uuid = 
                BLE_UUID128_INIT(0x9e, 0xca, 0xdc, 0x24, 0x0e, 0xe5, 0xa9, 0xe0,
                                 0x93, 0xf3, 0xa3, 0xb5, 0x03, 0x00, 0x40, 0x6e);
            const ble_uuid128_t nus_rx_uuid = 
                BLE_UUID128_INIT(0x9e, 0xca, 0xdc, 0x24, 0x0e, 0xe5, 0xa9, 0xe0,
                                 0x93, 0xf3, 0xa3, 0xb5, 0x02, 0x00, 0x40, 0x6e);
            
            ble_uuid128_t *chr_uuid = (ble_uuid128_t *)ctxt->chr.def->uuid;
            
            if (memcmp(chr_uuid->value, nus_tx_uuid.value, 16) == 0) {
                s_tx_char_handle = ctxt->chr.val_handle;
                ESP_LOGI(TAG, ">>> TX char handle saved: %d", s_tx_char_handle);
            }
            if (memcmp(chr_uuid->value, nus_rx_uuid.value, 16) == 0) {
                s_rx_char_handle = ctxt->chr.val_handle;
                ESP_LOGI(TAG, ">>> RX char handle saved: %d", s_rx_char_handle);
            }
        }
        break;

    case BLE_GATT_REGISTER_OP_DSC:
        ESP_LOGI(TAG, "registering descriptor with handle=%d", ctxt->dsc.handle);
        break;

    default:
        break;
    }
    return 0;
}
```

ВАЖНО: Если в коде UUID хранится в другом порядке байт (big-endian vs little-endian), 
нужно адаптировать сравнение. Самый простой способ - вывести UUID в лог при регистрации:
```c
char uuid_str[BLE_UUID_STR_LEN];
ble_uuid_to_str(ctxt->chr.def->uuid, uuid_str);
ESP_LOGI(TAG, "Registering char UUID: %s, val_handle=%d", uuid_str, ctxt->chr.val_handle);
```
И затем сравнить строки или использовать тот же макрос BLE_UUID128, что и в определении сервиса.

## Задача 2: Проверить инициализацию глобальных переменных

Убедиться, что переменные объявлены и инициализированы:
```c
static uint16_t s_tx_char_handle = 0;   // Хендл значения TX характеристики
static uint16_t s_rx_char_handle = 0;   // Хендл значения RX характеристики
static uint16_t s_conn_handle = BLE_HS_CONN_HANDLE_NONE;
static bool s_connected = false;
```

## Задача 3: Использовать сохранённый хендл в ble_nus_send_nmea()

В функции отправки добавить проверку хендла ПЕРЕД вызовом notify:
```c
esp_err_t ble_nus_send_nmea(const char *nmea_str, int len) {
    if (!s_connected || s_conn_handle == BLE_HS_CONN_HANDLE_NONE) {
        ESP_LOGW(TAG, "send_nmea: not connected");
        return ESP_FAIL;
    }
    
    // === ДОБАВИТЬ ПРОВЕРКУ ХЕНДЛА ===
    if (s_tx_char_handle == 0) {
        ESP_LOGE(TAG, "send_nmea: TX char handle is 0! GATT registration failed?");
        return ESP_FAIL;
    }
    
    ESP_LOGI(TAG, "Sending NMEA: len=%d, conn=%d, tx_handle=%d, mtu=%d", 
             len, s_conn_handle, s_tx_char_handle, ble_att_mtu(s_conn_handle));
    
    // ... логика чанкинга ...
    // В вызове ble_gatts_notify_custom использовать s_tx_char_handle:
    int rc = ble_gatts_notify_custom(s_conn_handle, s_tx_char_handle, om);
    // ...
}
```

## Задача 4: Убрать дублирование GAP event listener

В логе видно, что каждое GAP-событие обрабатывается дважды.
Найти в коде место, где назначается GAP callback (обычно в ble_hs_cfg.sync_cb 
или при инициализации), и убедиться, что оно вызывается ОДИН раз.
Если есть два вызова ble_gap_event_register или два назначения listener'а - убрать один.

## Задача 5: Отладочный вывод после исправления

После применения правок в логе монитора должно появиться:
```
>>> TX char handle saved: 16
```
И при попытке отправки:
```
Sending NMEA: len=62, conn=1, tx_handle=16, mtu=23
```
Если всё верно, rc=0 и данные уйдут в эфир.

## Критерии приёмки
1. При старте в логе появляется "TX char handle saved: 16" (не 0!)
2. При отправке в логе "Sending NMEA: ... tx_handle=16"
3. ble_gatts_notify_custom возвращает rc=0
4. В nRF Connect на телефоне появляются NMEA-строки
5. GAP-события обрабатываются один раз (нет дублей count)
```

---

