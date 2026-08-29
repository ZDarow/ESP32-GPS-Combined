package com.example.esp32gps

import android.Manifest
import android.bluetooth.BluetoothAdapter
import android.bluetooth.BluetoothDevice
import android.bluetooth.BluetoothManager
import android.bluetooth.le.ScanCallback
import android.bluetooth.le.ScanResult
import android.content.Context
import android.content.pm.PackageManager
import android.os.Build
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import androidx.activity.ComponentActivity
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Card
import androidx.compose.material3.Divider
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalLifecycleOwner
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.unit.dp
import androidx.compose.ui.viewinterop.AndroidView
import androidx.core.content.ContextCompat
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleEventObserver
import androidx.lifecycle.viewmodel.compose.viewModel
import org.osmdroid.tileprovider.tilesource.TileSourceFactory
import org.osmdroid.util.GeoPoint
import org.osmdroid.views.MapView
import org.osmdroid.views.overlay.Marker
import org.osmdroid.views.overlay.Polyline
import java.util.Locale

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent {
            MaterialTheme {
                Surface(modifier = Modifier.fillMaxSize()) {
                    val viewModel: GpsTrackerViewModel =
                        viewModel(
                            factory = GpsTrackerViewModelFactory(application)
                        )
                    AppRoot(viewModel = viewModel)
                }
            }
        }
    }
}

@Suppress("FunctionNaming")
@Composable
fun AppRoot(viewModel: GpsTrackerViewModel) {
    val context = LocalContext.current
    val lifecycleOwner = LocalLifecycleOwner.current
    val btManager = context.getSystemService(Context.BLUETOOTH_SERVICE) as? BluetoothManager
    val adapter: BluetoothAdapter? = btManager?.adapter

    val connected by viewModel.connected.collectAsState()
    val scanning by viewModel.scanning.collectAsState()
    val currentFix by viewModel.currentFix.collectAsState()
    val batteryLevel by viewModel.batteryLevel.collectAsState()
    val nmeaLog by viewModel.nmeaLog.collectAsState()
    val trackPoints by viewModel.trackPoints.collectAsState()
    val isRecording by viewModel.isRecording.collectAsState()
    val lastTrackFile by viewModel.lastTrackFile.collectAsState()
    val trackPointsCount by viewModel.trackPointsCount.collectAsState()

    val listState = rememberLazyListState()

    LaunchedEffect(nmeaLog.size) {
        if (nmeaLog.isNotEmpty()) listState.animateScrollToItem(0)
    }

    DisposableEffect(lifecycleOwner) {
        val observer =
            LifecycleEventObserver { _, event ->
                if (event == Lifecycle.Event.ON_STOP && connected) {
                    viewModel.disconnect()
                }
            }
        lifecycleOwner.lifecycle.addObserver(observer)
        onDispose { lifecycleOwner.lifecycle.removeObserver(observer) }
    }

    val permissionLauncher =
        rememberLauncherForActivityResult(
            ActivityResultContracts.RequestMultiplePermissions()
        ) { _ ->
            if (adapter != null) {
                startScan(adapter, { dev ->
                    viewModel.connect(dev)
                }) { /* scan finished without result */ }
            }
        }

    Column(
        modifier =
            Modifier
                .fillMaxSize()
                .padding(12.dp)
    ) {
        StatusCard(
            connected = connected,
            scanning = scanning,
            fix = currentFix,
            isRecording = isRecording,
            trackPointsCount = trackPointsCount,
            trackFile = lastTrackFile,
            batteryLevel = batteryLevel
        )

        Spacer(Modifier.height(10.dp))

        MapCard(
            fix = currentFix,
            trackPoints = trackPoints,
            modifier =
                Modifier
                    .fillMaxWidth()
                    .height(280.dp)
        )

        Spacer(Modifier.height(10.dp))

        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.spacedBy(8.dp)
        ) {
            Button(
                onClick = {
                    val perms =
                        buildList {
                            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
                                add(Manifest.permission.BLUETOOTH_SCAN)
                                add(Manifest.permission.BLUETOOTH_CONNECT)
                            }
                            add(Manifest.permission.ACCESS_FINE_LOCATION)
                        }.toTypedArray()
                    val granted =
                        perms.all {
                            ContextCompat.checkSelfPermission(context, it) == PackageManager.PERMISSION_GRANTED
                        }
                    if (granted && adapter != null) {
                        startScan(adapter, { dev ->
                            viewModel.connect(dev)
                        }) { /* scan finished without result */ }
                    } else {
                        permissionLauncher.launch(perms)
                    }
                },
                enabled = !connected && !scanning,
                modifier = Modifier.weight(1f),
                colors =
                    ButtonDefaults.buttonColors(
                        containerColor = if (connected) Color(0xFF4CAF50) else MaterialTheme.colorScheme.primary
                    )
            ) {
                Text(
                    when {
                        scanning -> stringResource(R.string.status_scanning)
                        connected -> stringResource(R.string.status_connected)
                        else -> stringResource(R.string.btn_connect)
                    }
                )
            }
            OutlinedButton(
                onClick = {
                    if (connected) {
                        viewModel.disconnect()
                    }
                },
                enabled = connected,
                modifier = Modifier.weight(1f)
            ) {
                Text(stringResource(R.string.btn_disconnect))
            }
        }

        Spacer(Modifier.height(8.dp))

        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.spacedBy(8.dp)
        ) {
            val recColor = if (isRecording) Color(0xFFF44336) else MaterialTheme.colorScheme.secondary
            Button(
                onClick = { viewModel.toggleRecording() },
                modifier = Modifier.weight(1f),
                colors = ButtonDefaults.buttonColors(containerColor = recColor)
            ) {
                Text(
                    if (isRecording) {
                        stringResource(R.string.btn_stop_track)
                    } else {
                        stringResource(R.string.btn_start_track)
                    }
                )
            }
            OutlinedButton(
                onClick = { viewModel.clearLog() },
                enabled = nmeaLog.isNotEmpty(),
                modifier = Modifier.weight(1f)
            ) { Text(stringResource(R.string.btn_clear_log)) }
        }

        Spacer(Modifier.height(8.dp))
        Divider()
        Spacer(Modifier.height(6.dp))

        Text(stringResource(R.string.label_nmea_log), style = MaterialTheme.typography.titleSmall)
        Spacer(Modifier.height(4.dp))

        LazyColumn(
            state = listState,
            modifier =
                Modifier
                    .fillMaxWidth()
                    .heightIn(min = 80.dp)
        ) {
            items(nmeaLog) { line ->
                Text(
                    text = line,
                    style = MaterialTheme.typography.bodySmall.copy(fontFamily = FontFamily.Monospace),
                    modifier = Modifier.padding(vertical = 1.dp)
                )
            }
        }
    }
}

