# ADR-006 — Data stack: DuckDB + Parquet
- **Status:** accepted · **Date:** 2026-09-25 · the Pandera part is superseded by ADR-012

## Context
About 19M rows in 13 tables with intentional duplicates, nulls, late arrivals and schema evolution. Solo team, no cloud budget.

## Decision
DuckDB over Parquet with bronze/silver/gold layers, data contracts, dedup, quarantine and a run manifest for lineage. SQLite operational store with a gold sample for the demo.

## Alternatives considered
- **Spark/Databricks:** unnecessary scale, cost and setup.
- **dbt:** better lineage, but one more tool to maintain alone.
- **Postgres:** no gain for the demo.

## Consequences
- Runs on a laptop and is reproducible with `make data` (full dataset in ~20 s).
- Lineage is home-made (manifest + lineage columns), simpler than dbt; a documented limitation.
