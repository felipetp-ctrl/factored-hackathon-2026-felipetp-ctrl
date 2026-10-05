"""One customer conversation turn: gateway -> NLU -> deterministic flow -> templated reply."""

from __future__ import annotations

import re
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Protocol

from pydantic import BaseModel, Field

from dispute_ops.domain import AuditEvent, Channel, PolicyDecision, ReasonCode, Transaction
from dispute_ops.flow import DisputeFlow, FlowResult, State, Turn
from dispute_ops.handoff import HandoffPackage
from dispute_ops.language import responses
from dispute_ops.language.breaker import CircuitBreaker
from dispute_ops.language.keywords import _norm
from dispute_ops.language.rule_nlu import _TXN_ID, POSSESSION_CUES, is_rules_model
from dispute_ops.language.gateway import detect_human_request, detect_injection, detect_language, redact_pii
from dispute_ops.language.nlu import LlmUsage, NluContext, NluOutcome, NluResult, NluUnavailable
from dispute_ops.policy.engine import PolicyEngine
from dispute_ops.store import Store
from dispute_ops.tools import BankingTools

BARE_NO = re.compile(r"(no|nao|nop|no gracias|nao obrigad[oa])")


class Nlu(Protocol):
    def interpret(self, text: str, ctx: NluContext) -> NluOutcome: ...


class Budget:
    """Spend caps for model calls; past any of them the service uses the free rule-based NLU (ADR-026).

    `limit_usd` caps this process's source (the demo, or evaluation runs), `daily_limit_usd` one calendar day of it,
    `global_limit_usd` every source together (the project's API credit), and `child` gives each demo workspace its own
    share. With a `SpendLedger` the counters live in Postgres, shared across processes and restarts; a ledger error
    fails closed. Without one they live in memory (tests, local runs)."""

    def __init__(
        self, limit_usd: float | None, *, daily_limit_usd: float | None = None,
        global_limit_usd: float | None = None, ledger: Any = None,
        clock: Callable[[], datetime] | None = None, parent: Budget | None = None,
    ) -> None:
        self.limit_usd, self.daily_limit_usd, self.global_limit_usd = limit_usd, daily_limit_usd, global_limit_usd
        self.ledger, self.parent = ledger, parent
        self.clock = clock or (lambda: datetime.now().astimezone())
        self.spent_usd = 0.0
        self.by_day: dict[str, float] = {}
        self.failed = False  # ledger unreachable: closed, retried after REOPEN_SECONDS
        self._failed_at = 0.0

    def child(self, limit_usd: float | None) -> Budget:
        """A per-workspace cap that also counts against this budget."""
        return Budget(limit_usd, clock=self.clock, parent=self)

    def _today(self) -> str:
        return self.clock().date().isoformat()

    REOPEN_SECONDS = 30.0

    def _ledger_call(self, fn: Callable[[], None]) -> None:
        from dispute_ops.spend_ledger import LedgerError

        try:
            fn()
            self.failed = False
        except LedgerError:
            self.failed, self._failed_at = True, time.monotonic()

    def add(self, cost_usd: float) -> None:
        if cost_usd <= 0:
            return
        self.spent_usd += cost_usd
        day = self._today()
        self.by_day[day] = self.by_day.get(day, 0.0) + cost_usd
        if self.ledger is not None:
            self._ledger_call(lambda: self.ledger.add(cost_usd))
        if self.parent is not None:
            self.parent.add(cost_usd)

    def _totals(self) -> tuple[float, float, float]:
        """(this source, this source today, every source)."""
        if self.ledger is None:
            return self.spent_usd, self.by_day.get(self._today(), 0.0), self.spent_usd
        self._ledger_call(self.ledger.refresh)
        return self.ledger.total_source, self.ledger.today_source, self.ledger.total_all

    def exhausted(self) -> bool:
        if self.failed and time.monotonic() - self._failed_at < self.REOPEN_SECONDS:
            return True
        source, today, everyone = self._totals()  # with a ledger, a successful read reopens the budget
        if self.failed:
            return True
        if self.limit_usd is not None and source >= self.limit_usd:
            return True
        if self.daily_limit_usd is not None and today >= self.daily_limit_usd:
            return True
        if self.global_limit_usd is not None and everyone >= self.global_limit_usd:
            return True
        return self.parent is not None and self.parent.exhausted()

    def status(self) -> dict[str, Any]:
        root = self.parent or self
        source, today, everyone = root._totals()
        return {
            "spent_usd": round(source, 4), "limit_usd": root.limit_usd,
            "today_usd": round(today, 4), "daily_limit_usd": root.daily_limit_usd,
            "all_sources_usd": round(everyone, 4), "global_limit_usd": root.global_limit_usd,
            "durable": root.ledger is not None, "exhausted": self.exhausted(),
        }


