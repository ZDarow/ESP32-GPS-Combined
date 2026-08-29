import asyncio
from bleak import BleakScanner

async def scan():
    print('Scanning for ESP32S3-GPS...')
    devices = await BleakScanner.discover(timeout=10.0)
    for d in devices:
        if d.name and 'ESP32' in d.name:
            rssi = getattr(d, 'rssi', 'N/A')
            print(f'Found: {d.name} [{d.address}] RSSI={rssi}')

asyncio.run(scan())
