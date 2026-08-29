import asyncio
import sys
from winrt.windows.devices.bluetooth import BluetoothDevice
from winrt.windows.devices.enumeration import DeviceInformation, DevicePairingResult, DevicePairingResultStatus
from winrt.windows.devices.bluetooth.genericattributeprofile import GattDeviceService, GattCharacteristic
from winrt.windows.storage.streams import DataReader

TARGET_NAME = "ESP32S3-GPS"
NUS_SERVICE_UUID = "6E400001-B5A3-F393-E0A9-E50E24DCCA9E"
NUS_TX_CHAR_UUID = "6E400003-B5A3-F393-E0A9-E50E24DCCA9E"

received_data = []

def notification_handler(sender, args):
    try:
        reader = DataReader.from_buffer(args.characteristic_value)
        text = reader.read_string(reader.unconsumed_buffer_length)
        received_data.append(text)
        print(f"NOTIFY [{len(received_data)}]: {text}")
    except Exception as e:
        print(f"NOTIFY error: {e}")

async def find_and_pair_device():
    print(f"Looking for {TARGET_NAME}...")
    
    # Find the device using AQS filter
    selector = f"System.Devices.Aep.ProtocolId:={{bb7bb05e-5972-42b5-94fc-76eaa7084d49}}"
    devices = await DeviceInformation.find_all_async(selector)
    
    target_device = None
    for device in devices:
        if device.name and TARGET_NAME in device.name:
            target_device = device
            print(f"Found: {device.name} [{device.id}]")
            break
    
    if not target_device:
        print("ERROR: Device not found")
        return None
    
    # Pair the device
    print("Pairing...")
    pairing_result = await target_device.pairing.pair_async()
    
    if pairing_result.status != DevicePairingResultStatus.paired:
        print(f"Pairing failed: {pairing_result.status}")
        return None
    
    print("Paired successfully!")
    
    # Get the Bluetooth device
    bt_device = await BluetoothDevice.from_id_async(target_device.id)
    if not bt_device:
        print("ERROR: Could not get BluetoothDevice")
        return None
    
    return bt_device

async def test_ble_connection():
    bt_device = await find_and_pair_device()
    if not bt_device:
        return False
    
    print(f"Device: {bt_device.name}, Address: {bt_device.bluetooth_address}")
    
    # Get GATT services
    print("Getting GATT services...")
    services_result = await bt_device.get_gatt_services_async()
    if services_result.status != 0:  # Success
        print(f"ERROR: Failed to get services, status={services_result.status}")
        return False
    
    services = services_result.services
    print(f"Found {len(services)} services")
    
    nus_service = None
    for service in services:
        uuid_str = str(service.uuid).upper()
        if NUS_SERVICE_UUID in uuid_str or "6E400001" in uuid_str:
            nus_service = service
            print(f"Found NUS service: {service.uuid}")
            break
    
    if not nus_service:
        print("ERROR: NUS service not found")
        print("Available services:")
        for service in services:
            print(f"  {service.uuid}")
        return False
    
    # Get characteristics
    print("Getting characteristics...")
    chars_result = await nus_service.get_characteristics_async()
    if chars_result.status != 0:
        print(f"ERROR: Failed to get characteristics, status={chars_result.status}")
        return False
    
    characteristics = chars_result.characteristics
    print(f"Found {len(characteristics)} characteristics")
    
    tx_char = None
    rx_char = None
    for char in characteristics:
        uuid_str = str(char.uuid).upper()
        if NUS_TX_CHAR_UUID in uuid_str or "6E400003" in uuid_str:
            tx_char = char
            print(f"Found TX char: {char.uuid}")
        elif NUS_RX_CHAR_UUID in uuid_str or "6E400002" in uuid_str:
            rx_char = char
            print(f"Found RX char: {char.uuid}")
    
    if not tx_char:
        print("ERROR: TX char not found")
        return False
    
    # Subscribe to notifications
    print("Subscribing to notifications...")
    subscribe_result = await tx_char.write_client_characteristic_configuration_descriptor_async(1)  # Notify
    if subscribe_result.status != 0:
        print(f"ERROR: Failed to subscribe, status={subscribe_result.status}")
        return False
    
    print("Subscribed! Listening for 15 seconds...")
    await asyncio.sleep(15)
    
    print(f"\nTotal notifications: {len(received_data)}")
    if received_data:
        print("Sample data:")
        for i, d in enumerate(received_data[:5]):
            print(f"  {i+1}: {d[:80]}")
    else:
        print("No data received")
    
    return True

if __name__ == "__main__":
    try:
        result = asyncio.run(test_ble_connection())
        sys.exit(0 if result else 1)
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
