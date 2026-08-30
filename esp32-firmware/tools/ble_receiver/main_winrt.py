import asyncio
import logging
import threading
from datetime import datetime

import config
from nmea_parser import parse_rmc

try:
    from winrt.windows.devices.bluetooth.genericattributeprofile import (
        GattCommunicationStatus,
        GattSessionStatus,
    )

    WINRT_AVAILABLE = True
except ImportError:
    WINRT_AVAILABLE = False
    print(
        "winrt not available, install: pip install winrt-runtime winrt-windows-devices-bluetooth"
    )

logger = logging.getLogger(__name__)


class WinRTBleClient:
    def __init__(self, on_line):
        self.on_line = on_line
        self._buffer = bytearray()
        self._running = False
        self._last_data_time = 0
        self._device = None
        self._session = None
        self._characteristic = None
        self._event_token = None

    async def start(self):
        if not WINRT_AVAILABLE:
            raise RuntimeError("winrt not available")
        self._running = True
        while self._running:
            try:
                await self._connect_and_run()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("BLE error: %s", e)
            if self._running:
                logger.info("Reconnecting in %d seconds...", config.RECONNECT_DELAY)
                await asyncio.sleep(config.RECONNECT_DELAY)

    async def stop(self):
        self._running = False
        if self._event_token:
            try:
                self._characteristic.remove_value_changed(self._event_token)
            except Exception:
                pass
            self._event_token = None
        if self._session:
            try:
                self._session.close()
            except Exception:
                pass
            self._session = None

    async def _connect_and_run(self):
        from winrt.windows.devices.bluetooth import BluetoothDevice
        from winrt.windows.devices.bluetooth.genericattributeprofile import GattSession

        logger.info("Requesting Bluetooth device...")
        mac_int = int(config.DEVICE_MAC.replace(":", ""), 16)
        device = await BluetoothDevice.from_bluetooth_address_async(mac_int)
        if device is None:
            raise RuntimeError("Device not found")
        logger.info("Device found: %s", device.name)

        logger.info("Creating GATT session...")
        session = GattSession.from_device_id(device.bluetooth_device_id)
        session.can_provide_characteristics = True
        self._session = session

        logger.info("Waiting for session...")
        for _ in range(50):
            if session.session_status == GattSessionStatus.ACTIVE:
                break
            await asyncio.sleep(0.1)
        else:
            raise RuntimeError("GATT session not active")

        logger.info("Getting services...")
        services = await session.get_services_for_async()
        target_char = None
        for svc in services:
            logger.debug("Service: %s", svc.uuid)
            if str(svc.uuid).lower() == config.NUS_SERVICE_UUID.lower():
                logger.info("Found NUS service, getting characteristics...")
                chars = await svc.get_characteristics_for_async()
                for ch in chars:
                    logger.debug("Char: %s", ch.uuid)
                    if str(ch.uuid).lower() == config.NUS_TX_CHAR_UUID.lower():
                        target_char = ch
                        break
                break

        if target_char is None:
            raise RuntimeError("TX characteristic not found")

        self._characteristic = target_char
        logger.info("Subscribing to notifications...")

        def _on_value_changed(sender, args):
            try:
                data = bytes(args.characteristic_value)
                self._buffer.extend(data)
                while b"\r\n" in self._buffer:
                    line, self._buffer = self._buffer.split(b"\r\n", 1)
                    text = line.decode("utf-8", errors="replace").strip()
                    if text:
                        self.on_line(text)
            except Exception as e:
                logger.error("Notification error: %s", e)

        self._event_token = target_char.add_value_changed(_on_value_changed)
        status = await target_char.write_client_characteristic_configuration_descriptor_async(
            1  # GattClientNotificationValue.Notify
        )
        if status != GattCommunicationStatus.SUCCESS:
            raise RuntimeError(f"Failed to enable notifications: {status}")

        self._last_data_time = asyncio.get_event_loop().time()
        logger.info("Listening for NMEA data...")
        while self._running and session.session_status == GattSessionStatus.ACTIVE:
            await asyncio.sleep(1)
            now = asyncio.get_event_loop().time()
            if now - self._last_data_time > config.DATA_TIMEOUT:
                logger.warning("No data received for %d seconds", config.DATA_TIMEOUT)
                self._last_data_time = now


class TrackLogger:
    def __init__(self, output_dir: str):
        self.output_dir = output_dir
        import os

        os.makedirs(output_dir, exist_ok=True)
        timestamp = datetime.now().astimezone().strftime("%Y%m%d_%H%M%S")
        self.filename = os.path.join(output_dir, f"track_{timestamp}.csv")
        self._lock = threading.Lock()
        with open(self.filename, "w", newline="", encoding="utf-8") as f:
            writer = __import__("csv").writer(f)
            writer.writerow(
                ["local_time", "utc_time", "lat", "lon", "speed_kmh", "valid"]
            )

    def log(self, utc_time, lat, lon, speed_kmh, valid):
        local_time = datetime.now().astimezone().strftime("%H:%M:%S")
        with self._lock, open(self.filename, "a", newline="", encoding="utf-8") as f:
            writer = __import__("csv").writer(f)
            writer.writerow(
                [
                    local_time,
                    utc_time,
                    f"{lat:.6f}",
                    f"{lon:.6f}",
                    f"{speed_kmh:.1f}",
                    int(valid),
                ]
            )


logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


def on_nmea_line(line: str):
    fix = parse_rmc(line)
    if fix:
        print(
            f"[{fix['utc_time'][:2]}:{fix['utc_time'][2:4]}:{fix['utc_time'][4:6]}] "
            f"FIX lat={fix['lat']:.6f} lon={fix['lon']:.6f} "
            f"spd={fix['speed_kmh']:.1f} km/h {fix['valid'] and 'A' or 'V'}"
        )
        track_logger.log(
            fix["utc_time"],
            fix["lat"],
            fix["lon"],
            fix["speed_kmh"],
            fix["valid"],
        )
    else:
        logger.debug("RAW: %s", line)


async def main():
    global track_logger
    track_logger = TrackLogger(config.OUTPUT_DIR)
    client = WinRTBleClient(on_line=on_nmea_line)

    loop = asyncio.get_event_loop()
    stop_event = asyncio.Event()

    def _signal_handler():
        logger.info("Shutting down...")
        stop_event.set()

    for sig in (2, 15):  # SIGINT, SIGTERM
        try:
            loop.add_signal_handler(sig, _signal_handler)
        except NotImplementedError:
            import signal as signal_mod

            signal_mod.signal(sig, lambda s, f: _signal_handler())

    client_task = asyncio.create_task(client.start())
    await stop_event.wait()
    await client.stop()
    client_task.cancel()
    try:
        await client_task
    except asyncio.CancelledError:
        pass
    logger.info("Stopped.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
