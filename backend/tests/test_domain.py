from decimal import Decimal

import pytest
from pydantic import ValidationError

from dispute_ops.domain import FRAUD_CODES, PolicyDecision, ReasonCode, Transaction


def test_fraud_codes_are_only_fraud_reasons():
    assert FRAUD_CODES == {ReasonCode.FRAUD_CNP, ReasonCode.FRAUD_CP}


def test_transaction_parses_decimal_and_datetime_from_strings():
    t = Transaction(
        transaction_id="T1", customer_id="C1", product_id="P1",
        transaction_date="2026-06-15T10:00:00+00:00", amount="1250.00", currency="MXN",
        amount_usd="68.50", transaction_status="Approved", transaction_country="Mexico",
    )
    assert t.amount == Decimal("1250.00")
    assert t.transaction_date.year == 2026


def test_policy_decision_rejects_unknown_decision():
    with pytest.raises(ValidationError):
        PolicyDecision(decision="approve", rule_ids=[], policy_version="v", inputs={})
