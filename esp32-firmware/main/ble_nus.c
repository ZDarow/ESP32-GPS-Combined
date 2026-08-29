#include "ble_nus.h"
#include "app_config.h"
#include "battery_adc.h"
#include "esp_log.h"
#include "esp_err.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "nimble/ble.h"
#include "nimble/nimble_port.h"
#include "nimble/nimble_port_freertos.h"
#include "host/ble_hs.h"
#include "host/ble_gap.h"
#include "host/ble_gatt.h"
#include "host/util/util.h"
#include "services/gap/ble_svc_gap.h"
#include "services/gatt/ble_svc_gatt.h"
#include "nvs_flash.h"
#include <string.h>
#include <stdio.h>

void ble_store_config_init(void);

static const char *TAG = "BLE_NUS";

#define NUS_SERVICE_UUID        "6E400001-B5A3-F393-E0A9-E50E24DCCA9E"
#define NUS_TX_CHAR_UUID        "6E400003-B5A3-F393-E0A9-E50E24DCCA9E"
#define NUS_RX_CHAR_UUID        "6E400002-B5A3-F393-E0A9-E50E24DCCA9E"

#define BATTERY_SERVICE_UUID    "0000180F-0000-1000-8000-00805F9B34FB"
#define BATTERY_LEVEL_CHAR_UUID "00002A19-0000-1000-8000-00805F9B34FB"

#define BLE_SEND_TASK_STACK_SIZE 6144
#define BLE_SEND_TASK_PRIORITY   4
#define BLE_SEND_MAX_LINES_PER_CYCLE 2   // Reduced to prevent BLE stack overload
#define BLE_SEND_CYCLE_MS         500     // 500ms between send cycles to let BLE breathe

#define BLE_STATE_LOCK()   portENTER_CRITICAL(&s_ble_mux)
#define BLE_STATE_UNLOCK() portEXIT_CRITICAL(&s_ble_mux)

static portMUX_TYPE s_ble_mux = portMUX_INITIALIZER_UNLOCKED;
static uint16_t s_conn_handle = BLE_HS_CONN_HANDLE_NONE;
static bool s_connected = false;
static bool s_is_subscribed = false;
static volatile int s_gap_event_count = 0;
static uint16_t s_tx_val_handle = 0;
static uint16_t s_rx_val_handle = 0;

static ble_uuid128_t s_nus_service_uuid;
static ble_uuid128_t s_nus_tx_char_uuid;
static ble_uuid128_t s_nus_rx_char_uuid;

static ble_uuid128_t s_battery_service_uuid;
static ble_uuid128_t s_battery_level_char_uuid;
static uint16_t s_battery_level_val_handle = 0;
static uint8_t s_battery_level = 0;
static uint8_t s_last_reported_battery = 0xFF;

static struct ble_gap_event_listener s_gap_listener;
static int ble_nus_gap_event(struct ble_gap_event *event, void *arg);

static void on_stack_reset(int reason)
{
    ESP_LOGI(TAG, "nimble stack reset, reason=%d", reason);
}

static void on_stack_sync(void)
{
    ESP_LOGI(TAG, "nimble stack synced");
    ble_hs_util_ensure_addr(0);

    memset(&s_gap_listener, 0, sizeof(s_gap_listener));
    int gap_rc = ble_gap_event_listener_register(&s_gap_listener, ble_nus_gap_event, NULL);
    if (gap_rc != 0) {
        ESP_LOGE(TAG, "Failed to register GAP event listener: %d", gap_rc);
    } else {
        ESP_LOGI(TAG, "GAP event listener registered");
    }

    ble_nus_start_advertising();
}

