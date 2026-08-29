# ESP32 GPS Tracker

![Platform](https://img.shields.io/badge/platform-ESP32--S3-blue)
![Language](https://img.shields.io/badge/language-C%20%7C%20Kotlin-orange)
![License](https://img.shields.io/badge/license-MIT-green)
![Android](https://img.shields.io/badge/Android-8.0%2B-brightgreen)
![BLE](https://img.shields.io/badge/BLE-Nordic%20NUS-5.0-blue)

GPS трекер на базе ESP32-S3 с передачей данных по BLE на Android.

## 📦 Структура проекта

```
ESP32-GPS-Combined/
├── esp32-firmware/     # Прошивка для ESP32-S3 (ESP-IDF)
└── android-app/        # Android приложение (Kotlin, Jetpack Compose)
```

## ✨ Возможности

### ESP32-S3 Firmware
- **BLE Nordic UART Service (NUS)** — передача NMEA данных
- **GPS парсинг** — поддержка $GPRMC, $GNGGA, $GPGSV
- **OLED дисплей** — SSD1306 128x64 I2C
- **Power management** — deep sleep, wake-up по кнопке
- **Battery monitoring** — ADC с калибровкой

### Android App
- **BLE подключение** — Nordic Android-BLE Library
- **Карта OSMDroid** — OpenStreetMap без API ключей
- **GPX запись** — экспорт треков
- **NMEA парсинг** — lat/lon, speed, course, altitude
- **MTU 256 + LE 2M PHY** — максимальная скорость

## 🛠 Быстрый старт

### Аппаратное обеспечение

| Компонент | Модель |
|-----------|--------|
| Микроконтроллер | ESP32-S3 DevKitC-1 |
| GPS модуль | u-blox NEO-7M |
| Дисплей | SSD1306 128x64 I2C |

### Сборка прошивки ESP32

```bash
# Клонирование
git clone https://github.com/ZDarow/ESP32-GPS-Combined.git
cd ESP32-GPS-Combined/esp32-firmware

# Активация ESP-IDF
source ~/esp-idf/esp-idf/export.sh

# Конфигурация
idf.py menuconfig

# Сборка
idf.py build

# Прошивка
idf.py -p /dev/ttyACM0 flash monitor
```

### Сборка Android приложения

```bash
cd ../android-app

# Открыть в Android Studio
# или через командную строку:
./gradlew assembleDebug
```

APK будет в `android-app/app/build/outputs/apk/debug/app-debug.apk`

## 📡 BLE UUID

| Сервис/Характеристика | UUID |
|-----------------------|------|
| Nordic UART Service | `6e400001-b5a3-f393-e0a9-e50e24dcca9e` |
| TX (Notify) | `6e400003-b5a3-f393-e0a9-e50e24dcca9e` |
| RX (Write) | `6e400002-b5a3-f393-e0a9-e50e24dcca9e` |

## 📁 Документация

- [ESP32 Firmware README](esp32-firmware/README.md)
- [Android App README](android-app/README.md)
- [Полная документация](esp32-firmware/DOCUMENTATION.ru.md)

## 🔧 Конфигурация

### ESP32 (menuconfig)

```
CONFIG_BLE_DEVICE_NAME="ESP32S3-GPS"
CONFIG_GPS_UART_NUM=1
CONFIG_GPS_BAUD=9600
CONFIG_BATTERY_MIN_VOLTAGE=3.0
CONFIG_BATTERY_MAX_VOLTAGE=4.2
```

### Android команды (BLE RX)

| Команда | Описание |
|---------|---------|
| `SET_RATE 1` | Установить частоту 1 Гц |

## 📊 Архитектура

```
┌─────────────────┐      BLE       ┌─────────────────┐
│   ESP32-S3      │◄──────────────►│    Android      │
│                 │   NUS TX/RX    │                 │
│  ┌───────────┐  │               │  ┌───────────┐  │
│  │  GPS UART │──┼──► NMEA ──────┼─►│  Parser   │  │
│  └───────────┘  │               │  └───────────┘  │
│  ┌───────────┐  │               │  ┌───────────┐  │
│  │   OLED    │  │               │  │   Map     │  │
│  └───────────┘  │               │  └───────────┘  │
│  ┌───────────┐  │               │  ┌───────────┐  │
│  │ Battery   │  │               │  │ GPX Log  │  │
│  └───────────┘  │               │  └───────────┘  │
└─────────────────┘               └─────────────────┘
```

## 🤝 Вклад

Прочитайте [CONTRIBUTING.md](CONTRIBUTING.md) для информации о вкладе в проект.

## 📄 Лицензия

MIT License — подробности в файле [LICENSE](LICENSE).

## 🔗 Полезные ссылки

- [ESP-IDF Documentation](https://docs.espressif.com/projects/esp-idf/)
- [Nordic BLE Android Library](https://github.com/NordicSemiconductor/Android-BLE-Library)
- [OSMDroid Wiki](https://github.com/osmdroid/osmdroid/wiki)
- [u-blox NEO-7 Series](https://www.u-blox.com/en/ublox-neo-7-series-modules.html)
