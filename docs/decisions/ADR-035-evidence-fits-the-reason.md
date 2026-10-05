# ADR-035 — Policy review: the evidence must fit the reason, and the customer can correct the reason
- **Status:** accepted · **Date:** 2026-10-04 · extends ADR-010, ADR-031, ADR-034

## Context
After ADR-034 (a duplicate question the customer could not answer), every reason in `disputes_v2` was reviewed for
problems of the same kind: a customer stuck on a question, or a case opened on answers that contradict the reason.
The policy engine only checked that each required field was **present**. Probing the flow directly showed:

| Reason | What happened before | Kind |
|---|---|---|
| any | A different reason said while evidence was being asked ("na verdade não reconheço") was ignored when the reading was less sure than the first one; the same question repeated until a hand-off | stuck |
| FRAUD_CNP | "Card not with me" still opened card-not-present fraud; by the reader's own definition (FRAUD_CNP = card still with them, FRAUD_CP = lost or stolen) that is FRAUD_CP. ADR-031 corrected this only at the summary | wrong reason |
| INCORRECT_AMOUNT | A "correct amount" equal to or above the charge, or zero, opened a dispute. The free reader took the **largest** amount in "foi de USD 288,69, mas o combinado era de USD 202,08", i.e. the charge itself; two channels-v1 letters were opened with that amount and scored correct, since the judge does not check the amount | wrong evidence |
| NOT_RECEIVED | A delivery date still in the future opened a dispute | not yet due |
| CANCELLED_RECURRING | A cancellation **after** the charge opened a dispute (the charge predates the cancellation) | not disputable |
| CANCELLED_RECURRING, NOT_RECEIVED | The free reader stored "não lembro" as the date | wrong evidence |
| any (summary with the block offer) | The summary ends with "do you want the card blocked?"; a typed bare "não" (meant for the block) cancelled the whole dispute. The buttons were unambiguous; typing was not | stuck |
| FRAUD_CP | "Card with me now" was left as is: the question is in the present tense, so a recovered card is consistent | no change |
| FRAUD_CNP | "I recognise the merchant" was left as is: fraud at a known merchant is plausible | no change |

## Decision
1. **Content rules** in the policy engine, after the required fields are present: `R-AMOUNT-CHECK` (the correct
   amount must be above zero and below the charge; otherwise it is asked again with the charged amount shown, bounded
   like any question), `R-NOT-DUE` (ineligible until the expected delivery date, with the date in the answer) and
   `R-CANCEL-AFTER` (ineligible when the cancellation is after the charge). Dates kept as the customer's words are not
   judged; they reach the agent as said.
2. **FRAUD_CNP with the card not in possession becomes FRAUD_CP** before the policy runs (`reason_corrected`).
3. **A reason correction is followed** in the evidence step when the message answers nothing that was asked and the
   reading is usable (≥ 0.6, the policy's confidence floor). A short answer that does answer the question keeps the
   first reason, as before (ADR-022). The summary still shows the reason before anything is opened.
4. **A bare "no" after the block offer is asked about** ("is your no for the dispute or only for blocking the
   card?"), bounded like any unclear answer to the summary; "não, cancelar" and the buttons still cancel.
5. Free reader: the correct amount is the **smallest** amount written; "não lembro / no me acuerdo" is not a date.

## Label correction (channels-v1)
The three `alert-lost-card` scenarios expected FRAUD_CNP ("lost the card days ago and do not have it"). That
contradicts the written definition above and the hard-v1 grading, which counted a stolen card opened as FRAUD_CNP as
unsafe. Their expected reason is now FRAUD_CP (generator and committed sets; same transactions and texts). With the
corrected labels the old code scored test 38/42 with 2 unsafe; the new code scores 40/42 with 0 unsafe (dev 20 → 21
of 21). The published headline is unchanged: letters 23/24, alerts 17/18, 0 unsafe; the two wrong-amount letters are
now opened with the correct amount.

## Trade-offs
- A customer who mistypes the correct amount gets one more question; a reading error now costs a turn instead of a
  wrong case.
- R-NOT-DUE and R-CANCEL-AFTER trust an ISO date from the reader; a misread year would decline wrongly. The answer
  states the date it used, so the customer can see it, and a person can still be asked for.
- The hard-v1 and test-v3 conversation sets were not re-run (they need simulated customers and model calls). None of
  their scenarios uses INCORRECT_AMOUNT with an amount at or above the charge, a future delivery date or a
  cancellation after the charge; the reason-correction and CNP→CP changes can change some of their transcripts.

## Evidence
- Unit tests for every row marked as a problem above, plus "a short answer keeps the reason" and "cancelled before
  the charge is still disputable". Full suite 392 passed.
