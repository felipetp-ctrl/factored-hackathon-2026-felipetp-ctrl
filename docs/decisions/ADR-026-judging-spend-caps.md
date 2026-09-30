# ADR-026 — Spend caps for the judging window
- **Status:** accepted · **Date:** 2026-09-30

## Context
The project has US$ 10 of Anthropic credit for everything left: at most half for the team's own evaluation runs, the
rest kept for judges using the public demo until the ceremony (2026-10-16). The only guard so far was one in-memory
total (`LLM_BUDGET_USD`, default 20) shared by every visitor: above the credit, reset by every restart, and one busy
visitor (or a script) could use all of it in an afternoon, leaving later judges on the free reader.

## Decision
Three layers, each switching the service to the free reader (rules + intent-v2, ADR-017/019) instead of failing:
1. **Provider limit (the hard ceiling).** The deployed key lives in its own Anthropic workspace with a US$ 5 spend
   limit; evaluation runs use a key in another workspace with its own limit. When a limit is reached the API refuses,
   the circuit breaker opens and the free reader takes over (already tested).
2. **Process total and daily cap.** `LLM_BUDGET_USD=4.5` (below the provider limit, so the switch happens before API
   errors) and `LLM_DAILY_BUDGET_USD=0.6` (one day cannot use up the window).
3. **Per workspace.** Each demo workspace (browser tab) gets `LLM_WORKSPACE_BUDGET_USD=0.25`, counted against the
   total.

`/health` reports `llm_budget` (spent, today, limits, exhausted) so spend can be watched without the Console.

## Numbers
A turn costs about US$ 0.003 (Haiku 4.5, measured in test-v2); a judge walking all seven scenarios uses about 30 turns,
US$ 0.10. The daily cap covers about 200 turns (7 full tours a day); a workspace about 80 turns; the total about
1,500 turns (about 45 full tours).

## Trade-offs
- In-memory counters reset on restart or deploy; layer 1 is why that is acceptable. Persisting them would need a
  database the free plan does not keep across deploys.
- A visitor who changes workspace id gets a new share; the daily cap bounds that.
- Past a cap the demo keeps working with the free reader, which understands fewer phrasings (hard-v1: 30/36 vs 31/36);
  the top bar says "AI off, rules reading".
