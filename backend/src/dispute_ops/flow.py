from __future__ import annotations

import time
from collections.abc import Callable
from datetime import datetime, timedelta
from decimal import Decimal
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field

from dispute_ops.auth import AuthError
from dispute_ops.domain import (
    FRAUD_CODES, AuditEvent, Card, Channel, DisputeCase, PolicyDecision, ReasonCode, Transaction,
)
from dispute_ops.errors import AccessDenied, NotFound, ToolUnavailable
from dispute_ops.handoff import ActionRecord, HandoffPackage, build_handoff
from dispute_ops.policy.engine import PolicyContext, PolicyEngine
from dispute_ops.retry import call_with_retry
from dispute_ops.store import Store
from dispute_ops.tools import BankingTools

MAX_CLARIFY = 2
# Look further back than the dispute window when identifying a transaction, so the policy can
# explain why an old charge is out of window instead of the customer never finding it.
IDENTIFY_LOOKBACK_DAYS = 365


class State(StrEnum):
    START = "START"
    IDENTIFY_TXN = "IDENTIFY_TXN"
    CLASSIFY = "CLASSIFY"
    COLLECT_EVIDENCE = "COLLECT_EVIDENCE"
    CONFIRM = "CONFIRM"
    DONE = "DONE"
    INELIGIBLE = "INELIGIBLE"
    HANDOFF = "HANDOFF"
    CANCELLED = "CANCELLED"


TERMINAL = frozenset({State.DONE, State.INELIGIBLE, State.HANDOFF, State.CANCELLED})


class Turn(BaseModel):
    """Structured input for one customer turn. Produced by the NLU layer (LLM + classifier)
    in a later plan; the flow never sees free text."""

    token: str
    summary: str | None = None
    transaction_id: str | None = None
    merchant: str | None = None
    amount: Decimal | None = None
    reason_code: ReasonCode | None = None
    classifier_confidence: float | None = None
    evidence: dict[str, str] = Field(default_factory=dict)
    confirm: bool | None = None
    block_card: bool = False
    human_requested: bool = False
    very_negative_sentiment: bool = False
    ip_country_mismatch: bool = False
    regulatory_threat: bool = False


Action = Literal["ask", "confirm", "done", "ineligible", "handoff", "reauth", "cancelled"]


class FlowResult(BaseModel):
    state: State
    action: Action
    ask_for: list[str] = Field(default_factory=list)
    candidates: list[Transaction] = Field(default_factory=list)
    offer_block_card: bool = False
    case: DisputeCase | None = None
    card: Card | None = None
    policy: PolicyDecision | None = None
    handoff: HandoffPackage | None = None


