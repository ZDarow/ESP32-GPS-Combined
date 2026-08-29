# Security Policy

## Supported Versions

We release security updates for the following versions:

| Version | Supported          |
| ------- | ------------------ |
| 1.0.x   | ✅ Yes             |
| < 1.0   | ❌ No              |

## Reporting a Vulnerability

We take security vulnerabilities seriously. If you discover a security issue, please report it responsibly.

### How to Report

**Preferred:** Email us at **security@esp32gpstracker.example.com** (replace with actual contact)

**Alternative:** Open a private GitHub Security Advisory:
1. Go to the [Security tab](https://github.com/ZDarow/ESP32GPSTracker/security)
2. Click "Report a vulnerability"
3. Fill in the details

### What to Include

Please provide as much detail as possible:
- Description of the vulnerability
- Steps to reproduce
- Potential impact
- Suggested fix (if any)
- Your contact information for follow-up

### Response Timeline

- **Acknowledgment:** Within 48 hours
- **Initial assessment:** Within 7 days
- **Fix timeline:** Depends on severity
  - Critical: Within 7 days
  - High: Within 30 days
  - Medium: Within 90 days
  - Low: Next minor release

## Security Architecture

### BLE Security

- **Pairing:** LE Secure Connections (ECDH P-256) enforced
- **Bonding:** Mandatory verification before data exchange (`GpsBleManager.onDeviceReady()`)
- **Encryption:** AES-CCM on link layer (Bluetooth 4.2+)
- **Characteristics:** Security Level `ENCRYPTED` required for NUS TX/RX
- **Device Authentication:** Device name filtering + bonding verification (planned: challenge-response)

### Data Protection

- **NMEA Data:** Transmitted over encrypted BLE link
- **GPX Files:** Stored in app-private external files directory (`Documents/`)
- **No Cloud Sync:** All data stays on device unless user exports
- **No Analytics/Tracking:** Zero telemetry by default

### Permissions

| Permission | Purpose | Protection Level |
|------------|---------|------------------|
| `BLUETOOTH_SCAN` | Discover BLE devices | Normal (API 31+) |
| `BLUETOOTH_CONNECT` | Connect to bonded devices | Normal (API 31+) |
| `ACCESS_FINE_LOCATION` | Required for BLE scan on Android | Dangerous (runtime) |
| `INTERNET` | Map tile downloads (OSMDroid) | Normal |
| `WRITE_EXTERNAL_STORAGE` | GPX export (API 28-) | Dangerous (runtime) |

## Known Limitations

1. **Application-layer encryption:** Currently relies on link-layer encryption only. For high-security deployments, implement AES-GCM on NUS RX/TX characteristics.
2. **Device impersonation:** Any device advertising as "ESP32*" can trigger connection. Mitigation: bonding verification + future challenge-response.
3. **No certificate pinning:** Not applicable (BLE, not TLS).

## Security Best Practices for Users

- Keep Android OS updated (monthly security patches)
- Only pair with trusted ESP32 devices in controlled environment
- Use "Forget device" in Bluetooth settings if device is lost/stolen
- Review GPX exports before sharing (may contain location history)

## Third-Party Dependencies

We monitor vulnerabilities in:
- Nordic Android-BLE Library (`no.nordicsemi.android:ble:2.7.5`)
- OSMDroid (`org.osmdroid:osmdroid-android:6.1.18`)
- Jetpack Compose / AndroidX libraries

Dependencies are updated via [Renovate](https://github.com/ZDarow/ESP32GPSTracker/blob/main/renovate.json) with automated PRs.

## Disclosure Policy

We follow [Coordinated Vulnerability Disclosure](https://en.wikipedia.org/wiki/Responsible_disclosure):
1. Private report → acknowledgment → fix → coordinated release
2. Public disclosure after fix is available (or 90 days, whichever comes first)
3. Credit given to reporter (unless anonymous requested)

---

**Last Updated:** 2026-08-29  
**Policy Version:** 1.0