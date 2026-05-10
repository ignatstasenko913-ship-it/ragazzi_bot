"""Input validation helpers."""
from __future__ import annotations

import re
from typing import Optional

import phonenumbers


def normalize_phone(raw: str) -> str:
    """Normalize a Russian phone number to +7 (XXX) XXX-XX-XX format."""
    try:
        parsed = phonenumbers.parse(raw, "RU")
        if phonenumbers.is_valid_number(parsed):
            return phonenumbers.format_number(
                parsed, phonenumbers.PhoneNumberFormat.INTERNATIONAL
            )
    except Exception:
        pass
    digits = re.sub(r"\D", "", raw)
    if len(digits) == 11 and digits.startswith(("7", "8")):
        d = digits[1:]
        return f"+7 ({d[:3]}) {d[3:6]}-{d[6:8]}-{d[8:]}"
    if len(digits) == 10:
        return f"+7 ({digits[:3]}) {digits[3:6]}-{digits[6:8]}-{digits[8:]}"
    return raw


def is_valid_order_number(value: str) -> bool:
    return bool(re.match(r"^\d{5,12}$", value.strip()))


def is_suspicious_address(address: str) -> bool:
    """Heuristic: flag addresses that look wrong for Vladivostok."""
    suspicious_patterns = [
        r"уссурийск",
        r"находка",
        r"арсеньев",
        r"партизанск",
        r"спасск",
        r"дальнереченск",
        r"лесозаводск",
        r"хабаровск",
        r"москва",
        r"санкт-петербург",
    ]
    low = address.lower()
    for pat in suspicious_patterns:
        if re.search(pat, low):
            return True
    return False
