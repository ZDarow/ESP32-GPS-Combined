import asyncio
import logging
from collections.abc import Callable

from bleak import BleakClient, BleakScanner
from bleak.exc import BleakError

import config

logger = logging.getLogger(__name__)


class BleNusClient:
    def __init__(self, on_line: Callable[[str], None]):
        self.on_line = on_line
        self._buffer = bytearray()
        self._client: BleakClient | None = None
        self._running = False
        self._last_data_time = 0

    async def start(self):
        self._running = True
        while self._running:
            try:
                await self._connect_and_run()
            except asyncio.CancelledError:
                break
            except (BleakError, OSError) as e:
                logger.error("BLE error: %s", e)
            if self._running:
                logger.info("Reconnecting in %d seconds...", config.RECONNECT_DELAY)
                await asyncio.sleep(config.RECONNECT_DELAY)

    async def stop(self):
        self._running = False
        if self._client and self._client.is_connected:
            await self._client.disconnect()

    async def _connect_and_run(self):
        logger.info("Scanning for %s (%s)...", config.DEVICE_NAME, config.DEVICE_MAC)
        device = await BleakScanner.find_device_by_address(config.DEVICE_MAC)
        if device is None:
            logger.warning("Device not found by MAC, trying by name...")
            device = await BleakScanner.find_device_by_name(config.DEVICE_NAME)
        if device is None:
            raise BleakError("Device not found")

        logger.info("Connecting to %s...", device.name or device.address)
        async with BleakClient(device.address, timeout=20.0) as client:
            self._client = client
            logger.info("Connected, subscribing to notifications...")
            for attempt in range(3):
                try:
                    await client.start_notify(config.NUS_TX_CHAR_UUID, self._notification_handler)
                    break
                except BleakError as e:
                    logger.warning("Subscribe attempt %d failed: %s", attempt + 1, e)
                    if attempt < 2:
                        await asyncio.sleep(2)
                    else:
                        raise
            self._last_data_time = asyncio.get_event_loop().time()
            logger.info("Listening for NMEA data...")
            while self._running and client.is_connected:
                await asyncio.sleep(1)
                now = asyncio.get_event_loop().time()
                if now - self._last_data_time > config.DATA_TIMEOUT:
                    logger.warning("No data received for %d seconds", config.DATA_TIMEOUT)
                    self._last_data_time = now

    def _notification_handler(self, sender, data: bytearray):
        logger.debug("RAW notification: %s", data.hex())
        self._last_data_time = asyncio.get_event_loop().time()
        self._buffer.extend(data)
        while b"\r\n" in self._buffer:
            line, self._buffer = self._buffer.split(b"\r\n", 1)
            try:
                text = line.decode("utf-8", errors="replace").strip()
                if text:
                    self.on_line(text)
            except UnicodeDecodeError as e:
                logger.error("Decode error: %s", e)
