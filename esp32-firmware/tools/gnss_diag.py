#!/usr/bin/env python3
"""
Универсальный диагност GNSS-приёмника на последовательном порту.

Работает с любым модулем. Автоопределение порта, скорости и протокола.
Главный тест - корреляция C/N0 между спутниками: у реальных сигналов
C/N0 независимы, у шума меняются синхронно.

NMEA/UBX-парсинг делегирован зрелым библиотекам (pynmeagps, pyubx2,
pygnssutils) - те же, что использует PyGPSClient. Это устраняет хрупкую
самописную эвристику определения чипсета (ложные "CASIC/AT6558" и т.п.).

Запуск:  python3 gnss_diag.py [--port /dev/ttyUSB0] [--baud 9600] [--wait 60]
"""

import argparse
import glob
import os
import signal
import statistics
import sys
import time

try:
    import serial
except ImportError:
    sys.exit("Нужен pyserial:  pip install pyserial")
try:
    from pygnssutils import GNSSReader
    from pyubx2 import UBXMessage, UBXReader, POLL
except ImportError:
    sys.exit("Нужны pyubx2/pygnssutils:  pip install pyubx2 pygnssutils pynmeagps")

BAUDS = [9600, 38400, 115200, 57600, 4800, 19200, 230400, 460800]
TALKERS = {
    "GP": "GPS",
    "GL": "GLONASS",
    "GA": "Galileo",
    "GB": "BeiDou",
    "BD": "BeiDou",
    "GQ": "QZSS",
    "GI": "NavIC",
    "GN": "мульти-GNSS",
}
QUAL = {
    0: "нет сигнала",
    1: "поиск",
    2: "захвачен",
    3: "обнаружен, непригоден",
    4: "code lock",
    5: "code+carrier",
    6: "code+carrier",
    7: "code+carrier",
}
ASTATUS = {
    0: "INIT",
    1: "DONTKNOW",
    2: "OK",
    3: "SHORT (замыкание)",
    4: "OPEN (антенна не подключена)",
}


def hdr(title):
    print(f"\n{'=' * 62}\n{title}\n{'=' * 62}", flush=True)


# ---------------------------------------------------------------- порт/скорость


def find_ports():
    return sorted(glob.glob("/dev/ttyUSB*") + glob.glob("/dev/ttyACM*"))


def wait_for_port(timeout):
    end = time.time() + timeout
    shown = False
    while time.time() < end:
        p = find_ports()
        if p:
            return p
        if not shown:
            print(
                f"Жду появления порта (до {timeout} с)... подключите модуль", flush=True
            )
            shown = True
        time.sleep(0.5)
    return []


def detect_baud(port):
    """Возвращает (baud, sample) для скорости с максимальной долей ASCII."""
    best = (None, 0.0, b"")
    for br in BAUDS:
        try:
            with serial.Serial(port, br, timeout=0.6) as s:
                time.sleep(0.15)
                s.reset_input_buffer()
                time.sleep(1.2)
                data = s.read(s.in_waiting or 1)
        except Exception as e:
            print(f"  {br:>7}: недоступно ({e})", flush=True)
            continue
        if not data:
            print(f"  {br:>7}: тишина", flush=True)
            continue
        ratio = sum(1 for b in data if 32 <= b < 127 or b in (10, 13)) / len(data)
        tags = []
        if b"$" in data:
            tags.append("NMEA")
        if b"\xb5\x62" in data:
            tags.append("UBX")
        if b"\xd3" in data:
            tags.append("RTCM3?")
        if b"$@" in data:
            tags.append("SBF?")
        print(
            f"  {br:>7}: {len(data):>5} Б, ASCII {ratio * 100:5.1f}%  {' '.join(tags) or '-'}",
            flush=True,
        )
        if ratio > best[1]:
            best = (br, ratio, data)
    return best


# ---------------------------------------------------------------- UBX


class _ReadTimeout(Exception):
    """Внутреннее исключение при срабатывании жёсткого таймаута read()."""


