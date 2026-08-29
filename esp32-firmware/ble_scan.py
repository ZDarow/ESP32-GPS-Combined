import asyncio
from bleak import BleakScanner

async def scan():
    print('Scanning for BLE devices...')
    devices = await BleakScanner.discover(timeout=10.0)
    for d in devices:
        rssi = getattr(d, 'rssi', 'N/A')
        name = d.name or "Unknown"
        print(f'  {name} [{d.address}] RSSI={rssi}')

asyncio.run(scan())
