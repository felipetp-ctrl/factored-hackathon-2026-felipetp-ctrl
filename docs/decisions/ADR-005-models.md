# ADR-005 — Models: Claude + local ML
- **Status:** accepted · **Date:** 2026-09-25

## Context
No API credits are provided. The challenge requires at least one learned component against a baseline, privacy in external calls, and measured cost and latency.

## Decision
- Claude Haiku 4.5 for understanding customer messages; Claude Sonnet 5 for the customer simulator (and a future judge).
- Local, deterministic components where they suffice (PII masking, language detection, injection signals).
- The learned component is deferred (see the EDA findings in the data quality report: the dataset's text is templated and its only learnable signal is `fraud_score`); candidate: fraud model over `transactions` vs. the bank's `fraud_score`.

## Alternatives considered
- **Other providers:** no clear advantage in Spanish/Portuguese.
- **Local models only:** weaker conversational quality in Spanish/Portuguese.

## Consequences
- PII is masked before any external call, even though the dataset is synthetic.
- The API key lives in an environment variable with a spending limit.
