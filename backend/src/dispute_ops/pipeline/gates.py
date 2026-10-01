"""Quality gates: the audit step of write-audit-publish (ADR-028).

Gold is written to a staging folder; these checks run on the run's numbers and on the staged gold; any failed
`block` gate keeps the previously published gold and makes the command exit non-zero. `warn` gates are reported only.
Thresholds are part of the data contract and live here, next to their reasons."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import duckdb

MAX_SILVER_DROP = 0.01  # a run may not lose more than 1% of a table's rows against the last published run
MAX_USD_MISSING = 0.01  # card transactions without a USD amount: the policy thresholds are in USD
MAX_QUARANTINE_SHARE = 0.05
CORE_GOLD = ("card_transactions", "card_products", "customer_dim")
# Column profile (ADR-032): a delivery whose column is suddenly emptier than the history is an upstream break (a
# renamed field, a failed join in the source system) that row counts and contracts do not see.
NULL_JUMP_BLOCK = 0.20  # percentage points of extra nulls in the rows this run brought, against the reference
NULL_JUMP_WARN = 0.05
MIN_PROFILE_ROWS = 200  # below this a share is too noisy to judge


def gold_audit(con: duckdb.DuckDBPyConnection, staging: Path) -> dict[str, Any]:
    out: dict[str, Any] = {}
    f = staging / "card_transactions.parquet"
    if f.exists():
        total, missing, dup = con.execute(
            f"SELECT count(*), count(*) FILTER (WHERE amount_usd IS NULL), count(*) - count(DISTINCT transaction_id) "
            f"FROM read_parquet('{f}')").fetchone()
        out["card_transactions"] = {"rows": total, "usd_missing": missing, "duplicate_ids": dup}
    return out


def _profile_gates(name: str, p: dict[str, Any], previous: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Rows this run recomputed against the rows it kept; in a full rebuild, against the last published run."""
    if p.get("run_rows", 0) < MIN_PROFILE_ROWS:
        return []
    if p.get("kept_rows", 0) >= MIN_PROFILE_ROWS:
        reference, against = p["kept_null"], f"{p['kept_rows']:,} kept rows"
    elif previous and previous.get("null_share", {}).get(name):
        reference, against = previous["null_share"][name], f"run {previous['run_id']}"
    else:
        return []
    jumps = {col: p["run_null"][col] - reference[col] for col in p["run_null"] if col in reference}
    worst = max(jumps, key=jumps.__getitem__, default=None)
    if worst is None:
        return []
    jump = jumps[worst]
    detail = (f"worst column {worst}: {p['run_null'][worst]:.1%} null in {p['run_rows']:,} rows of this run vs "
              f"{reference[worst]:.1%} in {against} ({jump:+.1%})")
    return [_gate(f"{name}: column profile", "block", jump <= NULL_JUMP_BLOCK, detail),
            _gate(f"{name}: column profile drift", "warn", jump <= NULL_JUMP_WARN, detail)]


def _gate(gate: str, severity: str, ok: bool, detail: str) -> dict[str, Any]:
    return {"gate": gate, "severity": severity, "status": "pass" if ok else "fail", "detail": detail}


def evaluate_gates(tables: dict[str, dict], gold_rows: dict[str, int], audit: dict[str, Any],
                   freshness: dict[str, Any], previous: dict[str, Any] | None) -> list[dict[str, Any]]:
    gates = []
    for name, t in tables.items():
        if t.get("skipped"):
            continue
        quarantined = sum(t["orphans_quarantined"].values()) + sum(t["immutable_conflicts"].values())
        # Row conservation: every distinct key of bronze is either in silver or in quarantine; every other bronze row
        # is a superseded version or has no key. Nothing disappears unaccounted.
        balanced = (t["bronze_rows_total"] == t["pk_null_rows"] + t["duplicate_rows_removed"] + t["distinct_keys"]
                    and t["distinct_keys"] == t["silver_rows"] + quarantined)
        gates.append(_gate(f"{name}: row conservation", "block", balanced,
                           f"bronze {t['bronze_rows_total']:,} = no key {t['pk_null_rows']:,} + superseded "
                           f"{t['duplicate_rows_removed']:,} + silver {t['silver_rows']:,} + quarantined {quarantined:,}"))
        share = quarantined / t["distinct_keys"] if t["distinct_keys"] else 0.0
        gates.append(_gate(f"{name}: quarantine share", "warn", share <= MAX_QUARANTINE_SHARE,
                           f"{share:.2%} of keys quarantined (limit {MAX_QUARANTINE_SHARE:.0%})"))
        if previous and name in previous.get("silver_rows", {}):
            before = previous["silver_rows"][name]
            drop = (before - t["silver_rows"]) / before if before else 0.0
            gates.append(_gate(f"{name}: volume", "block", drop <= MAX_SILVER_DROP,
                               f"{before:,} -> {t['silver_rows']:,} rows ({-drop:+.2%}) since run {previous['run_id']}"))
        gates.extend(_profile_gates(name, t.get("profile") or {}, previous))
    for name in CORE_GOLD:
        if name in gold_rows:  # a gold table this run's inputs could build
            gates.append(_gate(f"gold {name}: not empty", "block", gold_rows.get(name, 0) > 0,
                               f"{gold_rows.get(name, 0):,} rows"))
    ct = audit.get("card_transactions")
    if ct:
        share = ct["usd_missing"] / ct["rows"] if ct["rows"] else 0.0
        gates.append(_gate("gold card_transactions: USD amount present", "block", share <= MAX_USD_MISSING,
                           f"{ct['usd_missing']:,} of {ct['rows']:,} without amount_usd ({share:.2%})"))
        gates.append(_gate("gold card_transactions: unique ids", "block", ct["duplicate_ids"] == 0,
                           f"{ct['duplicate_ids']} duplicate ids"))
    for name, f in freshness.items():
        gates.append(_gate(f"{name}: freshness", "warn", f["status"] == "fresh",
                           f"newest {f['newest_process_date']}, lag {f['lag_days']} days"))
    return gates
