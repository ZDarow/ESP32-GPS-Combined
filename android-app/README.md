# ESP32 GPSTracker (Android)

Android-клиент для ESP32S3 с GPS по BLE (Nordic UART Service).

## Возможности

- BLE-подключение к устройству `ESP32S3-GPS` через Nordic Android-BLE Library
- Парсинг NMEA-сообщений (`$GPRMC`, `$GNGGA`): широта/долгота, скорость, курс, высота, HDOP, число спутников
- Отображение текущей позиции на карте OpenStreetMap (OSMDroid, без API-ключей)
- Запись трека в GPX-файл во внешнюю `Documents` директорию приложения
- Сборка NMEA-строк через буферизацию фрагментированных BLE-пакетов
- MTU 256 + LE 2M PHY
- Минимальный SDK 26 (Android 8.0), target SDK 35

## Стек

- Kotlin 1.9.24
- Jetpack Compose (BOM 2024.09.00)
- Nordic BLE 2.7.0 (`ble`, `ble-livedata`, `ble-ktx`)
- OSMDroid 6.1.18
- kotlinx-coroutines 1.8.1

## Структура

```
app/src/main/java/com/example/esp32gps/
├── GpsApplication.kt   // инициализация OSMDroid (user-agent)
├── MainActivity.kt     // Compose UI + BLE-сканер + карта
├── GpsBleManager.kt    // Nordic BleManager: NUS TX/RX, MTU, PHY
├── NmeaParser.kt       // RMC + GGA, lat/lon в decimal degrees
├── GpsFix.kt           // data-class с текущим фиксом
└── GpxLogger.kt        // запись трека в GPX 1.1
```

## Сборка

1. Открыть `C:\Users\Mi\AndroidProjects\ESP32GPSTracker` в Android Studio (Hedgehog 2024.1.1+ / Koala 2024.1.2+)
2. Gradle Sync → подтянуть wrapper
3. Build → Run
4. На телефоне выдать разрешения BLUETOOTH_SCAN / BLUETOOTH_CONNECT / ACCESS_FINE_LOCATION
5. Нажать **«Подключиться к ESP32»** — найдёт устройство с именем `ESP32S3-GPS` (или содержащее `ESP32`)

## UUID (Nordic UART Service)

| Характеристика | UUID |
|---|---|
| Service | `6e400001-b5a3-f393-e0a9-e50e24dcca9e` |
| TX (notify) | `6e400003-b5a3-f393-e0a9-e50e24dcca9e` |
| RX (write) | `6e400002-b5a3-f393-e0a9-e50e24dcca9e` |

## Команды в ESP32 (RX)

```kotlin
bleManager.sendCommand("SET_RATE 1")
```

## GPX-файлы

Сохраняются в `Android/data/com.example.esp32gps/files/Documents/track_YYYYMMDD_HHMMSS.gpx` и доступны через Files / MTP.
