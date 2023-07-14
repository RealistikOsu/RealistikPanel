# TODO: Rename
from __future__ import annotations

from typing import Optional
from typing import TypeVar

T = TypeVar("T")


def decode_int_or(value: Optional[bytes], default: int = 0) -> int:
    """Decodes a byte stream and casts it to an int or returns a default value if `value`
    is `None`."""

    if value is None:
        return default

    return int(value.decode("utf-8"))


def halve_list(_input: list[T]) -> tuple[list[T], list[T]]:
    return (
        _input[::2],
        _input[1::2],
    )
