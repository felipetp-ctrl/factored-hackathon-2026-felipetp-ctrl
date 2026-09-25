import json

from dispute_ops.domain import Channel, ReasonCode
from dispute_ops.handoff import ActionRecord, HandoffPackage, build_handoff
from helpers import NOW


def test_package_carries_verified_facts_with_sources(store):
    pkg = build_handoff(
        trace_id="t1", channel=Channel.CHAT, language="pt", reasons=["amount_above_threshold"],
        summary="Cliente não reconhece compra", transaction=store.get_transaction("TXN005"),
        reason_code=ReasonCode.FRAUD_CNP,
        actions=[ActionRecord(action="block_card", status="verified", at=NOW, ref="PRD001")],
        policy=None, open_questions=[],
    )
    assert pkg.verified_facts[0].source == "txn:TXN005"
    assert pkg.risk_signals["fraud_score"] == "91.00"
    assert pkg.open_questions == []
    json.loads(pkg.model_dump_json())  # serialisable for the agent console


def test_missing_transaction_and_reason_become_open_questions():
    pkg = build_handoff(
        trace_id="t2", channel=Channel.PQR, language="es", reasons=["async_missing_info"],
        summary="", transaction=None, reason_code=None, actions=[], policy=None, open_questions=[],
    )
    assert pkg.open_questions == ["transaction", "reason_code"]
    assert pkg.verified_facts == []


def test_package_has_no_raw_transcript_field():
    assert not any("transcript" in f for f in HandoffPackage.model_fields)
