from datetime import timedelta
from decimal import Decimal

import pytest

from dispute_ops.domain import ReasonCode
from dispute_ops.flow import DisputeFlow, State, Turn
from dispute_ops.policy.engine import PolicyEngine

EVIDENCE = {"card_in_possession": "yes", "recognizes_merchant": "no"}


@pytest.fixture
def flow(tools, store, clock):
    return DisputeFlow(
        tools=tools, store=store, policy=PolicyEngine.load_default(), clock=clock,
        trace_id="t-flow", sleep=lambda s: None,
    )


@pytest.fixture
def token(sessions):
    return sessions.issue("CUST001")


def kinds(store, trace_id="t-flow"):
    return [e.kind for e in store.list_audit(trace_id)]


def test_normal_path_opens_dispute_and_blocks_card_after_confirmation(flow, token, store):
    r = flow.handle(Turn(token=token, transaction_id="TXN001", reason_code=ReasonCode.FRAUD_CNP))
    assert (r.action, r.ask_for) == ("ask", ["card_in_possession", "recognizes_merchant"])
    r = flow.handle(Turn(token=token, evidence=EVIDENCE))
    assert (r.action, r.offer_block_card) == ("confirm", True)
    assert store.find_open_dispute("TXN001") is None  # nothing written before confirmation
    r = flow.handle(Turn(token=token, confirm=True, block_card=True))
    assert r.state == State.DONE
    assert store.get_dispute(r.case.case_id).status == "Open"
    assert r.card.product_status == "Blocked"
    assert [a.status for a in flow.actions] == ["verified", "verified"]
    assert kinds(store)[-1] == "done"


def test_no_block_without_explicit_request(flow, token, store):
    flow.handle(Turn(token=token, transaction_id="TXN001", reason_code=ReasonCode.FRAUD_CNP, evidence=EVIDENCE))
    r = flow.handle(Turn(token=token, confirm=True))
    assert r.state == State.DONE and r.card is None
    assert store.get_card("PRD001").product_status == "Active"


def test_customer_declines_confirmation(flow, token, store):
    flow.handle(Turn(token=token, transaction_id="TXN001", reason_code=ReasonCode.FRAUD_CNP, evidence=EVIDENCE))
    r = flow.handle(Turn(token=token, confirm=False))
    assert r.action == "cancelled"
    assert store.find_open_dispute("TXN001") is None


def test_ambiguous_merchant_asks_with_candidates(flow, token):
    r = flow.handle(Turn(token=token, merchant="Netflix", reason_code=ReasonCode.DUPLICATE))
    assert r.action == "ask" and r.ask_for == ["transaction"]
    assert {c.transaction_id for c in r.candidates} == {"TXN002", "TXN003"}


def test_clarification_is_bounded_then_hands_off(flow, token):
    assert flow.handle(Turn(token=token)).action == "ask"
    assert flow.handle(Turn(token=token)).action == "ask"
    r = flow.handle(Turn(token=token))
    assert r.action == "handoff"
    assert r.handoff.reason_for_handoff == ["clarification_exhausted"]


def test_missing_reason_code_is_asked(flow, token):
    r = flow.handle(Turn(token=token, transaction_id="TXN001"))
    assert (r.state, r.ask_for) == (State.CLASSIFY, ["reason_code"])


def test_ineligible_outside_window_explains_rule(flow, token):
    r = flow.handle(Turn(token=token, transaction_id="TXN004", reason_code=ReasonCode.FRAUD_CNP))
    assert r.action == "ineligible" and r.policy.rule_ids == ["R-WINDOW"]


def test_high_amount_hands_off_with_verified_facts(flow, token):
    r = flow.handle(Turn(token=token, transaction_id="TXN005", reason_code=ReasonCode.FRAUD_CNP, summary="No reconozco"))
    assert r.action == "handoff"
    assert r.handoff.reason_for_handoff == ["amount_above_threshold"]
    assert r.handoff.verified_facts[0].source == "txn:TXN005"
    assert r.handoff.customer_request_summary == "No reconozco"


