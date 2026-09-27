# ADR-021 — Learnability scan: the organizer data has no multivariate signal; ML effort goes to the conversation
- **Status:** accepted · **Date:** 2026-09-27

## Context
After the fraud audit (ADR-020) the open question was whether any other outcome in the organizer data would justify a
trained model: satisfaction, first-contact resolution, escalation, SLA, resolution time, delinquency, customer status,
campaign conversion.

## Finding (`make learnability`, `ml/results/learnability_scan.md`)
Same protocol for 9 targets: features known at prediction time, temporal split at 2025-07-01 (seeded 80/20 for
snapshot tables), gradient boosting, a permuted-label control, and a one-column lookup table as a second baseline.

- **No signal (6):** call escalation, complaint SLA breach, resolution days, resolution satisfaction, product
  delinquency, customer status — all at chance, like the permuted control.
- **Signal (3), each carried by one column:** CSAT by `was_resolved` (ρ 0.45 model vs 0.62 lookup), first-contact
  resolution by `contact_reason` (AUC 0.762 vs 0.763), campaign conversion by `send_channel` (0.652 vs 0.660).
  A lookup table on that column matches or beats the model: the generator encodes each outcome as a function of a
  single field. There is nothing multivariate to learn.

## Decision
- No tabular model is trained on the organizer data. The scan, with its controls, is the evidence.
- The trained component stays where the task has structure: reading customer text (ADR-019).
- The one-column effects are used as analysis: complaint contacts ("Queja") have the lowest first-contact resolution
  (43.6%), and CSAT averages 3.0 when a contact is resolved vs 2.0 when it is not (85% vs 15% scoring ≥ 3 on 1–4).
  Resolving a dispute inside the first conversation is therefore the lever on satisfaction in this data
  (`docs/problem_analysis.md` §4, labelled as a projection).

## Trade-offs
- On a real bank's data these outcomes are multivariate and a model would likely pay off; the same scan decides it.
- A synthetic dataset rewards finding its generator rules; we report them as such instead of presenting a fitted
  lookup table as a model.
