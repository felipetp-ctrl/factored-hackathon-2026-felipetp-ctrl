"""Backtest of the PQR matching rule on every real dispute complaint (same rule as channels.match_complaint,
expressed in SQL over the full silver data): how many complaints could be tied to exactly one transaction?"""

from __future__ import annotations

import json
from pathlib import Path

import duckdb

SQL = """
WITH q AS (
    SELECT c.complaint_id, c.customer_id, c.claimed_amount, c.creation_date,
           -- a product reference is only trusted if the product belongs to the complaining customer
           CASE WHEN p.customer_id = c.customer_id THEN c.affected_product_id END AS affected_product_id,
           (c.affected_product_id IS NOT NULL) AS has_product, (c.claimed_amount IS NOT NULL) AS has_amount,
           (c.affected_product_id IS NOT NULL AND p.customer_id IS DISTINCT FROM c.customer_id) AS foreign_product
    FROM read_parquet('{silver}/complaints.parquet') c
    LEFT JOIN read_parquet('{silver}/products.parquet') p ON p.product_id = c.affected_product_id
    WHERE c.category = 'Transactions'
),
cand AS (
    SELECT q.complaint_id, t.transaction_id, t.amount
    FROM q JOIN read_parquet('{silver}/transactions.parquet') t
      ON t.customer_id = q.customer_id
     AND t.transaction_date BETWEEN q.creation_date - INTERVAL 120 DAY AND q.creation_date
     AND t.transaction_status IN ('Approved', 'Pending')
     AND (q.affected_product_id IS NULL OR t.product_id = q.affected_product_id)
),
narrowed AS (
    SELECT q.complaint_id, q.has_product, q.has_amount, q.foreign_product,
           count(c.transaction_id) AS n_all,
           count(c.transaction_id) FILTER (WHERE q.claimed_amount IS NOT NULL
                                             AND abs(c.amount - q.claimed_amount) <= q.claimed_amount * 0.01) AS n_amount
    FROM q LEFT JOIN cand c USING (complaint_id)
    GROUP BY ALL
)
SELECT *, CASE WHEN n_amount > 0 THEN n_amount ELSE n_all END AS n_final FROM narrowed
"""


def backtest(silver: Path) -> dict:
    con = duckdb.connect()
    con.execute(f"CREATE TEMP TABLE r AS {SQL.format(silver=silver)}")
    total = con.execute("SELECT count(*) FROM r").fetchone()[0]
    rows = con.execute("""
        SELECT has_product, has_amount, count(*) n,
               sum((n_final = 1)::int) unique_match, sum((n_final = 0)::int) no_candidate, sum((n_final > 1)::int) ambiguous,
               round(median(n_final), 1) median_candidates
        FROM r GROUP BY ALL ORDER BY 1 DESC, 2 DESC""").fetchall()
    cols = ["has_product", "has_amount", "n", "unique_match", "no_candidate", "ambiguous", "median_candidates"]
    overall = con.execute("SELECT sum((n_final=1)::int), sum((n_final=0)::int), sum((n_final>1)::int), "
                          "sum(foreign_product::int) FROM r").fetchone()
    return {"complaints": total, "unique_match": overall[0], "no_candidate": overall[1], "ambiguous": overall[2],
            "foreign_product_reference": overall[3],
            "by_available_fields": [dict(zip(cols, r)) for r in rows]}


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[4]
    print(json.dumps(backtest(root / "data" / "silver"), indent=1, default=float))
