"""Firmware version parsing (spec Appendix A.1)."""
import re

ASSUMED = (3, 2, 3)

_VERSION = re.compile(r"^(\d+)\.(\d+)(?:\.(\d+))?")


def parse_firmware(version: str | None) -> tuple[tuple[int, int, int], bool]:
    """Spec Appendix A.1 rule. Returns ((major, minor, patch), assumed); assumed=True -> (3,2,3)."""
    if not version:
        return ASSUMED, True
    text = version.strip()
    if text.startswith("v"):
        text = text[1:]
    m = _VERSION.match(text)
    if not m:
        return ASSUMED, True
    major, minor_s, patch_s = m.group(1), m.group(2), m.group(3)
    if patch_s is None:
        if len(minor_s) == 2 and minor_s[0] != "0":
            return (int(major), int(minor_s[0]), int(minor_s[1])), False
        return (int(major), int(minor_s), 0), False
    return (int(major), int(minor_s), int(patch_s)), False