static void ble_nus_gatts_register_cb(struct ble_gatt_register_ctxt *ctxt, void *arg)
{
    char buf[BLE_UUID_STR_LEN];

    switch (ctxt->op) {
        case BLE_GATT_REGISTER_OP_SVC:
            ESP_LOGI(TAG, "registered service %s with handle=%d",
                     ble_uuid_to_str(ctxt->svc.svc_def->uuid, buf),
                     ctxt->svc.handle);
            break;

        case BLE_GATT_REGISTER_OP_CHR:
            ESP_LOGI(TAG, "registering characteristic %s with def_handle=%d val_handle=%d",
                     ble_uuid_to_str(ctxt->chr.chr_def->uuid, buf),
                     ctxt->chr.def_handle,
                     ctxt->chr.val_handle);

            if (ctxt->chr.val_handle != 0) {
                ble_uuid128_t *chr_uuid = (ble_uuid128_t *)ctxt->chr.chr_def->uuid;
                if (memcmp(chr_uuid->value, s_nus_tx_char_uuid.value, 16) == 0) {
                    s_tx_val_handle = ctxt->chr.val_handle;
                    ESP_LOGI(TAG, ">>> TX char handle saved: %d", s_tx_val_handle);
                } else if (memcmp(chr_uuid->value, s_nus_rx_char_uuid.value, 16) == 0) {
                    s_rx_val_handle = ctxt->chr.val_handle;
                    ESP_LOGI(TAG, ">>> RX char handle saved: %d", s_rx_val_handle);
                } else if (memcmp(chr_uuid->value, s_battery_level_char_uuid.value, 16) == 0) {
                    s_battery_level_val_handle = ctxt->chr.val_handle;
                    ESP_LOGI(TAG, ">>> Battery Level char handle saved: %d", s_battery_level_val_handle);
                }
            }
            break;

        default:
            break;
    }
}

static void nimble_host_config_init(void)
{
    ble_hs_cfg.reset_cb = on_stack_reset;
    ble_hs_cfg.sync_cb = on_stack_sync;
    ble_hs_cfg.gatts_register_cb = ble_nus_gatts_register_cb;
    ble_hs_cfg.store_status_cb = ble_store_util_status_rr;

    // Security: LE Secure Connections с NoInputNoOutput.
    // Android 10+ требует LESC (sm_sc=1), иначе соединение разрывается
    // со статусом 0x08 (GATT CONN TIMEOUT) через 30 мс после connect.
    ble_hs_cfg.sm_io_cap = 0;       // NoInputNoOutput
    ble_hs_cfg.sm_bonding = 1;       // Enable bonding (matches Android expectation)
    ble_hs_cfg.sm_our_key_dist = 1;  // Distribute LTK, IRK, CSRK
    ble_hs_cfg.sm_their_key_dist = 1;
    ble_hs_cfg.sm_sc = 1;            // LE Secure Connections (required by Android)
    ble_hs_cfg.sm_mitm = 0;          // No MITM protection
}

static void nimble_host_task(void *param)
{
    ESP_LOGI(TAG, "nimble_host_task started");
    nimble_port_run();
    ESP_LOGI(TAG, "nimble_host_task exited");
    vTaskDelete(NULL);
}

