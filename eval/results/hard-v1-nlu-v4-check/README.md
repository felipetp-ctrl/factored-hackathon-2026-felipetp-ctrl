# nlu-v4 targeted check (not a held-out measurement)

35 requests from the hard-v1 after-run (15 whose nlu-v3 reading set a flag we suspected — very negative sentiment,
regulatory threat, decline at the summary, Spanish on a Portuguese message — plus 20 random others) re-read by a Claude
Haiku subagent with the nlu-v4 prompt. Compared field by field with the nlu-v3 readings in
`../hard-v1-after-test/nlu_cache.json`.

- Fixed on the targeted cases: stressed theft victims no longer flagged very negative (8 readings), "confirmo, mas não
  quero bloqueio" read as confirm, Portuguese messages labelled pt, a bank-transfer complaint read as out of scope
  instead of a human request, a cancelled-subscription message no longer read as a regulatory threat.
- Explicit lawyer/regulator threats kept `regulatory_threat` true.
- Regression seen: "¿cuál es mi saldo? … y también un cobro raro" read as out of scope (dispute under v3). The prompt now
  says a message that also contests a charge is a dispute; that line was added after this check and is unmeasured.
- Part of the differences can be run-to-run variation of the subagent; nlu-v4 needs a held-out run (with the API) before
  its effect is claimed.
