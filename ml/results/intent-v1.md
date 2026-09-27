# Intent classifier `intent-v1` — training and evaluation

> Offline. Corpus is **team-generated** (written by the coding assistant, labelled by construction). Held-out messages come from the frozen test-v2/test-v1 runs (LLM-simulated customers) and are labelled by the scenario ground truth. No evaluation message was used for fitting, model selection or the threshold.

## Data

- Corpus: 937 messages (ES/PT), 936 used after dropping 1 near-duplicate(s) of evaluation messages (char 3-gram Jaccard ≥ 0.6).
- Labels: `{'CANCELLED_RECURRING': 100, 'DISPUTE_NO_REASON': 140, 'DUPLICATE': 100, 'FRAUD_CNP': 97, 'FRAUD_CP': 99, 'HUMAN': 100, 'INCORRECT_AMOUNT': 100, 'NOT_RECEIVED': 100, 'OUT_OF_SCOPE': 100}`

## Model selection — 5-fold stratified cross-validation on the corpus

| Candidate | Accuracy | Macro-F1 | ECE | CV time (s) |
|---|---|---|---|---|
| tfidf[wbc]+lr C=30 **(selected)** | 0.937 | 0.939 | 0.120 | 3.2 |
| tfidf[c]+lr C=30 | 0.934 | 0.936 | 0.117 | 2.7 |
| tfidf[wbc]+lr C=10 | 0.933 | 0.935 | 0.189 | 3.1 |
| tfidf[c]+lr C=10 | 0.927 | 0.929 | 0.181 | 2.6 |
| tfidf[wbc]+lr C=3 | 0.921 | 0.923 | 0.307 | 2.6 |
| tfidf[c]+lr C=3 | 0.919 | 0.922 | 0.299 | 2.4 |
| tfidf[c]+lr C=1 | 0.892 | 0.895 | 0.438 | 1.9 |
| tfidf[wbc]+lr C=1 | 0.888 | 0.891 | 0.439 | 2.1 |
| tfidf[wb]+lr C=30 | 0.855 | 0.857 | 0.086 | 0.8 |
| tfidf[wb]+lr C=10 | 0.853 | 0.856 | 0.156 | 0.8 |
| tfidf[wb]+lr C=3 | 0.850 | 0.853 | 0.285 | 0.7 |
| tfidf[wb]+lr C=1 | 0.825 | 0.829 | 0.424 | 0.5 |
| keyword-baseline | 0.471 | 0.508 | 0.529 | 0.1 |

Per-class out-of-fold recall of the selected model:

| FRAUD_CNP | FRAUD_CP | DUPLICATE | INCORRECT_AMOUNT | NOT_RECEIVED | CANCELLED_RECURRING | OUT_OF_SCOPE | HUMAN | DISPUTE_NO_REASON |
|---|---|---|---|---|---|---|---|---|
| 0.87 | 0.97 | 0.95 | 0.91 | 0.95 | 1.00 | 0.94 | 0.98 | 0.89 |

## Confidence threshold

Chosen on out-of-fold predictions: lowest threshold with ≥ 95% accuracy on accepted predictions, never below the policy's 0.6 hand-off floor → **0.60** (accepts 84.3% of corpus messages at 98.6% accuracy). Below it the rule NLU's reading stands.

| Threshold | Coverage | Accuracy on accepted |
|---|---|---|
| 0.20 | 99.9% | 93.8% |
| 0.25 | 99.5% | 94.0% |
| 0.30 | 98.2% | 94.9% |
| 0.35 | 97.5% | 95.2% |
| 0.40 | 95.5% | 96.2% |
| 0.45 | 92.6% | 96.9% |
| 0.50 | 90.3% | 97.5% |
| 0.55 | 87.0% | 98.3% |
| 0.60 | 84.3% | 98.6% |
| 0.65 | 81.3% | 98.8% |
| 0.70 | 78.0% | 98.8% |
| 0.75 | 73.3% | 98.8% |
| 0.80 | 67.4% | 99.4% |
| 0.85 | 59.0% | 99.5% |
| 0.90 | 47.5% | 99.8% |
| 0.95 | 31.2% | 99.7% |

## Held-out evaluation (scored once, after selection)

| Set | n | Labels | intent-v1 | Keyword baseline | intent-v1 accepted at threshold | By language (intent-v1) |
|---|---|---|---|---|---|---|
| test-v2 reason | 46 | `{'CANCELLED_RECURRING': 4, 'FRAUD_CNP': 30, 'INCORRECT_AMOUNT': 8, 'NOT_RECEIVED': 4}` | 34/46 = 73.9% (95% CI 60%–84%) | 40/46 = 87.0% (95% CI 74%–94%) | 28/34 | es 17/24 · pt 17/22 |
| test-v1 reason | 69 | `{'FRAUD_CNP': 69}` | 60/69 = 87.0% (95% CI 77%–93%) | 68/69 = 98.6% (95% CI 92%–100%) | 48/50 | es 28/36 · pt 32/33 |

| Out-of-scope detection, test-v2 first messages | Recall | False positives |
|---|---|---|
| model | 0/8 | 0/76 |
| keyword | 6/8 | 0/76 |

### Held-out errors (intent-v1)

