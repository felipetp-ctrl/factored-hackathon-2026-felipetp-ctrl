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


def test_old_transaction_is_found_so_ineligibility_can_be_explained(flow, token):
    r = flow.handle(Turn(token=token, merchant="Liverpool", reason_code=ReasonCode.FRAUD_CNP))
    assert r.action == "ineligible" and r.policy.rule_ids == ["R-WINDOW"]


def test_regulatory_threat_hands_off(flow, token):
    r = flow.handle(Turn(token=token, transaction_id="TXN001", reason_code=ReasonCode.FRAUD_CNP, regulatory_threat=True))
    assert "regulatory_or_legal_threat" in r.handoff.reason_for_handoff


def test_repeated_references_to_another_customers_transaction_escalate_as_suspicious(flow, sessions, store):
    attacker = sessions.issue("CUST002")
    r1 = flow.handle(Turn(token=attacker, transaction_id="TXN001", reason_code=ReasonCode.FRAUD_CNP))
    assert r1.action == "ask"
    r2 = flow.handle(Turn(token=attacker, transaction_id="TXN001"))
    assert r2.action == "handoff" and r2.handoff.reason_for_handoff == ["suspicious_access"]
    assert r2.handoff.risk_signals["rejected_references"] == ["TXN001", "TXN001"]
    assert r2.handoff.verified_facts == []  # nothing about the victim's transaction is shared


def test_customer_sees_the_same_reply_for_foreign_and_nonexistent_ids(flow, sessions):
    token = sessions.issue("CUST002")
    foreign = flow.handle(Turn(token=token, transaction_id="TXN001", reason_code=ReasonCode.FRAUD_CNP))
    other = DisputeFlow(tools=flow.tools, store=flow.store, policy=flow.policy, clock=flow.clock, trace_id="t2",
                        sleep=lambda s: None)
    missing = other.handle(Turn(token=token, transaction_id="TXN999", reason_code=ReasonCode.FRAUD_CNP))
    assert (foreign.action, foreign.ask_for, foreign.state) == (missing.action, missing.ask_for, missing.state)


def test_repeated_nonexistent_ids_are_not_labelled_suspicious(flow, token):
    flow.handle(Turn(token=token, transaction_id="TXN998", reason_code=ReasonCode.FRAUD_CNP))
    r = flow.handle(Turn(token=token, transaction_id="TXN999"))
    assert r.handoff.reason_for_handoff == ["invalid_transaction_references"]


# ---- duplicate charge: the customer is shown the other charges to pick from -----------------------------------

def test_duplicate_shows_the_other_charges_at_the_same_merchant(flow, token):
    r = flow.handle(Turn(token=token, transaction_id="TXN003", reason_code=ReasonCode.DUPLICATE))
    assert (r.action, r.ask_for) == ("ask", ["duplicate_transaction_id"])
    assert [c.transaction_id for c in r.candidates] == ["TXN002"]  # the disputed charge itself is not offered
    r = flow.handle(Turn(token=token, evidence={"duplicate_transaction_id": "TXN002"}))
    assert r.action == "confirm"


def test_duplicate_with_no_other_charge_goes_back_to_the_reason(flow, token, store):
    # Demo, 04/10: "Qual é a outra cobrança idêntica?" was asked with nothing to pick, the customer could not answer
    # and the case went to a person. With no other charge at that merchant, the reason is asked again.
    r = flow.handle(Turn(token=token, transaction_id="TXN001", reason_code=ReasonCode.DUPLICATE))
    assert (r.state, r.ask_for, r.candidates_note) == (State.CLASSIFY, ["reason_code"], "no_duplicate")
    assert flow.reason_code is None and "duplicate_not_found" in kinds(store)
    r = flow.handle(Turn(token=token, reason_code=ReasonCode.FRAUD_CNP))
    assert r.ask_for == ["card_in_possession", "recognizes_merchant"]


def test_duplicate_not_picked_goes_back_to_the_reason(flow, token):
    flow.handle(Turn(token=token, transaction_id="TXN003", reason_code=ReasonCode.DUPLICATE))
    r = flow.handle(Turn(token=token))  # "não tem cobrança idêntica, foi 1 mês depois"
    assert (r.state, r.ask_for, r.candidates_note) == (State.CLASSIFY, ["reason_code"], "no_duplicate")


