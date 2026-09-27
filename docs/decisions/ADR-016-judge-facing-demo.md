# ADR-016 — The demo is a bank app beside the bank side, with guided scenarios
- **Status:** accepted · **Date:** 2026-09-27 · supersedes the layout part of ADR-007

## Context
v0.0.1's web app was a developer console: the visitor picked an opaque customer id, got an empty chat, could not see
any purchase, and every bank-side view sat behind an agent key the judges did not have. The kickoff's first criterion
is that judges can use the deployed solution; they have minutes, not an onboarding.

## Decision
- **One split screen.** Left: what the customer sees, a small bank app in Spanish or Portuguese (greeting with the
  synthetic first name, card and status, recent purchases, a fraud alert when there is one, the assistant, and
  "my disputes" read from the case store). Right: what the bank sees, in English (handoff queue with agent actions,
  the decision trail of the current conversation, operations counters and the held-out results).
- **Start from a purchase.** "I don't recognise this" on a purchase starts the conversation with the transaction
  already identified (ownership checked by the tool layer), so the common path is two questions and a confirmation.
- **Five guided scenarios** (normal, ambiguous, out of scope, needs a person, attack) in a top bar, each with what to
  do and what should happen, on real customers of the gold sample. A free customer picker stays for exploration.
- **"Why?" under every bank message**, built only from the policy decision and flow outcome returned with the reply,
  never from model text.
- **Agents act on the queue.** A handed-off case can be opened or closed by the agent. Opening re-evaluates the policy
  as a human review (`R-HUMAN-REVIEW`): handoff triggers no longer block, ineligibility rules still do; the case is read
  back before it is reported, and the action is audited on the conversation's trace. The customer sees the case
  appear under their disputes, marked as opened by a specialist.
- **Demo mode** (`DEMO_MODE=true`, public deploy only): each browser tab gets its own copy of the data (workspace,
  LRU of 40), so one judge's dispute does not break another judge's scenario, and bank-side routes open without a key
  because the data is synthetic and there is no staff login. Controls for the failure paths: expire the session,
  simulate a model outage, reset.

## Alternatives
- Replay recorded conversations as the main experience: never breaks, but it is not something the judges can use.
- Keep the console and only translate it and remove the key: cheapest, still a developer tool.
- Real staff login for the bank side: right for production, a barrier for a demo with synthetic data.

## Consequences
- Judges can go through the three required paths and see the handoff land with the agent in about three minutes.
- Demo mode weakens access control on purpose; it is off by default and documented in operations.md.
- Workspaces live in process memory: a restart resets every visitor's demo (acceptable for a demo; see ADR-011).
