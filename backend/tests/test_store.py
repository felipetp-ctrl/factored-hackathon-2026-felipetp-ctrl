import sqlite3
from datetime import timedelta
from decimal import Decimal

import pytest

from dispute_ops.domain import AuditEvent, DisputeCase, ReasonCode
from helpers import NOW


def test_seed_loads_customers_cards_and_transactions(store):
    assert store.get_customer("CUST002").is_repeat_complainer is True
    assert store.get_card("PRD001").product_status == "Active"
    assert store.get_transaction("TXN001").amount == Decimal("1250.00")
    assert store.get_transaction("NOPE") is None


def test_list_transactions_filters_by_customer_and_date(store):
    txns = store.list_transactions("CUST001", NOW - timedelta(days=120))
    ids = [t.transaction_id for t in txns]
    assert "TXN004" not in ids  # older than 120 days
    assert "TXN101" not in ids  # other customer
    assert ids[0] == "TXN007"  # newest first


def test_dispute_roundtrip_and_open_lookup(store):
    case = DisputeCase(
        case_id="DSP-1", customer_id="CUST001", transaction_id="TXN001",
        reason_code=ReasonCode.FRAUD_CNP, evidence={"card_in_possession": "yes"},
        status="Open", created_at=NOW, policy_version="disputes_v1",
    )
    store.insert_dispute(case)
    assert store.get_dispute("DSP-1") == case
    assert store.find_open_dispute("TXN001").case_id == "DSP-1"
    assert store.count_disputes_since("CUST001", NOW - timedelta(days=30)) == 1


def test_high_fraud_score_excludes_disputed_and_low_scores(store):
    ids = [t.transaction_id for t in store.list_high_fraud_score(NOW - timedelta(days=7), Decimal("80"))]
    assert ids == ["TXN005", "TXN007"]


def test_audit_log_is_append_only(store):
    store.append_audit(AuditEvent(trace_id="t1", at=NOW, kind="x", data={"a": 1}))
    assert store.list_audit("t1")[0].data == {"a": 1}
    with pytest.raises(sqlite3.DatabaseError):
        store.conn.execute("DELETE FROM audit_events")
    with pytest.raises(sqlite3.DatabaseError):
        store.conn.execute("UPDATE audit_events SET kind='y'")


# ---- v0.0.2 ----------------------------------------------------------------------------------------

def test_first_name_is_optional_and_old_databases_are_migrated(tmp_path):
    from dispute_ops.store import Store

    path = tmp_path / "old.db"
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE customers (customer_id TEXT PRIMARY KEY, country TEXT NOT NULL, segment TEXT NOT NULL, "
                 "is_repeat_complainer INTEGER NOT NULL)")
    conn.execute("INSERT INTO customers VALUES ('C1','Mexico','Basic',0)")
    conn.commit()
    conn.close()
    s = Store(path)
    assert s.get_customer("C1").first_name is None


def test_seed_first_names_merchants_cards_and_cases(store):
    assert store.get_customer("CUST001").first_name == "Lucía"
    assert "Netflix" in store.distinct_merchants() and None not in store.distinct_merchants()
    assert [c.product_id for c in store.list_cards("CUST001")] == ["PRD001"]
    case = DisputeCase(case_id="DSP-9", customer_id="CUST001", transaction_id="TXN001", reason_code=ReasonCode.FRAUD_CNP,
                       evidence={}, status="Open", created_at=NOW, policy_version="disputes_v2")
    store.insert_dispute(case)
    assert [c.case_id for c in store.list_disputes("CUST001")] == ["DSP-9"]
    assert store.list_disputes("CUST002") == []
