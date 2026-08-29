package com.example.esp32gps

import android.app.Application
import android.bluetooth.BluetoothDevice
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import org.osmdroid.util.GeoPoint

class GpsTrackerViewModel(
    application: Application
) : AndroidViewModel(application) {
    private val appContext = application.applicationContext

    private val _connected = MutableStateFlow(false)
    val connected: StateFlow<Boolean> = _connected.asStateFlow()

    private val _scanning = MutableStateFlow(false)
    val scanning: StateFlow<Boolean> = _scanning.asStateFlow()

    private val _currentFix = MutableStateFlow(GpsFix())
    val currentFix: StateFlow<GpsFix> = _currentFix.asStateFlow()

    private val _batteryLevel = MutableStateFlow<Int?>(null)
    val batteryLevel: StateFlow<Int?> = _batteryLevel.asStateFlow()

    private val _nmeaLog = MutableStateFlow<List<String>>(emptyList())
    val nmeaLog: StateFlow<List<String>> = _nmeaLog.asStateFlow()

    private val _trackPoints = MutableStateFlow<List<GeoPoint>>(emptyList())
    val trackPoints: StateFlow<List<GeoPoint>> = _trackPoints.asStateFlow()

    private val _isRecording = MutableStateFlow(false)
    val isRecording: StateFlow<Boolean> = _isRecording.asStateFlow()

    private val _lastTrackFile = MutableStateFlow<String?>(null)
    val lastTrackFile: StateFlow<String?> = _lastTrackFile.asStateFlow()

    private val _trackPointsCount = MutableStateFlow(0)
    val trackPointsCount: StateFlow<Int> = _trackPointsCount.asStateFlow()

    private val _error = MutableStateFlow<String?>(null)
    val error: StateFlow<String?> = _error.asStateFlow()

    private val bleManager = GpsBleManager(appContext)
    private val gpxLogger = GpxLogger(appContext)

    init {
        setupBleCallbacks()
    }

    @Suppress("MissingPermission")
    private fun setupBleCallbacks() {
        bleManager.onConnectionStateChanged = { isConn ->
            viewModelScope.launch(Dispatchers.Main) {
                _connected.value = isConn
                if (!isConn) {
                    _trackPoints.value = emptyList()
                    _trackPointsCount.value = 0
                }
            }
        }

        bleManager.onNmeaReceived = { nmea ->
            viewModelScope.launch(Dispatchers.Main) {
                val fix = NmeaParser.parse(nmea, _currentFix.value)
                _currentFix.value = fix
                _nmeaLog.value = listOf(nmea) + _nmeaLog.value
                if (_nmeaLog.value.size > 200) {
                    _nmeaLog.value = _nmeaLog.value.take(200)
                }
                if (fix.hasCoordinates) {
                    val p = GeoPoint(fix.latitude!!, fix.longitude!!)
                    if (_isRecording.value) {
                        gpxLogger.append(fix)
                        _trackPointsCount.value = gpxLogger.pointCount
                    }
                    _trackPoints.value = listOf(p) + _trackPoints.value
                    if (_trackPoints.value.size > 5000) {
                        _trackPoints.value = _trackPoints.value.take(5000)
                    }
                }
            }
        }

        bleManager.onError = { msg ->
            viewModelScope.launch(Dispatchers.Main) {
                _error.value = msg
            }
        }

        bleManager.onBatteryLevel = { level ->
            viewModelScope.launch(Dispatchers.Main) {
                _batteryLevel.value = level
            }
        }
    }

    @Suppress("MissingPermission")
    fun connect(device: BluetoothDevice) {
        _scanning.value = false
        _error.value = null
        _connected.value = false
        bleManager.connect(device).enqueue()
    }

    fun disconnect() {
        _connected.value = false
        viewModelScope.launch(Dispatchers.Main) {
            runCatching { bleManager.disconnect().enqueue() }
        }
    }

    fun startRecording() {
        _isRecording.value = true
        val file = gpxLogger.start()
        _lastTrackFile.value = file?.absolutePath
    }

    fun stopRecording() {
        _isRecording.value = false
        val file = gpxLogger.stop()
        _lastTrackFile.value = file?.absolutePath
    }

    fun toggleRecording() {
        if (_isRecording.value) {
            stopRecording()
        } else {
            startRecording()
        }
    }

    fun clearLog() {
        _nmeaLog.value = emptyList()
    }

    fun consumeError(): String? {
        val e = _error.value
        _error.value = null
        return e
    }

    override fun onCleared() {
        super.onCleared()
        runCatching { bleManager.disconnect().enqueue() }
    }
}