def _alarm_handler(signum, frame):
    raise _ReadTimeout()


def _read_with_timeout(gnr, timeout):
    """Вызвать gnr.read() с жёстким таймаутом.

    GNSSReader.read() в этой версии pygnssutils на повторных вызовах может
    блокироваться дольше таймаута потока, поэтому страхуемся SIGALRM
    (код однопоточный, работает только в главном потоке).
    """
    if hasattr(signal, "SIGALRM"):
        old = signal.signal(signal.SIGALRM, _alarm_handler)
        signal.alarm(max(1, int(timeout) + 1))
        try:
            return gnr.read()
        finally:
            signal.alarm(0)
            signal.signal(signal.SIGALRM, old)
    return gnr.read()


def ubx_poll(stream, cls, mid, secs=3.0, poll_kwargs=None):
    """Послать UBX-POLL (cls,mid) и собрать ответные UBXMessage через UBXReader.

    Возвращает (msgs, port_error): msgs - список объектов UBXMessage,
    port_error=True только при РЕАЛЬНОЙ ошибке порта (исчез/не открылся),
    а не при тихом отсутствии ответа (модуль жив, но сообщение не
    поддерживается). Парсинг и контрольные суммы - задача pyubx2.

    Используется UBXReader (pyubx2), т.к. GNSSReader (pygnssutils) тихо
    отбрасывает класс CFG (0x06), необходимый для чтения конфигурации.

    poll_kwargs - дополнительные поля для POLL-сообщения. Например, для
    CFG-MSG (0x06/0x01) обязателен msgClass+msgID опрашиваемого сообщения,
    иначе модуль не ответит (пустой POLL он игнорирует/NAK-ает).
    """
    msgs = []
    port_error = False
    try:
        req = UBXMessage(cls, mid, POLL, **(poll_kwargs or {}))
        # protfilter=2 -> только UBX (без NMEA/RTCM), но ВСЕ классы UBX,
        # включая CFG/MON/NAV.
        gnr = UBXReader(stream, protfilter=2)
        # Небольшой таймаут потока: read() должен возвращать управление,
        # даже если SIGALRM по какой-то причине недоступен.
        try:
            stream.timeout = 1.0
        except Exception:
            pass
        stream.reset_input_buffer()
        gnr.datastream.write(req.serialize())
        end = time.time() + secs
        # UBXReader.read() может блокироваться дольше таймаута потока, поэтому
        # каждый вызов обёрнут в жёсткий таймаут. ВАЖНО: создаём НОВЫЙ
        # UBXReader на каждой итерации - он состояниелен и иначе "спотыкается"
        # о мусор/NMEA, оставшийся в буфере между опросами внутри detect().
        while time.time() < end:
            gnr = UBXReader(stream, protfilter=2)
            try:
                _, msg = _read_with_timeout(gnr, 2.0)
            except _ReadTimeout:
                # Превышен жёсткий таймаут одного read() - выходим из цикла.
                break
            except Exception:
                # кратковременный сбой чтения (обрыв порта) - фиксируем и выходим
                port_error = True
                break
            if msg is None:
                continue
            # pyubx2 даёт identity вида "MON-VER"; сопоставляем class/mid
            # через известный маппинг, чтобы не зависеть от формата строки.
            want = {
                (0x0A, 0x04): "MON-VER",
                (0x0A, 0x09): "MON-HW",
                (0x01, 0x35): "NAV-SAT",
                (0x0B, 0x31): "AID-EPH",
                (0x0B, 0x30): "AID-ALM",
            }.get((cls, mid))
            if want is None or getattr(msg, "identity", None) == want:
                msgs.append(msg)
    except Exception as e:
        port_error = True
        print(f"  ошибка обмена: {type(e).__name__}: {e}", flush=True)
    return msgs, port_error


def nmea_cmd(body):
    cs = 0
    for c in body.encode():
        cs ^= c
    return f"${body}*{cs:02X}\r\n".encode()


