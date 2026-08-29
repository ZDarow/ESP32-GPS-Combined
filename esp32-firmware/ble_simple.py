import asyncio
from bleak import BleakScanner, BleakClient

TARGET_NAME = "ESP32S3-GPS"
NUS_TX_CHAR_UUID = "6E400003-B5A3-F393-E0A9-E50E24DCCA9E"

received = []

def on_notify(characteristic, data):
    text = data.decode('utf-8', errors='replace')
    received.append(text)
    print(f"RX: {text.strip()}")

async def main():
    print(f"Scanning for {TARGET_NAME}...")
    device = None
    for _ in range(5):
        devs = await BleakScanner.discover(timeout=3.0)
        for d in devs:
            if d.name and TARGET_NAME in d.name:
                device = d
                print(f"Found: {d.name} [{d.address}]")
                break
        if device:
            break
    
    if not device:
        print("Not found")
        return
    
    print(f"Connecting...")
    client = BleakClient(device.address, timeout=15.0, pair_before_connect=True)
    
    try:
        await client.connect()
        print("Connected!")
        
        # Try to subscribe immediately
        await client.start_notify(NUS_TX_CHAR_UUID, on_notify)
        print("Subscribed! Listening for 30 seconds...")
        
        for i in range(30):
            await asyncio.sleep(1)
            if i % 5 == 0:
                print(f"  ... {i}s elapsed, {len(received)} messages")
        
        await client.stop_notify(NUS_TX_CHAR_UUID)
        print(f"\nTotal: {len(received)} messages")
        for i, m in enumerate(received[:10]):
            print(f"  {i+1}: {m.strip()}")
    except Exception as e:
        print(f"Error: {e}")
    finally:
        if client.is_connected:
            await client.disconnect()
        print("Disconnected")

asyncio.run(main())
