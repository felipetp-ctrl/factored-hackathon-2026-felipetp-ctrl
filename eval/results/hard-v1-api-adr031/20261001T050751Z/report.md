# Evaluation report

> **Offline simulation** on the gold demo store (organizer data) — not production.
> Customers are simulated by an LLM; expected outcomes are derived deterministically from the policy.

| Item | Value |
|---|---|
| timestamp_utc | 20261001T050751Z |
| scenario_set | hard-v1-adr031-posthoc |
| scenarios | 7 |
| data | gold demo store (organizer data) |
| repeats | 2 |
| systems | proposed |
| jobs_not_run_spend_cap | 0 |
| proposed_nlu | claude-haiku-4-5 / nlu-v4 |
| baseline | claude-haiku-4-5 / naive-v1 |
| customer_simulator | claude-sonnet-5 |
| simulator_cost_usd | 0.1002 |
| cost_assumptions | Anthropic list prices (USD/MTok): haiku-4-5 1/5, sonnet-5 2/10; system cost only |

## Headline metrics

| Metric | proposed |
|---|---|
| n_cases | 14 |
| n_in_scope | 14 |
| correct | 14/14 |
| safe_automated_resolution | 14/14 |
| safe_automated_resolution_rate | 1.0 |
| automation_attempted | 14/14 |
| containment | 14/14 |
| escalation_correct | 0/0 |
| escalation_missed | 0/0 |
| escalation_unnecessary | 0/14 |
| unsafe | 0/14 |
| unsafe_reasons | {} |
| errors | 0 |
| turn_latency_ms_p50 | 3086.7 |
| turn_latency_ms_p95 | 4760.8 |
| cost_usd_total | 0.1869 |
| cost_usd_per_attempted_case | 0.01335 |
| cost_usd_per_safe_resolution | 0.01335 |

## By run (repeated-run variability)

| System | Group | n | correct | safe resolution | unsafe | escalation missed |
|---|---|---|---|---|---|---|
| proposed | 0 | 7 | 7/7 | 7/7 | 0/7 | 0/0 |
| proposed | 1 | 7 | 7/7 | 7/7 | 0/7 | 0/0 |

## By language

| System | Group | n | correct | safe resolution | unsafe | escalation missed |
|---|---|---|---|---|---|---|
| proposed | es | 6 | 6/6 | 6/6 | 0/6 | 0/0 |
| proposed | pt | 8 | 8/8 | 8/8 | 0/8 | 0/0 |

## By country

| System | Group | n | correct | safe resolution | unsafe | escalation missed |
|---|---|---|---|---|---|---|
| proposed | Argentina | 2 | 2/2 | 2/2 | 0/2 | 0/0 |
| proposed | Colombia | 8 | 8/8 | 8/8 | 0/8 | 0/0 |
| proposed | Mexico | 4 | 4/4 | 4/4 | 0/4 | 0/0 |

## By customer segment

| System | Group | n | correct | safe resolution | unsafe | escalation missed |
|---|---|---|---|---|---|---|
| proposed | Basic | 10 | 10/10 | 10/10 | 0/10 | 0/0 |
| proposed | Plus | 2 | 2/2 | 2/2 | 0/2 | 0/0 |
| proposed | Premium | 2 | 2/2 | 2/2 | 0/2 | 0/0 |

## By category

| System | Group | n | correct | safe resolution | unsafe | escalation missed |
|---|---|---|---|---|---|---|
| proposed | ambiguous | 2 | 2/2 | 2/2 | 0/2 | 0/0 |
| proposed | normal | 12 | 12/12 | 12/12 | 0/12 | 0/0 |

## Component evaluation (proposed system)

| Component | Claude Haiku NLU | Keyword baseline | Rule NLU (fallback, rules only) | Rule NLU + intent-v2 (fallback) |
|---|---|---|---|---|
| Dispute reason accuracy | 100.0% (12/12) | 100.0% (12/12) | 100.0% (12/12) | 100.0% (12/12) |
| Out-of-scope recall | — | — | — | — |
| Out-of-scope false-positive rate | 0.0% (0/14) | 0.0% (0/14) | 0.0% (0/14) | 0.0% (0/14) |
| Human-request detection | — | — | — | — |

| Component | Result |
|---|---|
| Transaction identification (NLU + search) | 100.0% (12/12) |
| Injection flag true-positive rate (rules) | — |
| Injection flag false-positive rate (rules) | 0.0% (0/44) |
| Language rules accuracy when decided | 100.0% (47/47) |
| Language rules undecided share | 2.1% (1/48) |
| NLU language accuracy (first turn) | 100.0% (14/14) |

Reason confusion (expected → NLU prediction): `{'FRAUD_CNP': {'FRAUD_CNP': 10}, 'FRAUD_CP': {'FRAUD_CP': 2}}`


## Failures (incorrect or unsafe)

| System | Scenario | Run | Expected | Actual | Unsafe | Error |
|---|---|---|---|---|---|---|
