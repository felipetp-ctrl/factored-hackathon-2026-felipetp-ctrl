# Requirements traceability

Every requirement of the challenge (problem statement + kickoff), where it is met, and how to verify it yourself.
Status: ✅ met · 🟡 partial (gap stated) · ⬜ not yet.

## Scope

| Requirement | Status | Evidence | How to verify |
|---|---|---|---|
| Working prototype of one coherent workflow | ✅ | Card-charge dispute intake end to end ([ADR-001](decisions/ADR-001-workflow.md)); judge-facing demo with guided scenarios ([ADR-016](decisions/ADR-016-judge-facing-demo.md)) | Live web app, scenarios 1–5 · `tests/test_demo_scenarios.py` |
| Normal resolution path | ✅ | Identify → reason → evidence → policy → confirm → act → verify | Web: "No reconozco un cargo de …" · `tests/test_flow.py::test_normal_path_*` |
| Ambiguous or unsupported request | ✅ | Candidate lists, bounded clarification, out-of-scope abstention | `test_ambiguous_merchant_asks_with_candidates`, `test_out_of_scope_abstains_*`; test-v2 `same-merchant-*`, `oos-*` |
| Case requiring human intervention | ✅ | Structured handoff on 11 triggers | Agent view; `test_high_amount_hands_off_with_verified_facts`; test-v2 `human_required` 16/16 |
| Spanish and Portuguese interactions | ✅ | Language gateway, NLU, ES/PT templates | test-v2 by language; web language selector |
| Report limitations in data and language coverage | ✅ | README "Known limitations", [problem_analysis §5](problem_analysis.md), [data_quality_report](data_quality_report.md) | Read |
| Evidence of production readiness + honest account of remaining work | ✅ | [operations.md](operations.md) | Read |

## 1. A problem supported by data

| Requirement | Status | Evidence |
|---|---|---|
| Contact reasons | ✅ | Call-center reasons, FCR and handle time; complaint categories ([problem_analysis §1–2](problem_analysis.md)) |
| Demand patterns | ✅ | 377 disputes/month, flat 2023–2026; channel mix |
| Data quality | ✅ | [data_quality_report.md](data_quality_report.md) + defects found: USD amounts missing for Mexico, foreign product references, orphan branches, no duplicates |
| Operational constraints | ✅ | 69.5% backlog, 37 h first response, 20% SLA breaches, intake gaps; PQR backtest (84% not matchable) |
| Prioritise the workflow with this evidence | ✅ | [ADR-001](decisions/ADR-001-workflow.md), problem_analysis |
| Intended customer and business outcomes | ✅ | problem_analysis §3–4 (projection labelled as such) |

## 2. A functioning AI system

| Requirement | Status | Evidence |
|---|---|---|
| Maintain conversational context | ✅ | Flow state + recent turns in NLU context; language fixed after the first turn; polite endings ([ADR-018](decisions/ADR-018-conversation-fixes.md)) |
| Clarify ambiguity | ✅ | Ask-for fields, candidate lists, max 2 attempts then handoff |
| Ground factual responses in permitted information | ✅ | Replies are templates filled only from verified store data ([ADR-010](decisions/ADR-010-llm-interprets-templates-speak.md)) |
| Use tools when they serve the workflow | ✅ | `BankingTools` (search, get card, case status, open dispute, block card) |
| Report only verified actions | ✅ | Read-back verification before any "done"; oracle checks `fabricated_case_id` |

## 3. Controlled automation

| Requirement | Status | Evidence |
|---|---|---|
| Define what is answered / needs confirmation / abstains or transfers | ✅ | [ADR-002](decisions/ADR-002-automation-boundary.md) table |
| Enforce permissions and policy outside model prose | ✅ | Versioned policy YAML + state machine; write tools never exposed to the model ([ADR-004](decisions/ADR-004-hybrid-orchestration.md)) |
| Handoff with request, verified facts, actions, evidence, open questions | ✅ | `HandoffPackage` (no raw transcript) with customer and transaction; agent queue can open the dispute under a human-review policy or close it, audited (ADR-016) | Web: scenario 4 → Queue · `tests/test_api_demo.py` |

## 4. Sound data and ML practice

| Requirement | Status | Evidence |
|---|---|---|
| Repeatable preparation with contracts | ✅ | `pipeline/contracts.py`, `make data` ([ADR-012](decisions/ADR-012-data-pipeline.md)) |
| Quality checks | ✅ | Rejects, cast failures, domains, ranges, required nulls, duplicates, orphans |
| Lineage | ✅ | `_source_file`, `_ingested_at`, `_batch_id`; `amount_usd_source`; run manifests |
| Update / freshness policy | ✅ | Incremental bronze, recomputed silver; late-arrival and correction test on a labelled fixture |
| ≥ 1 learned component evaluated against a baseline | ✅ | Trained intent/reason classifier intent-v2 (TF-IDF + LR, ES/PT) vs keyword baseline and a sentence-embedding model, CV and held-out ([ADR-019](decisions/ADR-019-learned-intent-classifier.md), [report](../ml/results/intent-v2.md)); Claude Haiku NLU vs keywords (component report); fraud labels audited: no learnable signal ([ADR-020](decisions/ADR-020-fraud-label-audit.md)) |
| Valid labels / relevance judgments | ✅ / 🟡 | Expected outcomes derived from the policy on real transactions; re-derived by a test. Intent corpus labelled by construction by its (AI) author; human review sample pending |
| Prevent leakage | ✅ / 🟡 | Test sets frozen by commit before any run; dev set separate ([ADR-009](decisions/ADR-009-evaluation-method.md)); intent corpus de-duplicated against every evaluation message, CV grouped by source sentence. Disclosed exceptions: one fallback rule and intent-v2's augmentation were motivated by reading test-v2 errors (post-hoc, labelled in the reports); `test-v3` frozen before intent-v2 for a clean re-check |
| Justify representations, metrics, thresholds, splits | ✅ | ADR-009, ADR-013 (threshold calibrated at p90 of real amounts), ADR-019 (TF-IDF vs embeddings, macro-F1, confidence threshold from out-of-fold accuracy), ADR-020 (temporal split, PR-AUC vs prevalence, alert threshold fixed on train and checked on test) |
| Model tracking | ✅ | MLflow runs for every candidate (`make train`, `make fraud-audit`, `make mlflow-ui`); model version recorded on every NLU turn (`rules+intent-v2`); model + prompt versions in every evaluation report |

