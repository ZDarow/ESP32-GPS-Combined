#pragma once

#include <stdint.h>
#include "driver/uart.h"
#include "driver/i2c.h"

// GPS UART (GPIO9/10 - не strapping, не конфликтуют)
#define GPS_UART_NUM        UART_NUM_1
#define GPS_UART_TX_PIN     10
#define GPS_UART_RX_PIN     9
#define GPS_UART_BAUD       9600
#define GPS_UART_RX_BUF     2048
#define GPS_DATA_TIMEOUT_MS 5000

// GPS RAW debug (0=выкл, 1=вкл). Включайте только для short debugging sessions.
#define GPS_RAW_DEBUG      0
#define GPS_RAW_DEBUG_LIMIT 50

// Battery ADC (GPIO4 - ADC1_CH3, свободный)
#define BATTERY_ADC_PIN         4
#define BATTERY_VOLTAGE_DIVIDER 2.0f
#define BATTERY_MIN_VOLTAGE     3.0f
#define BATTERY_MAX_VOLTAGE     4.2f

// Deep sleep (GPIO5 - не strapping, не занят)
#define DEEP_SLEEP_BTN_PIN  5
#define DEEP_SLEEP_TIMEOUT_S 300  // 5 минут без соединений -> сон

// OLED SSD1306 (GPIO41/42 - I2C0, свободны)
#define OLED_I2C_SDA_PIN     41
#define OLED_I2C_SCL_PIN     42
#define OLED_I2C_PORT        I2C_NUM_0
#define OLED_I2C_ADDR        0x3C
#define OLED_I2C_CLK_HZ      (400 * 1000)

// BLE
#define BLE_DEVICE_NAME      "ESP32S3-GPS"
#define BLE_ADV_INTERVAL_MS  500
#define BLE_MTU_CHUNK_SIZE   20
