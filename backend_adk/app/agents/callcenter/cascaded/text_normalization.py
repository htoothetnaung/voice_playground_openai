"""Expands money, dates, phone numbers, and long digit sequences into speech-friendly text."""

from __future__ import annotations

import re
from datetime import date


_MONTHS = {
    1: "January",
    2: "February",
    3: "March",
    4: "April",
    5: "May",
    6: "June",
    7: "July",
    8: "August",
    9: "September",
    10: "October",
    11: "November",
    12: "December",
}


def normalize_for_tts(text: str) -> str:
    """Make common call-center numerics easier for low-latency TTS models."""
    text = re.sub(r"\$(\d+(?:\.\d{1,2})?)", _money_replacement, text)
    text = re.sub(r"\b(\d{4})-(\d{2})-(\d{2})\b", _date_replacement, text)
    text = re.sub(r"\b(\d{3})[-.](\d{3})[-.](\d{4})\b", _phone_replacement, text)
    text = re.sub(r"\b(\d{4,})\b", _digit_sequence_replacement, text)
    return text


def _money_replacement(match: re.Match[str]) -> str:
    """Expand dollar amounts into words for clearer TTS pronunciation."""
    amount = match.group(1)
    if "." in amount:
        dollars, cents = amount.split(".", 1)
        cents = cents.ljust(2, "0")
        return f"{dollars} dollars and {cents} cents"
    return f"{amount} dollars"


def _date_replacement(match: re.Match[str]) -> str:
    """Expand ISO-like dates into month-day-year phrasing when the date is valid."""
    year = int(match.group(1))
    month = int(match.group(2))
    day = int(match.group(3))
    try:
        date(year, month, day)
    except ValueError:
        return match.group(0)
    return f"{_MONTHS[month]} {day}, {year}"


def _phone_replacement(match: re.Match[str]) -> str:
    """Separate phone number digits for speech synthesis."""
    return " ".join(" ".join(group) for group in match.groups())


def _digit_sequence_replacement(match: re.Match[str]) -> str:
    """Spell out long digit sequences while preserving likely year values."""
    value = match.group(1)
    if len(value) == 4 and value.startswith("20"):
        return value
    return " ".join(value)

