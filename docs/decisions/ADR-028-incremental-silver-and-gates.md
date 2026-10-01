# ADR-028 — Incremental silver, quality gates before publishing, a generated catalog
- **Status:** accepted · **Date:** 2026-10-01 · extends ADR-012

## Context
ADR-012 read only new bronze files but recomputed all of silver on every run and published gold unconditionally. That
is correct and fast at 4.4M transactions, but it leaves three questions a data engineer would ask unanswered: does an
incremental transformation give the same answer as a rebuild, what stops a bad delivery from reaching the service, and
where does a consumer read what each table guarantees.

## Decision
1. **Key-scoped incremental silver.** Every silver rule (newest-wins, identity, contract checks, foreign keys) depends
   only on the versions of one key and on its parents. A run recomputes the keys in this run's bronze batch plus child
   keys whose parent changed (new, corrected or quarantined parent), from **all** their bronze versions, and keeps every
   other row. Quarantine files are merged the same way. `--full` (and the first run, or a parent rebuilt in full)
   recomputes everything. Batch-scoped counters (cast failures, nulled FKs) say which scope they cover.
2. **Write-audit-publish.** Gold is written to `gold.__staging__`, audited by `pipeline/gates.py`, then swapped in by
   two renames. Blocking gates: **row conservation** per table (bronze = rows without a key + superseded versions +
   silver + quarantined keys: nothing disappears unaccounted), **volume** (≤ 1% fewer rows than the last published run),
   core gold not empty, USD amount present on ≥ 99% of card transactions, unique transaction ids. Warnings: quarantine
   share > 5%, stale partitions. A blocked run keeps the previous gold, skips the demo export and exits with code 2.
3. **Run history.** `_state/runs.jsonl` (status, mode, rows per table, seconds per step, failed gates) next to the
   per-run manifest; the volume gate reads it.
4. **Catalog from the contracts.** `docs/data_catalog.md` is generated from `contracts.py` and the last published
   manifest: grain, key, newest-wins column, identity columns, every column's type, requirement, domain or range and
   reference (and whether an orphan is quarantined or nulled), gold lineage and consumers.
5. **Data CI.** Every push runs the pipeline CLI on the labelled fixture; it must publish.

## Evidence
- Tests (fixture): incremental equals a full rebuild of the same bronze after a late, corrected delivery, an orphan
  whose parents arrive one run later, and a card re-delivered with another owner (its charges quarantined through the
  foreign key); a run with no new files recomputes nothing; rows are conserved; a delivery that hands every card to
  someone else is **blocked** and the previous gold is byte-identical.
- Organizer data ([proof](../analysis/incremental-silver.md), `make data-proof`): the last week of every fact table
  held back, delivered, and run incrementally: **identical** to the full rebuild on all 5,741,913 rows; 4.5 s
  (29,159 transaction keys recomputed) vs 12.1 s.
- Gates on the full data: all pass; 13 of 1,547,432 card transactions have no USD amount (no daily FX rate), within
  the 1% limit and reported.

## Trade-offs
- Each silver table is still one Parquet file, rewritten on every run; the saving is compute, not I/O. Past ~100M rows,
  partition silver by month so only touched partitions are rewritten.
- Schedule: production would run `make data` daily after `process_date` closes (cron or an orchestrator task with
  the exit code as the success signal). The organizer bucket needs credentials, so CI runs the fixture instead.
