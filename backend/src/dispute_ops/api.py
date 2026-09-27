"""HTTP API. Customer endpoints authenticate with a session token; agent/ops endpoints require
an agent key. Neither role can reach the other's data paths."""


import json
import logging
import re
import statistics
import time
import uuid
from collections import OrderedDict, defaultdict, deque
from collections.abc import Callable
from datetime import timedelta
from typing import Annotated, Any, Literal

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from dispute_ops.auth import AuthError
from dispute_ops.channels import PqrComplaint, run_pqr_complaint, select_fraud_alerts
from dispute_ops.container import Container
from dispute_ops.conversation import Reply
from dispute_ops.domain import AuditEvent, ReasonCode
from dispute_ops.errors import AccessDenied, NotFound
from dispute_ops.policy.engine import PolicyContext

log = logging.getLogger("dispute_ops.api")


class SessionRequest(BaseModel):
    customer_id: str
    ttl_seconds: int | None = Field(default=None, ge=1, le=3600)


class StartRequest(BaseModel):
    language: str = "es"
    transaction_id: str | None = Field(default=None, max_length=64)


class ResolveRequest(BaseModel):
    action: Literal["open_dispute", "close"]
    note: str = Field(default="", max_length=500)
    reason_code: ReasonCode | None = None


class MessageRequest(BaseModel):
    text: str = Field(min_length=1, max_length=2000)


class PqrItem(PqrComplaint):
    reason_code: ReasonCode | None = None
    classifier_confidence: float | None = None


class PqrRun(BaseModel):
    complaints: list[PqrItem] = Field(max_length=500)


class RateLimiter:
    def __init__(self, per_minute: int) -> None:
        self.per_minute = per_minute
        self.hits: dict[str, deque[float]] = defaultdict(deque)

    def allow(self, key: str) -> bool:
        now, window = time.monotonic(), self.hits[key]
        while window and now - window[0] > 60:
            window.popleft()
        if len(window) >= self.per_minute:
            return False
        window.append(now)
        return True


_WORKSPACE_ID = re.compile(r"^[A-Za-z0-9_-]{4,64}$")
DEMO_AGENT_ID = "agent-demo"  # the demo has no staff login; production would take the id from staff SSO


class Workspaces:
    """Per-visitor copies of the demo (store, conversations, queue), least-recently-used eviction."""

    def __init__(self, factory: Callable[[], Container], max_size: int = 40) -> None:
        self.factory, self.max_size = factory, max_size
        self.items: OrderedDict[str, Container] = OrderedDict()

    def get(self, key: str) -> Container:
        if key in self.items:
            self.items.move_to_end(key)
        else:
            self.items[key] = self.factory()
            while len(self.items) > self.max_size:
                self.items.popitem(last=False)
        return self.items[key]

    def reset(self, key: str) -> None:
        self.items.pop(key, None)


