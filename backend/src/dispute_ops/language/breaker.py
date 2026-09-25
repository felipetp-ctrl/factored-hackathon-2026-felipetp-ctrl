from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta


class CircuitBreaker:
    """Stops calling a failing dependency for `reset_seconds` after `failure_threshold`
    consecutive failures, then lets one probe through (half-open)."""

    def __init__(self, *, failure_threshold: int, reset_seconds: float, clock: Callable[[], datetime]) -> None:
        self.failure_threshold = failure_threshold
        self.reset = timedelta(seconds=reset_seconds)
        self.clock = clock
        self.failures = 0
        self.opened_at: datetime | None = None

    def allow(self) -> bool:
        if self.opened_at is None:
            return True
        return self.clock() - self.opened_at >= self.reset

    def record_success(self) -> None:
        self.failures = 0
        self.opened_at = None

    def record_failure(self) -> None:
        self.failures += 1
        if self.failures >= self.failure_threshold:
            self.opened_at = self.clock()
