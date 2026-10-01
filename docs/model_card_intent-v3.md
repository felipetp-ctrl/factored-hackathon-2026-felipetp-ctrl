# Model card — `intent-v3`

> Replaced `intent-v2` on 2026-10-01 after a test on real customer speech ([ADR-030](decisions/ADR-030-real-speech-and-intent-v3.md)). intent-v2's figures are kept in [ml/results/intent-v2.md](../ml/results/intent-v2.md) and the git history of this card.

| | |
|---|---|
| Task | Read what a card customer wants from one chat message: one of 9 labels (six dispute reasons, out of scope, wants a person, dispute without a reason yet) |
| Languages | Spanish (Mexico, Colombia, Argentina registers), Brazilian Portuguese; tested on European Spanish and Portuguese speech |
| Model | TF-IDF (sublinear) over word unigrams, word bigrams and character 2–5-grams → multinomial logistic regression, C = 30 |
| Size and speed | 21,040 features, 2.1 MB JSON, 0.15 ms per message in pure Python; no ML library at runtime |
| Version and lineage | `intent-v3`, MLflow registered model `intent-classifier`; decision records [ADR-019](decisions/ADR-019-learned-intent-classifier.md), [ADR-030](decisions/ADR-030-real-speech-and-intent-v3.md); rebuilt byte-identically by `make train ARGS="--version intent-v3"` |
| Owner | LATAM Bank dispute operations (hackathon team) |

## Intended use
Inside the free fallback NLU (`RuleNlu`), used when the language model is down, over budget or disabled
(`NLU_MODE=rules`). Only on turns where the customer says what they want (`START`, `IDENTIFY_TXN`, `CLASSIFY`).
A reading is used only at probability ≥ 0.60 (the policy's own hand-off floor); below it the keyword rules decide.
An out-of-scope reading is used only while the six dispute reasons and "dispute, no reason" together stay below
0.2 (the *dispute guard*): a caller who mixes a request with an unrecognised payment is not turned away.
Its output is a reason code and a routing hint. **It never decides an action**: the versioned policy decides, the
customer confirms a summary that names the reason, and every action is verified by reading it back.

Out of scope: yes/no and evidence answers (rules read those), slot extraction (amount, date, merchant, transaction),
anything outside card disputes, languages other than ES/PT, credit or fraud decisions.

## Training data
`ml/corpus/intent-v1.tsv`: 937 messages, ~50 per label and language, **team-generated** (written by the coding
assistant at the team's request, labelled by construction; no customer data). Near-duplicates of any evaluation
message are removed (1). Compositional augmentation (2 variants per sentence: invented merchants, local amounts and
dates, openers and trailers), one *compound* copy of each reason sentence (an out-of-scope request from the corpus
followed by the dispute, labelled as the dispute) and one *spoken-style* copy of every example (lower case, no
punctuation, call openers), plus **872 real calls** from MInDS-14 (PolyAI, CC BY 4.0; 11 intents that are never a
dispute: balance, app error, card declined, abroad…) as OUT_OF_SCOPE: 7,960 training examples. Cross-validation
groups keep every variant of a sentence, and every call of one MInDS-14 intent, on one side. The organizer data has
no usable customer text (5 distinct complaint descriptions, 42 distinct call transcripts with one intent label).

## Evaluation
| Set | What it is | intent-v3 | intent-v2 | Keyword rules |
|---|---|---|---|---|
| CV (grouped 5-fold) | model selection | macro-F1 0.931 | 0.943 (no speech, easier folds) | 0.508 |
| **Real speech, topics never trained on** (MInDS-14, leave one intent out, 872 calls) | non-disputes sent to the dispute intake, inside the fallback | **7.9%** (CI 6–10%) | 31.1% | 67.3% |
| **Real speech, mixed intents, Portuguese** (never trained on; test) | disputes turned away · unnecessary questions | 4/21 · 24/83 | 2/21 · 47/83 | 2/21 · 78/83 |
| **Independent set** (525 gold) | different author (Sonnet subagent that never saw the corpus), blind second annotator κ = 1.0 | 95.2% alone · **93.5%** inside the fallback NLU | 95.6% · 93.7% | 45.7% |
| test-v3 (frozen before v2) | 23 reason messages from simulated conversations | 23/23 | 23/23 | 22/23 |
| test-v2 run 3 | 23 never-opened messages | 23/23 | 23/23 | 21/23 |
| test-v2 / test-v1 | read during intent-v1 error analysis | 45/46 · 69/69 (post-hoc) | 45/46 · 69/69 | 40/46 · 68/69 |

- Real speech: paired McNemar against intent-v2 on the left-out calls, 208 fixed vs 6 broken, p = 1e-53
  ([report](../ml/results/external-minds14.md)). Without the spoken-style copies the first fit learned "sounds like a
  call → out of scope" and turned away 33 of 44 real disputes; the guard was chosen on the Spanish mixed calls only.
- Conversations: hard-v1 replayed with the free reader, same 32/36 correct, unnecessary escalations 5 → 3;
  channels-v1 unchanged.
- By language (independent set, inside the fallback): ES 244/261, PT 247/264.
- Confident errors: at the 0.60 threshold it accepts 505/525 independent messages, 16 of them wrongly (3.2%).
- Cross-author (intent-v2 configuration): trained on our corpus → 95.6% on the independent set; trained on the
  independent set → 85.5% on ours.
- Alternatives compared: 12 TF-IDF variants; multilingual-e5-small embeddings + LR (CV macro-F1 0.935); the same
  encoder **fine-tuned** on the same data (independent set 93.0% vs 95.6% for TF-IDF, 15× slower on CPU; one seed,
  no hyperparameter search — `ml/results/finetune-e5-small.md`). Neither is deployable on the 512 MB instance.

## Calibration (out of sample)
On the independent set (n = 540): ECE **0.034** (intent-v2: 0.064), Brier 0.065. At the 0.60 threshold it accepts
96.1% of messages at 96.9% accuracy; one bin above 0.6 is slightly less accurate than its stated confidence
([calibration](../ml/results/calibration.md)).

## Risks and limitations
- Real speech is European Spanish and Portuguese call transcripts (MInDS-14), not the bank's Latin American chat
  customers; the rest of the evaluation text is written by language models, and the organizer data has no Portuguese.
  The mixed-intent labels of MInDS-14 were assigned by the coding assistant under a written criterion.
- It turns away more real disputes than intent-v2 (7 vs 2 of 44 mixed calls). The out-of-scope reply asks whether the
  customer wants to dispute a charge, so the dispute is one turn away, not lost. Both independent annotators are Sonnet instances: κ = 1.0 shows the set is
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
