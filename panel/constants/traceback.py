from __future__ import annotations

from enum import IntEnum


class TracebackType(IntEnum):
    PRIMARY = 1
    WARNING = 2
    DANGER = 3