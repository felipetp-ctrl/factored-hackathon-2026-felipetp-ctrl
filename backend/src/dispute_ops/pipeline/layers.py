"""Bronze -> silver -> gold with DuckDB.

Bronze: raw CSV rows as text + lineage columns, appended per ingestion batch. Only new or changed source
files are read (incremental). Silver: typed, contract-checked, deduplicated (newest wins, so late and
corrected deliveries are handled by recomputation), orphans quarantined. Gold: the views the service uses."""

from __future__ import annotations

import json
import shutil
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import duckdb

from dispute_ops.domain import FRAUD_ALERT_MIN_SCORE
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
    immutable_conflicts: dict[str, int] = field(default_factory=dict)
    silver_rows: int = 0
    pk_null_rows: int = 0
    distinct_keys: int = 0
    mode: str = ""
    skipped: str | None = None
    # Column profile (ADR-032): null share of every contracted column in the rows this run recomputed, the rows it
    # kept, and the whole table; the gates compare the first with the second (or with the last published run).
    profile: dict[str, Any] = field(default_factory=dict)


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
# Silver is computed per key: every check (newest-wins, identity, contracts, foreign keys) depends only on the versions
# of one key and on the parent tables. So a run only has to recompute the keys it touched — the keys in this run's
# bronze batch, plus child rows whose parent key changed — and keep every other silver row as it was. A full rebuild
# (`full=True`, the first run, or a parent rebuilt in full) recomputes everything; the two are proven equal by test
# and on the organizer data (docs/analysis/incremental-silver.md).
def _aff(table: str) -> str:
    return f"_aff_{table}"


def _key_in(c: Contract, keys_table: str, prefix: str = "") -> str:
    cols = ", ".join(f"{prefix}{_q(k)}" for k in c.pk)
    return f"({cols}) IN (SELECT {', '.join(_q(k) for k in c.pk)} FROM {keys_table})"


def _typed_key(c: Contract, present: set[str]) -> str:
    return ", ".join(f"TRY_CAST({_q(k)} AS {c.columns[k].type}) AS {_q(k)}" for k in c.pk if k in present)


