"""The bank's case board: every channel (app, written complaint, fraud alert) on one list, with the stage reached."""

from pathlib import Path

from fastapi.testclient import TestClient

from dispute_ops.api import create_app
from dispute_ops.container import Container, Settings

DEMO = Path(__file__).resolve().parents[1] / "demo_data"
WS = {"X-Demo-Workspace": "ws-boardtest1"}


def make_client():
    settings = Settings(demo_db=str(DEMO / "dispute_ops.db"), session_secret="s", nlu_mode="rules", demo_mode=True,
                        demo_now="2026-06-17T12:00:00+00:00", fraud_alert_lookback_hours=720)
    factory = lambda: Container.build(settings, sleep=lambda s: None)  # noqa: E731
    return TestClient(create_app(factory(), workspace_factory=factory))


def auth(client, customer_id):
    token = client.post("/auth/session", json={"customer_id": customer_id}, headers=WS).json()["token"]
    return {"Authorization": f"Bearer {token}", **WS}


def test_board_shows_every_channel_with_its_stages():
    client = make_client()
    assert client.get("/agent/cases", headers=WS).json() == []

    # app: a purchase tapped, two answers, confirmed
    h = auth(client, "CLI-G5M17CH817NF")
    start = client.post("/conversations", json={"language": "es", "transaction_id": "TRX-RVW0G88DKH9RGHZDREDW"}, headers=h).json()
    cid = start["conversation_id"]
    assert start["reply"]["draft"]["transaction"]["transaction_id"] == "TRX-RVW0G88DKH9RGHZDREDW"
    for text in ("no la reconozco", "sí, la tengo"):
        r = client.post(f"/conversations/{cid}/messages", json={"text": text}, headers=h).json()
    assert r["action"] == "confirm" and r["draft"]["reason_code"] == "FRAUD_CNP"
    assert r["draft"]["evidence"] == {"recognizes_merchant": "no", "card_in_possession": "yes"}
    row = next(x for x in client.get("/agent/cases", headers=WS).json() if x["trace_id"] == cid)
    assert (row["channel"], row["outcome"], row["stages"]["confirm"]["status"]) == ("chat", "in_progress", "active")
    client.post(f"/conversations/{cid}/messages", json={"text": "sí, confirmo, sin bloquear"}, headers=h)

    # written complaints
    client.post("/demo/pqr/process", headers=WS)
    # fraud alert answered "not me"
    ha = auth(client, "CLI-LP2BQNTMC2F5")
    txn = client.get("/me/alerts", headers=ha).json()[0]["transaction_id"]
    alert = client.post(f"/alerts/{txn}/start", json={"language": "pt"}, headers=ha).json()
    for text in ("não fui eu", "sim, o cartão está comigo", "sim, e bloqueiem o cartão"):
        last = client.post(f"/conversations/{alert['conversation_id']}/messages", json={"text": text}, headers=ha).json()
    assert last["action"] == "done" and last["card_status"] == "Blocked"

    board = client.get("/agent/cases", headers=WS).json()
    by = {r["trace_id"]: r for r in board}
    chat = by[cid]
    assert chat["outcome"] == "resolved" and chat["case_id"] and chat["customer_name"]
    assert all(chat["stages"][s]["status"] == "done" for s in ("understand", "decide", "confirm", "act", "verify"))
    assert "open_dispute verified" in chat["stages"]["verify"]["detail"]

    pqr = [r for r in board if r["channel"] == "pqr"]
    assert len(pqr) == 6
    assert sorted(r["outcome"] for r in pqr) == ["person"] * 4 + ["resolved"] * 2
    assert by["pqr-PQR-DEMO-01"]["stages"]["confirm"]["detail"] == "filed complaint = consent"
    assert by["pqr-PQR-DEMO-06"]["outcome_detail"] == "regulatory_or_legal_threat"

    alert_row = by[alert["conversation_id"]]
    assert alert_row["channel"] == "proactive" and alert_row["reason_code"] == "FRAUD_CNP"
    assert alert_row["outcome"] == "resolved" and "block_card" in alert_row["stages"]["act"]["detail"]


def test_unclear_answers_are_bounded_and_open_nothing():
    client = make_client()
    ha = auth(client, "CLI-LP2BQNTMC2F5")
    txn = client.get("/me/alerts", headers=ha).json()[0]["transaction_id"]
    cid = client.post(f"/alerts/{txn}/start", json={"language": "pt"}, headers=ha).json()["conversation_id"]
    for _ in range(3):
        last = client.post(f"/conversations/{cid}/messages", json={"text": "não sei"}, headers=ha).json()
    assert last["action"] == "handoff" and last["handoff"]["reason_for_handoff"] == ["clarification_exhausted"]
    assert last["handoff"]["transaction_id"] == txn and last["case_id"] is None

    h = auth(client, "CLI-G5M17CH817NF")
    cid = client.post("/conversations", json={"language": "es", "transaction_id": "TRX-RVW0G88DKH9RGHZDREDW"}, headers=h).json()["conversation_id"]
    for text in ("no la reconozco", "sí, la tengo", "mmm", "hmm", "eh"):
        last = client.post(f"/conversations/{cid}/messages", json={"text": text}, headers=h).json()
    assert last["action"] == "handoff" and last["case_id"] is None
