# Component re-scoring (offline)

Recomputed from the stored customer messages of this run; no model was called. Adds the rule-based fallback NLU (v0.0.2).

## Component evaluation (proposed system)

| Component | Claude Haiku NLU | Keyword baseline | Rule NLU (fallback) |
|---|---|---|---|
| Dispute reason accuracy | 100.0% (46/46) | 87.0% (40/46) | 87.0% (40/46) |
| Out-of-scope recall | 100.0% (8/8) | 100.0% (8/8) | 100.0% (8/8) |
| Out-of-scope false-positive rate | 0.0% (0/76) | 0.0% (0/76) | 0.0% (0/76) |
| Human-request detection | 100.0% (2/2) | 100.0% (2/2) | 100.0% (2/2) |

| Component | Result |
|---|---|
| Transaction identification (NLU + search) | 100.0% (46/46) |
| Injection flag true-positive rate (rules) | 100.0% (6/6) |
| Injection flag false-positive rate (rules) | 0.0% (0/98) |
| Language rules accuracy when decided | 98.3% (177/180) |
| Language rules undecided share | 5.3% (10/190) |
| NLU language accuracy (first turn) | 100.0% (80/80) |

Reason confusion (expected → NLU prediction): `{'FRAUD_CNP': {'FRAUD_CNP': 30}, 'NOT_RECEIVED': {'NOT_RECEIVED': 4}, 'INCORRECT_AMOUNT': {'INCORRECT_AMOUNT': 8}, 'CANCELLED_RECURRING': {'CANCELLED_RECURRING': 4}}`

**Leakage note.** The first re-scoring gave the rule NLU 75.0% (6/8) out-of-scope recall: it read
"empréstimo pessoal" (personal loan) as a request for a person ("pessoa"). That rule was fixed after looking at
these two test-v2 messages, so the rule NLU's out-of-scope figure above is no longer a held-out measurement.
Its dispute-reason accuracy is the keyword baseline's and was not tuned on this set.
