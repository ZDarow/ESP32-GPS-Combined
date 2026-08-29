#pragma once

#include <stdint.h>

void battery_adc_init(void);
float battery_read_voltage(void);
uint8_t battery_read_percentage(void);

/**
 * @brief Установить пороги калибровки батареи
 * @param min_v Минимальное напряжение (0%)
 * @param max_v Максимальное напряжение (100%)
 */
void battery_set_calibration(float min_v, float max_v);

/**
 * @brief Получить текущие пороги калибровки
 * @param min_v Указатель для min напряжения
 * @param max_v Указатель для max напряжения
 */
void battery_get_calibration(float *min_v, float *max_v);

/**
 * @brief Проверить, критически ли низкий заряд
 * @return true если напряжение < min_v
 */
bool battery_is_low(void);