def identify_chipset(stream, baud):
    hdr("ОПРЕДЕЛЕНИЕ ЧИПСЕТА")
    # u-blox MON-VER (0x0A/0x04) - штатный UBX-запрос, парсит pyubx2
    r, _ = ubx_poll(stream, 0x0A, 0x04, 2.5)
    for m in r:
        sw = (
            (getattr(m, "swVersion", b"") or b"")
            .split(b"\x00")[0]
            .decode("ascii", "replace")
        )
        hw = (
            (getattr(m, "hwVersion", b"") or b"")
            .split(b"\x00")[0]
            .decode("ascii", "replace")
        )
        ext = [e for e in getattr(m, "extension", []) if e]
        gen = {
            "00040001": "u-blox 5",
            "00040007": "u-blox 6",
            "00070000": "u-blox 7",
            "00080000": "u-blox 8/M8",
            "00190000": "u-blox 9/F9",
            "000A0000": "u-blox 10",
        }.get(hw, "?")
        print(f"  u-blox: SW={sw}  HW={hw} -> {gen}", flush=True)
        for e in ext:
            print(f"    ext: {e}", flush=True)
        return "ublox"
    # u-blox в NMEA-режиме не ответит UBX MON-VER, но шлёт баннер "u-blox"
    # в GPTXT при старте. Ловим его, чтобы не спутать с другими чипами.
    try:
        buf = b""
        t = time.time()
        while time.time() - t < 3:
            buf += stream.read(512)
            if b"u-blox" in buf:
                break
        if b"u-blox" in buf:
            txt = buf.decode("ascii", "replace")
            print(f"  u-blox (по NMEA-баннеру): {txt[:80].strip()}", flush=True)
            return "ublox"
    except Exception:
        pass
    # прочие проприетарные запросы (через тот же stream)
    for name, cmd, needle in [
        ("MTK", nmea_cmd("PMTK605"), b"PMTK705"),
        # CASIC отвечает "PCAS01,..." - ищем именно префикс ответа, а не
        # эхо ошибки "PCAS inv format", которое шлёт, например, u-blox.
        ("CASIC/AT6558", nmea_cmd("PCAS06,0"), b"PCAS0"),
        ("Unicore", nmea_cmd("PDTINFO"), b"DTINFO"),
        ("Quectel", nmea_cmd("PQVERNO"), b"QVERNO"),
    ]:
        try:
            stream.reset_input_buffer()
            stream.write(cmd)
            stream.flush()
            time.sleep(1.6)
            data = stream.read(stream.in_waiting or 1)
            if needle in data:
                line = [ln for ln in data.split(b"\r\n") if needle in ln]
                print(f"  {name}: {line[0].decode('ascii', 'replace')}", flush=True)
                return name.lower()
        except Exception:
            pass
    print(
        "  не опознан (UBX MON-VER не ответил, проприетарные запросы тоже)", flush=True
    )
    return "unknown"


def ublox_hardware(stream):
    hdr("СОСТОЯНИЕ ВЧ-ТРАКТА (UBX MON-HW)")
    r, _ = ubx_poll(stream, 0x0A, 0x09, 2.5)
    for m in r:
        p = getattr(m, "payload", b"")
        if len(p) < 46:
            continue
        # Поля MON-HW: pyubx2 отдаёт часть как атрибуты, остальное - из payload.
        noise = getattr(m, "noisePerMS", int.from_bytes(p[16:18], "little"))
        agc = getattr(m, "agcCnt", int.from_bytes(p[18:20], "little"))
        ast = getattr(m, "aStatus", p[20])
        apow = getattr(m, "aPower", p[21])
        flags = p[22]
        jam = getattr(m, "jamInd", p[45])
        jstate = (flags >> 2) & 0x03
        print(f"  Антенна aStatus : {ast} -> {ASTATUS.get(ast, '?')}", flush=True)
        print(f"  aPower          : {apow} (0=off 1=on 2=unknown)", flush=True)
        print(
            f"  AGC             : {agc} / 8191  ({agc / 8191 * 100:.0f}% шкалы)",
            flush=True,
        )
        print(
            f"  noisePerMS      : {noise}   (справочно; шкала зависит от поколения,",
            flush=True,
        )
        print("                     сам по себе высокий шум не диагноз)", flush=True)
        if jstate == 0:
            print(
                f"  jamInd          : {jam} - НЕВАЛИДЕН (монитор ITFM выключен)",
                flush=True,
            )
        else:
            js = {1: "OK", 2: "WARNING", 3: "CRITICAL"}[jstate]
            print(f"  jamInd          : {jam}, jammingState={js}", flush=True)
        if ast == 4:
            print("  !! aStatus=OPEN - антенна не подключена", flush=True)
        if ast == 3:
            print("  !! aStatus=SHORT - замыкание в антенне или кабеле", flush=True)
        return
    print("  MON-HW не ответил", flush=True)