static int ble_nus_gap_event(struct ble_gap_event *event, void *arg)
{
    // НЕ используем BLE_STATE_LOCK здесь — callback вызывается из
    // NimBLE host task (single-threaded), и portENTER_CRITICAL блокирует
    // прерывания, из-за чего NimBLE пропускает события.
    s_gap_event_count++;
    ESP_LOGI(TAG, "GAP event type=%d count=%d", event->type, s_gap_event_count);
    switch (event->type) {
        case BLE_GAP_EVENT_CONNECT:
            ESP_LOGI(TAG, "BLE CONNECT event: status=%d conn_handle=%d",
                     event->connect.status, event->connect.conn_handle);
            if (event->connect.status == 0) {
                s_conn_handle = event->connect.conn_handle;
                s_connected = true;
                ESP_LOGI(TAG, ">>> BLE connected, handle=%d", s_conn_handle);

                // Reset idle timer on connect to prevent deep sleep
                extern void power_register_activity(void);
                power_register_activity();

                // Request stable connection params to prevent Android timeouts
                // itvl: 30-50ms, latency: 3 (can skip 3 intervals), timeout: 4s
                struct ble_gap_upd_params params = {
                    .itvl_min = 24,       // 24 * 1.25ms = 30ms
                    .itvl_max = 40,       // 40 * 1.25ms = 50ms
                    .latency = 3,         // Skip up to 3 intervals without disconnect
                    .supervision_timeout = 400, // 400 * 10ms = 4000ms
                    .min_ce_len = 0,
                    .max_ce_len = 0,
                };
                int rc = ble_gap_update_params(s_conn_handle, &params);
                if (rc != 0) {
                    ESP_LOGW(TAG, ">>> Connection params update failed: %d", rc);
                } else {
                    ESP_LOGI(TAG, ">>> Connection params requested (30-50ms, latency=3, timeout=4s)");
                }
            } else {
                ESP_LOGE(TAG, "BLE connection failed, status=%d", event->connect.status);
                ble_nus_start_advertising();
            }
            return 0;

        case BLE_GAP_EVENT_DISCONNECT:
            ESP_LOGI(TAG, "BLE DISCONNECT event: reason=%d", event->disconnect.reason);
            s_conn_handle = BLE_HS_CONN_HANDLE_NONE;
            s_connected = false;
            s_is_subscribed = false;
            ESP_LOGI(TAG, "BLE disconnected");
            ble_nus_start_advertising();
            return 0;

        case BLE_GAP_EVENT_ADV_COMPLETE:
            ESP_LOGI(TAG, "BLE advertising complete");
            return 0;

        case BLE_GAP_EVENT_SUBSCRIBE:
            ESP_LOGI(TAG, "SUBSCRIBE event: conn_handle=%d, attr_handle=%d, cur_notify=%d",
                     event->subscribe.conn_handle,
                     event->subscribe.attr_handle,
                     event->subscribe.cur_notify);

            if (event->subscribe.attr_handle == s_tx_val_handle) {
                s_is_subscribed = (event->subscribe.cur_notify != 0);
                ESP_LOGI(TAG, ">>> Client notifications %s!",
                         s_is_subscribed ? "ENABLED" : "DISABLED");
            }
            return 0;

        case BLE_GAP_EVENT_MTU:
            ESP_LOGI(TAG, "MTU update: conn=%d mtu=%d",
                     event->mtu.conn_handle, event->mtu.value);
            return 0;

        case BLE_GAP_EVENT_CONN_UPDATE:
            ESP_LOGI(TAG, "BLE_CONN_UPDATE: conn_handle=%d status=%d",
                     event->conn_update.conn_handle, event->conn_update.status);
            // Workaround: NimBLE may not fire CONNECT event, try to get handle here
            if (s_conn_handle == BLE_HS_CONN_HANDLE_NONE) {
                s_conn_handle = event->conn_update.conn_handle;
                s_connected = true;
                ESP_LOGI(TAG, ">>> Got handle from CONN_UPDATE: %d", s_conn_handle);
            }
            return 0;

        case BLE_GAP_EVENT_LINK_ESTAB:
            ESP_LOGI(TAG, "BLE_LINK_ESTAB: conn_handle=%d", event->link_estab.conn_handle);
            if (s_conn_handle == BLE_HS_CONN_HANDLE_NONE) {
                s_conn_handle = event->link_estab.conn_handle;
                s_connected = true;
                ESP_LOGI(TAG, ">>> Got handle from LINK_ESTAB: %d", s_conn_handle);
            }
            return 0;

        case BLE_GAP_EVENT_DATA_LEN_CHG:
            ESP_LOGI(TAG, "Data len change: conn=%d max_tx=%d max_rx=%d",
                     event->data_len_chg.conn_handle,
                     event->data_len_chg.max_tx_octets,
                     event->data_len_chg.max_rx_octets);
            return 0;

        default:
            ESP_LOGI(TAG, "Unhandled GAP event type=%d", event->type);
            return 0;
    }
}

