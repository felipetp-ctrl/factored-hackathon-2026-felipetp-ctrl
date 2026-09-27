# Learnability scan of the organizer data

> Organizer data (synthetic LATAM Bank). Offline. Same protocol for every target: features known at prediction time, temporal split at 2025-07-01 for dated tables (seeded 80/20 for snapshots), histogram gradient boosting, and the same model trained on permuted labels as the no-signal control. 95% bootstrap intervals on the test set.

| Target | Question | Metric | Model (95% CI) | One-column lookup | Permuted control | Base rate / mean | Test rows | Verdict |
|---|---|---|---|---|---|---|---|---|
| `csat_score` | CSAT score after a contact (CSAT surveys only, 1–4) | Spearman ρ | 0.452 (0.441–0.460) | 0.615 (`resolved`) | -0.009 | 2.768 | 41,046 | **signal** |
| `first_contact_resolution` | Call resolved at first contact (was_resolved) | ROC-AUC | 0.762 (0.759–0.764) | 0.763 (`contact_reason`) | 0.469 | 0.766 | 221,505 | **signal** |
| `call_escalated` | Call escalated (was_escalated) | ROC-AUC | 0.501 (0.497–0.505) | 0.498 (`interaction_type`) | 0.502 | 0.100 | 221,505 | **no signal** |
| `complaint_sla_breached` | Complaint breaches its SLA (sla_breached) | ROC-AUC | 0.502 (0.491–0.512) | 0.503 (`credit_score`) | 0.495 | 0.199 | 21,709 | **no signal** |
| `complaint_resolution_days` | Days to resolve a complaint (resolution_days) | Spearman ρ | -0.007 (-0.031–0.019) | 0.007 (`subcategory`) | 0.010 | 15.500 | 5,026 | **no signal** |
| `complaint_resolution_satisfaction` | Satisfaction with the resolution (1–5) | Spearman ρ | -0.002 (-0.050–0.078) | 0.074 (`estimated_monthly_income`) | -0.003 | 3.040 | 804 | **no signal** |
| `campaign_conversion` | Marketing send converts (had_conversion) | ROC-AUC | 0.652 (0.638–0.661) | 0.660 (`send_channel`) | 0.489 | 0.006 | 536,312 | **signal** |
| `product_past_due` | Product is past due (days_past_due > 0) | ROC-AUC | 0.501 (0.492–0.512) | 0.505 (`current_balance`) | 0.499 | 0.151 | 24,984 | **no signal** |
| `customer_inactive` | Customer is not active (customer_status) | ROC-AUC | 0.496 (0.487–0.504) | 0.509 (`age`) | 0.497 | 0.149 | 29,928 | **no signal** |

**Reading.** Where there is signal, a lookup table on one column matches the gradient-boosting model: the generator encodes each outcome as a function of a single field (CSAT of `was_resolved`, first-contact resolution of `contact_reason`, conversion of `send_channel`). Everything else — escalation, SLA, resolution time and satisfaction, delinquency, customer status, fraud beyond the score — is noise. There is no multivariate pattern in this dataset for a trained model to add.


## What drives the targets with signal (permutation importance: drop in the metric)

- `csat_score`: resolved +0.455
- `first_contact_resolution`: contact_reason +0.267
- `campaign_conversion`: send_channel +0.114, segment +0.002

Fraud (`is_fraud`) is covered separately in [fraud_label_audit.md](fraud_label_audit.md): no behavioural signal; the label follows the organizer's `fraud_score`.

Runtime: 101 s on a laptop.
