# Contributing to ESP32 GPS Tracker

Thank you for your interest in contributing!

## Development Setup

### Prerequisites
- ESP-IDF v6.0.2 or later
- Android Studio Hedgehog (2024.1.1) or later
- Git

### Setting Up Development Environment

#### ESP32 Firmware
```bash
# Clone the repository
git clone https://github.com/ZDarow/ESP32-GPS-Combined.git
cd ESP32-GPS-Combined/esp32-firmware

# Install ESP-IDF and source it
source ~/esp-idf/esp-idf/export.sh

# Configure and build
idf.py menuconfig
idf.py build
```

#### Android App
```bash
cd ../android-app
# Open in Android Studio or build via command line
./gradlew assembleDebug
```

## Code Style

### ESP32 (C)
- Follow ESP-IDF style guide
- Use `ESP_LOGI`, `ESP_LOGW`, `ESP_LOGE` for logging
- Maximum line length: 120 characters

### Android (Kotlin)
- Follow Kotlin style guide
- Use ktlint for formatting (pre-commit hook available)
- Max line length: 120 characters

## Pull Request Process

1. **Fork** the repository
2. **Create a feature branch**: `git checkout -b feature/your-feature-name`
3. **Make your changes** with proper commit messages
4. **Add tests** if applicable
5. **Ensure CI passes** (builds successfully)
6. **Update documentation** if needed
7. **Submit a pull request** with clear description

## Commit Message Format

```
<type>(<scope>): <subject>

<body>
```

Types: `feat`, `fix`, `docs`, `style`, `refactor`, `test`, `chore`

Example:
```
feat(ble): add connection parameters request on connect

- Request 30-50ms interval with latency=3
- Prevents Android GATT timeout issues
```

## Issues

Before creating an issue:
- Check existing issues
- Provide minimal reproduction steps
- Include version information

## License

By contributing, you agree that your contributions will be licensed under the MIT License.
