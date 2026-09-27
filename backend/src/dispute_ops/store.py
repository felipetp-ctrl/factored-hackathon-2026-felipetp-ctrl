from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from dispute_ops.domain import AuditEvent, Card, Customer, DisputeCase, Transaction

SCHEMA = """
CREATE TABLE IF NOT EXISTS customers (
    customer_id TEXT PRIMARY KEY, country TEXT NOT NULL, segment TEXT NOT NULL,
    is_repeat_complainer INTEGER NOT NULL, first_name TEXT);
CREATE TABLE IF NOT EXISTS products (
    product_id TEXT PRIMARY KEY, customer_id TEXT NOT NULL REFERENCES customers,
    product_type TEXT NOT NULL, product_status TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS transactions (
    transaction_id TEXT PRIMARY KEY, customer_id TEXT NOT NULL REFERENCES customers,
    product_id TEXT NOT NULL REFERENCES products, transaction_date TEXT NOT NULL,
    amount TEXT NOT NULL, currency TEXT NOT NULL, amount_usd TEXT NOT NULL, merchant_name TEXT,
    transaction_status TEXT NOT NULL, transaction_country TEXT NOT NULL, fraud_score TEXT);
CREATE TABLE IF NOT EXISTS disputes (
    case_id TEXT PRIMARY KEY, customer_id TEXT NOT NULL, transaction_id TEXT NOT NULL,
    reason_code TEXT NOT NULL, evidence TEXT NOT NULL, status TEXT NOT NULL,
    created_at TEXT NOT NULL, policy_version TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS audit_events (
    seq INTEGER PRIMARY KEY AUTOINCREMENT, trace_id TEXT NOT NULL, at TEXT NOT NULL,
    kind TEXT NOT NULL, data TEXT NOT NULL);
CREATE TRIGGER IF NOT EXISTS audit_no_update BEFORE UPDATE ON audit_events
    BEGIN SELECT RAISE(ABORT, 'audit log is append-only'); END;
CREATE TRIGGER IF NOT EXISTS audit_no_delete BEFORE DELETE ON audit_events
    BEGIN SELECT RAISE(ABORT, 'audit log is append-only'); END;
"""


class _Rows:
    """Rows fetched while holding the lock, so no cursor is shared across threads."""

    def __init__(self, rows: list[sqlite3.Row]) -> None:
        self._rows = rows

    def fetchone(self) -> sqlite3.Row | None:
        return self._rows[0] if self._rows else None

    def fetchall(self) -> list[sqlite3.Row]:
        return self._rows

    def __iter__(self):
        return iter(self._rows)


