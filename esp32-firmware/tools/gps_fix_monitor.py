#!/usr/bin/env python3
"""
Монитор захвата фикса GNSS по NMEA с авто-переподключением.

Если порт кратковременно исчезает (микро-обрыв питания/кабеля), монитор
ждёт его возвращения и продолжает, не падая. Показывает GGA/GSA/GSV-сводку
раз в 5 с. Запуск:
  python3 gps_fix_monitor.py --port /dev/ttyUSB0 --baud 57600
Ctrl-C для выхода.
"""

import argparse
import os
import sys
import time

try:
    import serial
except ImportError:
    sys.exit("Нужен pyserial:  pip install pyserial")


def main():
    ap = argparse.ArgumentParser(
        description="Монитор фикса GNSS по NMEA (с реконнектом)"
    )
    ap.add_argument("--port", default="/dev/ttyUSB0")
    ap.add_argument("--baud", type=int, default=57600)
    ap.add_argument("--wait", type=int, default=30, help="ждать порта, сек")
    a = ap.parse_args()

    gga = {"fix": "?", "nsat": "?", "hdop": "?"}
    gsa_used = "?"
    cno = {}
    last_t = 0

    print(
        f"Монитор {a.port} @ {a.baud} Бод (NMEA, авто-реконнект). Ctrl-C для выхода.\n",
        flush=True,
    )
    while True:  # внешний цикл - переподключение
        if not os.path.exists(a.port):
            print(f"[порт {a.port} нет, жду до {a.wait} с...]", flush=True)
            t0 = time.time()
            while not os.path.exists(a.port) and time.time() - t0 < a.wait:
                time.sleep(1)
            if not os.path.exists(a.port):
                print("[порт не появился - выход]", flush=True)
                break
        try:
            with serial.Serial(a.port, a.baud, timeout=1) as ser:
                print(f"[подключено {a.port}]", flush=True)
                while True:
                    if not os.path.exists(a.port):
                        print("[порт исчез - реконнект]", flush=True)
                        break
                    raw = ser.readline()
                    try:
                        line = raw.decode("ascii", "replace").strip()
                    except Exception:
                        continue
                    if not line.startswith("$") or "," not in line:
                        continue
                    f = line.split(",")
                    tag = f[0][1:]

                    if tag[2:] == "GGA" and len(f) > 8:
                        gga = {
                            "fix": f[6] or "?",
                            "nsat": f[7] or "?",
                            "hdop": f[8] or "?",
                        }
                    elif tag[2:] == "GSA" and len(f) >= 3:
                        used = [p for p in f[3:15] if p]
                        gsa_used = str(len(used))
                    elif tag[2:] == "GSV" and len(f) > 4:
                        for i in range(4, len(f) - 3, 4):
                            try:
                                sv = f[i]
                                sig = f[i + 3].split("*")[0]
                            except IndexError:
                                continue
                            if sv and sig.isdigit():
                                cno[sv] = int(sig)

                    t = time.time()
                    if t - last_t >= 5:
                        last_t = t
                        if cno:
                            vals = sorted(cno.values())
                            best = vals[-1]
                            weak = sum(1 for v in vals if v >= 30)
                            med = vals[len(vals) // 2]
                        else:
                            best = med = weak = 0
                        print(
                            f"  fix={gga['fix']} sv={gga['nsat']} в_решении={gsa_used} "
                            f"HDOP={gga['hdop']} | видимо={len(cno)} "
                            f"C/N0 мед={med} лучш={best} (>=30дБ: {weak})",
                            flush=True,
                        )
        except serial.SerialException as e:
            print(f"[SerialException: {e} - реконнект]", flush=True)
            time.sleep(2)
        except KeyboardInterrupt:
            print("\nпрервано", flush=True)
            return


if __name__ == "__main__":
    main()
