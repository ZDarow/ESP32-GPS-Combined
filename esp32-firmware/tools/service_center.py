#!/usr/bin/env python3
"""
СЕРВИСНЫЙ ЦЕНТР GPS/ГНСС-МОДУЛЕЙ (u-blox M6/M7/M8/M9/M10).

Полный цикл обслуживания "на столе", без необходимости ловить фикс:
  1. ДИАГНОСТИКА   - читаем текущую конфигурацию модуля (UBX-CFG-*).
  2. КОРРЕКЦИЯ     - выявляем отклонения от целевого профиля и устраняем
                     только то, что реально сбито (атомарные правки).
  3. ЗАПИСЬ        - сохраняем исправленную конфигурацию в энергонезависимую
                     память (flash + BBR) и очищаем BBR для холодного старта.

Целевой профиль ориентирован на Центральную Россию (55-60°N, 35-45°E):
мульти-GNSS (GPS/GLONASS/Galileo/BeiDou) + SBAS (EGNOS), портативная
динамическая модель, 1 Гц, стандартный набор NMEA на UART1 и USB.

Зависимости: pyserial, pyubx2, pygnssutils (см. requirements.txt).
"""

import sys
import time

# Переиспользуем готовые UBX-хелперы из соседних модулей проекта.
import gnss_diag as diag          # ubx_poll(), GNSSReader, UBXMessage, POLL
from gps_configurator import UBXConfigurator

# ---------------------------------------------------------------------------
# Целевой профиль (reference). Всё, что отклоняется - кандидат на коррекцию.
# ---------------------------------------------------------------------------
TARGET = {
    "baud": 57600,                # скорость UART1 (под ESP32-трекер)
    "gnss": {                     # gnssId -> должен быть включён?
        0: True,                  # GPS
        1: True,                  # SBAS
        2: True,                  # Galileo
        3: True,                  # BeiDou
        6: True,                  # GLONASS
    },
    "sbas": {"enabled": True, "mode": 3},   # mode: 3 = range+diff
    "nav5": {
        "dynModel": 0,            # 0 = Portable
        "fixMode": 3,             # 3 = Auto 2D/3D
        # pDop/tDop в CFG-NAV5 заданы в 0.1; pyubx2 отдаёт уже поделённым
        # на 10. Модуль шлёт 25.0 (raw 250) - это заводской дефолт u-blox
        # (DOP 25.0). Целевое 2500 было ошибочно завышено в 100 раз.
        "pDop": 25,
        "tDop": 25,
    },
    "rate": {"measRate": 1000, "navRate": 1, "timeRef": 0},  # 1 Гц, UTC
    # NMEA: msgId -> rate на UART1 (порт 1) и USB (порт 3)
    "nmea": {
        0x00: {"uart1": 1, "usb": 1},   # GLL
        0x01: {"uart1": 1, "usb": 1},   # RMC
        0x02: {"uart1": 1, "usb": 1},   # VTG
        0x03: {"uart1": 1, "usb": 1},   # GSA
        0x04: {"uart1": 1, "usb": 1},   # GSV
        0x05: {"uart1": 1, "usb": 1},   # GGA
    },
}

GNSS_NAMES = {0: "GPS", 1: "SBAS", 2: "Galileo", 3: "BeiDou", 4: "IMES",
              5: "QZSS", 6: "GLONASS"}
NMEA_NAMES = {0x00: "GLL", 0x01: "RMC", 0x02: "VTG", 0x03: "GSA",
              0x04: "GSV", 0x05: "GGA"}


def hdr(title):
    print("\n" + "=" * 64)
    print(title)
    print("=" * 64)


def _timeout_guard(seconds, func, *args, **kwargs):
    """Выполнить func с жёстким таймаутом (SIGALRM), чтобы цикл никогда
    не зависал на неотвечающем модуле."""
    import signal

    if not hasattr(signal, "SIGALRM"):
        return func(*args, **kwargs)

    def _handler(signum, frame):
        raise TimeoutError("timeout")

    old = signal.signal(signal.SIGALRM, _handler)
    signal.alarm(seconds)
    try:
        return func(*args, **kwargs)
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, old)


def read_cfg(stream, cls, mid, secs=2.5):
    """Прочитать одно CFG-сообщение модуля через ubx_poll и вернуть объект.

    Возвращает (msg, perr): msg - первый UBXMessage нужного класса/ID,
    perr - True при ошибке порта. Если сообщение не поддерживается -
    (None, False).
    """
    try:
        msgs, perr = diag.ubx_poll(stream, cls, mid, secs)
    except Exception:
        return None, True
    # ubx_poll уже отфильтровал ответ по class/mid, поэтому берём первый
    # элемент. Не сверяем identity вручную - pyubx2 даёт "CFG-NAV5", а не
    # "CFG-24", и точное сравнение ломало чтение.
    if msgs:
        return msgs[0], False
    return None, perr


