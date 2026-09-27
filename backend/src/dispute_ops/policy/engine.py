from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from importlib import resources
from typing import Any

import yaml

from dispute_ops.domain import FRAUD_CODES, Card, Customer, PolicyDecision, ReasonCode, Transaction


@dataclass(frozen=True)
class PolicyContext:
    transaction: Transaction
    customer: Customer
    reason_code: ReasonCode
    now: datetime
    evidence: dict[str, str] = field(default_factory=dict)
    open_dispute_case_id: str | None = None
    disputes_last_30d: int = 0
    classifier_confidence: float = 1.0
    human_requested: bool = False
    very_negative_sentiment: bool = False
    ip_country_mismatch: bool = False
    regulatory_threat: bool = False


class PolicyEngine:
    """Deterministic dispute policy. Every decision carries rule ids + inputs (the audit explanation)."""

    def __init__(self, rules: dict[str, Any]) -> None:
        self.rules = rules
        self.version: str = rules["version"]

    @classmethod
    def load_default(cls, version: str = "disputes_v2") -> PolicyEngine:
        text = resources.files("dispute_ops.policy").joinpath(f"{version}.yaml").read_text()
        return cls(yaml.safe_load(text))

    def required_evidence(self, reason_code: ReasonCode) -> list[str]:
        return list(self.rules["required_evidence"][reason_code.value])

    def evaluate(self, ctx: PolicyContext) -> PolicyDecision:
        txn = ctx.transaction
        h = self.rules["handoff"]
        age_days = (ctx.now - txn.transaction_date).days
        window = self.rules["dispute_window_days"][ctx.reason_code.value]
        threshold = h["amount_usd_threshold"].get(ctx.customer.country, h["amount_usd_threshold_default"])
        inputs: dict[str, Any] = {
            "transaction_id": txn.transaction_id,
            "reason_code": ctx.reason_code.value,
            "age_days": age_days,
            "window_days": window,
            "transaction_status": txn.transaction_status,
            "amount_usd": str(txn.amount_usd),
            "amount_usd_threshold": threshold,
            "disputes_last_30d": ctx.disputes_last_30d,
            "classifier_confidence": ctx.classifier_confidence,
        }

        def decide(decision: str, rule_ids: list[str], **extra: Any) -> PolicyDecision:
            return PolicyDecision(
                decision=decision, rule_ids=rule_ids, policy_version=self.version, inputs=inputs, **extra
            )

        if ctx.human_requested:
            return decide("handoff", ["R-HUMAN-REQUEST"], handoff_reasons=["customer_requested_human"])
        if ctx.open_dispute_case_id is not None:
            inputs["open_dispute_case_id"] = ctx.open_dispute_case_id
            return decide("ineligible", ["R-DUP-OPEN"])
        if txn.transaction_status not in self.rules["eligible_txn_status"]:
            return decide("ineligible", ["R-TXN-STATUS"])
        if age_days > window:
            return decide("ineligible", ["R-WINDOW"])

        checks = [
            (txn.amount_usd > Decimal(str(threshold)), "R-HO-AMOUNT", "amount_above_threshold"),
            (ctx.customer.is_repeat_complainer, "R-HO-REPEAT", "repeat_complainer"),
            (ctx.disputes_last_30d >= h["max_disputes_30d"], "R-HO-VELOCITY", "dispute_velocity"),
            (ctx.ip_country_mismatch, "R-HO-ATO", "account_takeover_signal"),
            (ctx.very_negative_sentiment, "R-HO-SENTIMENT", "very_negative_sentiment"),
            (ctx.regulatory_threat, "R-HO-REGULATOR", "regulatory_or_legal_threat"),
            (ctx.classifier_confidence < h["min_classifier_confidence"], "R-HO-LOWCONF", "low_classifier_confidence"),
        ]
        hits = [(rule_id, reason) for hit, rule_id, reason in checks if hit]
        if hits:
            return decide(
                "handoff", [r for r, _ in hits], handoff_reasons=[reason for _, reason in hits]
            )

        missing = [e for e in self.required_evidence(ctx.reason_code) if not ctx.evidence.get(e)]
        return decide("eligible", ["R-ELIGIBLE"], missing_evidence=missing)

    def evaluate_human_review(self, ctx: PolicyContext) -> PolicyDecision:
        """Decision for a human agent resolving a handed-off case. Handoff triggers exist to bring a person in,
        so they no longer block; ineligibility rules (open duplicate, status, window) still apply."""
        automated = self.evaluate(ctx)
        if automated.decision == "ineligible":
            return automated
        overridden = automated.rule_ids if automated.decision == "handoff" else []
        return PolicyDecision(
            decision="eligible", rule_ids=["R-HUMAN-REVIEW"], policy_version=self.version,
            inputs={**automated.inputs, "overridden_rules": overridden},
        )

    def can_block_card(self, reason_code: ReasonCode, card: Card, customer_confirmed: bool) -> PolicyDecision:
        inputs = {
            "reason_code": reason_code.value,
            "product_id": card.product_id,
            "product_status": card.product_status,
            "customer_confirmed": customer_confirmed,
        }

        def decide(decision: str, rule_id: str) -> PolicyDecision:
            return PolicyDecision(decision=decision, rule_ids=[rule_id], policy_version=self.version, inputs=inputs)

        if reason_code not in FRAUD_CODES:
            return decide("ineligible", "R-BLOCK-NOT-FRAUD")
        if card.product_status != "Active":
            return decide("ineligible", "R-BLOCK-NOT-ACTIVE")
        if not customer_confirmed:
            return decide("ineligible", "R-BLOCK-NO-CONFIRM")
        return decide("eligible", "R-BLOCK-OK")
