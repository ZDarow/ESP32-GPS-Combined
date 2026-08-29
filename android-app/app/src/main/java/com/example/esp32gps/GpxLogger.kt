package com.example.esp32gps

import android.content.Context
import android.os.Environment
import android.util.Log
import java.io.BufferedWriter
import java.io.File
import java.io.FileWriter
import java.time.LocalDate
import java.time.LocalDateTime
import java.time.LocalTime
import java.time.ZoneOffset
import java.time.ZonedDateTime
import java.time.format.DateTimeFormatter
import java.util.Locale

class GpxLogger(
    private val context: Context
) {
    companion object {
        private const val TAG = "GpxLogger"
    }

    // Thread-safe formatters (Java 8+ DateTimeFormatter is immutable and thread-safe)
    private val fileNameFormatter: DateTimeFormatter =
        DateTimeFormatter.ofPattern("yyyyMMdd_HHmmss", Locale.US).withZone(ZoneOffset.UTC)

    private val isoDateTimeFormatter: DateTimeFormatter =
        DateTimeFormatter.ofPattern("yyyy-MM-dd'T'HH:mm:ss'Z'").withZone(ZoneOffset.UTC)

    private val utcTimeFormatter: DateTimeFormatter =
        DateTimeFormatter.ofPattern("HHmmss.SS").withZone(ZoneOffset.UTC)

    private var writer: BufferedWriter? = null
    private var currentFile: File? = null
    private var trackPoints: Int = 0

    val isRecording: Boolean get() = writer != null
    val filePath: String? get() = currentFile?.absolutePath
    val pointCount: Int get() = trackPoints

    fun start(): File? {
        if (writer != null) return currentFile
        return try {
            val dir =
                context.getExternalFilesDir(Environment.DIRECTORY_DOCUMENTS)
                    ?: context.filesDir
            if (!dir.exists()) dir.mkdirs()
            val file = File(dir, "track_${fileNameFormatter.format(java.time.ZonedDateTime.now(ZoneOffset.UTC))}.gpx")
            val w = BufferedWriter(FileWriter(file))
            w.write(gpxHeader())
            w.flush()
            writer = w
            currentFile = file
            trackPoints = 0
            Log.i(TAG, "GPX started: ${file.absolutePath}")
            file
        } catch (t: Throwable) {
            Log.e(TAG, "GPX start failed: ${t.message}")
            stop()
            null
        }
    }

    fun append(fix: GpsFix) {
        val w = writer ?: return
        val lat = fix.latitude ?: return
        val lon = fix.longitude ?: return
        if (!fix.valid) return
        try {
            val time = fix.timestampUtc?.let { parseUtcToIso(it) } ?: nowIso8601()
            val trkpt =
                String.format(
                    Locale.US,
                    "<trkpt lat=\"%.6f\" lon=\"%.6f\"><ele>%.2f</ele><time>%s</time><speed>%.3f</speed><sat>%d</sat></trkpt>%n",
                    lat,
                    lon,
                    fix.altitudeMeters ?: 0.0,
                    time,
                    fix.speedKmh / 3.6,
                    fix.satellites
                )
            w.write(trkpt)
            trackPoints++
            if (trackPoints % 20 == 0) w.flush()
        } catch (t: Throwable) {
            Log.e(TAG, "GPX append failed: ${t.message}")
        }
    }

    fun stop(): File? {
        val file = currentFile
        try {
            writer?.write(gpxFooter())
            writer?.flush()
            writer?.close()
        } catch (t: Throwable) {
            Log.e(TAG, "GPX close failed: ${t.message}")
        }
        writer = null
        currentFile = null
        trackPoints = 0
        return file
    }

    /**
     * Parses NMEA UTC time (HHmmss.SS) and returns ISO 8601 timestamp string.
     * Thread-safe using DateTimeFormatter.
     */
    private fun parseUtcToIso(hhmmss: String): String? =
        try {
            val today = LocalDate.now(ZoneOffset.UTC)
            val time = LocalTime.from(utcTimeFormatter.parse(hhmmss))
            val dateTime = LocalDateTime.of(today, time).atZone(ZoneOffset.UTC)
            isoDateTimeFormatter.format(dateTime)
        } catch (_: Exception) {
            null
        }

    /**
     * Returns current UTC time as ISO 8601 string.
     * Thread-safe.
     */
    private fun nowIso8601(): String = ZonedDateTime.now(ZoneOffset.UTC).format(isoDateTimeFormatter)

    private fun gpxHeader(): String =
        """<?xml version="1.0" encoding="UTF-8"?>
<gpx version="1.1" creator="ESP32GPSTracker" xmlns="http://www.topografix.com/GPX/1/1">
  <trk>
    <name>ESP32 GPS Track</name>
    <trkseg>
"""

    private fun gpxFooter(): String =
        """    </trkseg>
  </trk>
</gpx>
"""
}
