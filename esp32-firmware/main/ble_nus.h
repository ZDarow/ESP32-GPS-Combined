#pragma once

#include "esp_err.h"
#include "nmea_parser.h"
#include <stdint.h>
#include <stdbool.h>
#include "freertos/FreeRTOS.h"

#ifdef __cplusplus
extern "C" {
#endif

esp_err_t ble_nus_init(void);
esp_err_t ble_nus_start_advertising(void);
bool ble_nus_is_connected(void);
void ble_nus_status_task(void *arg);

/**
 * @brief Отправить NMEA строки из FreeRTOS очереди через BLE
 * @return Количество отправленных байт, или -1 при ошибке
 */
int ble_nus_send_from_queue(QueueHandle_t queue, int max_lines);

/**
 * @brief Задача отправки BLE данных из очереди
 */
void ble_nus_send_task(void *arg);

/**
 * @brief Обновить Battery Level characteristic
 * @param level Уровень заряда 0..100%
 * @return ESP_OK при успехе
 */
esp_err_t ble_nus_set_battery_level(uint8_t level);

/**
 * @brief Прочитать текущий Battery Level из BLE состояния
 * @return Уровень заряда 0..100%
 */
uint8_t ble_nus_get_battery_level(void);

#ifdef __cplusplus
}
#endif