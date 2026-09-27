"""Training corpus and held-out sets for the intent classifier.

- The corpus (`ml/corpus/intent-v1.tsv`) is team-generated: written by the coding assistant, labelled by
  construction. It is the only data used for fitting, model selection and the confidence threshold.
- Held-out sets are the customer messages of the frozen evaluation runs (test-v2 primary, test-v1 secondary),
  labelled by the scenario ground truth (derived from the policy), never by the system under test.
- Leakage guard: corpus lines that are near-duplicates of any evaluation message are dropped and counted."""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from dispute_ops.evaluation.gold_scenarios import load as load_scenarios
from dispute_ops.language.keywords import _norm

REPO = Path(__file__).resolve().parents[4]
CORPUS = REPO / "ml" / "corpus" / "intent-v1.tsv"
EVAL_RESULTS = REPO / "eval" / "results"
TEST_V2 = EVAL_RESULTS / "20260926T181317Z-test-v2" / "results.jsonl"
# Run 3 of test-v2 (proposed system), cut short by exhausted API credit: messages never opened during the
# intent-v1 error analysis, so they are the unseen check for intent-v2.
TEST_V2_RUN3 = EVAL_RESULTS / "20260926T181317Z-test-v2" / "results_aborted_credit.jsonl"
TEST_V1 = EVAL_RESULTS / "20260926T175451Z-test-v1" / "results.jsonl"
TEST_V1_SCENARIOS = REPO / "eval" / "scenarios" / "test-v1.json"
NEAR_DUPLICATE = 0.6  # char 3-gram Jaccard


@dataclass(frozen=True)
class Example:
    text: str
    label: str
    language: str
    source: str = "corpus"


def load_corpus(path: Path = CORPUS) -> list[Example]:
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        label, language, text = line.split("\t", 2)
        out.append(Example(text=text.strip(), label=label, language=language))
    return out


def _grams(text: str) -> set[str]:
    t = " ".join(_norm(text).split())
    return {t[i:i + 3] for i in range(max(len(t) - 2, 1))}


def jaccard(a: str, b: str) -> float:
    ga, gb = _grams(a), _grams(b)
    return len(ga & gb) / len(ga | gb) if ga | gb else 0.0


def eval_messages(root: Path = EVAL_RESULTS) -> list[str]:
    """Every customer message in every stored evaluation run (all sets, all systems)."""
    msgs = set()
    for f in root.glob("*/results*.jsonl"):
        for line in f.read_text().splitlines():
            for role, text in json.loads(line)["transcript"]:
                if role == "customer":
                    msgs.add(text)
    return sorted(msgs)


def drop_near_duplicates(corpus: list[Example], messages: list[str], threshold: float = NEAR_DUPLICATE
                         ) -> tuple[list[Example], list[tuple[Example, str, float]]]:
    grams = [(m, _grams(m)) for m in messages]
    kept, dropped = [], []
    for ex in corpus:
        g = _grams(ex.text)
        best = max(((m, len(g & gm) / len(g | gm)) for m, gm in grams), key=lambda x: x[1], default=("", 0.0))
        (dropped.append((ex, *best)) if best[1] >= threshold else kept.append(ex))
    return kept, dropped


def _rows(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines()]


def _customer(r: dict) -> list[str]:
    return [t for role, t in r["transcript"] if role == "customer"]


def heldout_reason_v2(path: Path = TEST_V2) -> list[Example]:
    """Same items as the component report: the customer's messages up to the turn where the production NLU
    committed to a reason (or the whole conversation if it never did), labelled with the expected reason."""
    out = []
    for r in _rows(path):
        if r["system"] != "proposed" or not r.get("expected_reason_code") or r["category"] == "adversarial":
            continue
        msgs = _customer(r)
        if not msgs or (r.get("error") and path == TEST_V2):
            continue
        k = next((i for i, t in enumerate(r.get("nlu_turns") or []) if t.get("reason_code")), len(msgs) - 1)
        out.append(Example(" ".join(msgs[: k + 1]), r["expected_reason_code"], r["language"], f"test-v2:{r['scenario_id']}"))
    return out


def heldout_scope_v2(path: Path = TEST_V2) -> list[Example]:
    """First customer message of every proposed conversation: OUT_OF_SCOPE vs IN_SCOPE."""
    out = []
    for r in _rows(path):
        if r["system"] != "proposed" or r.get("error") or not r.get("nlu_turns"):
            continue
        label = "OUT_OF_SCOPE" if r["category"] == "out_of_scope" else "IN_SCOPE"
        out.append(Example(_customer(r)[0], label, r["language"], f"test-v2:{r['scenario_id']}"))
    return out


def heldout_reason_v1(path: Path = TEST_V1, scenarios: Path = TEST_V1_SCENARIOS) -> list[Example]:
    """test-v1 has no per-turn NLU record: the opening message, labelled with the scenario's expected reason."""
    expected = {s.id: s for s in load_scenarios(scenarios)}
    out = []
    for r in _rows(path):
        s = expected.get(r["scenario_id"])
        if r["system"] != "proposed" or r.get("error") or not s or not s.expected.reason_code or s.category == "adversarial":
            continue
        out.append(Example(_customer(r)[0], s.expected.reason_code.value, r["language"], f"test-v1:{r['scenario_id']}"))
    return out


def describe(examples: list[Example]) -> dict[str, int]:
    return dict(sorted(Counter(e.label for e in examples).items()))
