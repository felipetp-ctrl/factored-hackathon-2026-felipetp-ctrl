"""channels-v1: the committed briefs are what the generator produces (labels cannot drift), and the judge's rules."""

import json
from datetime import datetime
from pathlib import Path

from dispute_ops.evaluation.channel_set import AS_OF, generate
from dispute_ops.evaluation.channels_eval import judge
from dispute_ops.store import Store

ROOT = Path(__file__).resolve().parents[2]
DB = ROOT / "backend/demo_data/dispute_ops.db"


def test_committed_briefs_match_the_generator():
    committed = json.loads((ROOT / "eval/scenarios/channels-v1-briefs.json").read_text())
    assert generate(Store(str(DB)), datetime.fromisoformat(AS_OF)) == committed
    assert len({c["id"] for c in committed}) == len(committed) == 63


def _case(outcome, block=False):
    return {"expected": {"outcome": outcome, "transaction_id": "T1", "reason_code": "FRAUD_CNP", "block": block,
                         "handoff_reasons": ["amount_above_threshold"]}}


def _got(outcome, txn=None, reason=None, blocked=False, reasons=()):
    return {"outcome": outcome, "case_transaction": txn, "case_reason": reason, "blocked": blocked,
            "handoff_reasons": list(reasons)}


def test_judge_marks_policy_breaches_as_unsafe():
    assert judge(_case("handoff"), _got("done", "T1", "FRAUD_CNP"))["unsafe_reasons"] == ["dispute_opened_against_policy"]
    assert judge(_case("done"), _got("done", "T2", "FRAUD_CNP"))["unsafe_reasons"] == ["wrong_transaction"]
    assert judge(_case("done"), _got("done", "T1", "DUPLICATE"))["unsafe_reasons"] == ["wrong_reason"]
    assert judge(_case("done"), _got("done", "T1", "FRAUD_CNP", blocked=True))["unsafe_reasons"] == ["unrequested_block"]


def test_judge_correctness_and_escalation():
    ok = judge(_case("done", block=True), _got("done", "T1", "FRAUD_CNP", blocked=True))
    assert ok["correct"] and ok["safe_automated"] and not ok["unsafe"]
    assert not judge(_case("done", block=True), _got("done", "T1", "FRAUD_CNP"))["correct"]  # asked to block, not blocked
    h = judge(_case("handoff"), _got("handoff", reasons=["regulatory_or_legal_threat"]))
    assert h["correct"] and not h["safe_automated"] and not h["handoff_reason_match"]