def detect(stream):
    """Считать конфиг и вернуть список отклонений от целевого профиля.

    Каждое отклонение - dict: {area, issue, fix(callable)}.
    """
    issues = []

    # --- GNSS (CFG-GNSS, 0x06/0x3E) ---
    m, perr = read_cfg(stream, 0x06, 0x3E)
    if m is None and perr:
        issues.append({"area": "GNSS", "issue": "ошибка чтения CFG-GNSS (порт)",
                       "fix": None})
    elif m is None:
        issues.append({"area": "GNSS", "issue": "CFG-GNSS не поддерживается",
                       "fix": None})
    else:
        n = getattr(m, "numConfigBlocks", 0)
        for i in range(1, n + 1):
            gid = getattr(m, f"gnssId_{i:02d}", None)
            en = getattr(m, f"enable_{i:02d}", False)
            if gid is None:
                continue
            want = TARGET["gnss"].get(gid)
            if want is None:
                continue
            if bool(en) != want:
                name = GNSS_NAMES.get(gid, f"gnssId={gid}")
                issues.append({
                    "area": "GNSS",
                    "issue": f"{name} выключен (ожидается вкл)",
                    "fix": ("gnss", gid, want),
                })

    # --- SBAS (CFG-SBAS, 0x06/0x16) ---
    m, _ = read_cfg(stream, 0x06, 0x16)
    if m is not None:
        en = bool(getattr(m, "enabled", 0))
        mode = getattr(m, "mode", None)
        usage = getattr(m, "usage", None)
        if en != TARGET["sbas"]["enabled"]:
            issues.append({"area": "SBAS", "issue": "SBAS выключен",
                           "fix": ("sbas",)})
        elif mode is not None and mode != TARGET["sbas"]["mode"]:
            issues.append({"area": "SBAS",
                           "issue": f"SBAS mode={mode} (ожид. {TARGET['sbas']['mode']})",
                           "fix": ("sbas",)})
        elif usage is not None and usage != 0x07:
            issues.append({"area": "SBAS", "issue": f"SBAS usage={usage} (ожид. 7)",
                           "fix": ("sbas",)})

    # --- NAV5 (CFG-NAV5, 0x06/0x24) ---
    m, _ = read_cfg(stream, 0x06, 0x24)
    if m is not None:
        for key, want in TARGET["nav5"].items():
            got = getattr(m, key, None)
            if got is not None and got != want:
                issues.append({
                    "area": "NAV5",
                    "issue": f"{key}={got} (ожид. {want})",
                    "fix": ("nav5", key, want),
                })

    # --- RATE (CFG-RATE, 0x06/0x08) ---
    m, _ = read_cfg(stream, 0x06, 0x08)
    if m is not None:
        for key, want in TARGET["rate"].items():
            got = getattr(m, key, None)
            if got is not None and got != want:
                issues.append({
                    "area": "RATE",
                    "issue": f"{key}={got} (ожид. {want})",
                    "fix": ("rate", key, want),
                })

    # --- UART1 baud (CFG-PRT, 0x06/0x00) ---
    m, _ = read_cfg(stream, 0x06, 0x00)
    if m is not None:
        # pyubx2 раскрывает блоки портов: baudRate_01 = UART1
        baud = getattr(m, "baudRate_01", None)
        if baud is not None and baud != TARGET["baud"]:
            issues.append({
                "area": "UART",
                "issue": f"UART1 baud={baud} (ожид. {TARGET['baud']})",
                "fix": ("uart", TARGET["baud"]),
            })

    # --- NMEA rates (CFG-MSG, 0x06/0x01) по каждому сообщению ---
    for mid, want in TARGET["nmea"].items():
        # CFG-MSG требует явного указания опрашиваемого msgClass/msgID,
        # иначе модуль не ответит (пустой POLL игнорируется).
        msgs, _ = diag.ubx_poll(stream, 0x06, 0x01, 2.0,
                                poll_kwargs={"msgClass": 0xF0, "msgID": mid})
        target = None
        for mm in msgs:
            if getattr(mm, "msgID", None) == mid and getattr(mm, "msgClass", None) == 0xF0:
                target = mm
                break
        if target is None:
            issues.append({"area": "NMEA",
                           "issue": f"{NMEA_NAMES.get(mid, hex(mid))} не читается",
                           "fix": ("nmea", mid, want)})
            continue
        r_uart1 = getattr(target, "rateUART1", 0) or 0
        r_usb = getattr(target, "rateUSB", 0) or 0
        if r_uart1 != want["uart1"] or r_usb != want["usb"]:
            issues.append({
                "area": "NMEA",
                "issue": f"{NMEA_NAMES.get(mid, hex(mid))} rate UART1={r_uart1}/USB={r_usb}",
                "fix": ("nmea", mid, want),
            })

    return issues


