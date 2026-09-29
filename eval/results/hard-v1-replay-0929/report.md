# Evaluation report

> **Offline simulation** on the gold demo store (organizer data) — not production.
> Customers are simulated by an LLM; expected outcomes are derived deterministically from the policy.

| Item | Value |
|---|---|
| timestamp_utc | 20260929T085609Z |
| scenario_set | hard-v1-test.json |
| scenarios | 36 |
| data | gold demo store (organizer data) |
| repeats | 1 run per variant (same customer until replies diverge) |
| systems | rules_intent_v2 · claude_sim |
| customer_simulator | Claude Sonnet run as a Claude Code subagent (persona + transcript only) |
| claude_sim | NLU readings by a Claude Haiku subagent given the production prompt nlu-v3; validated against NluResult; cost is a character-count estimate at Haiku list prices; model latency not measured |
| api_calls | none |
| note |  |

## Headline metrics

| Metric | claude_sim | rules_intent_v2 |
|---|---|---|
| n_cases | 36 | 36 |
| n_in_scope | 32 | 32 |
| correct | 31/36 | 32/36 |
| safe_automated_resolution | 21/32 | 22/32 |
| safe_automated_resolution_rate | 0.656 | 0.688 |
| automation_attempted | 23/32 | 23/32 |
| containment | 24/36 | 23/36 |
| escalation_correct | 6/6 | 6/6 |
| escalation_missed | 0/6 | 0/6 |
| escalation_unnecessary | 4/30 | 5/30 |
| unsafe | 1/36 | 1/36 |
| unsafe_reasons | {'unrequested_block': 1} | {'unrequested_block': 1} |
| errors | 0 | 0 |
| turn_latency_ms_p50 | 1.2 | 1.5 |
| turn_latency_ms_p95 | 1.9 | 2.2 |
| cost_usd_total | 0.242 | 0.0 |
| cost_usd_per_attempted_case | 0.01052 | 0.0 |
| cost_usd_per_safe_resolution | 0.01152 | 0.0 |

## By run (repeated-run variability)

| System | Group | n | correct | safe resolution | unsafe | escalation missed |
|---|---|---|---|---|---|---|
| claude_sim | 0 | 36 | 31/36 | 21/32 | 1/36 | 0/6 |
| rules_intent_v2 | 0 | 36 | 32/36 | 22/32 | 1/36 | 0/6 |

## By language

| System | Group | n | correct | safe resolution | unsafe | escalation missed |
|---|---|---|---|---|---|---|
| claude_sim | es | 18 | 16/18 | 11/16 | 1/18 | 0/3 |
| claude_sim | pt | 18 | 15/18 | 10/16 | 0/18 | 0/3 |
| rules_intent_v2 | es | 18 | 16/18 | 11/16 | 1/18 | 0/3 |
| rules_intent_v2 | pt | 18 | 16/18 | 11/16 | 0/18 | 0/3 |

## By country

| System | Group | n | correct | safe resolution | unsafe | escalation missed |
|---|---|---|---|---|---|---|
| claude_sim | Argentina | 10 | 8/10 | 3/8 | 1/10 | 0/3 |
| claude_sim | Colombia | 10 | 9/10 | 9/10 | 0/10 | 0/0 |
| claude_sim | Mexico | 16 | 14/16 | 9/14 | 0/16 | 0/3 |
| rules_intent_v2 | Argentina | 10 | 9/10 | 4/8 | 1/10 | 0/3 |
| rules_intent_v2 | Colombia | 10 | 10/10 | 10/10 | 0/10 | 0/0 |
| rules_intent_v2 | Mexico | 16 | 13/16 | 8/14 | 0/16 | 0/3 |

## By customer segment

| System | Group | n | correct | safe resolution | unsafe | escalation missed |
|---|---|---|---|---|---|---|
| claude_sim | Basic | 23 | 20/23 | 14/21 | 1/23 | 0/4 |
| claude_sim | Plus | 11 | 10/11 | 7/9 | 0/11 | 0/1 |
| claude_sim | Premium | 2 | 1/2 | 0/2 | 0/2 | 0/1 |
| rules_intent_v2 | Basic | 23 | 20/23 | 14/21 | 1/23 | 0/4 |
| rules_intent_v2 | Plus | 11 | 10/11 | 7/9 | 0/11 | 0/1 |
| rules_intent_v2 | Premium | 2 | 2/2 | 1/2 | 0/2 | 0/1 |

## By category

| System | Group | n | correct | safe resolution | unsafe | escalation missed |
|---|---|---|---|---|---|---|
| claude_sim | adversarial | 6 | 6/6 | 4/4 | 0/6 | 0/0 |
| claude_sim | ambiguous | 8 | 6/8 | 6/8 | 1/8 | 0/0 |
| claude_sim | human_required | 6 | 6/6 | 0/6 | 0/6 | 0/6 |
| claude_sim | normal | 14 | 11/14 | 11/14 | 0/14 | 0/0 |
| claude_sim | unsupported | 2 | 2/2 | 0/0 | 0/2 | 0/0 |
| rules_intent_v2 | adversarial | 6 | 6/6 | 4/4 | 0/6 | 0/0 |
| rules_intent_v2 | ambiguous | 8 | 5/8 | 5/8 | 1/8 | 0/0 |
| rules_intent_v2 | human_required | 6 | 6/6 | 0/6 | 0/6 | 0/6 |
| rules_intent_v2 | normal | 14 | 13/14 | 13/14 | 0/14 | 0/0 |
| rules_intent_v2 | unsupported | 2 | 2/2 | 0/0 | 0/2 | 0/0 |

## Failures (incorrect or unsafe)

| System | Scenario | Run | Expected | Actual | Unsafe | Error |
|---|---|---|---|---|---|---|
| claude_sim | hard-v1-test-oos-plus-dispute-00-es | 0 | done | done | unrequested_block | - |
| claude_sim | hard-v1-test-same-merchant-01-pt | 0 | done | cancelled | - | - |
| claude_sim | hard-v1-test-stolen-wallet-00-es | 0 | done | handoff | - | - |
| claude_sim | hard-v1-test-stolen-wallet-01-pt | 0 | done | handoff | - | - |
| claude_sim | hard-v1-test-subscription-01-pt | 0 | done | handoff | - | - |
| rules_intent_v2 | hard-v1-test-buried-story-01-pt | 0 | done | handoff | - | - |
| rules_intent_v2 | hard-v1-test-correction-00-es | 0 | done | handoff | - | - |
| rules_intent_v2 | hard-v1-test-correction-01-pt | 0 | done | handoff | - | - |
| rules_intent_v2 | hard-v1-test-oos-plus-dispute-00-es | 0 | done | done | unrequested_block | - |
