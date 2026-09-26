# ADR-004 — Hybrid orchestration
- **Status:** accepted · **Date:** 2026-09-25

## Context
Permissions and policy must be enforced outside model-generated prose, and the system may only report verified actions.

## Decision
`DisputeFlow`, a deterministic state machine, owns the case lifecycle and is the only caller of write tools (`open_dispute`, `block_card`): only after a `PolicyEngine` decision, explicit confirmation and a read-back verification. The language model works only in conversational states and produces structured `Turn` objects; the flow never sees free text. (ADR-010 refines the model's role.)

## Alternatives considered
- **Pure state machine with the LLM only for NLU/NLG:** the most predictable, but a rigid conversation.
- **Free agent with guardrails inside the tools:** flexible, but higher run-to-run variance and risk of claiming actions that never happened.

## Consequences
- The safety boundary is testable without any LLM (cross-customer access, expired/forged/swapped sessions, tool failure, failed verification are unit-tested).
- Tools take the session token; the resource owner comes from the token, never from an id supplied by the model.
- Explanations come from rules (`rule_ids`, `policy_version`, `inputs`) and the append-only audit log, not from chain-of-thought.
- Cost: more code than a free agent.
