package com.example.esp32gps

import android.bluetooth.BluetoothDevice
import android.bluetooth.BluetoothGatt
import android.bluetooth.BluetoothGattCharacteristic
import android.content.Context
import android.util.Log
import no.nordicsemi.android.ble.BleManager
import no.nordicsemi.android.ble.callback.DataReceivedCallback
import no.nordicsemi.android.ble.common.callback.battery.BatteryLevelDataCallback
import no.nordicsemi.android.ble.data.Data
import java.nio.charset.StandardCharsets
import java.util.UUID

private const val PHY_LE_2M = 0x02
private const val PHY_OPTION_NONE = 0x00

class GpsBleManager(
    context: Context
) : BleManager(context) {
    companion object {
        private const val TAG = "GpsBleManager"
        val NUS_SERVICE: UUID = UUID.fromString("6e400001-b5a3-f393-e0a9-e50e24dcca9e")
        val NUS_TX_CHAR: UUID = UUID.fromString("6e400003-b5a3-f393-e0a9-e50e24dcca9e")
        val NUS_RX_CHAR: UUID = UUID.fromString("6e400002-b5a3-f393-e0a9-e50e24dcca9e")
        private const val BATTERY_SERVICE_UUID = "0000180f-0000-1000-8000-00805f9b34fb"
        private const val BATTERY_LEVEL_CHAR_UUID = "00002a19-0000-1000-8000-00805f9b34fb"
    }

    var onNmeaReceived: ((String) -> Unit)? = null
    var onConnectionStateChanged: ((Boolean) -> Unit)? = null
    var onError: ((String) -> Unit)? = null
    var onBatteryLevel: ((Int) -> Unit)? = null

    private var txCharacteristic: BluetoothGattCharacteristic? = null
    private var rxCharacteristic: BluetoothGattCharacteristic? = null
    private var batteryCharacteristic: BluetoothGattCharacteristic? = null

    private val lineBuffer = StringBuilder()
    private val lock = Any()

    override fun initialize() {
        requestMtu(256).enqueue()
        try {
            setPreferredPhy(PHY_LE_2M, PHY_LE_2M, PHY_OPTION_NONE)
        } catch (t: Throwable) {
            Log.w(TAG, "setPreferredPhy failed: ${t.message}")
        }
    }

    override fun isRequiredServiceSupported(gatt: BluetoothGatt): Boolean {
        val nus = gatt.getService(NUS_SERVICE)
        if (nus == null) {
            onError?.invoke("NUS-сервис не найден")
            return false
        }
        txCharacteristic = nus.getCharacteristic(NUS_TX_CHAR)
        rxCharacteristic = nus.getCharacteristic(NUS_RX_CHAR)
        if (txCharacteristic == null || rxCharacteristic == null) {
            onError?.invoke("Характеристики NUS TX/RX не найдены")
            return false
        }
        val batteryService = gatt.getService(UUID.fromString(BATTERY_SERVICE_UUID))
        batteryCharacteristic = batteryService?.getCharacteristic(UUID.fromString(BATTERY_LEVEL_CHAR_UUID))
        return true
    }

    override fun onServicesInvalidated() {
        synchronized(lock) {
            txCharacteristic = null
            rxCharacteristic = null
            batteryCharacteristic = null
            lineBuffer.clear()
        }
        onConnectionStateChanged?.invoke(false)
    }

    @Suppress("ktlint:standard:chain-method-continuation")
    override fun onDeviceReady() {
        super.onDeviceReady()

        // Verify bonding status for security
        val bondState = bluetoothDevice?.bondState
        if (bondState != BluetoothDevice.BOND_BONDED) {
            Log.w(TAG, "Device not bonded. Bond state: $bondState")
            onError?.invoke("Устройство не сопряжено. Выполните сопряжение в настройках Bluetooth.")
            return
        }

        onConnectionStateChanged?.invoke(true)

        val tx = txCharacteristic ?: return
        setNotificationCallback(tx)
            .with(
                object : DataReceivedCallback {
                    override fun onDataReceived(
                        device: BluetoothDevice,
                        data: Data
                    ) {
                        val chunk = data.value ?: return
                        val text = String(chunk, StandardCharsets.UTF_8)
                        synchronized(lock) {
                            lineBuffer.append(text)
                            val buf = lineBuffer.toString()
                            val lines = buf.split('\n', '\r')
                            if (lines.size > 1) {
                                for (i in 0 until lines.size - 1) {
                                    val line = lines[i].trim()
                                    if (line.isNotEmpty()) onNmeaReceived?.invoke(line)
                                }
                                lineBuffer.setLength(0)
                                lineBuffer.append(lines.last())
                            }
                        }
                    }
                }
            )
        enableNotifications(tx).enqueue()

        batteryCharacteristic?.let { batt ->
            setNotificationCallback(batt)
                .with(object : BatteryLevelDataCallback() {
                    override fun onBatteryLevelChanged(device: BluetoothDevice, level: Int) {
                        onBatteryLevel?.invoke(level)
                    }
                })
            enableNotifications(batt).enqueue()
        }
    }

    fun sendCommand(command: String) {
        val rx = rxCharacteristic ?: return
        @Suppress("ktlint:standard:chain-method-continuation")
        writeCharacteristic(
            rx,
            command.toByteArray(StandardCharsets.UTF_8),
            BluetoothGattCharacteristic.WRITE_TYPE_DEFAULT
        ).enqueue()
    }
}
