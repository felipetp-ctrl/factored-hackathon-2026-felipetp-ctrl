# ADR-003 — Multichannel system: chat + written complaints (PQR) + proactive alert
- **Status:** accepted · **Date:** 2026-09-25

## Context
The organizers ask for "a customer-service system, not a chatbot". The dataset already holds 67k written complaints with historical human outcomes.

## Decision
One core with three entry points:
- **Chat** in Spanish/Portuguese (conversational requirements);
- **PQR inbox** (D1): batch triage of written complaints; it never clarifies synchronously — missing information means a handoff (`async_missing_info`);
- **Proactive alert** (D3): recent transactions with a high `fraud_score` trigger a "was it you?" message.

## Alternatives considered
- **Chat only:** cheaper, but closer to a chatbot and ignores the dataset's text.
- **Post-call transcript as a channel:** redundant with PQR.
- **Voice:** no audio in the dataset, high risk.

## Consequences
- The channels differ only in the state-machine entry state; marginal cost is small.
- Caveat found in the EDA: complaint descriptions are templated (5 distinct texts) and complaints carry no `transaction_id`, so the PQR value is operational (matching and policy), not language understanding.
