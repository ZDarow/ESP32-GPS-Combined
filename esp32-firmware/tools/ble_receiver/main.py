import asyncio
import logging
import signal

import config
from ble_client import BleNusClient
from nmea_parser import parse_rmc
from track_logger import TrackLogger

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
    client = BleNusClient(on_line=on_nmea_line)

    loop = asyncio.get_event_loop()
    stop_event = asyncio.Event()

    def _signal_handler():
        logger.info("Shutting down...")
        stop_event.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _signal_handler)
        except NotImplementedError:
            signal.signal(sig, lambda s, f: _signal_handler())

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
