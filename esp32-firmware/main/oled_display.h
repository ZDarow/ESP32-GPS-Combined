#pragma once

#include <stdint.h>
#include <stdbool.h>
#include "nmea_parser.h"
#include "app_config.h"

#ifdef __cplusplus
extern "C" {
#endif

#define OLED_WIDTH           128
#define OLED_HEIGHT          64
#define OLED_FONT_WIDTH      5
#define OLED_FONT_HEIGHT     7
#define OLED_CHAR_SPACING    1
#define OLED_LINE_HEIGHT     (OLED_FONT_HEIGHT + OLED_CHAR_SPACING)
#define OLED_MAX_LINES       (OLED_HEIGHT / OLED_LINE_HEIGHT)

void oled_display_init(void);
void oled_display_update(const gnss_fix_t *fix, bool ble_connected);
void oled_display_show_boot(void);

#ifdef __cplusplus
}
#endif