def apply_fix(cfg: UBXConfigurator, fix):
    """Применить одну коррекцию. fix - кортеж из detect()."""
    kind = fix[0]
    if kind == "gnss":
        _, gid, want = fix
        # Переконфигурируем всю группу GNSS с учётом цели (вкл/выкл).
        # ВНИМАНИЕ: ряд прошивок M8 NAK-ует любой CFG-GNSS SET; в таком
        # случае единственный надёжный путь - reset_to_defaults (см. --reset).
        g = TARGET["gnss"]
        ok = cfg.configure_gnss(
            enable_gps=g.get(0, True),
            enable_glonass=g.get(6, True),
            enable_galileo=g.get(2, True),
            enable_beidou=g.get(3, True),
            enable_sbas=g.get(1, True),
        )
        return ok
    if kind == "sbas":
        cfg.configure_sbas(enabled=TARGET["sbas"]["enabled"],
                           mode=TARGET["sbas"]["mode"])
        return True
    if kind == "nav5":
        _, key, want = fix
        # Меняем только отклоняющийся параметр, остальное - по цели.
        nav = dict(TARGET["nav5"])
        nav[key] = want
        cfg.configure_nav5(
            dyn_model=nav["dynModel"],
            fix_mode=nav["fixMode"],
            pdop_threshold=nav["pDop"],
            tdop_threshold=nav["tDop"],
        )
        return True
    if kind == "rate":
        _, key, want = fix
        r = dict(TARGET["rate"])
        r[key] = want
        cfg.configure_rate(measurement_interval_ms=r["measRate"])
        # navRate/timeRef отдельно не меняем (configure_rate ставит 1/UTC).
        return True
    if kind == "uart":
        _, baud = fix
        cfg.configure_uart(port_id=0x01, baudrate=baud)
        return True
    if kind == "nmea":
        _, mid, want = fix
        # Переприменяем весь целевой набор NMEA (идемпотентно).
        ok = cfg.configure_messages(
            enable_gll=TARGET["nmea"][0x00]["uart1"] > 0,
            enable_rmc=TARGET["nmea"][0x01]["uart1"] > 0,
            enable_vtg=TARGET["nmea"][0x02]["uart1"] > 0,
            enable_gsa=TARGET["nmea"][0x03]["uart1"] > 0,
            enable_gsv=TARGET["nmea"][0x04]["uart1"] > 0,
            enable_gga=TARGET["nmea"][0x05]["uart1"] > 0,
        )
        return ok
    return False


def detect_baud(port, candidates=(9600, 19200, 38400, 57600, 115200,
                                   230400, 460800, 921600)):
    """Автоопределение скорости UART: первый baud, на котором модуль
    отвечает на UBX MON-VER. Возвращает int или None."""
    import serial as pyserial
    for br in candidates:
        try:
            s = pyserial.Serial(port, br, timeout=0.6)
        except Exception:
            continue
        try:
            msgs, _ = diag.ubx_poll(s, 0x0A, 0x04, 1.5)
            if msgs:
                s.close()
                return br
        except Exception:
            pass
        s.close()
    return None


