# ADR-002 — Automation boundary: full intake + confirmed card block
- **Status:** accepted · **Date:** 2026-09-25

## Context
We must define what the system resolves alone, what needs confirmation and what goes to a person. The challenge does not authorize moving money.

## Decision
The system authenticates, identifies the transaction, classifies the reason code, collects evidence, checks eligibility against the policy, opens the case and verifies that it exists. For fraud it offers to block the card; the block only happens with explicit confirmation and is verified by reading it back.

| Automatic | Needs confirmation | Human |
|---|---|---|
| Look up transactions, check policy, classify, open the case | Open the dispute (summary confirmed), block the card | Amount above threshold, repeat complainer, dispute velocity, account-takeover signals, explicit request, very negative sentiment, regulator/legal threat, low confidence, tool or verification failure |

## Alternatives considered
- **Intake only:** safer, but without a real act-and-verify cycle.
- **Simulated provisional credit:** that is money movement, out of scope, and opens a safety gap.

## Consequences
- "Safe resolution" = case opened with the correct transaction, reason code and evidence, or a correct refusal by policy with the rule explained.
- No monetary action; the asynchronous channel never blocks a card (no synchronous confirmation is possible there).
