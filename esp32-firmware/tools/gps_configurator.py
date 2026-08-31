#!/usr/bin/env python3
"""
Конфигуратор u-blox GPS/ГНСС-модулей (Центральная Россия).

Построен поверх pyubx2: все UBX-CFG собираются библиотекой (корректные
поля и контрольные суммы), отправка и ожидание ACK - через pyserial.
Поддерживает M6/M7/M8/M9/M10.

Регион: Центральная Россия (55-60°N, 35-45°E) - мульти-GNSS + SBAS(EGNOS).
"""

import serial
import time
import sys
import argparse
from typing import Optional, Tuple

from pyubx2 import UBXMessage, UBXReader, SET, POLL


class UBXConfigurator:
    """Класс для конфигурации u-blox GPS модулей через pyubx2."""

    def __init__(self, port: str, baudrate: int = 57600, timeout: float = 2.0,
                 serial_obj: Optional[serial.Serial] = None):
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        # serial_obj позволяет переиспользовать УЖЕ открытый порт (сервис-центр
        # читает и пишет через один и тот же поток, чтобы не перетирать общий
        # буфер ядра tty вызовами reset_input_buffer из разных fd).
        self.serial: Optional[serial.Serial] = serial_obj
        self._owns_serial = serial_obj is None

    # ------------------------------------------------------------------ low
    def connect(self) -> bool:
        if self.serial is not None:
            # Порт передан извне - просто убеждаемся, что он открыт.
            try:
                if not self.serial.is_open:
                    self.serial.open()
            except serial.SerialException as e:
                print(f"✗ Ошибка открытия переданного порта: {e}")
                return False
            print(f"✓ Подключено к {self.port} на {self.baudrate} бод")
            return True
        try:
            self.serial = serial.Serial(
                port=self.port, baudrate=self.baudrate, timeout=self.timeout,
                parity=serial.PARITY_NONE, stopbits=serial.STOPBITS_ONE,
                bytesize=serial.EIGHTBITS,
            )
            print(f"✓ Подключено к {self.port} на {self.baudrate} бод")
            return True
        except serial.SerialException as e:
            print(f"✗ Ошибка подключения: {e}")
            return False

    def disconnect(self):
        # Закрываем только если порт открывали сами - переданный извне
        # закрывает владелец (service_center).
        if self.serial and self.serial.is_open and self._owns_serial:
            self.serial.close()
            print("✓ Отключено")

    def _send(self, msg: UBXMessage) -> bool:
        if not self.serial or not self.serial.is_open:
            print("✗ Не подключено к устройству")
            return False
        self.serial.reset_input_buffer()
        self.serial.write(msg.serialize())
        self.serial.flush()
        return True

    def _wait_for_ack(self, msg_class: int, msg_id: int, timeout: float = 3.0) -> bool:
        """Ожидание ACK/NAK через UBXReader (устойчиво к NMEA-мусору)."""
        if not self.serial or not self.serial.is_open:
            return False
        reader = UBXReader(self.serial, protfilter=2)  # только UBX
        start = time.time()
        while time.time() - start < timeout:
            try:
                _, parsed = reader.read()
            except Exception:
                continue
            if parsed is None:
                continue
            ident = getattr(parsed, "identity", "")
            if ident == "ACK-ACK":
                if parsed.clsID == msg_class and parsed.msgID == msg_id:
                    return True
            elif ident == "ACK-NAK":
                if parsed.clsID == msg_class and parsed.msgID == msg_id:
                    print(f"✗ NAK для 0x{msg_class:02X}:0x{msg_id:02X}")
                    return False
        print(f"✗ Таймаут ожидания ACK для 0x{msg_class:02X}:0x{msg_id:02X}")
        return False

    def _suppress_nmea(self):
        """Заглушить NMEA на UART1, чтобы не мешал разбору ACK.

        Возвращаемые настройки восстанавливаются целевым профилем
        (service_center включит нужный набор обратно).
        """
        try:
            for mid in (0x00, 0x01, 0x02, 0x03, 0x04, 0x05):
                msg = UBXMessage(0x06, 0x01, SET, msgClass=0xF0, msgID=mid,
                                 rateI2C=0, rateUART1=0, rateUART2=0,
                                 rateUSB=0, rateSPI=0)
                self._send(msg)
                self._wait_for_ack(0x06, 0x01, 1.0)
        except Exception:
            pass

    def _cfg(self, cls, mid, **kwargs) -> bool:
        try:
            msg = UBXMessage(cls, mid, SET, **kwargs)
        except Exception as e:
            print(f"✗ Ошибка сборки CFG 0x{cls:02X}:0x{mid:02X}: {e}")
            return False
        if self._send(msg):
            return self._wait_for_ack(cls, mid)
        return False

    # --------------------------------------------------------------- версия
    def get_version(self) -> Optional[str]:
        try:
            self.serial.reset_input_buffer()
            self.serial.write(UBXMessage(0x0A, 0x04, POLL).serialize())
            time.sleep(0.5)
            if self.serial.in_waiting > 0:
                data = self.serial.read(self.serial.in_waiting)
                if b"u-blox" in data or b"UBLOX" in data:
                    return data.decode("ascii", errors="replace")
        except Exception:
            pass
        return "Unknown"

    # -------------------------------------------------------------- конфиг
    def configure_uart(self, port_id: int = 1, baudrate: int = 57600) -> bool:
        # UBX-CFG-PRT: включаем UBX+NMEA на in/out, только UART.
        return self._cfg(0x06, 0x00,
                         portID=port_id, reserved0=0, txReady=0, reserved1=0,
                         baudRate=baudrate, inProtoMask=7, outProtoMask=3,
                         reserved2=0, reserved3=0)

    def configure_gnss(self, enable_gps=True, enable_glonass=True,
                       enable_galileo=True, enable_beidou=True,
                       enable_sbas=True) -> bool:
        """Включить/выключить ГНСС-системы.

        Опрашиваем текущий CFG-GNSS, сохраняем родные maxTrkCh/resTrkCh
        модуля (чтобы не превысить лимит каналов M8) и меняем только флаг
        enable. Блоки шлём по одному.
        """
        want = {0: enable_gps, 1: enable_sbas, 2: enable_galileo,
                3: enable_beidou, 6: enable_glonass}
        # узнаём текущие maxTrkCh/resTrkCh каждой системы
        cur = {}
        try:
            self.serial.reset_input_buffer()
            self.serial.write(UBXMessage(0x06, 0x3E, POLL).serialize())
            reader = UBXReader(self.serial, protfilter=2)
            t0 = time.time()
            while time.time() - t0 < 2.0:
                try:
                    _, parsed = reader.read()
                except Exception:
                    continue
                if parsed is None:
                    continue
                if getattr(parsed, "identity", "") == "CFG-GNSS":
                    n = getattr(parsed, "numConfigBlocks", 0)
                    for i in range(1, n + 1):
                        gid = getattr(parsed, f"gnssId_{i:02d}", None)
                        if gid is None:
                            continue
                        cur[gid] = (
                            getattr(parsed, f"resTrkCh_{i:02d}", 255) & 0xFF,
                            getattr(parsed, f"maxTrkCh_{i:02d}", 255) & 0xFF,
                        )
                    break
        except Exception:
            pass

        ok_all = True
        for gid, en in want.items():
            res, mx = cur.get(gid, (8, 8))
            # flags: bit0=enable, bit8(0x0100)=enable сигналов (для M8)
            flags = 0x0101 if en else 0x0000
            msg = UBXMessage(0x06, 0x3E, SET,
                             msgVer=0, gnssId=gid, resTrkCh=res,
                             maxTrkCh=mx, flags=flags)
            sent = self._send(msg)
            ack = self._wait_for_ack(0x06, 0x3E) if sent else False
            name = {0: "GPS", 1: "SBAS", 2: "Galileo", 3: "BeiDou", 6: "GLONASS"}[gid]
            print(f"    {'✓' if ack else '✗'} {name}: {'вкл' if en else 'выкл'}")
            ok_all = ok_all and ack
        return ok_all

    def configure_sbas(self, enabled: bool = True, mode: int = 3) -> bool:
        # mode: 1=range,2=diff,3=range+diff; usage=7 (integrity+range+diff)
        return self._cfg(0x06, 0x16, mode=(0x01 | (mode << 1)) if enabled else 0,
                         usage=0x07 if enabled else 0, maxSBAS=3,
                         scanmode=[1] if enabled else [0])

    def configure_nav5(self, dyn_model: int = 0, fix_mode: int = 3,
                        altitude_threshold: int = 500, pdop_threshold: int = 250,
                        tdop_threshold: int = 250) -> bool:
        # mask: бит0 - зарезервирован (всегда 1), бит1 - dynModel,
        # бит3 - fixMode, бит7 - маска DOP (pDop/tDop). Без этих битов модуль
        # законно ACK-ает CFG-NAV5, но НЕ применяет параметры.
        return self._cfg(0x06, 0x24,
                          mask=0x008B, dynModel=dyn_model, fixMode=fix_mode,
                          fixedAlt=0, fixedAltVar=0, minElev=0, drLimit=0,
                          pDop=pdop_threshold, tDop=tdop_threshold,
                          pAcc=100, tAcc=300, staticHoldThresh=0, dgnssTimeout=0,
                          cnoThresh=0, reserved1=0, staticHoldMaxDist=0,
                          utcStandard=0, reserved2=0)

    def configure_rate(self, measurement_interval_ms: int = 1000) -> bool:
        return self._cfg(0x06, 0x08, measRate=measurement_interval_ms,
                         navRate=1, timeRef=0)

    def configure_messages(self, enable_gga=True, enable_gll=True,
                           enable_gsa=True, enable_gsv=True,
                           enable_rmc=True, enable_vtg=True) -> bool:
        nmea = 0xF0
        plan = [(0x00, enable_gll), (0x01, enable_rmc), (0x02, enable_vtg),
                (0x03, enable_gsa), (0x04, enable_gsv), (0x05, enable_gga)]
        ok = True
        for mid, en in plan:
            # rate: I2C(0), UART1(1), UART2(2), USB(3), SPI(4)
            rate = 0x01 if en else 0x00
            msg = UBXMessage(0x06, 0x01, SET, msgClass=nmea, msgID=mid,
                             rateI2C=0, rateUART1=rate, rateUART2=rate,
                             rateUSB=rate, rateSPI=0)
            sent = self._send(msg)
            ack = self._wait_for_ack(0x06, 0x01) if sent else False
            if not ack:
                ok = False
        return ok

    def save_configuration(self) -> bool:
        # CFG-CFG: сохраняем всё (saveMask=all) в BBR+Flash. loadMask=0 -
        # НЕ перезагружаем конфиг из flash обратно в RAM, иначе модуль
        # откатывает только что записанные параметры к старым (на M8
        # timeRef/RATE возвращались к прежним сразу после save).
        mask = (0x000FFFFF).to_bytes(4, "little")
        dev = (0x07).to_bytes(1, "little")  # 1=BBR,2=Flash,4=EEPROM
        return self._cfg(0x06, 0x09, saveMask=mask, loadMask=(0).to_bytes(4, "little"),
                        deviceMask=dev)

    def reset_to_defaults(self) -> bool:
        # CFG-CFG: clear=load=все биты, save=0 -> загрузка заводских из ROM.
        mask = (0x000FFFFF).to_bytes(4, "little")
        dev = (0x07).to_bytes(1, "little")
        ok = self._cfg(0x06, 0x09, clearMask=mask, saveMask=(0).to_bytes(4, "little"),
                       loadMask=mask, deviceMask=dev)
        time.sleep(1.0)
        return ok

    def clear_bbr(self) -> bool:
        # CFG-CFG: clear/load bit1 (BBR), save=0.
        bbr = (0x00000002).to_bytes(4, "little")
        dev = (0x07).to_bytes(1, "little")
        return self._cfg(0x06, 0x09, clearMask=bbr, saveMask=(0).to_bytes(4, "little"),
                         loadMask=bbr, deviceMask=dev)


