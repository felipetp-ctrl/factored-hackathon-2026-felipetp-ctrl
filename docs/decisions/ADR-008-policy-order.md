# ADR-008 — Policy evaluation order and thresholds
- **Status:** accepted · **Date:** 2026-09-25 · thresholds superseded by ADR-013

## Context
`PolicyEngine.evaluate` needs a deterministic order when several rules apply to the same case.

## Decision
Evaluation order:
1. Human requested (`R-HUMAN-REQUEST`).
2. Dispute already open (`R-DUP-OPEN`).
3. Ineligible status (`R-TXN-STATUS`).
4. Outside the window (`R-WINDOW`).
5. Handoff triggers, all reported together: `R-HO-AMOUNT`, `R-HO-REPEAT`, `R-HO-VELOCITY`, `R-HO-ATO`, `R-HO-SENTIMENT`, `R-HO-REGULATOR`, `R-HO-LOWCONF`.
6. Eligible (`R-ELIGIBLE`), with `missing_evidence`.

- A human request comes first, out of respect for the customer's autonomy.
- Ineligibility comes before handoff: explaining the rule to the customer is a safe resolution and needs no person.
- All handoff triggers are listed, not just the first, to give the agent more context.

## Consequences
- Each decision carries `rule_ids`, `policy_version` and `inputs`, which serve as the auditable explanation.
- v1 thresholds were placeholders; ADR-013 replaces them with values calibrated on the data.