def test_duplicate_reference_not_offered_is_ignored(flow, token):
    flow.handle(Turn(token=token, transaction_id="TXN003", reason_code=ReasonCode.DUPLICATE))
    r = flow.handle(Turn(token=token, evidence={"duplicate_transaction_id": "TXN101"}))  # another customer's charge
    assert r.action != "confirm" and "duplicate_transaction_id" not in flow.evidence


# ---- every reason: the answers must make sense for the reason (policy review, 04/10) ------------------------

def test_unrecognised_charge_with_the_card_not_with_the_customer_becomes_lost_or_stolen(flow, token, store):
    # FRAUD_CNP means "card still with me" (reader prompt); a "no" to the card question is a lost or stolen card.
    flow.handle(Turn(token=token, transaction_id="TXN001", reason_code=ReasonCode.FRAUD_CNP))
    r = flow.handle(Turn(token=token, evidence={"card_in_possession": "no", "recognizes_merchant": "no"}))
    assert r.action == "confirm" and flow.reason_code == ReasonCode.FRAUD_CP
    assert "reason_corrected" in kinds(store)


def test_reason_corrected_while_evidence_is_asked_is_followed(flow, token, store):
    # "Na verdade eu não reconheço essa compra" while the correct amount is asked: the new reason is followed even if
    # the reading is less sure than the first one; before, the same question repeated until a hand-off.
    flow.handle(Turn(token=token, transaction_id="TXN001", reason_code=ReasonCode.INCORRECT_AMOUNT,
                     classifier_confidence=0.9))
    r = flow.handle(Turn(token=token, reason_code=ReasonCode.FRAUD_CNP, classifier_confidence=0.8))
    assert flow.reason_code == ReasonCode.FRAUD_CNP
    assert r.ask_for == ["card_in_possession", "recognizes_merchant"]


def test_a_short_answer_with_a_reason_reading_does_not_change_the_reason(flow, token):
    # The answer to the question asked is kept, and its incidental reason reading does not replace the first one.
    flow.handle(Turn(token=token, transaction_id="TXN001", reason_code=ReasonCode.INCORRECT_AMOUNT,
                     classifier_confidence=0.9))
    r = flow.handle(Turn(token=token, reason_code=ReasonCode.FRAUD_CNP, classifier_confidence=0.8,
                         evidence={"expected_amount": "1000.00"}))
    assert flow.reason_code == ReasonCode.INCORRECT_AMOUNT and r.action == "confirm"


@pytest.mark.parametrize("expected", ["1250.00", "3000.00", "0.00"])
def test_wrong_amount_needs_a_correct_amount_below_the_charge(flow, token, expected):
    flow.handle(Turn(token=token, transaction_id="TXN001", reason_code=ReasonCode.INCORRECT_AMOUNT))
    r = flow.handle(Turn(token=token, evidence={"expected_amount": expected}))
    assert (r.action, r.ask_for, r.candidates_note) == ("ask", ["expected_amount"], "invalid_expected_amount")
    assert "expected_amount" not in flow.evidence
    assert flow.handle(Turn(token=token, evidence={"expected_amount": "1000.00"})).action == "confirm"


def test_not_received_before_the_delivery_date_is_not_disputable_yet(flow, token):
    flow.handle(Turn(token=token, transaction_id="TXN001", reason_code=ReasonCode.NOT_RECEIVED))
    r = flow.handle(Turn(token=token, evidence={"expected_delivery_date": "2026-07-01", "contacted_merchant": "yes"}))
    assert r.action == "ineligible" and r.policy.rule_ids == ["R-NOT-DUE"]


def test_subscription_cancelled_after_the_charge_is_not_disputable(flow, token):
    flow.handle(Turn(token=token, transaction_id="TXN002", reason_code=ReasonCode.CANCELLED_RECURRING))
    r = flow.handle(Turn(token=token, evidence={"cancellation_date": "2026-06-16"}))  # charge on 2026-06-14
    assert r.action == "ineligible" and r.policy.rule_ids == ["R-CANCEL-AFTER"]


def test_subscription_cancelled_before_the_charge_is_disputable(flow, token):
    flow.handle(Turn(token=token, transaction_id="TXN002", reason_code=ReasonCode.CANCELLED_RECURRING))
    assert flow.handle(Turn(token=token, evidence={"cancellation_date": "2026-06-01"})).action == "confirm"
