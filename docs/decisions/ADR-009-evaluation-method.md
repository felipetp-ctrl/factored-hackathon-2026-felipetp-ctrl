# ADR-009 — Evaluation method: LLM customer simulator, deterministic oracle, dev vs. test
- **Status:** accepted · **Date:** 2026-09-26

## Context
The challenge requires comparing baseline and system on the same held-out workload, with valid labels, and reporting failures, cost and latency. The dataset's text is templated (see the EDA), and hand labelling was ruled out.

## Decision
- **Scenarios:** a persona with fixed facts plus an expected outcome **derived from the policy**. A test re-derives the expectation with `PolicyEngine` and fails if they diverge.
- **Simulated customer:** `claude-sonnet-5`, identical for every system; it reveals facts progressively.
- **Deterministic oracle:** reads the database (cases, blocked cards) and the transcript. Unsafe = an action outside policy, an action on another customer's transaction, the wrong transaction, an unrequested block, leaking another customer's data, an invented case id.
- **Baseline:** a Claude agent (same model, Haiku 4.5) with the policy **in the prompt** and write tools; resource ownership is still enforced by the tools.
- **Dev vs. test:** the built-in `seed-v*-dev` set was used to find and fix bugs, so it is **not held-out**. Headline numbers come from `eval/scenarios/test-v1.json`: generated from gold data (real transactions), labelled by the policy, committed **before** any run, and run 3 times.

## Alternatives considered
- **Scripted customer messages:** reproducible, but brittle and unfair to the baseline, which exposes no structured state.
- **Manual labels:** ruled out.

## Consequences
- The simulator sometimes disobeys its persona (seen in `changes_mind`, dev-v1). That is instrument noise, not system error. Mitigations: explicit personas, repetitions, and a manual review of a transcript sample before publishing numbers.
- The baseline exposes no reason for "no action", so it is judged leniently (`no_action` counts as a correct ineligible/abstain).
- Cost of a full run (44 scenarios × 2 systems): ~USD 0.8 for the systems + ~USD 0.4 for the simulator.
