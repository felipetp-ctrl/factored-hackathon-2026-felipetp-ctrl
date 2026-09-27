"""Gold -> SQLite operational store used by the API demo (a deterministic sample of customers)."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import duckdb

from dispute_ops.store import Store


def export_demo_store(gold: Path, db_path: Path, as_of: datetime, n_customers: int = 300) -> dict[str, int]:
    """Pick customers with recent card activity (plus every customer with an open fraud alert), deterministically."""
    g = lambda t: f"read_parquet('{gold / (t + '.parquet')}')"  # noqa: E731
    ts = f"TIMESTAMP '{as_of.replace(tzinfo=None).isoformat(sep=' ')}'"
    con = duckdb.connect()
    con.execute(f"""
        CREATE TEMP TABLE picked AS
        WITH active AS (
            SELECT DISTINCT customer_id FROM {g('card_transactions')}
            WHERE transaction_date BETWEEN {ts} - INTERVAL 120 DAY AND {ts}
        )
        (SELECT customer_id FROM active ORDER BY hash(customer_id) LIMIT {n_customers})
        UNION SELECT DISTINCT customer_id FROM {g('fraud_alert_candidates')}
        -- keep every customer with a recent high-risk card charge so the proactive channel has real cases
        UNION SELECT DISTINCT customer_id FROM {g('card_transactions')}
              WHERE fraud_score >= 80 AND transaction_date BETWEEN {ts} - INTERVAL 30 DAY AND {ts}
    """)
    customers = con.execute(f"""
        SELECT customer_id, country, segment, is_repeat_complainer, first_name FROM {g('customer_dim')}
        WHERE customer_id IN (SELECT customer_id FROM picked)""").fetchall()
    products = con.execute(f"""
        SELECT product_id, customer_id, product_type, product_status FROM {g('card_products')}
        WHERE customer_id IN (SELECT customer_id FROM picked)""").fetchall()
    txns = con.execute(f"""
        SELECT transaction_id, customer_id, product_id,
               strftime(transaction_date, '%Y-%m-%dT%H:%M:%S+00:00'), printf('%.2f', amount), currency,
               printf('%.2f', coalesce(amount_usd, 0)), merchant_name, transaction_status, transaction_country,
               CASE WHEN fraud_score IS NULL THEN NULL ELSE printf('%.2f', fraud_score) END
        FROM {g('card_transactions')}
        WHERE customer_id IN (SELECT customer_id FROM picked)
          AND transaction_date BETWEEN {ts} - INTERVAL 400 DAY AND {ts}""").fetchall()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        db_path.unlink()
    store = Store(db_path)
    with store.conn:
        store.conn.executemany(
            "INSERT INTO customers VALUES (?,?,?,?,?)", [(c, co, s, int(bool(r)), n) for c, co, s, r, n in customers])
        store.conn.executemany("INSERT INTO products VALUES (?,?,?,?)", products)
        store.conn.executemany("INSERT INTO transactions VALUES (?,?,?,?,?,?,?,?,?,?,?)", txns)
    return {"customers": len(customers), "products": len(products), "transactions": len(txns)}
