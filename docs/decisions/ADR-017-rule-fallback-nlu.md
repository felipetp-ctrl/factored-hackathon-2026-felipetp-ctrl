# ADR-017 — A free rule-based NLU takes over when the model is unavailable or over budget
- **Status:** accepted · **Date:** 2026-09-27

## Context
In v0.0.1 a model outage made the chat hand every conversation to a person after a retry. During the review the API
credit ran out and the deployed chat did exactly that, which to a judge looks like a broken system. The judging window
is ten days and API spend has to stay bounded.

## Decision
- `RuleNlu` fills the same structured `NluResult` as the Claude NLU from rules: the keyword reason classifier
  (the component baseline), a merchant vocabulary (all merchant names, no customer data), amounts in local formats
  (1.575.714,48 / 91,558.20 / $452.16, ignoring dates, times and ids), yes/no answers mapped to the question the
  service just asked, candidate picks (ordinal, time, amount, id), card-block wishes with negation, regulator threats.
- `ConversationService` uses Claude first; on an API failure, an open circuit, a reached spend cap or a simulated
  outage it uses the rules and audits `nlu_fallback` with the reason. Every reply says which one read it (`nlu_mode`).
- `NLU_MODE=auto|claude|rules`; `auto` without an API key runs rules only. `LLM_BUDGET_USD` (default 20) is shared by all
  demo workspaces of the process; the hard cap stays the provider's workspace spend limit.
- Nothing else changes: the policy still decides, low-information turns are clarified twice and then handed off.

## Evidence (offline, no model calls)
Re-scored on the stored test-v2 customer messages (`eval/results/20260926T181317Z-test-v2/components_rescored.md`):
reason accuracy 87.0% (40/46) vs 100% for Claude; out-of-scope recall 100% (8/8, but see the leakage note: one rule was
fixed after reading two of these messages); human-request detection 2/2. The five demo scenarios pass end to end on
the gold sample with rules only (`tests/test_demo_scenarios.py`).

## Trade-offs
- Rules miss paraphrases (6/46 reasons, all less common reasons): those customers get a clarifying question or a person,
  never a wrong action, because the policy and confirmation steps are unchanged.
- The rule confidence is fixed at 0.75, above the policy's 0.6 floor, so a matched reason can proceed.
- A full end-to-end evaluation of fallback mode needs the LLM customer simulator (credits); not run yet.
