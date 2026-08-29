#include "oled_display.h"
#include "esp_log.h"
#include "esp_timer.h"
#include "driver/i2c_master.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/semphr.h"
#include <string.h>
#include <stdio.h>
#include <math.h>
#include <stdint.h>

static const char *TAG = "OLED";

static i2c_master_bus_handle_t s_i2c_bus = NULL;
static i2c_master_dev_handle_t s_i2c_dev = NULL;
static bool s_initialized = false;

static gnss_fix_t s_last_fix;
static bool s_ble_connected = false;
static bool s_display_dirty = true;

static SemaphoreHandle_t s_data_mutex = NULL;

// Line-based display state
#define OLED_LINES 8
#define OLED_LINE_HEIGHT 8
#define OLED_LINE_LEN 21

static char s_lines[OLED_LINES][OLED_LINE_LEN];
static bool s_line_dirty[OLED_LINES];
static uint8_t s_page_buf[OLED_WIDTH];

// Standard Adafruit GFX 5x7 font (glcdfont.c)
// Column-major: 5 bytes per character, bit 0 = top row, bit 6 = bottom row
// 95 characters from 0x20 (space) to 0x7E (~)
static const uint8_t s_font_5x7[] = {
    0x00, 0x00, 0x00, 0x00, 0x00, // space
    0x00, 0x00, 0x5F, 0x00, 0x00, // !
    0x00, 0x07, 0x00, 0x07, 0x00, // "
    0x14, 0x7F, 0x14, 0x7F, 0x14, // #
    0x24, 0x2A, 0x7F, 0x2A, 0x12, // $
    0x23, 0x13, 0x08, 0x64, 0x62, // %
    0x36, 0x49, 0x55, 0x22, 0x50, // &
    0x00, 0x05, 0x03, 0x00, 0x00, // '
    0x00, 0x1C, 0x22, 0x41, 0x00, // (
    0x00, 0x41, 0x22, 0x1C, 0x00, // )
    0x14, 0x08, 0x3E, 0x08, 0x14, // *
    0x08, 0x08, 0x3E, 0x08, 0x08, // +
    0x00, 0x50, 0x30, 0x00, 0x00, // ,
    0x08, 0x08, 0x08, 0x08, 0x08, // -
    0x00, 0x60, 0x60, 0x00, 0x00, // .
    0x20, 0x10, 0x08, 0x04, 0x02, // /
    0x3E, 0x51, 0x49, 0x45, 0x3E, // 0
    0x00, 0x42, 0x7F, 0x40, 0x00, // 1
    0x42, 0x61, 0x51, 0x49, 0x46, // 2
    0x21, 0x41, 0x45, 0x4B, 0x31, // 3
    0x18, 0x14, 0x12, 0x7F, 0x10, // 4
    0x27, 0x45, 0x45, 0x45, 0x39, // 5
    0x3C, 0x4A, 0x49, 0x49, 0x30, // 6
    0x01, 0x71, 0x09, 0x05, 0x03, // 7
    0x36, 0x49, 0x49, 0x49, 0x36, // 8
    0x06, 0x49, 0x49, 0x29, 0x1E, // 9
    0x00, 0x36, 0x36, 0x00, 0x00, // :
    0x00, 0x56, 0x36, 0x00, 0x00, // ;
    0x00, 0x08, 0x14, 0x22, 0x41, // <
    0x14, 0x14, 0x14, 0x14, 0x14, // =
    0x00, 0x41, 0x22, 0x14, 0x08, // >
    0x02, 0x01, 0x51, 0x09, 0x06, // ?
    0x32, 0x49, 0x79, 0x41, 0x3E, // @
    0x7E, 0x11, 0x11, 0x11, 0x7E, // A
    0x7F, 0x49, 0x49, 0x49, 0x36, // B
    0x3E, 0x41, 0x41, 0x41, 0x22, // C
    0x7F, 0x41, 0x41, 0x22, 0x1C, // D
    0x7F, 0x49, 0x49, 0x49, 0x41, // E
    0x7F, 0x09, 0x09, 0x09, 0x01, // F
    0x3E, 0x41, 0x49, 0x49, 0x7A, // G
    0x7F, 0x08, 0x08, 0x08, 0x7F, // H
    0x00, 0x41, 0x7F, 0x41, 0x00, // I
    0x20, 0x40, 0x41, 0x3F, 0x01, // J
    0x7F, 0x08, 0x14, 0x22, 0x41, // K
    0x7F, 0x40, 0x40, 0x40, 0x40, // L
    0x7F, 0x02, 0x0C, 0x02, 0x7F, // M
    0x7F, 0x04, 0x08, 0x10, 0x7F, // N
    0x3E, 0x41, 0x41, 0x41, 0x3E, // O
    0x7F, 0x09, 0x09, 0x09, 0x06, // P
    0x3E, 0x41, 0x51, 0x21, 0x5E, // Q
    0x7F, 0x09, 0x19, 0x29, 0x46, // R
    0x46, 0x49, 0x49, 0x49, 0x31, // S
    0x01, 0x01, 0x7F, 0x01, 0x01, // T
    0x3F, 0x40, 0x40, 0x40, 0x3F, // U
    0x1F, 0x20, 0x40, 0x20, 0x1F, // V
    0x3F, 0x40, 0x38, 0x40, 0x3F, // W
    0x63, 0x14, 0x08, 0x14, 0x63, // X
    0x07, 0x08, 0x70, 0x08, 0x07, // Y
    0x61, 0x51, 0x49, 0x45, 0x43, // Z
    0x00, 0x7F, 0x41, 0x41, 0x00, // [
    0x02, 0x04, 0x08, 0x10, 0x20, // backslash
    0x00, 0x41, 0x41, 0x7F, 0x00, // ]
    0x04, 0x02, 0x01, 0x02, 0x04, // ^
    0x40, 0x40, 0x40, 0x40, 0x40, // _
    0x00, 0x01, 0x02, 0x04, 0x00, // `
    0x20, 0x54, 0x54, 0x54, 0x78, // a
    0x7F, 0x48, 0x44, 0x44, 0x38, // b
    0x38, 0x44, 0x44, 0x44, 0x20, // c
    0x38, 0x44, 0x44, 0x48, 0x7F, // d
    0x38, 0x54, 0x54, 0x54, 0x18, // e
    0x08, 0x7E, 0x09, 0x01, 0x02, // f
    0x0C, 0x52, 0x52, 0x52, 0x3E, // g
    0x7F, 0x08, 0x04, 0x04, 0x78, // h
    0x00, 0x44, 0x7D, 0x40, 0x00, // i
    0x20, 0x40, 0x44, 0x3D, 0x00, // j
    0x7F, 0x10, 0x28, 0x44, 0x00, // k
    0x00, 0x41, 0x7F, 0x40, 0x00, // l
    0x7C, 0x04, 0x18, 0x04, 0x78, // m
    0x7C, 0x08, 0x04, 0x04, 0x78, // n
    0x38, 0x44, 0x44, 0x44, 0x38, // o
    0x7C, 0x14, 0x14, 0x14, 0x08, // p
    0x08, 0x14, 0x14, 0x18, 0x7C, // q
    0x7C, 0x08, 0x04, 0x04, 0x08, // r
    0x48, 0x54, 0x54, 0x54, 0x20, // s
    0x04, 0x3F, 0x44, 0x40, 0x20, // t
    0x3C, 0x40, 0x40, 0x20, 0x7C, // u
    0x1C, 0x20, 0x40, 0x20, 0x1C, // v
    0x3C, 0x40, 0x30, 0x40, 0x3C, // w
    0x44, 0x28, 0x10, 0x28, 0x44, // x
    0x0C, 0x50, 0x50, 0x50, 0x3C, // y
    0x44, 0x64, 0x54, 0x4C, 0x44, // z
    0x00, 0x08, 0x36, 0x41, 0x00, // {
    0x00, 0x00, 0x7F, 0x00, 0x00, // |
    0x00, 0x41, 0x36, 0x08, 0x00, // }
    0x08, 0x14, 0x08, 0x14, 0x08, // ~
};