@Suppress("FunctionNaming")
@Composable
private fun StatusCard(
    connected: Boolean,
    scanning: Boolean,
    fix: GpsFix,
    isRecording: Boolean,
    trackPointsCount: Int,
    trackFile: String?,
    batteryLevel: Int?
) {
    Card(modifier = Modifier.fillMaxWidth()) {
        Column(modifier = Modifier.padding(12.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text(
                    text = "ESP32S3-GPS",
                    style = MaterialTheme.typography.titleMedium,
                    modifier = Modifier.weight(1f)
                )
                val (label, color) =
                    when {
                        scanning -> stringResource(R.string.status_scanning) to Color(0xFFFF9800)
                        connected -> stringResource(R.string.status_connected) to Color(0xFF4CAF50)
                        else -> stringResource(R.string.status_disconnected) to Color(0xFFF44336)
                    }
                Box(
                    modifier =
                        Modifier
                            .background(color.copy(alpha = 0.15f), MaterialTheme.shapes.small)
                            .padding(horizontal = 8.dp, vertical = 4.dp)
                ) { Text(label, color = color) }
            }
            Spacer(Modifier.height(6.dp))
            if (fix.hasCoordinates) {
                Text("📍 ${fmt(fix.latitude!!)}, ${fmt(fix.longitude!!)}")
                Text("🛰️ Спутников: ${fix.satellites}  HDOP: ${"%.1f".format(fix.hdop)}")
                Text("🚗 Скорость: ${"%.1f".format(fix.speedKmh)} км/ч  Курс: ${"%.0f".format(fix.courseDeg)}°")
                fix.altitudeMeters?.let { Text("⛰️ Высота: ${"%.1f".format(it)} м") }
            } else {
                Text(stringResource(R.string.label_waiting_fix))
            }
            batteryLevel?.let {
                val battColor =
                    when {
                        it >= 50 -> Color(0xFF4CAF50)
                        it >= 20 -> Color(0xFFFF9800)
                        else -> Color(0xFFF44336)
                    }
                Text("🔋 Батарея: $it%", color = battColor)
            }
            if (isRecording) {
                Spacer(Modifier.height(4.dp))
                Text("⏺ Запись трека: $trackPointsCount точек", color = Color(0xFFF44336))
                trackFile?.let { Text("💾 $it", style = MaterialTheme.typography.bodySmall) }
            }
        }
    }
}

