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
