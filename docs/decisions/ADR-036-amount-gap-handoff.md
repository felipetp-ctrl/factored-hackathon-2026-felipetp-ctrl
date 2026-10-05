# ADR-036 — A wrong-amount claim far below the charge goes to a person
- **Status:** accepted · **Date:** 2026-10-05 · extends ADR-035

## Context
Found testing the demo: a Mercado Central purchase of ARS 91,558.20 (US$ 261.59). The customer said "achei muito
caro", then "deveria ter custado no máximo 5 reais", and confirmed. The reader filled INCORRECT_AMOUNT with
expected_amount 5. `R-AMOUNT-CHECK` (ADR-035) only asks for `0 < correct amount < charge`, which 5 < 91,558 passes,
so a dispute for almost the whole charge was opened and verified with no one looking at it. The case shows three
problems: a price complaint ("too expensive") is not a billing error, "reais" is not the charge currency, and the
claim is to about 99.99 % of the money back.

## Decision
`R-HO-AMOUNT-GAP`: for INCORRECT_AMOUNT, a correct amount below `min_expected_amount_ratio` × the charge (0.5 in
`disputes_v2`, compared in the charge currency) hands off with reason `implausible_amount_claim`. It runs after
`R-AMOUNT-CHECK`, so an amount that is zero or at/above the charge is still asked again (a reading error), and an
amount far below it goes to a person (a judgement).

## Trade-offs
- A wrong-amount dispute is usually a small gap (tip, rounding, shelf price vs till). A gap above half is either a
  scam or a decimal slip (charged 1,000 instead of 10). Both are real; telling them apart needs the receipt, which
  the chat does not have, so a person checks it. The cost is specialist time on real decimal slips.
- The line is a placeholder like the other thresholds: the organizer data has no claimed-vs-charged amount to
  calibrate on. Evaluation sets ask for 70 % of the charge, so their scores do not change.
- Not changed: the reader still maps "achei muito caro" to INCORRECT_AMOUNT and does not record the currency the
  customer named. The rule catches the demo case without a prompt change (which would need the model-based sets
  re-run); the specialist gets the transcript with both.

## Evidence
Unit tests: the flow hands off "5.00" for TXN001 and opens nothing; the boundary at half the charge (4.99 hands
off, 5.00 and 9.00 of 10 are eligible). Full suite 397 passed, 1 skipped.
