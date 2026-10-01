# Evaluation sets and results

Method: [ADR-009](../docs/decisions/ADR-009-evaluation-method.md). Results and caveats: [docs/evaluation.md](../docs/evaluation.md).
Code: `backend/src/dispute_ops/evaluation/`. Commands: `make eval`, `make eval-channels` (see `make help`).

Every set is frozen before it is run; failed, invalid and discarded runs are kept on purpose so the history can be
audited. Runs that the documentation cites as headline results are marked **headline**.

## `scenarios/` — the sets

| File | What it is |
|---|---|
| `test-v1.json` | 35 held-out conversations from real transactions (customers know the charge) |
| `test-v2.json` | 42 held-out conversations: every dispute reason, every handoff trigger, attacks |
| `test-v3.json` | 42 conversations frozen before intent-v2, for the free fallback reader |
| `hard-v1-dev.json` · `hard-v1-test.json` | Vague-memory set ([ADR-022](../docs/decisions/ADR-022-hard-set-and-fuzzy-references.md)): dev split for fixes, blind test split |
| `hard-v1-briefs.json` · `hard-v1-personas.json` | Inputs used to build hard-v1 (scenario briefs, personas by an independent author) |
| `channels-v1.json` | Written complaints and fraud-alert answers, dev/test splits ([ADR-025](../docs/decisions/ADR-025-channels-evaluation.md)) |
| `channels-v1-briefs.json` · `channels-v1-texts.json` | Inputs used to build channels-v1 (briefs, customer text by an independent author) |

## `results/` — every run

Conversation runs write `report.md` (read this), `summary.json` and `results.jsonl` (full transcripts). Subagent runs
add `config.json`, `messages.json` and `nlu_cache.json` so they can be replayed without model calls.

| Run | Set | What it is |
|---|---|---|
| `20260926T141524Z-dev-v1-before-fixes` | dev (fixture) | First development run; found 3 bugs fixed before test-v1 was frozen |
| `20260926T175133Z-test-v1-INVALID-oracle-bug` | test-v1 | **Invalid**: the oracle had a bug; kept for the record, superseded by the next run |
| `20260926T175451Z-test-v1` | test-v1 | **Headline** — 3 runs per system |
| `20260926T181317Z-test-v2` | test-v2 | **Headline** — 2 runs per system; offline component re-scoring and cascade analysis |
| `test-v3-subagent` | test-v3 | Fallback reader end to end (customers played by a Sonnet subagent) |
| `hard-v1-dev-after1` | hard-v1 dev | Dev split after the first round of fixes |
| `hard-v1-before-test` · `hard-v1-after-test` | hard-v1 test | **Headline** — blind test before and after the fixes |
| `hard-v1-after-test-posthoc` | hard-v1 test | After a post-hoc fix found on the test split (negated card block) |
| `hard-v1-nlu-v4-check` | hard-v1 | Targeted check of the nlu-v4 prompt; **not** a held-out measurement (see its README) |
| `hard-v1-discarded` | hard-v1 | Scripted customer answers discarded after audit (ADR-022) |
| `hard-v1-replay-0929` | hard-v1 test | Regression replay after the channels-v1 fixes: identical outcomes |
| `hard-v1-replay-1001` | hard-v1 test | Regression replay after ADR-027 |
| `hard-v1-replay-intent-v3` | hard-v1 test | Regression replay with intent-v3 in the free reader (ADR-030): same 32/36, unnecessary escalations 5 → 3 |
| `hard-v1-replay-grounding` | hard-v1 test | Partial replay after ADR-031: 66/72 identical, 6 Claude-path conversations now ask where the card is (see its README) |
| `hard-v1-api/` | hard-v1 test | **Headline** — real API (Claude Haiku 4.5 reader, Sonnet 5 customers), 2 runs per system, one folder per launch |
| `hard-v1-api-posthoc/` | hard-v1 test | Post-hoc re-run of the two human-request scenarios after ADR-027 |
| `channels-v1-dev-before` · `channels-v1-dev-after` | channels-v1 dev | Before and after the fixes made on the dev split |
| `channels-v1-test-before` · `channels-v1-test` | channels-v1 test | **Headline** — `channels-v1-test` is the current code (`make eval-channels`) |
