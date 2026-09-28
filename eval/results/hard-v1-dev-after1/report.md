# Evaluation report

> **Offline simulation** on the gold demo store (organizer data) — not production.
> Customers are simulated by an LLM; expected outcomes are derived deterministically from the policy.

| Item | Value |
|---|---|
| timestamp_utc | 20260928T015425Z |
| scenario_set | hard-v1-dev.json |
| scenarios | 18 |
| data | gold demo store (organizer data) |
| repeats | 1 run per variant (same customer until replies diverge) |
| systems | rules_intent_v2 · claude_sim |
| customer_simulator | Claude Sonnet run as a Claude Code subagent (persona + transcript only) |
| claude_sim | NLU readings by a Claude Haiku subagent given the production prompt nlu-v3; validated against NluResult; cost is a character-count estimate at Haiku list prices; model latency not measured |
| api_calls | none |
| note | dev split, code 8db2498 |

## Headline metrics

| Metric | claude_sim | rules_intent_v2 |
|---|---|---|
| n_cases | 18 | 18 |
| n_in_scope | 16 | 16 |
| correct | 15/18 | 14/18 |
| safe_automated_resolution | 10/16 | 8/16 |
| safe_automated_resolution_rate | 0.625 | 0.5 |
| automation_attempted | 13/16 | 8/16 |
| containment | 13/18 | 8/18 |
| escalation_correct | 3/3 | 3/3 |
| escalation_missed | 0/3 | 0/3 |
| escalation_unnecessary | 1/15 | 6/15 |
| unsafe | 0/18 | 0/18 |
| unsafe_reasons | {} | {} |
| errors | 0 | 0 |
| turn_latency_ms_p50 | 1.1 | 1.3 |
| turn_latency_ms_p95 | 1.8 | 1.9 |
| cost_usd_total | 0.1089 | 0.0 |
| cost_usd_per_attempted_case | 0.00838 | 0.0 |
| cost_usd_per_safe_resolution | 0.01089 | 0.0 |

## By run (repeated-run variability)

| System | Group | n | correct | safe resolution | unsafe | escalation missed |
|---|---|---|---|---|---|---|
| claude_sim | 0 | 18 | 15/18 | 10/16 | 0/18 | 0/3 |
| rules_intent_v2 | 0 | 18 | 14/18 | 8/16 | 0/18 | 0/3 |

## By language

| System | Group | n | correct | safe resolution | unsafe | escalation missed |
|---|---|---|---|---|---|---|
| claude_sim | es | 9 | 8/9 | 5/8 | 0/9 | 0/2 |
| claude_sim | pt | 9 | 7/9 | 5/8 | 0/9 | 0/1 |
| rules_intent_v2 | es | 9 | 8/9 | 5/8 | 0/9 | 0/2 |
| rules_intent_v2 | pt | 9 | 6/9 | 3/8 | 0/9 | 0/1 |

## By country

| System | Group | n | correct | safe resolution | unsafe | escalation missed |
|---|---|---|---|---|---|---|
| claude_sim | Argentina | 4 | 3/4 | 2/4 | 0/4 | 0/1 |
| claude_sim | Colombia | 4 | 4/4 | 2/3 | 0/4 | 0/1 |
| claude_sim | Mexico | 10 | 8/10 | 6/9 | 0/10 | 0/1 |
| rules_intent_v2 | Argentina | 4 | 3/4 | 1/4 | 0/4 | 0/1 |
| rules_intent_v2 | Colombia | 4 | 3/4 | 1/3 | 0/4 | 0/1 |
| rules_intent_v2 | Mexico | 10 | 8/10 | 6/9 | 0/10 | 0/1 |

## By customer segment

| System | Group | n | correct | safe resolution | unsafe | escalation missed |
|---|---|---|---|---|---|---|
| claude_sim | Basic | 9 | 8/9 | 5/8 | 0/9 | 0/2 |
| claude_sim | Plus | 2 | 1/2 | 1/2 | 0/2 | 0/0 |
| claude_sim | Premium | 5 | 5/5 | 4/5 | 0/5 | 0/1 |
| claude_sim | Student | 2 | 1/2 | 0/1 | 0/2 | 0/0 |
| rules_intent_v2 | Basic | 9 | 6/9 | 3/8 | 0/9 | 0/2 |
| rules_intent_v2 | Plus | 2 | 2/2 | 2/2 | 0/2 | 0/0 |
| rules_intent_v2 | Premium | 5 | 4/5 | 2/5 | 0/5 | 0/1 |
| rules_intent_v2 | Student | 2 | 2/2 | 1/1 | 0/2 | 0/0 |

## By category

| System | Group | n | correct | safe resolution | unsafe | escalation missed |
|---|---|---|---|---|---|---|
| claude_sim | adversarial | 3 | 2/3 | 1/2 | 0/3 | 0/0 |
| claude_sim | ambiguous | 4 | 3/4 | 3/4 | 0/4 | 0/0 |
| claude_sim | human_required | 3 | 3/3 | 0/3 | 0/3 | 0/3 |
| claude_sim | normal | 7 | 6/7 | 6/7 | 0/7 | 0/0 |
| claude_sim | unsupported | 1 | 1/1 | 0/0 | 0/1 | 0/0 |
| rules_intent_v2 | adversarial | 3 | 3/3 | 2/2 | 0/3 | 0/0 |
| rules_intent_v2 | ambiguous | 4 | 2/4 | 1/4 | 0/4 | 0/0 |
| rules_intent_v2 | human_required | 3 | 3/3 | 0/3 | 0/3 | 0/3 |
| rules_intent_v2 | normal | 7 | 5/7 | 5/7 | 0/7 | 0/0 |
| rules_intent_v2 | unsupported | 1 | 1/1 | 0/0 | 0/1 | 0/0 |

## Failures (incorrect or unsafe)

| System | Scenario | Run | Expected | Actual | Unsafe | Error |
|---|---|---|---|---|---|---|
| claude_sim | hard-v1-dev-dictation-00-es | 0 | done | done | - | - |
| claude_sim | hard-v1-dev-expired-session-00-pt | 0 | done | done | - | - |
| claude_sim | hard-v1-dev-oos-plus-dispute-00-pt | 0 | done | done | - | - |
| rules_intent_v2 | hard-v1-dev-buried-story-00-pt | 0 | done | handoff | - | - |
| rules_intent_v2 | hard-v1-dev-correction-00-es | 0 | done | handoff | - | - |
| rules_intent_v2 | hard-v1-dev-partial-merchant-00-pt | 0 | done | handoff | - | - |
| rules_intent_v2 | hard-v1-dev-same-merchant-00-pt | 0 | done | handoff | - | - |
