# hard-v1 on the real API after ADR-031 — post-hoc check

Not a held-out measurement: the 7 scenarios were chosen *because* ADR-031 changes them (the 6 Claude-path conversations
whose replay diverged in `hard-v1-replay-grounding`, plus `stolen-wallet-01-pt`, the unsafe case that motivated it).
Same frozen scenarios (`eval/scenarios/hard-v1-adr031-posthoc.json` is a subset of `hard-v1-test.json`), Claude
Haiku 4.5 reader (nlu-v4), Claude Sonnet 5 customers, 2 runs each, proposed system only, metered on the ledger with a
US$ 0.30 cap (ADR-026).

- **14/14 correct, 0 unsafe**, no unnecessary escalations. Before ADR-031 the same 7 scenarios on the API: 13/14
  correct, 1 unsafe (stolen-wallet-01-pt run 2, opened as card-not-present fraud).
- Card question asked in 8 of 12 dispute conversations (the other 4: the customer had said where the card was).
- stolen-wallet-01-pt: FRAUD_CP and card blocked in both runs. In both, the simulated customer mentioned the theft in
  the first message, so the **summary-correction path was not exercised** here; it is covered by the unit test only.
- Turn latency p50 3.1 s / p95 4.8 s; model cost US$ 0.013 per resolved case; total spend of this check US$ 0.287
  (system + simulated customers).

Report: [`20261001T050751Z/report.md`](20261001T050751Z/report.md).
