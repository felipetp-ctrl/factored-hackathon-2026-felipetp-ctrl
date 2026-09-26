# ADR-001 — Workflow: card-transaction dispute intake
- **Status:** accepted · **Date:** 2026-09-25

## Context
The challenge asks for one coherent banking workflow; more workflows earn no bonus. Suggested options: account/payment inquiries, card support, transaction disputes, credit eligibility. The team is one person working part-time for 10 days.

## Decision
Card-transaction dispute intake.

## Alternatives considered
- **Card support:** simple verifiable actions, but a thinner ML component.
- **Account/payments:** the simplest and most "typical"; the organizers asked for creativity.
- **Credit:** rich in ML, but it needs an elaborate synthetic policy service and a strict split between conversation, risk estimate and eligibility; risky for a solo team.

## Consequences
- Rich data: `transactions` (status, `is_fraud`, `fraud_score`), `complaints` (category, resolution, SLA) and interactions.
- The three required paths appear naturally (normal, ambiguous, human).
- A sensitive domain: it requires deterministic policy, confirmation and verification (see ADR-002 and ADR-004).
- Validated by the EDA: "Cargo no reconocido" is the only subcategory of the `Transactions` category, 20% of all complaints.