static int ble_nus_gatt_access(uint16_t conn_handle, uint16_t attr_handle,
                               struct ble_gatt_access_ctxt *ctxt, void *arg)
{
    if (ctxt->op == BLE_GATT_ACCESS_OP_READ_CHR) {
        if (attr_handle == s_battery_level_val_handle) {
            uint8_t level = ble_nus_get_battery_level();
            ESP_LOGI(TAG, "Battery Level read: %d%%", level);
            return os_mbuf_append(ctxt->om, &level, sizeof(level));
        }
        return 0;
    }

    if (ctxt->op == BLE_GATT_ACCESS_OP_WRITE_CHR) {
        uint16_t len = ctxt->om->om_len;
        ESP_LOGI(TAG, "RX write %u bytes", len);
        return 0;
    }

    return 0;
}

void ble_nus_status_task(void *arg)
{
    while (1) {
        vTaskDelay(pdMS_TO_TICKS(5000));

        BLE_STATE_LOCK();
        bool connected = s_connected;
        uint16_t conn_handle = s_conn_handle;
        BLE_STATE_UNLOCK();

        if (!connected || conn_handle == BLE_HS_CONN_HANDLE_NONE) {
            continue;
        }

        struct ble_gap_conn_desc desc;
        int rc = ble_gap_conn_find(conn_handle, &desc);
        if (rc == 0) {
            ESP_LOGI(TAG, "status: connection OK handle=%d", desc.conn_handle);
            // Reset idle timer on successful status check
            extern void power_register_activity(void);
            power_register_activity();
        } else {
            ESP_LOGW(TAG, "status: connection lost, rc=%d. Resetting state", rc);
            BLE_STATE_LOCK();
            s_conn_handle = BLE_HS_CONN_HANDLE_NONE;
            s_connected = false;
            s_is_subscribed = false;
            BLE_STATE_UNLOCK();
            ble_nus_start_advertising();
        }

        // Battery level отключён (Battery Service удалён, чтобы избежать
        // двойной регистрации характеристики 0x2A19 в NimBLE).
        // uint8_t new_level = battery_read_percentage();
        // if (abs((int)new_level - (int)s_last_reported_battery) >= 5) {
        //     ble_nus_set_battery_level(new_level);
        // }
    }
}

static void ble_nus_add_service(void)
{
    s_nus_service_uuid = (ble_uuid128_t)BLE_UUID128_INIT(0x9E, 0xCA, 0xDC, 0x24, 0x0E, 0xE5, 0xA9, 0xE0,
                                          0x93, 0xF3, 0xA3, 0xB5, 0x01, 0x00, 0x40, 0x6E);
    s_nus_tx_char_uuid = (ble_uuid128_t)BLE_UUID128_INIT(0x9E, 0xCA, 0xDC, 0x24, 0x0E, 0xE5, 0xA9, 0xE0,
                                            0x93, 0xF3, 0xA3, 0xB5, 0x03, 0x00, 0x40, 0x6E);
    s_nus_rx_char_uuid = (ble_uuid128_t)BLE_UUID128_INIT(0x9E, 0xCA, 0xDC, 0x24, 0x0E, 0xE5, 0xA9, 0xE0,
                                            0x93, 0xF3, 0xA3, 0xB5, 0x02, 0x00, 0x40, 0x6E);
    s_battery_service_uuid = (ble_uuid128_t)BLE_UUID128_INIT(0xFB, 0x34, 0x9B, 0x05, 0x80, 0x00, 0x00, 0x10,
                                                 0x00, 0x00, 0x0F, 0x18, 0x00, 0x00, 0x00, 0x00);
    s_battery_level_char_uuid = (ble_uuid128_t)BLE_UUID128_INIT(0xFB, 0x34, 0x9B, 0x05, 0x80, 0x00, 0x00, 0x10,
                                                   0x00, 0x00, 0x19, 0x2A, 0x00, 0x00, 0x00, 0x00);

    static const struct ble_gatt_chr_def chr_defs[] = {
        {
            .uuid = &s_nus_tx_char_uuid.u,
            .access_cb = ble_nus_gatt_access,
            .flags = BLE_GATT_CHR_F_NOTIFY,
            .val_handle = &s_tx_val_handle,
        },
        {
            .uuid = &s_nus_rx_char_uuid.u,
            .access_cb = ble_nus_gatt_access,
            .flags = BLE_GATT_CHR_F_WRITE,
            .val_handle = &s_rx_val_handle,
        },
        {0},
    };

    static const struct ble_gatt_svc_def svc_defs[] = {
        {
            .type = BLE_GATT_SVC_TYPE_PRIMARY,
            .uuid = &s_nus_service_uuid.u,
            .characteristics = chr_defs,
        },
        {0},
    };

    ble_gatts_count_cfg(svc_defs);
    ble_gatts_add_svcs(svc_defs);

    ESP_LOGI(TAG, "TX char handle=%d, RX char handle=%d, Battery Level handle=%d",
             s_tx_val_handle, s_rx_val_handle, s_battery_level_val_handle);
}

