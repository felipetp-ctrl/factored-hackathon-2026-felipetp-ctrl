"""python -m dispute_ops.pipeline --raw ../data/raw --out ../data"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

from dispute_ops.pipeline.export import export_demo_store
from dispute_ops.pipeline.layers import run_pipeline

ROOT = Path(__file__).resolve().parents[4]


def quality_markdown(m: dict) -> str:
    lines = [f"# Data quality report — run `{m['run_id']}`", "",
             f"As of {m['as_of']} · contracts {m['contracts_version']} · **{m.get('status', 'published')}** "
             f"({m.get('mode', 'full')} run; write-audit-publish, ADR-028)", "",
             "| Table | new files | bronze rows | rejected lines | duplicates removed | silver rows | quarantined | identity conflicts | nulled FKs |",
             "|---|---|---|---|---|---|---|---|---|"]
    for t, r in m["tables"].items():
        if r["skipped"]:
            lines.append(f"| {t} | skipped: {r['skipped']} ||||||||")
            continue
        lines.append(f"| {t} | {r['new_files']} | {r['bronze_rows_total']:,} | {r['rejected_lines']} | {r['duplicate_rows_removed']:,} | "
                     f"{r['silver_rows']:,} | {r['orphans_quarantined'] or '-'} | {r.get('immutable_conflicts') or '-'} | {r['orphans_nulled'] or '-'} |")
    lines += ["", "## Contract findings", ""]
    for t, r in m["tables"].items():
        items = [(k, r[k]) for k in ("unexpected_columns", "missing_columns", "cast_failures", "required_nulls",
                                     "domain_violations", "range_violations") if r.get(k)]
        if items:
            lines.append(f"**{t}**")
            lines += [f"- {k}: `{json.dumps(v, ensure_ascii=False)}`" for k, v in items]
            lines.append("")
    if m.get("freshness"):
        lines += ["## Freshness", "", "Policy: daily batch; the newest partition may lag the run by at most 2 days (ADR-012).", "",
                  "| Table | newest process_date | lag (days) | status | rows processed > 1 day after the event |", "|---|---|---|---|---|"]
        lines += [f"| {t} | {f['newest_process_date']} | {f['lag_days']} | {f['status']} | {f['late_rows'] if f['late_rows'] is not None else '-'} |"
                  for t, f in m["freshness"].items()]
        lines.append("")
    if m.get("gates"):
        lines += ["## Quality gates", "", "Gold is staged, audited, then published; a failed **block** gate keeps the previous gold.", "",
                  "| Gate | Severity | Result | Detail |", "|---|---|---|---|"]
        lines += [f"| {g['gate']} | {g['severity']} | {'✅ pass' if g['status'] == 'pass' else ('❌ FAIL' if g['severity'] == 'block' else '⚠️ warn')} | {g['detail']} |"
                  for g in m["gates"]]
        lines.append("")
    if m.get("seconds"):
        lines += ["## Run", "", "| Step | Mode | Seconds |", "|---|---|---|"]
        lines += [f"| {k} | {m['tables'].get(k, {}).get('mode', '') or '-'} | {v} |" for k, v in m["seconds"].items()]
        lines.append("")
    lines += ["## Gold", "", *[f"- {k}: {v:,} rows" for k, v in m["gold_rows"].items()]]
    if "demo_store" in m:
        lines += ["", f"Demo store: {m['demo_store']}"]
    return "\n".join(lines) + "\n"


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--raw", default=str(ROOT / "data" / "raw"))
    p.add_argument("--out", default=str(ROOT / "data"))
    p.add_argument("--as-of", default="2026-06-17T12:00:00+00:00")
    p.add_argument("--tables", nargs="*")
    p.add_argument("--demo-customers", type=int, default=300)
    p.add_argument("--report", default=str(ROOT / "docs" / "data_quality_report.md"))
    p.add_argument("--full", action="store_true", help="recompute every silver key (default: only the keys touched)")
    args = p.parse_args()
    as_of = datetime.fromisoformat(args.as_of)
    m = run_pipeline(Path(args.raw), Path(args.out), as_of, args.tables, full=args.full)
    gold = Path(args.out) / "gold"
    if m["status"] == "published" and {"card_transactions", "customer_dim", "card_products"} <= {x.stem for x in gold.glob("*.parquet")}:
        m["demo_store"] = export_demo_store(gold, Path(args.out) / "demo" / "dispute_ops.db", as_of, args.demo_customers)
    Path(args.report).write_text(quality_markdown(m))
    print(quality_markdown(m))
    if m["status"] != "published":
        raise SystemExit(2)  # blocked by a quality gate: the previous gold stays published


if __name__ == "__main__":
    main()
