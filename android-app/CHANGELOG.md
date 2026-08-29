# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - 2026-08-29

### Added
- Initial release
- GPS tracking via ESP32 BLE connection
- NMEA sentence parsing (GGA, RMC, GSA, GSV)
- Map display with OSMDroid
- Battery level monitoring via BLE
- Bluetooth bonding verification for security
- ProGuard rules for release builds

### Security
- Added bonding status verification before BLE connection
- Added error callbacks for connection failures

### Infrastructure
- GitHub Actions CI/CD pipeline (ktlint, detekt, assembleDebug)
- Gradle 8.7 with Kotlin 1.9.24
- Android SDK 35 (compileSdk), minSdk 26
- Nordic BLE Library 2.7.5
- Jetpack Compose with Material3
