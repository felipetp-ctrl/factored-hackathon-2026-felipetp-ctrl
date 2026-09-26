# ADR-013 — Policy `disputes_v2`: single USD 450 threshold calibrated on the data
- **Status:** accepted · **Date:** 2026-09-26 · `disputes_v1` kept for reproducibility

## Context
`disputes_v1` had per-country amount thresholds chosen a priori (MX 500, CO 400, AR 300 USD). Running the full pipeline revealed:
1. **Mexican customers' transactions are in USD with a null `amount_usd`** (541,812 card purchases), and ~5% of ARS/COP transactions also lack `amount_usd`. Uncorrected, no Mexican dispute would ever trigger the amount rule.
2. After the fix (gold: reported value → USD identity → daily FX, with `amount_usd_source`), card-purchase amounts in USD are **~U(0, 500) in all three countries** (p50 ≈ 252, p90 ≈ 450, p95 ≈ 475).

## Decision
- A single threshold of **USD 450** (p90): about 10% of purchase disputes go to a person for amount, equally in every country.
- `max_disputes_30d = 3` is kept. The data never exceeds 2 transaction complaints per customer in 30 days, so the rule is a guard that does not fire on history.

## Alternatives considered
- **Keep v1's per-country thresholds:** they would escalate 0% (MX), 20% (CO) and 40% (AR) of disputes with no risk difference in the data — an unjustifiable disparity between customer segments, exactly what the challenge asks us to investigate.
- **Threshold at p95 (USD 475):** more automation, less margin on the highest-value purchases.

## Consequences
- The calibration is descriptive (value distribution), not loss-based: the data shows no fraud signal correlated with amount (`is_fraud` ≈ 0.1% in every band).
- Evaluation scenarios are labelled with the policy in force; the generator records the version in its metadata.