esp_err_t ble_nus_init(void)
{
    // Стираем NVS чтобы убрать остатки старых сервисов (ae00) и bonding keys.
    // Это одноразовая операция — при следующих запусках NVS будет чистым.
    esp_err_t ret = nvs_flash_init();
    if (ret == ESP_ERR_NVS_NO_FREE_PAGES || ret == ESP_ERR_NVS_NEW_VERSION_FOUND) {
        ESP_ERROR_CHECK(nvs_flash_erase());
        ret = nvs_flash_init();
    }
    // Принудительно стираем NVS для чистой конфигурации BLE
    if (ret == ESP_OK) {
        ESP_ERROR_CHECK(nvs_flash_erase());
        ret = nvs_flash_init();
    }
    if (ret != ESP_OK) {
        ESP_LOGE(TAG, "NVS init failed: %s", esp_err_to_name(ret));
        return ESP_FAIL;
    }

    ret = nimble_port_init();
    if (ret != ESP_OK) {
        ESP_LOGE(TAG, "nimble_port_init failed: %s", esp_err_to_name(ret));
        return ESP_FAIL;
    }

    nimble_host_config_init();

    ble_svc_gap_init();
    ble_svc_gatt_init();

    ble_nus_add_service();

    int rc = ble_svc_gap_device_name_set(BLE_DEVICE_NAME);
    if (rc != 0) {
        ESP_LOGE(TAG, "Failed to set device name: %d", rc);
        return ESP_FAIL;
    }

    ble_store_config_init();

    nimble_port_freertos_init(nimble_host_task);

    ESP_LOGI(TAG, "BLE NUS initialized, device name=%s", BLE_DEVICE_NAME);
    return ESP_OK;
}

