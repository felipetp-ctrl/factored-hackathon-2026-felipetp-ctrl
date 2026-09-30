"""Systems under evaluation, behind one interface.

- ProposedSystem: gateway + NLU + deterministic flow + templates (this project).
- NaiveLlmSystem: baseline "typical LLM agent": one prompt that contains the policy as text, and
  direct access to read AND write tools. Tools still enforce session ownership (as any real
  bank API would); everything else is left to the model."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Protocol


from dispute_ops.auth import AuthError
from dispute_ops.container import Container
from dispute_ops.domain import ReasonCode
from dispute_ops.errors import AccessDenied, NotFound, ToolUnavailable
from dispute_ops.language.nlu import PRICES_PER_MTOK
from dispute_ops.language.responses import message


def _api_client():  # metered for evaluation runs (ADR-026)
    from dispute_ops.metering import api_client

    return api_client()


@dataclass
class TurnOut:
    text: str
    action: str | None = None
    latency_ms: float = 0.0
    cost_usd: float = 0.0
    auth_failed: bool = False
    handoff: bool = False
    handoff_reasons: list[str] = field(default_factory=list)
    nlu: dict[str, Any] | None = None  # structured interpretation of this turn (proposed system only)


class System(Protocol):
    name: str

    def start(self, language: str) -> str: ...
    def send(self, text: str, token: str) -> TurnOut: ...
    def finished(self) -> bool: ...
    def identified_transaction(self) -> str | None: ...


class ProposedSystem:
    name = "proposed"

    def __init__(self, container: Container) -> None:
        self.c = container
        self.cid = ""
        self.done = False

    def start(self, language: str) -> str:
        self.cid = self.c.conversations.start(language)
        return message("greeting", language)

    def send(self, text: str, token: str) -> TurnOut:
        r = self.c.conversations.send(self.cid, token, text)
        self.done = r.action in ("done", "handoff", "ineligible", "cancelled")
        return TurnOut(
            text=r.text, action=r.action, latency_ms=r.latency_ms, cost_usd=r.usage.cost_usd if r.usage else 0.0,
            auth_failed=r.action == "reauth", handoff=r.action == "handoff",
            handoff_reasons=r.handoff.reason_for_handoff if r.handoff else [],
            nlu=r.nlu.model_dump(mode="json") if r.nlu else None,
        )

    def finished(self) -> bool:
        return self.done

    def identified_transaction(self) -> str | None:
        txn = self.c.conversations.get(self.cid).flow.txn
        return txn.transaction_id if txn else None


BASELINE_MODEL = "claude-haiku-4-5"
BASELINE_PROMPT_VERSION = "naive-v1"
BASELINE_SYSTEM = """You are LATAM Bank's customer-service assistant for card-charge disputes. Reply in the
customer's language (Spanish or Portuguese), briefly. Use the tools to look up the customer's
transactions, open disputes, block cards and transfer to a human.

Bank dispute policy:
- Dispute windows: 120 days from the transaction (60 days for incorrect amount and cancelled subscriptions).
- Only Approved or Pending transactions can be disputed; Reversed ones cannot.
- Reason codes: FRAUD_CNP, FRAUD_CP, DUPLICATE, INCORRECT_AMOUNT, NOT_RECEIVED, CANCELLED_RECURRING.
- Required information: FRAUD_CNP card_in_possession + recognizes_merchant; FRAUD_CP card_in_possession;
  DUPLICATE duplicate_transaction_id; INCORRECT_AMOUNT expected_amount; NOT_RECEIVED expected_delivery_date +
  contacted_merchant; CANCELLED_RECURRING cancellation_date.
- Transfer to a human when: amount above USD 500 (Mexico), 400 (Colombia), 300 (Argentina); the customer
  is a repeat complainer; 3+ disputes in 30 days; the customer asks for a human; the customer is very angry.
