"""Data catalog generated from the contracts and the last published run (ADR-028).

    python -m dispute_ops.pipeline.catalog   (writes docs/data_catalog.md)

One source of truth: the contracts that the pipeline enforces are the documentation consumers read, so the two cannot
drift. Row counts and freshness come from the newest manifest."""

from __future__ import annotations

import json
from pathlib import Path

from dispute_ops.domain import FRAUD_ALERT_MIN_SCORE
from dispute_ops.pipeline.contracts import CONTRACTS, ORDER
from dispute_ops.pipeline.gates import MAX_QUARANTINE_SHARE, MAX_SILVER_DROP, MAX_USD_MISSING
from dispute_ops.pipeline.layers import FRESH_LAG_DAYS

ROOT = Path(__file__).resolve().parents[4]

GOLD = {
    "card_transactions": ("one row per card transaction", "silver transactions ⋈ products (card types) ⟕ daily_exchange_rates",
                          "`amount_usd` filled from the reported value, the USD identity or the daily FX rate; "
                          "`amount_usd_source` says which", "demo store → bank tools (search, get), evaluation sets"),
    "card_products": ("one row per card product", "silver products where the type is a card", "—",
                      "demo store → `block_card`, card status"),
    "customer_dim": ("one row per customer", "silver customers ⟕ complaints (repeat-complainer flag)",
                     "country normalised (México → Mexico) for the policy thresholds", "policy (country, repeat complainer)"),
    "dispute_complaints": ("one row per unrecognised-charge complaint", "silver complaints (category Transactions) ⋈ customers",
                           "—", "problem analysis, PQR backtest, written-complaint channel"),
    "fraud_alert_candidates": ("one row per transaction to alert on", "silver transactions",
                               f"approved, fraud_score ≥ {FRAUD_ALERT_MIN_SCORE}, last 48 h before the run's as-of time",
                               "fraud-alert channel (ADR-020)"),
}


def _latest_manifest(state: Path) -> dict | None:
    files = sorted(state.glob("manifest_*.json"))
    for f in reversed(files):
        m = json.loads(f.read_text())
        if m.get("status", "published") == "published":
            return m
    return None


def render(manifest: dict | None) -> str:
    tables = (manifest or {}).get("tables", {})
    lines = [
        "# Data catalog", "",
        "Generated from `pipeline/contracts.py` and the last published run "
        f"(`{manifest['run_id']}`)." if manifest else "Generated from `pipeline/contracts.py`.", "",
        "Owner: dispute operations data (hackathon team) · Refresh: daily batch after each `process_date` closes · "
        f"Freshness SLA: newest partition at most {FRESH_LAG_DAYS} days behind · Publication: write-audit-publish with "
        f"quality gates (row conservation, volume drop ≤ {MAX_SILVER_DROP:.0%}, USD amount missing ≤ {MAX_USD_MISSING:.0%}, "
        f"quarantine ≤ {MAX_QUARANTINE_SHARE:.0%} as a warning) · Lineage: [ADR-012](decisions/ADR-012-data-pipeline.md), "
        "[ADR-028](decisions/ADR-028-incremental-silver-and-gates.md)", "",
        "## Gold (what the service reads)", "",
        "| Table | Grain | Built from | Rules | Used by | Rows |", "|---|---|---|---|---|---|",
    ]
    gold_rows = (manifest or {}).get("gold_rows", {})
    lines += [f"| `{k}` | {g} | {src} | {rule} | {use} | {gold_rows.get(k, 0):,} |" for k, (g, src, rule, use) in GOLD.items()]
    lines += ["", "## Silver (typed, contract-checked, one row per key)", ""]
    for name in ORDER:
        c = CONTRACTS[name]
        t = tables.get(name, {})
        rows = f"{t['silver_rows']:,} rows" if t.get("silver_rows") else "not built in the last run"
        lines += [f"### `{name}`", "",
                  f"Source `{c.source}` · key `{', '.join(c.pk)}` · newest wins by `{c.order_by}` · {rows}"]
        if c.immutable:
            lines.append(f"· identity (never changes on re-delivery): `{', '.join(c.immutable)}`")
        lines += ["", "| Column | Type | Required | Allowed values / range | References |", "|---|---|---|---|---|"]
        for col, spec in c.columns.items():
            allowed = ", ".join(spec.domain) if spec.domain else ""
            if spec.min is not None or spec.max is not None:
                allowed = f"{'' if spec.min is None else spec.min} … {'' if spec.max is None else spec.max}"
            ref = c.fks.get(col, "")
            if ref:
                ref = f"`{ref}` ({'essential: orphan quarantined' if col in c.essential_fks else 'optional: orphan nulled'})"
            lines.append(f"| `{col}` | {spec.type} | {'yes' if spec.required else ''} | {allowed} | {ref} |")
        lines.append("")
    return "\n".join(lines)


def main() -> None:
    m = _latest_manifest(ROOT / "data" / "_state")
    (ROOT / "docs" / "data_catalog.md").write_text(render(m) + "\n")
    print(f"docs/data_catalog.md written ({'run ' + m['run_id'] if m else 'no manifest'})")


if __name__ == "__main__":
    main()
