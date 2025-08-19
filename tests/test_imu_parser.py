import pytest

from src.hardware.plugin_system import IMUPlugin


@pytest.mark.parametrize(
    "line,expected_len",
    [
        ("1.0, -2.0, 3.0, 0.1, 0.2, 0.3, -0.4, 0.5, -0.6", 10),
        ("0.01,0.02,0.03, -1.0, 2.0, -3.0", 10),
        ("-10, 5, 0", 10),
    ],
)
def test_parse_imu_line(line, expected_len):
    parsed = IMUPlugin._parse_imu_line(line)
    assert parsed is not None
    assert isinstance(parsed, tuple)
    assert len(parsed) == expected_len
    # Quality is last element, in [0,1]
    q = parsed[-1]
    assert 0.0 <= q <= 1.0


def test_parse_invalid_line_returns_none():
    assert IMUPlugin._parse_imu_line("abc,def,ghi") is None
