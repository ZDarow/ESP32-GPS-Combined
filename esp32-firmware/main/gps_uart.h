#pragma once

#include "app_config.h"
#include "esp_err.h"
#include <stdint.h>
#include <stdbool.h>
#include "freertos/FreeRTOS.h"

#ifdef __cplusplus
extern "C" {
#endif

typedef void (*gps_line_callback_t)(const char *line, size_t len);

esp_err_t gps_uart_init(void);
esp_err_t gps_uart_detect_baud(void);
esp_err_t gps_uart_register_callback(gps_line_callback_t cb);
esp_err_t gps_uart_task_start(void);
QueueHandle_t gps_uart_get_line_queue(void);
esp_err_t gps_uart_send_raw(const uint8_t *data, size_t len);

#ifdef __cplusplus
}
#endif