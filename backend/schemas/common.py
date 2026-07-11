from datetime import date, datetime
from typing import Annotated

from pydantic import PlainSerializer

from utils.dates import format_date_dmy_month_abbr


def _serialize_ist_date(value: datetime | date | None) -> str | None:
    return format_date_dmy_month_abbr(value)


ISTDateStr = Annotated[datetime, PlainSerializer(_serialize_ist_date, return_type=str)]
ISTDateStrOptional = Annotated[
    datetime | None,
    PlainSerializer(_serialize_ist_date, return_type=str | None),
]
ISTCalendarDateStr = Annotated[date, PlainSerializer(_serialize_ist_date, return_type=str)]
ISTCalendarDateStrOptional = Annotated[
    date | None,
    PlainSerializer(_serialize_ist_date, return_type=str | None),
]
