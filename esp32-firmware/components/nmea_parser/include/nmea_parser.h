#pragma once

#include <stdint.h>
#include <stdbool.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef enum {
    GNSS_FIX_NONE = 0,
    GNSS_FIX_2D,
    GNSS_FIX_3D
} gnss_fix_type_t;

typedef struct {
    gnss_fix_type_t type;
    bool valid;
    double latitude;
    double longitude;
    double altitude_m;
    double speed_kmh;
    double course_deg;
    uint8_t satellites_used;
    uint8_t fix_quality;
    double hdop;
    int64_t last_update_ms;
    /* Extended fields from official ESP-IDF NMEA parser */
    uint8_t hour;
    uint8_t minute;
    uint8_t second;
    uint16_t thousand;
    uint8_t day;
    uint8_t month;
    uint16_t year;
    uint8_t sats_in_view;
    double dop_p;
    double dop_v;
    float speed;
    float cog;
    float variation;
} gnss_fix_t;

void nmea_parser_init(void);
bool nmea_parser_feed(const char *sentence, int len, gnss_fix_t *out_fix);

#ifdef __cplusplus
}
#endif
