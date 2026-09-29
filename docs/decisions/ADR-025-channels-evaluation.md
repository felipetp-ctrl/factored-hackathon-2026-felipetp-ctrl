# ADR-025 — channels-v1: a held-out evaluation for written complaints and fraud-alert answers
- **Status:** accepted · **Date:** 2026-09-28

## Context
The demo leads with three ways in (ADR-023/024), but only the app conversation had held-out evaluations (test-v1…v3,
hard-v1). Written complaints (PQR letters) and answers to proactive fraud alerts were covered by unit tests and six
illustrative letters. A judge could fairly say: three channels shown, one measured.

## Method
- **Set** (`evaluation/channel_set.py`, frozen at commit `96f0a75` before any run): 12 letter templates and 9 alert
  templates on real transactions of the demo gold sample; each template gives one dev case and one test case per
  language → 21 dev + 42 test (24 letters, 18 alerts). Templates cover complete and incomplete letters, every reason
  whose evidence a letter can carry, a duplicate (whose evidence a letter cannot carry), a vague letter with no amount or
  card, amount above the limit, a regulator threat, a request for an advisor and an out-of-window charge; alerts cover
  "not me" with and without a card block, a lost card, "it was me" plainly and through a story, a request for a person,
  a refusal at the summary, and an unsure first answer.
- **Labels:** computed by code from the brief, not by a model — the channel's charge matcher on the structured PQR
  fields, then the PolicyEngine (handoff triggers, window, missing evidence). A test re-generates the briefs and checks
  they equal the committed file, so labels cannot drift.
- **Text:** written by a Claude Sonnet subagent that received only label-free briefs and was told not to read the
  repository (`eval/scenarios/channels-v1-texts.json`).
- **Harness** (`evaluation/channels_eval.py`): letters go through `channels.process_letter`, the same function the demo
  inbox uses; alerts through the conversation service with a scripted customer whose lines were written in advance and
  are picked by what the bank asks. No model calls: the deployed free reader (rules + intent-v2) against the keyword rules
  alone; for letters, "everything to a person" (the bank's current process) as a reference row.
- **Discipline:** test run once before any fix (aggregates only read), dev read and fixed, test run once after.

## Results (test, n = 24 letters, 18 alerts; offline, deterministic)
| | Before fixes | After fixes | Keyword rules after | Everything to a person |
|---|---|---|---|---|
| Letters: correct | 19/24 | **23/24** | 19/24 | 12/24 |
| Letters: safe automated resolution | 9/24 | **11/24** | 7/24 | 0/24 |
| Letters: unsafe | 4/24 | **0/24** | 0/24 | 0/24 |
| Alerts: correct | 16/18 | **17/18** | 17/18 | — |
| Alerts: unsafe | 0/18 | 0/18 | 0/18 | — |

Deployed vs keyword rules on letters: 4 vs 0 discordant pairs (exact McNemar p = 0.125, n = 24: a direction, not
proof). On alerts the learned classifier adds nothing: alert answers are short yes/no replies the keyword rules already
read. Whole-case latency p50 2.4 ms, p95 5.0 ms on a laptop, US$ 0 model cost.

## What the dev split found (fixed before the test after-run)
- **Unsafe:** "Pode deixar, não precisa abrir disputa, era mesmo uma compra minha" at the summary was read as a yes
  ("pode" is a yes-word) and **opened a dispute**. Refusals are now checked before yes-words, with a guard so that
  "sim, mas prefiro não bloquear" stays a yes without a block.
- **Unsafe:** "não sei" to a fraud alert was read as "not me" and started a dispute. Unsure answers now re-ask; three
  unclear answers hand the flagged charge to a person, nothing opened.
- **Unbounded:** the confirmation summary repeated forever on an answer it could not read; two unclear answers now go
  to a person (the same bound as every other question).
- A regulator threat in Portuguese ("órgão regulador bancário") was missed and the letter was auto-opened (the
  before-run's other unsafe outcomes); a stolen-card letter was filed as card-not-present fraud; indirect recognition
  ("deve ser aquele presente que comprei") was not read as "it was me".

## Remaining failures (test, not fixed: fixing them now would be post-hoc)
- "Yo tengo mi tarjeta en mano" is not read as the card being in the customer's possession → the letter goes to a person
  as missing information (safe, unnecessary handoff).
- "Ya vi bien, no, esa compra no fue mía" after an unsure first answer is not read as "not me" → after the bound, the
  alert goes to a person (safe, unnecessary handoff).

## Limitations
- Small: 24 letters and 18 alerts in the test split; one run (the pipeline is deterministic, so repeats are identical).
- The Claude reader is not measured here (no API credit).
- Alert customers are scripted, not interactive; a question the author did not foresee gets "I don't know" (one gap in
  the test run).
- Structured PQR fields are taken as the intake form gives them; the channel reads only the free text.
- The fixes change how the summary and the alert question are read in every channel. Regression check (2026-09-29):
  hard-v1's recorded customer messages and NLU readings replayed on the current code (`eval/results/hard-v1-replay-0929`)
  finish all 72 conversations without diverging and give the same outcomes as the last measurement (free reader 32/36,
  Claude path 31/36, one unsafe each). test-v3 was not replayed.
