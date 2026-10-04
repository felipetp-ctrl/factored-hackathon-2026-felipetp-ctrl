# ADR-033 — A "no" to the fraud alert is read from the stated fact, not the intent
- **Status:** accepted · **Date:** 2026-10-04 · extends ADR-020, ADR-031

## Context
On the deployed demo the fraud-alert scenario sometimes closed by itself: the customer answered "Não fui eu" and the
case appeared as *Closed with no dispute: transaction recognized*, with *Charge not identified* in the bank console.
Reproduced on the live API (two tries, same customer and charge): the first reading was `intent: "dispute"`,
`recognizes_merchant: "no"` (correct); the second was `intent: "confirm"`, `recognizes_merchant: "no"`. The model
"confirmed the no". `_proactive_turn` checked `intent == "confirm"` before the stated fact and closed the alert. The
prompt (nlu-v4) defined confirm/decline only for the CONFIRM state and never described PROACTIVE_CONFIRM, so the
reading varied. The close also left the charge off the flow, hence *Charge not identified*.

## Decision
1. **The stated fact outranks the intent** in the alert answer: `recognizes_merchant` decides when the model filled it;
   the intent decides only when it did not. Erring towards "no" is the safe side: it prepares a FRAUD_CNP dispute
   that is still shown as a summary and needs the customer's yes; erring towards "yes" closed a possible fraud silently.
2. **Prompt nlu-v5** describes PROACTIVE_CONFIRM: "sim, fui eu" is confirm with recognizes_merchant yes; "não fui
   eu" / "no fui yo" / "não reconheço" is decline with recognizes_merchant no.
3. A recognised alert keeps its charge on the closed case, so the console shows what was closed.

## Trade-offs
- A model that returns `confirm` with no fact still closes the alert; the prompt line is what covers that case.
- nlu-v5 changes the cache key of evaluation replays; earlier runs record nlu-v4 in their config and stay
  reproducible. The hard-v1 and channels-v1 numbers were measured with nlu-v4 and were not re-run (the rule reader,
  used by channels-v1, is unchanged).

## Evidence
- Unit tests: `confirm` + `recognizes_merchant: "no"` asks the card question instead of closing; a recognised alert
  keeps TXN007 on the flow. Full suite 372 passed.
