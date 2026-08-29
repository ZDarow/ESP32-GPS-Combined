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
    
    print(f"Connecting without pairing...")
    client = BleakClient(device.address, timeout=20.0, pair=False)
    
    try:
        await client.connect()
        print("Connected!")
        
        # Check connection state
        print(f"is_connected: {client.is_connected}")
        
        # Get services
        services = client.services
        print(f"Services available")
        
        tx_char = None
        for service in services:
            for char in service.characteristics:
                if NUS_TX_CHAR_UUID.lower() in str(char.uuid).lower():
                    tx_char = char
                    break
        
        if not tx_char:
            print("TX char not found")
            return
        
        print(f"TX char: {tx_char.uuid}")
        
        # Try start_notify
        await client.start_notify(tx_char, on_notify)
        print("Subscribed! Listening for 20 seconds...")
        
        for i in range(20):
            await asyncio.sleep(1)
            if i % 5 == 0:
                print(f"  ... {i}s elapsed, {len(received)} messages")
        
        await client.stop_notify(tx_char)
        print(f"\nTotal: {len(received)} messages")
        for i, m in enumerate(received[:10]):
            print(f"  {i+1}: {m.strip()}")
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        if client.is_connected:
            await client.disconnect()
        print("Disconnected")

asyncio.run(main())
