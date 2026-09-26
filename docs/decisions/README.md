# Decision Log

Cada decisão relevante do projeto é registrada aqui, com alternativas e trade-offs.

| ADR | Decisão | Status |
|---|---|---|
| [001](ADR-001-workflow.md) | Workflow: intake de disputa de transação | aceito |
| [002](ADR-002-automation-boundary.md) | Intake completo + bloqueio de cartão confirmado; sem movimentação de dinheiro | aceito |
| [003](ADR-003-multichannel.md) | Sistema multicanal: chat + PQR + proativo | aceito |
| [004](ADR-004-hybrid-orchestration.md) | Orquestração híbrida: máquina de estados dona das escritas; LLM só leitura | aceito |
| [005](ADR-005-models.md) | Claude (Haiku/Sonnet) + ML local | aceito |
| [006](ADR-006-data-stack.md) | DuckDB + Parquet + Pandera, sem Spark/dbt | aceito |
| [007](ADR-007-frontend.md) | Next.js, estilo inspirado na Factored, marca LATAM Bank | aceito |
| [008](ADR-008-policy-order.md) | Ordem de avaliação da política e limiares placeholder | aceito |
| [009](ADR-009-evaluation-method.md) | Avaliação: simulador LLM, oracle determinístico, dev vs. teste | aceito |
| [010](ADR-010-llm-interprets-templates-speak.md) | O LLM interpreta; templates falam | aceito |
| [011](ADR-011-api-roles-and-test-identity.md) | API: papéis, identidade de teste e limites | aceito |
| [012](ADR-012-data-pipeline.md) | Pipeline: contratos em SQL/DuckDB, incremental, silver recomputada | aceito |
| [013](ADR-013-policy-v2-calibration.md) | Política v2: limite único US$ 450 calibrado nos dados | aceito |
