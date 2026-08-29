import asyncio
from bleak import BleakScanner

async def scan():
    print('Scanning for 15 seconds...')
    devices = await BleakScanner.discover(timeout=15.0)
    for d in devices:
        if d.name:
            rssi = getattr(d, 'rssi', 'N/A')
            print(f'  {d.name} [{d.address}] RSSI={rssi}')

asyncio.run(scan())