class Reply(BaseModel):
    conversation_id: str
    text: str
    language: str
    state: State
    action: str
    ask_for: list[str] = Field(default_factory=list)
    candidates: list[dict[str, str]] = Field(default_factory=list)
    offer_block_card: bool = False
    case_id: str | None = None
    card_status: str | None = None
    handoff: HandoffPackage | None = None
    policy: PolicyDecision | None = None  # the rule that decided this turn, shown as "why" in the app
    injection_flags: list[str] = Field(default_factory=list)
    pii_redacted: list[str] = Field(default_factory=list)
    nlu: NluResult | None = None
    usage: LlmUsage | None = None
    nlu_mode: str = "none"  # "claude" | "rules" | "none" (no interpretation needed this turn)
    latency_ms: float = 0.0
    # The case as it stands after this turn (charge from bank records, reason and evidence read so far).
    draft: dict[str, Any] = Field(default_factory=dict)


@dataclass
class Conversation:
    id: str
    flow: DisputeFlow
    language: str = "es"
    proactive_txn: Transaction | None = None
    candidates: list[dict[str, str]] = field(default_factory=list)
    last_ask: list[str] = field(default_factory=list)
    block_offered: bool = False  # the last summary also asked whether to block the card
    history: list[str] = field(default_factory=list)
    usages: list[LlmUsage] = field(default_factory=list)
    customer_turns: int = 0
    out_of_scope_streak: int = 0
    proactive_unclear: int = 0


def _draft(flow: DisputeFlow) -> dict[str, Any]:
    return {
        "transaction": _candidate(flow.txn) if flow.txn else None,
        "reason_code": flow.reason_code.value if flow.reason_code else None,
        "evidence": dict(flow.evidence),
        "channel": flow.channel.value,
    }


def _candidate(t: Transaction) -> dict[str, str]:
    return {
        "transaction_id": t.transaction_id, "merchant": t.merchant_name or "", "amount": str(t.amount),
        "currency": t.currency, "date": t.transaction_date.strftime("%Y-%m-%d %H:%M"),
    }


