from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import datetime, timedelta
from decimal import Decimal

from dispute_ops.auth import SessionService
from dispute_ops.domain import Card, DisputeCase, ReasonCode, Transaction
from dispute_ops.errors import AccessDenied, NotFound, ToolUnavailable
from dispute_ops.store import Store

# Only READ_TOOLS may ever be exposed to the LLM. WRITE_TOOLS are called by the orchestrator
# after policy + customer confirmation.
READ_TOOLS = frozenset({"search_transactions", "get_transaction", "get_card", "get_case_status", "list_cards", "list_cases"})
WRITE_TOOLS = frozenset({"open_dispute", "block_card"})


class FailureInjector:
    """Test hook: make the next `times` calls of a tool raise ToolUnavailable."""

    def __init__(self) -> None:
        self._remaining: dict[str, int] = {}

    def fail(self, tool: str, times: int = 1) -> None:
        self._remaining[tool] = times

    def check(self, tool: str) -> None:
        n = self._remaining.get(tool, 0)
        if n > 0:
            self._remaining[tool] = n - 1
            raise ToolUnavailable(tool)


class BankingTools:
    """Mock banking tools. Every call takes a session token; ownership is resolved from it,
    never from an id supplied by the model."""

    def __init__(
        self,
        store: Store,
        sessions: SessionService,
        clock: Callable[[], datetime],
        policy_version: str,
        failures: FailureInjector | None = None,
    ) -> None:
        self.store = store
        self.sessions = sessions
        self.clock = clock
        self.policy_version = policy_version
        self.failures = failures or FailureInjector()
        self._idempotent: dict[str, DisputeCase | Card] = {}

    def _customer_id(self, token: str) -> str:
        return self.sessions.verify(token).customer_id

    def search_transactions(
        self, token: str, *, days: int = 120, merchant: str | None = None, amount: Decimal | None = None
    ) -> list[Transaction]:
        self.failures.check("search_transactions")
        customer_id = self._customer_id(token)
        txns = self.store.list_transactions(customer_id, self.clock() - timedelta(days=days))
        if merchant:
            txns = [t for t in txns if t.merchant_name and merchant.lower() in t.merchant_name.lower()]
        if amount is not None:
            txns = [t for t in txns if t.amount == amount]
        return txns

    def get_transaction(self, token: str, transaction_id: str) -> Transaction:
        self.failures.check("get_transaction")
        customer_id = self._customer_id(token)
        txn = self.store.get_transaction(transaction_id)
        if txn is None:
            raise NotFound(transaction_id)
        if txn.customer_id != customer_id:
            raise AccessDenied(transaction_id)
        return txn

    def get_card(self, token: str, product_id: str) -> Card:
        self.failures.check("get_card")
        customer_id = self._customer_id(token)
        card = self.store.get_card(product_id)
        if card is None:
            raise NotFound(product_id)
        if card.customer_id != customer_id:
            raise AccessDenied(product_id)
        return card

    def get_case_status(self, token: str, case_id: str) -> DisputeCase:
        self.failures.check("get_case_status")
        customer_id = self._customer_id(token)
        case = self.store.get_dispute(case_id)
        if case is None:
            raise NotFound(case_id)
        if case.customer_id != customer_id:
            raise AccessDenied(case_id)
        return case

    def list_cards(self, token: str) -> list[Card]:
        self.failures.check("list_cards")
        return self.store.list_cards(self._customer_id(token))

    def list_cases(self, token: str) -> list[DisputeCase]:
        self.failures.check("list_cases")
        return self.store.list_disputes(self._customer_id(token))

    def open_dispute(
        self,
        token: str,
        transaction_id: str,
        reason_code: ReasonCode,
        evidence: dict[str, str],
        *,
        idempotency_key: str,
    ) -> DisputeCase:
        if idempotency_key in self._idempotent:
            return self._idempotent[idempotency_key]  # type: ignore[return-value]
        self.failures.check("open_dispute")
        txn = self.get_transaction(token, transaction_id)
        case = DisputeCase(
            case_id=f"DSP-{uuid.uuid4().hex[:10].upper()}",
            customer_id=txn.customer_id,
            transaction_id=txn.transaction_id,
            reason_code=reason_code,
            evidence=dict(evidence),
            status="Open",
            created_at=self.clock(),
            policy_version=self.policy_version,
        )
        self.store.insert_dispute(case)
        self._idempotent[idempotency_key] = case
        return case

    def open_dispute_as_agent(
        self,
        agent_id: str,
        customer_id: str,
        transaction_id: str,
        reason_code: ReasonCode,
        evidence: dict[str, str],
        *,
        idempotency_key: str,
    ) -> DisputeCase:
        """Staff path: a human agent resolving a handed-off case. The customer comes from the handoff, and the
        transaction must belong to that customer; the caller has already applied the human-review policy."""
        if idempotency_key in self._idempotent:
            return self._idempotent[idempotency_key]  # type: ignore[return-value]
        self.failures.check("open_dispute")
        txn = self.store.get_transaction(transaction_id)
        if txn is None:
            raise NotFound(transaction_id)
        if txn.customer_id != customer_id:
            raise AccessDenied(transaction_id)
        case = DisputeCase(
            case_id=f"DSP-{uuid.uuid4().hex[:10].upper()}", customer_id=customer_id, transaction_id=transaction_id,
            reason_code=reason_code, evidence={**evidence, "opened_by": f"agent:{agent_id}"}, status="Open",
            created_at=self.clock(), policy_version=self.policy_version,
        )
        self.store.insert_dispute(case)
        self._idempotent[idempotency_key] = case
        return case

    def block_card(self, token: str, product_id: str, *, idempotency_key: str) -> Card:
        if idempotency_key in self._idempotent:
            return self._idempotent[idempotency_key]  # type: ignore[return-value]
        self.failures.check("block_card")
        self.get_card(token, product_id)
        self.store.set_card_status(product_id, "Blocked")
        card = self.store.get_card(product_id)
        assert card is not None
        self._idempotent[idempotency_key] = card
        return card
