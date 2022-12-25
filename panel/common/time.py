from __future__ import annotations

import datetime

from panel.config import config


def timestamp_as_date(timestamp: int, exclude_date: bool = True) -> str:
    """Converts timestamps into readable time."""
    date = datetime.datetime.fromtimestamp(timestamp)  # converting into datetime object
    date += datetime.timedelta(
        hours=config.app_time_offset,
    )  # adding timezone offset to current time

    if exclude_date:
        return date.strftime("%H:%M")

    return date.strftime("%H:%M %d/%m/%Y")
