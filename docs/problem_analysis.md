# Problem analysis — why card-charge disputes

All numbers come from the organizer dataset (LATAM Bank v1.0.0, synthetic, June 2023 – June 2026), computed on the
silver layer of our pipeline (`make data`; data quality in [`data_quality_report.md`](data_quality_report.md)).
Business figures in the last section are **projections from stated assumptions**, not measurements.

## 1. Disputes are a large, steady and slow-moving share of complaints

| Fact | Value |
|---|---|
| Complaints (PQR) in three years | 67,095 |
| Share in category `Transactions` | **20.2 %** (13,580) — its only subcategory is **"Cargo no reconocido"** (unrecognised charge) |
| Monthly volume | 335–424, mean **377 per month**, flat across 2023–2026 |
| Rate | ~30 disputes per 1,000 customers per year |
| How they arrive | Call center 50.4 % · email 19.4 % · web 14.8 % · app 10.4 % · branch 3.9 % · **regulator 1.1 %** |
| Current state | Open 29.7 % + In process 39.8 % = **69.5 % not resolved**; escalated 5.0 %; resolved/closed 24.6 %; rejected 0.9 % |
| First response | median **37 h**, p90 58 h |
| Time to resolution (resolved cases) | median **15 days**, p90 27 days |
| SLA breached | **~20 %** in every status |
| Resolution satisfaction | 3.09 / 5 |
| Compensation paid | 995 cases, mean 255 (local currency) |
| Repeat complainers among disputers | 14.7 % |

## 2. The intake is where the process breaks

Transaction complaints reach the back office **without the information needed to act on them**:

| Field needed to open a dispute | Missing |
|---|---|
| The disputed transaction (`transaction_id`) | **100 %** — the complaint schema has no such field |
| The affected product (`affected_product_id`) | 33.7 % |
| The claimed amount (`claimed_amount`) | 66.9 % |
| The originating interaction (`origin_interaction_id`) | 100 % |
| A usable description | 5 distinct templated texts in 67,095 complaints |

In the call center, complaint contacts (`Queja`, 117,021 interactions) have the **lowest first-contact resolution of any
reason: 43.6 %** (vs 91.5 % for transactional contacts), and the longest handle time after sales/retention: **7.2 minutes**.
Contact reasons are coarse (`contact_reason` equals `reason_category`, six values), so the bank cannot even tell a dispute
from other complaints at intake.

**Problem statement.** Customers who do not recognise a card charge wait a day and a half for a first answer and about two
weeks for a resolution, while seven in ten cases sit open. The root cause visible in the data is an intake that captures
neither the transaction, nor the reason, nor the evidence — so every case needs a person to reconstruct it.

## 3. What the service changes, and how it is measured

| Target outcome | Mechanism | Evidence |
|---|---|---|
| A complete, actionable case at the first contact | The conversation identifies the transaction from the customer's own history, classifies the reason code, collects the evidence the policy requires and opens the case | Held-out evaluation: transaction identification and reason accuracy (component report) |
| Minutes instead of 37 h to a registered case | Automated resolution when the policy allows; verified case id returned in the chat | Per-turn latency p50 ≈ 2 s; conversations of 2–5 turns |
| People only where they add value | Deterministic handoff triggers (amount, repeat complainer, regulator threat, security, failures) with a structured package | Missed and unnecessary escalations, measured |
| No new risk | Policy outside the model, confirmation before acting, verification before reporting | Unsafe outcomes counted with denominators, vs. an LLM baseline |
| Same treatment across countries | Single calibrated amount threshold (ADR-013) | Outcomes by country and segment |

## 4. Customer and business outcomes (projection — assumptions stated)

Assumptions, all adjustable:
- Human cost of a dispute intake = one complaint contact (7.2 min, measured) + 15 min of back-office reconstruction
  (assumed), at a loaded agent cost of US$ 8 per hour (assumed for a LATAM contact center) → **≈ US$ 3.0 per dispute**.
- Share of disputes the service resolves safely without a person = the held-out **offline** result (≈ 70 % on `test-v1`);
  the real share would need a pilot.
- Model cost per safely resolved dispute ≈ US$ 0.011 (measured in the evaluation, list prices).

| Per year, at the dataset's volume (≈ 4,530 disputes) | Human only | With the service (projected) |
|---|---|---|
| Disputes handled end to end by a person | 4,530 | ≈ 1,360 |
| Intake cost | ≈ US$ 13,400 | ≈ US$ 4,000 + ≈ US$ 35 of model cost |
| Time to a registered case | median 37 h to first response | minutes for the ≈ 70 % resolved in the conversation |

These are **simulated, offline** figures on a synthetic bank; they illustrate the order of magnitude and the levers, not a
measured production improvement.

## 5. Limitations of the evidence

- The dataset is synthetic: outcome fields in complaints (escalation, SLA, resolution time) are statistically independent of
  priority, channel, amount and customer type, so they cannot explain *why* cases are slow — only that they are.
- There is no Portuguese text in the dataset; Portuguese behaviour is evaluated with simulated customers only.
- Complaints cannot be joined to interactions or transactions, so the historical human baseline is available only in
  aggregate (not case by case).
