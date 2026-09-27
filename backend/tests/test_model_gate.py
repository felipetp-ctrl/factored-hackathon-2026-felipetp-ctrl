"""Regression gate for the bundled intent classifier: CI fails if a retrained model drops below what the deployed
one achieved on the frozen held-out messages. Floors are the recorded results minus a small tolerance."""

import json

import pytest

from dispute_ops.language.intent_model import IntentModel
from dispute_ops.ml import corpus as C

TEST_V3 = C.REPO / "eval" / "results" / "test-v3-subagent" / "results.jsonl"


@pytest.fixture(scope="module")
def model():
    return IntentModel.load()


def _test_v3_reason_messages() -> list[tuple[str, str]]:
    """Reason messages of test-v3 as the rules-only variant saw them (independent of the classifier's reading)."""
    out = []
    for line in TEST_V3.read_text().splitlines():
        r = json.loads(line)
        if r["system"] != "rules_only" or not r.get("expected_reason_code") or r["category"] == "adversarial":
            continue
        msgs = [t for role, t in r["transcript"] if role == "customer"]
        k = next((i for i, t in enumerate(r["nlu_turns"]) if t.get("reason_code")), len(msgs) - 1)
        out.append((" ".join(msgs[: k + 1]), r["expected_reason_code"]))
    return out


def test_gate_test_v3_reasons(model):  # recorded 23/23
    items = _test_v3_reason_messages()
    assert len(items) == 23
    assert sum(model.predict(t).label == y for t, y in items) >= 22


def test_gate_test_v2_run3_reasons(model):  # recorded 23/23 (never opened before intent-v2)
    items = C.heldout_reason_v2(C.TEST_V2_RUN3)
    assert len(items) == 23
    assert sum(model.predict(e.text).label == e.label for e in items) >= 22


def test_gate_independent_set(model):  # recorded: intent-v2 alone 502/525, fallback with intent-v2 494/525
    from dispute_ops.language.rule_nlu import RuleNlu
    from dispute_ops.ml.independent import load_independent, nlu_label
    from dispute_ops.ml.corpus import drop_near_duplicates, load_corpus
    gold, _ = drop_near_duplicates(load_independent(), [e.text for e in load_corpus()])
    assert len(gold) == 525
    assert sum(model.predict(e.text).label == e.label for e in gold) >= 495
    fallback = RuleNlu([], intent_model=model)
    assert sum(nlu_label(fallback, e.text) == e.label for e in gold) >= 485
