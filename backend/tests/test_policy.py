import pytest

from dispute_ops.domain import ReasonCode
from dispute_ops.policy.engine import PolicyContext, PolicyEngine
from helpers import NOW


@pytest.fixture
def policy():
    return PolicyEngine.load_default()


def ctx(store, txn_id, reason=ReasonCode.FRAUD_CNP, **kw):
    txn = store.get_transaction(txn_id)
    return PolicyContext(
        transaction=txn, customer=store.get_customer(txn.customer_id), reason_code=reason, now=NOW, **kw
    )


def test_version_is_exposed(policy):
    assert policy.version == "disputes_v2"


def test_v1_is_kept_for_reproducibility():
    assert PolicyEngine.load_default("disputes_v1").version == "disputes_v1"


@pytest.mark.parametrize("country", ["Mexico", "Colombia", "Argentina"])
def test_v2_threshold_is_the_same_in_every_country(policy, store, country):
    txn = store.get_transaction("TXN001").model_copy(update={"amount_usd": 451})
    cust = store.get_customer("CUST001").model_copy(update={"country": country})
    d = policy.evaluate(PolicyContext(transaction=txn, customer=cust, reason_code=ReasonCode.FRAUD_CNP, now=NOW))
    assert d.handoff_reasons == ["amount_above_threshold"] and d.inputs["amount_usd_threshold"] == 450


def test_eligible_reports_missing_evidence(policy, store):
    d = policy.evaluate(ctx(store, "TXN001"))
    assert d.decision == "eligible"
    assert d.missing_evidence == ["card_in_possession", "recognizes_merchant"]
    assert d.inputs["transaction_id"] == "TXN001"


def test_eligible_with_full_evidence(policy, store):
    ev = {"card_in_possession": "yes", "recognizes_merchant": "no"}
    assert policy.evaluate(ctx(store, "TXN001", evidence=ev)).missing_evidence == []


@pytest.mark.parametrize(
    ("txn_id", "kw", "rule"),
    [
        ("TXN004", {}, "R-WINDOW"),
        ("TXN006", {}, "R-TXN-STATUS"),
        ("TXN001", {"open_dispute_case_id": "DSP-9"}, "R-DUP-OPEN"),
    ],
)
def test_ineligible_rules(policy, store, txn_id, kw, rule):
    d = policy.evaluate(ctx(store, txn_id, **kw))
    assert (d.decision, d.rule_ids) == ("ineligible", [rule])


@pytest.mark.parametrize(
    ("txn_id", "kw", "reason"),
    [
        ("TXN005", {}, "amount_above_threshold"),
        ("TXN101", {}, "repeat_complainer"),
        ("TXN001", {"disputes_last_30d": 3}, "dispute_velocity"),
        ("TXN001", {"ip_country_mismatch": True}, "account_takeover_signal"),
        ("TXN001", {"very_negative_sentiment": True}, "very_negative_sentiment"),
        ("TXN001", {"classifier_confidence": 0.4}, "low_classifier_confidence"),
    ],
)
def test_handoff_triggers(policy, store, txn_id, kw, reason):
    d = policy.evaluate(ctx(store, txn_id, **kw))
    assert d.decision == "handoff"
    assert reason in d.handoff_reasons


def test_human_request_wins_over_ineligibility(policy, store):
    d = policy.evaluate(ctx(store, "TXN004", human_requested=True))
    assert (d.decision, d.rule_ids) == ("handoff", ["R-HUMAN-REQUEST"])


@pytest.mark.parametrize(
    ("reason", "status", "confirmed", "expected"),
    [
        (ReasonCode.FRAUD_CNP, "Active", True, "R-BLOCK-OK"),
        (ReasonCode.DUPLICATE, "Active", True, "R-BLOCK-NOT-FRAUD"),
        (ReasonCode.FRAUD_CP, "Blocked", True, "R-BLOCK-NOT-ACTIVE"),
        (ReasonCode.FRAUD_CNP, "Active", False, "R-BLOCK-NO-CONFIRM"),
    ],
)
def test_can_block_card(policy, store, reason, status, confirmed, expected):
    card = store.get_card("PRD001").model_copy(update={"product_status": status})
    assert policy.can_block_card(reason, card, confirmed).rule_ids == [expected]


# ---- v0.0.2: a human reviewer may override handoff triggers, never ineligibility -----------------------

def test_human_review_clears_handoff_triggers_but_keeps_ineligibility(policy, store):
    high = policy.evaluate_human_review(ctx(store, "TXN005"))  # 822 USD > 450: automation hands off
    assert high.decision == "eligible" and high.rule_ids == ["R-HUMAN-REVIEW"]
    assert high.inputs["overridden_rules"] == ["R-HO-AMOUNT"]
    old = policy.evaluate_human_review(ctx(store, "TXN004"))  # outside the window
    assert old.decision == "ineligible" and old.rule_ids == ["R-WINDOW"]
