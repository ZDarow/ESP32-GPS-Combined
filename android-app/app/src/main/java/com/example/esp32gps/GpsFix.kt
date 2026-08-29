package com.example.esp32gps

data class GpsFix(
    val latitude: Double? = null,
    val longitude: Double? = null,
    val altitudeMeters: Double? = null,
    val satellites: Int = 0,
    val speedKmh: Double = 0.0,
    val courseDeg: Double = 0.0,
    val fixQuality: Int = 0,
    val hdop: Double = 0.0,
    val timestampUtc: String? = null,
    val valid: Boolean = false,
    val rawNmea: String = "",
    val batteryLevel: Int? = null
) {
    val hasCoordinates: Boolean
        get() = valid && latitude != null && longitude != null
}
