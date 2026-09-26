"""HTTP API. Customer endpoints authenticate with a session token; agent/ops endpoints require
an agent key. Neither role can reach the other's data paths."""


import json
import logging
import statistics
import time
import uuid
from collections import defaultdict, deque
from datetime import timedelta
from typing import Annotated, Any

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from dispute_ops.auth import AuthError
from dispute_ops.channels import PqrComplaint, run_pqr_complaint, select_fraud_alerts
from dispute_ops.container import Container
from dispute_ops.conversation import Reply
from dispute_ops.domain import ReasonCode
from dispute_ops.errors import AccessDenied, NotFound

log = logging.getLogger("dispute_ops.api")


class SessionRequest(BaseModel):
    customer_id: str
    ttl_seconds: int | None = Field(default=None, ge=1, le=3600)


class StartRequest(BaseModel):
    language: str = "es"


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


def _percentile(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    if len(values) == 1:
        return values[0]
    return statistics.quantiles(values, n=100, method="inclusive")[int(q) - 1]


def create_app(container: Container) -> FastAPI:
    app = FastAPI(title="LATAM Bank Dispute Ops", version="0.1.0")
    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
    limiter = RateLimiter(container.settings.rate_limit_per_minute)
    c = container

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

    def bearer(authorization: Annotated[str | None, Header()] = None) -> str:
        if not authorization or not authorization.startswith("Bearer "):
            raise HTTPException(401, "missing bearer token")
        return authorization.removeprefix("Bearer ")

    def agent(x_agent_key: Annotated[str | None, Header()] = None) -> None:
        if not x_agent_key or x_agent_key != c.settings.agent_api_key:
            raise HTTPException(401, "agent key required")

    Token = Annotated[str, Depends(bearer)]
    AgentOnly = Depends(agent)

    # ---- public / customer ---------------------------------------------------------------
    @app.get("/health")
    def health() -> dict[str, Any]:
        return {"status": "ok", "policy_version": c.policy.version, "now": c.clock().isoformat()}

    @app.get("/demo/customers")
    def demo_customers() -> list[dict[str, Any]]:
        rows = c.store.conn.execute("SELECT customer_id, country, segment FROM customers ORDER BY customer_id")
        return [dict(r) for r in rows]

    @app.post("/auth/session")
    def create_session(body: SessionRequest) -> dict[str, str]:
        """TEST identity provider: stands in for the bank's real login (documented limitation)."""
        if c.store.get_customer(body.customer_id) is None:
            raise HTTPException(404, "unknown demo customer")
        sessions = c.sessions
        if body.ttl_seconds:
            from dispute_ops.auth import SessionService

            sessions = SessionService(c.sessions.secret, timedelta(seconds=body.ttl_seconds), c.clock)
        return {"token": sessions.issue(body.customer_id)}

    @app.post("/conversations")
    def start_conversation(body: StartRequest | None = None) -> dict[str, str]:
        from dispute_ops.language.responses import message

        lang = (body or StartRequest()).language
        return {"conversation_id": c.conversations.start(lang), "text": message("greeting", lang)}

    @app.post("/conversations/{conversation_id}/messages")
    def send_message(conversation_id: str, body: MessageRequest, token: Token) -> Reply:
        if conversation_id not in c.conversations.conversations:
            raise HTTPException(404, "conversation not found")
        if not limiter.allow(token):
            raise HTTPException(429, "too many messages, slow down")
        return c.conversations.send(conversation_id, token, body.text)

    @app.get("/cases/{case_id}")
    def get_case(case_id: str, token: Token) -> dict[str, Any]:
        try:
            return c.tools.get_case_status(token, case_id).model_dump(mode="json")
        except AuthError:
            raise HTTPException(401, "invalid or expired session") from None
        except (AccessDenied, NotFound):
            raise HTTPException(404, "case not found") from None

    @app.post("/alerts/{transaction_id}/start")
    def start_alert(transaction_id: str, token: Token, body: StartRequest | None = None) -> dict[str, str]:
        try:
            cid, text = c.conversations.start_proactive(token, transaction_id, (body or StartRequest()).language)
        except AuthError:
            raise HTTPException(401, "invalid or expired session") from None
        except (AccessDenied, NotFound):
            raise HTTPException(404, "transaction not found") from None
        return {"conversation_id": cid, "text": text}

    # ---- agent / ops -----------------------------------------------------------------------
    @app.get("/agent/handoffs", dependencies=[AgentOnly])
    def handoffs() -> list[dict[str, Any]]:
        return [e.data for e in reversed(c.store.list_audit_by_kind("handoff"))]

    @app.get("/agent/traces/{trace_id}", dependencies=[AgentOnly])
    def trace(trace_id: str) -> list[dict[str, Any]]:
        return [e.model_dump(mode="json") for e in c.store.list_audit(trace_id)]

    @app.get("/agent/alerts", dependencies=[AgentOnly])
    def alerts() -> list[dict[str, Any]]:
        return [t.model_dump(mode="json") for t in select_fraud_alerts(
            c.store, c.clock, lookback_hours=c.settings.fraud_alert_lookback_hours)]

    @app.post("/agent/pqr/run", dependencies=[AgentOnly])
    def pqr_run(body: PqrRun) -> list[dict[str, Any]]:
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
    def metrics() -> dict[str, Any]:
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
            "actions_verified": sum(1 for e in actions if e.data["status"] == "verified"),
            "actions_failed": sum(1 for e in actions if e.data["status"] == "failed"),
            "llm_calls": len(nlu),
            "llm_cost_usd": round(sum(e.data["usage"]["cost_usd"] for e in nlu), 6),
            "latency_ms_p50": _percentile(latencies, 50),
            "latency_ms_p95": _percentile(latencies, 95),
        }

    return app