def test_explicit_human_request_hands_off_immediately(flow, token):
    r = flow.handle(Turn(token=token, human_requested=True))
    assert r.handoff.reason_for_handoff == ["customer_requested_human"]


def test_other_customers_transaction_is_not_leaked(flow, sessions, store):
    r = flow.handle(Turn(token=sessions.issue("CUST002"), transaction_id="TXN001", reason_code=ReasonCode.FRAUD_CNP))
    assert r.action == "ask" and r.ask_for == ["transaction"]
    assert r.candidates == []
    assert "transaction_lookup_rejected" in kinds(store)


def test_expired_session_requires_reauth_and_keeps_progress(flow, token, sessions, clock):
    flow.handle(Turn(token=token, transaction_id="TXN001", reason_code=ReasonCode.FRAUD_CNP))
    clock.now += timedelta(minutes=20)
    assert flow.handle(Turn(token=token, evidence=EVIDENCE)).action == "reauth"
    r = flow.handle(Turn(token=sessions.issue("CUST001"), evidence=EVIDENCE))
    assert r.action == "confirm"


def test_session_swap_mid_conversation_is_rejected(flow, token, sessions, store):
    flow.handle(Turn(token=token, transaction_id="TXN001", reason_code=ReasonCode.FRAUD_CNP))
    r = flow.handle(Turn(token=sessions.issue("CUST002"), evidence=EVIDENCE))
    assert r.action == "reauth"
    assert store.list_audit("t-flow")[-1].data["reason"] == "session_mismatch"


def test_transient_tool_failure_is_retried(flow, token, failures):
    flow.handle(Turn(token=token, transaction_id="TXN001", reason_code=ReasonCode.FRAUD_CNP, evidence=EVIDENCE))
    failures.fail("open_dispute", times=1)
    assert flow.handle(Turn(token=token, confirm=True)).state == State.DONE


def test_persistent_tool_failure_hands_off_without_claiming_success(flow, token, failures, store):
    flow.handle(Turn(token=token, transaction_id="TXN001", reason_code=ReasonCode.FRAUD_CNP, evidence=EVIDENCE))
    failures.fail("open_dispute", times=3)
    r = flow.handle(Turn(token=token, confirm=True))
    assert r.handoff.reason_for_handoff == ["tool_failure"]
    assert r.handoff.actions_taken[0].status == "failed"
    assert store.find_open_dispute("TXN001") is None


def test_failed_verification_hands_off(flow, token, failures):
    flow.handle(Turn(token=token, transaction_id="TXN001", reason_code=ReasonCode.FRAUD_CNP, evidence=EVIDENCE))
    failures.fail("get_case_status", times=3)
    r = flow.handle(Turn(token=token, confirm=True))
    assert r.handoff.reason_for_handoff == ["verification_failed"]


def test_terminal_state_is_sticky(flow, token):
    r1 = flow.handle(Turn(token=token, human_requested=True))
    r2 = flow.handle(Turn(token=token, transaction_id="TXN001", reason_code=ReasonCode.FRAUD_CNP))
    assert r1 == r2


def test_amount_search_identifies_single_transaction(flow, token):
    r = flow.handle(Turn(token=token, amount=Decimal("1250.00"), reason_code=ReasonCode.FRAUD_CNP))
    assert r.ask_for == ["card_in_possession", "recognizes_merchant"]
    assert flow.txn.transaction_id == "TXN001"


def test_escalate_hands_off_with_given_reason_and_keeps_known_facts(flow, token):
    flow.handle(Turn(token=token, transaction_id="TXN001", reason_code=ReasonCode.FRAUD_CNP))
    r = flow.escalate(["nlu_unavailable"])
    assert r.handoff.reason_for_handoff == ["nlu_unavailable"]
    assert r.handoff.verified_facts[0].source == "txn:TXN001"
    assert flow.handle(Turn(token=token)).action == "handoff"
