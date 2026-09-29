# Model card — `intent-v2`

| | |
|---|---|
| Task | Read what a card customer wants from one chat message: one of 9 labels (six dispute reasons, out of scope, wants a person, dispute without a reason yet) |
| Languages | Spanish (Mexico, Colombia, Argentina registers), Brazilian Portuguese |
| Model | TF-IDF (sublinear) over word unigrams, word bigrams and character 2–5-grams → multinomial logistic regression, C = 30 |
| Size and speed | 15,075 features, 1.5 MB JSON, 0.2 ms per message in pure Python; no ML library at runtime |
| Version and lineage | `intent-v2`, MLflow registered model `intent-classifier` v1; decision record [ADR-019](decisions/ADR-019-learned-intent-classifier.md); rebuilt byte-identically by `make train` |
| Owner | LATAM Bank dispute operations (hackathon team) |

## Intended use
Inside the free fallback NLU (`RuleNlu`), used when the language model is down, over budget or disabled
(`NLU_MODE=rules`). Only on turns where the customer says what they want (`START`, `IDENTIFY_TXN`, `CLASSIFY`).
A reading is used only at probability ≥ 0.60 (the policy's own hand-off floor); below it the keyword rules decide.
Its output is a reason code and a routing hint. **It never decides an action**: the versioned policy decides, the
customer confirms a summary that names the reason, and every action is verified by reading it back.

Out of scope: yes/no and evidence answers (rules read those), slot extraction (amount, date, merchant, transaction),
anything outside card disputes, languages other than ES/PT, credit or fraud decisions.

## Training data
`ml/corpus/intent-v1.tsv`: 937 messages, ~50 per label and language, **team-generated** (written by the coding
assistant at the team's request, labelled by construction; no customer data). Near-duplicates of any evaluation
message are removed (1). Compositional augmentation (2 variants per sentence: invented merchants, local amounts and
dates, openers and trailers) gives 2,808 training examples. The organizer data has no usable customer text
(5 distinct complaint descriptions, 42 distinct call transcripts with one intent label).

## Evaluation
| Set | What it is | intent-v2 | Keyword rules |
|---|---|---|---|
| CV (grouped 5-fold, corpus) | model selection | macro-F1 0.943 | 0.508 |
| **Independent set** (525 gold) | different author (Sonnet subagent that never saw the corpus), blind second annotator κ = 1.0 | **95.6%** alone · **94.1%** inside the fallback NLU (CI 92–96%) | 45.7% |
| test-v3 (frozen before v2) | 23 reason messages from simulated conversations | 23/23 | 22/23 |
| test-v2 run 3 | 23 never-opened messages | 23/23 | 21/23 |
| test-v2 / test-v1 | read during intent-v1 error analysis | 45/46 · 69/69 (post-hoc) | 40/46 · 68/69 |

- Paired McNemar (independent set, fallback with vs without intent-v2): 260 vs 6 discordant, p = 8e-69.
- By language (independent set, inside the fallback): ES 243/261, PT 251/264.
- Weakest labels (independent set, inside the fallback): OUT_OF_SCOPE 51/58, INCORRECT_AMOUNT 52/60, HUMAN 53/57.
- Confident errors: at the 0.60 threshold it accepts 492/525 independent messages, 12 of them wrongly (2.4%).
- Calibration: out-of-fold ECE 0.081 (slightly over-confident at C = 30).
- Cross-author: trained on our corpus → 95.6% on the independent set; trained on the independent set → 85.5% on ours.
- Alternatives compared: 12 TF-IDF variants; multilingual-e5-small embeddings + LR (CV macro-F1 0.935); the same
  encoder **fine-tuned** on the same data (independent set 93.0% vs 95.6% for TF-IDF, 15× slower on CPU; one seed,
  no hyperparameter search — `ml/results/finetune-e5-small.md`). Neither is deployable on the 512 MB instance.

## Calibration (out of sample)
On the independent set (n = 540): ECE 0.064, Brier 0.082; above 0.6 the model under-states its confidence. At the
0.60 threshold it accepts 93.5% of messages at 97.6% accuracy, the same in Spanish and Portuguese
([calibration](../ml/results/calibration.md)).

## Risks and limitations
- All evaluation text is written by language models (simulated customers, subagent writers); none by real customers,
  and the organizer data has no Portuguese. Both independent annotators are Sonnet instances: κ = 1.0 shows the set is
  unambiguous under the definitions. A blind human review of 90 messages agreed on 78 of 85 decided (91.8%,
  κ = 0.91; 5 “can't decide”); the weak label is DISPUTE_NO_REASON (4/8), which a person reads as an unrecognised
  charge ([human review](../ml/results/human-review.md)). One annotator, the project's author.
- A confident wrong reason reaches the confirmation summary; a customer who confirms without reading gets the wrong
  dispute type (the same holds for the keyword rules and for the language model).
- Explicit keywords keep precedence for routing (out of scope over "human"), so keyword false positives are not
  corrected by the model (e.g. merchant names containing product words, fixed separately).
- Balanced test sets overstate performance on rare labels relative to a real traffic mix (about 65% fraud in the
  simulated conversations).

## Monitoring
Every turn records the classifier's label, probability and whether it was used (`nlu` audit event). `/agent/metrics`
reports turns read, share accepted, mean confidence, label mix and the population stability index of the confidence
distribution against the training out-of-fold histogram stored in the model (alarm at PSI > 0.2, from 30 turns).
CI fails if a retrained model drops below the recorded results on test-v3, run 3 or the independent set
(`tests/test_model_gate.py`).

## Retraining
`make train` (corpus → augmentation → grouped CV over candidates → threshold → export → held-out scoring → MLflow run
and registry version). Retrain when real, consented customer messages are available, when the PSI alarm fires, or when
the dispute reason taxonomy changes; the gate decides whether a new version may replace the deployed one.
