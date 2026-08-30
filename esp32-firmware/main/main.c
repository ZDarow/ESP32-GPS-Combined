#include "gps_uart.h"
#include "nmea_parser.h"
#include "ble_nus.h"
#include "power_manager.h"
#include "battery_adc.h"
#include "oled_display.h"
#include "esp_log.h"
#include "esp_err.h"
#include "esp_task_wdt.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include <string.h>

static const char *TAG = "MAIN";
static volatile bool s_real_fix = false;
static QueueHandle_t s_ble_queue = NULL;

// Симулятор: генерирует NMEA при отсутствии реального фикса
// ВАЖНО: Используем очередь вместо прямого вызова ble_nus_send_nmea
static void simulator_task(void *arg) {
    ESP_LOGI(TAG, "Simulator task started");
    while (1) {
        vTaskDelay(pdMS_TO_TICKS(1000));
        if (s_ble_queue != NULL && ble_nus_is_connected() && !s_real_fix) {
            const char *nmea = "$GPRMC,120000,A,4807.038,N,01131.000,E,0.0,0.0,010124,,,A*77\r\n";
            // Отправляем в очередь, а не напрямую - чтобы работал throttling
            if (xQueueSend(s_ble_queue, nmea, pdMS_TO_TICKS(10)) != pdTRUE) {
                ESP_LOGW(TAG, "Simulator: queue send failed");
            }
        }
    }
}

// Idle monitor: вход в сон через 5 мин без BLE-соединения
static void idle_task(void *arg) {
    while (1) {
        vTaskDelay(pdMS_TO_TICKS(30000));
        if (power_is_idle_timeout() && !ble_nus_is_connected()) {
            ESP_LOGI(TAG, "Idle timeout, entering deep sleep");
            ble_nus_prepare_deep_sleep();   // E5: корректно остановить BLE перед сном
            power_enter_deep_sleep();
        }
    }
}

// Накопительный fix: парсер дополняет его из каждой NMEA-строки,
// поэтому не сбрасываем между вызовами (иначе GSA/GSV перезапишут valid).
static gnss_fix_t s_gnss_fix;

// E2 (embedded-аудит): OLED-рендер вынесен в отдельную задачу. Горячий путь
// GPS (gps_uart_task) больше не блокируется на I2C — on_gps_line кладёт копию
// fix в mailbox, oled_task рендерит с троттлингом (не чаще ~2 Гц).
static QueueHandle_t s_oled_queue = NULL;

static void oled_task(void *arg)
{
    (void)arg;
    gnss_fix_t fix;
    while (1) {
        if (xQueueReceive(s_oled_queue, &fix, pdMS_TO_TICKS(500)) == pdTRUE) {
            oled_display_update(&fix, ble_nus_is_connected());
        }
    }
}

static void on_gps_line(const char *line, size_t len) {
    if (nmea_parser_feed(line, (int)len, &s_gnss_fix)) {
        s_real_fix = s_gnss_fix.valid;
        // Копия fix в mailbox OLED-задачи (decouple от I2C в hot-path).
        if (s_oled_queue != NULL) {
            xQueueOverwrite(s_oled_queue, &s_gnss_fix);
        }
    }
}

void app_main(void) {
    ESP_LOGI(TAG, "Simplified BLE GNSS tracker starting");

    // E1 (embedded-аудит): Task Watchdog. idle-задачи обеих ядер кормят WDT;
    // любой spin/зависание задачи, не дающей планировщику работать, => ребут.
    esp_task_wdt_config_t wdt_cfg = {
        .timeout_ms = 10000,
        .idle_core_mask = 0x03,
        .trigger_panic = true,
    };
    ESP_ERROR_CHECK(esp_task_wdt_init(&wdt_cfg));

    ESP_ERROR_CHECK(gps_uart_init());
    nmea_parser_init();
    ESP_ERROR_CHECK(gps_uart_register_callback(on_gps_line));
    ESP_ERROR_CHECK(gps_uart_task_start());

    power_manager_init();
    battery_adc_init();
    oled_display_init();
    oled_display_show_boot();

    // E2: OLED-рендер в отдельной задаче (mailbox на 1 элемент).
    s_oled_queue = xQueueCreate(1, sizeof(gnss_fix_t));
    if (s_oled_queue) {
        xTaskCreate(oled_task, "oled", 3072, NULL, 3, NULL);
    }

    ESP_ERROR_CHECK(ble_nus_init());
    xTaskCreate(ble_nus_status_task, "ble_status", 4096, NULL, 5, NULL);

    // Получаем очередь GPS и передаём в BLE send задачу
    s_ble_queue = gps_uart_get_line_queue();
    if (s_ble_queue) {
        xTaskCreate(ble_nus_send_task, "ble_send", 6144, s_ble_queue, 4, NULL);
    }

    // Симулятор отключён по запросу: шлёт fake NMEA (Мюнхен) при
    // BLE-connected и отсутствии реального фикса, что мешает записи
    // реального трека. Реальные координаты пойдут только от GPS-модуля.
    // xTaskCreate(simulator_task, "simulator", 2048, NULL, 2, NULL);
    xTaskCreate(idle_task, "idle", 2048, NULL, 2, NULL);

    ESP_LOGI(TAG, "Ready. Advertising as '%s'", BLE_DEVICE_NAME);
}
