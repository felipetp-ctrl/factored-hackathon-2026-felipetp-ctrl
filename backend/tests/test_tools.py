from datetime import timedelta
from decimal import Decimal

import pytest

from dispute_ops.auth import AuthError
from dispute_ops.domain import ReasonCode
from dispute_ops.errors import AccessDenied, NotFound, ToolUnavailable
from dispute_ops.tools import READ_TOOLS, WRITE_TOOLS


def test_read_and_write_tool_sets_are_disjoint():
    assert READ_TOOLS.isdisjoint(WRITE_TOOLS)


def test_search_returns_only_session_customer_transactions(tools, sessions):
    token = sessions.issue("CUST002")
    assert [t.transaction_id for t in tools.search_transactions(token)] == ["TXN101"]


def test_search_filters_by_merchant_and_amount(tools, sessions):
    token = sessions.issue("CUST001")
    assert len(tools.search_transactions(token, merchant="netflix")) == 2
    assert [t.transaction_id for t in tools.search_transactions(token, amount=Decimal("1250.00"))] == ["TXN001"]


def test_cross_customer_access_is_denied(tools, sessions):
    token = sessions.issue("CUST002")
    with pytest.raises(AccessDenied):
        tools.get_transaction(token, "TXN001")
    with pytest.raises(AccessDenied):
        tools.get_card(token, "PRD001")
    with pytest.raises(NotFound):
        tools.get_transaction(token, "TXN999")


def test_expired_session_is_rejected(tools, sessions, clock):
    token = sessions.issue("CUST001")
    clock.now += timedelta(hours=1)
    with pytest.raises(AuthError):
        tools.search_transactions(token)


def test_open_dispute_persists_and_is_idempotent(tools, sessions, store):
    token = sessions.issue("CUST001")
    a = tools.open_dispute(token, "TXN001", ReasonCode.FRAUD_CNP, {"card_in_possession": "yes"}, idempotency_key="k1")
    b = tools.open_dispute(token, "TXN001", ReasonCode.FRAUD_CNP, {"card_in_possession": "yes"}, idempotency_key="k1")
    assert a.case_id == b.case_id
    assert tools.get_case_status(token, a.case_id).status == "Open"
    assert store.count_disputes_since("CUST001", a.created_at - timedelta(seconds=1)) == 1


def test_open_dispute_rejects_other_customers_transaction(tools, sessions):
    with pytest.raises(AccessDenied):
        tools.open_dispute(sessions.issue("CUST002"), "TXN001", ReasonCode.FRAUD_CNP, {}, idempotency_key="k2")


def test_block_card_changes_status(tools, sessions):
    token = sessions.issue("CUST001")
    assert tools.block_card(token, "PRD001", idempotency_key="b1").product_status == "Blocked"
    assert tools.get_card(token, "PRD001").product_status == "Blocked"


def test_failure_injection_is_transient(tools, sessions, failures):
    token = sessions.issue("CUST001")
    failures.fail("search_transactions", times=1)
    with pytest.raises(ToolUnavailable):
        tools.search_transactions(token)
    assert tools.search_transactions(token)


# ---- v0.0.2 ----------------------------------------------------------------------------------------

def test_customer_reads_only_their_own_cards_and_cases(tools, sessions):
    t1, t2 = sessions.issue("CUST001"), sessions.issue("CUST002")
    case = tools.open_dispute(t1, "TXN001", ReasonCode.FRAUD_CNP, {}, idempotency_key="k1")
    assert [c.case_id for c in tools.list_cases(t1)] == [case.case_id]
    assert tools.list_cases(t2) == []
    assert [c.product_id for c in tools.list_cards(t2)] == ["PRD002"]


def test_agent_opens_a_dispute_on_behalf_of_the_case_customer_only(tools):
    case = tools.open_dispute_as_agent("agent-demo", "CUST001", "TXN005", ReasonCode.FRAUD_CNP, {"agent_note": "ok"},
                                       idempotency_key="a1")
    assert case.customer_id == "CUST001" and case.evidence["opened_by"] == "agent:agent-demo"
    with pytest.raises(AccessDenied):
        tools.open_dispute_as_agent("agent-demo", "CUST002", "TXN005", ReasonCode.FRAUD_CNP, {}, idempotency_key="a2")