esp_err_t ble_nus_start_advertising(void)
{
    uint8_t own_addr_type;
    int rc = ble_hs_id_infer_auto(0, &own_addr_type);
    if (rc != 0) {
        ESP_LOGE(TAG, "Failed to infer address type: %d", rc);
        return ESP_FAIL;
    }

    struct ble_hs_adv_fields adv_fields = {0};
    adv_fields.flags = BLE_HS_ADV_F_DISC_GEN | BLE_HS_ADV_F_BREDR_UNSUP;
    adv_fields.name = (uint8_t *)BLE_DEVICE_NAME;
    adv_fields.name_len = strlen(BLE_DEVICE_NAME);
    adv_fields.name_is_complete = 1;
    adv_fields.tx_pwr_lvl = BLE_HS_ADV_TX_PWR_LVL_AUTO;
    adv_fields.tx_pwr_lvl_is_present = 1;

    rc = ble_gap_adv_set_fields(&adv_fields);
    if (rc != 0) {
        ESP_LOGE(TAG, "Failed to set adv fields: %d", rc);
        return ESP_FAIL;
    }

    struct ble_gap_adv_params adv_params = {0};
    adv_params.conn_mode = BLE_GAP_CONN_MODE_UND;
    adv_params.disc_mode = BLE_GAP_DISC_MODE_GEN;
    adv_params.itvl_min = BLE_GAP_ADV_ITVL_MS(BLE_ADV_INTERVAL_MS);
    adv_params.itvl_max = BLE_GAP_ADV_ITVL_MS(BLE_ADV_INTERVAL_MS + 10);

    rc = ble_gap_adv_start(own_addr_type, NULL, BLE_HS_FOREVER, &adv_params,
                           NULL, NULL);
    if (rc != 0) {
        ESP_LOGE(TAG, "Failed to start advertising: %d", rc);
        return ESP_FAIL;
    }

    ESP_LOGI(TAG, "BLE advertising started");
    return ESP_OK;
}

static esp_err_t ble_nus_notify_raw(const uint8_t *data, int len)
{
    BLE_STATE_LOCK();
    if (!s_connected || s_conn_handle == BLE_HS_CONN_HANDLE_NONE) {
        BLE_STATE_UNLOCK();
        return ESP_FAIL;
    }

    if (!s_is_subscribed) {
        BLE_STATE_UNLOCK();
        return ESP_OK;
    }

    uint16_t conn_handle = s_conn_handle;
    BLE_STATE_UNLOCK();

    int mtu = ble_att_mtu(conn_handle);
    int chunk_size = (mtu > 23) ? (mtu - 3) : BLE_MTU_CHUNK_SIZE;

    int offset = 0;
    int chunk_idx = 0;
    while (offset < len) {
        int current_chunk = (len - offset > chunk_size) ? chunk_size : (len - offset);

        // FIXED: data + offset to send from correct position in buffer
        struct os_mbuf *om = ble_hs_mbuf_from_flat(data + offset, current_chunk);
        if (!om) {
            ESP_LOGE(TAG, "Failed to allocate mbuf for chunk %d", chunk_idx);
            return ESP_FAIL;
        }

        int rc = ble_gatts_notify_custom(conn_handle, s_tx_val_handle, om);
        if (rc != 0) {
            ESP_LOGE(TAG, "ble_gatts_notify_custom FAILED! rc=%d, chunk=%d, offset=%d",
                     rc, chunk_idx, offset);
            os_mbuf_free(om);
            return ESP_FAIL;
        }

        offset += current_chunk;
        chunk_idx++;

        // Critical: give NimBLE stack time to process ACK and queue the packet
        vTaskDelay(pdMS_TO_TICKS(5));
    }

    return ESP_OK;
}

esp_err_t ble_nus_send_nmea(const char *nmea_str, int len)
{
    BLE_STATE_LOCK();
    if (!s_connected || s_conn_handle == BLE_HS_CONN_HANDLE_NONE) {
        BLE_STATE_UNLOCK();
        ESP_LOGE(TAG, "BLE send skipped: connected=%d conn_handle=%d", s_connected, s_conn_handle);
        return ESP_FAIL;
    }
    BLE_STATE_UNLOCK();

    ESP_LOGI(TAG, "Sending NMEA direct: len=%d", len);

    esp_err_t rc = ble_nus_notify_raw((const uint8_t *)nmea_str, len);
    if (rc == ESP_OK) {
        ESP_LOGI(TAG, "BLE direct send OK: %d bytes", len);
    } else {
        ESP_LOGE(TAG, "BLE direct send FAILED: %s", esp_err_to_name(rc));
    }
    return rc;
}

