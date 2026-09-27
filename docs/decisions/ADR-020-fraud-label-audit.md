# ADR-020 — No fraud model: the labels have no behavioural signal; recalibrate the fraud alert instead
- **Status:** accepted · **Date:** 2026-09-27

## Context
The dataset has `is_fraud` and `fraud_score` on 4.4 million transactions, and "transaction fraud detection" is listed
as a use case. A trained fraud model would feed the proactive fraud alert and the queue priority. Before building it
we checked whether the labels can be learned.

## Finding (`ml/results/fraud_label_audit.md`, `make fraud-audit`)
- Temporal split: train before 2025-07-01, test from then (1.43M transactions, 1,302 fraud, prevalence 0.091%).
- Logistic regression and gradient boosting on behavioural features (amount, type, channel, status, merchant
  category, response code, currency, hour, weekday, foreign country, 24 h velocity, prior transactions and prior
  fraud of the customer, segment, age, tenure, credit score, income), without `fraud_score`:
  **ROC-AUC 0.501 and 0.503**, PR-AUC 0.0009 = prevalence; a permuted-label control gives 0.492.
- The fraud rate is 0.08–0.11% in every group of every behavioural feature.
- `fraud_score`: every transaction scored ≥ 40 is fraud, 37% of 30–40, 0.03% below 30 and 0.10% when missing.
  About half of the fraud is uniform noise that nothing in the data distinguishes.

## Decision
1. **No fraud model is trained for the service.** With the score it would relearn the generator's rule (leakage);
   without it there is nothing to learn. The evidence is published instead of a model.
2. **Proactive alert threshold 80 → 35**, by a rule fixed before looking at the test period: the lowest score whose
   precision on the train period is ≥ 95%. Train: 100% precision, 50.5% recall; test: 100% precision, 52.0% recall,
   ~59 alerts a month across all transactions (≥ 80 caught 15.8%). One constant, `domain.FRAUD_ALERT_MIN_SCORE`,
   used by the gold layer, the demo export and the API.
3. The demo store was rebuilt with the new threshold: a strict superset of the previous one (306 → 323 customers,
   no customer or transaction removed), so every frozen scenario still resolves.

## Trade-offs
- The alert rule leans on a vendor score whose behaviour is known only from this data; in production it would be
  monitored for drift (precision of confirmed alerts per week).
- Customers whose fraud has a low score are served only by the dispute conversation. That is the service's main path.
- On real data the same pipeline (temporal split, permutation control, PR-AUC against prevalence) is how a fraud
  model would be justified; here it justifies not shipping one.
