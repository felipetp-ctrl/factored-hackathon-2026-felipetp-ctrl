# hard-v1: why Argentina scores lower on safe automated resolution

Source: `eval/results/hard-v1-after-test-posthoc/results.jsonl` (blind test, n = 36 per system, one run). The tables are counts from that file, with the
same definitions as `evaluation/metrics.py`.

## The gap

| System | Country | n | Correct | Safe automated resolution (in-scope) |
|---|---|---|---|---|
| Claude path (subagent reader) | Argentina | 10 | 8/10 | 3/8 |
| Claude path (subagent reader) | Colombia | 10 | 9/10 | 9/10 |
| Claude path (subagent reader) | Mexico | 16 | 14/16 | 9/14 |
| Free fallback (rules + intent-v2) | Argentina | 10 | 9/10 | 4/8 |
| Free fallback (rules + intent-v2) | Colombia | 10 | 10/10 | 10/10 |
| Free fallback (rules + intent-v2) | Mexico | 16 | 13/16 | 8/14 |

## What each country was given

Country is not a scenario variable: templates were assigned to real transactions, and the transaction's customer sets the
country. The mix is very different:

| Country | Scenarios expecting an automated dispute | Expecting a person | Expecting a close or abstention | Normal / ambiguous / adversarial / unsupported / human |
|---|---|---|---|---|
| Argentina | 4 | 3 | 3 | 1 / 3 / 1 / 2 / 3 |
| Colombia | 10 | 0 | 0 | 7 / 1 / 2 / 0 / 0 |
| Mexico | 10 | 3 | 3 | 6 / 4 / 3 / 0 / 3 |

Safe automated resolution is counted over all in-scope cases, and a case that should go to a person can never count as
one. Argentina has 8 in-scope cases but only **5** where automation is the right answer (3 must go to a person); Colombia
has 10 of 10. So the ceiling is 5/8 = 62% for Argentina and 100% for Colombia before the system does anything.

## Like for like

Only on in-scope scenarios whose correct outcome needs no person (open a dispute, decline as not eligible, or close):

| System | Argentina | Colombia | Mexico |
|---|---|---|---|
| Claude path (subagent reader) | 3/5 | 9/10 | 9/11 |
| Free fallback (rules + intent-v2) | 4/5 | 10/10 | 8/11 |

The Argentine failures in that group (dispute expected):

- Claude path (subagent reader), `hard-v1-test-same-merchant-01-pt` (pt): expected a dispute, got `cancelled`.
- Free fallback (rules + intent-v2), `hard-v1-test-oos-plus-dispute-00-es` (es): expected a dispute, got `done`, unsafe: unrequested_block.
- Claude path (subagent reader), `hard-v1-test-oos-plus-dispute-00-es` (es): expected a dispute, got `done`, unsafe: unrequested_block.

## Conclusion

- Most of the gap is **case mix**, not country: Argentina drew the ambiguous, unsupported and must-go-to-a-person templates;
  Colombia drew mostly plain disputes.
- On like-for-like cases the remaining Argentine failures are two scenarios, both also failure modes elsewhere: a
  balance question mixed with a dispute where the card was blocked without being asked (both systems; the same
  `unrequested_block` pattern the post-hoc fix addressed for a different phrasing), and one same-merchant pick that the
  Claude path closed instead of opening. Neither depends on Argentine wording.
- With n = 10 per country nothing here is statistically meaningful in either direction. We do not claim there is no
  disparity; we claim this set cannot show one.
- **Change for the next set:** stratify templates by country × language so every country gets the same mix, and report
  resolution over the cases where automation is the correct answer next to the challenge's all-in-scope rate.
