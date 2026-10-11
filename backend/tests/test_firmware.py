import pytest

from heishamon_dashboard.firmware import parse_firmware

CASES = [
    ("3.2.3", ((3, 2, 3), False)),
    ("3.2.4-beta-2", ((3, 2, 4), False)),
    ("3.9", ((3, 9, 0), False)),
    ("4.0", ((4, 0, 0), False)),
    ("3.61", ((3, 6, 1), False)),
    ("v4.2.3", ((4, 2, 3), False)),
    ("Local build", ((3, 2, 3), True)),
    ("Alpha-abc1234", ((3, 2, 3), True)),
    (None, ((3, 2, 3), True)),
    ("", ((3, 2, 3), True)),
]


@pytest.mark.parametrize("version,expected", CASES)
def test_parse_firmware(version, expected):
    assert parse_firmware(version) == expected
