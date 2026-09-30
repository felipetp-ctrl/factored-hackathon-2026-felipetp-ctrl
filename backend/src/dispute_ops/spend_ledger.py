"""Durable model-spend ledger shared by every process that spends the project's API credit (ADR-026).

The deployed demo and the team's evaluation runs write to the same Postgres table, one row per day and source, so the
caps survive restarts and deploys and one ceiling covers both. Any database error fails closed: the caller treats the
budget as exhausted and the free reader takes over."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from datetime import datetime

SOURCES = ("demo", "eval")


class LedgerError(RuntimeError):
    pass


class SpendLedger:
    def __init__(self, url: str, source: str, *, refresh_seconds: float = 20.0,
                 clock: Callable[[], datetime] | None = None) -> None:
        if source not in SOURCES:
            raise ValueError(f"unknown ledger source {source!r}")
        import psycopg

        self.source, self.refresh_seconds = source, refresh_seconds
        self.clock = clock or (lambda: datetime.now().astimezone())
        self._lock = threading.Lock()
        self._loaded_at = 0.0
        self.total_all = self.total_source = self.today_source = 0.0
        try:
            self._conn = psycopg.connect(url, autocommit=True, connect_timeout=10)
            self._conn.execute(
                "CREATE TABLE IF NOT EXISTS llm_spend (day date NOT NULL, source text NOT NULL, "
                "usd double precision NOT NULL DEFAULT 0, PRIMARY KEY (day, source))"
            )
        except Exception as e:  # noqa: BLE001 - any failure closes the budget
            raise LedgerError(str(e)) from e
        self.refresh(force=True)

    def _today(self) -> str:
        return self.clock().date().isoformat()

    def refresh(self, force: bool = False) -> None:
        with self._lock:
            if not force and time.monotonic() - self._loaded_at < self.refresh_seconds:
                return
            try:
                row = self._conn.execute(
                    "SELECT COALESCE(SUM(usd), 0), COALESCE(SUM(usd) FILTER (WHERE source = %s), 0), "
                    "COALESCE(SUM(usd) FILTER (WHERE source = %s AND day = %s), 0) FROM llm_spend",
                    (self.source, self.source, self._today()),
                ).fetchone()
            except Exception as e:  # noqa: BLE001
                raise LedgerError(str(e)) from e
            self.total_all, self.total_source, self.today_source = (float(x) for x in row)
            self._loaded_at = time.monotonic()

    def add(self, usd: float) -> None:
        with self._lock:
            try:
                self._conn.execute(
                    "INSERT INTO llm_spend (day, source, usd) VALUES (%s, %s, %s) "
                    "ON CONFLICT (day, source) DO UPDATE SET usd = llm_spend.usd + EXCLUDED.usd",
                    (self._today(), self.source, usd),
                )
            except Exception as e:  # noqa: BLE001
                raise LedgerError(str(e)) from e
            self.total_all += usd
            self.total_source += usd
            self.today_source += usd
