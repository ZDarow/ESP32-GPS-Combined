#include "nmea_parser.h"
#include "esp_log.h"
#include "esp_timer.h"
#include <string.h>
#include <ctype.h>
#include <math.h>

static const char *TAG = "nmea_parser";

static double nmea_to_deg(double nmea_coord, bool is_lat)
{
    int deg = (int)(nmea_coord / 100.0);
    double min = nmea_coord - (deg * 100.0);
    return deg + min / 60.0;
}

static bool nmea_checksum(const char *sentence, int len)
{
    if (len < 4 || sentence[0] != '$') {
        return false;
    }

    uint8_t checksum = 0;
    for (int i = 1; i < len; i++) {
        if (sentence[i] == '*') {
            break;
        }
        checksum ^= (uint8_t)sentence[i];
    }

    const char *star = strchr(sentence, '*');
    if (!star || *(star + 1) == '\0') {
        return false;
    }

    unsigned int rx_sum = 0;
    if (sscanf(star + 1, "%2x", &rx_sum) != 1) {
        return false;
    }

    return checksum == (uint8_t)rx_sum;
}

static const char *nmea_field(const char *sentence, int field_idx)
{
    const char *p = sentence;
    while (*p && field_idx > 0) {
        if (*p == ',') {
            field_idx--;
        }
        p++;
    }
    return p;
}

static double nmea_parse_double(const char *field)
{
    if (!field || *field == '\0') {
        return 0.0;
    }
    return atof(field);
}

void nmea_parser_init(void)
{
    ESP_LOGI(TAG, "NMEA parser initialized");
}

bool nmea_parser_feed(const char *sentence, int len, gnss_fix_t *out_fix)
{
    if (!sentence || !out_fix || len < 5) {
        return false;
    }

    if (!nmea_checksum(sentence, len)) {
        return false;
    }

    memset(out_fix, 0, sizeof(gnss_fix_t));
    out_fix->last_update_ms = esp_timer_get_time() / 1000;

    if (strncmp(sentence, "$GPGGA", 6) == 0 || strncmp(sentence, "$GNGGA", 6) == 0) {
        const char *fix_quality = nmea_field(sentence, 6);
        const char *satellites = nmea_field(sentence, 7);
        const char *hdop = nmea_field(sentence, 8);
        const char *altitude = nmea_field(sentence, 9);
        const char *lat = nmea_field(sentence, 2);
        const char *ns = nmea_field(sentence, 3);
        const char *lon = nmea_field(sentence, 4);
        const char *ew = nmea_field(sentence, 5);

        out_fix->fix_quality = (uint8_t)nmea_parse_double(fix_quality);
        out_fix->satellites_used = (uint8_t)nmea_parse_double(satellites);
        out_fix->hdop = nmea_parse_double(hdop);
        out_fix->altitude_m = nmea_parse_double(altitude);

        double lat_val = nmea_parse_double(lat);
        double lon_val = nmea_parse_double(lon);

        if (lat_val != 0.0 && lon_val != 0.0) {
            out_fix->latitude = nmea_to_deg(lat_val, true);
            out_fix->longitude = nmea_to_deg(lon_val, false);
            if (ns && *ns == 'S') {
                out_fix->latitude = -out_fix->latitude;
            }
            if (ew && *ew == 'W') {
                out_fix->longitude = -out_fix->longitude;
            }
        }

        if (out_fix->fix_quality > 0) {
            out_fix->type = out_fix->fix_quality >= 2 ? GNSS_FIX_3D : GNSS_FIX_2D;
            out_fix->valid = true;
        }

        return true;
    }

    if (strncmp(sentence, "$GPRMC", 6) == 0 || strncmp(sentence, "$GNRMC", 6) == 0) {
        const char *status = nmea_field(sentence, 2);
        const char *lat = nmea_field(sentence, 3);
        const char *ns = nmea_field(sentence, 4);
        const char *lon = nmea_field(sentence, 5);
        const char *ew = nmea_field(sentence, 6);
        const char *speed = nmea_field(sentence, 7);
        const char *course = nmea_field(sentence, 8);

        if (status && *status == 'A') {
            out_fix->valid = true;
            out_fix->type = GNSS_FIX_2D;

            double lat_val = nmea_parse_double(lat);
            double lon_val = nmea_parse_double(lon);

            if (lat_val != 0.0 && lon_val != 0.0) {
                out_fix->latitude = nmea_to_deg(lat_val, true);
                out_fix->longitude = nmea_to_deg(lon_val, false);
                if (ns && *ns == 'S') {
                    out_fix->latitude = -out_fix->latitude;
                }
                if (ew && *ew == 'W') {
                    out_fix->longitude = -out_fix->longitude;
                }
            }

            out_fix->speed_kmh = nmea_parse_double(speed) * 1.852;
            out_fix->course_deg = nmea_parse_double(course);
        }

        return true;
    }

    if (strncmp(sentence, "$GPGSA", 6) == 0 || strncmp(sentence, "$GNGSA", 6) == 0) {
        const char *mode = nmea_field(sentence, 2);
        const char *fix_type = nmea_field(sentence, 3);
        const char *hdop = nmea_field(sentence, 16);

        if (fix_type && *fix_type >= '1' && *fix_type <= '3') {
            out_fix->type = (gnss_fix_type_t)(*fix_type - '0');
            out_fix->valid = true;
        }

        if (mode && *mode == 'A') {
            out_fix->valid = true;
        }

        out_fix->hdop = nmea_parse_double(hdop);

        return true;
    }

    if (strncmp(sentence, "$GPGSV", 6) == 0 || strncmp(sentence, "$GNGSV", 6) == 0) {
        const char *total_sats = nmea_field(sentence, 3);
        out_fix->satellites_used = (uint8_t)nmea_parse_double(total_sats);
        return true;
    }

    if (strncmp(sentence, "$GPVTG", 6) == 0 || strncmp(sentence, "$GNVTG", 6) == 0) {
        const char *speed = nmea_field(sentence, 7);
        const char *course = nmea_field(sentence, 1);

        out_fix->speed_kmh = nmea_parse_double(speed);
        out_fix->course_deg = nmea_parse_double(course);

        return true;
    }

    if (strncmp(sentence, "$GPGLL", 6) == 0 || strncmp(sentence, "$GNGLL", 6) == 0) {
        const char *lat = nmea_field(sentence, 1);
        const char *ns = nmea_field(sentence, 2);
        const char *lon = nmea_field(sentence, 3);
        const char *ew = nmea_field(sentence, 4);
        const char *status = nmea_field(sentence, 6);

        if (status && *status == 'A') {
            out_fix->valid = true;

            double lat_val = nmea_parse_double(lat);
            double lon_val = nmea_parse_double(lon);

            if (lat_val != 0.0 && lon_val != 0.0) {
                out_fix->latitude = nmea_to_deg(lat_val, true);
                out_fix->longitude = nmea_to_deg(lon_val, false);
                if (ns && *ns == 'S') {
                    out_fix->latitude = -out_fix->latitude;
                }
                if (ew && *ew == 'W') {
                    out_fix->longitude = -out_fix->longitude;
                }
            }
        }

        return true;
    }

    return false;
}
