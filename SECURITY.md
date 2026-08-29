# Security Policy

## Supported Versions

| Version | Status |
| ------- | ------ |
| 1.0.x   | ✅ Supported |

## Reporting a Vulnerability

If you discover a security vulnerability, please report it by:

1. **Do NOT** create a public GitHub issue
2. Email the maintainer directly or
3. Use GitHub's [Private vulnerability reporting](https://github.com/ZDarow/ESP32-GPS-Combined/security/advisories/new)

Please include as much detail as possible:
- Description of the vulnerability
- Steps to reproduce
- Potential impact
- Suggested fix (if any)

## Security Best Practices

### ESP32 Firmware
- BLE uses LE Secure Connections (LESC)
- No hardcoded credentials in production code
- All sensitive data stored in encrypted NVS

### Android App
- Requires Bluetooth permissions with user consent
- No data transmitted without encryption
- Local storage only (no cloud backend)