class DisputeFlow:
    """Deterministic owner of a dispute case. Only this class calls write tools, and only
    after a policy decision, explicit confirmation, and it reports success only after a
    read-back verification."""

    def __init__(
        self,
        *,
        tools: BankingTools,
        store: Store,
        policy: PolicyEngine,
        clock: Callable[[], datetime],
        trace_id: str,
        channel: Channel = Channel.CHAT,
        language: str = "es",
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.tools, self.store, self.policy, self.clock = tools, store, policy, clock
        self.trace_id, self.channel, self.language, self.sleep = trace_id, channel, language, sleep
        self.state = State.START
        self.customer_id: str | None = None
        self.txn: Transaction | None = None
        self.reason_code: ReasonCode | None = None
        self.confidence = 1.0
        self.evidence: dict[str, str] = {}
        self.summary = ""
        self.flags = {
            "human_requested": False, "very_negative_sentiment": False, "ip_country_mismatch": False,
            "regulatory_threat": False,
        }
        self.actions: list[ActionRecord] = []
        self.attempts: dict[str, int] = {}
        self.last_policy: PolicyDecision | None = None
        self._final: FlowResult | None = None
        self.rejected_references: list[str] = []
        self.foreign_references = 0

    # ---- public API -------------------------------------------------------------------
    def handle(self, turn: Turn) -> FlowResult:
        if self._final is not None:
            return self._final
        try:
            session = self.tools.sessions.verify(turn.token)
        except AuthError as e:
            self._audit("auth_failed", reason=e.reason)
            return FlowResult(state=self.state, action="reauth")
        if self.customer_id is not None and session.customer_id != self.customer_id:
            self._audit("auth_failed", reason="session_mismatch")
            return FlowResult(state=self.state, action="reauth")
        self.customer_id = session.customer_id
        self._merge(turn)
        if self.flags["human_requested"]:
            return self._handoff(["customer_requested_human"])
        if self.state == State.CONFIRM:
            return self._on_confirm(turn)
        return self._advance(turn)

    def escalate(self, reasons: list[str]) -> FlowResult:
        """Hand off from outside the flow (e.g. the language layer is unavailable)."""
        if self._final is not None:
            return self._final
        return self._handoff(reasons)

    def close(self, reason: str) -> FlowResult:
        """End without action (e.g. customer recognised a proactively flagged transaction)."""
        self._audit("closed", reason=reason)
        return self._finish(FlowResult(state=State.CANCELLED, action="cancelled"))

    # ---- steps ------------------------------------------------------------------------
    def _merge(self, turn: Turn) -> None:
        if turn.summary:
            self.summary = turn.summary
        if turn.reason_code is not None:
            self.reason_code = turn.reason_code
            self.confidence = turn.classifier_confidence if turn.classifier_confidence is not None else 1.0
        self.evidence.update({k: v for k, v in turn.evidence.items() if v})
        for name in self.flags:
            self.flags[name] = self.flags[name] or getattr(turn, name)

    def _advance(self, turn: Turn) -> FlowResult:
        if self.txn is None:
            pending = self._identify(turn)
            if pending is not None:
                return pending
        if self.reason_code is None:
            return self._clarify(["reason_code"], "reason_code", State.CLASSIFY)
        try:
            decision = self._evaluate()
        except ToolUnavailable:
            return self._handoff(["tool_failure"])
        if decision.decision == "ineligible":
            return self._finish(FlowResult(state=State.INELIGIBLE, action="ineligible", policy=decision))
        if decision.decision == "handoff":
            return self._handoff(decision.handoff_reasons, decision)
        if decision.missing_evidence:
            return self._clarify(decision.missing_evidence, "evidence", State.COLLECT_EVIDENCE, policy=decision)
        self.state = State.CONFIRM
        self._audit("confirm_requested")
        return FlowResult(
            state=State.CONFIRM, action="confirm", policy=decision, offer_block_card=self._offer_block(turn.token)
        )

    def _identify(self, turn: Turn) -> FlowResult | None:
        try:
            if turn.transaction_id:
                try:
                    self.txn = self._retry(lambda: self.tools.get_transaction(turn.token, turn.transaction_id))
                except (AccessDenied, NotFound) as e:
                    # The customer gets the same answer for "not yours" and "does not exist" (no existence
                    # leak); the agent learns the real reason. Two invalid references end the automation.
                    self._audit("transaction_lookup_rejected", error=type(e).__name__, transaction_id=turn.transaction_id)
                    self.rejected_references.append(turn.transaction_id)
                    self.foreign_references += isinstance(e, AccessDenied)
                    if len(self.rejected_references) >= 2:
                        reason = "suspicious_access" if self.foreign_references else "invalid_transaction_references"
                        return self._handoff([reason], open_questions=["transaction"])
                    return self._clarify(["transaction"], "transaction", State.IDENTIFY_TXN)
            elif turn.merchant or turn.amount is not None:
                candidates = self._retry(
                    lambda: self.tools.search_transactions(
                        turn.token, days=IDENTIFY_LOOKBACK_DAYS, merchant=turn.merchant, amount=turn.amount
                    )
                )
                if len(candidates) != 1:
                    return self._clarify(["transaction"], "transaction", State.IDENTIFY_TXN, candidates=candidates[:5])
                self.txn = candidates[0]
            else:
                return self._clarify(["transaction"], "transaction", State.IDENTIFY_TXN)
        except ToolUnavailable:
            return self._handoff(["tool_failure"])
        self._audit("transaction_identified", transaction_id=self.txn.transaction_id)
        return None

    def _evaluate(self) -> PolicyDecision:
        assert self.txn is not None and self.reason_code is not None and self.customer_id is not None
        customer = self.store.get_customer(self.customer_id)
        assert customer is not None
        open_case = self.store.find_open_dispute(self.txn.transaction_id)
        ctx = PolicyContext(
            transaction=self.txn,
            customer=customer,
            reason_code=self.reason_code,
            now=self.clock(),
            evidence=self.evidence,
            open_dispute_case_id=open_case.case_id if open_case else None,
            disputes_last_30d=self.store.count_disputes_since(self.customer_id, self.clock() - timedelta(days=30)),
            classifier_confidence=self.confidence,
            very_negative_sentiment=self.flags["very_negative_sentiment"],
            ip_country_mismatch=self.flags["ip_country_mismatch"],
            regulatory_threat=self.flags["regulatory_threat"],
        )
        decision = self.policy.evaluate(ctx)
        self.last_policy = decision
        self._audit("policy_decision", **decision.model_dump(mode="json"))
        return decision

    def _on_confirm(self, turn: Turn) -> FlowResult:
        if turn.confirm is None:
            return FlowResult(
                state=State.CONFIRM, action="confirm", policy=self.last_policy,
                offer_block_card=self._offer_block(turn.token),
            )
        if turn.confirm is False:
            self._audit("customer_declined")
            return self._finish(FlowResult(state=State.CANCELLED, action="cancelled"))
        return self._act(turn)

    def _act(self, turn: Turn) -> FlowResult:
        assert self.txn is not None and self.reason_code is not None
        txn_id, reason = self.txn.transaction_id, self.reason_code
        try:
            case = self._retry(
                lambda: self.tools.open_dispute(
                    turn.token, txn_id, reason, self.evidence, idempotency_key=f"{self.trace_id}:open:{txn_id}"
                )
            )
        except ToolUnavailable:
            self._record("open_dispute", "failed")
            return self._handoff(["tool_failure"])
        if not self._verify(lambda: self.tools.get_case_status(turn.token, case.case_id).status == "Open"):
            self._record("open_dispute", "failed", case.case_id)
            return self._handoff(["verification_failed"])
        self._record("open_dispute", "verified", case.case_id)

        card: Card | None = None
        if turn.block_card:
            product_id = self.txn.product_id
            try:
                current = self._retry(lambda: self.tools.get_card(turn.token, product_id))
            except ToolUnavailable:
                self._record("block_card", "failed", product_id)
                return self._handoff(["tool_failure"])
            decision = self.policy.can_block_card(reason, current, customer_confirmed=True)
            self._audit("block_card_policy", **decision.model_dump(mode="json"))
            if decision.decision == "eligible":
                try:
                    self._retry(
                        lambda: self.tools.block_card(
                            turn.token, product_id, idempotency_key=f"{self.trace_id}:block:{product_id}"
                        )
                    )
                except ToolUnavailable:
                    self._record("block_card", "failed", product_id)
                    return self._handoff(["tool_failure"])
                if not self._verify(lambda: self.tools.get_card(turn.token, product_id).product_status == "Blocked"):
                    self._record("block_card", "failed", product_id)
                    return self._handoff(["verification_failed"])
                self._record("block_card", "verified", product_id)
                card = self.tools.get_card(turn.token, product_id)

        self._audit("done", case_id=case.case_id)
        return self._finish(
            FlowResult(state=State.DONE, action="done", case=case, card=card, policy=self.last_policy)
        )

    # ---- helpers ------------------------------------------------------------------------
    def _clarify(
        self,
        fields: list[str],
        counter: str,
        state: State,
        *,
        candidates: list[Transaction] | None = None,
        policy: PolicyDecision | None = None,
    ) -> FlowResult:
        if self.channel == Channel.PQR:
            return self._handoff(["async_missing_info"], policy, open_questions=fields)
        self.attempts[counter] = self.attempts.get(counter, 0) + 1
        if self.attempts[counter] > MAX_CLARIFY:
            return self._handoff(["clarification_exhausted"], policy, open_questions=fields)
        self.state = state
        self._audit("clarify", fields=fields, attempt=self.attempts[counter])
        return FlowResult(state=state, action="ask", ask_for=fields, candidates=candidates or [], policy=policy)

    def _handoff(
        self, reasons: list[str], policy: PolicyDecision | None = None, open_questions: list[str] | None = None
    ) -> FlowResult:
        pkg = build_handoff(
            trace_id=self.trace_id, channel=self.channel, language=self.language, reasons=reasons,
            summary=self.summary, transaction=self.txn, reason_code=self.reason_code, actions=self.actions,
            policy=policy or self.last_policy, open_questions=open_questions or [],
        )
        if self.rejected_references:
            pkg.risk_signals["rejected_references"] = list(self.rejected_references)
        self._audit("handoff", **pkg.model_dump(mode="json"))
        return self._finish(FlowResult(state=State.HANDOFF, action="handoff", handoff=pkg))

    def _offer_block(self, token: str) -> bool:
        if self.reason_code not in FRAUD_CODES or self.txn is None:
            return False
        try:
            return self.tools.get_card(token, self.txn.product_id).product_status == "Active"
        except ToolUnavailable:
            return False

    def _verify(self, check: Callable[[], bool]) -> bool:
        try:
            return self._retry(check)
        except ToolUnavailable:
            return False

    def _retry(self, fn: Callable[[], Any]) -> Any:
        return call_with_retry(fn, sleep=self.sleep)

    def _record(self, action: str, status: Literal["verified", "failed"], ref: str | None = None) -> None:
        self.actions.append(ActionRecord(action=action, status=status, at=self.clock(), ref=ref))
        self._audit("action", action=action, status=status, ref=ref)

    def _finish(self, result: FlowResult) -> FlowResult:
        self.state = result.state
        self._final = result
        return result

    def _audit(self, kind: str, **data: Any) -> None:
        self.store.append_audit(
            AuditEvent(trace_id=self.trace_id, at=self.clock(), kind=kind, data={"state": self.state, **data})
        )
