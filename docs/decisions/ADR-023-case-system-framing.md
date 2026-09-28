# ADR-023 — Show a case system, not a chat: the written-complaint channel in the demo
- **Status:** accepted · **Date:** 2026-09-28

## Context
The kickoff asks for "a customer-service system, not a chatbot". The system already was one (a state machine owns the
case, a versioned policy decides, write tools are out of the model's reach, actions are verified, handoffs carry a
package) and already had three ways in: chat, written complaints (PQR) and proactive fraud alerts. But the demo opened
on a chat, and the PQR channel existed only as `POST /agent/pqr/run` with no screen, so a judge's first ten seconds
looked like a chatbot.

## Decision
- The demo header states the framing (one case system, three ways in; AI reads, rules decide, actions are checked).
- A **Written complaints** tab on the bank side and a sixth guided scenario process a demo inbox
  (`backend/demo_data/pqr_inbox.json`): six letters (email, web form, branch, app; ES and PT) **written by the team**
  about real charges of the gold sample, because the organizer's complaint texts are five templates.
- Letters are read by the **free reader** (rules + intent-v2), not Claude: one-shot text, no one to clarify, US$ 0, and
  deterministic for judges. Reading is two passes (`channels.read_complaint`): the reason, then the evidence that
  reason requires, the same question the chat would ask, answered by the letter itself.
- The tab shows the real backtest on all 13,580 dispute complaints (15.8% point to one charge) so the demo outcome
  (2 of 6 opened, 4 to a person) is read against the data, not as a success rate.

## Found while building it
A letter threatening to go to the regulator was **opened automatically**: `run_pqr_complaint` did not pass the
regulator-threat and very-negative-sentiment signals to the flow, which the chat does. Fixed; the PQR handoff now also
carries the letter's language instead of always "es". Tests: `tests/test_pqr_inbox.py`, `tests/test_channels.py`.

## Trade-offs
- The inbox is illustrative (n = 6, team-written); it demonstrates behaviour, it is not an evaluation.
- The Operations tab now shows hard-v1 next to test-v2 so the demo does not present only the 100% numbers.
- Not done: the fraud-alert channel still appears only inside the customer app when a customer has a high-score charge.