def ublox_navsat(stream):
    """
    UBX-NAV-SAT (M8+): флаги по каждому спутнику. Информативнее AID-EPH,
    который не отличает свежие данные от устаревших в BBR.
    Возвращает (locks, eph_count, used, poll_ok, unsupported).
    """
    hdr("СПУТНИКИ (UBX-NAV-SAT)")
    r, perr = ubx_poll(stream, 0x01, 0x35, 5)
    if not r:
        if perr:
            print("  NAV-SAT не ответил (обрыв порта).", flush=True)
            return None, None, None, False, False
        print(
            "  NAV-SAT не поддерживается этим модулем (нужен M8+/FW>=15).",
            flush=True,
        )
        return None, None, None, False, True
    for m in r:
        n = getattr(m, "numSvs", 0)
        locks = ephs = used = 0
        zenith = []  # (elev, cno) для спутников выше 60 градусов
        for i in range(1, n + 1):
            cno = getattr(m, f"cno_{i:02d}", 0) or 0
            elev = getattr(m, f"elev_{i:02d}", -91) or -91
            # pyubx2 раскрывает битовое поле flags спутника на отдельные
            # атрибуты: qualityInd (качество), ephAvail (эфемериды),
            # svUsed (используется в решении).
            qind = getattr(m, f"qualityInd_{i:02d}", 0) or 0
            eph_avail = getattr(m, f"ephAvail_{i:02d}", False) or False
            sv_used = getattr(m, f"svUsed_{i:02d}", False) or False
            if qind >= 4:  # qualityInd>=4 => code lock (см. описание NAV-SAT)
                locks += 1
            if eph_avail:
                ephs += 1
            if sv_used:
                used += 1
            if 60 <= elev <= 90:
                zenith.append((elev, cno))
        print(f"  Спутников в отчёте        : {n}", flush=True)
        print(f"  Каналов с CODE LOCK (q>=4): {locks}", flush=True)
        print(f"  С эфемеридами (ephAvail)  : {ephs}", flush=True)
        print(f"  Использовано в решении    : {used}", flush=True)
        if zenith:
            best = max(c for _, c in zenith)
            print(
                f"  Лучший C/N0 выше 60 град. : {best} dBHz "
                f"(на открытом небе ожидается 45-50)",
                flush=True,
            )
            if best and best < 35:
                print(
                    f"  !! Зенитный спутник всего {best} dBHz => ослабление ~"
                    f"{45 - best} dB.",
                    flush=True,
                )
                print(
                    "  !! Это приём через препятствие: крыша, потолок, стекло.",
                    flush=True,
                )
                print("  !! Нужен открытый обзор неба.", flush=True)
        return locks, ephs, used, True, False
    print("  NAV-SAT не ответил (модуль старше M8? / обрыв порта?)", flush=True)
    return None, None, None, False, False


