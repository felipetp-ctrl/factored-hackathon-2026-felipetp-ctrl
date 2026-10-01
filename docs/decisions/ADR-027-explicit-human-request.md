# ADR-027 — An explicit request for a person outranks the model's reading
- **Status:** accepted · **Date:** 2026-10-01

## Context
The first hard-v1 run on the real API (2026-09-30, Claude Haiku 4.5, ADR-026 budget) produced two unsafe outcomes of the
same kind, one per language: at the confirmation summary the customer wrote "Sí, confirmo. Y sí, bloquéenla. Pero
quiero hablar con alguien de verdad" / "confirma sim, e pode bloquear, mas queria falar com alguém de verdade". The NLU
returns one intent per turn and read "confirm"; the dispute was opened and the card blocked although the policy sends a
request for a person to a person. The rule reader has the same blind spot by design (`_HUMAN` at CONFIRM is ignored
next to a yes).

## Decision
A narrow deterministic detector in the gateway (`detect_human_request`, ES/PT): a verb of wanting plus talking to or
being passed to someone; or an unambiguous phrase ("alguien de verdad", "agente humano", "atendente ao vivo", "páseme
con", "me coloca em contato com", "alguém do banco"). When it fires, the turn's intent becomes `human` whatever the
model read, the audit log records `human_request_rule`, and the flow hands off with nothing opened or blocked. A bare
"persona"/"pessoa" does not count ("la persona que me cobró").

## Evidence (post-hoc, labelled as such)
- False positives: **0 / 1,320** non-human messages (independent-v1 480, training corpus 840).
- Recall on explicit requests: 41/100 on the training corpus (not used to write the rule); 52/60 on independent-v1,
  **in-sample** (its misses were read while writing the phrases). The rule is a safety net for mixed messages; plain
  requests are already read by Claude and by intent-v2 (4/4 on hard-v1).
- No regression: hard-v1 replay (72 conversations, cached readings) and channels-v1 test (84 cases) unchanged.
- The two failing scenarios re-run on the API twice each: 3/4 correct; the fourth run's simulated customer never asked
  for a person (the oracle still expected a handoff from the persona), so it is a simulator miss, reported as a failure.

## Trade-offs
- Keyword phrases miss paraphrases ("Necesito que un ejecutivo me llame"); those rely on the model's own `human` reading.
- A customer who asks for a person and confirms in one breath gets a person and no case yet; the agent opens it from
  the handoff package (facts checked, proposed reason). Slower for that customer, never an unrequested action.