def run_silver(con: duckdb.DuckDBPyConnection, c: Contract, paths: Paths, report: TableReport, *, run_id: str = "",
               full: bool = True) -> None:
    bronze_glob = paths.bronze / c.name / "*.parquet"
    if not any((paths.bronze / c.name).glob("*.parquet")):
        report.skipped = report.skipped or "no bronze data"
        return
    silver_file = paths.silver / f"{c.name}.parquet"
    full = full or not silver_file.exists()
    con.execute(f"CREATE OR REPLACE TEMP VIEW _bronze AS SELECT * FROM read_parquet('{bronze_glob}', union_by_name=true)")
    present = {r[0] for r in con.execute("DESCRIBE _bronze").fetchall()}
    lineage = {"_source_file", "_ingested_at", "_batch_id"}
    report.unexpected_columns = sorted(present - set(c.columns) - lineage)
    report.missing_columns = sorted(set(c.columns) - present)
    missing_required = [col for col in report.missing_columns if c.columns[col].required]
    if missing_required or any(k not in present for k in c.pk):
        raise ContractError(f"{c.name}: missing required columns {missing_required or list(c.pk)}")
    report.bronze_rows_total = con.execute("SELECT count(*) FROM _bronze").fetchone()[0]
    pk_cols = ", ".join(_q(k) for k in c.pk)
    tkey = _typed_key(c, present)

    if full:
        con.execute(f"CREATE OR REPLACE TEMP TABLE {_aff(c.name)} AS SELECT DISTINCT {tkey} FROM _bronze")
        source = "_bronze"
        report.mode = "full"
    else:
        batch = paths.bronze / c.name / f"batch_{run_id}.parquet"
        parts = [f"SELECT DISTINCT {tkey} FROM read_parquet('{batch}', union_by_name=true)"] if batch.exists() else []
        for col, target in c.fks.items():  # children of keys that changed (new, corrected or quarantined parents)
            parent, parent_col = target.split(".")
            if col in present and con.execute(
                    f"SELECT count(*) FROM duckdb_tables() WHERE table_name = '{_aff(parent)}'").fetchone()[0]:
                parent_type = CONTRACTS[parent].columns[parent_col].type
                parts.append(f"SELECT DISTINCT {tkey} FROM _bronze WHERE TRY_CAST({_q(col)} AS {parent_type}) IN "
                             f"(SELECT {_q(parent_col)} FROM {_aff(parent)})")
        if not parts:
            con.execute(f"CREATE OR REPLACE TEMP TABLE {_aff(c.name)} AS SELECT {tkey} FROM _bronze LIMIT 0")
        else:
            con.execute(f"CREATE OR REPLACE TEMP TABLE {_aff(c.name)} AS " + " UNION ".join(parts))
        n_aff = con.execute(f"SELECT count(*) FROM {_aff(c.name)}").fetchone()[0]
        report.mode = f"incremental ({n_aff:,} keys recomputed)"
        con.execute(f"CREATE OR REPLACE TEMP VIEW _bronze_aff AS SELECT * FROM _bronze WHERE "
                    f"({', '.join(f'TRY_CAST({_q(k)} AS {c.columns[k].type})' for k in c.pk)}) IN "
                    f"(SELECT {pk_cols} FROM {_aff(c.name)})")
        source = "_bronze_aff"

    typed = ", ".join(
        (f"TRY_CAST({_q(col)} AS {spec.type}) AS {_q(col)}" if col in present else f"CAST(NULL AS {spec.type}) AS {_q(col)}")
        for col, spec in c.columns.items()
    )
    con.execute(f"CREATE OR REPLACE TEMP TABLE _typed AS SELECT {typed}, _source_file, _ingested_at, _batch_id FROM {source}")

    for col, spec in c.columns.items():  # scope: every bronze row (full) or the recomputed keys (incremental)
        if col in present and spec.type != "VARCHAR":
            n = con.execute(f"SELECT count(*) FROM {source} WHERE {_q(col)} IS NOT NULL AND TRY_CAST({_q(col)} AS {spec.type}) IS NULL").fetchone()[0]
            if n:
                report.cast_failures[col] = n

    con.execute(f"""
        CREATE OR REPLACE TEMP TABLE _dedup AS SELECT * FROM _typed
        WHERE {' AND '.join(f'{_q(k)} IS NOT NULL' for k in c.pk)}
        QUALIFY row_number() OVER (PARTITION BY {pk_cols} ORDER BY {_q(c.order_by)} DESC NULLS LAST, _ingested_at DESC, _source_file DESC) = 1
    """)

    quarantined: dict[str, str] = {}  # quarantine file name -> temp table with this run's rows for it
    for col in c.immutable:
        # Versions of one key that disagree on an identity column: keep none of them in silver.
        conflict = (f"({pk_cols}) IN (SELECT {pk_cols} FROM _typed WHERE {_q(col)} IS NOT NULL GROUP BY {pk_cols} "
                    f"HAVING count(DISTINCT {_q(col)}) > 1)")
        tmp = f"_qi_{col}"
        con.execute(f"CREATE OR REPLACE TEMP TABLE {tmp} AS SELECT * FROM _typed WHERE {conflict}")
        con.execute(f"DELETE FROM _dedup WHERE {conflict}")
        quarantined[f"{c.name}__immutable_{col}.parquet"] = tmp
    for col, target in c.fks.items():
        parent, parent_col = target.split(".")
        parent_file = paths.silver / f"{parent}.parquet"
        if not parent_file.exists():
            continue
        orphan = f"{_q(col)} IS NOT NULL AND {_q(col)} NOT IN (SELECT {_q(parent_col)} FROM read_parquet('{parent_file}'))"
        if col in c.essential_fks:  # the row is unusable without its parent: quarantine it
            tmp = f"_qf_{col}"
            con.execute(f"CREATE OR REPLACE TEMP TABLE {tmp} AS SELECT * FROM _dedup WHERE {orphan}")
            con.execute(f"DELETE FROM _dedup WHERE {orphan}")
            quarantined[f"{c.name}__{col}.parquet"] = tmp
        else:  # optional reference: keep the row, drop the dangling link (scope as for cast failures)
            n = con.execute(f"SELECT count(*) FROM _dedup WHERE {orphan}").fetchone()[0]
            if n:
                con.execute(f"UPDATE _dedup SET {_q(col)} = NULL WHERE {orphan}")
                report.orphans_nulled[col] = n

    # Merge: recomputed keys replace their old rows; untouched keys keep theirs. Same for each quarantine file.
    paths.silver.mkdir(parents=True, exist_ok=True)
    quarantine_dir = paths.silver / "_quarantine"
    keep = "" if full else f"SELECT * FROM read_parquet('{silver_file}') WHERE NOT {_key_in(c, _aff(c.name))} UNION ALL BY NAME "
    con.execute(f"CREATE OR REPLACE TEMP TABLE _final AS {keep}SELECT * FROM _dedup")
    for fname, tmp in quarantined.items():
        old = quarantine_dir / fname
        keep_q = (f"SELECT * FROM read_parquet('{old}') WHERE NOT {_key_in(c, _aff(c.name))} UNION ALL BY NAME "
                  if not full and old.exists() else "")
        con.execute(f"CREATE OR REPLACE TEMP TABLE _q AS {keep_q}SELECT * FROM {tmp}")
        if con.execute("SELECT count(*) FROM _q").fetchone()[0]:
            quarantine_dir.mkdir(parents=True, exist_ok=True)
            con.execute(f"COPY (SELECT * FROM _q ORDER BY ALL) TO '{old}' (FORMAT parquet)")
            n_keys = con.execute(f"SELECT count(DISTINCT ({pk_cols})) FROM _q").fetchone()[0]
            if "__immutable_" in fname:
                report.immutable_conflicts[fname.split("__immutable_")[1].removesuffix(".parquet")] = n_keys
            else:
                report.orphans_quarantined[fname.split("__")[1].removesuffix(".parquet")] = n_keys
        elif old.exists():
            old.unlink()
    con.execute(f"COPY (SELECT * FROM _final ORDER BY {pk_cols}) TO '{silver_file}' (FORMAT parquet)")

    # Checks on the published silver table (the same in both modes) and the row-conservation counts.
    report.silver_rows = con.execute("SELECT count(*) FROM _final").fetchone()[0]
    keys = con.execute(f"SELECT count(*) FILTER (WHERE {' OR '.join(f'k.{_q(k)} IS NULL' for k in c.pk)}), "
                       f"count(DISTINCT ({', '.join(f'k.{_q(k)}' for k in c.pk)})) "
                       f"FROM (SELECT {tkey} FROM _bronze) k").fetchone()
    report.pk_null_rows, report.distinct_keys = keys[0], keys[1]
    report.duplicate_rows_removed = report.bronze_rows_total - report.pk_null_rows - report.distinct_keys
    report.profile = _profile(con, c, pk_cols)
    for col, spec in c.columns.items():
        if spec.required and col not in c.fks:  # a dangling optional FK is reported once, as a nulled FK
            n = con.execute(f"SELECT count(*) FROM _final WHERE {_q(col)} IS NULL").fetchone()[0]
            if n:
                report.required_nulls[col] = n
        if spec.domain:
            allowed = ", ".join("'" + v.replace("'", "''") + "'" for v in spec.domain)
            rows = con.execute(
                f"SELECT {_q(col)}, count(*) FROM _final WHERE {_q(col)} IS NOT NULL AND {_q(col)} NOT IN ({allowed}) "
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
            n = con.execute(f"SELECT count(*) FROM _final WHERE {' OR '.join(conds)}").fetchone()[0]
            if n:
                report.range_violations[col] = n


def _profile(con: duckdb.DuckDBPyConnection, c: Contract, pk_cols: str) -> dict[str, Any]:
    cols = list(c.columns)
    counts = ", ".join(f"count({_q(col)})" for col in cols)
    in_run = f"({pk_cols}) IN (SELECT {pk_cols} FROM {_aff(c.name)})"

    def shares(where: str) -> tuple[int, dict[str, float]]:
        row = con.execute(f"SELECT count(*), {counts} FROM _final WHERE {where}").fetchone()
        return row[0], ({col: round(1 - n / row[0], 4) for col, n in zip(cols, row[1:])} if row[0] else {})

    run_rows, run_null = shares(in_run)
    kept_rows, kept_null = shares(f"NOT {in_run}")
    all_rows, all_null = shares("TRUE")
    return {"run_rows": run_rows, "run_null": run_null, "kept_rows": kept_rows, "kept_null": kept_null,
            "null": all_null}


# ---------------------------------------------------------------------------------------------- gold
# Business normalisation lives in gold (silver keeps and reports the raw value): the policy keys its
# thresholds on the canonical country name.
COUNTRY_SQL = "CASE c.country WHEN 'México' THEN 'Mexico' ELSE c.country END"
def run_gold(con: duckdb.DuckDBPyConnection, paths: Paths, as_of: datetime, target: Path | None = None) -> dict[str, int]:
    s = lambda t: f"read_parquet('{paths.silver / (t + '.parquet')}')"  # noqa: E731
    have = {p.stem for p in paths.silver.glob("*.parquet")}
    target = target or paths.gold
    target.mkdir(parents=True, exist_ok=True)
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
              AND fraud_score >= {FRAUD_ALERT_MIN_SCORE} AND transaction_status = 'Approved'"""),
    }
    counts = {}
    for name, (needs, sql) in queries.items():
        if needs <= have:
            con.execute(f"COPY ({sql}) TO '{target / f'{name}.parquet'}' (FORMAT parquet)")
            counts[name] = con.execute(f"SELECT count(*) FROM read_parquet('{target / f'{name}.parquet'}')").fetchone()[0]
    return counts


# ---------------------------------------------------------------------------------------------- orchestration
# Freshness policy (ADR-012): a daily batch after each process_date closes, so the newest partition may lag the run by
# at most FRESH_LAG_DAYS; a late file for an older day is absorbed by the next run and counted here as a late arrival.
FRESH_LAG_DAYS = 2
EVENT_DATE = {"transactions": "transaction_date", "complaints": "creation_date", "call_center_interactions": "interaction_date"}


def check_freshness(con: duckdb.DuckDBPyConnection, paths: Paths, as_of: datetime) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for table, event_col in EVENT_DATE.items():
        f = paths.silver / f"{table}.parquet"
        if not f.exists():
            continue
        cols = {r[0] for r in con.execute(f"DESCRIBE SELECT * FROM read_parquet('{f}')").fetchall()}
        if "process_date" not in cols:
            continue
        newest = con.execute(f"SELECT max(process_date) FROM read_parquet('{f}')").fetchone()[0]
        lag = (as_of.date() - newest).days if newest else None
        late = None
        if event_col in cols:  # rows processed more than a day after the event happened
            late = con.execute(f"SELECT count(*) FROM read_parquet('{f}') WHERE process_date > CAST({_q(event_col)} AS DATE) + 1").fetchone()[0]
        out[table] = {"newest_process_date": str(newest), "lag_days": lag,
                      "status": "fresh" if lag is not None and lag <= FRESH_LAG_DAYS else "stale", "late_rows": late}
    return out


def run_pipeline(raw: Path, out: Path, as_of: datetime, tables: list[str] | None = None, *,
                 full: bool = False) -> dict[str, Any]:
    """Bronze (new files only) -> silver (recomputed keys, or everything with full=True) -> gold written to staging,
    audited by the quality gates, then published (write-audit-publish). A blocked run keeps the previous gold."""
    from dispute_ops.pipeline.gates import evaluate_gates, gold_audit

    paths = Paths(raw=Path(raw), out=Path(out))
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S") + "-" + uuid.uuid4().hex[:6]
    state = json.loads(paths.state.read_text()) if paths.state.exists() else {}
    con = duckdb.connect()
    reports: dict[str, TableReport] = {}
    rebuilt: set[str] = set()
    timings: dict[str, float] = {}
    for name in tables or ORDER:
        c = CONTRACTS[name]
        report = reports[name] = TableReport(table=name)
        t0 = time.perf_counter()
        run_bronze(con, c, paths, state, run_id, report)
        # A table is rebuilt in full when asked, on its first run, or when a parent was rebuilt in full this run.
        table_full = full or any(t.split(".")[0] in rebuilt for t in c.fks.values())
        run_silver(con, c, paths, report, run_id=run_id, full=table_full)
        if report.mode == "full":
            rebuilt.add(name)
        timings[name] = round(time.perf_counter() - t0, 2)
    staging = paths.out / "gold.__staging__"
    if staging.exists():
        shutil.rmtree(staging)
    t0 = time.perf_counter()
    gold = run_gold(con, paths, as_of, target=staging)
    timings["gold"] = round(time.perf_counter() - t0, 2)
    freshness = check_freshness(con, paths, as_of)
    history = paths.out / "_state" / "runs.jsonl"
    previous = _last_published(history)
    gates = evaluate_gates({k: vars(v) for k, v in reports.items()}, gold, gold_audit(con, staging), freshness, previous)
    blocked = [g for g in gates if g["status"] == "fail" and g["severity"] == "block"]
    if blocked:
        shutil.rmtree(staging)
        status = "blocked"
    else:
        _publish(staging, paths.gold)
        status = "published"
    paths.state.parent.mkdir(parents=True, exist_ok=True)
    paths.state.write_text(json.dumps(state, indent=1))
    manifest = {
        "run_id": run_id,
        "as_of": as_of.isoformat(),
        "contracts_version": "dictionary-v1.0.0/contracts-v1",
        "status": status,
        "mode": "full" if full else "incremental",
        "tables": {k: vars(v) for k, v in reports.items()},
        "gold_rows": gold,
        "freshness": freshness,
        "gates": gates,
        "seconds": timings,
    }
    (paths.out / "_state").mkdir(parents=True, exist_ok=True)
    (paths.out / "_state" / f"manifest_{run_id}.json").write_text(json.dumps(manifest, indent=1, default=str))
    with history.open("a") as fh:
        fh.write(json.dumps({"run_id": run_id, "status": status, "mode": manifest["mode"], "as_of": manifest["as_of"],
                             "silver_rows": {k: v.silver_rows for k, v in reports.items() if not v.skipped},
                             "null_share": {k: v.profile.get("null", {}) for k, v in reports.items() if not v.skipped},
                             "gold_rows": gold, "seconds": timings,
                             "gates_failed": [g["gate"] for g in gates if g["status"] == "fail"]}) + "\n")
    return manifest


def _last_published(history: Path) -> dict[str, Any] | None:
    if not history.exists():
        return None
    runs = [json.loads(x) for x in history.read_text().splitlines() if x.strip()]
    published = [r for r in runs if r["status"] == "published"]
    return published[-1] if published else None


def _publish(staging: Path, gold: Path) -> None:
    """Swap the audited staging folder in for the published gold (two renames; readers never see a half-written set)."""
    previous = gold.with_name("gold.__previous__")
    if previous.exists():
        shutil.rmtree(previous)
    if gold.exists():
        gold.rename(previous)
    staging.rename(gold)
    if previous.exists():
        shutil.rmtree(previous)