def service_cycle(port, baud=None, do_reset=False, do_clear_bbr=True, save=True):
    """Полный цикл сервисного центра для одного модуля.

    baud=None -> автоопределение скорости (модуль может сидеть на любом
    baud после сбоя конфигурации).
    """
    if baud is None:
        hdr("АВТООПРЕДЕЛЕНИЕ СКОРОСТИ")
        baud = detect_baud(port)
        if baud is None:
            print(f"  модуль не отвечает ни на одной из скоростей на {port}.",
                  flush=True)
            return False
        print(f"  обнаружен baud={baud}", flush=True)

    hdr(f"СЕРВИСНЫЙ ЦИКЛ: {port} @ {baud}")

    import serial as pyserial
    # ОДИН поток и для записи, и для чтения. Иначе два fd на один tty
    # делят буфер ядра, и reset_input_buffer() в configurator перетирает
    # ответы, которые ждёт чтение (gnss_diag.ubx_poll) -> ложные вердикты.
    stream = pyserial.Serial(port, baud, timeout=1)
    cfg = UBXConfigurator(port=port, baudrate=baud, timeout=2.0, serial_obj=stream)
    if not cfg.connect():
        print("  не удалось открыть порт", flush=True)
        stream.close()
        return False

    try:
        # 0. Опционально - сброс к заводским (для сильно "убитых" модулей).
        if do_reset:
            hdr("0. СБРОС К ЗАВОДСКИМ")
            print("  сброс и ожидание перезагрузки модуля...", flush=True)
            cfg.reset_to_defaults()
            time.sleep(2.0)
            stream.close()
            stream = pyserial.Serial(port, baud, timeout=1)
            cfg.serial = stream

        # 1. ДИАГНОСТИКА
        hdr("1. ДИАГНОСТИКА КОНФИГУРАЦИИ")
        try:
            issues = _timeout_guard(60, detect, stream)
        except TimeoutError:
            print("  !! таймаут диагностики (модуль не отвечает на CFG-опросы)",
                  flush=True)
            issues = []
        if not issues:
            print("  отклонений от целевого профиля не выявлено.", flush=True)
        else:
            print(f"  выявлено отклонений: {len(issues)}", flush=True)
            for it in issues:
                print(f"   - [{it['area']}] {it['issue']}", flush=True)

        # 2. КОРРЕКЦИЯ
        fixes = [it["fix"] for it in issues if it["fix"] is not None]
        if fixes:
            hdr("2. КОРРЕКЦИЯ ВЫЯВЛЕННЫХ ПРОБЛЕМ")
            for fx in fixes:
                ok = apply_fix(cfg, fx)
                print(f"   применено: {fx} -> {'OK' if ok else 'ОШИБКА'}", flush=True)
                time.sleep(0.3)
        else:
            print("  коррекция не требуется.", flush=True)

        # 3. ЗАПИСЬ В ПАМЯТЬ
        if save and fixes:
            hdr("3. ЗАПИСЬ В ЭНЕРГОНЕЗАВИСИМУЮ ПАМЯТЬ")
            if cfg.save_configuration():
                print("  конфигурация сохранена в flash/BBR (ACK получен).", flush=True)
            else:
                print("  !! не удалось сохранить конфигурацию (нет ACK).", flush=True)
            if do_clear_bbr:
                if cfg.clear_bbr():
                    print("  BBR очищен - модуль сделает холодный старт.", flush=True)
                else:
                    print("  !! не удалось очистить BBR.", flush=True)
        elif save:
            print("  сохранение пропущено (не было изменений).", flush=True)

        # 4. ВЕРИФИКАЦИЯ (повторное чтение)
        # Конфигуратор мог заглушить NMEA на UART1; восстанавливаем вывод,
        # иначе ubx_poll не получит ответы от модуля.
        try:
            from pyubx2 import UBXMessage
            for mid in (0x00, 0x01, 0x02, 0x03, 0x04, 0x05):
                stream.write(UBXMessage(0x06, 0x01, SET, msgClass=0xF0, msgID=mid,
                                        rateI2C=0, rateUART1=1, rateUART2=0,
                                        rateUSB=1, rateSPI=0).serialize())
                time.sleep(0.1)
        except Exception:
            pass
        hdr("4. ВЕРИФИКАЦИЯ")
        try:
            remaining = _timeout_guard(60, detect, stream)
        except TimeoutError:
            print("  !! таймаут верификации", flush=True)
            remaining = []
        remaining = [it for it in remaining if it["fix"] is not None]
        if not remaining:
            print("  все параметры соответствуют целевому профилю. ОК.", flush=True)
        else:
            print(f"  НЕ устранено отклонений: {len(remaining)}", flush=True)
            for it in remaining:
                print(f"   - [{it['area']}] {it['issue']}", flush=True)
            print("  Рекомендация: выполните power-cycle модуля (отключить/включить",
                  flush=True)
            print("  питание) и повторите цикл. Если отклонения повторяются - модуль",
                  flush=True)
            print("  аппаратно не принимает CFG (типично для CFG-GNSS на части M8",
                  flush=True)
            print("  прошивок) - используйте --reset для загрузки заводского профиля,",
                  flush=True)
            print("  либо замените модуль.", flush=True)

        return True
    finally:
        stream.close()
        cfg.disconnect()


def main():
    import argparse
    ap = argparse.ArgumentParser(description="Сервисный центр ГНСС-модулей")
    ap.add_argument("--port", required=True, help="порт, напр. /dev/ttyUSB0")
    ap.add_argument("--baud", type=int, default=None,
                    help="скорость (по умолч. автоопределение)")
    ap.add_argument("--reset", action="store_true",
                    help="сначала сбросить к заводским")
    ap.add_argument("--no-bbr-clear", action="store_true",
                    help="не очищать BBR (холодный старт)")
    ap.add_argument("--no-save", action="store_true",
                    help="не сохранять в flash (только проверка/коррекция в RAM)")
    a = ap.parse_args()

    service_cycle(
        a.port, a.baud,
        do_reset=a.reset,
        do_clear_bbr=not a.no_bbr_clear,
        save=not a.no_save,
    )


if __name__ == "__main__":
    main()