static void oled_clear_line(int line)
{
    memset(s_lines[line], 0, OLED_LINE_LEN);
    s_line_dirty[line] = true;
}

static void oled_draw_char_to_page(int x, int y, char c, uint8_t *page_buf)
{
    if (c < 32 || c > 126) {
        c = '?';
    }
    int idx = (int)(c - 32) * 5;
    const uint8_t *glyph = &s_font_5x7[idx];

    for (int col = 0; col < OLED_FONT_WIDTH; col++) {
        uint8_t col_data = glyph[col];
        for (int row = 0; row < OLED_FONT_HEIGHT; row++) {
            int fb_x = x + col;
            int fb_y = y + row;
            if (fb_x < 0 || fb_x >= OLED_WIDTH || fb_y < 0 || fb_y >= OLED_HEIGHT) {
                continue;
            }
            if (col_data & (1 << row)) {
                int bit = fb_y % 8;
                page_buf[fb_x] |= (1 << bit);
            }
        }
    }
}

static void oled_render_line_to_page(int line, uint8_t *page_buf)
{
    memset(page_buf, 0, OLED_WIDTH);
    int x = 0;
    int y = line * OLED_LINE_HEIGHT;
    const char *str = s_lines[line];

    while (*str && x < OLED_WIDTH) {
        oled_draw_char_to_page(x, y, *str, page_buf);
        x += OLED_FONT_WIDTH + OLED_CHAR_SPACING;
        str++;
    }
}

