from __future__ import annotations

from threading import Thread
from typing import Any
from typing import Callable

from panel import logger


def run(function: Callable, *args: Any) -> Thread:
    """Creates a new thread and automatically runs `function` in it.

    Args:
        function (Callable): The function to run in a new thread.

    Returns:
        Thread: The thread object created.
    """
    t = Thread(
        target=function,
        args=args,
    )
    t.start()
    logger.debug(f"Created and started a new thread for {function.__name__}")
    return t
