# intent-v2: calibration and threshold, out of sample

Independent set, n = 540 (another author; labels re-checked blind, κ = 1.0; [independent-v1](independent-v1.md)). Model unchanged; script `dispute_ops.ml.calibration`.

- Accuracy (model alone, no rules): **95.7%**; multi-class Brier score 0.082.
- Expected calibration error (10 bins): **0.064**.
- At the 0.60 threshold in use: coverage **93.5%**, accuracy when accepted **97.6%**.
- Above 0.6 every bin is at least as accurate as its stated confidence: the model under-states its confidence, the safe direction for a threshold.
- n = 540 is the whole set; the 94.1% reported in independent-v1 is the full fallback reader (rules + model) on 525 of these messages.

![Calibration](../../docs/figures/intent_calibration.png)

| Threshold | Coverage | Accuracy when accepted |
|---|---|---|
| 0.3 | 99.4% | 96.1% |
| 0.4 | 98.3% | 96.2% |
| 0.5 | 96.5% | 96.9% |
| 0.6 | 93.5% | 97.6% |
| 0.7 | 87.2% | 98.7% |
| 0.8 | 80.4% | 99.3% |
| 0.9 | 69.1% | 99.7% |

| Confidence bin | n | Mean confidence | Accuracy |
|---|---|---|---|
| 0.1–0.2 | 1 | 0.19 | 0.00 |
| 0.2–0.3 | 2 | 0.26 | 0.50 |
| 0.3–0.4 | 6 | 0.36 | 0.83 |
| 0.4–0.5 | 10 | 0.45 | 0.60 |
| 0.5–0.6 | 16 | 0.54 | 0.75 |
| 0.6–0.7 | 34 | 0.65 | 0.82 |
| 0.7–0.8 | 37 | 0.76 | 0.92 |
| 0.8–0.9 | 61 | 0.85 | 0.97 |
| 0.9–1.0 | 373 | 0.98 | 1.00 |

| Language | n | Accuracy | Coverage at 0.60 | Accuracy when accepted |
|---|---|---|---|---|
| es | 270 | 95.9% | 91.9% | 97.6% |
| pt | 270 | 95.6% | 95.2% | 97.7% |

Below the threshold the keyword rules keep their reading and the policy's own confidence floor (0.6) sends
an unclear reason to a person; the model never decides alone.