def _percentile(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    if len(values) == 1:
        return values[0]
    return statistics.quantiles(values, n=100, method="inclusive")[int(q) - 1]


def create_app(container: Container, workspace_factory: Callable[[], Container] | None = None) -> FastAPI:
    app = FastAPI(title="LATAM Bank Dispute Ops", version="0.2.0")
    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
    limiter = RateLimiter(container.settings.rate_limit_per_minute)
    demo = container.settings.demo_mode
    workspaces = Workspaces(workspace_factory) if demo and workspace_factory else None

    @app.middleware("http")
    async def request_log(request: Request, call_next):  # structured access log + request id
        request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex[:16]
        started = time.perf_counter()
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        log.info(json.dumps({
            "request_id": request_id, "method": request.method, "path": request.url.path,
            "status": response.status_code, "ms": round((time.perf_counter() - started) * 1000, 1),
        }))
        return response

    def ctr(x_demo_workspace: Annotated[str | None, Header()] = None) -> Container:
        if workspaces is None or not x_demo_workspace:
            return container
        if not _WORKSPACE_ID.match(x_demo_workspace):
            raise HTTPException(400, "invalid workspace id")
        return workspaces.get(x_demo_workspace)

    def bearer(authorization: Annotated[str | None, Header()] = None) -> str:
        if not authorization or not authorization.startswith("Bearer "):
            raise HTTPException(401, "missing bearer token")
        return authorization.removeprefix("Bearer ")

    def optional_bearer(authorization: Annotated[str | None, Header()] = None) -> str | None:
        return authorization.removeprefix("Bearer ") if authorization and authorization.startswith("Bearer ") else None

    def agent(x_agent_key: Annotated[str | None, Header()] = None) -> None:
        if demo:  # judges have no staff login; the demo only holds synthetic data
            return
        if not x_agent_key or x_agent_key != container.settings.agent_api_key:
            raise HTTPException(401, "agent key required")

    C = Annotated[Container, Depends(ctr)]
    Token = Annotated[str, Depends(bearer)]
    AgentOnly = Depends(agent)

    def customer_call(fn: Callable[[], Any]) -> Any:
        try:
            return fn()
        except AuthError:
            raise HTTPException(401, "invalid or expired session") from None
        except (AccessDenied, NotFound):  # same answer for "not yours" and "does not exist"
            raise HTTPException(404, "not found") from None

    # ---- public / customer ---------------------------------------------------------------
    @app.get("/health")
    def health(c: C) -> dict[str, Any]:
        return {"status": "ok", "policy_version": c.policy.version, "now": c.clock().isoformat(),
                "demo_mode": demo, "nlu": c.conversations.nlu_status()}

    @app.get("/demo/customers")
    def demo_customers(c: C) -> list[dict[str, Any]]:
        rows = c.store.conn.execute("SELECT customer_id, first_name, country, segment FROM customers ORDER BY customer_id")
        return [dict(r) for r in rows]

    @app.get("/demo/scenarios")
    def demo_scenarios(c: C) -> list[dict[str, Any]]:
        path = c.settings.resolved_scenarios_path()
        return json.loads(path.read_text()) if path.exists() else []

    @app.post("/demo/reset")
    def demo_reset(x_demo_workspace: Annotated[str | None, Header()] = None) -> dict[str, str]:
        if workspaces is None:
            raise HTTPException(404, "not available")
        if not x_demo_workspace or not _WORKSPACE_ID.match(x_demo_workspace):
            raise HTTPException(400, "workspace id required")
        workspaces.reset(x_demo_workspace)
        return {"status": "reset"}

    @app.post("/auth/session")
    def create_session(body: SessionRequest, c: C) -> dict[str, str]:
        """TEST identity provider: stands in for the bank's real login (documented limitation)."""
        if c.store.get_customer(body.customer_id) is None:
            raise HTTPException(404, "unknown demo customer")
        sessions = c.sessions
        if body.ttl_seconds:
            from dispute_ops.auth import SessionService

            sessions = SessionService(c.sessions.secret, timedelta(seconds=body.ttl_seconds), c.clock)
        return {"token": sessions.issue(body.customer_id)}

    @app.get("/me")
    def me(token: Token, c: C) -> dict[str, Any]:
        profile = customer_call(lambda: c.tools.get_profile(token))
        cards = customer_call(lambda: c.tools.list_cards(token))
        return {
            "customer_id": profile.customer_id, "first_name": profile.first_name, "country": profile.country,
            "segment": profile.segment, "cards": [card.model_dump(exclude={"customer_id"}) for card in cards],
        }

    @app.get("/me/transactions")
    def my_transactions(token: Token, c: C) -> list[dict[str, Any]]:
        txns = customer_call(lambda: c.tools.search_transactions(token, days=120))[:40]
        open_cases = {k.transaction_id: k.case_id for k in customer_call(lambda: c.tools.list_cases(token))
                      if k.status == "Open"}
        return [{**t.model_dump(mode="json", exclude={"customer_id", "fraud_score"}),
                 "case_id": open_cases.get(t.transaction_id)} for t in txns]

    @app.get("/me/cases")
    def my_cases(token: Token, c: C) -> list[dict[str, Any]]:
        out = []
        for case in customer_call(lambda: c.tools.list_cases(token)):
            txn = customer_call(lambda case=case: c.tools.get_transaction(token, case.transaction_id))
            out.append({
                **case.model_dump(mode="json", exclude={"customer_id", "evidence"}),
                "opened_by": "agent" if case.evidence.get("opened_by", "").startswith("agent:") else "assistant",
                "merchant_name": txn.merchant_name, "amount": str(txn.amount), "currency": txn.currency,
                "transaction_date": txn.transaction_date.isoformat(),
            })
        return out

    @app.get("/me/alerts")
    def my_alerts(token: Token, c: C) -> list[dict[str, Any]]:
        customer_id = customer_call(lambda: c.tools.get_profile(token)).customer_id
        found = select_fraud_alerts(c.store, c.clock, lookback_hours=c.settings.fraud_alert_lookback_hours)
        return [t.model_dump(mode="json", exclude={"customer_id"}) for t in found if t.customer_id == customer_id]

    @app.post("/conversations")
    def start_conversation(
        c: C, body: StartRequest | None = None, token: Annotated[str | None, Depends(optional_bearer)] = None,
    ) -> dict[str, Any]:
        from dispute_ops.language.responses import message

        body = body or StartRequest()
        if body.transaction_id:
            if token is None:
                raise HTTPException(401, "missing bearer token")
            reply = customer_call(lambda: c.conversations.start_from_purchase(token, body.transaction_id, body.language))
            return {"conversation_id": reply.conversation_id, "text": reply.text, "reply": reply}
        return {"conversation_id": c.conversations.start(body.language), "text": message("greeting", body.language),
                "reply": None}

    @app.post("/conversations/{conversation_id}/messages")
    def send_message(conversation_id: str, body: MessageRequest, token: Token, c: C) -> Reply:
        if conversation_id not in c.conversations.conversations:
            raise HTTPException(404, "conversation not found")
        if not limiter.allow(token):
            raise HTTPException(429, "too many messages, slow down")
        return c.conversations.send(conversation_id, token, body.text)

    @app.get("/cases/{case_id}")
    def get_case(case_id: str, token: Token, c: C) -> dict[str, Any]:
        return customer_call(lambda: c.tools.get_case_status(token, case_id)).model_dump(mode="json")

    @app.post("/alerts/{transaction_id}/start")
    def start_alert(transaction_id: str, token: Token, c: C, body: StartRequest | None = None) -> dict[str, str]:
        cid, text = customer_call(
            lambda: c.conversations.start_proactive(token, transaction_id, (body or StartRequest()).language))
        return {"conversation_id": cid, "text": text}

    # ---- agent / ops -----------------------------------------------------------------------
    def _resolutions(c: Container) -> dict[str, dict[str, Any]]:
        return {e.data["case_ref"]: {**e.data, "at": e.at.isoformat()} for e in c.store.list_audit_by_kind("agent_action")}

    @app.get("/agent/handoffs", dependencies=[AgentOnly])
    def handoffs(c: C) -> list[dict[str, Any]]:
        done = _resolutions(c)
        out = []
        for e in reversed(c.store.list_audit_by_kind("handoff")):
            resolution = done.get(e.data["case_ref"])
            status = "new" if resolution is None else ("resolved" if resolution["action"] == "open_dispute" else "closed")
            out.append({**e.data, "at": e.at.isoformat(), "status": status, "resolution": resolution})
        return out

    @app.post("/agent/handoffs/{case_ref}/resolve", dependencies=[AgentOnly])
    def resolve_handoff(case_ref: str, body: ResolveRequest, c: C) -> dict[str, Any]:
        event = next((e for e in c.store.list_audit_by_kind("handoff") if e.data["case_ref"] == case_ref), None)
        if event is None:
            raise HTTPException(404, "handoff not found")
        if case_ref in _resolutions(c):
            raise HTTPException(409, "handoff already resolved")
        pkg = event.data

        def record(**data: Any) -> None:
            c.store.append_audit(AuditEvent(trace_id=pkg["trace_id"], at=c.clock(), kind="agent_action",
                                            data={"case_ref": case_ref, "agent_id": DEMO_AGENT_ID, "note": body.note, **data}))

        if body.action == "close":
            record(action="close")
            return {"status": "closed"}
        reason = body.reason_code or pkg.get("proposed_reason_code")
        txn = c.store.get_transaction(pkg["transaction_id"]) if pkg.get("transaction_id") else None
        customer = c.store.get_customer(pkg["customer_id"]) if pkg.get("customer_id") else None
        if txn is None or customer is None or txn.customer_id != customer.customer_id:
            raise HTTPException(409, "the handoff has no verified transaction; ask the customer first")
        if reason is None:
            raise HTTPException(422, "choose a dispute reason")
        open_case = c.store.find_open_dispute(txn.transaction_id)
        decision = c.policy.evaluate_human_review(PolicyContext(
            transaction=txn, customer=customer, reason_code=ReasonCode(reason), now=c.clock(),
            open_dispute_case_id=open_case.case_id if open_case else None,
            disputes_last_30d=c.store.count_disputes_since(customer.customer_id, c.clock() - timedelta(days=30)),
        ))
        if decision.decision == "ineligible":
            raise HTTPException(409, {"message": "not eligible", "rule_ids": decision.rule_ids,
                                      "inputs": decision.inputs})
        case = c.tools.open_dispute_as_agent(DEMO_AGENT_ID, customer.customer_id, txn.transaction_id, ReasonCode(reason),
                                             {"agent_note": body.note}, idempotency_key=f"{case_ref}:open")
        stored = c.store.get_dispute(case.case_id)
        verified = stored is not None and stored.status == "Open"  # read back before reporting it as done
        record(action="open_dispute", case_id=case.case_id, verified=verified,
               decision=decision.model_dump(mode="json"))
        if not verified:
            raise HTTPException(500, "the dispute could not be verified")
        return {"status": "resolved", "case_id": case.case_id, "decision": decision.model_dump(mode="json")}

    @app.get("/agent/traces/{trace_id}", dependencies=[AgentOnly])
    def trace(trace_id: str, c: C) -> list[dict[str, Any]]:
        return [e.model_dump(mode="json") for e in c.store.list_audit(trace_id)]

    @app.get("/agent/alerts", dependencies=[AgentOnly])
    def alerts(c: C) -> list[dict[str, Any]]:
        return [t.model_dump(mode="json") for t in select_fraud_alerts(
            c.store, c.clock, lookback_hours=c.settings.fraud_alert_lookback_hours)]

    @app.post("/agent/pqr/run", dependencies=[AgentOnly])
    def pqr_run(body: PqrRun, c: C) -> list[dict[str, Any]]:
        out = []
        for item in body.complaints:
            r = run_pqr_complaint(
                PqrComplaint(**item.model_dump(exclude={"reason_code", "classifier_confidence"})),
                reason_code=item.reason_code, classifier_confidence=item.classifier_confidence,
                tools=c.tools, store=c.store, policy=c.policy, sessions=c.sessions, clock=c.clock,
                sleep=c.conversations.sleep,
            )
            out.append({
                "complaint_id": item.complaint_id, "action": r.action, "state": r.state,
                "case_id": r.case.case_id if r.case else None,
                "handoff_reasons": r.handoff.reason_for_handoff if r.handoff else [],
                "rule_ids": r.policy.rule_ids if r.policy else [],
                "candidate_transactions": (r.handoff.risk_signals.get("candidate_transactions", []) if r.handoff else []),
            })
        return out

    @app.get("/agent/metrics", dependencies=[AgentOnly])
    def metrics(c: C) -> dict[str, Any]:
        replies = c.store.list_audit_by_kind("reply")
        nlu = c.store.list_audit_by_kind("nlu")
        actions = c.store.list_audit_by_kind("action")
        latencies = [e.data["latency_ms"] for e in replies]
        by_action: dict[str, int] = defaultdict(int)
        for e in replies:
            by_action[e.data["action"]] += 1
        handoff_reasons: dict[str, int] = defaultdict(int)
        for e in c.store.list_audit_by_kind("handoff"):
            for reason in e.data["reason_for_handoff"]:
                handoff_reasons[reason] += 1
        return {
            "replies": len(replies),
            "replies_by_action": dict(by_action),
            "handoffs": sum(1 for e in c.store.list_audit_by_kind("handoff")),
            "handoff_reasons": dict(handoff_reasons),
            "agent_actions": len(c.store.list_audit_by_kind("agent_action")),
            "actions_verified": sum(1 for e in actions if e.data["status"] == "verified"),
            "actions_failed": sum(1 for e in actions if e.data["status"] == "failed"),
            "llm_calls": sum(1 for e in nlu if e.data["usage"]["model"] != "rules"),
            "rule_nlu_turns": sum(1 for e in nlu if e.data["usage"]["model"] == "rules"),
            "llm_cost_usd": round(sum(e.data["usage"]["cost_usd"] for e in nlu), 6),
            "latency_ms_p50": _percentile(latencies, 50),
            "latency_ms_p95": _percentile(latencies, 95),
            "nlu": c.conversations.nlu_status(),
        }

    return app