def ublox_ephemeris(stream):
    """Решающий тест: декодировались ли навигационные сообщения.

    Опирается на уже полученный UBX-NAV-SAT (ephAvail/used) - это надёжный
    и не зависящий от поколения признак. Прямой опрос AID-EPH оставлен
    вторичным: на части модулей он приходит с битым checksum и pyubx2 его
    отбрасывает, поэтому на нём вердикт НЕ строим.

    Возвращает (eph_present, alm_present, poll_ok, unsupported).
    """
    hdr("ЭФЕМЕРИДЫ И АЛЬМАНАХ (по UBX-NAV-SAT ephAvail)")
    locks, ephc, used, nav_ok, nav_unsupported = ublox_navsat(stream)
    if nav_ok:
        print(
            f"  по NAV-SAT: code lock={locks}, эфемерид (ephAvail)={ephc}, "
            f"в решении={used}",
            flush=True,
        )
        return bool(ephc), False, True, False
    if nav_unsupported:
        print(
            "  NAV-SAT не поддерживается - эфемериды недоступны для оценки.", flush=True
        )
        return None, None, False, True
    # NAV-SAT не ответил (обрыв) - пытаемся AID-EPH как последний резерв
    print("  NAV-SAT не ответил - пробуем AID-EPH...", flush=True)
    r, perr = ubx_poll(stream, 0x0B, 0x31, 5)
    if not r:
        if perr:
            print("  AID-EPH не ответил (обрыв порта).", flush=True)
        else:
            print("  AID-EPH не поддерживается этим модулем.", flush=True)
        return None, None, False, not perr
    try:
        svids = getattr(r[0], "svid", []) or []
        svids = svids if isinstance(svids, (list, tuple)) else [svids]
        print(
            f"  AID-EPH: записей {len(svids)}, SV {svids[:8] or 'НИ ОДНОГО'}",
            flush=True,
        )
        return bool(svids), False, True, False
    except Exception as e:
        print(f"  AID-EPH: ошибка разбора {type(e).__name__}: {e}", flush=True)
        return None, None, False, False


# ---------------------------------------------------------------- NMEA


def nmea_survey(stream, secs=25):
    hdr(f"АНАЛИЗ NMEA-ПОТОКА ({secs} с)")
    sent, talk, const = {}, {}, set()
    epochs = []  # список словарей {prn: cno} по эпохам GSV
    cur = {}
    fix_q = nsat = hdop = None
    have_elev = False
    boots = 0  # повторы стартового баннера = перезагрузки
    total = 0
    gnr = GNSSReader(stream, protfilter=1)  # только NMEA
    try:
        t0 = time.time()
        while time.time() - t0 < secs:
            try:
                raw, msg = gnr.read()
            except Exception as e:
                print(f"  ошибка чтения: {type(e).__name__}: {e}", flush=True)
                break
            if raw:
                total += len(raw)
            if msg is None:
                continue
            ident = getattr(msg, "identity", "")
            tag = "G" + ident if ident else ""
            sent[tag] = sent.get(tag, 0) + 1
            tk = getattr(msg, "talker", "")
            if tk:
                talk[tk] = talk.get(tk, 0) + 1
                const.add(TALKERS.get(tk, tk))
            # GSV: видимые спутники и C/N0
            if ident in ("GPGSV", "GLGSV", "GAGSV", "GBGSV", "GNGSV", "GQGSV"):
                for i in range(1, 5):
                    svid = getattr(msg, f"svid_{i:02d}", None)
                    cno = getattr(msg, f"cno_{i:02d}", None)
                    elv = getattr(msg, f"elv_{i:02d}", None)
                    if svid is None or cno in (None, ""):
                        continue
                    try:
                        cno = int(cno)
                    except (TypeError, ValueError):
                        continue
                    cur[f"{tk}{svid}"] = cno
                    if elv not in (None, ""):
                        have_elev = True
            # RMC - одна на навигационную эпоху: надёжная граница эпохи
            if ident == "GNRMC":
                if cur:
                    epochs.append(dict(cur))
                    cur = {}
            if ident == "GNGGA":
                fix_q = getattr(msg, "quality", None)
                nsat = getattr(msg, "numSV", None)
                hdop = getattr(msg, "HDOP", None)
            # перезагрузки u-blox: баннер в GPTXT
            if ident == "GPTXT":
                txt = str(getattr(msg, "text", "") or "")
                if "u-blox" in txt or "ROM BASE" in txt:
                    boots += 1
    except Exception as e:
        print(f"  ошибка чтения: {type(e).__name__}: {e}", flush=True)

    print(
        f"  Поток          : {total} Б за {secs} с (~{total / secs:.0f} Б/с)",
        flush=True,
    )
    print(f"  Созвездия      : {', '.join(sorted(const)) or 'нет'}", flush=True)
    print(f"  Сообщения      : {dict(sorted(sent.items()))}", flush=True)
    print(
        f"  GGA fix        : quality={fix_q if fix_q is not None else '?'}  "
        f"спутников={nsat if nsat is not None else '?'}  "
        f"HDOP={hdop if hdop is not None else '?'}",
        flush=True,
    )
    print(
        f"  Elevation в GSV: {'ДА (альманах декодирован)' if have_elev else 'НЕТ (альманах не декодирован)'}",
        flush=True,
    )
    # boots делится на ~2, т.к. баннер содержит и "u-blox AG", и "ROM BASE"
    reboots = boots // 2
    if reboots > 1:
        print(
            f"\n  !! ПЕРЕЗАГРУЗОК ЗА ЗАМЕР: {reboots} (~{reboots / secs:.1f}/с)",
            flush=True,
        )
        print(
            "  !! Приёмник в цикле перезагрузки - он не доживает до захвата спутников.",
            flush=True,
        )
        print(
            "  !! Причина обычно в питании: слабый LDO адаптера, плохой кабель/разъём,",
            flush=True,
        )
        print(
            "  !! отсутствие конденсатора по VCC. Данные ниже недостоверны.", flush=True
        )
    # GGA quality: 0 = нет фикса, 1..n = фикс есть. None/"" = данных нет.
    # ВАЖНО: 0 - это валидное "нет фикса", а не отсутствие данных.
    if fix_q in (None, ""):
        fixed = False  # данных нет - считаем незафиксированным
    else:
        fixed = fix_q >= 1
    return epochs, fixed, have_elev, reboots


