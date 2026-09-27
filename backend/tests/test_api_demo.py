"""v0.0.2: customer app reads, conversations started from a purchase, demo workspaces and the agent queue."""

from fastapi.testclient import TestClient

from dispute_ops.api import create_app
from dispute_ops.container import Container, Settings
from dispute_ops.language.rule_nlu import RuleNlu
from helpers import SEED

SCENARIOS = str(SEED.parent / "scenarios.json")


def make_client(*, demo_mode=True, nlu=None):
    settings = Settings(
        seed_path=str(SEED), session_secret="s", agent_api_key="agent-test-key", demo_now="2026-06-17T12:00:00+00:00",
        demo_mode=demo_mode, scenarios_path=SCENARIOS, fraud_alert_lookback_hours=720,
    )
    rules = RuleNlu(["Amazon MX", "Netflix"])
    factory = lambda: Container.build(settings, nlu=nlu or rules, fallback=rules if nlu else None, sleep=lambda s: None)  # noqa: E731
    return TestClient(create_app(factory(), workspace_factory=factory if demo_mode else None))


def login(client, customer_id="CUST001", ws=None):
    headers = {"X-Demo-Workspace": ws} if ws else {}
    token = client.post("/auth/session", json={"customer_id": customer_id}, headers=headers).json()["token"]
    return {"Authorization": f"Bearer {token}", **headers}


def test_me_returns_name_cards_and_recent_purchases_of_the_session_customer_only():
    client = make_client()
    auth = login(client)
    me = client.get("/me", headers=auth).json()
    assert me["first_name"] == "Lucía" and me["country"] == "Mexico"
    assert me["cards"] == [{"product_id": "PRD001", "product_type": "Credit Card", "product_status": "Active"}]
    txns = client.get("/me/transactions", headers=auth).json()
    ids = [t["transaction_id"] for t in txns]
    assert ids[0] == "TXN007" and "TXN101" not in ids and "TXN004" not in ids
    assert set(txns[0]) >= {"merchant_name", "amount", "currency", "amount_usd", "transaction_date", "case_id"}
    assert client.get("/me").status_code == 401


def test_alerts_for_the_customer():
    client = make_client()
    alerts = client.get("/me/alerts", headers=login(client)).json()
    assert [a["transaction_id"] for a in alerts] == ["TXN005", "TXN007"]
    assert client.get("/me/alerts", headers=login(client, "CUST002")).json() == []


def test_conversation_started_from_a_purchase_skips_identification_and_the_case_shows_up():
    client = make_client()
    auth = login(client)
    start = client.post("/conversations", json={"language": "es", "transaction_id": "TXN001"}, headers=auth).json()
    assert "Amazon MX" in start["text"] and "¿Qué pasó" in start["text"]
    cid = start["conversation_id"]
    send = lambda text: client.post(f"/conversations/{cid}/messages", json={"text": text}, headers=auth).json()  # noqa: E731
    assert send("no lo reconozco")["ask_for"] == ["card_in_possession"]
    assert send("sí, la tengo")["action"] == "confirm"
    done = send("sí, confirmo, sin bloquear")
    assert done["action"] == "done" and done["nlu_mode"] == "rules"
    cases = client.get("/me/cases", headers=auth).json()
    assert [c["case_id"] for c in cases] == [done["case_id"]]
    txns = {t["transaction_id"]: t for t in client.get("/me/transactions", headers=auth).json()}
    assert txns["TXN001"]["case_id"] == done["case_id"]


def test_purchase_of_another_customer_cannot_start_a_conversation():
    client = make_client()
    r = client.post("/conversations", json={"transaction_id": "TXN001"}, headers=login(client, "CUST002"))
    assert r.status_code == 404
    assert client.post("/conversations", json={"transaction_id": "TXN001"}).status_code == 401


def test_workspaces_are_isolated_and_reset():
    client = make_client()
    a, b = login(client, ws="judge-a"), login(client, ws="judge-b")
    start = client.post("/conversations", json={"transaction_id": "TXN001"}, headers=a).json()
    for text in ["no lo reconozco", "sí, la tengo", "sí, confirmo, sin bloquear"]:
        client.post(f"/conversations/{start['conversation_id']}/messages", json={"text": text}, headers=a)
    assert len(client.get("/me/cases", headers=a).json()) == 1
    assert client.get("/me/cases", headers=b).json() == []
    assert client.post("/demo/reset", headers={"X-Demo-Workspace": "judge-a"}).status_code == 200
    assert client.get("/me/cases", headers=login(client, ws="judge-a")).json() == []


def test_agent_views_are_open_in_demo_mode_and_closed_otherwise():
    assert make_client(demo_mode=True).get("/agent/handoffs").status_code == 200
    closed = make_client(demo_mode=False)
    assert closed.get("/agent/handoffs").status_code == 401
    assert closed.post("/demo/reset").status_code == 404


