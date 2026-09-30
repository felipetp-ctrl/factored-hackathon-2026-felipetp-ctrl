# Operating the dispute service

What exists today, what it would take to run it for a real bank, and the numbers behind each claim.
Everything measured here is an offline measurement on a laptop or a simulation; nothing was measured in production.

## Runtime shape

| Component | Today | Scaling path |
|---|---|---|
| API | One FastAPI process (uvicorn), Docker image verified | Several stateless replicas behind a load balancer once state moves out of memory |
| Conversation state, rate limit, idempotency cache | In process memory | Redis (TTL = session TTL) or Postgres |
| Operational store + audit log | SQLite (fixture or gold sample copy) | Postgres; audit table append-only via permissions + triggers, partitioned by month |
| Language model | Claude Haiku 4.5, one structured call per customer turn | Unchanged; add prompt caching once the system prompt passes the model's minimum cacheable length |
| Fallback NLU | Rules + trained intent classifier `intent-v2` (1.5 MB JSON, 0.2 ms, pure Python; `INTENT_MODEL=off` disables) | Retrain with `make train` on real, consented messages; version recorded on every turn (`rules+intent-v2`) |
| Data pipeline | DuckDB batch, full dataset in ~20 s on a laptop | Same code on a scheduled job; switch silver to per-partition MERGE past ~100M rows |

## Capacity (estimates, labelled as such)

- Per customer turn: 1 model call, measured p50 ≈ 2.0 s and p95 ≈ 2.9 s end to end (dev run, 88 simulated conversations). Latency is dominated by the model call.
- Cost: ≈ US$ 0.003 per turn, ≈ US$ 0.009–0.017 per resolved dispute (Haiku list prices, measured token usage).
- Throughput limit is the model provider's rate limit for the account, not the API: the Python process spends < 50 ms per turn outside the model call.
- The circuit breaker opens after 3 consecutive model failures for 60 s. Since v0.0.2 the rule-based NLU takes over
  during that window, when a spend cap is reached (`LLM_BUDGET_USD` total, `LLM_DAILY_BUDGET_USD` per day,
  `LLM_WORKSPACE_BUDGET_USD` per demo workspace; ADR-026, reported in `/health`), or when the
  API key is missing (ADR-017); every turn records which NLU read it. Without a fallback configured, turns are handed
  to a person with a reference.

## Monitoring

Available now at `GET /agent/metrics` (agent key) and in the Operations view:

- replies by outcome (done, ask, confirm, handoff, ineligible, out of scope, retry, reauth)
- handoffs by reason, verified vs failed actions
- model calls, model cost, reply latency p50/p95

Learned classifier (`intent_classifier` in `/agent/metrics`): turns read, share accepted at the 0.60 threshold, mean
confidence, label mix and PSI of the confidence distribution against the training reference (alarm > 0.2 from 30
turns). See `docs/model_card_intent-v2.md`.

Alerts to add in production:

| Signal | Threshold (initial) | Why |
|---|---|---|
| `actions_failed` rate | > 1% of actions over 15 min | bank tool degradation; each failure already goes to a person |
| `nlu_failed` / `retry` replies | > 5% over 5 min | model outage or quota; breaker behaviour |
| handoff share | ± 50% vs 7-day baseline | policy or model drift |
| injection-flag share | spike vs baseline | attack campaign |
| p95 reply latency | > 6 s | customer experience |
| cost per resolved dispute | > 2× baseline | prompt or traffic change |

Tracing: every conversation has a `trace_id` (the conversation id) and every step is written to the audit log
(`/agent/traces/{id}`): redacted customer message, model output with tokens/latency/cost, policy decision with
rule ids and inputs, actions with verification status, handoff package. HTTP requests carry `X-Request-ID` in
structured JSON logs. OpenTelemetry export (Langfuse) is not wired yet.

## Access control

| Who | How | Can reach |
|---|---|---|
| Customer | Session token (test identity provider today; bank OIDC + MFA in production) | Own conversation, own cases, own transactions through the tools |
| Agent / operations | `X-Agent-Key` today; SSO with per-agent roles in production | Handoff queue and resolve actions, traces, metrics, PQR batch, fraud alerts |
| Public demo (`DEMO_MODE=true`) | No key; each browser tab has its own workspace copy of the synthetic data | The agent views of its own workspace only. Never enable with real data |
| Language model | No credentials at all | Receives redacted text and case context; cannot call write tools |

Ownership is enforced in the tool layer on every call (tested for cross-customer access, forged, expired and swapped sessions).

## Data retention (proposal)

| Data | Retention | Note |
|---|---|---|
| Customer messages (already redacted) | 90 days | Needed for disputes that reopen |
| Audit log (decisions, actions) | 5 years | Typical banking record-keeping; append-only |
| Model inputs/outputs at the provider | Provider default | Zero-data-retention agreement required for production |
| Evaluation transcripts | Kept in the repo | Synthetic customers only |

## Remaining work before production

1. Real identity (OIDC/MFA) and per-agent SSO; remove the test identity provider and demo mode; record the real agent id
   on agent actions (the demo records `agent-demo`).
2. Move conversation state, rate limit and idempotency to Redis/Postgres; horizontal scaling.
3. Replace mock tools with the bank's case-management and card-management APIs (same contracts).
4. Legal review of the dispute policy (the current one is synthetic and calibrated only on value distributions).
5. Human review sample of real conversations per week; drift dashboard on handoff reasons.
6. OpenTelemetry export and alerting as listed above.
7. Name detection in PII masking (structured identifiers only today).
8. Portuguese evaluation with real (not simulated) customer messages; the dataset has none.
9. Human review of a sample of the intent corpus labels (`ml/corpus/human-review.tsv`) and of the hard-v1 personas;
   the Claude path on hard-v1 was measured with the NLU played by a Claude Haiku subagent — re-run it once against
   the API to confirm (ADR-022).
10. Monitor the precision of confirmed fraud alerts (threshold 35 relies on the organizer score's behaviour, ADR-020).
