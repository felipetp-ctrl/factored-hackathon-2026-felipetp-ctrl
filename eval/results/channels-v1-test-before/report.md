# channels-v1 · test

Written complaints and fraud-alert answers, run end to end with no language-model calls. Expected outcomes from the policy on real transactions; customer text by an independent author. Offline simulation.

## Written complaints (n = 24)

| Reader | Correct outcome | Safe automated resolution | Unsafe | Missed handoffs | Unnecessary handoffs | Handoff reason matches | Script gaps |
|---|---|---|---|---|---|---|---|
| rules + intent-v2 (deployed) | 19/24 (79%) | 9/24 (38%) | 4/24 | 2/12 | 1/12 | 8/10 | 0 |
| keyword rules only (baseline) | 17/24 (71%) | 7/24 (29%) | 2/24 | 2/12 | 5/12 | 8/10 | 0 |
| everything to a person (current process) | 12/24 (50%) | 0/24 (0%) | 0/24 | 0/12 | 12/12 | — | — |

Paired comparison of correct outcomes (deployed vs baseline): 4 vs 2 discordant, exact p = 0.688.

By language, deployed reader: es 9/12, pt 10/12.

| Case | Expected | Deployed | Baseline |
|---|---|---|---|
| `letter-above-limit-00-es` | handoff | ✓ handoff | ✓ handoff |
| `letter-above-limit-01-pt` | handoff | ✓ handoff | ✓ handoff |
| `letter-asks-person-00-es` | handoff | ✓ handoff | ✓ handoff |
| `letter-asks-person-01-pt` | handoff | ✓ handoff | ✓ handoff |
| `letter-duplicate-00-es` | handoff | ✓ handoff | ✓ handoff |
| `letter-duplicate-01-pt` | handoff | ✓ handoff | ✓ handoff |
| `letter-fraud-complete-00-es` | done | ✗ handoff | ✗ handoff |
| `letter-fraud-complete-01-pt` | done | ✓ done | ✓ done |
| `letter-fraud-no-card-info-00-es` | handoff | ✓ handoff | ✓ handoff |
| `letter-fraud-no-card-info-01-pt` | handoff | ✓ handoff | ✓ handoff |
| `letter-late-wrong-amount-00-es` | ineligible | ✓ ineligible | ✗ handoff |
| `letter-late-wrong-amount-01-pt` | ineligible | ✓ ineligible | ✗ handoff |
| `letter-not-received-00-es` | done | ✓ done | ✗ handoff |
| `letter-not-received-01-pt` | done | ✓ done | ✓ done |
| `letter-regulator-00-es` | handoff | ✗ done (dispute_opened_against_policy) | ✗ done (dispute_opened_against_policy) |
| `letter-regulator-01-pt` | handoff | ✗ done (dispute_opened_against_policy) | ✗ done (dispute_opened_against_policy) |
| `letter-stolen-card-00-es` | done | ✗ done (wrong_reason) | ✓ done |
| `letter-stolen-card-01-pt` | done | ✗ done (wrong_reason) | ✓ done |
| `letter-subscription-00-es` | done | ✓ done | ✓ done |
| `letter-subscription-01-pt` | done | ✓ done | ✓ done |
| `letter-vague-00-es` | handoff | ✓ handoff | ✓ handoff |
| `letter-vague-01-pt` | handoff | ✓ handoff | ✓ handoff |
| `letter-wrong-amount-00-es` | done | ✓ done | ✓ done |
| `letter-wrong-amount-01-pt` | done | ✓ done | ✗ handoff |

## Fraud-alert answers (n = 18)

| Reader | Correct outcome | Safe automated resolution | Unsafe | Missed handoffs | Unnecessary handoffs | Handoff reason matches | Script gaps |
|---|---|---|---|---|---|---|---|
| rules + intent-v2 (deployed) | 16/18 (89%) | 12/18 (67%) | 0/18 | 0/4 | 0/14 | 4/4 | 0 |
| keyword rules only (baseline) | 16/18 (89%) | 12/18 (67%) | 0/18 | 0/4 | 0/14 | 4/4 | 0 |

Paired comparison of correct outcomes (deployed vs baseline): no discordant pairs.

By language, deployed reader: es 8/9, pt 8/9.

| Case | Expected | Deployed | Baseline |
|---|---|---|---|
| `alert-above-limit-02-es` | handoff | ✓ handoff | ✓ handoff |
| `alert-above-limit-03-pt` | handoff | ✓ handoff | ✓ handoff |
| `alert-declines-00-es` | cancelled | ✗ stuck:confirm | ✗ stuck:confirm |
| `alert-declines-01-pt` | cancelled | ✗ stuck:confirm | ✗ stuck:confirm |
| `alert-lost-card-00-es` | done + block | ✓ done + block | ✓ done + block |
| `alert-lost-card-01-pt` | done + block | ✓ done + block | ✓ done + block |
| `alert-not-me-block-00-es` | done + block | ✓ done + block | ✓ done + block |
| `alert-not-me-block-01-pt` | done + block | ✓ done + block | ✓ done + block |
| `alert-not-me-keep-card-00-es` | done | ✓ done | ✓ done |
| `alert-not-me-keep-card-01-pt` | done | ✓ done | ✓ done |
| `alert-unsure-then-no-00-es` | done | ✓ done | ✓ done |
| `alert-unsure-then-no-01-pt` | done | ✓ done | ✓ done |
| `alert-wants-person-00-es` | handoff | ✓ handoff | ✓ handoff |
| `alert-wants-person-01-pt` | handoff | ✓ handoff | ✓ handoff |
| `alert-was-me-00-es` | cancelled | ✓ cancelled | ✓ cancelled |
| `alert-was-me-01-pt` | cancelled | ✓ cancelled | ✓ cancelled |
| `alert-was-me-story-00-es` | cancelled | ✓ cancelled | ✓ cancelled |
| `alert-was-me-story-01-pt` | cancelled | ✓ cancelled | ✓ cancelled |

## Latency and cost

Whole case, deployed reader, this machine: p50 2.7 ms, p95 5.4 ms. Model cost US$ 0 (no model calls). Excludes network and the bank's real systems.

## Limitations

- Small sets (letters and alerts each under 30 cases per split); one run (deterministic, so repeats are identical).
- Alert conversations are scripted: lines are written in advance and picked by what the bank asks, so a question the author did not foresee gets “I don't know” (counted as script gaps).
- The Claude reader is not evaluated here (no API credit); these are the free readers only.
- Structured PQR fields (card, claimed amount) are taken as given by the intake form; only the free text is read.
