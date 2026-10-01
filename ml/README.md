# Machine learning: corpora and reports

Code lives in `backend/src/dispute_ops/ml/`; the deployed model is exported to
`backend/src/dispute_ops/language/models/intent-v2.json`. Commands: `make train`, `make calibration`,
`make fraud-audit`, `make learnability`, `make mlflow-ui`. Summary: [docs/evaluation.md](../docs/evaluation.md#machine-learning).

## `corpus/` — labelled text (team-generated or independent; no customer data)

| File | What it is |
|---|---|
| `intent-v1.tsv` | Training corpus of intent-v1 and intent-v2 (937 messages, ES/PT, labelled by construction) |
| `independent-v1.tsv` | Independent evaluation set: 540 messages by another author who never saw the training corpus |
| `independent-v1.blind.tsv` · `independent-v1.annotator2.tsv` | The same messages without labels, and the blind second annotation (κ = 1.0) |
| `independent-v1.annotator-haiku-discarded.tsv` | A weaker annotation discarded at κ = 0.48; kept for the record |
| `human-review.tsv` | 90 messages labelled blind by a human reviewer |

## `results/` — reports (`.md` to read, `.json` with the numbers)

| Report | What it answers |
|---|---|
| [intent-v1](results/intent-v1.md) · [intent-v2](results/intent-v2.md) | Model selection and held-out results; v1 lost to keywords and is kept ([ADR-019](../docs/decisions/ADR-019-learned-intent-classifier.md)) |
| [independent-v1](results/independent-v1.md) | intent-v2 on the independent set: 94.1% vs keyword rules 45.7% |
| [human-review](results/human-review.md) | Agreement of the labels with a blind human reviewer (κ = 0.91) |
| [calibration](results/calibration.md) | Is the classifier's confidence trustworthy out of sample; the 0.60 threshold |
| [finetune-e5-small](results/finetune-e5-small.md) | A fine-tuned transformer against the deployed TF-IDF model |
| [fraud_label_audit](results/fraud_label_audit.md) | Why there is no fraud model ([ADR-020](../docs/decisions/ADR-020-fraud-label-audit.md)) |
| [learnability_scan](results/learnability_scan.md) | Nine other targets, same protocol ([ADR-021](../docs/decisions/ADR-021-learnability-scan.md)) |
