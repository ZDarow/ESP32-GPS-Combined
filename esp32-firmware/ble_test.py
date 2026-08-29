import asyncio
import sys
from bleak import BleakScanner, BleakClient
from bleak.backends.characteristic import BleakGATTCharacteristic

TARGET_NAME = "ESP32S3-GPS"
NUS_SERVICE_UUID = "6E400001-B5A3-F393-E0A9-E50E24DCCA9E"
NUS_TX_CHAR_UUID = "6E400003-B5A3-F393-E0A9-E50E24DCCA9E"
NUS_RX_CHAR_UUID = "6E400002-B5A3-F393-E0A9-E50E24DCCA9E"

received_data = []

def notification_handler(characteristic: BleakGATTCharacteristic, data: bytearray):
    try:
        text = data.decode('utf-8', errors='replace')
        received_data.append(text)
        print(f"NOTIFY [{len(received_data)}]: {text}")
    except Exception as e:
        print(f"NOTIFY (raw): {data.hex()}")

async def scan_and_connect():
    print(f"Scanning for {TARGET_NAME}...")
    device = None
    for attempt in range(3):
        devices = await BleakScanner.discover(timeout=5.0)
        for d in devices:
            if d.name and TARGET_NAME in d.name:
                device = d
                rssi = getattr(d, 'rssi', 'N/A')
                print(f"Found: {d.name} [{d.address}] RSSI={rssi}")
                break
        if device:
            break
        print(f"Attempt {attempt+1}: not found, retrying...")
    
    if not device:
        print("ERROR: Device not found")
        return False
    
    print(f"Connecting to {device.address}...")
    client = BleakClient(device.address, timeout=10.0)
    try:
        await client.connect()
        print("Connected!")
        
        if not client.is_connected:
            print("ERROR: Connection failed")
            return False
        
        # Get services - try both methods for compatibility
        services = None
        if hasattr(client, 'get_services'):
            services = await client.get_services()
        elif hasattr(client, 'services'):
            services = client.services
        
        if not services:
            print("ERROR: No services available")
            return False
        
        nus_service = None
        for svc in services:
            svc_uuid = str(svc.uuid).lower()
            if NUS_SERVICE_UUID.lower() in svc_uuid or "6e400001" in svc_uuid:
                nus_service = svc
                break
        
        if not nus_service:
            print("ERROR: NUS service not found")
            print("Available services:")
            for svc in services:
                print(f"  {svc.uuid}")
            return False
        
        print(f"NUS service found: {nus_service.uuid}")
        
        tx_char = None
        rx_char = None
        for char in nus_service.characteristics:
            char_uuid = str(char.uuid).lower()
            if NUS_TX_CHAR_UUID.lower() in char_uuid or "6e400003" in char_uuid:
                tx_char = char
            elif NUS_RX_CHAR_UUID.lower() in char_uuid or "6e400002" in char_uuid:
                rx_char = char
        
        if tx_char:
            print(f"TX char found: {tx_char.uuid}")
            await client.start_notify(tx_char, notification_handler)
        else:
            print("ERROR: TX char not found")
            return False
        
        if rx_char:
            print(f"RX char found: {rx_char.uuid}")
        else:
            print("WARNING: RX char not found")
        
        print("\nListening for NMEA data for 15 seconds...")
        print("(If no real GPS fix, you should see fake NMEA from simulator)")
        await asyncio.sleep(15)
        
        if tx_char:
            await client.stop_notify(tx_char)
        
        print(f"\nTotal notifications received: {len(received_data)}")
        if received_data:
            print("Sample data:")
            for i, d in enumerate(received_data[:5]):
                print(f"  {i+1}: {d[:80]}")
        else:
            print("No data received - check BLE connection and simulator")
        
        return True
    finally:
        if client.is_connected:
            await client.disconnect()
        print("Disconnected")

if __name__ == "__main__":
    try:
        result = asyncio.run(scan_and_connect())
        sys.exit(0 if result else 1)
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
