# ADR-015 — Written complaints: match to a transaction, otherwise hand off with a shortlist
- **Status:** accepted · **Date:** 2026-09-26

## Context
Real dispute complaints have no transaction id; 34 % have no product and 67 % no claimed amount. Every
`affected_product_id` present belongs to a different customer than the complainant (a dataset defect), and claimed
amounts never match a transaction.

## Decision
- Candidates = the complainant's approved/pending charges in the 120 days before the complaint, narrowed by the product
  **only if it belongs to the complainant**, then by claimed amount ±1 %.
- One candidate → the normal policy path (the filed complaint is the consent to open; the card is never blocked
  asynchronously). Otherwise → handoff `async_missing_info` with up to five candidate ids for the agent.
- A SQL twin of the rule backtests it on all 13,580 real dispute complaints (`pipeline/pqr_backtest.py`).

## Consequences
- Backtest: 15.8 % uniquely matchable, 63.5 % ambiguous (median 2 candidates), 20.7 % none. The written channel cannot
  identify the charge in most cases, which is the data argument for the conversational intake.
- A foreign product reference is ignored rather than trusted; in production it should raise a security alert.