| Set | Message | Expected | Predicted | p |
|---|---|---|---|---|
| test-v2 reason | Oi, tudo bem? Quero contestar uma cobrança de 1.575.714,48 COP feita na "Conciertos Live" no dia 12/05/2026, por volta das 04:25. Eu reconhe | NOT_RECEIVED | FRAUD_CNP | 0.636 |
| test-v2 reason | Hola, quiero disputar un cargo de $91.558,20 ARS en "Mercado Central" del 2 de mayo, el producto nunca me llegó. | NOT_RECEIVED | DISPUTE_NO_REASON | 0.863 |
| test-v2 reason | Hola, quiero disputar un cargo de Mercado Central, me cobraron de más en una compra. | INCORRECT_AMOUNT | DISPUTE_NO_REASON | 0.83 |
| test-v2 reason | Hola, quiero disputar un cargo de $1,814,899.57 COP en "Mercado Central", no lo reconozco. | FRAUD_CNP | DISPUTE_NO_REASON | 0.537 |
| test-v2 reason | oi td bem, tem uma cobranca estranha aq no meu cartao foi na mercado central, valor de 91.558,20 ARS, dia 02/05/2026 mais ou menos 18:48 | FRAUD_CNP | INCORRECT_AMOUNT | 0.49 |
| test-v2 reason | Oi! É uma cobrança de 1.575.714,48 COP na "Conciertos Live", feita em 12/05/2026 por volta das 04:25. O produto nunca chegou. | NOT_RECEIVED | DISPUTE_NO_REASON | 0.508 |
| test-v2 reason | Hola, buenas. Quiero disputar un cargo de 91.558,20 ARS que me hicieron en Mercado Central, no me llegó el producto que compré. | NOT_RECEIVED | DISPUTE_NO_REASON | 0.657 |
| test-v2 reason | Hola, quiero disputar un cargo de Mercado Central del 2 de mayo, me cobraron de más. | INCORRECT_AMOUNT | DISPUTE_NO_REASON | 0.906 |
| test-v2 reason | Oi! Foi uma cobrança de 22,98 USD da "Cable TV" no dia 26 de abril de 2026, por volta das 11:23. Eu já tinha cancelado a assinatura uns 10 d | CANCELLED_RECURRING | DISPUTE_NO_REASON | 0.501 |
| test-v2 reason | Hola, quiero disputar un cargo de 404.33 USD de "Cable TV" del 24 de abril de 2026, como a las 22:07. Cancelé la suscripción de Cable TV hac | CANCELLED_RECURRING | DISPUTE_NO_REASON | 0.614 |
| test-v2 reason | Oi! É uma cobrança na Boutique Moda, dia 24 de março de 2026, foi cobrado errado. | INCORRECT_AMOUNT | DISPUTE_NO_REASON | 0.477 |
| test-v2 reason | Hola, veo un cargo de 169.582,75 ARS en "Mercado Central" del 1 de mayo a las 21:39 que yo no hice. | FRAUD_CNP | DISPUTE_NO_REASON | 0.567 |
| test-v1 reason | Hola, buenas. Hay un cargo de 854.203,18 COP en "Farmacia Salud" el 10 de abril de 2026 como a las 6:44 de la mañana que yo no hice. | FRAUD_CNP | DISPUTE_NO_REASON | 0.525 |
| test-v1 reason | Oi, tem uma cobrança de 1.582.903,60 COP na Uber, no dia 23/05/2026 por volta da 00:51, que eu não fiz. | FRAUD_CNP | DISPUTE_NO_REASON | 0.691 |
| test-v1 reason | Hola, buenas. Veo un cargo de 242.96 USD en "Super Ahorro" del 28 de febrero de 2026, como a las 2:30 de la mañana, y yo no hice esa compra. | FRAUD_CNP | DISPUTE_NO_REASON | 0.508 |
| test-v1 reason | Hola, buen día. Veo un cargo de 438.63 USD de "Cable TV" del 5 de abril de 2026, como a las 8:03 am, que yo no hice. | FRAUD_CNP | DISPUTE_NO_REASON | 0.542 |
| test-v1 reason | Hola, quiero disputar un cargo de 24,594.89 COP en "Cable TV" del 5 de junio de 2026, como a las 5:55 am. No lo reconozco. | FRAUD_CNP | DISPUTE_NO_REASON | 0.731 |
| test-v1 reason | Hola, veo un cargo de 242.96 USD en "Super Ahorro" del 28 de febrero de 2026, como a las 2:30 am, y yo no lo hice. | FRAUD_CNP | DISPUTE_NO_REASON | 0.585 |
| test-v1 reason | Hola, buenas. Veo un cargo de 438.63 USD de "Cable TV" del 5 de abril de 2026, como a las 08:03, que yo no hice. | FRAUD_CNP | DISPUTE_NO_REASON | 0.522 |
| test-v1 reason | Hola, veo un cargo de 7.071,04 ARS en "Tienda Don José" del 13 de marzo de 2026 como a las 20:19 que yo no hice. | FRAUD_CNP | DISPUTE_NO_REASON | 0.48 |
| test-v1 reason | Hola, buenas, quiero disputar un cobro de $24.594,89 COP de "Cable TV" que me hicieron el 05 de junio de 2026, no lo reconozco. | FRAUD_CNP | DISPUTE_NO_REASON | 0.565 |

## Runtime

- Pure-Python scoring from JSON: 0.56 ms per message, 807 KB, 8,129 features; max |p_runtime − p_sklearn| = 2.8e-06.
- No ML library in the API image; `scikit-learn` and `mlflow` live in the `ml` dependency group.

## Limitations

- The corpus author also wrote the system and saw a few evaluation transcripts while reviewing reports; the near-duplicate filter bounds verbatim leakage, not stylistic familiarity.
- Held-out reason labels cover four of the six reasons (no DUPLICATE or FRAUD_CP in test-v2) and repeat scenarios across runs (n counts messages, not independent scenarios).
- Held-out customers are simulated by an LLM, not real customers; Portuguese is not in the organizer data.
