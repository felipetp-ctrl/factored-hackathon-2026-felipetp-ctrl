# ADR-019 — A trained intent/reason classifier inside the free fallback NLU
- **Status:** accepted · **Date:** 2026-09-27

## Context
The challenge asks for at least one learned component evaluated against a baseline, with valid labels, leakage
prevention and justified representations, metrics, thresholds and splits. Until now that component was Claude
Haiku (pretrained) against keyword rules. Nothing was trained by us and nothing was tracked.

The obvious candidate for training, a fraud model, has no signal in this dataset (ADR-020). The task with signal is the
one the service depends on: reading what the customer wants (dispute reason, out of scope, wants a person) from free
text in Spanish and Portuguese. The free fallback NLU (ADR-017) reads it with keywords at 87% on test-v2 reasons,
and the fallback is what customers and judges get whenever the model is down or the credit runs out.

There is no labelled text for this in the organizer data: complaints have 5 distinct templated descriptions and the
200,000 call transcripts have 42 distinct texts with a single intent label (`consulta_general`).

## Decision
- **Labels (9):** the six `ReasonCode`s, `OUT_OF_SCOPE`, `HUMAN`, `DISPUTE_NO_REASON` (wants to dispute, no reason yet,
  including answers that only describe the charge: "la segunda", "a do iFood de 56").
- **Corpus:** `ml/corpus/intent-v1.tsv`, 937 messages, ~50 per label and language (ES with MX/CO/AR registers, PT-BR,
  typos, no accents), **written by the coding assistant in the session** at the user's request, without any API call.
  Labelled by construction. It is team-generated data and is labelled as such everywhere.
- **Leakage guards:** corpus lines with char 3-gram Jaccard ≥ 0.6 to any stored evaluation message are dropped (1 was);
  model and threshold selection use only the corpus (5-fold stratified CV, grouped by source sentence so augmented
  variants never straddle folds); held-out labels come from the scenario ground truth, never from the system.
- **Representation and model:** TF-IDF (sublinear) over word unigrams, word bigrams and character 2–5-grams inside
  word boundaries, on accent-free lower-case text with digits collapsed; multinomial logistic regression (C = 30).
  Selected among 12 TF-IDF variants (feature sets × C) by out-of-fold macro-F1; a multilingual sentence-embedding
  model (`multilingual-e5-small` + logistic regression) was compared and lost (macro-F1 0.935 vs 0.943).
- **Threshold:** the lowest confidence whose out-of-fold accepted predictions are ≥ 95% accurate, floored at the
  policy's 0.6 hand-off confidence → 0.60 (accepts 89% of corpus messages at 98.4% accuracy). Below it, the keyword
  reading stands.
- **Integration (`RuleNlu`):** only in the turns where the customer says what they want (`START`, `IDENTIFY_TXN`,
  `CLASSIFY`); yes/no and evidence answers stay with the rules. A confident reading sets the reason code and its
  probability becomes `reason_confidence` (which the policy checks). For routing, explicit keywords keep precedence:
  an out-of-scope product word outranks a "human" reading. Slots (amount, date, merchant, id) stay rule-based.
  The policy still decides; nothing here can grant an action. The Claude path is unchanged.
- **Runtime:** exported to JSON (15,075 features, 1.5 MB) and scored in pure Python in 0.2 ms; max difference from
  scikit-learn's probabilities 1.5e-6 (checked at export and in a test). No ML library in the API image.
  `INTENT_MODEL=off` returns to keywords only.
- **Tracking:** every candidate is an MLflow run (`make train`, `make mlflow-ui`); reports in `ml/results/`.

## Evidence (offline)
| | intent-v1 (no augmentation) | intent-v2 (deployed) | Keyword baseline |
|---|---|---|---|
| CV macro-F1 on the corpus | 0.939 | 0.943 | 0.508 |
| test-v2 reason messages (n = 46) | 34/46 (74%) | 45/46 (98%) *post-hoc* | 40/46 (87%) |
| test-v1 reason messages (n = 69, all fraud) | 60/69 (87%) | 69/69 *post-hoc* | 68/69 |
| test-v2 run 3, never opened (n = 23) | — | 23/23 (CI 86–100%) | 21/23 |
| Fallback NLU end to end on run 3: reason / out-of-scope / human | — | 22/23 · 3/3 · 1/1 | 21/23 · 3/3 · 1/1 |
| **test-v3** (frozen before intent-v2), fallback NLU end to end: reason | — | **23/23** | 22/23 (rules) |
| test-v3 end-to-end correct · unsafe · safe automated resolution | — | 42/42 · 0 · 25/35 | 42/42 · 0 · 25/35 |

test-v3 customers were played by Claude Sonnet as a Claude Code subagent that saw only persona and transcript (no API
call; the original simulator was `claude-sonnet-5` through the API). The one reason difference is `cancelled-sub-00-pt`,
where the keyword rule matched "cobrado **2**43,12" as a duplicate charge. With n = 23 and one discordant pair the
difference is not significant; the honest reading is "at least as good as the rules, and fixes a real keyword
failure". Two keyword bugs found on test-v3 were fixed afterwards (`83d7ade`), so test-v3 is no longer held-out for
the keyword rules. Details: `eval/results/test-v3-subagent/components.md`.

## How we got here (in order, all committed)
1. intent-v1 trained on isolated clauses scored **worse than keywords** on held-out (74% vs 87%): the simulated
   customers open with "quiero disputar un cargo de X en Y del día Z" and then give the reason, and the model had
   learned that opening as "no reason". The result was committed as is.
2. `test-v3` (42 new scenarios, new seed) was frozen **before** any corpus change, as the clean held-out set for the
   next version; it needs the LLM customer simulator (API credit) to run.
3. intent-v2 adds generic compositional augmentation (invented merchants, local amounts and dates, openers and
   trailers combined with each corpus sentence; no evaluation text). Because the intent-v1 errors were read, the
   test-v2/test-v1 numbers for intent-v2 are post-hoc; run 3 had not been opened.
4. The first run-3 re-score showed one out-of-scope miss ("empréstimo pessoal" read as a person). The routing
   precedence above was added; the run-3 out-of-scope figure is post-hoc from then on.

## Trade-offs and risks
- **A confident wrong reason can reach confirmation.** One test-v2 message was accepted at p = 0.63 with the wrong
  reason. The confirmation summary names the reason ("abriré una disputa por monto incorrecto… ¿Confirma?"), so the
  customer can refuse, but a customer who confirms without reading gets the wrong dispute type. The same risk exists
  with keywords and with Claude.
- Corpus written by the same author as the system: stylistic familiarity is not bounded by the duplicate filter.
- Held-out reasons cover 4 of 6 codes (no DUPLICATE or FRAUD_CP), repeat scenarios across runs, and come from
  LLM-simulated customers; no real customer text exists in the organizer data, and none in Portuguese.
- TF-IDF + LR over a transformer: slightly better here, 100× cheaper, fits the 512 MB free instance; a larger
  real corpus would likely favour embeddings or fine-tuning.

## Next
An independent message set written by a different author with human-checked labels (inter-annotator agreement);
a larger test for a significant comparison; retrain on real, consented customer messages when available.
