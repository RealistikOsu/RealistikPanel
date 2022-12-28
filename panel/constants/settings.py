from __future__ import annotations

from enum import IntEnum


class PanelTheme(IntEnum):
    LIGHT = 1
    DARK = 2

    def __str__(self) -> str:
        if self is PanelTheme.LIGHT:
            return "light"
        else:
            return "dark"
