#include "gps_uart.h"
#include "nmea_parser.h"
#include "ble_nus.h"
#include "power_manager.h"
#include "battery_adc.h"
#include "oled_display.h"
#include "esp_log.h"
#include "esp_err.h"
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
            power_enter_deep_sleep();
        }
    }
}

static void on_gps_line(const char *line, size_t len) {
    gnss_fix_t fix;
    if (nmea_parser_feed(line, len, &fix)) {
        s_real_fix = fix.valid;
        oled_display_update(&fix, ble_nus_is_connected());
    }
}

void app_main(void) {
    ESP_LOGI(TAG, "Simplified BLE GNSS tracker starting");

    ESP_ERROR_CHECK(gps_uart_init());
    nmea_parser_init();
    ESP_ERROR_CHECK(gps_uart_register_callback(on_gps_line));
    ESP_ERROR_CHECK(gps_uart_task_start());

    power_manager_init();
    battery_adc_init();
    oled_display_init();
    oled_display_show_boot();

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
