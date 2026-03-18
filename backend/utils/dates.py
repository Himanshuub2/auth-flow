from __future__ import annotations

from datetime import date, datetime
from typing import Union

MONTH_ABBR: tuple[str, ...] = ("", "JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC")

DateInput = Union[datetime, date, str, int, float]


def format_date_dmy_month_abbr(value: DateInput | None) -> str | None:
    """
    Convert various date-like inputs into 'DD/MON/YYYY' (e.g. '05/MAR/2024').

    Returns None if value is falsy.
    Raises ValueError if the value cannot be interpreted as a date.
    """
    if not value:
        return None

    d: date

    if isinstance(value, datetime):
        d = value.date()
    elif isinstance(value, date):
        d = value
    elif isinstance(value, (int, float)):
        d = datetime.fromtimestamp(value).date()
    elif isinstance(value, str):
        # Try ISO 8601 first
        try:
            d = datetime.fromisoformat(value).date()
        except Exception:
            # Fallback to common day/month/year patterns
            from datetime import datetime as _dt

            patterns = [
                "%d/%m/%Y",
                "%m/%d/%Y",
                "%Y-%m-%d",
                "%d-%m-%Y",
                "%d.%m.%Y",
            ]
            for p in patterns:
                try:
                    d = _dt.strptime(value, p).date()
                    break
                except Exception:
                    continue
            else:
                raise ValueError(f"Cannot parse date value: {value!r}")
    else:
        raise ValueError(f"Unsupported date type: {type(value)!r}")

    return f"{d.day:02d}/{MONTH_ABBR[d.month]}/{d.year:04d}"

