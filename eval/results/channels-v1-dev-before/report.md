# channels-v1 · dev

Written complaints and fraud-alert answers, run end to end with no language-model calls. Expected outcomes from the policy on real transactions; customer text by an independent author. Offline simulation.

## Written complaints (n = 12)

| Reader | Correct outcome | Safe automated resolution | Unsafe | Missed handoffs | Unnecessary handoffs | Handoff reason matches | Script gaps |
|---|---|---|---|---|---|---|---|
| rules + intent-v2 (deployed) | 10/12 (83%) | 5/12 (42%) | 2/12 | 1/6 | 0/6 | 4/5 | 0 |
| keyword rules only (baseline) | 9/12 (75%) | 4/12 (33%) | 1/12 | 1/6 | 2/6 | 4/5 | 0 |
| everything to a person (current process) | 6/12 (50%) | 0/12 (0%) | 0/12 | 0/6 | 6/6 | — | — |

Paired comparison of correct outcomes (deployed vs baseline): 2 vs 1 discordant, exact p = 1.

By language, deployed reader: es 5/6, pt 5/6.

| Case | Expected | Deployed | Baseline |
|---|---|---|---|
| `letter-above-limit-00-es` | handoff | ✓ handoff | ✓ handoff |
| `letter-asks-person-00-es` | handoff | ✓ handoff | ✓ handoff |
| `letter-duplicate-00-pt` | handoff | ✓ handoff | ✓ handoff |
| `letter-fraud-complete-00-es` | done | ✓ done | ✓ done |
| `letter-fraud-no-card-info-00-pt` | handoff | ✓ handoff | ✓ handoff |
| `letter-late-wrong-amount-00-pt` | ineligible | ✓ ineligible | ✗ handoff |
| `letter-not-received-00-pt` | done | ✓ done | ✗ handoff |
| `letter-regulator-00-pt` | handoff | ✗ done (dispute_opened_against_policy) | ✗ done (dispute_opened_against_policy) |
| `letter-stolen-card-00-es` | done | ✗ done (wrong_reason) | ✓ done |
| `letter-subscription-00-es` | done | ✓ done | ✓ done |
| `letter-vague-00-pt` | handoff | ✓ handoff | ✓ handoff |
| `letter-wrong-amount-00-es` | done | ✓ done | ✓ done |

## Fraud-alert answers (n = 9)

| Reader | Correct outcome | Safe automated resolution | Unsafe | Missed handoffs | Unnecessary handoffs | Handoff reason matches | Script gaps |
|---|---|---|---|---|---|---|---|
| rules + intent-v2 (deployed) | 7/9 (78%) | 5/9 (56%) | 1/9 | 0/2 | 0/7 | 2/2 | 2 |
| keyword rules only (baseline) | 7/9 (78%) | 5/9 (56%) | 1/9 | 0/2 | 0/7 | 2/2 | 2 |

Paired comparison of correct outcomes (deployed vs baseline): no discordant pairs.

By language, deployed reader: es 5/5, pt 2/4.

| Case | Expected | Deployed | Baseline |
|---|---|---|---|
| `alert-above-limit-01-pt` | handoff | ✓ handoff | ✓ handoff |
| `alert-declines-00-pt` | cancelled | ✗ stuck:confirm | ✗ stuck:confirm |
| `alert-lost-card-00-es` | done + block | ✓ done + block | ✓ done + block |
| `alert-not-me-block-00-es` | done + block | ✓ done + block | ✓ done + block |
| `alert-not-me-keep-card-00-pt` | done | ✓ done | ✓ done |
| `alert-unsure-then-no-00-es` | done | ✓ done | ✓ done |
| `alert-wants-person-00-es` | handoff | ✓ handoff | ✓ handoff |
| `alert-was-me-00-es` | cancelled | ✓ cancelled | ✓ cancelled |
| `alert-was-me-story-00-pt` | cancelled | ✗ done (dispute_opened_against_policy) | ✗ done (dispute_opened_against_policy) |

## Latency and cost

Whole case, deployed reader, this machine: p50 2.9 ms, p95 5.8 ms. Model cost US$ 0 (no model calls). Excludes network and the bank's real systems.

## Limitations

- Small sets (letters and alerts each under 30 cases per split); one run (deterministic, so repeats are identical).
- Alert conversations are scripted: lines are written in advance and picked by what the bank asks, so a question the author did not foresee gets “I don't know” (counted as script gaps).
- The Claude reader is not evaluated here (no API credit); these are the free readers only.
- Structured PQR fields (card, claimed amount) are taken as given by the intake form; only the free text is read.