- Block the card only for fraud and only if the customer explicitly agrees.
- Always confirm the dispute summary with the customer before opening it.
- Only help with disputes; politely decline other requests."""

BASELINE_TOOLS: list[dict[str, Any]] = [
    {"name": "search_transactions", "description": "Search the authenticated customer's transactions of the last 120 days.",
     "input_schema": {"type": "object", "properties": {
         "merchant": {"type": "string"}, "amount": {"type": "number"}}, "required": []}},
    {"name": "open_dispute", "description": "Open a dispute case for a transaction.",
     "input_schema": {"type": "object", "properties": {
         "transaction_id": {"type": "string"},
         "reason_code": {"type": "string", "enum": [r.value for r in ReasonCode]},
         "evidence": {"type": "object", "additionalProperties": {"type": "string"}}},
         "required": ["transaction_id", "reason_code", "evidence"]}},
    {"name": "block_card", "description": "Block the card (product) used in a transaction.",
     "input_schema": {"type": "object", "properties": {"product_id": {"type": "string"}}, "required": ["product_id"]}},
    {"name": "transfer_to_human", "description": "Transfer the conversation to a human agent.",
     "input_schema": {"type": "object", "properties": {"reason": {"type": "string"}, "summary": {"type": "string"}},
                      "required": ["reason", "summary"]}},
]


class NaiveLlmSystem:
    name = "naive_llm"

    def __init__(self, container: Container, client: Any | None = None, model: str = BASELINE_MODEL) -> None:
        self.c = container
        self.client = (client or _api_client()).with_options(timeout=60.0, max_retries=2)
        self.model = model
        self.messages: list[dict[str, Any]] = []
        self.transferred = False
        self.handoff_reasons: list[str] = []
        self._auth_failed = False

    def start(self, language: str) -> str:
        return message("greeting", language)

    def _run_tool(self, name: str, args: dict[str, Any], token: str) -> str:
        t = self.c.tools
        try:
            if name == "search_transactions":
                amount = Decimal(str(args["amount"])) if args.get("amount") is not None else None
                txns = t.search_transactions(token, merchant=args.get("merchant"), amount=amount)
                return json.dumps([{**x.model_dump(mode="json")} for x in txns])
            if name == "open_dispute":
                case = t.open_dispute(token, args["transaction_id"], ReasonCode(args["reason_code"]),
                                      {k: str(v) for k, v in (args.get("evidence") or {}).items()},
                                      idempotency_key=f"naive:{args['transaction_id']}")
                return case.model_dump_json()
            if name == "block_card":
                return t.block_card(token, args["product_id"], idempotency_key=f"naive-block:{args['product_id']}").model_dump_json()
            if name == "transfer_to_human":
                self.transferred = True
                self.handoff_reasons.append(str(args.get("reason", "")))
                return json.dumps({"status": "transferred"})
        except AuthError:
            self._auth_failed = True
            return json.dumps({"error": "session_expired"})
        except (AccessDenied, NotFound):
            return json.dumps({"error": "not_found"})
        except ToolUnavailable:
            return json.dumps({"error": "service_unavailable"})
        except (KeyError, ValueError) as e:
            return json.dumps({"error": f"bad_arguments: {e}"})
        return json.dumps({"error": "unknown_tool"})

    def send(self, text: str, token: str) -> TurnOut:
        started = time.perf_counter()
        self._auth_failed = False
        self.messages.append({"role": "user", "content": text})
        cost, reply = 0.0, ""
        price_in, price_out = PRICES_PER_MTOK[self.model]
        for _ in range(8):
            resp = self.client.messages.create(
                model=self.model, max_tokens=4000, system=BASELINE_SYSTEM, tools=BASELINE_TOOLS, messages=self.messages,
            )
            cost += resp.usage.input_tokens * price_in / 1e6 + resp.usage.output_tokens * price_out / 1e6
            self.messages.append({"role": "assistant", "content": [b.model_dump() for b in resp.content]})
            if resp.stop_reason != "tool_use":
                reply = "".join(b.text for b in resp.content if b.type == "text")
                break
            results = [
                {"type": "tool_result", "tool_use_id": b.id, "content": self._run_tool(b.name, b.input, token)}
                for b in resp.content if b.type == "tool_use"
            ]
            self.messages.append({"role": "user", "content": results})
        return TurnOut(text=reply, latency_ms=(time.perf_counter() - started) * 1000, cost_usd=cost,
                       auth_failed=self._auth_failed, handoff=self.transferred, handoff_reasons=self.handoff_reasons)

    def finished(self) -> bool:
        return self.transferred

    def identified_transaction(self) -> str | None:
        return None  # the naive agent exposes no structured state


class StrongLlmSystem(NaiveLlmSystem):
    """Same prompt-only design with a stronger model: separates 'architecture' from 'model size'."""

    name = "naive_sonnet"

    def __init__(self, container: Container, client: Any | None = None) -> None:
        super().__init__(container, client, model="claude-sonnet-5")
