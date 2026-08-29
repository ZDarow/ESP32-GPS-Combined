import sys
import os

# Добавляем путь к tools/ble_receiver для импорта
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'tools', 'ble_receiver'))

from nmea_parser import validate_checksum, parse_rmc


def test_validate_checksum_valid():
    sentence = "$GPRMC,120000,A,4807.038,N,01131.000,E,0.0,0.0,010124,,,A*77"
    assert validate_checksum(sentence) is True


def test_validate_checksum_invalid():
    sentence = "$GPRMC,120000,A,4807.038,N,01131.000,E,0.0,0.0,010124,,,A*00"
    assert validate_checksum(sentence) is False


def test_validate_checksum_no_checksum():
    sentence = "$GPRMC,120000,A,4807.038,N,01131.000,E,0.0,0.0,010124,,,A"
    assert validate_checksum(sentence) is False


def test_validate_checksum_missing_dollar():
    sentence = "GPRMC,120000,A,4807.038,N,01131.000,E,0.0,0.0,010124,,,A*77"
    assert validate_checksum(sentence) is False


def test_validate_checksum_with_crlf():
    sentence = "$GPRMC,120000,A,4807.038,N,01131.000,E,0.0,0.0,010124,,,A*77\r\n"
    assert validate_checksum(sentence) is True


def test_parse_rmc_valid():
    sentence = "$GPRMC,120000,A,4807.038,N,01131.000,E,0.0,0.0,010124,,,A*77"
    result = parse_rmc(sentence)
    assert result is not None
    assert result["valid"] is True
    assert abs(result["lat"] - 48.1173) < 1e-4
    assert abs(result["lon"] - 11.516666666666667) < 1e-4
    assert result["speed_kmh"] == 0.0
    assert result["course"] == 0.0


def test_parse_rmc_no_fix():
    sentence = "$GPRMC,120000,V,4807.038,N,01131.000,E,0.0,0.0,010124,,,A*77"
    result = parse_rmc(sentence)
    assert result is None


def test_parse_rmc_invalid_checksum():
    sentence = "$GPRMC,120000,A,4807.038,N,01131.000,E,0.0,0.0,010124,,,A*00"
    result = parse_rmc(sentence)
    assert result is None


def test_parse_rmc_wrong_type():
    sentence = "$GPGGA,120000,4807.038,N,01131.000,E,1,08,0.9,545.4,M,46.9,M,,*47"
    result = parse_rmc(sentence)
    assert result is None


if __name__ == "__main__":
    pytest = sys.argv[1] if len(sys.argv) > 1 else "pytest"
    os.system(f"{pytest} {__file__} -v")
