# ADR-024 — Bank first, no chat window: a case board, a workflow diagram and a guided dispute form
- **Status:** accepted · **Date:** 2026-09-28 · extends [ADR-023](ADR-023-case-system-framing.md)

## Context
After ADR-023 the demo still opened on a chat window, and a chat window reads as "a chatbot" whatever sits behind it.
The kickoff asks for a customer-service system; the challenge still requires conversational context, clarification
and Spanish/Portuguese interaction, so the free-text channel stays, but it must not be the product's face.

## Decision
- **The bank side is the main view.** A workflow diagram shows how every case moves: three ways in (app, written
  complaint, fraud alert) → Understand (the only AI step) → Decide (written policy) → Confirm (customer) → Act (bank
  tools) → Verify (read back) → resolved / to a person / closed. With a case selected, its own path lights up with the
  rule ids and verified actions; otherwise each step shows how many cases passed it.
- **Case board** (`GET /agent/cases`, `board.py`): one row per flow from any channel, in four columns (in progress,
  resolved automatically, with a person, closed). Built only from the flow's state and the append-only audit trail —
  never from model output. A case's detail shows the steps, the handoff package with the agent's actions and the audit
  trail. The separate Queue and Decisions tabs are folded into it.
- **Fraud alerts tab:** the alert list the bank sends (score ≥ 35), with a link to open that customer's phone.
- **The customer's app has no chat window.** "Dispute a charge" is a form that fills itself: the charge (tagged *from
  bank records*), the reason (tagged *read from what you wrote*), the details, the result; one current question with
  candidate buttons and quick answers; free text is an input to the form. The message history is one click away.
  Replies carry a `draft` (charge, reason, evidence) so the form shows exactly what the flow holds.
- Scenario order puts the non-chat channels first: 1 written complaints, 2 fraud alert (new, PT, resolved and card
  blocked on request), then the app scenarios.

## Trade-offs
- Same backend flow, templates and evaluation: this changes presentation and adds read-only views, not behaviour.
- The board lives in the demo workspace's memory like the rest of the demo state (restart resets it).
- Tests: `tests/test_case_board.py` (all three channels, stages and outcomes).

## Revision (same day): less on screen, more on demand
The first version showed everything at once (a pitch paragraph, a seven-step diagram with counters, four board columns,
case details under the board, a long scenario hint). The user found it overloaded. Now:
- a one-line top bar (brand, *Guided tour* menu, language, a *⋯* menu with the demo controls); the AI status appears only
  when the AI is off; a scenario's instruction shows in a thin bar only while a tour is running, with *What should
  happen?* folded;
- the five-step path is explained once, in the empty state, with three ways to start; afterwards it appears only inside
  a case, in a side drawer opened by clicking the card;
- cards show who, what and where it came from; the "Closed" column appears only when it has cases; the agent's panel
  shows the request, checked facts and what is still to ask, with rules, risk signals and the audit trail folded;
- written complaints and fraud alerts are one-line lists that expand on click; results show four live numbers and the
  hard-set table, with the chatbot comparison folded.
