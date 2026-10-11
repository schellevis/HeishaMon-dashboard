"""Value validation and MQTT payload encoding (spec §4.4 "Value encoding", Appendix A.2)."""
import json
import math
from decimal import Decimal, InvalidOperation

INT_TYPES = ("int", "bool", "int2", "int12")


class EncodingError(ValueError):
    """A value that has the wrong JSON type or shape. `code` is an Error code (§4.4)."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def to_decimal(value) -> Decimal:
    """Exact decimal of a JSON number (shortest repr for floats). Raises `bad_type`."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise EncodingError("bad_type", "a number is required")
    if isinstance(value, float) and not math.isfinite(value):
        raise EncodingError("bad_type", "the number must be finite")
    try:
        return Decimal(repr(value))
    except InvalidOperation:  # pragma: no cover - repr of a finite float always parses
        raise EncodingError("bad_type", "not a number") from None


def check_type(type_: str, value) -> Decimal | dict:
    """Validate the JSON type of `value` for a payload type; return its numeric/structural form."""
    if type_ == "json":
        if not isinstance(value, dict):
            raise EncodingError("bad_type", "an object is required")
        return value
    if type_ in INT_TYPES:
        if isinstance(value, bool) or not isinstance(value, int):
            raise EncodingError("bad_type", "an integer literal is required")
        return Decimal(value)
    if type_ == "dec1":
        d = to_decimal(value)
        if d != d.quantize(Decimal("0.1")):
            raise EncodingError("bad_type", "at most one fractional digit is allowed")
        return d
    if type_ == "dec3":
        d = to_decimal(value)
        if d != d.quantize(Decimal("0.001")):
            raise EncodingError("bad_type", "at most three fractional digits are allowed")
        return d
    raise EncodingError("bad_type", f"unknown payload type {type_!r}")


def _plain(d: Decimal, places: int, strip: bool) -> str:
    text = format(d.quantize(Decimal(1).scaleb(-places)), "f")
    if strip and "." in text:
        text = text.rstrip("0").rstrip(".")
    if text in ("-0", "-0.0"):
        text = text.lstrip("-")
    return text


def encode(type_: str, value) -> str:
    """The exact MQTT payload text for a value of the given payload type."""
    checked = check_type(type_, value)
    if type_ == "json":
        return json.dumps(checked, separators=(",", ":"), ensure_ascii=False)
    if type_ == "int2":
        return f"{int(checked):02d}" if checked >= 0 else str(int(checked))
    if type_ in INT_TYPES:
        return str(int(checked))
    if type_ == "dec1":
        return _plain(checked, 1, strip=False)
    return _plain(checked, 3, strip=True)  # dec3