int ble_nus_send_from_queue(QueueHandle_t queue, int max_lines)
{
    if (queue == NULL || max_lines <= 0) {
        return -1;
    }

    BLE_STATE_LOCK();
    if (!s_connected || s_conn_handle == BLE_HS_CONN_HANDLE_NONE) {
        BLE_STATE_UNLOCK();
        return -1;
    }

    if (!s_is_subscribed) {
        BLE_STATE_UNLOCK();
        return 0;
    }
    BLE_STATE_UNLOCK();

    char line_buf[128];
    size_t line_len = 0;
    int lines_sent = 0;
    int total_bytes = 0;

    while (lines_sent < max_lines) {
        if (xQueueReceive(queue, line_buf, 0) != pdTRUE) {
            break;
        }
        line_len = strlen(line_buf);
        if (line_len == 0) {
            continue;
        }

        esp_err_t rc = ble_nus_notify_raw((const uint8_t *)line_buf, line_len);
        if (rc == ESP_OK) {
            total_bytes += line_len;
            lines_sent++;
            // Update idle timer on successful data send
            extern void power_register_activity(void);
            power_register_activity();
            // 20ms is enough since notify_raw already has 5ms internal delay
            vTaskDelay(pdMS_TO_TICKS(20));
        } else {
            ESP_LOGW(TAG, "BLE send failed after %d lines", lines_sent);
            break;
        }
    }

    if (lines_sent > 0) {
        ESP_LOGI(TAG, "Queue send: %d lines, %d bytes", lines_sent, total_bytes);
    }

    return total_bytes;
}

void ble_nus_send_task(void *arg)
{
    QueueHandle_t queue = (QueueHandle_t)arg;
    if (queue == NULL) {
        ESP_LOGE(TAG, "Send task: queue is NULL");
        vTaskDelete(NULL);
        return;
    }

    ESP_LOGI(TAG, "BLE send task started");

    while (1) {
        vTaskDelay(pdMS_TO_TICKS(BLE_SEND_CYCLE_MS));

        BLE_STATE_LOCK();
        bool connected = s_connected;
        bool subscribed = s_is_subscribed;
        BLE_STATE_UNLOCK();

        if (!connected || !subscribed) {
            continue;
        }

        if (uxQueueMessagesWaiting(queue) == 0) {
            continue;
        }

        ble_nus_send_from_queue(queue, BLE_SEND_MAX_LINES_PER_CYCLE);
    }
}

bool ble_nus_is_connected(void)
{
    BLE_STATE_LOCK();
    bool connected = s_connected;
    BLE_STATE_UNLOCK();
    return connected;
}

esp_err_t ble_nus_set_battery_level(uint8_t level)
{
    if (s_battery_level_val_handle == 0) {
        return ESP_FAIL;
    }

    // Обновляем только если изменение > 5% или первый раз
    if (s_last_reported_battery == 0xFF || abs((int)level - (int)s_last_reported_battery) >= 5) {
        s_battery_level = level;
        s_last_reported_battery = level;

        struct os_mbuf *om = ble_hs_mbuf_from_flat(&level, sizeof(level));
        if (!om) {
            ESP_LOGE(TAG, "Failed to allocate mbuf for battery level");
            return ESP_FAIL;
        }

        BLE_STATE_LOCK();
        bool connected = s_connected;
        uint16_t conn_handle = s_conn_handle;
        BLE_STATE_UNLOCK();

        if (connected && conn_handle != BLE_HS_CONN_HANDLE_NONE) {
            int rc = ble_gatts_notify_custom(conn_handle, s_battery_level_val_handle, om);
            if (rc != 0) {
                ESP_LOGE(TAG, "Failed to notify battery level: %d", rc);
                os_mbuf_free(om);
                return ESP_FAIL;
            }
            ESP_LOGI(TAG, "Battery Level updated: %d%%", level);
        } else {
            os_mbuf_free(om);
        }
    }

    return ESP_OK;
}

uint8_t ble_nus_get_battery_level(void)
{
    return s_battery_level;
}
