# ADR-006 — Stack de dados: DuckDB + Parquet + Pandera
- **Status:** aceito · **Data:** 2026-09-25

## Contexto
São cerca de 19 milhões de linhas em 13 tabelas, com duplicatas, nulos, chegadas atrasadas e mudança de schema intencionais. O time é solo e não tem orçamento de nuvem.

## Decisão
DuckDB sobre Parquet, com camadas bronze/silver/gold, contratos Pandera, dedup, quarentena de FKs órfãs e `run_manifest.json` para lineage. Store operacional em SQLite, com um subconjunto gold para a demo.

## Alternativas consideradas
- **Spark/Databricks:** escala desnecessária, com custo e setup.
- **dbt:** lineage melhor, mas é mais uma ferramenta para manter sozinho.
- **Postgres:** sem ganho para a demo.

## Consequências
- Roda num laptop e é reprodutível com `make data`.
- A lineage é própria (manifest + `_source_ids`), mais simples que a do dbt. É uma limitação documentada.