static esp_err_t oled_i2c_write(uint8_t *data, size_t len)
{
    return i2c_master_transmit(s_i2c_dev, data, len, pdMS_TO_TICKS(10));
}

static void oled_send_cmd(uint8_t cmd)
{
    uint8_t buf[2] = {0x00, cmd};
    esp_err_t ret = oled_i2c_write(buf, 2);
    if (ret != ESP_OK) {
        ESP_LOGW(TAG, "I2C cmd write failed: %s", esp_err_to_name(ret));
    }
}

static void oled_send_page_data(const uint8_t *data, size_t len)
{
    uint8_t buf[OLED_WIDTH + 1];
    if (len > OLED_WIDTH) {
        len = OLED_WIDTH;
    }
    buf[0] = 0x40;
    memcpy(buf + 1, data, len);
    esp_err_t ret = oled_i2c_write(buf, len + 1);
    if (ret != ESP_OK) {
        ESP_LOGW(TAG, "I2C page data write failed: %s", esp_err_to_name(ret));
    }
}

static void oled_init_commands(void)
{
    oled_send_cmd(0xAE);
    oled_send_cmd(0x20);
    oled_send_cmd(0x00);
    oled_send_cmd(0xB0);
    oled_send_cmd(0xC8);
    oled_send_cmd(0x00);
    oled_send_cmd(0x10);
    oled_send_cmd(0x40);
    oled_send_cmd(0x81);
    oled_send_cmd(0xFF);
    oled_send_cmd(0xA1);
    oled_send_cmd(0xA6);
    oled_send_cmd(0xA8);
    oled_send_cmd(0x3F);
    oled_send_cmd(0xA4);
    oled_send_cmd(0xD3);
    oled_send_cmd(0x00);
    oled_send_cmd(0xD5);
    oled_send_cmd(0xF0);
    oled_send_cmd(0xD9);
    oled_send_cmd(0x22);
    oled_send_cmd(0xDA);
    oled_send_cmd(0x12);
    oled_send_cmd(0xDB);
    oled_send_cmd(0x20);
    oled_send_cmd(0x8D);
    oled_send_cmd(0x14);
    oled_send_cmd(0xAF);
}

static void oled_flush_line(int line)
{
    if (!s_initialized || !s_line_dirty[line]) {
        return;
    }

    oled_render_line_to_page(line, s_page_buf);
    oled_send_cmd(0xB0 + line);
    oled_send_cmd(0x00);
    oled_send_cmd(0x10);
    oled_send_page_data(s_page_buf, OLED_WIDTH);
    s_line_dirty[line] = false;
}

