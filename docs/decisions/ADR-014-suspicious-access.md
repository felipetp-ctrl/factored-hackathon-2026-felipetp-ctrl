# ADR-014 — Invalid transaction references: same reply for the customer, real reason for the agent
- **Status:** accepted · **Date:** 2026-09-26

## Context
In `test-v1`, attempts to dispute another customer's transaction were handed to a person with reason
"clarification exhausted", which hid a security signal from the agent. Replying differently to "not yours" and
"does not exist" would let an attacker enumerate valid transaction ids.

## Decision
- The customer always gets the same reply for a foreign or non-existent transaction id.
- The second invalid reference ends the automation: handoff with `suspicious_access` if any reference belonged to another
  customer, otherwise `invalid_transaction_references`.
- The handoff package lists the rejected references in `risk_signals`; it never includes facts about the other customer's
  transaction.

## Consequences
- The agent sees an explicit security reason; ops can alert on its rate.
- Scenarios that test this are marked `handoff_acceptable` so the handoff is not counted as unnecessary.
