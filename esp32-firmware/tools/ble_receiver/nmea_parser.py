def validate_checksum(sentence: str) -> bool:
    if "*" not in sentence:
        return False
    data_part, checksum_hex = sentence.split("*", 1)
    if not data_part.startswith("$"):
        return False
    data_bytes = data_part[1:].encode("ascii")
    checksum = 0
    for b in data_bytes:
        checksum ^= b
    return checksum == int(checksum_hex.strip(), 16)


def _convert_to_decimal(raw: str, hemisphere: str) -> float:
    if not raw:
        return 0.0
    raw = raw.strip()
    if len(raw) < 3:
        return 0.0
    if hemisphere in ("N", "S"):
        degrees = int(raw[:2])
        minutes = float(raw[2:])
    else:
        degrees = int(raw[:3])
        minutes = float(raw[3:])
    decimal = degrees + minutes / 60.0
    if hemisphere in ("S", "W"):
        decimal = -decimal
    return decimal


def parse_rmc(sentence: str) -> dict:
    if not validate_checksum(sentence):
        return None
    parts = sentence.split(",")
    if len(parts) < 12 or parts[0].strip() not in ("$GPRMC", "$GNRMC"):
        return None
    status = parts[2].strip()
    if status != "A":
        return None
    utc_time = parts[1].strip()
    lat = _convert_to_decimal(parts[3], parts[4])
    lon = _convert_to_decimal(parts[5], parts[6])
    speed_knots = float(parts[7].strip()) if parts[7].strip() else 0.0
    speed_kmh = speed_knots * 1.852
    course = float(parts[8].strip()) if parts[8].strip() else 0.0
    return {
        "utc_time": utc_time,
        "lat": lat,
        "lon": lon,
        "speed_kmh": speed_kmh,
        "course": course,
        "valid": True,
    }
