from __future__ import annotations

import time
from collections.abc import Callable
from datetime import datetime, timedelta
from decimal import Decimal

from pydantic import BaseModel, Field

from dispute_ops.auth import SessionService
from dispute_ops.domain import FRAUD_ALERT_MIN_SCORE, Channel, ReasonCode, Transaction
from dispute_ops.flow import DisputeFlow, FlowResult, Turn
from dispute_ops.policy.engine import PolicyEngine
from dispute_ops.store import Store
from dispute_ops.tools import BankingTools


class PqrComplaint(BaseModel):
    """A written complaint already received and identified by the PQR system. Real complaints carry no
    transaction id; product, claimed amount and creation date are used to find it."""

    complaint_id: str
    customer_id: str
    description: str
    transaction_id: str | None = None
    affected_product_id: str | None = None
    claimed_amount: Decimal | None = None
    created_at: datetime | None = None
    evidence: dict[str, str] = Field(default_factory=dict)


MATCH_LOOKBACK_DAYS = 120


def match_complaint(store: Store, c: PqrComplaint, as_of: datetime) -> tuple[str | None, list[Transaction]]:
    """Candidate transactions for a complaint: the customer's approved/pending charges in the 120 days before
    the complaint, narrowed by product and by claimed amount (±1%) when present. Unique -> matched."""
    until = c.created_at or as_of
    txns = [t for t in store.list_transactions(c.customer_id, until - timedelta(days=MATCH_LOOKBACK_DAYS))
            if t.transaction_date <= until and t.transaction_status in ("Approved", "Pending")]
    card = store.get_card(c.affected_product_id) if c.affected_product_id else None
    if card is not None and card.customer_id == c.customer_id:  # a foreign product reference is ignored
        txns = [t for t in txns if t.product_id == c.affected_product_id]
    if c.claimed_amount:
        close = [t for t in txns if abs(t.amount - c.claimed_amount) <= c.claimed_amount * Decimal("0.01")]
        txns = close or txns
    return (txns[0].transaction_id if len(txns) == 1 else None), txns[:5]


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
    shortlist: list[Transaction] = []
    if complaint.transaction_id is None:
        matched, shortlist = match_complaint(store, complaint, clock())
        complaint = complaint.model_copy(update={"transaction_id": matched})
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
    if result.handoff is not None and shortlist and complaint.transaction_id is None:
        result.handoff.risk_signals["candidate_transactions"] = [t.transaction_id for t in shortlist]
    return result


def select_fraud_alerts(
    store: Store, clock: Callable[[], datetime], *, lookback_hours: int = 48, min_score: Decimal = Decimal(FRAUD_ALERT_MIN_SCORE)
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
