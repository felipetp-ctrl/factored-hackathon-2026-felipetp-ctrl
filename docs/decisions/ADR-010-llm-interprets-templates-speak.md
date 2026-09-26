# ADR-010 — The LLM interprets; templates speak
- **Status:** accepted · **Date:** 2026-09-26

## Context
The challenge asks to "report only actions whose outcomes the system has verified" and to enforce policy outside model prose.

## Decision
- Claude Haiku 4.5 turns the message, already redacted by the gateway, into a structured object validated with Pydantic (`NluResult`). It calls no write tools and writes no replies.
- Customer replies come from Spanish/Portuguese templates filled only with verified data: the case id read back, the card status read back, the rule and the numbers from the policy.
- **This replaces, for now, the spec's plan of Claude as an agent with read-only tools.** Structured extraction proved sufficient, cheaper and easier to evaluate.

## Alternatives considered
- **LLM writes free replies:** more natural, but it can claim actions that never happened; it would need an extra verifier.
- **Agent with read-only tools:** more flexible, but more variance and cost.

## Consequences
- No reply can invent a case id or a block; the oracle checks this (`fabricated_case_id`).
- Replies are less fluid. The candidate list had to show the time of day (a bug found in the dev evaluation).
- The customer message is delimited as data with HTML escaped; injection signals are passed as context and never grant or remove permissions.