def test_health_reports_demo_mode_and_nlu():
    body = make_client().get("/health").json()
    assert body["demo_mode"] is True and body["nlu"]["mode"] == "rules"


def test_scenarios_are_served():
    ids = [s["id"] for s in make_client().get("/demo/scenarios").json()]
    assert ids == ["normal", "human"]


def _hand_off_high_amount(client, ws="judge"):
    auth = login(client, ws=ws)
    start = client.post("/conversations", json={"transaction_id": "TXN005"}, headers=auth).json()
    r = client.post(f"/conversations/{start['conversation_id']}/messages", json={"text": "no lo reconozco"}, headers=auth).json()
    assert r["action"] == "handoff"
    return auth, r["handoff"]["case_ref"]


def test_agent_queue_shows_the_handoff_and_the_agent_opens_the_dispute():
    client = make_client()
    auth, ref = _hand_off_high_amount(client)
    ws = {"X-Demo-Workspace": "judge"}
    queue = client.get("/agent/handoffs", headers=ws).json()
    item = queue[0]
    assert item["case_ref"] == ref and item["status"] == "new" and item["customer_id"] == "CUST001"
    assert item["transaction_id"] == "TXN005" and item["reason_for_handoff"] == ["amount_above_threshold"]
    r = client.post(f"/agent/handoffs/{ref}/resolve", json={"action": "open_dispute", "note": "Verified by phone"},
                    headers=ws).json()
    assert r["status"] == "resolved" and r["case_id"].startswith("DSP-")
    assert r["decision"]["rule_ids"] == ["R-HUMAN-REVIEW"]
    assert [c["case_id"] for c in client.get("/me/cases", headers=auth).json()] == [r["case_id"]]
    assert client.get("/agent/handoffs", headers=ws).json()[0]["status"] == "resolved"
    again = client.post(f"/agent/handoffs/{ref}/resolve", json={"action": "close", "note": "x"}, headers=ws)
    assert again.status_code == 409
    trail = [e["kind"] for e in client.get(f"/agent/traces/{item['trace_id']}", headers=ws).json()]
    assert trail[-1] == "agent_action"


def test_agent_can_close_without_action_and_unknown_refs_are_404():
    client = make_client()
    _, ref = _hand_off_high_amount(client)
    ws = {"X-Demo-Workspace": "judge"}
    r = client.post(f"/agent/handoffs/{ref}/resolve", json={"action": "close", "note": "Customer withdrew"}, headers=ws)
    assert r.json()["status"] == "closed"
    assert client.post("/agent/handoffs/HO-nope/resolve", json={"action": "close"}, headers=ws).status_code == 404


def test_reply_carries_the_policy_decision_for_the_why_link():
    client = make_client()
    auth = login(client)
    start = client.post("/conversations", json={"transaction_id": "TXN001"}, headers=auth).json()
    r = client.post(f"/conversations/{start['conversation_id']}/messages", json={"text": "no lo reconozco"}, headers=auth).json()
    assert r["policy"]["rule_ids"] == ["R-ELIGIBLE"] and r["policy"]["missing_evidence"] == ["card_in_possession"]


def test_simulated_model_outage_is_per_workspace():
    from nlu_fakes import ScriptedNlu, nlu_result

    client = make_client(nlu=ScriptedNlu(*[nlu_result(intent="greeting")] * 5))
    ws = {"X-Demo-Workspace": "judge-x"}
    assert client.get("/health", headers=ws).json()["nlu"]["mode"] == "claude"
    assert client.post("/demo/outage", json={"on": True}, headers=ws).json()["nlu"]["mode"] == "rules"
    auth = login(client, ws="judge-x")
    cid = client.post("/conversations", json={}, headers=auth).json()["conversation_id"]
    r = client.post(f"/conversations/{cid}/messages", json={"text": "hola"}, headers=auth).json()
    assert r["nlu_mode"] == "rules"
    assert client.get("/health", headers={"X-Demo-Workspace": "judge-y"}).json()["nlu"]["mode"] == "claude"
    assert client.post("/demo/outage", json={"on": False}, headers=ws).json()["nlu"]["mode"] == "claude"


def test_parallel_first_requests_of_a_new_workspace_share_it():
    from concurrent.futures import ThreadPoolExecutor

    from dispute_ops.api import Workspaces

    built = []
    ws = Workspaces(lambda: built.append(object()) or built[-1])
    with ThreadPoolExecutor(max_workers=8) as pool:
        got = set(map(id, pool.map(lambda _: ws.get("same-tab"), range(32))))
    assert len(built) == 1 and len(got) == 1
