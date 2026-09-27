# Evaluation report

> **Offline simulation** on the gold demo store (organizer data) — not production.
> Customers are simulated by an LLM; expected outcomes are derived deterministically from the policy.

| Item | Value |
|---|---|
| timestamp_utc | 20260927T161006Z |
| scenario_set | test-v3 |
| scenarios | 42 |
| data | gold demo store (organizer data) |
| repeats | 1 run per system variant (same customer until the variants' replies diverge) |
| systems | rules_only (fallback NLU, keyword rules) · rules_intent_v2 (fallback NLU + intent-v2 classifier) |
| nlu_mode | rules (no language-model call in the system under test) |
| customer_simulator | Claude Sonnet run as a Claude Code subagent, persona + transcript only |
| api_calls | none from the harness |

## Headline metrics

| Metric | rules_intent_v2 | rules_only |
|---|---|---|
| n_cases | 42 | 42 |
| n_in_scope | 35 | 35 |
| correct | 42/42 | 42/42 |
| safe_automated_resolution | 25/35 | 25/35 |
| safe_automated_resolution_rate | 0.714 | 0.714 |
| automation_attempted | 25/35 | 25/35 |
| containment | 29/42 | 29/42 |
| escalation_correct | 10/10 | 10/10 |
| escalation_missed | 0/10 | 0/10 |
| escalation_unnecessary | 0/32 | 0/32 |
| unsafe | 0/42 | 0/42 |
| unsafe_reasons | {} | {} |
| errors | 0 | 0 |
| turn_latency_ms_p50 | 1.4 | 1.2 |
| turn_latency_ms_p95 | 2.8 | 3.9 |
| cost_usd_total | 0.0 | 0.0 |
| cost_usd_per_attempted_case | 0.0 | 0.0 |
| cost_usd_per_safe_resolution | 0.0 | 0.0 |

## By run (repeated-run variability)

| System | Group | n | correct | safe resolution | unsafe | escalation missed |
|---|---|---|---|---|---|---|
| rules_intent_v2 | 0 | 42 | 42/42 | 25/35 | 0/42 | 0/10 |
| rules_only | 0 | 42 | 42/42 | 25/35 | 0/42 | 0/10 |

## By language

| System | Group | n | correct | safe resolution | unsafe | escalation missed |
|---|---|---|---|---|---|---|
| rules_intent_v2 | es | 21 | 21/21 | 12/17 | 0/21 | 0/5 |
| rules_intent_v2 | pt | 21 | 21/21 | 13/18 | 0/21 | 0/5 |
| rules_only | es | 21 | 21/21 | 12/17 | 0/21 | 0/5 |
| rules_only | pt | 21 | 21/21 | 13/18 | 0/21 | 0/5 |

## By country

| System | Group | n | correct | safe resolution | unsafe | escalation missed |
|---|---|---|---|---|---|---|
| rules_intent_v2 | Argentina | 4 | 4/4 | 3/3 | 0/4 | 0/0 |
| rules_intent_v2 | Colombia | 27 | 27/27 | 18/25 | 0/27 | 0/7 |
| rules_intent_v2 | Mexico | 11 | 11/11 | 4/7 | 0/11 | 0/3 |
| rules_only | Argentina | 4 | 4/4 | 3/3 | 0/4 | 0/0 |
| rules_only | Colombia | 27 | 27/27 | 18/25 | 0/27 | 0/7 |
| rules_only | Mexico | 11 | 11/11 | 4/7 | 0/11 | 0/3 |

## By customer segment

| System | Group | n | correct | safe resolution | unsafe | escalation missed |
|---|---|---|---|---|---|---|
| rules_intent_v2 | Basic | 22 | 22/22 | 14/20 | 0/22 | 0/6 |
| rules_intent_v2 | Plus | 7 | 7/7 | 3/4 | 0/7 | 0/1 |
| rules_intent_v2 | Premium | 3 | 3/3 | 1/2 | 0/3 | 0/1 |
| rules_intent_v2 | Student | 10 | 10/10 | 7/9 | 0/10 | 0/2 |
| rules_only | Basic | 22 | 22/22 | 14/20 | 0/22 | 0/6 |
| rules_only | Plus | 7 | 7/7 | 3/4 | 0/7 | 0/1 |
| rules_only | Premium | 3 | 3/3 | 1/2 | 0/3 | 0/1 |
| rules_only | Student | 10 | 10/10 | 7/9 | 0/10 | 0/2 |

## By category

| System | Group | n | correct | safe resolution | unsafe | escalation missed |
|---|---|---|---|---|---|---|
| rules_intent_v2 | adversarial | 12 | 12/12 | 7/9 | 0/12 | 0/2 |
| rules_intent_v2 | ambiguous | 3 | 3/3 | 3/3 | 0/3 | 0/0 |
| rules_intent_v2 | human_required | 8 | 8/8 | 0/8 | 0/8 | 0/8 |
| rules_intent_v2 | ineligible | 6 | 6/6 | 6/6 | 0/6 | 0/0 |
| rules_intent_v2 | normal | 9 | 9/9 | 9/9 | 0/9 | 0/0 |
| rules_intent_v2 | out_of_scope | 4 | 4/4 | 0/0 | 0/4 | 0/0 |
| rules_only | adversarial | 12 | 12/12 | 7/9 | 0/12 | 0/2 |
| rules_only | ambiguous | 3 | 3/3 | 3/3 | 0/3 | 0/0 |
| rules_only | human_required | 8 | 8/8 | 0/8 | 0/8 | 0/8 |
| rules_only | ineligible | 6 | 6/6 | 6/6 | 0/6 | 0/0 |
| rules_only | normal | 9 | 9/9 | 9/9 | 0/9 | 0/0 |
| rules_only | out_of_scope | 4 | 4/4 | 0/0 | 0/4 | 0/0 |

## Failures (incorrect or unsafe)

| System | Scenario | Run | Expected | Actual | Unsafe | Error |
|---|---|---|---|---|---|---|
