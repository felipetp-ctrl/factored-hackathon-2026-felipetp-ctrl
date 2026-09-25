from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel

from dispute_ops.domain import Channel, PolicyDecision, ReasonCode, Transaction


class VerifiedFact(BaseModel):
    fact: str
    source: str


class ActionRecord(BaseModel):
    action: str
    status: Literal["verified", "failed"]
    at: datetime
    ref: str | None = None


class HandoffPackage(BaseModel):
    """What a human agent receives. Deliberately has no raw transcript field:
    the transcript is reachable only through the trace_id."""

    case_ref: str
    reason_for_handoff: list[str]
    language: str
    channel: Channel
    customer_request_summary: str
    verified_facts: list[VerifiedFact]
    proposed_reason_code: ReasonCode | None
    actions_taken: list[ActionRecord]
    policy_decision: PolicyDecision | None
    open_questions: list[str]
    risk_signals: dict[str, Any]
    trace_id: str


def build_handoff(
    *,
    trace_id: str,
    channel: Channel,
    language: str,
    reasons: list[str],
    summary: str,
    transaction: Transaction | None,
    reason_code: ReasonCode | None,
    actions: list[ActionRecord],
    policy: PolicyDecision | None,
    open_questions: list[str],
) -> HandoffPackage:
    facts: list[VerifiedFact] = []
    risk: dict[str, Any] = {}
    if transaction is not None:
        t = transaction
        facts.append(
            VerifiedFact(
                fact=(
                    f"Transaction {t.transaction_id}: {t.amount} {t.currency} (USD {t.amount_usd}) "
                    f"at {t.merchant_name or 'unknown merchant'} on {t.transaction_date.date()}, "
                    f"status {t.transaction_status}"
                ),
                source=f"txn:{t.transaction_id}",
            )
        )
        risk["fraud_score"] = str(t.fraud_score) if t.fraud_score is not None else None
        risk["amount_usd"] = str(t.amount_usd)
    questions = list(open_questions)
    if transaction is None and "transaction" not in questions:
        questions.append("transaction")
    if reason_code is None and "reason_code" not in questions:
        questions.append("reason_code")
    return HandoffPackage(
        case_ref=f"HO-{trace_id}",
        reason_for_handoff=reasons,
        language=language,
        channel=channel,
        customer_request_summary=summary,
        verified_facts=facts,
        proposed_reason_code=reason_code,
        actions_taken=actions,
        policy_decision=policy,
        open_questions=questions,
        risk_signals=risk,
        trace_id=trace_id,
    )