def main():
    parser = argparse.ArgumentParser(description='Конфигурация GPS для Центральной России')
    parser.add_argument('port')
    parser.add_argument('--baudrate', type=int, default=57600)
    parser.add_argument('--final-baudrate', type=int, default=57600)
    parser.add_argument('--rate', type=int, default=1000)
    parser.add_argument('--reset', action='store_true')
    parser.add_argument('--read', action='store_true')
    parser.add_argument('--read-duration', type=int, default=10)
    args = parser.parse_args()

    cfg = UBXConfigurator(port=args.port, baudrate=args.baudrate, timeout=2.0)
    if not cfg.connect():
        sys.exit(1)
    try:
        if args.reset:
            print("Сброс к заводским...")
            cfg.reset_to_defaults()
            time.sleep(2)
        print("GNSS...")
        cfg.configure_gnss()
        print("SBAS...")
        cfg.configure_sbas()
        print("NAV5...")
        cfg.configure_nav5()
        print("RATE...")
        cfg.configure_rate(args.rate)
        print("NMEA...")
        cfg.configure_messages()
        print("UART...")
        cfg.configure_uart(1, args.final_baudrate)
        print("SAVE...")
        cfg.save_configuration()
        print("✓ Готово")
    finally:
        cfg.disconnect()


if __name__ == '__main__':
    main()
