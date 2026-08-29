#pragma once

#include <stdbool.h>

/** Инициализация: GPIO для кнопки сна + wakeup настройка */
void power_manager_init(void);

/** Войти в deep sleep (не возвращается) */
void power_enter_deep_sleep(void);

/** Зарегистрировать активность (сбрасывает idle-таймер) */
void power_register_activity(void);

/** Проверить, истёк ли таймаут бездействия */
bool power_is_idle_timeout(void);
