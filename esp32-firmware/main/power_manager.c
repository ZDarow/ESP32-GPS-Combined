#include "power_manager.h"
#include "app_config.h"
#include "esp_sleep.h"
#include "driver/gpio.h"
#include "esp_log.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

static const char *TAG = "power";

// Таймаут: 5 минут без активности -> сон
#define IDLE_TIMEOUT_S  DEEP_SLEEP_TIMEOUT_S

static uint32_t s_last_activity_ms = 0;

void power_register_activity(void) {
    s_last_activity_ms = xTaskGetTickCount() * portTICK_PERIOD_MS;
}

void power_manager_init(void) {
    // GPIO5 с pull-up
    gpio_config_t cfg = {
        .pin_bit_mask = (1ULL << DEEP_SLEEP_BTN_PIN),
        .mode = GPIO_MODE_INPUT,
        .pull_up_en = GPIO_PULLUP_ENABLE,
        .pull_down_en = GPIO_PULLDOWN_DISABLE,
        .intr_type = GPIO_INTR_DISABLE,
    };
    gpio_config(&cfg);

    // Wakeup по LOW на GPIO5 (кнопка на GND)
    esp_sleep_enable_ext0_wakeup((gpio_num_t)DEEP_SLEEP_BTN_PIN, 0);

    s_last_activity_ms = xTaskGetTickCount() * portTICK_PERIOD_MS;
    ESP_LOGI(TAG, "Power manager initialized, GPIO%d as wakeup button", DEEP_SLEEP_BTN_PIN);
}

void power_enter_deep_sleep(void) {
    ESP_LOGI(TAG, "Entering deep sleep, wakeup by GPIO%d or RST", DEEP_SLEEP_BTN_PIN);
    esp_deep_sleep_start();
}

bool power_is_idle_timeout(void) {
    uint32_t now = xTaskGetTickCount() * portTICK_PERIOD_MS;
    return (now - s_last_activity_ms) > (IDLE_TIMEOUT_S * 1000U);
}
