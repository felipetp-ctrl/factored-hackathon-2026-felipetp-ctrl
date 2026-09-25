from __future__ import annotations

import time
from collections.abc import Callable
from typing import TypeVar

from dispute_ops.errors import ToolUnavailable

T = TypeVar("T")


def call_with_retry(
    fn: Callable[[], T],
    *,
    retries: int = 2,
    base_delay: float = 0.2,
    sleep: Callable[[float], None] = time.sleep,
    retry_on: tuple[type[Exception], ...] = (ToolUnavailable,),
) -> T:
    """Bounded retry with exponential backoff. Re-raises after `retries` extra attempts."""
    for attempt in range(retries + 1):
        try:
            return fn()
        except retry_on:
            if attempt == retries:
                raise
            sleep(base_delay * 2**attempt)
    raise AssertionError("unreachable")
