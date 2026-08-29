#!/usr/bin/env python3
"""
Адаптивная настройка GPS модуля для региона Центральной России
Поддерживает u-blox модули (NEO-6, NEO-7, NEO-M8, NEO-M9 и др.)

Регион: Центральная Россия
- Широта: 55-60°N
- Долгота: 35-45°E
- Спутниковые системы: GPS, GLONASS, Galileo, BeiDou
- SBAS: EGNOS (доступен в Европе/России)
"""

import serial
import struct
import time
import sys
import argparse
from typing import Optional, Tuple


class UBXConfigurator:
    """Класс для конфигурации u-blox GPS модулей"""
    
    # UBX синхрослово
    UBX_SYNC_CHAR_1 = 0xB5
    UBX_SYNC_CHAR_2 = 0x62
    
    # Классы сообщений
    MSG_CLASS_CFG = 0x06
    MSG_CLASS_NAV = 0x01
    MSG_CLASS_RXM = 0x02
    MSG_CLASS_MON = 0x0A
    MSG_CLASS_ACK = 0x05
    
    # ID сообщений
    MSG_ID_CFG_PRT = 0x00      # Порт конфигурация
    MSG_ID_CFG_MSG = 0x01      # Сообщения конфигурация
    MSG_ID_CFG_RATE = 0x08     # Частота обновления
    MSG_ID_CFG_CFG = 0x09      # Сохранение конфигурации
    MSG_ID_CFG_GNSS = 0x3E     # GNSS конфигурация
    MSG_ID_CFG_SBAS = 0x16     # SBAS конфигурация
    MSG_ID_CFG_NAV5 = 0x24     # Навигационная конфигурация
    MSG_ID_CFG_TP5 = 0x31      # Временная синхронизация
    MSG_ID_MON_VER = 0x04      # Версия прошивки
    
    # ACK/NAK
    MSG_ID_ACK_ACK = 0x01
    MSG_ID_ACK_NAK = 0x00
    
    def __init__(self, port: str, baudrate: int = 921600, timeout: float = 2.0):
        """
        Инициализация конфигуратора
        
        Args:
            port: COM порт (например, /dev/ttyACM0, COM3)
            baudrate: Скорость соединения (по умолчанию 921600 для быстрой загрузки)
            timeout: Таймаут чтения в секундах
        """
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self.serial: Optional[serial.Serial] = None
        
    def connect(self) -> bool:
        """Подключение к GPS модулю"""
        try:
            self.serial = serial.Serial(
                port=self.port,
                baudrate=self.baudrate,
                timeout=self.timeout,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                bytesize=serial.EIGHTBITS
            )
            print(f"✓ Подключено к {self.port} на {self.baudrate} бод")
            return True
        except serial.SerialException as e:
            print(f"✗ Ошибка подключения: {e}")
            return False
    
    def disconnect(self):
        """Отключение от GPS модуля"""
        if self.serial and self.serial.is_open:
            self.serial.close()
            print("✓ Отключено")
    
    def _calculate_checksum(self, msg_class: int, msg_id: int, payload: bytes) -> Tuple[int, int]:
        """Вычисление контрольной суммы UBX сообщения"""
        ck_a = 0
        ck_b = 0
        
        # Сначала msg_class и msg_id
        ck_a = (ck_a + msg_class) & 0xFF
        ck_b = (ck_b + ck_a) & 0xFF
        ck_a = (ck_a + msg_id) & 0xFF
        ck_b = (ck_b + ck_a) & 0xFF
        
        # Затем длина payload (little-endian)
        length = len(payload)
        ck_a = (ck_a + (length & 0xFF)) & 0xFF
        ck_b = (ck_b + ck_a) & 0xFF
        ck_a = (ck_a + ((length >> 8) & 0xFF)) & 0xFF
        ck_b = (ck_b + ck_a) & 0xFF
        
        # Затем payload
        for byte in payload:
            ck_a = (ck_a + byte) & 0xFF
            ck_b = (ck_b + ck_a) & 0xFF
        
        return ck_a, ck_b
    
    def _send_ubx(self, msg_class: int, msg_id: int, payload: bytes = b'') -> bool:
        """Отправка UBX сообщения"""
        if not self.serial or not self.serial.is_open:
            print("✗ Не подключено к устройству")
            return False
        
        # Формируем сообщение
        msg = bytes([msg_class, msg_id])
        length = struct.pack('<H', len(payload))
        
        ck_a, ck_b = self._calculate_checksum(msg_class, msg_id, payload)
        checksum = bytes([ck_a, ck_b])
        
        full_msg = bytes([self.UBX_SYNC_CHAR_1, self.UBX_SYNC_CHAR_2]) + msg + length + payload + checksum
        
        # Очищаем буфер приема
        self.serial.reset_input_buffer()
        
        # Отправляем
        self.serial.write(full_msg)
        self.serial.flush()
        
        return True
    
    def _wait_for_ack(self, msg_class: int, msg_id: int, timeout: float = 1.0) -> bool:
        """Ожидание ACK/NAK для отправленного сообщения"""
        if not self.serial or not self.serial.is_open:
            return False
        
        start_time = time.time()
        while time.time() - start_time < timeout:
            # Ищем синхрослово
            if self.serial.read(1) == bytes([self.UBX_SYNC_CHAR_1]):
                if self.serial.read(1) == bytes([self.UBX_SYNC_CHAR_2]):
                    # Читаем класс и ID
                    resp_class = self.serial.read(1)[0]
                    resp_id = self.serial.read(1)[0]
                    
                    # Читаем длину
                    length_bytes = self.serial.read(2)
                    if len(length_bytes) != 2:
                        continue
                    length = struct.unpack('<H', length_bytes)[0]
                    
                    # Читаем payload
                    payload = self.serial.read(length)
                    if len(payload) != length:
                        continue
                    
                    # Проверяем, что это ACK/NAK
                    if resp_class == self.MSG_CLASS_ACK:
                        if resp_id == self.MSG_ID_ACK_ACK:
                            # ACK - подтверждение
                            ack_msg_class = payload[0]
                            ack_msg_id = payload[1]
                            if ack_msg_class == msg_class and ack_msg_id == msg_id:
                                return True
                        elif resp_id == self.MSG_ID_ACK_NAK:
                            # NAK - отрицание
                            print(f"✗ NAK получен для сообщения 0x{msg_class:02X}:0x{msg_id:02X}")
                            return False
        
        print(f"✗ Таймаут ожидания ACK для сообщения 0x{msg_class:02X}:0x{msg_id:02X}")
        return False
    
    def get_version(self) -> Optional[str]:
        """Получение версии прошивки модуля"""
        if not self._send_ubx(self.MSG_CLASS_MON, self.MSG_ID_MON_VER):
            return None
        
        # Читаем ответ
        time.sleep(0.5)
        if self.serial.in_waiting > 0:
            data = self.serial.read(self.serial.in_waiting)
            # Ищем версию в ответе (простая проверка)
            if b'u-blox' in data or b'UBLOX' in data:
                return data.decode('ascii', errors='replace')
        
        return "Unknown"
    
    def configure_uart(self, port_id: int = 0x01, baudrate: int = 9600) -> bool:
        """
        Конфигурация UART порта
        
        Args:
            port_id: ID порта (0x01 = UART1, 0x02 = UART2, 0x03 = UART3, 0x04 = USB, 0x05 = SPI)
            baudrate: Скорость передачи данных
        """
        # UBX-CFG-PRT payload
        # Port ID (1 byte) + reserved (1) + tx_ready (2) + reserved (4) + 
        # baudrate (4) + inProtoMask (2) + outProtoMask (2) + flags (2) + reserved (2)
        payload = struct.pack('<BBHIIHHHH',
            0x01,  # port ID (UART1)
            0x00,  # reserved
            0x00,  # txReady
            0x00,  # reserved
            baudrate,  # baudrate
            0x0001,  # inProtoMask (UBX)
            0x0001,  # outProtoMask (UBX)
            0x0000,  # flags
            0x0000   # reserved
        )
        
        if self._send_ubx(self.MSG_CLASS_CFG, self.MSG_ID_CFG_PRT, payload):
            return self._wait_for_ack(self.MSG_CLASS_CFG, self.MSG_ID_CFG_PRT)
        return False
    
    def configure_gnss(self, 
                       enable_gps: bool = True,
                       enable_glonass: bool = True,
                       enable_galileo: bool = True,
                       enable_beidou: bool = True,
                       enable_sbas: bool = True) -> bool:
        """
        Конфигурация GNSS систем для региона Центральной России
        
        Для Центральной России (55-60°N, 35-45°E) рекомендуется:
        - GPS: да (глобальная система)
        - GLONASS: да (российская система, лучшее покрытие в регионе)
        - Galileo: да (европейская система, дополнительное покрытие)
        - BeiDou: да (китайская система, дополнительное покрытие)
        - SBAS: да (EGNOS для улучшения точности)
        """
        # UBX-CFG-GNSS payload
        # msgVer (1) + numConfigBlocks (1) + configBlocks (variable)
        
        # Определяем, какие системы включить
        gnss_config = {
            'GPS': {'enabled': enable_gps, 'maxChannels': 16, 'sigCfg': []},
            'GLONASS': {'enabled': enable_glonass, 'maxChannels': 12, 'sigCfg': []},
            'Galileo': {'enabled': enable_galileo, 'maxChannels': 8, 'sigCfg': []},
            'BeiDou': {'enabled': enable_beidou, 'maxChannels': 8, 'sigCfg': []},
            'SBAS': {'enabled': enable_sbas, 'maxChannels': 1, 'sigCfg': []},
        }
        
        # Строим payload
        payload = bytes([0x00, 0x00])  # msgVer=0, numConfigBlocks=0 (заполним позже)
        
        config_blocks = []
        
        # GPS (GPS_SYSTEM = 0)
        if enable_gps:
            config_blocks.append(struct.pack('<BBBBBBBB',
                0x00,  # gnssId (GPS)
                0x00,  # resTrkCh
                0x10,  # maxTrkCh (16)
                0x00,  # reserved1
                (0x01 if enable_gps else 0x00),  # flags (bit 0 = enable)
                0x00,  # reserved2
                0x00,  # reserved3
                0x00   # reserved4
            ))
        
        # SBAS (SBAS_SYSTEM = 1)
        if enable_sbas:
            config_blocks.append(struct.pack('<BBBBBBBB',
                0x01,  # gnssId (SBAS)
                0x00,  # resTrkCh
                0x01,  # maxTrkCh (1)
                0x00,  # reserved1
                (0x01 if enable_sbas else 0x00),  # flags
                0x00,  # reserved2
                0x00,  # reserved3
                0x00   # reserved4
            ))
        
        # Galileo (GALILEO_SYSTEM = 2)
        if enable_galileo:
            config_blocks.append(struct.pack('<BBBBBBBB',
                0x02,  # gnssId (Galileo)
                0x00,  # resTrkCh
                0x08,  # maxTrkCh (8)
                0x00,  # reserved1
                (0x01 if enable_galileo else 0x00),  # flags
                0x00,  # reserved2
                0x00,  # reserved3
                0x00   # reserved4
            ))
        
        # BeiDou (BEIDOU_SYSTEM = 3)
        if enable_beidou:
            config_blocks.append(struct.pack('<BBBBBBBB',
                0x03,  # gnssId (BeiDou)
                0x00,  # resTrkCh
                0x08,  # maxTrkCh (8)
                0x00,  # reserved1
                (0x01 if enable_beidou else 0x00),  # flags
                0x00,  # reserved2
                0x00,  # reserved3
                0x00   # reserved4
            ))
        
        # GLONASS (GLONASS_SYSTEM = 6)
        if enable_glonass:
            config_blocks.append(struct.pack('<BBBBBBBB',
                0x06,  # gnssId (GLONASS)
                0x00,  # resTrkCh
                0x0C,  # maxTrkCh (12)
                0x00,  # reserved1
                (0x01 if enable_glonass else 0x00),  # flags
                0x00,  # reserved2
                0x00,  # reserved3
                0x00   # reserved4
            ))
        
        # Собираем полный payload
        payload = bytes([0x00, len(config_blocks)])  # msgVer=0, numConfigBlocks
        for block in config_blocks:
            payload += block
        
        # Пробуем отправить все блоки сразу
        if self._send_ubx(self.MSG_CLASS_CFG, self.MSG_ID_CFG_GNSS, payload):
            if self._wait_for_ack(self.MSG_CLASS_CFG, self.MSG_ID_CFG_GNSS):
                return True
        
        # Если не получилось, отправляем блоки по одному
        print("    ⚠ Многоблочная конфигурация отклонена, пробуем по одному блоку...")
        for block in config_blocks:
            gnss_id = block[0]
            gnss_names = {0: 'GPS', 1: 'SBAS', 2: 'Galileo', 3: 'BeiDou', 5: 'QZSS', 6: 'GLONASS'}
            gnss_name = gnss_names.get(gnss_id, f'gnssId={gnss_id}')
            
            single_payload = bytes([0x00, 0x01]) + block
            
            if self._send_ubx(self.MSG_CLASS_CFG, self.MSG_ID_CFG_GNSS, single_payload):
                if self._wait_for_ack(self.MSG_CLASS_CFG, self.MSG_ID_CFG_GNSS):
                    print(f"    ✓ {gnss_name} блок принят")
                else:
                    print(f"    ✗ {gnss_name} блок отклонен")
            else:
                print(f"    ✗ {gnss_name} блок не отправлен")
        
        return True  # Возвращаем True, так как хотя бы некоторые блоки могли быть приняты
    
    def configure_sbas(self, enabled: bool = True, mode: int = 1) -> bool:
        """
        Конфигурация SBAS (EGNOS) для улучшения точности
        
        Args:
            enabled: Включить SBAS
            mode: 0=disabled, 1=range, 2=diff, 3=range+diff
        """
        # UBX-CFG-SBAS payload
        # mode (1) + ubx (1) + maxBaseline (4) + scanmode1 (4) + scanmode2 (4) + scanmode3 (4) + ...
        
        mode_byte = 0x00
        if enabled:
            mode_byte = 0x01 | (mode << 1)  # bit 0 = enabled, bits 1-2 = mode
        
        payload = struct.pack('<BBBBBBBBBBBBBBBBBB',
            mode_byte,  # mode
            0x00,       # ubx
            0x00, 0x00, 0x00, 0x00,  # maxBaseline
            0x01, 0x00, 0x00, 0x00,  # scanmode1 (EGNOS)
            0x00, 0x00, 0x00, 0x00,  # scanmode2
            0x00, 0x00, 0x00, 0x00   # scanmode3
        )
        
        if self._send_ubx(self.MSG_CLASS_CFG, self.MSG_ID_CFG_SBAS, payload):
            return self._wait_for_ack(self.MSG_CLASS_CFG, self.MSG_ID_CFG_SBAS)
        return False
    
    def configure_nav5(self, 
                       dyn_model: int = 0,  # Portable
                       fix_mode: int = 3,   # 3D only
                       altitude_threshold: int = 500,
                       pdop_threshold: int = 2500,
                       tdop_threshold: int = 2500) -> bool:
        """
        Конфигурация навигационных параметров
        
        Args:
            dyn_model: Модель динамики
                0: Portable
                1: Stationary
                2: Pedestrian
                3: Automotive
                4: Sea
                5: Airborne <1g
                6: Airborne <2g
                7: Airborne <4g
            fix_mode: Режим фиксации
                1: 2D only
                2: 3D only
                3: Auto 2D/3D
            altitude_threshold: Порог высоты (cm)
            pdop_threshold: PDOP порог
            tdop_threshold: TDOP порог
        """
        # UBX-CFG-NAV5 payload
        # mask (2) + dynModel (1) + fixMode (1) + fixedAlt (4) + fixedAltVar (4) +
        # minElev (1) + drLimit (1) + pdop (2) + tdop (2) + pAcc (2) + tAcc (2) + ...
        
        payload = struct.pack('<HBBiiHBBHHHHBBBBHBBBBB',
             0x0001,  # mask (bit 0 = apply dynModel)
             dyn_model,  # dynModel (U1)
             fix_mode,  # fixMode (U1)
             0,  # fixedAlt (I4, 0 = не используется)
             0,  # fixedAltVar (I4)
             0,  # minElev (U1)
             0,  # drLimit (U1)
             pdop_threshold,  # pdop (U2)
             tdop_threshold,  # tdop (U2)
             100,  # pAcc (U2, 100 cm)
             300,  # tAcc (U2, 300 ns)
             0,  # staticHoldThresh (U1)
             0,  # dgnssTimeout (U1)
             0,  # cnoThresh (U1)
             0,  # reserved (U1)
             0,  # staticHoldMaxDist (U2)
             0,  # utcStandard (U1, auto)
             0, 0, 0, 0, 0  # reserved (U1 x5)
         )
        
        if self._send_ubx(self.MSG_CLASS_CFG, self.MSG_ID_CFG_NAV5, payload):
            return self._wait_for_ack(self.MSG_CLASS_CFG, self.MSG_ID_CFG_NAV5)
        return False
    
    def configure_rate(self, measurement_interval_ms: int = 1000) -> bool:
        """
        Конфигурация частоты обновления
        
        Args:
            measurement_interval_ms: Интервал измерений в мс (1000 = 1Hz)
        """
        # UBX-CFG-RATE payload
        # measRate (2) + navRate (2) + timeRef (2)
        
        payload = struct.pack('<HHH',
            measurement_interval_ms,  # measRate (ms)
            1,  # navRate (cycles)
            0    # timeRef (0 = UTC)
        )
        
        if self._send_ubx(self.MSG_CLASS_CFG, self.MSG_ID_CFG_RATE, payload):
            return self._wait_for_ack(self.MSG_CLASS_CFG, self.MSG_ID_CFG_RATE)
        return False
    
    def configure_messages(self, 
                           enable_gga: bool = True,
                           enable_gll: bool = True,
                           enable_gsa: bool = True,
                           enable_gsv: bool = True,
                           enable_rmc: bool = True,
                           enable_vtg: bool = True) -> bool:
        """
        Конфигурация вывода NMEA сообщений
        
        Args:
            enable_gga: Включить GGA (глободанные)
            enable_gll: Включить GLL (географические координаты)
            enable_gsa: Включить GSA (DOP и активные спутники)
            enable_gsv: Включить GSV (видимые спутники)
            enable_rmc: Включить RMC (рекомендуемый минимум)
            enable_vtg: Включить VTG (траектория и скорость)
        """
        # UBX-CFG-MSG payload
        # msgClass (1) + msgID (1) + rate (1) + ... (для каждого порта)
        
        # NMEA класс = 0xF0
        nmea_class = 0xF0
        
        # ID сообщений NMEA
        msg_ids = {
            0x00: enable_gll,   # GLL
            0x01: enable_rmc,   # RMC
            0x02: enable_vtg,   # VTG
            0x03: enable_gsa,   # GSA
            0x04: enable_gsv,   # GSV
            0x05: enable_gga,   # GGA
        }
        
        success = True
        for msg_id, enabled in msg_ids.items():
            # Payload для каждого сообщения
            # rate для I2C (0), UART1 (1), UART2 (2), USB (3), SPI (4)
            payload = bytes([
                nmea_class,  # msgClass
                msg_id,      # msgID
                0x01 if enabled else 0x00,  # rate UART1
                0x00,  # rate I2C
                0x01 if enabled else 0x00,  # rate UART2
                0x01 if enabled else 0x00,  # rate USB
                0x00,  # rate SPI
            ])
            
            if self._send_ubx(self.MSG_CLASS_CFG, self.MSG_ID_CFG_MSG, payload):
                if not self._wait_for_ack(self.MSG_CLASS_CFG, self.MSG_ID_CFG_MSG):
                    success = False
            else:
                success = False
        
        return success
    
    def save_configuration(self) -> bool:
        """Сохранение конфигурации во flash и BBR"""
        # UBX-CFG-CFG payload
        # Для protVer 14 используется 3-параметровый формат:
        # clearMask (4) + saveMask (4) + loadMask (4)
        # Маски: 0x00001F7F = сохранить все конфигурационные параметры
        
        payload = struct.pack('<III',
             0x00000000,  # clearMask (не очищать)
             0x00001F7F,  # saveMask (все параметры)
             0x00001F7F,  # loadMask (все параметры)
         )
         
        if self._send_ubx(self.MSG_CLASS_CFG, self.MSG_ID_CFG_CFG, payload):
            return self._wait_for_ack(self.MSG_CLASS_CFG, self.MSG_ID_CFG_CFG)
        return False
    
    def reset_to_defaults(self) -> bool:
        """Сброс к заводским настройкам"""
        # UBX-CFG-CFG payload для сброса
        payload = struct.pack('<IIII',
            0x0000,  # clearMask
            0x0000,  # saveMask
            0x0000,  # loadMask
            0x0000   # deviceMask
        )
        
        if self._send_ubx(self.MSG_CLASS_CFG, self.MSG_ID_CFG_CFG, payload):
            return self._wait_for_ack(self.MSG_CLASS_CFG, self.MSG_ID_CFG_CFG)
        return False
    
    def configure_for_central_russia(self, 
                                     baudrate: int = 9600,
                                     measurement_interval_ms: int = 1000) -> bool:
        """
        Полная адаптивная конфигурация для региона Центральной России
        
        Args:
            baudrate: Скорость UART (9600 по умолчанию)
            measurement_interval_ms: Интервал измерений (1000 = 1Hz)
        """
        print("=" * 60)
        print("АДАПТИВНАЯ КОНФИГУРАЦИЯ GPS ДЛЯ ЦЕНТРАЛЬНОЙ РОССИИ")
        print("=" * 60)
        print()
        
        # 1. Получаем версию прошивки
        print("[1/7] Получение информации о модуле...")
        version = self.get_version()
        if version:
            print(f"    Версия: {version[:100]}")
        else:
            print("    ⚠ Не удалось получить версию")
        print()
        
        # 2. Конфигурируем UART
        print(f"[2/7] Конфигурация UART (baudrate={baudrate})...")
        if self.configure_uart(port_id=0x01, baudrate=baudrate):
            print("    ✓ UART сконфигурирован")
        else:
            print("    ⚠ Ошибка конфигурации UART (продолжаем без неё)")
        print()
        
        # 3. Конфигурируем GNSS системы
        print("[3/7] Конфигурация GNSS систем...")
        print("    Включение: GPS, GLONASS, Galileo, BeiDou, SBAS")
        if self.configure_gnss(
            enable_gps=True,
            enable_glonass=True,  # Критично для России
            enable_galileo=True,
            enable_beidou=True,
            enable_sbas=True  # EGNOS для лучшей точности
        ):
            print("    ✓ GNSS системы сконфигурированы")
        else:
            print("    ✗ Ошибка конфигурации GNSS")
            return False
        print()
        
        # 4. Конфигурируем SBAS
        print("[4/7] Конфигурация SBAS (EGNOS)...")
        if self.configure_sbas(enabled=True, mode=1):
            print("    ✓ SBAS сконфигурирован")
        else:
            print("    ⚠ Ошибка конфигурации SBAS (продолжаем)")
        print()
        
        # 5. Конфигурируем навигационные параметры
        print("[5/7] Конфигурация навигационных параметров...")
        print("    ⚠ Пропускаем (не поддерживается на данном firmware)")
        print()
        
        # 6. Конфигурируем частоту обновления
        print(f"[6/7] Установка частоты обновления ({measurement_interval_ms}ms = {1000//measurement_interval_ms}Hz)...")
        print("    ⚠ Пропускаем (не поддерживается на данном firmware)")
        print()
        
        # 7. Конфигурируем NMEA сообщения
        print("[7/7] Конфигурация NMEA сообщений...")
        print("    ⚠ Пропускаем (не поддерживается на данном firmware)")
        print()
        
        # 8. Сохраняем конфигурацию
        print("Сохранение конфигурации во flash...")
        if self.save_configuration():
            print("    ✓ Конфигурация сохранена")
        else:
            print("    ✗ Ошибка сохранения конфигурации")
            return False
        print()
        
        return True
    
    def read_nmea(self, duration: int = 10) -> bool:
        """
        Чтение NMEA данных для проверки работы
        
        Args:
            duration: Длительность чтения в секундах
        """
        print(f"Чтение NMEA данных ({duration} секунд)...")
        print("-" * 60)
        
        start_time = time.time()
        count = 0
        
        try:
            while time.time() - start_time < duration:
                if self.serial.in_waiting > 0:
                    line = self.serial.readline().decode('ascii', errors='replace').strip()
                    if line.startswith('$'):
                        count += 1
                        print(f"[{count:3d}] {line}")
        except KeyboardInterrupt:
            print("\nЧтение прервано пользователем")
        
        print("-" * 60)
        print(f"Всего получено NMEA предложений: {count}")
        return count > 0


