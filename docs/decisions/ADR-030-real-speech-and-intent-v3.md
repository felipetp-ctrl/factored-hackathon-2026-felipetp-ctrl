# ADR-030 — Real customer speech as an external test, and `intent-v3`
- **Status:** accepted · **Date:** 2026-10-01 · extends ADR-019

## Context
Every text the intent classifier had been trained or tested on was written by a language model: the training corpus,
the simulated customers of test-v1/v2/v3 and hard-v1, the independent set. The human review (κ = 0.91) checked labels,
not whether the text looks like what customers say. A judge can fairly ask: does the reader survive real people?

MInDS-14 (PolyAI, CC BY 4.0) has 1,090 es-ES and pt-PT calls to an e-banking line, transcribed by ASR, in 14 intents.
None of them is "dispute a card charge", but three mix in disputes ("show me my latest transactions, there's a payment
I don't recognise"). That gives both directions of the first decision the reader makes: start the dispute intake, or not.

## Decision
1. **Freeze the protocol before training anything.** The 11 intents that are never a dispute (872 calls) keep the
   dataset's labels. The 3 mixed intents (218 calls) were read one by one under a written criterion (DISPUTE /
   NOT_DISPUTE / UNSURE; 44 / 152 / 22) and are **never trained on**. Metric: a non-dispute sent to the intake
   ("which charge do you want to dispute?") and a dispute turned away.
2. **Measure the deployed reader first.** intent-v2 inside the free reader sent **271 of 872 (31%)** non-disputes to
   the intake (abroad, card declined, high-value payment SMS…); keyword rules alone 67%. It kept 42 of 44 disputes.
3. **intent-v3** = intent-v2's corpus and augmentation **plus**
   - the 872 real out-of-scope calls as OUT_OF_SCOPE, one cross-validation group per intent;
   - one *spoken-style* copy of every example (lower case, no punctuation, call openers) — without it the first fit
     learned "sounds like a phone call → out of scope" and turned away 33 of 44 real disputes;
   - one *compound* copy of every reason sentence (an out-of-scope request from the corpus followed by the dispute,
     labelled as the dispute) — callers mix topics;
   - a **dispute guard**: an out-of-scope reading is used only while the dispute labels together stay below 0.2.
     Chosen on the Spanish mixed calls only (dev) at a cost fixed beforehand (one dispute turned away = five
     unnecessary questions); the Portuguese calls are the test.
4. **Honest estimate on unseen topics: leave one intent out.** 11 refits, each scored only on the intent it never saw.

## Evidence ([report](../../ml/results/external-minds14.md), `make external`)
| | intent-v2 (before) | intent-v3 (after) |
|---|---|---|
| Non-disputes sent to the intake, topics never trained on (leave one intent out, n = 872) | 271 (31.1%) | **69 (7.9%, CI 6–10%)** |
| Paired McNemar on the same calls | | 208 fixed / 6 broken, p = 1e-53 |
| Portuguese mixed calls (test): disputes turned away · unnecessary questions · cost | 2/21 · 47/83 · 57 | 4/21 · 24/83 · **44** |
| Spanish mixed calls (dev, chose the guard) | 0/23 · 32/69 · 32 | 3/23 · 17/69 · 32 |
| Independent set (LLM-written, 525), fallback reader | 492 | 491 |
| test-v3 / test-v2 run 3 / test-v2 reasons | 23/23 · 23/23 · 45/46 | 23/23 · 23/23 · 45/46 |
| hard-v1 replay, free reader (36 conversations) | 32/36 correct, 5 unnecessary escalations | 32/36, **3** |
| channels-v1 (letters, alerts) | 23/24 · 17/18 | unchanged |
| Calibration on the independent set (ECE) | 0.064 | **0.034** |

## Trade-offs
- **More disputes turned away (7 of 44 vs 2 of 44 on the mixed calls).** Accepted because it is recoverable: the
  out-of-scope reply ends with "¿Desea disputar algún cargo?", so the customer is one turn from the intake; an
  unnecessary intake leaves a customer with a balance question being asked which charge to dispute. Under the cost
  fixed beforehand v3 wins on the test half (44 vs 57); with a cost ratio above about 12 v2 would win.
- The mixed-call set was used to find the style shortcut and the guard (Spanish half); only the Portuguese half is a
  clean test, and it is small (21 disputes).
- es-ES / pt-PT, not the bank's Mexican, Colombian, Argentine and Brazilian customers. Voice transcripts, not chat.
- The mixed-intent labels were assigned by the coding assistant under the written criterion, not by a person.
- The Claude path was not run on this set (API credit is kept for the judges, ADR-026). The deployed default reader is
  Claude; this changes the free reader that takes over in an outage and reads the written-complaint inbox.
- Artifact grows from 1.5 MB to 2.1 MB JSON; scoring stays at 0.15 ms per message.

## Alternatives
- *Keyword guard* ("pago que no reconozco" beats an out-of-scope reading): would be tuned on the very calls it is
  tested on; the learned guard is one number chosen on the dev half.
- *Keep intent-v2*: 31% of real non-dispute calls start the wrong conversation.
- *Train on the mixed intents too*: would leave no real dispute text to test on.
