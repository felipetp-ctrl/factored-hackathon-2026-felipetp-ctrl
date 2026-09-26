import pytest

from dispute_ops.channels import PqrComplaint, handle_proactive_reply, run_pqr_complaint, select_fraud_alerts
from dispute_ops.domain import Channel, ReasonCode
from dispute_ops.flow import DisputeFlow, State, Turn
from dispute_ops.policy.engine import PolicyEngine


@pytest.fixture
def policy():
    return PolicyEngine.load_default()


@pytest.fixture
def deps(tools, store, policy, sessions, clock):
    return dict(tools=tools, store=store, policy=policy, sessions=sessions, clock=clock, sleep=lambda s: None)


def test_pqr_complete_complaint_opens_dispute_without_blocking(deps, store):
    c = PqrComplaint(
        complaint_id="Q1", customer_id="CUST001", transaction_id="TXN003",
        description="Me cobraron dos veces Netflix", evidence={"duplicate_transaction_id": "TXN002"},
    )
    r = run_pqr_complaint(c, reason_code=ReasonCode.DUPLICATE, classifier_confidence=0.93, **deps)
    assert r.state == State.DONE
    assert store.get_dispute(r.case.case_id).reason_code == ReasonCode.DUPLICATE
    assert store.get_card("PRD001").product_status == "Active"


def test_pqr_missing_info_goes_to_human_not_to_clarification(deps):
    c = PqrComplaint(complaint_id="Q2", customer_id="CUST001", description="Cobro raro", transaction_id="TXN001")
    r = run_pqr_complaint(c, reason_code=ReasonCode.FRAUD_CNP, classifier_confidence=0.9, **deps)
    assert r.action == "handoff"
    assert r.handoff.reason_for_handoff == ["async_missing_info"]
    assert r.handoff.channel == Channel.PQR
    assert r.handoff.open_questions == ["card_in_possession", "recognizes_merchant"]


def test_pqr_low_confidence_classification_goes_to_human(deps):
    c = PqrComplaint(
        complaint_id="Q3", customer_id="CUST001", transaction_id="TXN003", description="...",
        evidence={"duplicate_transaction_id": "TXN002"},
    )
    r = run_pqr_complaint(c, reason_code=ReasonCode.DUPLICATE, classifier_confidence=0.3, **deps)
    assert r.handoff.reason_for_handoff == ["low_classifier_confidence"]


def test_fraud_alert_selection(store, clock):
    assert [t.transaction_id for t in select_fraud_alerts(store, clock)] == ["TXN005", "TXN007"]


def proactive_flow(tools, store, policy, clock):
    return DisputeFlow(
        tools=tools, store=store, policy=policy, clock=clock, trace_id="pro-1",
        channel=Channel.PROACTIVE, sleep=lambda s: None,
    )


def test_proactive_not_me_leads_to_dispute_and_block(tools, store, policy, clock, sessions):
    flow = proactive_flow(tools, store, policy, clock)
    token = sessions.issue("CUST001")
    r = handle_proactive_reply(flow, token=token, transaction_id="TXN007", recognized=False)
    assert r.ask_for == ["card_in_possession"]
    r = flow.handle(Turn(token=token, evidence={"card_in_possession": "yes"}))
    assert (r.action, r.offer_block_card) == ("confirm", True)
    r = flow.handle(Turn(token=token, confirm=True, block_card=True))
    assert r.state == State.DONE and r.card.product_status == "Blocked"


def test_proactive_recognized_closes_without_action(tools, store, policy, clock, sessions):
    flow = proactive_flow(tools, store, policy, clock)
    r = handle_proactive_reply(flow, token=sessions.issue("CUST001"), transaction_id="TXN007", recognized=True)
    assert r.action == "cancelled"
    assert store.find_open_dispute("TXN007") is None


def test_pqr_without_transaction_id_matches_by_product_and_amount(deps, store):
    from decimal import Decimal

    from dispute_ops.channels import match_complaint
    from helpers import NOW

    c = PqrComplaint(complaint_id="Q9", customer_id="CUST001", description="cargo raro", affected_product_id="PRD001",
                     claimed_amount=Decimal("1250.00"), created_at=NOW)
    matched, cands = match_complaint(store, c, NOW)
    assert matched == "TXN001" and [t.transaction_id for t in cands] == ["TXN001"]


def test_pqr_ambiguous_match_goes_to_agent_with_shortlist(deps):
    from decimal import Decimal

    c = PqrComplaint(complaint_id="Q10", customer_id="CUST001", description="cobro Netflix",
                     affected_product_id="PRD001", claimed_amount=Decimal("399.00"))
    r = run_pqr_complaint(c, reason_code=ReasonCode.DUPLICATE, classifier_confidence=0.9, **deps)
    assert r.action == "handoff" and r.handoff.reason_for_handoff == ["async_missing_info"]
    assert set(r.handoff.risk_signals["candidate_transactions"]) == {"TXN002", "TXN003"}


def test_pqr_ignores_a_product_that_belongs_to_another_customer(store):
    from decimal import Decimal

    from dispute_ops.channels import match_complaint
    from helpers import NOW

    c = PqrComplaint(complaint_id="Q11", customer_id="CUST001", description="x", affected_product_id="PRD002",
                     claimed_amount=Decimal("1250.00"), created_at=NOW)
    assert match_complaint(store, c, NOW)[0] == "TXN001"
