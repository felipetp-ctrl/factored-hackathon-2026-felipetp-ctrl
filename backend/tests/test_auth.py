import base64
import json
from datetime import timedelta

import pytest

from dispute_ops.auth import AuthError


def test_issue_and_verify_roundtrip(sessions):
    assert sessions.verify(sessions.issue("CUST001")).customer_id == "CUST001"


def test_expired_token_is_rejected(sessions, clock):
    token = sessions.issue("CUST001")
    clock.now += timedelta(minutes=16)
    with pytest.raises(AuthError) as exc:
        sessions.verify(token)
    assert exc.value.reason == "expired"


def test_tampered_subject_is_rejected(sessions):
    payload, sig = sessions.issue("CUST001").rsplit(".", 1)
    data = json.loads(base64.urlsafe_b64decode(payload))
    data["sub"] = "CUST002"
    forged = base64.urlsafe_b64encode(json.dumps(data).encode()).decode()
    with pytest.raises(AuthError) as exc:
        sessions.verify(f"{forged}.{sig}")
    assert exc.value.reason == "invalid"


@pytest.mark.parametrize("token", ["", "garbage", "CUST001"])
def test_garbage_and_bare_customer_id_are_rejected(sessions, token):
    with pytest.raises(AuthError):
        sessions.verify(token)