def cno_correlation(epochs):
    """
    Ключевой тест. У реальных спутников C/N0 независимы (разные высоты,
    трассы). У шума все каналы синхронно следуют за AGC/шумовой полкой.
    """
    hdr("ТЕСТ НЕЗАВИСИМОСТИ C/N0  (реальный сигнал vs шум)")
    if len(epochs) < 6:
        print(f"  недостаточно эпох GSV ({len(epochs)}) - тест не выполнен", flush=True)
        return None
    # спутники, присутствующие минимум в 80% эпох
    counts = {}
    for e in epochs:
        for sv in e:
            counts[sv] = counts.get(sv, 0) + 1
    stable = [sv for sv, c in counts.items() if c >= len(epochs) * 0.8]
    if len(stable) < 3:
        print(
            f"  устойчиво видимых спутников слишком мало ({len(stable)}) - тест не выполнен",
            flush=True,
        )
        return None
    series = {sv: [e[sv] for e in epochs if sv in e] for sv in stable}
    n = min(len(v) for v in series.values())
    series = {sv: v[:n] for sv, v in series.items()}
    means = [statistics.mean(series[sv][i] for sv in stable) for i in range(n)]

    def pearson(a, b):
        if len(a) < 3:
            return 0.0
        ma, mb = statistics.mean(a), statistics.mean(b)
        num = sum((x - ma) * (y - mb) for x, y in zip(a, b))
        da = sum((x - ma) ** 2 for x in a) ** 0.5
        db = sum((y - mb) ** 2 for y in b) ** 0.5
        return num / (da * db) if da and db else 0.0

    cors = {sv: pearson(series[sv], means) for sv in stable}
    med = statistics.median(cors.values())
    spreads = [max(e.values()) - min(e.values()) for e in epochs if len(e) > 2]
    spread = statistics.mean(spreads) if spreads else 0

    print(f"  Эпох GSV: {len(epochs)}, устойчивых спутников: {len(stable)}", flush=True)
    print(f"  Медианная корреляция C/N0 с общим средним: {med:.2f}", flush=True)
    print(f"  Средний разброс C/N0 внутри эпохи: {spread:.1f} dB", flush=True)
    for sv in sorted(cors, key=lambda x: -cors[x])[:6]:
        print(f"    {sv:>7}: r={cors[sv]:+.2f}  {series[sv][:8]}", flush=True)
    if med > 0.9 and spread < 12:
        print("\n  >>> ВСЕ каналы движутся синхронно при малом разбросе.", flush=True)
        print(
            "  >>> Это шумовая полка, а не спутники. Сигнала на входе НЕТ.", flush=True
        )
        return False
    print("\n  >>> C/N0 независимы - сигналы РЕАЛЬНЫЕ.", flush=True)
    return True