## 5. Measured quality and failure handling

| Requirement | Status | Evidence |
|---|---|---|
| Held-out evaluation | ✅ | `eval/scenarios/test-v1.json`, `test-v2.json` (frozen) |
| Incorrect or missing data | ✅ | Vague customers, missing evidence, reversed / out-of-window transactions |
| Expired sessions | ✅ | `expired-session-*`; unit tests for expired, forged, swapped sessions |
| Unauthorized access attempts | ✅ | `cross-customer-*` → `suspicious_access` ([ADR-014](decisions/ADR-014-suspicious-access.md)) |
| Prompt injection | ✅ | `injection-*`, gateway flags (TPR 100%, FPR 0% on test-v2) |
| Tool failures | ✅ | `tool-failure-*`, bounded retry, handoff without claiming success |
| Multilingual ambiguity | ✅ | `mixed-language-*` |
| Report success, unsafe, handoff, latency, cost, sample sizes, limitations | ✅ | Every `eval/results/*/report.md` |

## 6. A credible route to operation

| Requirement | Status | Evidence |
|---|---|---|
| Tracing | 🟡 | Per-conversation audit trace + request logs with ids; OpenTelemetry export not wired |
| Bounded retries | ✅ | `call_with_retry` (max 2) |
| Safe fallback | ✅ | Model down, circuit open or spend cap reached → rule-based NLU with the same guards ([ADR-017](decisions/ADR-017-rule-fallback-nlu.md)); no fallback → handoff with reference | Web: "Simulate AI outage" · `test_model_failure_uses_the_rule_fallback_*` |
| Reproducible setup | ✅ | `uv`, `pnpm`, Makefile, Docker image verified, CI workflow |
| Capacity, monitoring, access control, retention, remaining work | ✅ | [operations.md](operations.md) |
| Explanations from sources, policy rules and execution records | ✅ | `rule_ids`, `policy_version`, `inputs` on every decision; decision inspector in the web app |

## Data and execution boundaries

| Requirement | Status | Evidence |
|---|---|---|
| Only organizer-approved data | ✅ | Organizer S3 dataset + team-generated fixtures; no external data |
| Label real / synthetic / team-generated inputs | ✅ | README "Data", fixture READMEs, report headers |
| No private data or credentials in the repo or external model requests | ✅ | `.env` ignored; S3 credentials only in a local AWS profile; PII masked before model calls |
| Sandbox tools with documented contracts | ✅ | Pydantic contracts in `tools.py`; mock over SQLite |
| Authentication via a trusted test session | ✅ | HMAC tokens with TTL; a customer id alone is rejected (tested) |
| Access enforced in the tool layer | ✅ | Ownership check on every tool call |

## Evaluation evidence

| Requirement | Status | Evidence |
|---|---|---|
| Baseline and proposed on the same held-out workload | ✅ | Same scenarios, same simulator, same data copy per conversation |
| Number and mix of cases, label quality, model/prompt versions, repeated runs | ✅ / 🟡 | Report headers; by-run tables. test-v2 has 2 of 3 runs (credit ran out) |
| Include failures | ✅ | "Failures" table in every report; invalid runs kept and labelled |
| LLM judge validated against humans | n/a | No LLM judge: outcomes are judged deterministically. 🟡 Simulator fidelity still needs a human review sample |
| Safe automated resolution + share attempted | ✅ | Headline metrics |
| Containment | ✅ | Headline metrics |
| Escalation quality (missed and unnecessary) | ✅ | Headline metrics |
| Unsafe outcomes with counts and denominators | ✅ | Headline metrics + reasons |
| p50/p95 latency, cost per attempted case and per resolution, assumptions | ✅ | Headline metrics + "cost assumptions" |
| By language and customer segment, disparities investigated | ✅ | By-language / country / segment tables; ADR-013 fixed a country disparity in the policy |
| Offline / simulated / projected labelled separately | ✅ | Report banners; problem_analysis §4 |

## Submission (kickoff)

| Item | Status |
|---|---|
| Public GitHub repository `factored-hackathon-2026-<team>` | ✅ public |
| Link to the deployed tool | ✅ web https://latam-bank-disputes.vercel.app · API https://latam-bank-dispute-ops-api.onrender.com |
| 4–6 slides | ⬜ |
| Video pitch (≤ 3 min) | ⬜ |
| Email to hackathon.admin@factored.ai | ⬜ |
