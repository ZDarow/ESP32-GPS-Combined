package com.example.esp32gps

import java.time.LocalDate
import java.time.LocalDateTime
import java.time.LocalTime
import java.time.ZoneOffset
import java.time.ZonedDateTime
import java.time.format.DateTimeFormatter

/**
 * Stateless NMEA 0183 parser for GPS sentences.
 * Supports RMC (Recommended Minimum) and GGA (Global Positioning System Fix Data).
 *
 * Each call to [parse] is independent and thread-safe. The caller is responsible
 * for maintaining the latest [GpsFix] state and passing it as [previousFix] to
 * merge data from multiple sentence types.
 */
object NmeaParser {
    // Thread-safe formatters (Java 8+)
    private val utcTimeFormatter: DateTimeFormatter =
        DateTimeFormatter.ofPattern("HHmmss.SS").withZone(ZoneOffset.UTC)

    private val isoDateTimeFormatter: DateTimeFormatter =
        DateTimeFormatter.ofPattern("yyyy-MM-dd'T'HH:mm:ss'Z'").withZone(ZoneOffset.UTC)

    /**
     * Parses a single NMEA sentence and merges with previous fix data.
     *
     * @param line The raw NMEA sentence line (e.g., "$GPRMC,...").
     * @param previousFix The previous fix to merge with, or null for a fresh fix.
     * @return A new [GpsFix] with merged data from this sentence and [previousFix].
     */
    fun parse(
        line: String,
        previousFix: GpsFix = GpsFix()
    ): GpsFix {
        val trimmed = line.trim()
        if (trimmed.isEmpty() || !trimmed.startsWith("$")) return previousFix

        // Validate checksum (must match C nmea_parser_feed() behaviour).
        if (!validateChecksum(trimmed)) return previousFix

        // Remove checksum (*XX)
        val noChecksum = trimmed.substringBeforeLast("*")
        val parts = noChecksum.split(",")
        if (parts.isEmpty()) return previousFix

        return when {
            parts[0].endsWith("RMC") -> parseRmc(parts, trimmed, previousFix)
            parts[0].endsWith("GGA") -> parseGga(parts, trimmed, previousFix)
            else -> previousFix
        }
    }

    /**
     * Validates the NMEA 0183 checksum (*XX at the end of the sentence).
     * Mirrors [nmea_checksum] in components/nmea_parser/src/nmea_parser.c so that
     * Android and ESP32 reject the same corrupted sentences.
     */
    private fun validateChecksum(sentence: String): Boolean {
        val star = sentence.indexOf('*')
        if (star < 0) return false
        val dataPart = sentence.substring(0, star)
        if (!dataPart.startsWith("$")) return false
        val checksumHex = sentence.substring(star + 1)
        if (checksumHex.isEmpty()) return false
        val computed = dataPart.drop(1).fold(0) { acc, c -> acc xor c.code }
        val received = try {
            Integer.parseInt(checksumHex.take(2), 16)
        } catch (_: NumberFormatException) {
            return false
        }
        return computed == received
    }

    /**
     * Parses multiple NMEA sentences in sequence, merging them into a single fix.
     * Useful when you have a batch of lines (e.g., from a buffer).
     */
    fun parseAll(lines: List<String>): GpsFix = lines.fold(GpsFix()) { fix, line -> parse(line, fix) }

    private fun parseRmc(
        parts: List<String>,
        raw: String,
        previous: GpsFix
    ): GpsFix {
        if (parts.size < 10) return previous.copy(rawNmea = raw)

        val status = parts.getOrNull(2) ?: return previous.copy(rawNmea = raw)
        val isValid = status == "A"

        val lat = nmeaToDecimal(parts.getOrNull(3), parts.getOrNull(4))
        val lon = nmeaToDecimal(parts.getOrNull(5), parts.getOrNull(6))

        val speedKmh =
            parts.getOrNull(7)?.toDoubleOrNull()?.let { it * 1.852 }
                ?: previous.speedKmh

        val course = parts.getOrNull(8)?.toDoubleOrNull() ?: previous.courseDeg
        val time = parts.getOrNull(1)
        val date = parts.getOrNull(9)?.takeIf { it.isNotBlank() }

        return previous.copy(
            latitude = lat ?: previous.latitude,
            longitude = lon ?: previous.longitude,
            speedKmh = speedKmh,
            courseDeg = course,
            timestampUtc = time ?: previous.timestampUtc,
            dateUtc = date ?: previous.dateUtc,
            valid = isValid && lat != null && lon != null,
            rawNmea = raw
        )
    }

    private fun parseGga(
        parts: List<String>,
        raw: String,
        previous: GpsFix
    ): GpsFix {
        if (parts.size < 9) return previous.copy(rawNmea = raw)

        val sats = parts.getOrNull(7)?.toIntOrNull() ?: previous.satellites
        val hdop = parts.getOrNull(8)?.toDoubleOrNull() ?: previous.hdop
        val altitude = parts.getOrNull(9)?.toDoubleOrNull()
        val quality = parts.getOrNull(6)?.toIntOrNull() ?: previous.fixQuality
        val time = parts.getOrNull(1)

        return previous.copy(
            satellites = sats,
            hdop = hdop,
            altitudeMeters = altitude ?: previous.altitudeMeters,
            fixQuality = quality,
            timestampUtc = time ?: previous.timestampUtc,
            rawNmea = raw
        )
    }

    /**
     * Converts NMEA coordinate format (DDDMM.MMMM) to decimal degrees.
     *
     * @param coord Coordinate string (e.g., "5004.7485").
     * @param hemisphere Hemisphere indicator ("N", "S", "E", "W").
     * @return Decimal degrees, or null if parsing fails.
     */
    private fun nmeaToDecimal(
        coord: String?,
        hemisphere: String?
    ): Double? {
        if (coord.isNullOrEmpty() || hemisphere.isNullOrEmpty()) return null

        val value = coord.toDoubleOrNull() ?: return null
        val degrees = (value / 100).toInt()
        val minutes = value - degrees * 100
        var decimal = degrees + minutes / 60.0

        if (hemisphere == "S" || hemisphere == "W") decimal = -decimal
        return decimal
    }

    /**
     * Formats UTC time string (HHmmss.SS) to ISO 8601 timestamp using current date.
     * Thread-safe.
     */
    fun formatTimestamp(raw: String?): String? =
        if (raw.isNullOrEmpty()) {
            null
        } else {
            try {
                val today = LocalDate.now(ZoneOffset.UTC)
                val time = LocalTime.from(utcTimeFormatter.parse(raw))
                val dateTime = LocalDateTime.of(today, time).atZone(ZoneOffset.UTC)
                isoDateTimeFormatter.format(dateTime)
            } catch (_: Exception) {
                null
            }
        }

    /**
     * Parses UTC time string to epoch milliseconds (for GPX timestamps).
     * Thread-safe.
     */
    fun parseUtcToEpochMillis(raw: String?): Long? =
        if (raw.isNullOrEmpty()) {
            null
        } else {
            try {
                val today = LocalDate.now(ZoneOffset.UTC)
                val time = LocalTime.from(utcTimeFormatter.parse(raw))
                val dateTime = LocalDateTime.of(today, time).atZone(ZoneOffset.UTC)
                dateTime.toInstant().toEpochMilli()
            } catch (_: Exception) {
                null
            }
        }

    /**
     * Formats current UTC time to ISO 8601 string for GPX.
     * Thread-safe.
     */
    fun nowIso8601(): String = ZonedDateTime.now(ZoneOffset.UTC).format(isoDateTimeFormatter)
}