static void oled_flush_all(void)
{
    if (!s_initialized) {
        return;
    }

    for (int line = 0; line < OLED_LINES; line++) {
        oled_flush_line(line);
    }
}

static void oled_set_line(int line, const char *text)
{
    if (line < 0 || line >= OLED_LINES || !text) {
        return;
    }

    size_t len = strlen(text);
    if (len >= OLED_LINE_LEN) {
        len = OLED_LINE_LEN - 1;
    }

    memcpy(s_lines[line], text, len);
    s_lines[line][len] = '\0';
    s_line_dirty[line] = true;
}

static void oled_draw_screen(const gnss_fix_t *fix, bool ble_connected)
{
    char buf[OLED_LINE_LEN];

    oled_set_line(0, "GNSS Tracker");

    if (fix && fix->valid) {
        switch (fix->type) {
            case GNSS_FIX_3D:
                oled_set_line(1, "3D FIX");
                break;
            case GNSS_FIX_2D:
                oled_set_line(1, "2D FIX");
                break;
            default:
                oled_set_line(1, "NO FIX");
                break;
        }

        snprintf(buf, sizeof(buf), "Lat:%.5f", fix->latitude);
        oled_set_line(2, buf);

        snprintf(buf, sizeof(buf), "Lon:%.5f", fix->longitude);
        oled_set_line(3, buf);

        snprintf(buf, sizeof(buf), "Alt:%.1fm", fix->altitude_m);
        oled_set_line(4, buf);

        snprintf(buf, sizeof(buf), "%d sat %.1fkm/h", fix->satellites_used, fix->speed_kmh);
        oled_set_line(5, buf);
    } else {
        oled_set_line(1, "Waiting for fix");
        oled_set_line(2, "No satellites");
        oled_set_line(3, "Go outside...");
        oled_clear_line(4);
        oled_clear_line(5);
    }

    oled_set_line(7, ble_connected ? "BLE: ON" : "BLE: OFF");

    oled_flush_all();
}

static void oled_task(void *arg)
{
    ESP_LOGI(TAG, "Display task started");
    vTaskDelay(pdMS_TO_TICKS(500));

    while (1) {
        gnss_fix_t fix;
        bool ble_conn;
        bool dirty = false;

        // Atomically read data and reset dirty flag under mutex protection
        if (xSemaphoreTake(s_data_mutex, pdMS_TO_TICKS(100)) == pdTRUE) {
            fix = s_last_fix;
            ble_conn = s_ble_connected;
            dirty = s_display_dirty;    // Read dirty flag
            s_display_dirty = false;     // Reset atomically with read
            xSemaphoreGive(s_data_mutex);
        }

        // Draw outside mutex to avoid blocking other tasks
        if (dirty) {
            oled_draw_screen(&fix, ble_conn);
        }

        vTaskDelay(pdMS_TO_TICKS(250));
    }
}