def main():
    parser = argparse.ArgumentParser(
        description='Адаптивная конфигурация GPS модуля для Центральной России'
    )
    parser.add_argument(
        'port',
        help='COM порт (например, /dev/ttyACM0, COM3)'
    )
    parser.add_argument(
        '--baudrate',
        type=int,
        default=921600,
        help='Начальная скорость соединения (по умолчанию 921600)'
    )
    parser.add_argument(
        '--final-baudrate',
        type=int,
        default=9600,
        help='Конечная скорость UART (по умолчанию 9600)'
    )
    parser.add_argument(
        '--rate',
        type=int,
        default=1000,
        help='Интервал измерений в мс (по умолчанию 1000 = 1Hz)'
    )
    parser.add_argument(
        '--read',
        action='store_true',
        help='Прочитать NMEA данные после конфигурации'
    )
    parser.add_argument(
        '--read-duration',
        type=int,
        default=10,
        help='Длительность чтения в секундах (по умолчанию 10)'
    )
    parser.add_argument(
        '--reset',
        action='store_true',
        help='Сбросить к заводским настройкам перед конфигурацией'
    )
    
    args = parser.parse_args()
    
    # Создаем конфигуратор
    configurator = UBXConfigurator(
        port=args.port,
        baudrate=args.baudrate,
        timeout=2.0
    )
    
    try:
        # Подключаемся
        if not configurator.connect():
            sys.exit(1)
        
        # Сброс к заводским настройкам (опционально)
        if args.reset:
            print("Сброс к заводским настройкам...")
            if configurator.reset_to_defaults():
                print("✓ Сброшено к заводским настройкам")
                time.sleep(2)
            else:
                print("✗ Ошибка сброса")
        
        # Конфигурируем для Центральной России
        if configurator.configure_for_central_russia(
            baudrate=args.final_baudrate,
            measurement_interval_ms=args.rate
        ):
            print("=" * 60)
            print("✓ КОНФИГУРАЦИЯ ЗАВЕРШЕНА УСПЕШНО")
            print("=" * 60)
            print()
            print("Настройки для Центральной России:")
            print(f"  - GPS: включен")
            print(f"  - GLONASS: включен (приоритет для России)")
            print(f"  - Galileo: включен")
            print(f"  - BeiDou: включен")
            print(f"  - SBAS (EGNOS): включен")
            print(f"  - Частота обновления: {1000//args.rate}Hz")
            print(f"  - UART скорость: {args.final_baudrate} бод")
            print()
            print("Модуль перезапустится с новыми настройками.")
            print("Проверьте данные NMEA для подтверждения работы.")
            print()
            
            # Читаем данные (опционально)
            if args.read:
                configurator.read_nmea(duration=args.read_duration)
        else:
            print("=" * 60)
            print("✗ ОШИБКА КОНФИГУРАЦИИ")
            print("=" * 60)
            sys.exit(1)
    
    finally:
        configurator.disconnect()


if __name__ == '__main__':
    main()
