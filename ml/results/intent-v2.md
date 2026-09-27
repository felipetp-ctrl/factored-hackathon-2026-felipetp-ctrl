# Intent classifier `intent-v2` — training and evaluation

> Offline. Corpus is **team-generated** (written by the coding assistant, labelled by construction). Held-out messages come from the frozen test-v2/test-v1 runs (LLM-simulated customers) and are labelled by the scenario ground truth. No evaluation message was used for fitting, model selection or the threshold.

## Data

- Corpus: 937 messages (ES/PT), 936 used after dropping 1 near-duplicate(s) of evaluation messages (char 3-gram Jaccard ≥ 0.6); 2808 training examples after compositional augmentation (2 per sentence).
- Labels: `{'CANCELLED_RECURRING': 300, 'DISPUTE_NO_REASON': 420, 'DUPLICATE': 300, 'FRAUD_CNP': 291, 'FRAUD_CP': 297, 'HUMAN': 300, 'INCORRECT_AMOUNT': 300, 'NOT_RECEIVED': 300, 'OUT_OF_SCOPE': 300}`

## Model selection — 5-fold stratified cross-validation on the corpus, grouped by source sentence

| Candidate | Accuracy | Macro-F1 | ECE | CV time (s) |
|---|---|---|---|---|
| tfidf[wbc]+lr C=30 **(selected)** | 0.942 | 0.943 | 0.081 | 3.6 |
| tfidf[c]+lr C=30 | 0.941 | 0.943 | 0.073 | 2.8 |
| tfidf[wbc]+lr C=10 | 0.937 | 0.939 | 0.137 | 3.8 |
| tfidf[c]+lr C=10 | 0.937 | 0.938 | 0.128 | 2.6 |
| e5-small+lr | 0.937 | 0.935 | 0.213 | 6.1 |
| tfidf[wbc]+lr C=3 | 0.927 | 0.929 | 0.232 | 3.1 |
| tfidf[c]+lr C=3 | 0.926 | 0.928 | 0.220 | 2.6 |
| tfidf[wbc]+lr C=1 | 0.909 | 0.912 | 0.356 | 2.5 |
| tfidf[c]+lr C=1 | 0.908 | 0.911 | 0.342 | 2.2 |
| tfidf[wb]+lr C=30 | 0.860 | 0.867 | 0.069 | 1.0 |
| tfidf[wb]+lr C=10 | 0.854 | 0.862 | 0.136 | 0.9 |
| tfidf[wb]+lr C=3 | 0.843 | 0.852 | 0.240 | 0.9 |
| tfidf[wb]+lr C=1 | 0.821 | 0.833 | 0.362 | 0.8 |
| keyword-baseline | 0.473 | 0.508 | 0.527 | 0.1 |

Per-class out-of-fold recall of the selected model:

| FRAUD_CNP | FRAUD_CP | DUPLICATE | INCORRECT_AMOUNT | NOT_RECEIVED | CANCELLED_RECURRING | OUT_OF_SCOPE | HUMAN | DISPUTE_NO_REASON |
|---|---|---|---|---|---|---|---|---|
| 0.86 | 0.98 | 0.92 | 0.88 | 0.93 | 0.99 | 0.97 | 0.98 | 0.95 |

## Confidence threshold

Chosen on out-of-fold predictions: lowest threshold with ≥ 95% accuracy on accepted predictions, never below the policy's 0.6 hand-off floor → **0.60** (accepts 89.1% of corpus messages at 98.4% accuracy). Below it the rule NLU's reading stands.

| Threshold | Coverage | Accuracy on accepted |
|---|---|---|
| 0.20 | 100.0% | 94.2% |
| 0.25 | 99.8% | 94.3% |
| 0.30 | 99.5% | 94.5% |
| 0.35 | 98.5% | 95.1% |
| 0.40 | 97.1% | 95.8% |
| 0.45 | 95.6% | 96.5% |
| 0.50 | 93.7% | 97.2% |
| 0.55 | 91.6% | 97.9% |
| 0.60 | 89.1% | 98.4% |
| 0.65 | 86.5% | 98.8% |
| 0.70 | 84.0% | 98.9% |
| 0.75 | 80.4% | 99.2% |
| 0.80 | 76.2% | 99.3% |
| 0.85 | 70.4% | 99.5% |
| 0.90 | 61.3% | 99.5% |
| 0.95 | 42.5% | 99.7% |

## Held-out evaluation (scored after selection)

> **Post-hoc caveat.** The test-v2 and test-v1 messages were read during the intent-v1 error analysis that motivated this version's augmentation, so their numbers are optimistic. `test-v2 run 3 (unseen)` holds messages from the credit-aborted third run that were never opened; `test-v3` (frozen before this version was trained) is the clean held-out set once it is run.

| Set | n | Labels | intent-v2 | Keyword baseline | intent-v2 accepted at threshold | By language (intent-v2) |
|---|---|---|---|---|---|---|
| test-v2 reason | 46 | `{'CANCELLED_RECURRING': 4, 'FRAUD_CNP': 30, 'INCORRECT_AMOUNT': 8, 'NOT_RECEIVED': 4}` | 45/46 = 97.8% (95% CI 89%–100%) | 40/46 = 87.0% (95% CI 74%–94%) | 45/46 | es 24/24 · pt 21/22 |
| test-v1 reason | 69 | `{'FRAUD_CNP': 69}` | 69/69 = 100.0% (95% CI 95%–100%) | 68/69 = 98.6% (95% CI 92%–100%) | 68/68 | es 36/36 · pt 33/33 |
| test-v2 run 3 reason (unseen) | 23 | `{'CANCELLED_RECURRING': 2, 'FRAUD_CNP': 15, 'INCORRECT_AMOUNT': 4, 'NOT_RECEIVED': 2}` | 23/23 = 100.0% (95% CI 86%–100%) | 21/23 = 91.3% (95% CI 73%–98%) | 22/22 | es 12/12 · pt 11/11 |

| Out-of-scope detection, test-v2 first messages | Recall | False positives |
|---|---|---|
| model | 5/8 | 0/76 |
| keyword | 6/8 | 0/76 |

### Held-out errors (intent-v2)

| Set | Message | Expected | Predicted | p |
|---|---|---|---|---|
| test-v2 reason | oi td bem, tem uma cobranca estranha aq no meu cartao foi na mercado central, valor de 91.558,20 ARS, dia 02/05/2026 mais ou menos 18:48 | FRAUD_CNP | INCORRECT_AMOUNT | 0.626 |

## Runtime

- Pure-Python scoring from JSON: 0.20 ms per message, 1525 KB, 15,075 features; max |p_runtime − p_sklearn| = 1.5e-06.
- No ML library in the API image; `scikit-learn` and `mlflow` live in the `ml` dependency group.

## Limitations

- The corpus author also wrote the system and saw a few evaluation transcripts while reviewing reports; the near-duplicate filter bounds verbatim leakage, not stylistic familiarity.
- Held-out reason labels cover four of the six reasons (no DUPLICATE or FRAUD_CP in test-v2) and repeat scenarios across runs (n counts messages, not independent scenarios).
- Held-out customers are simulated by an LLM, not real customers; Portuguese is not in the organizer data.
