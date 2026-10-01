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
        self.source, self.refresh_seconds = source, refresh_seconds
        self.clock = clock or (lambda: datetime.now().astimezone())
        self._lock = threading.Lock()
        self._loaded_at = 0.0
        self.total_all = self.total_source = self.today_source = 0.0
        self._url = url
        self._conn = None
        self._pending = 0.0  # spend not yet written because the database was unreachable; flushed first next time
        self._ready = False  # totals have been read at least once; until then the caller must stay closed
        try:
            self.refresh(force=True)
        except LedgerError:
            pass  # unreachable at start-up: every check raises (budget closed) until a read succeeds

    def _execute(self, sql: str, params: tuple = ()) -> object:
        """Run one statement; on a broken connection reconnect once. Callers hold the lock."""
        import psycopg

        for attempt in (1, 2):
            try:
                if self._conn is None or self._conn.closed:
                    self._conn = psycopg.connect(self._url, autocommit=True, connect_timeout=10)
                return self._conn.execute(sql, params)
            except Exception as e:  # noqa: BLE001 - any failure is reported, the caller fails closed
                try:
                    if self._conn is not None:
                        self._conn.close()
                except Exception:  # noqa: BLE001
                    pass
                self._conn = None
                if attempt == 2:
                    raise LedgerError(str(e)) from e
        raise AssertionError("unreachable")

    def _upsert(self, usd: float) -> None:
        self._execute(
            "INSERT INTO llm_spend (day, source, usd) VALUES (%s, %s, %s) "
            "ON CONFLICT (day, source) DO UPDATE SET usd = llm_spend.usd + EXCLUDED.usd",
            (self._today(), self.source, usd),
        )

    def _today(self) -> str:
        return self.clock().date().isoformat()

    def refresh(self, force: bool = False) -> None:
        with self._lock:
            if not force and time.monotonic() - self._loaded_at < self.refresh_seconds:
                return
            if not self._ready:
                self._execute("CREATE TABLE IF NOT EXISTS llm_spend (day date NOT NULL, source text NOT NULL, "
                              "usd double precision NOT NULL DEFAULT 0, PRIMARY KEY (day, source))")
            if self._pending:
                self._upsert(self._pending)
                self._pending = 0.0
            row = self._execute(
                "SELECT COALESCE(SUM(usd), 0), COALESCE(SUM(usd) FILTER (WHERE source = %s), 0), "
                "COALESCE(SUM(usd) FILTER (WHERE source = %s AND day = %s), 0) FROM llm_spend",
                (self.source, self.source, self._today()),
            ).fetchone()
            self.total_all, self.total_source, self.today_source = (float(x) for x in row)
            self._loaded_at, self._ready = time.monotonic(), True

    def add(self, usd: float) -> None:
        with self._lock:
            self.total_all += usd  # counted locally even if the write fails, so the caps still see it
            self.total_source += usd
            self.today_source += usd
            try:
                self._upsert(self._pending + usd)
                self._pending = 0.0
            except LedgerError:
                self._pending += usd
                raise
