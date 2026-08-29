idf_component_register(SRCS "oled_display.c" "power_manager.c" "ble_nus.c" "battery_adc.c" "gps_uart.c" "main.c"
                      INCLUDE_DIRS "."
                      REQUIRES bt driver nmea_parser nvs_flash esp_driver_i2c esp_driver_uart esp_adc)
