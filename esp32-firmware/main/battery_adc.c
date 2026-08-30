#include "app_config.h"
#include "battery_adc.h"
#include "esp_adc/adc_oneshot.h"
#include "esp_log.h"

static const char *TAG = "battery_adc";
static adc_oneshot_unit_handle_t s_adc1_handle;

// Канал ADC для BATTERY_ADC_PIN: GPIO4 = ADC1_CH3 (источник истины — app_config.h).
// Макрос ADC_CHANNEL_GPIO_TO_CHANNEL удалён в IDF v6.0.2 (legacy driver/adc.h),
// поэтому используем adc_channel_t напрямую.
static const adc_channel_t s_battery_adc_channel = ADC_CHANNEL_3;

static float s_battery_min_v = BATTERY_MIN_VOLTAGE;
static float s_battery_max_v = BATTERY_MAX_VOLTAGE;

void battery_adc_init(void)
{
    adc_oneshot_unit_init_cfg_t init_cfg = {
        .unit_id = ADC_UNIT_1,
    };
    ESP_ERROR_CHECK(adc_oneshot_new_unit(&init_cfg, &s_adc1_handle));

    adc_oneshot_chan_cfg_t chan_cfg = {
        .atten = ADC_ATTEN_DB_12,
        .bitwidth = ADC_BITWIDTH_12,
    };
    // BATTERY_ADC_PIN = GPIO4 = ADC1_CH3 (источник истины — app_config.h)
    ESP_ERROR_CHECK(adc_oneshot_config_channel(s_adc1_handle, s_battery_adc_channel, &chan_cfg));
    ESP_LOGI(TAG, "Battery ADC initialized on GPIO%d (ADC1_CH%d)", BATTERY_ADC_PIN,
             ADC_CHANNEL_3);
}

float battery_read_voltage(void)
{
    int adc_raw = 0;
    ESP_ERROR_CHECK(adc_oneshot_read(s_adc1_handle, s_battery_adc_channel, &adc_raw));
    float voltage = (adc_raw * 3.3f / 4095.0f) * BATTERY_VOLTAGE_DIVIDER;
    return voltage;
}

uint8_t battery_read_percentage(void)
{
    float v = battery_read_voltage();
    if (v <= s_battery_min_v) {
        return 0;
    }
    if (v >= s_battery_max_v) {
        return 100;
    }
    float ratio = (v - s_battery_min_v) / (s_battery_max_v - s_battery_min_v);
    return (uint8_t)(ratio * 100.0f);
}

void battery_set_calibration(float min_v, float max_v)
{
    if (min_v < max_v && min_v > 0.0f) {
        s_battery_min_v = min_v;
        s_battery_max_v = max_v;
        ESP_LOGI(TAG, "Battery calibration set: %.2fV - %.2fV", min_v, max_v);
    } else {
        ESP_LOGW(TAG, "Invalid calibration values: min=%.2f max=%.2f", min_v, max_v);
    }
}

void battery_get_calibration(float *min_v, float *max_v)
{
    if (min_v) *min_v = s_battery_min_v;
    if (max_v) *max_v = s_battery_max_v;
}

bool battery_is_low(void)
{
    static int low_count = 0;
    const int LOW_THRESHOLD = 3;  // Требуется N последовательных низких измерений

    float v = battery_read_voltage();
    if (v < s_battery_min_v) {
        low_count++;
        if (low_count >= LOW_THRESHOLD) {
            return true;
        }
    } else {
        low_count = 0;
    }
    return false;
}
