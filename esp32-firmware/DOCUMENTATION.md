# ESP32-S3 GNSS Tracker — Technical Documentation

> **Project:** esp32s3-gnss  
> **Target:** ESP32-S3 DevKitC-1 (Rev 2, 16MB QIO, без PSRAM)  
> **Framework:** ESP-IDF v5.5.5  
> **Language:** C (FreeRTOS, NimBLE)  
> **Last updated:** 2026-08-17

---

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [Directory Structure & Modules](#2-directory-structure--modules)
3. [Installation, Environment Setup & Running](#3-installation-environment-setup--running)
4. [API Reference](#4-api-reference)
5. [Usage Examples](#5-usage-examples)
6. [Troubleshooting & FAQ](#6-troubleshooting--faq)
7. [Appendix](#7-appendix)

---

## 1. Architecture Overview

### 1.1 System Context

The ESP32-S3 GNSS Tracker is a low-power BLE beacon that receives NMEA sentences from a u-blox NEO-7M GPS receiver and forwards them to a paired smartphone or PC via the Nordic UART Service (NUS). When no real GPS fix is available, an internal simulator generates synthetic NMEA data for testing.

### 1.2 Hardware Stack

| Component | Specification |
|-----------|---------------|
| **MCU** | ESP32-S3 (Xtensa LX7, dual-core, 160 MHz, 16MB Flash QIO) |
| **GPS** | u-blox NEO-7M (UART1, 9600 baud, 3.3V) |
| **OLED** | SSD1306 128×64 (I2C, GPIO8=SDA, GPIO9=SCL, addr 0x3C) |
| **Power** | 18650 Li-ion + DC-DC buck converter |
| **BLE** | NimBLE stack (Bluetooth 5.0, LE 2M PHY) |
| **Battery ADC** | ADC1_CH2 (GPIO2) |
| **Deep-sleep button** | GPIO0 (active LOW) |

### 1.3 Software Stack

```
┌──────────────────────────────────────────────────────┐
│  Application Layer                                    │
│  ├── main.c         — app_main, simulator task       │
│  ├── gps_uart.c     — UART driver, line parser       │
│  ├── nmea_parser.c  — NMEA sentence parser           │
│  ├── ble_nus.c      — BLE Nordic UART Service        │
│  ├── battery_adc.c  — Battery voltage measurement    │
│  ├── power_manager.c — Deep-sleep management          │
│  └── oled_display.c  — SSD1306 OLED via I2C           │
├──────────────────────────────────────────────────────┤
│  ESP-IDF Framework                                    │
│  ├── FreeRTOS        — Task scheduling                │
│  ├── NimBLE Host     — BLE GATT/GAP/ATT              │
│  ├── ESP-IDF Drivers — UART, ADC, GPIO, Timer        │
│  └── NVS             — Non-volatile storage           │
├──────────────────────────────────────────────────────┤
│  Hardware Abstraction Layer (HAL)                     │
│  ├── BT Controller   — BLE radio                      │
│  ├── UART Driver     — GPS data reception             │
│  └── ADC Driver      — Battery monitoring             │
└──────────────────────────────────────────────────────┘
```

### 1.4 Data Flow

```
NEO-7M ──UART 9600──> GPIO18 (RX) ──> gps_uart_task ──> line callback
                                                                   │
                                                                    v
                                                              nmea_parser_feed()
                                                                   │
                                                                    v
                                                              gnss_fix_t
                                                                   │
                                                                    v
                                                              ble_nus_send_nmea()
                                                                   │
                                                                    v
                                                              BLE Notification
                                                                   │
                                                                    v
                                                              Smartphone / PC
```

### 1.5 Key Design Decisions

| Decision | Rationale |
|----------|-----------|
| **NimBLE over Bluedroid** | Lower memory footprint, better performance on ESP32-S3 |
| **BLE security disabled** | Simplifies connection flow; no pairing/bonding required for data transfer |
| **GAP event listener over callback** | `ble_gap_event_listener_register()` provides cleaner multi-event handling |
| **Direct `val_handle` usage** | Avoids race condition where `ble_gatts_add_svcs()` callback is asynchronous |
| **Chunked notifications** | BLE MTU-aware splitting prevents oversized ATT packets |

---

## 2. Directory Structure & Modules

```
esp32s3-gnss-ESP-IDF/
├── main/
│   ├── app_config.h          # Pin definitions, timeouts, BLE constants
│   ├── main.c                # Entry point, module integration, simulator
│   ├── gps_uart.c / .h       # UART1 driver for NEO-7M
│   ├── nmea_parser.c / .h    # NMEA sentence parser (GGA, RMC, GSA, GSV, VTG, GLL)
│   ├── ble_nus.c / .h        # BLE Nordic UART Service (NUS)
│   ├── battery_adc.c / .h    # Battery voltage via ADC1_CH2
│   └── power_manager.c / .h  # Deep-sleep button handling
│
├── components/
│   └── nmea_parser/          # Reusable NMEA parser component
│       ├── include/
│       │   └── nmea_parser.h
│       └── src/
│           └── nmea_parser.c
│
├── build/                    # Build artifacts (generated)
├── sdkconfig                 # ESP-IDF configuration
├── partitions.csv            # Partition table
├── CMakeLists.txt            # Top-level CMake
├── README.md                 # Quick-start guide
├── fix4.md                   # Bug report: BLE notification delivery
└── DOCUMENTATION.md          # This file
```

### 2.1 Module Descriptions

#### `app_config.h`
Central configuration header defining hardware pins, baud rates, timeouts, and BLE parameters.

| Macro | Value | Description |
|-------|-------|-------------|
| `GPS_UART_NUM` | `UART_NUM_1` | UART peripheral for GPS |
| `GPS_UART_TX_PIN` | `17` | ESP32 TX → GPS RX |
| `GPS_UART_RX_PIN` | `18` | ESP32 RX ← GPS TX |
| `GPS_UART_BAUD` | `9600` | NEO-7M default baud rate |
| `GPS_DATA_TIMEOUT_MS` | `5000` | No-data warning threshold |
| `GPS_RAW_DEBUG` | `1` | Enable raw byte logging (first 200 bytes) |
| `BATTERY_ADC_PIN` | `2` | ADC1 channel 2 |
| `DEEP_SLEEP_BTN_PIN` | `0` | Boot button (GPIO0) |
| `BLE_DEVICE_NAME` | `"ESP32S3-GPS"` | BLE advertised name |
| `BLE_ADV_INTERVAL_MS` | `500` | Advertising interval |
| `BLE_MTU_CHUNK_SIZE` | `20` | Default chunk size for BLE packets |

#### `main.c`
Application entry point and orchestrator.

- **`app_main()`** — Initializes GPS UART, NMEA parser, power manager, battery ADC, BLE NUS, and creates background tasks.
- **`on_gps_line()`** — Callback invoked for each complete NMEA line. Parses the sentence and forwards valid fixes via BLE.
- **`simulator_task()`** — FreeRTOS task that sends a synthetic `$GPRMC` sentence every second when BLE is connected and no real fix is available.

#### `gps_uart.c / .h`
UART driver for the NEO-7M GPS module.

- **`gps_uart_init()`** — Configures UART1 (GPIO17/18, 9600 baud, 8N1, no flow control), installs driver with 2048-byte RX buffer.
- **`gps_uart_register_callback()`** — Registers a line-completion callback.
- **`gps_uart_task_start()`** — Creates the FreeRTOS task that reads bytes, assembles lines, and invokes the callback.
- **Diagnostics:** Counts total bytes, lines, and NMEA sentences; logs statistics every 5 seconds; warns after 5 seconds of no data.

#### `nmea_parser.c / .h`
Standalone NMEA sentence parser supporting multi-GNSS prefixes.

- **Supported sentences:** `$GPGGA`, `$GNGGA`, `$GPRMC`, `$GNRMC`, `$GPGSA`, `$GNGSA`, `$GPGSV`, `$GNGSV`, `$GPVTG`, `$GNVTG`, `$GPGLL`, `$GNGLL`
- **`nmea_parser_init()`** — Initializes the parser.
- **`nmea_parser_feed()`** — Parses a sentence, validates checksum, and populates a `gnss_fix_t` structure.
- **`gnss_fix_t`** — Struct containing: `type`, `valid`, `latitude`, `longitude`, `altitude_m`, `speed_kmh`, `course_deg`, `satellites_used`, `fix_quality`, `hdop`, `last_update_ms`.

#### `ble_nus.c / .h`
BLE Nordic UART Service implementation using NimBLE.

- **Service UUID:** `6E400001-B5A3-F393-E0A9-E50E24DCCA9E`
- **TX Characteristic (Notify):** `6E400003-B5A3-F393-E0A9-E50E24DCCA9E` — handle 16
- **RX Characteristic (Write):** `6E400002-B5A3-F393-E0A9-E50E24DCCA9E` — handle 19
- **Key features:**
  - GAP event listener for CONNECT/DISCONNECT/SUBSCRIBE/MTU
  - Asynchronous GATT registration callback with UUID-based handle resolution
  - Chunked notification sending (MTU-aware)
  - Automatic advertising restart on disconnect
  - Security disabled (no pairing required)

#### `battery_adc.c / .h`
Simple battery voltage measurement.

- **`battery_adc_init()`** — Configures ADC1, channel 2 (GPIO2), 12-bit, 11dB attenuation.
- **`battery_read_voltage()`** — Returns voltage in volts ( assumes 3.3V reference, no divider calibration).

#### `oled_display.c / .h`
SSD1306 OLED display driver via I2C.

- **`oled_display_init()`** — Initializes I2C master bus (GPIO8=SDA, GPIO9=SCL, 400kHz), creates SSD1306 panel via `esp_lcd`, starts display task.
- **`oled_display_show_boot()`** — Shows boot screen with "GNSS Tracker" / "Booting...".
- **`oled_display_update(fix, ble_connected)`** — Thread-safe update from GPS callback. Refreshes display with latest fix data and BLE status.
- **Display layout (128×64, 5×7 font):**
  - Line 0: `GNSS Tracker`
  - Line 1: Fix status (`3D FIX` / `2D FIX` / `Waiting for fix`)
  - Line 2: Latitude
  - Line 3: Longitude
  - Line 4: Altitude
  - Line 5: Satellites + speed
  - Line 6: BLE status (`ON`/`OFF`)

#### `power_manager.c / .h`
Power management utilities.

- **`power_manager_init()`** — Configures GPIO0 as input with pull-up for deep-sleep button.
- **`power_enter_deep_sleep()`** — Triggers deep sleep mode.

---

## 3. Installation, Environment Setup & Running

### 3.1 Prerequisites

| Tool | Version | Notes |
|------|---------|-------|
| **ESP-IDF** | v5.5.5 | Pre-installed at `C:\Users\Mi\esp-idf-v5.5.5` |
| **Python** | 3.14.6 | Used by `idf.py` |
| **CMake** | 3.30.2 | Bundled with ESP-IDF |
| **Ninja** | Bundled | Build system |
| **Serial port** | COM5 | ESP32-S3 DevKitC-1 |

### 3.2 Environment Setup (Windows PowerShell)

```powershell
# Activate ESP-IDF environment
powershell -ExecutionPolicy Bypass -File C:\Users\Mi\esp-idf-v5.5.5\export.ps1 -ForDesktop

# Navigate to project
cd C:\Users\Mi\Ublox\esp32s3-gnss-ESP-IDF
```

### 3.3 Build

```powershell
idf.py build
```

Build artifacts are placed in the `build/` directory:
- `build/esp32s3_gnss.bin` — Application firmware
- `build/bootloader/bootloader.bin` — Bootloader
- `build/partition_table/partition-table.bin` — Partition table

### 3.4 Flash

```powershell
idf.py -p COM5 flash
```

Or flash + monitor in one command:

```powershell
idf.py -p COM5 flash monitor
```

### 3.5 Monitor (Serial Console)

```powershell
idf.py -p COM5 monitor
```

- **Baud rate:** 115200
- **Exit monitor:** `Ctrl+]`

### 3.6 Configuration

Project configuration is stored in `sdkconfig`. Key settings:

| Setting | Value | Description |
|---------|-------|-------------|
| `CONFIG_BT_NIMBLE_ENABLED` | `y` | NimBLE stack enabled |
| `CONFIG_BT_NIMBLE_SECURITY_ENABLE` | `n` | BLE security disabled |
| `CONFIG_BT_NIMBLE_ATT_PREFERRED_MTU` | `256` | Preferred MTU |
| `CONFIG_BT_NIMBLE_MAX_CONNECTIONS` | `3` | Max simultaneous connections |
| `CONFIG_MONITOR_BAUD` | `115200` | Serial monitor baud rate |
| `CONFIG_ESP_DEFAULT_CPU_FREQ_MHZ` | `160` | CPU frequency |

To modify settings:

```powershell
idf.py menuconfig
```

### 3.7 Partition Table

Defined in `partitions.csv`:

| Name | Type | SubType | Offset | Size |
|------|------|---------|--------|------|
| nvs | data | nvs | 0x9000 | 24K |
| phy_init | data | phy | 0xf000 | 4K |
| factory | app | factory | 0x10000 | 1M |

---

## 4. API Reference

### 4.1 GPS UART (`gps_uart.h`)

```c
esp_err_t gps_uart_init(void);
esp_err_t gps_uart_register_callback(gps_line_callback_t cb);
esp_err_t gps_uart_task_start(void);
```

**Details:**

- **`gps_uart_init()`** — Initializes UART1 with configured baud rate, pins, and buffer size. Must be called before `gps_uart_task_start()`.
- **`gps_uart_register_callback(cb)`** — Registers a callback of type `void (*cb)(const char *line, int len)` that is invoked for each complete NMEA line (terminated by `\n`).
- **`gps_uart_task_start()`** — Creates the FreeRTOS task `gps_uart_task` that continuously reads UART bytes, assembles lines, and invokes the registered callback.

### 4.2 NMEA Parser (`nmea_parser.h`)

```c
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
} gnss_fix_t;

void nmea_parser_init(void);
bool nmea_parser_feed(const char *sentence, int len, gnss_fix_t *out_fix);
```

**Details:**

- **`nmea_parser_init()`** — Initializes the parser (logs initialization).
- **`nmea_parser_feed(sentence, len, out_fix)`** — Parses a complete NMEA sentence. Validates checksum. Populates `out_fix` with parsed data. Returns `true` if the sentence was recognized and parsed.

**Parsing rules:**
- `$GPGGA` / `$GNGGA`: Fix quality, satellites, HDOP, altitude, lat/lon
- `$GPRMC` / `$GNRMC`: Status (A=valid), lat/lon, speed, course
- `$GPGSA` / `$GNGSA`: Fix type (1=no fix, 2=2D, 3=3D), HDOP
- `$GPGSV` / `$GNGSV`: Total satellites in view
- `$GPVTG` / `$GNVTG`: Speed and course
- `$GPGLL` / `$GNGLL`: Lat/lon with status

### 4.3 BLE NUS (`ble_nus.h`)

```c
esp_err_t ble_nus_init(void);
esp_err_t ble_nus_start_advertising(void);
esp_err_t ble_nus_send_nmea(const char *nmea_str, int len);
bool ble_nus_is_connected(void);
void ble_nus_status_task(void *arg);
```

**Details:**

- **`ble_nus_init()`** — Initializes NVS, NimBLE port, host config, GAP/GATT services, NUS service, device name, and starts the NimBLE host task. Returns `ESP_OK` on success.
- **`ble_nus_start_advertising()`** — Starts BLE advertising with device name `ESP32S3-GPS`, undirected connectable mode, general discoverable. Automatically called on stack sync and disconnect.
- **`ble_nus_send_nmea(nmea_str, len)`** — Sends an NMEA string over BLE notifications. Handles MTU-aware chunking. Returns `ESP_OK` on success, `ESP_FAIL` if not connected or notification fails.
- **`ble_nus_is_connected()`** — Returns `true` if a BLE client is connected.
- **`ble_nus_status_task(arg)`** — FreeRTOS task that periodically checks connection status every 5 seconds.

### 4.4 Battery ADC (`battery_adc.h`)

```c
void battery_adc_init(void);
float battery_read_voltage(void);
```

**Details:**

- **`battery_adc_init()`** — Configures ADC1, channel 2 (GPIO2), 12-bit resolution, 11dB attenuation.
- **`battery_read_voltage()`** — Reads raw ADC value and converts to voltage assuming 3.3V reference. **Note:** Does not account for voltage divider — calibration required for accurate battery voltage.

### 4.5 Power Manager (`power_manager.h`)

```c
void power_manager_init(void);
void power_enter_deep_sleep(void);
```

**Details:**

- **`power_manager_init()`** — Configures GPIO0 (BOOT button) as input with internal pull-up.
- **`power_enter_deep_sleep()`** — Enters deep sleep mode. Wake-up sources must be configured separately if needed.

### 4.6 OLED Display (`oled_display.h`)

```c
void oled_display_init(void);
void oled_display_show_boot(void);
void oled_display_update(const gnss_fix_t *fix, bool ble_connected);
```

**Details:**

- **`oled_display_init()`** — Initializes I2C master bus (GPIO8=SDA, GPIO9=SCL, 400kHz), creates SSD1306 panel via `esp_lcd_panel_ssd1306()`, turns on display, and starts `oled_task` (priority 4, 4096 bytes stack).
- **`oled_display_show_boot()`** — Shows boot screen ("GNSS Tracker", "Booting...").
- **`oled_display_update(fix, ble_connected)`** — Thread-safe update from GPS callback. Uses FreeRTOS mutex to pass data to display task.

**Display layout (128×64, 5×7 bitmap font):**
- Row 0: `GNSS Tracker`
- Row 8: Fix status (`3D FIX` / `2D FIX` / `Waiting for fix`)
- Row 16: Latitude
- Row 24: Longitude
- Row 32: Altitude
- Row 40: Satellites + speed
- Row 56: BLE status (`ON`/`OFF`)

### 4.7 Main Application (`main.c`)

```c
void app_main(void);
```

**Details:**

- Initializes all subsystems in order: GPS UART → NMEA parser → Power manager → Battery ADC → BLE NUS
- Creates `ble_nus_status_task` (priority 5, 4096 bytes stack)
- Creates `simulator_task` (priority 5, 4096 bytes stack)
- Registers `on_gps_line` as the GPS line callback

### 4.7 Internal Data Structures

#### `gnss_fix_t` (nmea_parser.h)

```c
typedef struct {
    gnss_fix_type_t type;      // GNSS_FIX_NONE, GNSS_FIX_2D, GNSS_FIX_3D
    bool valid;                // True if fix is valid
    double latitude;           // Decimal degrees (negative for S)
    double longitude;          // Decimal degrees (negative for W)
    double altitude_m;         // Meters above mean sea level
    double speed_kmh;          // Speed over ground (km/h)
    double course_deg;         // Course over ground (degrees)
    uint8_t satellites_used;   // Number of satellites used in fix
    uint8_t fix_quality;       // 0=invalid, 1=GPS, 2=DGPS, etc.
    double hdop;               // Horizontal dilution of precision
    int64_t last_update_ms;    // Timestamp of last update (milliseconds)
} gnss_fix_t;
```

#### BLE NUS Internal State (ble_nus.c)

| Variable | Type | Description |
|----------|------|-------------|
| `s_conn_handle` | `uint16_t` | Current BLE connection handle (`BLE_HS_CONN_HANDLE_NONE` if disconnected) |
| `s_connected` | `bool` | Connection state flag |
| `s_is_subscribed` | `bool` | Client has enabled notifications on TX characteristic |
| `s_tx_val_handle` | `uint16_t` | Value handle of TX characteristic (16) |
| `s_rx_val_handle` | `uint16_t` | Value handle of RX characteristic (19) |
| `s_gap_event_count` | `volatile int` | Total GAP events received (diagnostic) |

---

## 5. Usage Examples

### 5.1 Receiving NMEA Data via BLE (Smartphone)

1. **Scan** for BLE devices and find `ESP32S3-GPS`.
2. **Connect** to the device.
3. **Discover services** — locate Nordic UART Service (`6E400001-B5A3-F393-E0A9-E50E24DCCA9E`).
4. **Enable notifications** on the TX Characteristic (`6E400003-B5A3-F393-E0A9-E50E24DCCA9E`) by writing `0x0100` to its CCCD (`0x2902`).
5. **Receive** NMEA sentences as notifications, e.g.:
   ```
    $GPRMC,120000,A,4807.038,N,01131.000,E,0.0,0.0,010124,,,A*77
   $GPVTG,,,,,,,,,N*30
   $GPGGA,,,,,,0,00,99.99,,,,,,*48
   ```

### 5.2 Receiving NMEA Data via BLE (Python / bleak)

```python
import asyncio
from bleak import BleakClient

DEVICE_ADDRESS = "7C:4F:AD:BB:E2:12"  # Replace with your device MAC
NUS_SERVICE_UUID = "6E400001-B5A3-F393-E0A9-E50E24DCCA9E"
NUS_TX_CHAR_UUID = "6E400003-B5A3-F393-E0A9-E50E24DCCA9E"

def notification_handler(sender, data):
    print(f"Received: {data.decode('utf-8', errors='replace')}")

async def main():
    async with BleakClient(DEVICE_ADDRESS) as client:
        await client.start_notify(NUS_TX_CHAR_UUID, notification_handler)
        print("Listening for NMEA notifications...")
        await asyncio.sleep(60)  # Listen for 60 seconds

asyncio.run(main())
```

### 5.3 Sending Data to ESP32 (Python / bleak)

```python
import asyncio
from bleak import BleakClient

DEVICE_ADDRESS = "7C:4F:AD:BB:E2:12"
NUS_RX_CHAR_UUID = "6E400002-B5A3-F393-E0A9-E50E24DCCA9E"

async def main():
    async with BleakClient(DEVICE_ADDRESS) as client:
        await client.write_gatt_char(NUS_RX_CHAR_UUID, b"Hello ESP32")
        print("Data sent")

asyncio.run(main())
```

### 5.4 Monitoring Serial Output

```powershell
idf.py -p COM5 monitor
```

Expected log output on successful connection:

```
I (325) BLE_NUS: nimble stack synced
I (566) BLE_NUS: GAP event listener registered
I (596) BLE_NUS: BLE advertising started
I (605) MAIN: Simulator task started
I (608) MAIN: GNSS tracker with BLE started. Waiting for connection...
I (31668) BLE_NUS: BLE CONNECT event: status=0 conn_handle=1
I (31673) BLE_NUS: >>> BLE connected, handle=1
I (55507) BLE_NUS: SUBSCRIBE event: conn_handle=1, attr_handle=16, cur_notify=1
I (55508) BLE_NUS: >>> Client notifications ENABLED!
I (32621) MAIN: Simulator: sending fake NMEA...
I (32624) BLE_NUS: Sending NMEA: len=62, conn=1, mtu=23, chunk_size=20
I (32629) NimBLE: att_handle=16
I (32632) BLE_NUS: Chunk 0 sent OK: 20 bytes
...
I (32628) BLE_NUS: BLE send OK: 62 bytes in 4 chunks
```

### 5.5 Custom NMEA Simulator

Replace the simulator string in `main.c` to test with different NMEA sentences:

```c
            const char *fake_nmea = "$GPRMC,120000,A,4807.038,N,01131.000,E,0.0,0.0,010124,,,A*77\r\n";
```

Or send real NMEA data from the GPS module — the parser automatically detects and forwards valid fixes.

---

## 6. Troubleshooting & FAQ

### 6.1 Common Issues

| Issue | Symptoms | Solution |
|-------|----------|----------|
| **No GPS data** | No NMEA strings in monitor log | Check wiring: GPS_TX → GPIO18, GPS_RX → GPIO17. Verify baud rate is 9600. Check `GPS_DATA_TIMEOUT_MS` warnings. |
| **Garbled NMEA output** | Invalid characters in log | NEO-7M baud rate mismatch. Ensure GPS is configured for 9600 baud. |
| **BLE not visible** | Device not found in scanner | Verify `ble_nus_start_advertising()` log message. Check `BLE_DEVICE_NAME` in `app_config.h`. |
| **No BLE notifications** | Connected but no data received | Ensure notifications are enabled on TX characteristic (CCCD = `0x0100`). Check `s_tx_val_handle` in log. |
| **`ble_gatts_notify_custom FAILED! rc=3`** | Notification send fails | Invalid handle. Verify `s_tx_val_handle` is non-zero (should be 16). |
| **`ble_gatts_notify_custom FAILED! rc=11`** | MBUF allocation failure | Increase `CONFIG_BT_NIMBLE_MSYS_1_BLOCK_COUNT` or reduce chunk size. |
| **Connection drops after MTU update** | Disconnect during PHY update | Normal behavior with some BLE stacks. Data resumes after reconnection. |
| **Battery voltage inaccurate** | Wrong voltage reading | Add voltage divider calibration factor in `battery_read_voltage()`. |

### 6.2 Debug Logging

Enable verbose logging via `menuconfig`:

```
Component config → Log → Default log level → DEBUG
```

Or dynamically via esp_log:

```c
esp_log_level_set("BLE_NUS", ESP_LOG_DEBUG);
esp_log_level_set("GPS_UART", ESP_LOG_DEBUG);
esp_log_level_set("nmea_parser", ESP_LOG_DEBUG);
```

### 6.3 BLE Security Note

BLE security (SMP) is **disabled** in this project (`CONFIG_BT_NIMBLE_SECURITY_ENABLE=n`). This means:
- No pairing/bonding required
- No encryption
- Data is transmitted in plaintext over the air
- Suitable for testing and non-sensitive applications

To enable security, modify `sdkconfig` and implement `ble_hs_cfg.sm_io_cap` callback.

### 6.4 FAQ

**Q: Why does the simulator run even when GPS is connected?**  
A: The simulator runs unconditionally every second. Real GPS fixes are forwarded via `on_gps_line()`. The simulator is a fallback for testing without sky view.

**Q: How do I change the BLE device name?**  
A: Modify `BLE_DEVICE_NAME` in `main/app_config.h` and rebuild.

**Q: Can I use WiFi simultaneously with BLE?**  
A: Yes, ESP32-S3 supports WiFi + BLE coexistence. However, this project does not use WiFi.

**Q: How do I enter deep sleep?**  
A: Press the BOOT button (GPIO0). The device will enter deep sleep and can be woken by a GPIO interrupt or timer.

**Q: What is the battery life?**  
A: Depends on advertising interval and connection frequency. At 500ms advertising interval with periodic connections, expect several days on a 18650 battery.

**Q: How do I add more NMEA sentence types?**  
A: Extend `nmea_parser_feed()` in `components/nmea_parser/src/nmea_parser.c` with new `strncmp` blocks and field extraction logic.

---

## 7. Appendix

### 7.1 NMEA Sentence Reference

| Sentence | Description | Key Fields |
|----------|-------------|------------|
| `$GPGGA` | Global Positioning System Fix Data | Time, lat, lon, fix quality, satellites, HDOP, altitude |
| `$GPRMC` | Recommended Minimum Navigation Information | Time, status (A/V), lat, lon, speed, course, date |
| `$GPGSA` | GNSS DOP and Active Satellites | Mode (M/A), fix type, satellites, PDOP, HDOP, VDOP |
| `$GPGSV` | GNSS Satellites in View | Total satellites, PRN, elevation, azimuth, SNR |
| `$GPVTG` | Course and Speed Over Ground | True track, magnetic track, speed (knots/km/h) |
| `$GPGLL` | Geographic Position (Lat/Lon) | Lat, lon, UTC time, status (A/V) |

### 7.2 BLE UUID Reference

| UUID | Type | Description |
|------|------|-------------|
| `6E400001-B5A3-F393-E0A9-E50E24DCCA9E` | Service | Nordic UART Service (NUS) |
| `6E400003-B5A3-F393-E0A9-E50E24DCCA9E` | Characteristic | TX (Notify) — ESP32 sends to client |
| `6E400002-B5A3-F393-E0A9-E50E24DCCA9E` | Characteristic | RX (Write) — Client sends to ESP32 |
| `00002902-0000-1000-8000-00805f9b34fb` | Descriptor | Client Characteristic Configuration (CCCD) |

### 7.3 Pinout Reference

| ESP32-S3 Pin | Function | Direction | Notes |
|--------------|----------|-----------|-------|
| GPIO17 | GPS TX | Output | UART1 TX to GPS RX |
| GPIO18 | GPS RX | Input | UART1 RX from GPS TX |
| GPIO2 | Battery ADC | Input | ADC1_CH2, 3.3V reference |
| GPIO0 | Deep-sleep button | Input | Active LOW, internal pull-up |
| GPIO8 | OLED SDA | Bidirectional | I2C0 data, 4.7kΩ pull-up to 3.3V |
| GPIO9 | OLED SCL | Output | I2C0 clock, 4.7kΩ pull-up to 3.3V |

### 7.4 Build Configurations

| Configuration | Command | Notes |
|---------------|---------|-------|
| **Debug** | `idf.py build` | Default, with assertions and debug symbols |
| **Release** | `idf.py menuconfig` → set optimization to Size/Perf | Smaller/faster binary |
| **Monitor only** | `idf.py -p COM5 monitor` | No rebuild |
| **Clean build** | `idf.py fullclean && idf.py build` | Removes all build artifacts |

### 7.5 Useful Resources

- [ESP-IDF Documentation](https://docs.espressif.com/projects/esp-idf/en/latest/esp32s3/)
- [NimBLE API Reference](https://mynewt.apache.org/latest/ble_hs_api/)
- [NMEA 0183 Standard](https://www.nmea.org/)
- [u-blox NEO-7M Datasheet](https://www.u-blox.com/en/product/neo-7-series)

---

*End of documentation.*
