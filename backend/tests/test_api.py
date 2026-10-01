from fastapi.testclient import TestClient

from dispute_ops.api import create_app
from dispute_ops.container import Container, Settings
from dispute_ops.domain import ReasonCode
from helpers import SEED
from nlu_fakes import ScriptedNlu, nlu_result

AGENT = {"X-Agent-Key": "agent-test-key"}


def make_client(*nlu_results, rate_limit_per_minute=30):
    settings = Settings(
        seed_path=str(SEED), session_secret="s", agent_api_key="agent-test-key",
        demo_now="2026-06-17T12:00:00+00:00", rate_limit_per_minute=rate_limit_per_minute,
    )
    container = Container.build(settings, nlu=ScriptedNlu(*nlu_results), sleep=lambda s: None)
    return TestClient(create_app(container)), container


def login(client, customer_id="CUST001", **kw):
    r = client.post("/auth/session", json={"customer_id": customer_id, **kw})
    assert r.status_code == 200
    return {"Authorization": f"Bearer {r.json()['token']}"}


def test_health_and_demo_customers():
    client, _ = make_client()
    assert client.get("/health").json()["status"] == "ok"
    ids = [c["customer_id"] for c in client.get("/demo/customers").json()]
    assert ids == ["CUST001", "CUST002"]


def test_full_conversation_over_http():
    client, _ = make_client(
        nlu_result(intent="dispute", language="pt", transaction_id=None, amount=1250,
                   reason_code=ReasonCode.FRAUD_CNP, reason_confidence=0.9,
                   card_in_possession="yes", recognizes_merchant="no"),
        nlu_result(intent="confirm", language="pt", wants_block_card=True),
    )
    auth = login(client)
    cid = client.post("/conversations", json={"language": "pt"}).json()["conversation_id"]
    r1 = client.post(f"/conversations/{cid}/messages", json={"text": "não reconheço 1250, o cartão está comigo"}, headers=auth).json()
    assert r1["action"] == "confirm"
    r2 = client.post(f"/conversations/{cid}/messages", json={"text": "sim, bloqueia"}, headers=auth).json()
    assert r2["action"] == "done" and r2["card_status"] == "Blocked"
    case = client.get(f"/cases/{r2['case_id']}", headers=auth).json()
    assert case["status"] == "Open" and case["transaction_id"] == "TXN001"


def test_message_without_token_is_401_and_bad_token_asks_reauth():
    client, _ = make_client()
    cid = client.post("/conversations", json={}).json()["conversation_id"]
    assert client.post(f"/conversations/{cid}/messages", json={"text": "hola"}).status_code == 401
    r = client.post(f"/conversations/{cid}/messages", json={"text": "hola"}, headers={"Authorization": "Bearer x.y"})
    assert r.status_code == 200 and r.json()["action"] == "reauth"


def test_unknown_conversation_is_404():
    client, _ = make_client()
    r = client.post("/conversations/nope/messages", json={"text": "x"}, headers=login(client))
    assert r.status_code == 404


def test_customer_cannot_read_another_customers_case():
    client, container = make_client(
        nlu_result(intent="dispute", transaction_id="TXN001", reason_code=ReasonCode.FRAUD_CNP,
                   reason_confidence=0.9, card_in_possession="yes", recognizes_merchant="no"),
        nlu_result(intent="confirm"),
    )
    auth = login(client)
    cid = client.post("/conversations", json={}).json()["conversation_id"]
    client.post(f"/conversations/{cid}/messages", json={"text": "x"}, headers=auth)
    case_id = client.post(f"/conversations/{cid}/messages", json={"text": "sí"}, headers=auth).json()["case_id"]
    assert client.get(f"/cases/{case_id}", headers=login(client, "CUST002")).status_code == 404


def test_agent_endpoints_require_agent_key():
    client, _ = make_client()
    assert client.get("/agent/handoffs").status_code == 401
    assert client.get("/agent/handoffs", headers={"X-Agent-Key": "wrong"}).status_code == 401
    assert client.get("/agent/handoffs", headers=AGENT).status_code == 200


def test_handoff_appears_in_agent_queue_with_trace():
    client, _ = make_client(nlu_result(intent="human", summary="Quiere hablar con una persona"))
    auth = login(client)
    cid = client.post("/conversations", json={}).json()["conversation_id"]
    client.post(f"/conversations/{cid}/messages", json={"text": "quiero un humano"}, headers=auth)
    queue = client.get("/agent/handoffs", headers=AGENT).json()
    assert queue[0]["trace_id"] == cid and queue[0]["reason_for_handoff"] == ["customer_requested_human"]
    trace = client.get(f"/agent/traces/{cid}", headers=AGENT).json()
    assert [e["kind"] for e in trace][:2] == ["customer_message", "nlu"]


def test_proactive_alerts_scan_and_start():
    client, _ = make_client(nlu_result(intent="confirm"))
    alerts = client.get("/agent/alerts", headers=AGENT).json()
    assert [a["transaction_id"] for a in alerts] == ["TXN005", "TXN007"]
    auth = login(client)
    started = client.post("/alerts/TXN007/start", json={"language": "es"}, headers=auth).json()
    assert "TiendaXYZ Online" in started["text"]
    r = client.post(f"/conversations/{started['conversation_id']}/messages", json={"text": "sí fui yo"}, headers=auth)
    assert r.json()["action"] == "cancelled"


def test_proactive_start_for_other_customers_transaction_is_404():
    client, _ = make_client()
    assert client.post("/alerts/TXN007/start", json={}, headers=login(client, "CUST002")).status_code == 404


def test_pqr_batch_triage():
    client, _ = make_client()
    body = {"complaints": [
        {"complaint_id": "Q1", "customer_id": "CUST001", "transaction_id": "TXN003", "description": "doble cobro",
         "evidence": {"duplicate_transaction_id": "TXN002"}, "reason_code": "DUPLICATE", "classifier_confidence": 0.95},
        {"complaint_id": "Q2", "customer_id": "CUST001", "transaction_id": "TXN001", "description": "cobro raro",
         "reason_code": "FRAUD_CNP", "classifier_confidence": 0.9},
    ]}
    results = client.post("/agent/pqr/run", json=body, headers=AGENT).json()
    assert [r["action"] for r in results] == ["done", "handoff"]


def test_metrics_summarise_outcomes_cost_and_latency():
    client, _ = make_client(nlu_result(intent="human"))
    auth = login(client)
    cid = client.post("/conversations", json={}).json()["conversation_id"]
    client.post(f"/conversations/{cid}/messages", json={"text": "humano"}, headers=auth)
    m = client.get("/agent/metrics", headers=AGENT).json()
    assert m["replies"] == 1 and m["handoffs"] == 1 and m["llm_calls"] == 1
    assert m["llm_cost_usd"] > 0 and m["latency_ms_p50"] >= 0


def test_rate_limit_per_session():
    client, _ = make_client(*[nlu_result(intent="greeting")] * 5, rate_limit_per_minute=2)
    auth = login(client)
    cid = client.post("/conversations", json={}).json()["conversation_id"]
    codes = [client.post(f"/conversations/{cid}/messages", json={"text": "hola"}, headers=auth).status_code for _ in range(3)]
    assert codes == [200, 200, 429]


def test_short_ttl_session_for_expiry_demo():
    client, container = make_client()
    auth = login(client, ttl_seconds=1)
    container.clock.advance(seconds=5)
    cid = client.post("/conversations", json={}).json()["conversation_id"]
    r = client.post(f"/conversations/{cid}/messages", json={"text": "hola"}, headers=auth)
    assert r.json()["action"] == "reauth"