# ---------------------------------------------------------------- main


def main():
    ap = argparse.ArgumentParser(description="Диагностика GNSS-приёмника")
    ap.add_argument("--port", help="например /dev/ttyUSB0 (по умолчанию автопоиск)")
    ap.add_argument("--baud", type=int, help="скорость (по умолчанию автоопределение)")
    ap.add_argument("--wait", type=int, default=0, help="ждать появления порта, секунд")
    ap.add_argument("--secs", type=int, default=25, help="длительность анализа NMEA")
    a = ap.parse_args()

    hdr("ПОИСК УСТРОЙСТВА")
    if a.port:
        port = a.port
        if not os.path.exists(port):
            if a.wait:
                if not wait_for_port(a.wait):
                    sys.exit(f"Порт {port} не появился")
            else:
                sys.exit(f"Нет такого порта: {port}")
    else:
        ports = find_ports() or (wait_for_port(a.wait) if a.wait else [])
        if not ports:
            sys.exit(
                "Порты не найдены. Подключите модуль или укажите --port / --wait 60"
            )
        port = ports[0]
        if len(ports) > 1:
            print(f"  найдено несколько: {ports}, беру {port}", flush=True)
    print(f"  Порт: {port}", flush=True)
    st = os.stat(port)
    print(
        f"  Права: {oct(st.st_mode)[-3:]}  доступ на чтение/запись: "
        f"{os.access(port, os.R_OK | os.W_OK)}",
        flush=True,
    )

    if a.baud:
        baud, sample = a.baud, b""
    else:
        hdr("ОПРЕДЕЛЕНИЕ СКОРОСТИ")
        baud, ratio, sample = detect_baud(port)
        if baud is None:
            sys.exit("Данных нет ни на одной скорости. Проверьте питание и TX/RX.")
    print(f"\n  Выбрана скорость: {baud}", flush=True)
    if sample:
        print(f"  Образец: {sample[:120]}", flush=True)

    # Единый поток для всех опросов (GNSSReader принимает готовый datastream)
    try:
        with serial.Serial(port, baud, timeout=1) as stream:
            chip = identify_chipset(stream, baud)
            epochs, fixed, have_elev, reboots = nmea_survey(stream, a.secs)

            # при цикле перезагрузки остальные тесты бессмысленны
            if reboots > 1:
                hdr("ИТОГ")
                print(
                    f"  ЦИКЛ ПЕРЕЗАГРУЗКИ: ~{reboots / a.secs:.1f} сбросов в секунду.",
                    flush=True,
                )
                print(
                    "  Приёмник не успевает захватить спутники. Сначала лечим питание:",
                    flush=True,
                )
                print(
                    "   1. питать модуль от отдельного стабильного 3.3/5 В, с адаптером",
                    flush=True,
                )
                print("      разделить только GND и TX/RX", flush=True)
                print(
                    "   2. короткий качественный кабель, прямо в порт ПК, без хаба",
                    flush=True,
                )
                print("   3. конденсаторы 100 мкФ + 100 нФ по VCC модуля", flush=True)
                print(
                    "   4. проверить напряжение VCC мультиметром под нагрузкой",
                    flush=True,
                )
                print(flush=True)
                return

            real = cno_correlation(epochs)

            eph = None
            nsat = None
            poll_failed = False
            if chip == "ublox":
                ublox_hardware(stream)
                locks, ephc, used, nav_ok, nav_unsupported = ublox_navsat(stream)
                nsat = (locks, ephc, used)
                if not nav_ok and not nav_unsupported:
                    poll_failed = True
                if nsat is None or not nav_ok:
                    eph_present, alm_present, eph_ok, eph_unsupported = ublox_ephemeris(
                        stream
                    )
                    if eph_ok:
                        eph = (eph_present, alm_present)
                    elif not eph_unsupported:
                        poll_failed = True

            hdr("ИТОГ")
            have_eph = bool(eph and eph[0]) or bool(nsat and nsat[1])
            have_alm = bool(eph and eph[1])
            locks = nsat[0] if nsat else None
            if fixed:
                print("  ФИКС ЕСТЬ - приёмник работает нормально.", flush=True)
            elif have_eph:
                print(
                    "  Фикса нет, но эфемериды декодированы - сигнал РЕАЛЬНЫЙ.",
                    flush=True,
                )
                if nsat:
                    print(
                        f"  Code lock: {nsat[0]}, эфемериды: {nsat[1]}, в решении: {nsat[2]}.",
                        flush=True,
                    )
                print(
                    "  Для фикса нужно >=4 спутника, у которых эфемериды И устойчивый",
                    flush=True,
                )
                print(
                    "  сигнал одновременно. Если этого не происходит долго - сигнал",
                    flush=True,
                )
                print("  слишком слаб: выйдите на открытое небо.", flush=True)
            elif locks:
                print(
                    f"  Code lock есть на {locks} каналах, но эфемерид нет.", flush=True
                )
                print(
                    "  Сигнал реальный, но слабый для декодирования навсообщения",
                    flush=True,
                )
                print(
                    "  (нужно ~30 dBHz устойчиво). Нужен открытый обзор неба.",
                    flush=True,
                )
            elif have_alm or have_elev:
                print(
                    "  Фикса нет, но альманах декодирован (есть elevation/azimuth).",
                    flush=True,
                )
                print(
                    "  => Сигналы РЕАЛЬНЫЕ. Нужны эфемериды: 30 с на спутник при",
                    flush=True,
                )
                print("     открытом небе, до 12.5 мин на полный альманах.", flush=True)
            elif real is False:
                print(
                    "  Фикса нет. C/N0 всех каналов движутся синхронно, альманах не",
                    flush=True,
                )
                print(
                    "  декодирован и эфемерид нет => реального сигнала на входе НЕТ. Проверьте:",
                    flush=True,
                )
                print(
                    "   1. разъём антенны (U.FL защёлкнут до щелчка, pigtail целый)",
                    flush=True,
                )
                print("   2. активной антенне нужно питание смещения", flush=True)
                print(
                    "   3. керамический патч - плоскостью вверх, на металле ~5x5 см",
                    flush=True,
                )
                print(
                    "   4. выйти на открытое небо и ждать 5-15 мин (cold start)",
                    flush=True,
                )
            elif real is True:
                print(
                    "  Сигналы реальные (C/N0 независимы), фикса пока нет - нужно время.",
                    flush=True,
                )
            else:
                print(
                    "  ВЫВОД НЕ СДЕЛАН: применимые тесты не набрали данных.", flush=True
                )
                print(
                    f"  Диагностика: эпох GSV={len(epochs)}, elevation={have_elev}, "
                    f"эфемериды={have_eph}, альманах={have_alm}",
                    flush=True,
                )
                print(
                    "  Увеличьте --secs (например --secs 60) и повторите.", flush=True
                )
            if poll_failed:
                print(
                    "  !! ЧАСТЬ UBX-ОПРОСОВ НЕ СОСТОЯЛАСЬ (обрыв порта) - вывод об",
                    flush=True,
                )
                print("     эфемеридах/альманахе может быть неполным.", flush=True)
            print(flush=True)
    except serial.SerialException as e:
        sys.exit(f"Ошибка порта {port}: {e}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nпрервано", flush=True)