@Suppress("FunctionNaming")
@Composable
private fun MapCard(
    fix: GpsFix,
    trackPoints: List<GeoPoint>,
    modifier: Modifier = Modifier
) {
    Card(modifier = modifier) {
        Box(Modifier.fillMaxSize()) {
            if (fix.hasCoordinates) {
                OsmMapView(
                    lat = fix.latitude!!,
                    lon = fix.longitude!!,
                    trackPoints = trackPoints
                )
            } else {
                Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                    Text(stringResource(R.string.label_no_coords))
                }
            }
        }
    }
}

/**
 * Creates a MapView that follows the Composable lifecycle.
 * Calls onResume/onPause automatically to properly manage OSMDroid resources.
 */
@Composable
private fun rememberMapViewWithLifecycle(): MapView {
    val context = LocalContext.current
    val mapView =
        remember {
            MapView(context).apply {
                id = android.view.View.generateViewId()
                setTileSource(TileSourceFactory.MAPNIK)
                setMultiTouchControls(true)
            }
        }

    val lifecycleObserver = rememberMapLifecycleObserver(mapView)
    val lifecycle = LocalLifecycleOwner.current.lifecycle
    DisposableEffect(lifecycle) {
        lifecycle.addObserver(lifecycleObserver)
        onDispose { lifecycle.removeObserver(lifecycleObserver) }
    }

    return mapView
}

@Composable
private fun rememberMapLifecycleObserver(mapView: MapView): LifecycleEventObserver =
    remember(mapView) {
        LifecycleEventObserver { _, event ->
            when (event) {
                Lifecycle.Event.ON_RESUME -> mapView.onResume()
                Lifecycle.Event.ON_PAUSE -> mapView.onPause()
                else -> {}
            }
        }
    }

@Suppress("FunctionNaming")
@Composable
private fun OsmMapView(
    lat: Double,
    lon: Double,
    trackPoints: List<GeoPoint>
) {
    val mapView = rememberMapViewWithLifecycle()
    AndroidView(
        modifier = Modifier.fillMaxSize(),
        factory = { mapView },
        update = { mv ->
            val center = GeoPoint(lat, lon)
            mv.controller.animateTo(center)
            mv.overlays.removeAll { it is Marker || it is Polyline }
            mv.overlays.add(
                Marker(mv).apply {
                    position = center
                    setAnchor(Marker.ANCHOR_CENTER, Marker.ANCHOR_BOTTOM)
                    title = "ESP32 GPS"
                }
            )
            if (trackPoints.size >= 2) {
                val poly =
                    Polyline().apply {
                        setPoints(trackPoints)
                        outlinePaint.color = android.graphics.Color.parseColor("#1565C0")
                        outlinePaint.strokeWidth = 6f
                    }
                mv.overlays.add(poly)
            }
            mv.invalidate()
        }
    )
}

private fun fmt(v: Double): String = String.format(Locale.US, "%.6f", v)

private fun startScan(
    adapter: BluetoothAdapter,
    onFound: (BluetoothDevice) -> Unit,
    onFinish: () -> Unit
) {
    val callback =
        object : ScanCallback() {
            override fun onScanResult(
                callbackType: Int,
                result: ScanResult
            ) {
                val dev = result.device
                val name = runCatching { dev.name }.getOrNull() ?: ""
                if (name == "ESP32S3-GPS" || name.contains("ESP32", ignoreCase = true)) {
                    runCatching { adapter.bluetoothLeScanner.stopScan(this) }
                    onFound(dev)
                }
            }

            override fun onScanFailed(errorCode: Int) {
                onFinish()
            }
        }

    // Auto-stop scan after 15 seconds to avoid battery drain
    val timeoutHandler = Handler(Looper.getMainLooper())
    val timeoutRunnable =
        Runnable {
            runCatching { adapter.bluetoothLeScanner.stopScan(callback) }
            onFinish()
        }
    timeoutHandler.postDelayed(timeoutRunnable, 15000)

    try {
        adapter.bluetoothLeScanner.startScan(callback)
    } catch (t: Throwable) {
        timeoutHandler.removeCallbacksAndMessages(null)
        onFinish()
    }
}
