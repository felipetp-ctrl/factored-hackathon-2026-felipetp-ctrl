"""Bronze -> silver -> gold with DuckDB.

Bronze: raw CSV rows as text + lineage columns, appended per ingestion batch. Only new or changed source
files are read (incremental). Silver: typed, contract-checked, deduplicated (newest wins, so late and
corrected deliveries are handled by recomputation), orphans quarantined. Gold: the views the service uses."""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import duckdb

from dispute_ops.pipeline.contracts import CONTRACTS, ORDER, Contract


class ContractError(Exception):
    """A structural break that makes the table unusable (e.g. a required column is missing)."""


def _q(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


@dataclass
class Paths:
    raw: Path
    out: Path

    @property
    def bronze(self) -> Path:
        return self.out / "bronze"

    @property
    def silver(self) -> Path:
        return self.out / "silver"

    @property
    def gold(self) -> Path:
        return self.out / "gold"

    @property
    def state(self) -> Path:
        return self.out / "_state" / "bronze_files.json"


@dataclass
class TableReport:
    table: str
    new_files: int = 0
    bronze_rows_added: int = 0
    rejected_lines: int = 0
    unexpected_columns: list[str] = field(default_factory=list)
    missing_columns: list[str] = field(default_factory=list)
    bronze_rows_total: int = 0
    duplicate_rows_removed: int = 0
    cast_failures: dict[str, int] = field(default_factory=dict)
    required_nulls: dict[str, int] = field(default_factory=dict)
    domain_violations: dict[str, dict[str, int]] = field(default_factory=dict)
    range_violations: dict[str, int] = field(default_factory=dict)
    orphans_quarantined: dict[str, int] = field(default_factory=dict)
    orphans_nulled: dict[str, int] = field(default_factory=dict)
    silver_rows: int = 0
    skipped: str | None = None


# ---------------------------------------------------------------------------------------------- bronze
def run_bronze(con: duckdb.DuckDBPyConnection, c: Contract, paths: Paths, state: dict[str, Any], run_id: str,
               report: TableReport) -> None:
    files = sorted(paths.raw.glob(c.source))
    if not files:
        report.skipped = "no source files"
        return
    seen = state.setdefault(c.name, {})
    new = [f for f in files if seen.get(str(f)) != [f.stat().st_size, int(f.stat().st_mtime)]]
    report.new_files = len(new)
    if new:
        out_dir = paths.bronze / c.name
        out_dir.mkdir(parents=True, exist_ok=True)
        groups: dict[str, list[Path]] = {}
        for f in new:  # one read per distinct header: keeps reject counting (not allowed with union_by_name)
            with f.open(encoding="utf-8-sig") as fh:
                groups.setdefault(fh.readline().strip(), []).append(f)
        parts = []
        for i, files_in_group in enumerate(groups.values()):
            file_list = "[" + ",".join(f"'{f}'" for f in files_in_group) + "]"
            con.execute(f"""
                CREATE OR REPLACE TEMP TABLE _b{i} AS
                SELECT *, current_timestamp AS _ingested_at, '{run_id}' AS _batch_id
                FROM read_csv({file_list}, header=true, all_varchar=true, filename='_source_file', hive_partitioning=false,
                              ignore_errors=true, store_rejects=true, rejects_table='_rej{i}', rejects_scan='_rejs{i}')
            """)
            report.rejected_lines += con.execute(f"SELECT count(*) FROM _rej{i}").fetchone()[0]
            parts.append(f"SELECT * FROM _b{i}")
        con.execute("CREATE OR REPLACE TEMP TABLE _b AS " + " UNION ALL BY NAME ".join(parts))
        report.bronze_rows_added = con.execute("SELECT count(*) FROM _b").fetchone()[0]
        con.execute(f"COPY _b TO '{out_dir / f'batch_{run_id}.parquet'}' (FORMAT parquet)")
        for f in new:
            seen[str(f)] = [f.stat().st_size, int(f.stat().st_mtime)]


# ---------------------------------------------------------------------------------------------- silver
def run_silver(con: duckdb.DuckDBPyConnection, c: Contract, paths: Paths, report: TableReport) -> None:
    bronze_glob = paths.bronze / c.name / "*.parquet"
    if not any((paths.bronze / c.name).glob("*.parquet")):
        report.skipped = report.skipped or "no bronze data"
        return
    con.execute(f"CREATE OR REPLACE TEMP VIEW _bronze AS SELECT * FROM read_parquet('{bronze_glob}', union_by_name=true)")
    present = {r[0] for r in con.execute("DESCRIBE _bronze").fetchall()}
    lineage = {"_source_file", "_ingested_at", "_batch_id"}
    report.unexpected_columns = sorted(present - set(c.columns) - lineage)
    report.missing_columns = sorted(set(c.columns) - present)
    missing_required = [col for col in report.missing_columns if c.columns[col].required]
    if missing_required or any(k not in present for k in c.pk):
        raise ContractError(f"{c.name}: missing required columns {missing_required or list(c.pk)}")
    report.bronze_rows_total = con.execute("SELECT count(*) FROM _bronze").fetchone()[0]

    typed = ", ".join(
        (f"TRY_CAST({_q(col)} AS {spec.type}) AS {_q(col)}" if col in present else f"CAST(NULL AS {spec.type}) AS {_q(col)}")
        for col, spec in c.columns.items()
    )
    con.execute(f"CREATE OR REPLACE TEMP TABLE _typed AS SELECT {typed}, _source_file, _ingested_at, _batch_id FROM _bronze")

    for col, spec in c.columns.items():
        if col in present and spec.type != "VARCHAR":
            n = con.execute(f"SELECT count(*) FROM _bronze WHERE {_q(col)} IS NOT NULL AND TRY_CAST({_q(col)} AS {spec.type}) IS NULL").fetchone()[0]
            if n:
                report.cast_failures[col] = n

    pk = ", ".join(_q(k) for k in c.pk)
    con.execute(f"""
        CREATE OR REPLACE TEMP TABLE _dedup AS SELECT * FROM _typed
        WHERE {' AND '.join(f'{_q(k)} IS NOT NULL' for k in c.pk)}
        QUALIFY row_number() OVER (PARTITION BY {pk} ORDER BY {_q(c.order_by)} DESC NULLS LAST, _ingested_at DESC, _source_file DESC) = 1
    """)
    report.duplicate_rows_removed = report.bronze_rows_total - con.execute("SELECT count(*) FROM _dedup").fetchone()[0]

    for col, spec in c.columns.items():
        if spec.required:
            n = con.execute(f"SELECT count(*) FROM _dedup WHERE {_q(col)} IS NULL").fetchone()[0]
            if n:
                report.required_nulls[col] = n
        if spec.domain:
            allowed = ", ".join("'" + v.replace("'", "''") + "'" for v in spec.domain)
            rows = con.execute(
                f"SELECT {_q(col)}, count(*) FROM _dedup WHERE {_q(col)} IS NOT NULL AND {_q(col)} NOT IN ({allowed}) "
                f"GROUP BY 1 ORDER BY 2 DESC LIMIT 5"
            ).fetchall()
            if rows:
                report.domain_violations[col] = {str(v): n for v, n in rows}
        if spec.min is not None or spec.max is not None:
            conds = []
            if spec.min is not None:
                conds.append(f"{_q(col)} < {spec.min}")
            if spec.max is not None:
                conds.append(f"{_q(col)} > {spec.max}")
            n = con.execute(f"SELECT count(*) FROM _dedup WHERE {' OR '.join(conds)}").fetchone()[0]
            if n:
                report.range_violations[col] = n

    quarantine_dir = paths.silver / "_quarantine"
    for col, target in c.fks.items():
        parent, parent_col = target.split(".")
        parent_file = paths.silver / f"{parent}.parquet"
        if not parent_file.exists():
            continue
        orphan = f"{_q(col)} IS NOT NULL AND {_q(col)} NOT IN (SELECT {_q(parent_col)} FROM read_parquet('{parent_file}'))"
        n = con.execute(f"SELECT count(*) FROM _dedup WHERE {orphan}").fetchone()[0]
        if not n:
            continue
        if col in c.essential_fks:  # the row is unusable without its parent: quarantine it
            quarantine_dir.mkdir(parents=True, exist_ok=True)
            con.execute(f"COPY (SELECT * FROM _dedup WHERE {orphan}) TO '{quarantine_dir / f'{c.name}__{col}.parquet'}' (FORMAT parquet)")
            con.execute(f"DELETE FROM _dedup WHERE {orphan}")
            report.orphans_quarantined[col] = n
        else:  # optional reference: keep the row, drop the dangling link
            con.execute(f"UPDATE _dedup SET {_q(col)} = NULL WHERE {orphan}")
            report.orphans_nulled[col] = n

    paths.silver.mkdir(parents=True, exist_ok=True)
    con.execute(f"COPY _dedup TO '{paths.silver / f'{c.name}.parquet'}' (FORMAT parquet)")
    report.silver_rows = con.execute("SELECT count(*) FROM _dedup").fetchone()[0]


# ---------------------------------------------------------------------------------------------- gold
# Business normalisation lives in gold (silver keeps and reports the raw value): the policy keys its
# thresholds on the canonical country name.
COUNTRY_SQL = "CASE c.country WHEN 'México' THEN 'Mexico' ELSE c.country END"
def run_gold(con: duckdb.DuckDBPyConnection, paths: Paths, as_of: datetime) -> dict[str, int]:
    s = lambda t: f"read_parquet('{paths.silver / (t + '.parquet')}')"  # noqa: E731
    have = {p.stem for p in paths.silver.glob("*.parquet")}
    paths.gold.mkdir(parents=True, exist_ok=True)
    as_of_sql = f"TIMESTAMP '{as_of.replace(tzinfo=None).isoformat(sep=' ')}'"
    queries: dict[str, tuple[set[str], str]] = {
        "card_products": ({"products"}, f"SELECT * FROM {s('products')} WHERE product_type ILIKE '%card%' OR product_type ILIKE '%tarjeta%'"),
        "card_transactions": ({"products", "transactions", "daily_exchange_rates"}, f"""
            SELECT t.* REPLACE (
                     coalesce(t.amount_usd, CASE WHEN t.currency = 'USD' THEN t.amount END, t.amount * fx.exchange_rate) AS amount_usd),
                   CASE WHEN t.amount_usd IS NOT NULL THEN 'reported'
                        WHEN t.currency = 'USD' THEN 'identity_usd'
                        WHEN fx.exchange_rate IS NOT NULL THEN 'fx_daily' ELSE 'missing' END AS amount_usd_source
            FROM {s('transactions')} t JOIN {s('products')} p USING (product_id)
            LEFT JOIN {s('daily_exchange_rates')} fx
              ON fx.date = CAST(t.transaction_date AS DATE) AND fx.source_currency = t.currency AND fx.target_currency = 'USD'
            WHERE p.product_type ILIKE '%card%' OR p.product_type ILIKE '%tarjeta%'"""),
        "customer_dim": ({"customers"}, f"""
            SELECT c.customer_id, {COUNTRY_SQL} AS country, c.segment, c.customer_status, c.detected_accent,
                   coalesce(r.is_repeat_complainer, false) AS is_repeat_complainer, c.first_name
            FROM {s('customers')} c
            LEFT JOIN (SELECT customer_id, bool_or(is_repeat_complainer) AS is_repeat_complainer
                       FROM {s('complaints')} GROUP BY 1) r USING (customer_id)""" if "complaints" in have else
            f"SELECT customer_id, {COUNTRY_SQL} AS country, segment, customer_status, detected_accent, false AS is_repeat_complainer, first_name FROM {s('customers')} c"),
        "dispute_complaints": ({"complaints", "customers"}, f"""
            SELECT q.*, c.country, c.segment FROM {s('complaints')} q JOIN {s('customers')} c USING (customer_id)
            WHERE q.category = 'Transactions'"""),
        "fraud_alert_candidates": ({"transactions"}, f"""
            SELECT * FROM {s('transactions')}
            WHERE transaction_date BETWEEN {as_of_sql} - INTERVAL 48 HOUR AND {as_of_sql}
              AND fraud_score >= 80 AND transaction_status = 'Approved'"""),
    }
    counts = {}
    for name, (needs, sql) in queries.items():
        if needs <= have:
            con.execute(f"COPY ({sql}) TO '{paths.gold / f'{name}.parquet'}' (FORMAT parquet)")
            counts[name] = con.execute(f"SELECT count(*) FROM read_parquet('{paths.gold / f'{name}.parquet'}')").fetchone()[0]
    return counts


# ---------------------------------------------------------------------------------------------- orchestration
def run_pipeline(raw: Path, out: Path, as_of: datetime, tables: list[str] | None = None) -> dict[str, Any]:
    paths = Paths(raw=Path(raw), out=Path(out))
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S") + "-" + uuid.uuid4().hex[:6]
    state = json.loads(paths.state.read_text()) if paths.state.exists() else {}
    con = duckdb.connect()
    reports: dict[str, TableReport] = {}
    for name in tables or ORDER:
        c = CONTRACTS[name]
        report = reports[name] = TableReport(table=name)
        run_bronze(con, c, paths, state, run_id, report)
        run_silver(con, c, paths, report)
    gold = run_gold(con, paths, as_of)
    paths.state.parent.mkdir(parents=True, exist_ok=True)
    paths.state.write_text(json.dumps(state, indent=1))
    manifest = {
        "run_id": run_id,
        "as_of": as_of.isoformat(),
        "contracts_version": "dictionary-v1.0.0/contracts-v1",
        "tables": {k: vars(v) for k, v in reports.items()},
        "gold_rows": gold,
    }
    (paths.out / "_state").mkdir(parents=True, exist_ok=True)
    (paths.out / "_state" / f"manifest_{run_id}.json").write_text(json.dumps(manifest, indent=1, default=str))
    return manifest
