# ADR-022 — hard-v1: a held-out set built to break the system, and what it changed
- **Status:** accepted · **Date:** 2026-09-28

## Context
Every earlier held-out set scored 100% (test-v1 105/105, test-v2 84/84, test-v3 42/42). Two reasons made those numbers
weak evidence: the simulated customer knew the charge exactly (amount to the cent, date and time), and the labels and
the system come from the same policy. A probe of the deployed fallback with ordinary free text ("uns 90 mil pesos…
acho que clonaram", then "foi no mercado") looped on the same question and handed the customer off although the
charge existed. The Claude path had never been measured on such text either (no API credit).

## Method
- **Set** (`evaluation/hard_set.py`, frozen at commit `9dad5be` before any fix): 18 templates × {dev, test-es, test-pt}
  = 18 dev + 36 test scenarios on real organizer transactions. The customer's memory is made fuzzy by code (amount
  rounded to 2 significant figures, relative day, one word of the merchant) so it stays true to the data. Templates
  include voice-to-text, a reason buried in a story, indirect overcharge/subscription wording, a stolen wallet, several
  charges at one merchant, a wrong pick then a correction, a balance question plus a dispute, unsupported requests with
  complaint words, "it was my kid after all", indirect human/regulator requests, social engineering, a polite injection
  and an expired session. Labels: PolicyEngine on the real transaction (deterministic).
- **Independent author:** personas were written from the briefs by a Claude Sonnet subagent that was told not to read
  the code or earlier sets (`eval/scenarios/hard-v1-personas.json`).
- **Split discipline:** dev transcripts were read to fix the system; test transcripts were not read until the after-run
  was finalized. The before-run used the code at `43289e3` (git worktree); the after-run the code at `c735828` and a
  fresh customer simulator that had not seen the before-run.
- **Claude path without API calls** (`evaluation/interactive.py`): the production Claude NLU is replaced by a cache of
  readings; each missing reading (the exact user content the service sends) is answered by a **Claude Haiku subagent**
  given the verbatim production prompt and schema; readings are validated against `NluResult`. Everything else is the
  production path (gateway, flow, policy, tools, templates, rule fallback). Customers are played by a Sonnet subagent.
- **Oracle fixes made during this work (applied to before and after alike):** every proposed-system variant is judged
  on its final action (test-v3 re-scored: same correctness); a polite close counts as an abstention; a case opened
  under the wrong reason is **unsafe** ("materially incorrect outcome", challenge brief), not only incorrect.

## Results (blind test split, n = 36 per system, 32 in scope, 6 needing a person)

| | Claude path (simulated Haiku NLU) before → after | Fallback (rules + intent-v2) before → after |
|---|---|---|
| Correct outcome | 24/36 → **31/36** | 16/36 → **30/36** |
| Safe automated resolution (in scope) | 13/32 (41%) → **21/32 (66%)** | 5/32 (16%) → **20/32 (63%)** |
| Automation attempted | 15/32 → 23/32 | 8/32 → 23/32 |
| Escalations missed | 0/6 → 0/6 | 1/6 → 0/6 |
| Unnecessary escalations | 12/30 → 4/30 | 21/30 → 5/30 |
| Unsafe | 2 (wrong reason) → 1 | 1 (wrong reason) → 3 (card blocked against the customer's words) |
| Paired change (exact McNemar) | 10 fixed, 3 broken, p = 0.09 | 15 fixed, 1 broken, p = 0.0005 |

Post-hoc (same messages and readings, fix found on this test run, `hard-v1-after-test-posthoc`): the fallback read
"no **la** bloqueen" and "no quiero que **la** bloqueen" as a yes to blocking — a pre-existing rule bug that the
before-run never reached because those conversations ended earlier. With the fix: fallback 32/36 correct, 22/32 safe
resolution, 1 unsafe. The one unsafe left on each path is the same scenario: the simulated customer answered "si hay
que bloquearla, bueno, está bien" although its persona did not want the block; the system blocked because the customer
agreed. We count it as the oracle does and note it as a simulator deviation.

## What was fixed (from the live probe and the dev split only)
- Details accumulate across turns; search is tolerant (amount ±25%, day ±3, one word of the merchant, accent-insensitive)
  and relaxes in order day → amount → merchant; an approximate match is shown for the customer to pick, never taken
  silently; nothing matching shows the latest purchases instead of repeating the question; new details do not use up
  clarifications (cap of 5 rounds).
- Rule NLU: spoken and scaled amounts ("noventa y un mil", "90 mil", "90k"), relative days, "la más reciente / a mais
  cara / la de febrero / la del sábado", "é essa mesmo", "no, esa no, la otra", "foi meu filho, pode deixar".
- The case opened is the one the customer confirmed: a new reading of the reason at the summary no longer changes it
  (dev: FRAUD_CNP confirmed, FRAUD_CP opened — **a pre-existing bug on both paths**); restating the problem at the
  summary is not a "no"; a bare "no" does not answer a different question; a reason already read is not replaced by a
  weaker reading; the classifier needs 0.8 on answers to "which purchase?".
- NLU prompt nlu-v3: `today`, `purchase_date`, `wrong_transaction`.

## Remaining failures (after-run, read after finalizing)
- Claude path: stressed theft victims flagged as very negative sentiment (2) and a subscription message flagged as a
  regulatory threat (1) → sent to a person; "confirmo, mas não quero bloqueio" read as a decline (1); one Portuguese
  message labelled Spanish, so the reply was in Spanish (1). Prompt **nlu-v4** addresses these; a targeted re-read of
  the flagged requests is reported in `eval/results/hard-v1-nlu-v4-check/` — it is not a held-out measurement.
- Fallback: a customer who rejects two candidates and then says "the first one you showed" (2, handed off by the amount
  rule on the wrong pick); a reason buried in a story still ends in a handoff (1); unsupported requests loop until a
  handoff (2).
- Social engineering ends in a handoff on both paths (accepted: nothing is disclosed or opened).

## Limitations
- The NLU is a Haiku **subagent**, not the API: same model family and prompt, different harness, no enforced
  structured-output decoding, no measured latency; cost is a character-count estimate. The first Haiku batch wrote a
  keyword script instead of reading the messages; it was detected (constant confidence 0.85, generic summaries,
  stolen wallet read as FRAUD_CNP) and discarded (`eval/results/hard-v1-discarded/`); later batches were audited for
  varied confidences and message-specific summaries.
- n = 36 per system, one run each; customers and personas are LLM-written; labels come from the policy. Latency in the
  report excludes model time.
- The after-run is one measurement: fixes made after it (card block negation, nlu-v4) are labelled post-hoc.

## Trade-offs
- Showing an approximate match for the customer to pick adds a turn to some conversations; opening a dispute on a
  charge the customer did not clearly choose would be worse.
- Freezing the case at the summary means a customer who changes the reason at the last moment must say "no" and start
  again; the alternative silently opened cases under a reason the customer never saw.
