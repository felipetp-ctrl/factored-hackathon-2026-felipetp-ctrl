# Decision log

Every significant decision in the project, with the alternatives considered and the trade-offs.

| ADR | Decision | Status |
|---|---|---|
| [001](ADR-001-workflow.md) | Workflow: card-transaction dispute intake | accepted |
| [002](ADR-002-automation-boundary.md) | Full intake + confirmed card block; no money movement | accepted |
| [003](ADR-003-multichannel.md) | Multichannel system: chat + written complaints (PQR) + proactive alert | accepted |
| [004](ADR-004-hybrid-orchestration.md) | Hybrid orchestration: state machine owns writes; the LLM is read-only | accepted |
| [005](ADR-005-models.md) | Claude (Haiku/Sonnet) + local ML | accepted |
| [006](ADR-006-data-stack.md) | DuckDB + Parquet, no Spark/dbt | accepted (Pandera part superseded by 012) |
| [007](ADR-007-frontend.md) | Next.js, Factored-inspired styling, LATAM Bank brand | accepted (layout superseded by 016) |
| [008](ADR-008-policy-order.md) | Policy evaluation order and placeholder thresholds | accepted (thresholds superseded by 013) |
| [009](ADR-009-evaluation-method.md) | Evaluation: LLM customer simulator, deterministic oracle, dev vs. test | accepted |
| [010](ADR-010-llm-interprets-templates-speak.md) | The LLM interprets; templates speak | accepted |
| [011](ADR-011-api-roles-and-test-identity.md) | API: roles, test identity and limits | accepted |
| [012](ADR-012-data-pipeline.md) | Pipeline: SQL contracts in DuckDB, incremental ingestion, recomputed silver | accepted |
| [013](ADR-013-policy-v2-calibration.md) | Policy v2: single USD 450 threshold calibrated on the data | accepted |
| [014](ADR-014-suspicious-access.md) | Invalid transaction references: same reply, real reason for the agent | accepted |
| [015](ADR-015-pqr-matching.md) | Written complaints: match to a transaction or hand off with a shortlist | accepted |
| [016](ADR-016-judge-facing-demo.md) | Demo: bank app beside the bank side, guided scenarios, agent actions, demo workspaces | accepted |
| [017](ADR-017-rule-fallback-nlu.md) | Free rule-based NLU when the model is down or over budget | accepted |
| [018](ADR-018-conversation-fixes.md) | Conversation fixes: fixed language, polite endings, local formats, visible re-login | accepted |
| [019](ADR-019-learned-intent-classifier.md) | Trained intent/reason classifier inside the free fallback NLU | accepted |
| [020](ADR-020-fraud-label-audit.md) | No fraud model (labels have no behavioural signal); fraud alert threshold 80 → 35 | accepted |
| [021](ADR-021-learnability-scan.md) | Learnability scan: no multivariate signal in the organizer data | accepted |
