#include "gps_uart.h"
#include "app_config.h"
#include "driver/uart.h"
#include "driver/gpio.h"
#include "esp_log.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esp_task_wdt.h"
#include <string.h>

static const char *TAG = "GPS_UART";

#define UART_READ_CHUNK_SIZE      512
#define GPS_PUBLISHER_STACK_SIZE 6144
#define GPS_PUBLISHER_PRIORITY    5
#define GPS_LINE_QUEUE_LENGTH     32  // Increased to handle NMEA bursts

static uint32_t s_bytes_total = 0;
static uint32_t s_lines_total = 0;
static uint32_t s_nmea_total = 0;
static uint32_t s_queue_send_count = 0;
static uint32_t s_queue_fail_count = 0;
static uint32_t s_raw_printed = 0;

static char s_line_buf[128];
static int  s_line_pos = 0;
static gps_line_callback_t s_callback = NULL;
static QueueHandle_t s_line_queue = NULL;

static void gps_uart_task(void *arg)
{
    uint8_t rx_buf[UART_READ_CHUNK_SIZE];
    int64_t last_data_time = esp_timer_get_time();
    int64_t last_stats_time = esp_timer_get_time();

    ESP_LOGI(TAG, "UART task started. Waiting for GPS data...");

    esp_task_wdt_add(NULL);

    while (1) {
        int len = uart_read_bytes(GPS_UART_NUM, rx_buf, sizeof(rx_buf), pdMS_TO_TICKS(100));

        if (len > 0) {
            s_bytes_total += len;
            last_data_time = esp_timer_get_time();

            for (int i = 0; i < len; i++) {
                uint8_t rx_byte = rx_buf[i];

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

                if (rx_byte == '\n' || s_line_pos >= (int)sizeof(s_line_buf) - 1) {
                    s_line_buf[s_line_pos] = '\0';
                    if (s_line_pos > 0 && s_line_buf[s_line_pos - 1] == '\r') {
                        s_line_buf[s_line_pos - 1] = '\0';
                    }
                    s_lines_total++;

                    if (s_line_buf[0] == '$') {
                        s_nmea_total++;
                        if (s_nmea_total <= 10) {
                            ESP_LOGI(TAG, "NMEA[%u]: %s", s_nmea_total, s_line_buf);
                        }

                        // 1. СНАЧАЛА отправляем в очередь для BLE (чистые данные)
                        if (s_line_queue != NULL) {
                            if (xQueueSend(s_line_queue, s_line_buf, pdMS_TO_TICKS(10)) == pdTRUE) {
                                s_queue_send_count++;
                            } else {
                                s_queue_fail_count++;
                            }
                        }

                        // 2. ТОЛЬКО ПОТОМ callback (может блокировать из-за I2C OLED)
                        if (s_callback) {
                            s_callback(s_line_buf, strlen(s_line_buf));
                        }
                    }
                    s_line_pos = 0;

                } else if (rx_byte != '\r') {
                    s_line_buf[s_line_pos++] = rx_byte;
                }
            }

        } else {
            int64_t now = esp_timer_get_time();
            if ((now - last_data_time) > (int64_t)GPS_DATA_TIMEOUT_MS * 1000) {
                ESP_LOGW(TAG, "*** NO DATA for %d ms! Total bytes: %u. "
                              "CHECK WIRING: TX/RX/GND! ***",
                         GPS_DATA_TIMEOUT_MS, s_bytes_total);
                last_data_time = now;
            }
        }

        int64_t now = esp_timer_get_time();
        if ((now - last_stats_time) > 5000000) {
            ESP_LOGI(TAG, "=== STATS: bytes=%u | lines=%u | nmea=%u | queue_free=%u | q_send=%u | q_fail=%u ===",
                     s_bytes_total, s_lines_total, s_nmea_total,
                     (unsigned int)uxQueueSpacesAvailable(s_line_queue),
                     s_queue_send_count, s_queue_fail_count);
            last_stats_time = now;
        }
        esp_task_wdt_reset();
    }
}

esp_err_t gps_uart_init(void)
{
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

    s_line_queue = xQueueCreate(GPS_LINE_QUEUE_LENGTH, sizeof(s_line_buf));
    if (s_line_queue == NULL) {
        ESP_LOGE(TAG, "Failed to create GPS line queue");
        return ESP_FAIL;
    }

    ESP_LOGI(TAG, "UART1 init: TX=%d RX=%d baud=%d", GPS_UART_TX_PIN, GPS_UART_RX_PIN, GPS_UART_BAUD);
    return ESP_OK;
}

esp_err_t gps_uart_register_callback(gps_line_callback_t cb)
{
    s_callback = cb;
    return ESP_OK;
}

esp_err_t gps_uart_task_start(void)
{
    // BLE send task — единственный consumer очереди.
    xTaskCreate(gps_uart_task, "gps_uart_task", GPS_PUBLISHER_STACK_SIZE, NULL, GPS_PUBLISHER_PRIORITY, NULL);
    ESP_LOGI(TAG, "GPS UART task started");
    return ESP_OK;
}

QueueHandle_t gps_uart_get_line_queue(void)
{
    return s_line_queue;
}

/**
 * Отправить сырые байты в GPS UART (для команд RX, например "SET_RATE 1").
 */
esp_err_t gps_uart_send_raw(const uint8_t *data, size_t len)
{
    if (!data || len == 0) {
        return ESP_ERR_INVALID_ARG;
    }
    int sent = uart_write_bytes(GPS_UART_NUM, data, len);
    if (sent < (int)len) {
        ESP_LOGE(TAG, "Failed to send all bytes to GPS: sent=%d, expected=%u", sent, (unsigned int)len);
        return ESP_FAIL;
    }
    return ESP_OK;
}