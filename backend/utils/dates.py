from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Union

MONTH_ABBR: tuple[str, ...] = ("", "JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC")

IST = timezone(timedelta(hours=5, minutes=30))

DateInput = Union[datetime, date, str, int, float]


def ist_now() -> datetime:
    """Current time in IST for DB inserts and updates."""
    return datetime.now(IST)


def to_ist(value: datetime) -> datetime:
    """Convert an aware or naive UTC datetime to IST."""
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(IST)


def parse_date_dmy_month_abbr(value: str) -> date:
    """Parse 'DD/MON/YYYY' date strings from the frontend."""
    try:
        return datetime.strptime(value.strip().upper(), "%d/%b/%Y").date()
    except Exception as exc:
        raise ValueError(f"Cannot parse date value: {value!r}") from exc


def parse_event_date(value: str) -> date:
    """Parse event date strings in 'YYYY/MM/DD' format (e.g. '2026/06/26')."""
    try:
        return datetime.strptime(value.strip(), "%Y/%m/%d").date()
    except Exception as exc:
        raise ValueError(f"Cannot parse event date value: {value!r}") from exc


def format_event_date(value: date | None) -> str | None:
    """Format a date as 'YYYY/MM/DD' for event APIs."""
    if value is None:
        return None
    return value.strftime("%Y/%m/%d")


def parse_event_date_range(value: list[str] | tuple[str, str] | None) -> tuple[date | None, date | None]:
    """Convert FE event_dates ['YYYY/MM/DD', 'YYYY/MM/DD'] into DB dates."""
    if value is None:
        return None, None
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        raise ValueError("event_dates must be an array with start and end dates")
    return parse_event_date(value[0]), parse_event_date(value[1])


def format_event_date_range(event_start: date | None, event_end: date | None) -> list[str] | None:
    """Convert DB event_start/event_end dates into FE event_dates array."""
    if event_start is None and event_end is None:
        return None
    return [
        format_event_date(event_start),
        format_event_date(event_end),
    ]


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
        d = to_ist(value).date()
    elif isinstance(value, date):
        d = value
    elif isinstance(value, (int, float)):
        d = to_ist(datetime.fromtimestamp(value, tz=timezone.utc)).date()
    elif isinstance(value, str):
        # Try ISO 8601 first
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            d = to_ist(parsed).date() if isinstance(parsed, datetime) else parsed.date()
        except Exception:
            # Fallback to common day/month/year patterns
            from datetime import datetime as _dt

            patterns = [
                "%d/%b/%Y",
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