class ConversationService:
    def __init__(
        self,
        *,
        tools: BankingTools,
        store: Store,
        policy: PolicyEngine,
        nlu: Nlu,
        breaker: CircuitBreaker,
        clock: Callable[[], datetime],
        sleep: Callable[[float], None] = time.sleep,
        fallback: Nlu | None = None,
        budget: Budget | None = None,
    ) -> None:
        self.tools, self.store, self.policy, self.nlu = tools, store, policy, nlu
        self.breaker, self.clock, self.sleep = breaker, clock, sleep
        # Free rule-based NLU used when the model fails, its circuit is open or the spend cap is reached.
        self.fallback, self.budget = fallback, budget or Budget(None)
        self.simulated_outage = False  # demo control: behave as if the model were down
        self.conversations: dict[str, Conversation] = {}

    def nlu_status(self) -> dict[str, Any]:
        """What the next turn will use, for the UI and /health."""
        primary = getattr(self.nlu, "mode", "claude")
        if primary == "claude" and self.fallback is not None:
            if self.simulated_outage:
                return {"mode": "rules", "reason": "simulated_outage", "fallback": True}
            if self._over_budget():
                return {"mode": "rules", "reason": "llm_budget_reached", "fallback": True}
            if not self.breaker.allow():
                return {"mode": "rules", "reason": "model_unavailable", "fallback": True}
        return {"mode": primary, "reason": None, "fallback": self.fallback is not None}

    def _over_budget(self) -> bool:
        return self.budget.exhausted()

    # ---- lifecycle ----------------------------------------------------------------------
    def _new(self, channel: Channel, language: str) -> Conversation:
        cid = f"conv-{uuid.uuid4().hex[:12]}"
        flow = DisputeFlow(
            tools=self.tools, store=self.store, policy=self.policy, clock=self.clock,
            trace_id=cid, channel=channel, language=language, sleep=self.sleep,
        )
        conv = Conversation(id=cid, flow=flow, language=language)
        self.conversations[cid] = conv
        return conv

    def start(self, language: str = "es") -> str:
        return self._new(Channel.CHAT, language).id

    def start_proactive(self, token: str, transaction_id: str, language: str = "es") -> tuple[str, str]:
        txn = self.tools.get_transaction(token, transaction_id)  # ownership enforced by the tool layer
        conv = self._new(Channel.PROACTIVE, language)
        conv.proactive_txn = txn
        opening = responses.proactive_prompt(txn, language)
        self._audit(conv, "proactive_alert", transaction_id=transaction_id, fraud_score=str(txn.fraud_score))
        conv.history.append(f"bank: {opening}")
        return conv.id, opening

    def start_from_purchase(self, token: str, transaction_id: str, language: str = "es") -> Reply:
        """The customer tapped "I don't recognise this" on a purchase in the app: the transaction is already
        known (ownership checked by the tool layer), so the conversation starts at the reason question."""
        started = time.perf_counter()
        txn = self.tools.get_transaction(token, transaction_id)
        conv = self._new(Channel.CHAT, language)
        self._audit(conv, "started_from_purchase", transaction_id=transaction_id)
        result = conv.flow.handle(Turn(token=token, transaction_id=transaction_id))
        return self._reply(conv, result, started, prefix=responses.purchase_intro(txn, language))

    def get(self, conversation_id: str) -> Conversation:
        return self.conversations[conversation_id]

    def metrics(self, conversation_id: str) -> dict[str, Any]:
        u = self.get(conversation_id).usages
        return {
            "llm_calls": len(u),
            "cost_usd": sum(x.cost_usd for x in u),
            "llm_latency_ms": [x.latency_ms for x in u],
        }

    # ---- one turn ---------------------------------------------------------------------------
    def send(self, conversation_id: str, token: str, text: str) -> Reply:
        started = time.perf_counter()
        conv = self.get(conversation_id)
        flow = conv.flow

        redacted, pii = redact_pii(text)
        flags = detect_injection(text)
        # The language is chosen at the start; only the customer's first message may change it (they write in the
        # language they read). Later switches, e.g. a mixed-language "sim", do not flip the replies.
        first_turn = conv.customer_turns == 0
        conv.customer_turns += 1
        if first_turn:
            self._set_language(conv, detect_language(text))
        self._audit(conv, "customer_message", text=redacted, pii=pii, injection_flags=flags)
        conv.history.append(f"customer: {redacted}")
        base = {"pii_redacted": pii, "injection_flags": flags}

        try:  # authenticate before spending a model call
            self.tools.sessions.verify(token)
        except Exception:
            return self._reply(conv, flow.handle(Turn(token=token)), started, **base)
        if flow.state in {State.DONE, State.INELIGIBLE, State.HANDOFF, State.CANCELLED}:
            return self._reply(conv, flow.handle(Turn(token=token)), started, text_key="ended", **base)

        ctx = NluContext(
            state=("PROACTIVE_CONFIRM" if conv.proactive_txn else flow.state.value),
            ask_for=conv.last_ask, candidates=conv.candidates or _confirm_context(flow), injection_flags=flags,
            history=conv.history,
            today=self.clock().date().isoformat(),
        )
        outcome: NluOutcome | None = None
        mode = "claude"
        if self.simulated_outage and self.fallback is not None:
            reason = "simulated_outage"
        elif self._over_budget() and self.fallback is not None:
            reason = "llm_budget_reached"
        elif not self.breaker.allow():
            if self.fallback is None:
                return self._reply(conv, flow.escalate(["nlu_unavailable"]), started, **base)
            reason = "model_unavailable"
        else:
            reason = None
            try:
                outcome = self.nlu.interpret(redacted, ctx)
                self.breaker.record_success()
            except NluUnavailable as e:
                self.breaker.record_failure()
                self._audit(conv, "nlu_failed", error=str(e), breaker_open=not self.breaker.allow())
                if self.fallback is None:
                    if not self.breaker.allow():
                        return self._reply(conv, flow.escalate(["nlu_unavailable"]), started, **base)
                    return self._text_reply(conv, "retry", started, **base)
                reason = "model_unavailable"
        if outcome is None:
            assert self.fallback is not None
            outcome = self.fallback.interpret(redacted, ctx)
            mode = "rules"
            self._audit(conv, "nlu_fallback", reason=reason)
        nlu, usage = outcome.result, outcome.usage
        if mode == "claude":
            nlu = self._ground(conv, nlu, ctx)
        if nlu.intent != "human" and detect_human_request(text):
            # An explicit request for a person outranks the reading, even next to a yes (ADR-027).
            self._audit(conv, "human_request_rule", nlu_intent=nlu.intent)
            nlu = nlu.model_copy(update={"intent": "human"})
        if is_rules_model(usage.model):
            mode = "rules"
        self.budget.add(usage.cost_usd)
        conv.usages.append(usage)
        if first_turn:
            self._set_language(conv, nlu.language)
        self._audit(conv, "nlu", result=nlu.model_dump(mode="json"), usage=usage.model_dump(mode="json"),
                    classifier=outcome.classifier)
        base.update(nlu=nlu, usage=usage, nlu_mode=mode)

        if conv.proactive_txn is not None:
            return self._proactive_turn(conv, token, nlu, started, base)
        if nlu.transaction_id is None and flow.state in {State.START, State.IDENTIFY_TXN} and (typed := _TXN_ID.findall(text)):
            # An id the customer typed goes to the tools, which check who owns it. The model leaves it out when it is
            # not among the candidates, so another customer's id never reached the check and repeated attempts were
            # not handed off as suspicious (demo, 2026-10-05).
            self._audit(conv, "typed_reference", transaction_id=typed[0].upper())
            nlu = nlu.model_copy(update={"transaction_id": typed[0].upper()})
        if nlu.intent == "out_of_scope":
            conv.out_of_scope_streak += 1
            if conv.out_of_scope_streak >= 2:  # a second unrelated request: redirect and end instead of looping
                return self._reply(conv, flow.close("out_of_scope_repeated"), started, text_key="goodbye_redirect", **base)
            return self._text_reply(conv, "out_of_scope", started, **base)
        after_out_of_scope = conv.out_of_scope_streak > 0
        conv.out_of_scope_streak = 0
        no_cues = not (nlu.reason_code or nlu.merchant or nlu.amount is not None or nlu.transaction_id)
        if after_out_of_scope and no_cues and nlu.intent in ("decline", "greeting", "unclear") and flow.state == State.START:
            # "Ok, gracias, hasta luego" after being told the request is not handled here ends the conversation.
            return self._reply(conv, flow.close("out_of_scope_accepted"), started, text_key="goodbye_redirect", **base)
        if nlu.intent == "decline" and flow.state in {State.START, State.IDENTIFY_TXN} and not (
                conv.candidates and nlu.wrong_transaction):
            # "No, nothing to dispute" before a charge was chosen ends the conversation politely.
            return self._reply(conv, flow.close("customer_has_nothing_to_dispute"), started, text_key="goodbye", **base)
        if nlu.intent == "greeting" and flow.state == State.START:
            return self._text_reply(conv, "greeting", started, **base)
        if (flow.state == State.CONFIRM and conv.block_offered and nlu.intent == "decline"
                and BARE_NO.fullmatch(_norm(text).strip(" .!"))):
            # The summary ends with "do you want the card blocked?": a bare "no" may answer only that. Ask, bounded
            # like any unclear answer to the summary; "não, cancelar" or the buttons still cancel.
            self._audit(conv, "ambiguous_no")
            return self._reply(conv, flow.handle(Turn(token=token)), started,
                               prefix=responses.message("ambiguous_no", conv.language), **base)
        return self._reply(conv, flow.handle(self._turn(conv, token, nlu)), started, **base)

    # ---- helpers ------------------------------------------------------------------------------
    def _ground(self, conv: Conversation, nlu: NluResult, ctx: NluContext) -> NluResult:
        """A fact the policy relies on must have been said. The model filled "card in possession: yes" from an opening
        that never mentioned the card (hard-v1 API run), so the question was skipped and a stolen card was opened as
        card-not-present fraud. Keep the reading only if the question was just asked or the customer's own words
        mention where the card is; otherwise the flow asks."""
        if nlu.card_in_possession is None or "card_in_possession" in ctx.ask_for:
            return nlu
        said = " ".join(_norm(h) for h in conv.history if h.startswith("customer: "))
        if POSSESSION_CUES.search(said):
            return nlu
        self._audit(conv, "ungrounded_evidence_dropped", field="card_in_possession", value=nlu.card_in_possession)
        return nlu.model_copy(update={"card_in_possession": None})

    def _turn(self, conv: Conversation, token: str, nlu: NluResult) -> Turn:
        in_confirm = conv.flow.state == State.CONFIRM
        evidence = nlu.evidence()
        transaction_id = nlu.transaction_id
        if ("duplicate_transaction_id" in conv.last_ask and not evidence.get("duplicate_transaction_id")
                and transaction_id in {c["transaction_id"] for c in conv.candidates}):
            # The pick buttons send "É a compra <id>"; read as the charge itself, it is the other charge asked for.
            evidence["duplicate_transaction_id"], transaction_id = transaction_id, None
        return Turn(
            token=token,
            summary=nlu.summary or None,
            transaction_id=transaction_id,
            merchant=nlu.merchant,
            amount=None if nlu.amount is None else Decimal(str(nlu.amount)),
            reason_code=nlu.reason_code,
            classifier_confidence=nlu.reason_confidence if nlu.reason_code else None,
            evidence=evidence,
            confirm=(True if nlu.intent == "confirm" else False if nlu.intent == "decline" else None) if in_confirm else None,
            block_card=bool(nlu.wants_block_card) if in_confirm else False,
            human_requested=nlu.intent == "human",
            very_negative_sentiment=nlu.very_negative_sentiment,
            regulatory_threat=nlu.regulatory_threat,
            purchase_date=_iso_date(nlu.purchase_date),
            wrong_transaction=nlu.wrong_transaction and (in_confirm or bool(conv.candidates)),
        )

    def _proactive_turn(self, conv: Conversation, token: str, nlu: NluResult, started: float, base: dict) -> Reply:
        txn = conv.proactive_txn
        assert txn is not None
        if nlu.intent == "human":
            conv.proactive_txn = None
            return self._reply(conv, conv.flow.handle(Turn(token=token, human_requested=True)), started, **base)
        # The stated fact outranks the intent: the model read "Não fui eu" as intent "confirm" (confirming the no)
        # with recognizes_merchant "no" on the deployed API, and the alert was closed as recognised.
        recognized = nlu.recognizes_merchant == "yes" or (
            nlu.recognizes_merchant is None and nlu.intent == "confirm")
        if recognized:
            conv.proactive_txn = None
            conv.flow.txn, conv.flow.customer_id = txn, txn.customer_id  # the closed case shows the charge
            result = conv.flow.close("transaction_recognized")
            return self._reply(conv, result, started, text_key="recognized", **base)
        if nlu.intent in ("decline", "dispute") or nlu.recognizes_merchant == "no":
            conv.proactive_txn = None
            turn = Turn(
                token=token, transaction_id=txn.transaction_id, reason_code=ReasonCode.FRAUD_CNP,
                evidence={"recognizes_merchant": "no", **nlu.evidence()},
                summary=nlu.summary or "Customer did not recognise a transaction flagged by the fraud alert",
            )
            return self._reply(conv, conv.flow.handle(turn), started, **base)
        conv.proactive_unclear += 1
        if conv.proactive_unclear > 2:
            # Unsure three times: a person calls, with the flagged charge attached; nothing is opened or blocked.
            conv.proactive_txn = None
            flow = conv.flow
            flow.txn, flow.customer_id = txn, txn.customer_id
            flow.summary = "Customer could not say whether they made a charge flagged by the fraud alert"
            return self._reply(conv, flow.escalate(["clarification_exhausted"]), started, **base)
        return self._text_reply(conv, "proactive", started, override=responses.proactive_prompt(txn, conv.language), **base)

    def _reply(
        self, conv: Conversation, result: FlowResult, started: float, text_key: str | None = None,
        prefix: str | None = None, **extra: Any,
    ) -> Reply:
        flow = conv.flow
        text = (
            responses.message(text_key, conv.language) if text_key
            else responses.render(result, conv.language, transaction=flow.txn, reason=flow.reason_code)
        )
        if prefix:
            text = f"{prefix}\n{text}"
        conv.candidates = [_candidate(c) for c in result.candidates]
        conv.last_ask = list(result.ask_for)
        conv.block_offered = result.offer_block_card
        conv.history.append(f"bank: {text}")
        reply = Reply(
            conversation_id=conv.id, text=text, language=conv.language, state=result.state, action=result.action,
            ask_for=result.ask_for, candidates=conv.candidates, offer_block_card=result.offer_block_card,
            case_id=result.case.case_id if result.case else None,
            card_status=result.card.product_status if result.card else None,
            handoff=result.handoff, policy=result.policy, latency_ms=(time.perf_counter() - started) * 1000,
            draft=_draft(flow), **extra,
        )
        self._audit(conv, "reply", action=reply.action, state=reply.state, text=text, latency_ms=reply.latency_ms)
        return reply

    def _text_reply(self, conv: Conversation, key: str, started: float, override: str | None = None, **extra: Any) -> Reply:
        text = override or responses.message(key, conv.language)
        conv.history.append(f"bank: {text}")
        reply = Reply(
            conversation_id=conv.id, text=text, language=conv.language, state=conv.flow.state, action=key,
            candidates=conv.candidates, ask_for=conv.last_ask, latency_ms=(time.perf_counter() - started) * 1000,
            draft=_draft(conv.flow), **extra,
        )
        self._audit(conv, "reply", action=key, state=reply.state, text=text, latency_ms=reply.latency_ms)
        return reply

    @staticmethod
    def _set_language(conv: Conversation, language: str | None) -> None:
        if language in ("es", "pt"):
            conv.language = language
            conv.flow.language = language

    def _audit(self, conv: Conversation, kind: str, **data: Any) -> None:
        self.store.append_audit(AuditEvent(trace_id=conv.id, at=self.clock(), kind=kind, data=data))


def _iso_date(value: str | None) -> date | None:
    """The NLU's day estimate, if it is a real ISO date (anything else is ignored, never guessed)."""
    try:
        return date.fromisoformat(value[:10]) if value else None
    except ValueError:
        return None


def _confirm_context(flow: DisputeFlow) -> list[dict[str, str]]:
    """At the summary, the charges shown before stay readable, so "no, the one from February" can be understood."""
    if flow.state != State.CONFIRM or len(flow.last_candidates) < 2:
        return []
    return [_candidate(t) for t in flow.last_candidates]
