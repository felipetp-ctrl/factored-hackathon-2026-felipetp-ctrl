# Intent classifier `intent-v3` — training and evaluation

> Offline. Corpus is **team-generated** (written by the coding assistant, labelled by construction). Held-out messages come from the frozen test-v2/test-v1 runs (LLM-simulated customers) and are labelled by the scenario ground truth. No evaluation message was used for fitting, model selection or the threshold.

## Data

- Corpus: 937 messages (ES/PT), 936 used after dropping 1 near-duplicate(s) of evaluation messages (char 3-gram Jaccard ≥ 0.6); 7960 training examples after compositional augmentation (2 per sentence), plus one compound copy of every reason sentence (an out-of-scope request followed by the dispute), one spoken-style copy of every example, and 872 real out-of-scope calls from MInDS-14 (11 intents, one CV group per intent; ADR-030).
- Labels: `{'CANCELLED_RECURRING': 800, 'DISPUTE_NO_REASON': 1120, 'DUPLICATE': 800, 'FRAUD_CNP': 776, 'FRAUD_CP': 792, 'HUMAN': 600, 'INCORRECT_AMOUNT': 800, 'NOT_RECEIVED': 800, 'OUT_OF_SCOPE': 1472}`

## Model selection — 5-fold stratified cross-validation on the corpus, grouped by source sentence

| Candidate | Accuracy | Macro-F1 | ECE | CV time (s) |
|---|---|---|---|---|
| tfidf[wbc]+lr C=30 **(selected)** | 0.929 | 0.931 | 0.060 | 7.7 |
| tfidf[wbc]+lr C=10 | 0.923 | 0.925 | 0.101 | 7.8 |
| tfidf[c]+lr C=30 | 0.921 | 0.924 | 0.044 | 6.2 |
| tfidf[c]+lr C=10 | 0.917 | 0.920 | 0.085 | 5.9 |
| tfidf[wbc]+lr C=3 | 0.914 | 0.916 | 0.170 | 7.4 |
| tfidf[c]+lr C=3 | 0.911 | 0.915 | 0.155 | 6.2 |
| tfidf[c]+lr C=1 | 0.898 | 0.902 | 0.249 | 5.6 |
| tfidf[wbc]+lr C=1 | 0.898 | 0.901 | 0.263 | 6.8 |
| tfidf[wb]+lr C=30 | 0.853 | 0.855 | 0.053 | 2.1 |
| tfidf[wb]+lr C=10 | 0.846 | 0.848 | 0.104 | 2.1 |
| tfidf[wb]+lr C=3 | 0.837 | 0.840 | 0.187 | 2.0 |
| tfidf[wb]+lr C=1 | 0.817 | 0.821 | 0.282 | 1.9 |
| keyword-baseline | 0.457 | 0.508 | 0.543 | 0.2 |

Only TF-IDF + logistic regression candidates are eligible for deployment: they export to a JSON the API scores in pure Python. The sentence-embedding candidate (when run with `--embeddings`) needs PyTorch and a 470 MB encoder, which the free API instance (512 MB RAM) cannot hold; it is trained for comparison only.

Per-class out-of-fold recall of the selected model:

| FRAUD_CNP | FRAUD_CP | DUPLICATE | INCORRECT_AMOUNT | NOT_RECEIVED | CANCELLED_RECURRING | OUT_OF_SCOPE | HUMAN | DISPUTE_NO_REASON |
|---|---|---|---|---|---|---|---|---|
| 0.82 | 0.96 | 0.94 | 0.86 | 0.93 | 0.99 | 0.97 | 0.96 | 0.91 |

## Confidence threshold

Chosen on out-of-fold predictions: lowest threshold with ≥ 95% accuracy on accepted predictions, never below the policy's 0.6 hand-off floor → **0.60** (accepts 89.3% of corpus messages at 97.0% accuracy). Below it the rule NLU's reading stands.

| Threshold | Coverage | Accuracy on accepted |
|---|---|---|
| 0.20 | 100.0% | 92.9% |
| 0.25 | 99.8% | 93.0% |
| 0.30 | 99.3% | 93.3% |
| 0.35 | 98.4% | 93.7% |
| 0.40 | 97.4% | 94.1% |
| 0.45 | 96.0% | 94.9% |
| 0.50 | 94.0% | 95.7% |
| 0.55 | 91.6% | 96.5% |
| 0.60 | 89.3% | 97.0% |
| 0.65 | 86.9% | 97.5% |
| 0.70 | 84.1% | 98.0% |
| 0.75 | 80.8% | 98.5% |
| 0.80 | 76.8% | 98.9% |
| 0.85 | 71.3% | 99.2% |
| 0.90 | 63.7% | 99.3% |
| 0.95 | 49.3% | 99.6% |

## Held-out evaluation (scored after selection)

> **Post-hoc caveat.** The test-v2 and test-v1 messages were read during the intent-v1 error analysis that motivated this version's augmentation, so their numbers are optimistic. `test-v2 run 3 (unseen)` holds messages from the credit-aborted third run that were never opened; `test-v3` (frozen before this version was trained) is the clean held-out set once it is run.

| Set | n | Labels | intent-v3 | Keyword baseline | intent-v3 accepted at threshold | By language (intent-v3) |
|---|---|---|---|---|---|---|
| test-v2 reason | 46 | `{'CANCELLED_RECURRING': 4, 'FRAUD_CNP': 30, 'INCORRECT_AMOUNT': 8, 'NOT_RECEIVED': 4}` | 45/46 = 97.8% (95% CI 89%–100%) | 40/46 = 87.0% (95% CI 74%–94%) | 45/46 | es 24/24 · pt 21/22 |
| test-v1 reason | 69 | `{'FRAUD_CNP': 69}` | 69/69 = 100.0% (95% CI 95%–100%) | 68/69 = 98.6% (95% CI 92%–100%) | 69/69 | es 36/36 · pt 33/33 |
| test-v2 run 3 reason (unseen) | 23 | `{'CANCELLED_RECURRING': 2, 'FRAUD_CNP': 15, 'INCORRECT_AMOUNT': 4, 'NOT_RECEIVED': 2}` | 23/23 = 100.0% (95% CI 86%–100%) | 21/23 = 91.3% (95% CI 73%–98%) | 22/22 | es 12/12 · pt 11/11 |

| Out-of-scope detection, test-v2 first messages | Recall | False positives |
|---|---|---|
| model | 7/8 | 0/76 |
| keyword | 6/8 | 0/76 |

### Held-out errors (intent-v3)

| Set | Message | Expected | Predicted | p |
|---|---|---|---|---|
| test-v2 reason | oi td bem, tem uma cobranca estranha aq no meu cartao foi na mercado central, valor de 91.558,20 ARS, dia 02/05/2026 mais ou menos 18:48 | FRAUD_CNP | INCORRECT_AMOUNT | 0.8 |

## Runtime

- Pure-Python scoring from JSON: 0.15 ms per message, 2139 KB, 21,040 features; max |p_runtime − p_sklearn| = 9.5e-07.
- No ML library in the API image; `scikit-learn` and `mlflow` live in the `ml` dependency group.

## Limitations

- The corpus author also wrote the system and saw a few evaluation transcripts while reviewing reports; the near-duplicate filter bounds verbatim leakage, not stylistic familiarity.
- Held-out reason labels cover four of the six reasons (no DUPLICATE or FRAUD_CP in test-v2) and repeat scenarios across runs (n counts messages, not independent scenarios).
- Held-out customers are simulated by an LLM, not real customers; Portuguese is not in the organizer data.
