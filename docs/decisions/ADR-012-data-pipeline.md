# ADR-012 — Data pipeline: SQL contracts in DuckDB, incremental ingestion, recomputed silver
- **Status:** accepted · **Date:** 2026-09-26 · supersedes the Pandera part of ADR-006

## Context
About 19M rows of daily-partitioned CSV with intentional duplicates, nulls, late arrivals and schema evolution. Real values diverge from the data dictionary (e.g. `branches.country = "México"`, `geographic_zone = "Urbana"`, `document_type = "Pasaporte"`).

## Decision
- **Declarative contracts** (`pipeline/contracts.py`): type, required, domain, range, primary key, newest-wins ordering, foreign keys, and which FKs are essential to the use case — taken from dictionary v1.0.0. Checks run as SQL in DuckDB, not Pandera: validating 4.4M transactions in pandas would be slow and memory-hungry.
- **Bronze:** raw text plus lineage (`_source_file`, `_ingested_at`, `_batch_id`), one Parquet per batch. Only new or changed files are read (size + mtime in `_state/bronze_files.json`). Malformed lines are counted (rejects), never silently dropped.
- **Silver:** recomputed from all bronze on every run:
  - types via `TRY_CAST`, failures counted;
  - dedup by primary key preferring the newest `process_date`/`last_updated`, then the newest ingestion — late arrivals and corrected re-deliveries are handled **by construction**;
  - orphan on an **essential** FK → quarantine; orphan on any other FK → set to NULL; both counted.
- **Gold:** `card_products`, `card_transactions` (with `amount_usd` filled and its source), `customer_dim` (canonical country, repeat-complainer flag), `dispute_complaints`, `fraud_alert_candidates`.
- **Export:** a deterministic customer sample to SQLite for the demo (`DEMO_DB`), used by the API as a private copy.
- **Lineage and freshness:** one manifest per run with per-layer counts and contract findings. Proposed policy: a daily batch after each `process_date` closes; late files are absorbed on the next run.

## Consequences
- Re-running without new files is idempotent (tested).
- Update correctness is tested with a **clearly labelled synthetic fixture** (`tests/fixtures/raw_mini`): a late file for an earlier day, a corrected re-delivery and a new column. A real earlier version of the dataset (`data_backup_20260831/`) is also available to validate this with organizer data.
- Findings on the full data: 99.99% of customers point to a non-existent registration branch (a generator defect, hence "essential FK" rather than "required column" decides quarantine); no duplicates were found in any table despite the dictionary's ~2%.
- Spanish domain values that diverge from the dictionary are reported, not silently fixed in silver; business normalisation happens in gold.
