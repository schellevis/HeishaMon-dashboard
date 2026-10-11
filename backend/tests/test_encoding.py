import json

import pytest

from heishamon_dashboard.encoding import EncodingError, check_type, encode


def code(type_, value):
    with pytest.raises(EncodingError) as e:
        encode(type_, value)
    return e.value.code


def test_dec1_pool_temp():
    assert encode("dec1", 20.5) == "20.5"
    assert encode("dec1", 20) == "20.0"
    assert encode("dec1", -3) == "-3.0"
    assert encode("dec1", -0.5) == "-0.5"
    assert encode("dec1", 0.0) == "0.0"
    assert code("dec1", 20.25) == "bad_type"


def test_dec1_rejects_non_numbers_and_non_finite():
    for bad in (True, "20.5", None, float("nan"), float("inf"), [1]):
        assert code("dec1", bad) == "bad_type"


def test_int_types_reject_floats_and_bools():
    assert code("int", 2.0) == "bad_type"  # SetDHWTemp 2.0
    assert code("bool", True) == "bad_type"
    assert code("int", "5") == "bad_type"
    assert encode("int", 45) == "45"
    assert encode("int", -5) == "-5"
    assert encode("bool", 1) == "1"


def test_int2_zero_padded_int12_not():
    assert encode("int2", 55) == "55"  # SetSterilizationTemp
    assert encode("int2", 5) == "05"
    assert encode("int12", 5) == "5"  # SetSterilizationMaxTime
    assert encode("int12", 60) == "60"


def test_dec3_s0_total():
    assert encode("dec3", 123456.789) == "123456.789"
    assert encode("dec3", 5000) == "5000"
    assert encode("dec3", 5000.0) == "5000"
    assert encode("dec3", 0.5) == "0.5"
    assert encode("dec3", 1e6) == "1000000"
    assert code("dec3", 1.2345) == "bad_type"


def test_json_compact():
    value = {"zone1": {"heat": {"target": {"high": 35, "low": 25}}}}
    assert encode("json", value) == '{"zone1":{"heat":{"target":{"high":35,"low":25}}}}'
    assert json.loads(encode("json", value)) == value
    assert code("json", [1]) == "bad_type"


def test_unknown_type():
    assert code("nope", 1) == "bad_type"


def test_check_type_returns_decimal():
    assert str(check_type("dec1", 20.5)) == "20.5"