class _SerializedConnection:
    """One SQLite connection used by the API's thread pool: every statement (and every `with conn:` transaction)
    runs under a re-entrant lock and returns fully fetched rows. Concurrent use of the raw connection returned
    corrupted reads in production (a customer lookup came back empty)."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn, self._lock = conn, threading.RLock()

    def execute(self, sql: str, params: tuple | list = ()) -> _Rows:
        with self._lock:
            return _Rows(self._conn.execute(sql, params).fetchall())

    def executemany(self, sql: str, rows) -> None:
        with self._lock:
            self._conn.executemany(sql, rows)

    def executescript(self, script: str) -> None:
        with self._lock:
            self._conn.executescript(script)

    def commit(self) -> None:
        with self._lock:
            self._conn.commit()

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def __enter__(self) -> _SerializedConnection:
        self._lock.acquire()
        self._conn.__enter__()
        return self

    def __exit__(self, *exc) -> None:
        try:
            self._conn.__exit__(*exc)
        finally:
            self._lock.release()


class Store:
    """SQLite operational store. Timestamps are stored as ISO-8601 UTC strings."""

    def __init__(self, path: str | Path = ":memory:") -> None:
        raw = sqlite3.connect(str(path), check_same_thread=False)
        raw.row_factory = sqlite3.Row
        self.conn = _SerializedConnection(raw)
        self.conn.executescript(SCHEMA)
        columns = {r["name"] for r in self.conn.execute("PRAGMA table_info(customers)")}
        if "first_name" not in columns:  # stores exported before v0.0.2
            with self.conn:
                self.conn.execute("ALTER TABLE customers ADD COLUMN first_name TEXT")

    def load_seed(self, path: str | Path) -> None:
        seed = json.loads(Path(path).read_text())
        with self.conn:
            for c in seed["customers"]:
                self.conn.execute(
                    "INSERT INTO customers (customer_id, country, segment, is_repeat_complainer, first_name) "
                    "VALUES (?,?,?,?,?)",
                    (c["customer_id"], c["country"], c["segment"], int(c["is_repeat_complainer"]), c.get("first_name")),
                )
            for p in seed["products"]:
                self.conn.execute(
                    "INSERT INTO products VALUES (?,?,?,?)",
                    (p["product_id"], p["customer_id"], p["product_type"], p["product_status"]),
                )
            for t in seed["transactions"]:
                self.conn.execute(
                    "INSERT INTO transactions VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                    (t["transaction_id"], t["customer_id"], t["product_id"], t["transaction_date"],
                     t["amount"], t["currency"], t["amount_usd"], t.get("merchant_name"),
                     t["transaction_status"], t["transaction_country"], t.get("fraud_score")),
                )

    def get_customer(self, customer_id: str) -> Customer | None:
        row = self.conn.execute("SELECT * FROM customers WHERE customer_id=?", (customer_id,)).fetchone()
        if row is None:
            return None
        return Customer(
            customer_id=row["customer_id"], country=row["country"], segment=row["segment"],
            is_repeat_complainer=bool(row["is_repeat_complainer"]), first_name=row["first_name"],
        )

    def get_card(self, product_id: str) -> Card | None:
        row = self.conn.execute("SELECT * FROM products WHERE product_id=?", (product_id,)).fetchone()
        return Card(**dict(row)) if row else None

    def list_cards(self, customer_id: str) -> list[Card]:
        rows = self.conn.execute("SELECT * FROM products WHERE customer_id=? ORDER BY product_id", (customer_id,))
        return [Card(**dict(r)) for r in rows]

    def distinct_merchants(self) -> list[str]:
        rows = self.conn.execute("SELECT DISTINCT merchant_name FROM transactions WHERE merchant_name IS NOT NULL")
        return sorted(r[0] for r in rows)

    def set_card_status(self, product_id: str, status: str) -> None:
        with self.conn:
            self.conn.execute("UPDATE products SET product_status=? WHERE product_id=?", (status, product_id))

    def get_transaction(self, transaction_id: str) -> Transaction | None:
        row = self.conn.execute(
            "SELECT * FROM transactions WHERE transaction_id=?", (transaction_id,)
        ).fetchone()
        return Transaction(**dict(row)) if row else None

    def list_transactions(self, customer_id: str, since: datetime) -> list[Transaction]:
        rows = self.conn.execute(
            "SELECT * FROM transactions WHERE customer_id=? AND transaction_date>=? "
            "ORDER BY transaction_date DESC",
            (customer_id, since.isoformat()),
        ).fetchall()
        return [Transaction(**dict(r)) for r in rows]

    def list_high_fraud_score(self, since: datetime, min_score: Decimal) -> list[Transaction]:
        rows = self.conn.execute(
            "SELECT t.* FROM transactions t WHERE t.transaction_date>=? "
            "AND CAST(t.fraud_score AS REAL)>=? AND t.transaction_status='Approved' "
            "AND NOT EXISTS (SELECT 1 FROM disputes d WHERE d.transaction_id=t.transaction_id) "
            "ORDER BY CAST(t.fraud_score AS REAL) DESC",
            (since.isoformat(), float(min_score)),
        ).fetchall()
        return [Transaction(**dict(r)) for r in rows]

    def insert_dispute(self, case: DisputeCase) -> None:
        with self.conn:
            self.conn.execute(
                "INSERT INTO disputes VALUES (?,?,?,?,?,?,?,?)",
                (case.case_id, case.customer_id, case.transaction_id, case.reason_code.value,
                 json.dumps(case.evidence), case.status, case.created_at.isoformat(), case.policy_version),
            )

    def get_dispute(self, case_id: str) -> DisputeCase | None:
        row = self.conn.execute("SELECT * FROM disputes WHERE case_id=?", (case_id,)).fetchone()
        return self._row_to_case(row) if row else None

    def find_open_dispute(self, transaction_id: str) -> DisputeCase | None:
        row = self.conn.execute(
            "SELECT * FROM disputes WHERE transaction_id=? AND status='Open'", (transaction_id,)
        ).fetchone()
        return self._row_to_case(row) if row else None

    def list_disputes(self, customer_id: str) -> list[DisputeCase]:
        rows = self.conn.execute(
            "SELECT * FROM disputes WHERE customer_id=? ORDER BY created_at DESC", (customer_id,)
        ).fetchall()
        return [self._row_to_case(r) for r in rows]

    def count_disputes_since(self, customer_id: str, since: datetime) -> int:
        (n,) = self.conn.execute(
            "SELECT COUNT(*) FROM disputes WHERE customer_id=? AND created_at>=?",
            (customer_id, since.isoformat()),
        ).fetchone()
        return n

    def append_audit(self, event: AuditEvent) -> None:
        with self.conn:
            self.conn.execute(
                "INSERT INTO audit_events (trace_id, at, kind, data) VALUES (?,?,?,?)",
                (event.trace_id, event.at.isoformat(), event.kind, json.dumps(event.data, default=str)),
            )

    def list_audit(self, trace_id: str) -> list[AuditEvent]:
        rows = self.conn.execute(
            "SELECT * FROM audit_events WHERE trace_id=? ORDER BY seq", (trace_id,)
        ).fetchall()
        return [
            AuditEvent(trace_id=r["trace_id"], at=r["at"], kind=r["kind"], data=json.loads(r["data"]))
            for r in rows
        ]

    def list_audit_by_kind(self, *kinds: str) -> list[AuditEvent]:
        marks = ",".join("?" * len(kinds))
        rows = self.conn.execute(
            f"SELECT * FROM audit_events WHERE kind IN ({marks}) ORDER BY seq", kinds
        ).fetchall()
        return [
            AuditEvent(trace_id=r["trace_id"], at=r["at"], kind=r["kind"], data=json.loads(r["data"]))
            for r in rows
        ]

    @staticmethod
    def _row_to_case(row: sqlite3.Row) -> DisputeCase:
        data = dict(row)
        data["evidence"] = json.loads(data["evidence"])
        return DisputeCase(**data)
