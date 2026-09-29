"""95% Wilson intervals for every headline number, so small samples read as what they are.

Counts are read from the committed result files where the format allows; each row names its source.

    python -m dispute_ops.evaluation.uncertainty   (writes docs/analysis/uncertainty.md)
"""

from __future__ import annotations

import json
from math import sqrt
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return max(0.0, c - h), min(1.0, c + h)


def _jsonl(path: str) -> list[dict]:
    return [json.loads(line) for line in (ROOT / path).read_text().splitlines() if line.strip()]


def rows() -> list[tuple[str, str, int, int, str]]:
    """(what, system, k, n, source)."""
    out = []
    v2 = "eval/results/20260926T181317Z-test-v2/results.jsonl"
    r = _jsonl(v2)
    for system, name in (("proposed", "this system"), ("naive_llm", "plain AI chatbot")):
        s = [x for x in r if x["system"] == system]
        ins = [x for x in s if x["in_scope"]]
        out.append(("test-v2 unsafe outcomes", name, sum(x["unsafe"] for x in s), len(s), v2))
        safe = [x for x in ins if x["correct"] and not x["unsafe"] and not x["handoff"]
                and x["expected_outcome"] in ("done", "ineligible", "cancelled")]
        out.append(("test-v2 safe automated resolution (in scope)", name, len(safe), len(ins), v2))
    hv = "eval/results/hard-v1-after-test/results.jsonl"
    for system, name in (("rules_intent_v2", "free reader"), ("claude_sim", "Claude path (subagent reader)")):
        s = [x for x in _jsonl(hv) if x["system"] == system]
        out.append(("hard-v1 correct outcome", name, sum(x["correct"] for x in s), len(s), hv))
    ch = "eval/results/channels-v1-test/results.jsonl"
    for kind, what in (("letter", "channels-v1 letters correct"), ("alert", "channels-v1 alert answers correct")):
        s = [x for x in _jsonl(ch) if x["kind"] == kind and x["system"] == "rules_intent_v2"]
        out.append((what, "free reader", sum(x["correct"] for x in s), len(s), ch))
        out.append((what.replace("correct", "unsafe"), "free reader", sum(x["unsafe"] for x in s), len(s), ch))
    ind = json.loads((ROOT / "ml/results/independent-v1.json").read_text())
    k, n = _independent(ind)
    out.append(("independent-v1 reason read correctly", "rules + intent-v2", k, n, "ml/results/independent-v1.json"))
    out.append(("human review: blind human agrees with the label", "—", 78, 85, "ml/results/human-review.md"))
    return out


def _independent(d: dict) -> tuple[int, int]:
    """The deployed fallback reader (rules + intent-v2) on the independent set's gold messages."""
    systems = d["systems"]
    name = next(k for k in systems if "intent" in k and "rule" in k)
    return systems[name]["hits"], systems[name]["n"]


def main() -> None:
    lines = ["# Uncertainty: 95% intervals for the headline numbers", "",
             "Wilson score intervals. Small held-out sets give wide intervals; zero observed failures bound the rate, "
             "they do not prove it is zero. Offline simulations throughout. Script: `dispute_ops.evaluation.uncertainty`.", "",
             "| Measure | System | Observed | Rate | 95% interval | Source |", "|---|---|---|---|---|---|"]
    for what, system, k, n, src in rows():
        lo, hi = wilson(k, n)
        lines.append(f"| {what} | {system} | {k}/{n} | {k / n:.1%} | {lo:.1%} – {hi:.1%} | `{src}` |")
    lines += ["", "Reading them: the system's unsafe rate on test-v2 (0/84) is below 4.4% with 95% confidence, while the "
              "chatbot's is at least 9%; the two intervals do not overlap. hard-v1 and channels-v1 intervals are wide "
              "(n = 18–36), so differences of a few cases between variants are not evidence on their own.", ""]
    path = ROOT / "docs/analysis/uncertainty.md"
    path.write_text("\n".join(lines))
    print("\n".join(lines))


if __name__ == "__main__":
    main()
