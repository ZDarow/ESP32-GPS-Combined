import serial
import time

ser = serial.Serial('/dev/ttyACM0', baudrate=9600, timeout=1)
print('Мониторинг /dev/ttyACM0 после cold start...')

while True:
    try:
        data = ser.readline()
        if data:
            line = data.decode('ascii', errors='replace').strip()
            if line:
                print(f'[{time.strftime("%H:%M:%S")}] {line}')
    except KeyboardInterrupt:
        break
    except Exception as e:
        print(f'Ошибка: {e}')
        time.sleep(1)

ser.close()
print('Мониторинг остановлен')
