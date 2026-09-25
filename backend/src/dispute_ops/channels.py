from __future__ import annotations

import time
from collections.abc import Callable
from datetime import datetime, timedelta
from decimal import Decimal

from pydantic import BaseModel, Field

from dispute_ops.auth import SessionService
from dispute_ops.domain import Channel, ReasonCode, Transaction
from dispute_ops.flow import DisputeFlow, FlowResult, Turn
from dispute_ops.policy.engine import PolicyEngine
from dispute_ops.store import Store
from dispute_ops.tools import BankingTools


class PqrComplaint(BaseModel):
    """A written complaint already received and identified by the PQR system."""

    complaint_id: str
    customer_id: str
    description: str
    transaction_id: str | None = None
    evidence: dict[str, str] = Field(default_factory=dict)


def run_pqr_complaint(
    complaint: PqrComplaint,
    *,
    reason_code: ReasonCode | None,
    classifier_confidence: float | None,
    tools: BankingTools,
    store: Store,
    policy: PolicyEngine,
    sessions: SessionService,
    clock: Callable[[], datetime],
    sleep: Callable[[float], None] = time.sleep,
) -> FlowResult:
    """Async channel. Identity comes from the PQR system (internal trusted issuer). The filed
    complaint is the customer's consent to open a dispute; card blocking is never done
    asynchronously because it needs explicit confirmation."""
    token = sessions.issue(complaint.customer_id)
    flow = DisputeFlow(
        tools=tools, store=store, policy=policy, clock=clock,
        trace_id=f"pqr-{complaint.complaint_id}", channel=Channel.PQR, language="es", sleep=sleep,
    )
    result = flow.handle(
        Turn(
            token=token, summary=complaint.description, transaction_id=complaint.transaction_id,
            reason_code=reason_code, classifier_confidence=classifier_confidence, evidence=complaint.evidence,
        )
    )
    if result.action == "confirm":
        result = flow.handle(Turn(token=token, confirm=True, block_card=False))
    return result


def select_fraud_alerts(
    store: Store, clock: Callable[[], datetime], *, lookback_hours: int = 48, min_score: Decimal = Decimal("80")
) -> list[Transaction]:
    """Proactive channel candidates: recent approved transactions with a high fraud score and no dispute."""
    return store.list_high_fraud_score(clock() - timedelta(hours=lookback_hours), min_score)


def handle_proactive_reply(
    flow: DisputeFlow, *, token: str, transaction_id: str, recognized: bool
) -> FlowResult:
    """Customer answered 'was it you?' from an authenticated app session.
    recognized=True closes the alert; otherwise a FRAUD_CNP dispute is prepared and the
    flow asks for confirmation (with the card-block offer) like any chat case."""
    if recognized:
        return flow.close("transaction_recognized")
    result = flow.handle(
        Turn(
            token=token, transaction_id=transaction_id, reason_code=ReasonCode.FRAUD_CNP,
            evidence={"recognizes_merchant": "no"},
        )
    )
    return result
