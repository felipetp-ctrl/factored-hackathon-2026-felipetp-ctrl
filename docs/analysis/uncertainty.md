# Uncertainty: 95% intervals for the headline numbers

Wilson score intervals. Small held-out sets give wide intervals; zero observed failures bound the rate, they do not prove it is zero. Offline simulations throughout. Script: `dispute_ops.evaluation.uncertainty`.

| Measure | System | Observed | Rate | 95% interval | Source |
|---|---|---|---|---|---|
| test-v2 unsafe outcomes | this system | 0/84 | 0.0% | 0.0% – 4.4% | `eval/results/20260926T181317Z-test-v2/results.jsonl` |
| test-v2 safe automated resolution (in scope) | this system | 50/70 | 71.4% | 59.9% – 80.7% | `eval/results/20260926T181317Z-test-v2/results.jsonl` |
| test-v2 unsafe outcomes | plain AI chatbot | 13/84 | 15.5% | 9.3% – 24.7% | `eval/results/20260926T181317Z-test-v2/results.jsonl` |
| test-v2 safe automated resolution (in scope) | plain AI chatbot | 31/70 | 44.3% | 33.2% – 55.9% | `eval/results/20260926T181317Z-test-v2/results.jsonl` |
| hard-v1 correct outcome | free reader | 30/36 | 83.3% | 68.1% – 92.1% | `eval/results/hard-v1-after-test/results.jsonl` |
| hard-v1 correct outcome | Claude path (subagent reader) | 31/36 | 86.1% | 71.3% – 93.9% | `eval/results/hard-v1-after-test/results.jsonl` |
| hard-v1 API correct outcome | this system (Claude Haiku, API) | 65/72 | 90.3% | 81.3% – 95.2% | `eval/results/hard-v1-api/20260930T225007Z/results.jsonl` |
| hard-v1 API unsafe outcomes | this system (Claude Haiku, API) | 4/72 | 5.6% | 2.2% – 13.4% | `eval/results/hard-v1-api/20260930T225007Z/results.jsonl` |
| hard-v1 API correct outcome | plain AI chatbot (API) | 49/72 | 68.1% | 56.6% – 77.7% | `eval/results/hard-v1-api/20260930T225007Z/results.jsonl (run 0) + eval/results/hard-v1-api/20261001T012906Z/results.jsonl` |
| hard-v1 API unsafe outcomes | plain AI chatbot (API) | 11/72 | 15.3% | 8.8% – 25.3% | `eval/results/hard-v1-api/20260930T225007Z/results.jsonl (run 0) + eval/results/hard-v1-api/20261001T012906Z/results.jsonl` |
| channels-v1 letters correct | free reader | 23/24 | 95.8% | 79.8% – 99.3% | `eval/results/channels-v1-test/results.jsonl` |
| channels-v1 letters unsafe | free reader | 0/24 | 0.0% | 0.0% – 13.8% | `eval/results/channels-v1-test/results.jsonl` |
| channels-v1 alert answers correct | free reader | 17/18 | 94.4% | 74.2% – 99.0% | `eval/results/channels-v1-test/results.jsonl` |
| channels-v1 alert answers unsafe | free reader | 0/18 | 0.0% | 0.0% – 17.6% | `eval/results/channels-v1-test/results.jsonl` |
| independent-v1 reason read correctly | rules + intent-v2 | 494/525 | 94.1% | 91.7% – 95.8% | `ml/results/independent-v1.json` |
| human review: blind human agrees with the label | — | 78/85 | 91.8% | 84.0% – 96.0% | `ml/results/human-review.md` |

Reading them: the system's unsafe rate on test-v2 (0/84) is below 4.4% with 95% confidence, while the chatbot's is at least 9%; the two intervals do not overlap. hard-v1 and channels-v1 intervals are wide (n = 18–36), so differences of a few cases between variants are not evidence on their own.