static esp_err_t oled_i2c_scan(uint8_t *found_addr)
{
    if (found_addr) {
        *found_addr = 0;
    }

    ESP_LOGI(TAG, "Scanning I2C bus (SDA=%d, SCL=%d)...", OLED_I2C_SDA_PIN, OLED_I2C_SCL_PIN);

    i2c_master_bus_handle_t scan_bus = NULL;
    i2c_master_bus_config_t bus_conf = {
        .clk_source = I2C_CLK_SRC_DEFAULT,
        .sda_io_num = OLED_I2C_SDA_PIN,
        .scl_io_num = OLED_I2C_SCL_PIN,
        .i2c_port = OLED_I2C_PORT,
    };

    esp_err_t ret = i2c_new_master_bus(&bus_conf, &scan_bus);
    if (ret != ESP_OK) {
        ESP_LOGE(TAG, "I2C scan: failed to create bus: %s", esp_err_to_name(ret));
        return ret;
    }

    // SSD1306 обычно живёт по 0x3C или 0x3D; принимаем и то, и другое
    const uint8_t candidate_addrs[] = {0x3C, 0x3D};
    bool found = false;
    uint8_t detected = 0;

    for (size_t i = 0; i < sizeof(candidate_addrs); i++) {
        uint8_t addr = candidate_addrs[i];
        i2c_master_dev_handle_t dev = NULL;
        esp_err_t rc = i2c_master_bus_add_device(scan_bus, &(i2c_device_config_t){
            .dev_addr_length = I2C_ADDR_BIT_LEN_7,
            .device_address = addr,
            .scl_speed_hz = 100000,
        }, &dev);

        if (rc == ESP_OK) {
            uint8_t dummy = 0x00;
            rc = i2c_master_transmit(dev, &dummy, 1, pdMS_TO_TICKS(10));
            if (rc == ESP_OK) {
                ESP_LOGI(TAG, "I2C scan: found OLED at 0x%02X", addr);
                detected = addr;
                found = true;
            }
            i2c_master_bus_rm_device(dev);
        }

        if (found) {
            break;
        }
    }

    i2c_del_master_bus(scan_bus);

    if (!found) {
        ESP_LOGW(TAG, "OLED not found on I2C bus. Display disabled.");
        return ESP_ERR_NOT_FOUND;
    }

    if (found_addr) {
        *found_addr = detected;
    }
    return ESP_OK;
}

void oled_display_init(void)
{
    ESP_LOGI(TAG, "Initializing OLED SSD1306...");

    s_data_mutex = xSemaphoreCreateMutex();
    if (!s_data_mutex) {
        ESP_LOGE(TAG, "Failed to create mutex");
        return;
    }

    uint8_t detected_addr = 0;
    esp_err_t scan_ret = oled_i2c_scan(&detected_addr);
    if (scan_ret != ESP_OK || detected_addr == 0) {
        ESP_LOGW(TAG, "OLED not detected, display disabled");
        s_initialized = false;
        return;
    }

    i2c_master_bus_config_t bus_conf = {
        .clk_source = I2C_CLK_SRC_DEFAULT,
        .sda_io_num = OLED_I2C_SDA_PIN,
        .scl_io_num = OLED_I2C_SCL_PIN,
        .i2c_port = OLED_I2C_PORT,
    };

    esp_err_t ret = i2c_new_master_bus(&bus_conf, &s_i2c_bus);
    if (ret != ESP_OK) {
        ESP_LOGE(TAG, "Failed to create I2C bus: %s", esp_err_to_name(ret));
        s_initialized = false;
        return;
    }

    i2c_master_bus_add_device(s_i2c_bus, &(i2c_device_config_t){
        .dev_addr_length = I2C_ADDR_BIT_LEN_7,
        .device_address = detected_addr,
        .scl_speed_hz = OLED_I2C_CLK_HZ,
    }, &s_i2c_dev);

    vTaskDelay(pdMS_TO_TICKS(100));

    oled_init_commands();

    // Initialize line buffer
    for (int i = 0; i < OLED_LINES; i++) {
        oled_clear_line(i);
    }

    s_initialized = true;
    ESP_LOGI(TAG, "OLED SSD1306 initialized at 0x%02X", detected_addr);

    xTaskCreate(oled_task, "oled_task", 6144, NULL, 4, NULL);
}

void oled_display_show_boot(void)
{
    if (!s_initialized) {
        return;
    }
    oled_set_line(0, "ESP32 GNSS /");
    oled_set_line(1, "ABC abc 0123");
    oled_flush_all();
}

void oled_display_update(const gnss_fix_t *fix, bool ble_connected)
{
    if (!s_initialized || !s_data_mutex) {
        return;
    }

    if (xSemaphoreTake(s_data_mutex, pdMS_TO_TICKS(10)) == pdTRUE) {
        if (fix) {
            s_last_fix = *fix;
        }
        s_ble_connected = ble_connected;
        s_display_dirty = true;
        xSemaphoreGive(s_data_mutex);
    }
}
