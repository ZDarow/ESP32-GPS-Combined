# ESP32 GPS Tracker

ESP32-S3 GPS трекер с BLE передачей данных на Android.

## Структура проекта

```
├── esp32-firmware/   # Прошивка для ESP32-S3 (ESP-IDF)
└── android-app/      # Android приложение (Kotlin, Jetpack Compose)
```

## Быстрый старт

### ESP32 прошивка

```bash
cd esp32-firmware
source ~/esp-idf/esp-idf/export.sh
idf.py menuconfig
idf.py build
idf.py -p /dev/ttyACM0 flash
```

### Android приложение

Открыть папку `android-app` в Android Studio (Hedgehog 2024.1.1+ / Koala 2024.1.2+).

## Возможности

- BLE Nordic UART Service (NUS)
- Парсинг NMEA ($GPRMC, $GNGGA)
- Отображение на карте OpenStreetMap
- Запись трека в GPX
- MTU 256 + LE 2M PHY

## UUID

- Service: `6e400001-b5a3-f393-e0a9-e50e24dcca9e`
- TX (notify): `6e400003-b5a3-f393-e0a9-e50e24dcca9e`
- RX (write): `6e400002-b5a3-f393-e0a9-e50e24dcca9e`
