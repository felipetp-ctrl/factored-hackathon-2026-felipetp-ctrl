import pytest

from dispute_ops.domain import ReasonCode
from dispute_ops.flow import DisputeFlow, Turn
from dispute_ops.language.responses import T, render
from dispute_ops.policy.engine import PolicyEngine

EVIDENCE = {"card_in_possession": "yes", "recognizes_merchant": "no"}


@pytest.fixture
def flow(tools, store, clock):
    return DisputeFlow(tools=tools, store=store, policy=PolicyEngine.load_default(), clock=clock,
                       trace_id="t-resp", sleep=lambda s: None)


def say(flow, lang, result):
    return render(result, lang, transaction=flow.txn, reason=flow.reason_code)


def test_both_languages_have_the_same_template_keys():
    assert T["es"].keys() == T["pt"].keys()


def test_confirm_message_uses_verified_transaction_data(flow, sessions):
    token = sessions.issue("CUST001")
    r = flow.handle(Turn(token=token, transaction_id="TXN001", reason_code=ReasonCode.FRAUD_CNP, evidence=EVIDENCE))
    text = say(flow, "pt", r)
    assert "1,250.00 MXN" in text and "Amazon MX" in text and "2026-06-15" in text
    assert "bloquear" in text


def test_done_message_only_mentions_block_when_card_was_blocked(flow, sessions):
    token = sessions.issue("CUST001")
    flow.handle(Turn(token=token, transaction_id="TXN001", reason_code=ReasonCode.FRAUD_CNP, evidence=EVIDENCE))
    r = flow.handle(Turn(token=token, confirm=True))
    text = say(flow, "es", r)
    assert r.case.case_id in text and "bloqueada" not in text


def test_ineligible_explains_the_rule_with_numbers(flow, sessions):
    r = flow.handle(Turn(token=sessions.issue("CUST001"), transaction_id="TXN004", reason_code=ReasonCode.FRAUD_CNP))
    assert "158" in say(flow, "es", r) and "120" in say(flow, "es", r)


def test_candidates_are_listed(flow, sessions):
    r = flow.handle(Turn(token=sessions.issue("CUST001"), merchant="Netflix", reason_code=ReasonCode.DUPLICATE))
    text = say(flow, "pt", r)
    assert "TXN002" in text and "TXN003" in text and "Qual delas" in text


def test_handoff_message_has_reference(flow, sessions):
    r = flow.handle(Turn(token=sessions.issue("CUST001"), human_requested=True))
    assert "HO-t-resp" in say(flow, "es", r)
