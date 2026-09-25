from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field


class ReasonCode(StrEnum):
    FRAUD_CNP = "FRAUD_CNP"
    FRAUD_CP = "FRAUD_CP"
    DUPLICATE = "DUPLICATE"
    INCORRECT_AMOUNT = "INCORRECT_AMOUNT"
    NOT_RECEIVED = "NOT_RECEIVED"
    CANCELLED_RECURRING = "CANCELLED_RECURRING"


FRAUD_CODES = frozenset({ReasonCode.FRAUD_CNP, ReasonCode.FRAUD_CP})


class Channel(StrEnum):
    CHAT = "chat"
    PQR = "pqr"
    PROACTIVE = "proactive"


class Customer(BaseModel):
    customer_id: str
    country: str
    segment: str
    is_repeat_complainer: bool = False


class Card(BaseModel):
    product_id: str
    customer_id: str
    product_type: str
    product_status: str


class Transaction(BaseModel):
    transaction_id: str
    customer_id: str
    product_id: str
    transaction_date: datetime
    amount: Decimal
    currency: str
    amount_usd: Decimal
    merchant_name: str | None = None
    transaction_status: str
    transaction_country: str
    fraud_score: Decimal | None = None


class DisputeCase(BaseModel):
    case_id: str
    customer_id: str
    transaction_id: str
    reason_code: ReasonCode
    evidence: dict[str, str]
    status: str
    created_at: datetime
    policy_version: str


class PolicyDecision(BaseModel):
    decision: Literal["eligible", "ineligible", "handoff"]
    rule_ids: list[str]
    policy_version: str
    inputs: dict[str, Any]
    missing_evidence: list[str] = Field(default_factory=list)
    handoff_reasons: list[str] = Field(default_factory=list)


class AuditEvent(BaseModel):
    trace_id: str
    at: datetime
    kind: str
    data: dict[str, Any]
