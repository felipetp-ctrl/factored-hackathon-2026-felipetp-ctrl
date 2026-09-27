# Fraud label audit

> Organizer data (synthetic LATAM Bank, silver layer). Offline. Temporal split: train before 2025-07-01, test from 2025-07-01.

## Question

Can a model learn `is_fraud` from how a transaction looks (amount, type, channel, merchant category, hour, country, velocity, customer history and profile) — i.e. is there a fraud model worth training here?

## Answer: no. The label is a function of the organizer's `fraud_score` plus uniform noise.

Test period: 1,430,411 transactions, 1,302 fraud (prevalence 0.091%). Learned models fit on all 3,014 train frauds + 300,000 sampled train non-frauds (class-balanced).

| Scorer | ROC-AUC (95% bootstrap CI) | PR-AUC | PR-AUC of a random scorer |
|---|---|---|---|
| Logistic regression, behavioural features | 0.501 (0.487–0.513) | 0.0009 | 0.0009 |
| Gradient boosting, behavioural features | 0.503 (0.488–0.516) | 0.0009 | 0.0009 |
| Control: gradient boosting on permuted labels | 0.492 (0.477–0.506) | 0.0009 | 0.0009 |
| Organizer `fraud_score` as a rule | 0.716 (0.694–0.736) | 0.5561 | 0.0009 |

Both behavioural models are indistinguishable from the permuted-label control. The organizer score is perfect on its high end (every transaction scored ≥ 40 is fraud) and blind below 30, where about half of the fraud sits at the same rate as normal traffic — hence a ROC-AUC of only ~0.72.

### Fraud rate by `fraud_score` (all data)

| Score | Transactions | Fraud | Rate |
|---|---|---|---|
| 00–10 | 1,179,452 | 337 | 0.03% |
| 10–20 | 1,179,243 | 359 | 0.03% |
| 20–30 | 1,178,174 | 356 | 0.03% |
| 30–40 | 969 | 360 | 37.15% |
| 40–50 | 343 | 343 | 100.00% |
| 50–60 | 327 | 327 | 100.00% |
| 60–70 | 344 | 344 | 100.00% |
| 70–80 | 326 | 326 | 100.00% |
| 80–90 | 334 | 334 | 100.00% |
| 90–100 | 339 | 339 | 100.00% |
| null | 885,157 | 891 | 0.10% |

### Fraud rate range across behavioural groups (all data)

| Feature | Groups | Lowest rate | Highest rate |
|---|---|---|---|
| transaction_type | 6 | 0.089% | 0.109% |
| channel | 6 | 0.095% | 0.108% |
| transaction_status | 4 | 0.080% | 0.098% |
| merchant_category | 7 | 0.096% | 0.108% |
| hour | 24 | 0.089% | 0.108% |

## Consequence: the proactive fraud alert threshold

Rule fixed in advance: the lowest `fraud_score` whose precision on the **train** period is ≥ 95%; then checked on the **test** period. Chosen: **≥ 35** (was ≥ 80, which catches a sliver of the fraud).

| Threshold | Train precision | Train recall | Test precision | Test recall | Test alerts / month (all transactions) |
|---|---|---|---|---|---|
| ≥ 30 | 79.9% | 54.8% | 78.8% | 55.5% | 79 |
| ≥ 35 | 100.0% | 50.5% | 100.0% | 52.0% | 59 |
| ≥ 40 | 100.0% | 46.0% | 100.0% | 48.1% | 54 |
| ≥ 50 | 100.0% | 38.4% | 100.0% | 39.3% | 44 |
| ≥ 60 | 100.0% | 31.1% | 100.0% | 31.2% | 35 |
| ≥ 80 | 100.0% | 15.5% | 100.0% | 15.8% | 18 |

## What this means for the ML pillar

- No fraud model is trained for production: on this data it could only relearn the generator's score (leakage) or, without it, learn nothing. Both are shown above instead of claimed.
- The learned component of the service is the intent/reason classifier (ADR-019), where the task has signal.
- About half of the fraud (score < 30 or missing) is indistinguishable from normal traffic in this dataset: the dispute conversation, not a proactive alert, is the only way those customers are served.

## Limitations

- Synthetic data: a real bank's labels come from chargebacks and investigations and carry behavioural signal; the pipeline and evaluation here would apply unchanged.
- `prior_fraud` uses earlier labels as if known immediately (label delay ignored); it did not help anyway.
