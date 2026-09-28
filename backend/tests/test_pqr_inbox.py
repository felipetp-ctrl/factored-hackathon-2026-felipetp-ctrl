"""The written-complaint (PQR) channel on the demo inbox: team-written letters about real charges of the gold sample,
read by the free reader (rules + intent-v2), matched to a charge and decided by the policy — no chat involved."""

from pathlib import Path

from fastapi.testclient import TestClient

from dispute_ops.api import create_app
from dispute_ops.container import Container, Settings

DEMO = Path(__file__).resolve().parents[1] / "demo_data"
WS = {"X-Demo-Workspace": "ws-pqrtest01"}


def make_client(demo_mode=True):
    settings = Settings(demo_db=str(DEMO / "dispute_ops.db"), session_secret="s", nlu_mode="rules", demo_mode=demo_mode,
                        demo_now="2026-06-17T12:00:00+00:00")
    factory = lambda: Container.build(settings, sleep=lambda s: None)  # noqa: E731
    return TestClient(create_app(factory(), workspace_factory=factory if demo_mode else None))


def test_inbox_outcomes():
    client = make_client()
    assert len(client.get("/demo/pqr/inbox", headers=WS).json()) == 6
    out = {r["complaint_id"]: r for r in client.post("/demo/pqr/process", headers=WS).json()}

    opened = out["PQR-DEMO-01"]  # fraud, card in hand, amount and product identify one charge
    assert opened["action"] == "done" and opened["case_id"] and opened["rule_ids"] == ["R-ELIGIBLE"]
    assert opened["reading"]["evidence"] == {"card_in_possession": "yes", "recognizes_merchant": "no"}

    wrong_amount = out["PQR-DEMO-02"]  # Portuguese; the expected amount is read in the second pass
    assert wrong_amount["action"] == "done" and wrong_amount["reading"]["reason_code"] == "INCORRECT_AMOUNT"
    assert wrong_amount["reading"]["evidence"]["expected_amount"] == "176.67"

    vague = out["PQR-DEMO-03"]  # like most real complaints: no amount, no product, templated text
    assert vague["action"] == "handoff" and vague["handoff_reasons"] == ["async_missing_info"]
    assert len(vague["candidate_transactions"]) == 3

    assert out["PQR-DEMO-04"]["handoff_reasons"] == ["amount_above_threshold"]
    assert out["PQR-DEMO-05"]["open_questions"] == ["card_in_possession"]

    regulator = out["PQR-DEMO-06"]  # a regulator threat goes to a person even when the case would be eligible
    assert regulator["action"] == "handoff" and regulator["case_id"] is None
    assert regulator["handoff_reasons"] == ["regulatory_or_legal_threat"]

    queue = client.get("/agent/handoffs", headers=WS).json()
    assert {q["case_ref"] for q in queue} >= {out[k]["case_ref"] for k in ("PQR-DEMO-03", "PQR-DEMO-04", "PQR-DEMO-06")}
    assert next(q for q in queue if q["case_ref"] == regulator["case_ref"])["language"] == "pt"


def test_demo_pqr_endpoints_do_not_exist_outside_demo_mode():
    client = make_client(demo_mode=False)
    assert client.get("/demo/pqr/inbox").status_code == 404
    assert client.post("/demo/pqr/process").status_code == 404
