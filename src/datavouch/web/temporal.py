"""Explicit UTC calendar conversion shared by web forms."""

import re
from datetime import UTC, datetime


def picker_timestamp(value: str, label: str) -> str:
    """Interpret explicit UTC calendar selections without using the host time zone."""
    if not re.fullmatch(
        r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}(?::[0-9]{2}(?:\.[0-9]{1,3})?)?", value
    ):
        raise ValueError(f"{label}: select a UTC date and time (up to milliseconds).")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{label}: select a valid UTC date and time.") from exc
    return parsed.replace(tzinfo=UTC).isoformat().replace("+00:00", "Z")
