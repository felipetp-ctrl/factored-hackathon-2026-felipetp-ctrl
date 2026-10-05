# ADR-034 — A duplicate is answered by picking the other charge; with none, the reason is asked again
- **Status:** accepted · **Date:** 2026-10-04 · extends ADR-022

## Context
Found by hand on the deployed demo. The customer tapped a 202.57 USD charge at Restaurante El Buen Sabor and wrote
"foi cobrado duas vezes e nunca estive nesse restaurante antes de abril". The reader returned DUPLICATE, which needs
`duplicate_transaction_id`, and the flow asked "Qual é a outra cobrança idêntica?" with **nothing to pick**. The
field can only be filled with the id of a charge the customer was shown, so no answer could satisfy it: the customer
said "não tem cobrança idêntica, foi 1 mês depois", got the same question again, and the case went to a person
(`clarification_exhausted`). What the customer meant was an unrecognised charge (the other visit was in April).
No held-out chat scenario covered DUPLICATE end to end (only written complaints, which hand off by design), so the
evaluations never exercised this question.

## Decision
1. **The other charge is picked, not typed.** When DUPLICATE lacks the other charge, the flow offers the customer's
   other charges at the same merchant (closest in time first, at most five, never the disputed one). The app shows
   them as buttons; the question says "if none is, tell me what happened".
2. **No other charge, or none picked → the reason is asked again**, prefixed by "with no other equal charge at this
   merchant, it is not a duplicate" (`duplicate_not_found` in the audit). The customer can then say they do not
   recognise it. The existing reason-question bound still hands off after repeated unclear answers.
3. **Only an offered charge counts** as the duplicate reference; a guessed or foreign id is dropped. A pick read as
   `transaction_id` (the buttons send "É a compra <id>") is taken as the other charge.

## Trade-offs
- A real duplicate at a merchant whose name differs between the two charges is not offered; it falls back to the
  reason question and, if the customer insists, to a person, as before.
- Asking the reason again costs one more turn; it replaces a question the customer could not answer.
- channels-v1 (letters and alerts, free readers): unchanged, test 36/42 and dev 19/21 before and after.

## Evidence
- Unit tests: same-merchant charges offered and a pick reaches the summary; no other charge and no pick both return
  to the reason question; a foreign id is ignored; a pick read as `transaction_id` counts. Full suite 377 passed.
