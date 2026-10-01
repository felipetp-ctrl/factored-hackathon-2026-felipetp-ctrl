# ADR-031 — A fact the policy relies on must have been said; a contradicted summary is not opened
- **Status:** accepted · **Date:** 2026-10-01 · extends ADR-010, ADR-022

## Context
The hard-v1 run on the real API (ADR-026) left one unsafe outcome without an explanation: `stolen-wallet-01-pt` opened
**card-not-present fraud** for a customer whose card had been stolen. The stored readings show why:

1. The opening was "tem uma cobrança aí no meu cartão que eu não reconheço…". Claude Haiku returned
   `card_in_possession: "yes"`. The customer never said where the card was. FRAUD_CNP requires that evidence, so the
   flow had it and skipped the question "is the card with you?".
2. At the summary the customer answered "sim, confirmo… já foi roubado junto com minha carteira". The reading changed
   to FRAUD_CP and `card_in_possession: "no"`, but a confirmed summary is frozen (ADR-022, so that a noisy re-reading
   cannot change what the customer confirmed), and the case opened as FRAUD_CNP.

The model guessed a fact, and the flow trusted the guess. The rest of the design (ADR-010) already says the model
interprets and the code decides; the code was not checking that the interpreted fact had been stated.

## Decision
1. **Grounding check on card possession** (`ConversationService._ground`). A Claude reading of `card_in_possession`
   is kept only if the flow had just asked that question, or the customer's own words so far say where the card is
   (the rule reader's possession words, either way, plus wallet/bag words). Otherwise it is dropped, the drop is
   audited (`ungrounded_evidence_dropped`) and the flow asks. The free reader is grounded by construction.
2. **A summary contradicted at confirmation is corrected, not opened** (`DisputeFlow._resummarize`). If the answer to
   the summary says the card is lost or stolen while the summary rested on "the card is with me", nothing is opened:
   the evidence is updated, an unrecognised charge becomes FRAUD_CP, the policy is evaluated again and the corrected
   summary is shown for confirmation (`summary_corrected` in the audit). A block requested in that answer is carried
   to the confirmation. A plain re-reading of the reason still cannot change a confirmed case.

## Evidence
- Unit tests: an ungrounded "yes" is dropped and the question asked; a grounded one ("la tengo conmigo") is kept; the
  stolen-wallet answer produces a corrected FRAUD_CP summary, then a FRAUD_CP case and a blocked card.
- hard-v1 replay with the cached Claude readings ([partial replay](../../eval/results/hard-v1-replay-grounding/README.md)):
  66 of 72 conversations identical; in **6 of 36 Claude-path conversations (17%) the model had filled card possession
  without the customer saying it** — those now get one more question and need a new simulated turn to be scored.
- **Real API, post-hoc** ([check](../../eval/results/hard-v1-api-adr031/README.md), US$ 0.29): the 7 affected
  scenarios × 2 runs — **14/14 correct, 0 unsafe** (before ADR-031: 13/14, 1 unsafe). The card question was asked in
  8 of 12 disputes; stolen-wallet-01-pt opened FRAUD_CP with the card blocked in both runs. There the simulated
  customer mentioned the theft up front, so the summary-correction path is still covered by the unit test only.
- Two older tests were written the same way (the fake reading said "card with me" for "no reconozco 1250"); their
  messages now state where the card is.

## Trade-offs
- About one conversation in six on the Claude path gets one more question ("¿Tiene la tarjeta con usted?").
- A customer who implies possession in words the cue list misses ("la uso todos los días") is asked anyway.
- Only card possession is grounded: it decides the fraud type and the block. `recognizes_merchant` is still taken from
  the reading; "no reconozco" is in almost every unrecognised-charge opening.
- The API check is post-hoc and small (7 scenarios chosen because the change affects them), not a new held-out result.

## Still open (from the same run)
`subscription-01-pt`: a subscription the customer only called "não reconheço" was opened as FRAUD_CNP, expected
CANCELLED_RECURRING. A fix would ask a recurring biller's customer whether they ever subscribed; it needs a new
evidence field in the model's schema (a prompt change), which cannot be measured without spending judge credit.
