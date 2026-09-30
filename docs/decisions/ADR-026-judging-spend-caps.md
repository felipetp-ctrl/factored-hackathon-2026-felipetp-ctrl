# ADR-026 — Spend caps for the judging window
- **Status:** accepted · **Date:** 2026-09-30

## Context
The project has US$ 10 of Anthropic credit for everything left: at most half for the team's own evaluation runs, the
rest for judges using the public demo until the ceremony (2026-10-16). The only guard so far was one in-memory total
(`LLM_BUDGET_USD`, default 20) shared by every visitor: above the credit, reset by every restart and deploy, blind to
evaluation runs on a laptop, and one busy visitor (or a script) could use all of it in an afternoon. No
provider-side spend limit is configured, so the caps in code are the ceiling.

## Decision
A durable **spend ledger** (`spend_ledger.py`): one Postgres table (Render free instance, until 2026-10-30), one row
per day and source (`demo`, `eval`). Every model call of the demo and of evaluation runs is recorded there, so caps
survive restarts and deploys and one ceiling covers both. Caps, each switching the demo to the free reader (rules +
intent-v2, ADR-017/019) instead of failing:

| Cap | Variable | Demo (Render) | Evaluation runs |
|---|---|---|---|
| All sources together | `LLM_GLOBAL_BUDGET_USD` | 9.5 | 9.5 |
| This source | `LLM_BUDGET_USD` | 9.5 (the rest of the credit) | 4.75 (at most half) |
| Per calendar day | `LLM_DAILY_BUDGET_USD` | 1.0 | — |
| Per demo workspace (browser tab) | `LLM_WORKSPACE_BUDGET_USD` | 0.3 | — |

- **Fail closed:** if the ledger cannot be reached at start-up or on a write, the budget counts as exhausted.
- **Evaluation runs** get their Anthropic client from `metering.api_client()`; with `LLM_METER_SOURCE=eval` every call
  (NLU, simulated customer, chatbot baseline) checks the caps first and records its cost after. Past a cap it raises
  `BudgetExceeded`, which is not an API error, so a run stops instead of silently switching to the free reader and
  mixing readers in its results. A model without a list price is refused.
- The 0.5 margin under the credit covers list-price estimates and spend before the ledger existed.
- `/health` reports `llm_budget` (this source, today, all sources, limits, whether it is durable).

## Numbers
A turn costs about US$ 0.003 (Haiku 4.5, measured in test-v2); a judge walking all seven scenarios uses about 30 turns,
US$ 0.10. The daily cap covers about 300 turns (10 full tours a day), a workspace about 100 turns.

## Trade-offs
- One more moving part (a database) in the demo path; a failure degrades to the free reader, never to an error.
- The free Postgres instance expires on 2026-10-30; after that the demo must run with `NLU_MODE=rules` or a new ledger.
- Checks read the ledger at most every 20 s, so concurrent processes can overshoot a cap by a few turns (cents).
- A visitor who changes workspace id gets a new share; the daily cap bounds that.
