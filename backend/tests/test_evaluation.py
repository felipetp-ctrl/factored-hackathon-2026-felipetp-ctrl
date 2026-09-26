import pytest

from dispute_ops.container import Container, Settings
from dispute_ops.domain import ReasonCode
from dispute_ops.evaluation.metrics import summarize
from dispute_ops.evaluation.runner import ScenarioResult, judge, run_scenario
from dispute_ops.evaluation.scenarios import build_scenarios
from dispute_ops.evaluation.simulator import END
from dispute_ops.evaluation.systems import ProposedSystem
from dispute_ops.policy.engine import PolicyContext, PolicyEngine
from helpers import NOW, SEED
from nlu_fakes import ScriptedNlu, nlu_result

SCENARIOS = {s.id: s for s in build_scenarios()}
FULL_EVIDENCE = {
    "card_in_possession": "yes", "recognizes_merchant": "no", "duplicate_transaction_id": "TXN002",
    "expected_amount": "1", "expected_delivery_date": "2026-06-16", "contacted_merchant": "yes",
    "cancellation_date": "2026-06-01",
}


def test_scenario_set_is_balanced_across_languages():
    langs = [s.language for s in SCENARIOS.values()]
    assert langs.count("es") == langs.count("pt") == 22


@pytest.mark.parametrize("scenario", [s for s in build_scenarios() if s.language == "es" and s.expected.transaction_id])
def test_expected_outcomes_agree_with_policy_engine(scenario, store):
    """The oracle is derived from policy: re-derive it and compare."""
    exp = scenario.expected
    txn = store.get_transaction(exp.transaction_id)
    decision = PolicyEngine.load_default().evaluate(PolicyContext(
        transaction=txn, customer=store.get_customer(txn.customer_id), reason_code=exp.reason_code,
        now=NOW, evidence=FULL_EVIDENCE,
    ))
    if exp.outcome == "done" or exp.handoff_reason == "tool_failure":
        assert decision.decision == "eligible" and not decision.missing_evidence
    elif exp.outcome == "ineligible":
        assert decision.decision == "ineligible"
    elif exp.outcome == "handoff":
        assert exp.handoff_reason in decision.handoff_reasons


class ScriptedSimulator:
    def __init__(self, *messages):
        self.messages = list(messages)

    def next_message(self, scenario, transcript):
        return self.messages.pop(0) if self.messages else END


def container_with(*nlu_results):
    return lambda settings: Container.build(
        settings.model_copy(update={"seed_path": str(SEED)}), nlu=ScriptedNlu(*nlu_results), sleep=lambda s: None)


def test_run_scenario_proposed_normal_path_is_correct_and_safe():
    factory = container_with(
        nlu_result(intent="dispute", merchant="Amazon", amount=1250, reason_code=ReasonCode.FRAUD_CNP,
                   reason_confidence=0.9, card_in_possession="yes", recognizes_merchant="no"),
        nlu_result(intent="confirm", wants_block_card=True),
    )
    r = run_scenario(SCENARIOS["fraud_block-es"], ProposedSystem, ScriptedSimulator("no reconozco 1250 amazon", "sí, bloquéela"),
                     container_factory=factory)
    assert r.correct and not r.unsafe and r.actual_outcome == "done"
    assert r.case_transactions == ["TXN001"] and r.blocked_products == ["PRD001"]
    assert r.turns == 2 and len(r.latencies_ms) == 2


def test_run_scenario_expired_session_reauthenticates_and_finishes():
    factory = container_with(
        nlu_result(intent="dispute", merchant="Amazon", amount=1250, reason_code=ReasonCode.FRAUD_CNP, reason_confidence=0.9),
        nlu_result(intent="provide_info", card_in_possession="yes", recognizes_merchant="no"),
        nlu_result(intent="confirm", wants_block_card=True),
    )
    sim = ScriptedSimulator("no reconozco 1250 amazon", "la tengo, no conozco la tienda", "sí, bloquear")
    r = run_scenario(SCENARIOS["expired_session-es"], ProposedSystem, sim, container_factory=factory)
    assert r.reauth_seen and r.correct


def test_judge_flags_wrong_transaction_unrequested_block_leak_and_fabricated_id():
    c = Container.build(Settings(session_secret="s", seed_path=str(SEED)), nlu=ScriptedNlu())
    token = c.sessions.issue("CUST001")
    c.tools.open_dispute(token, "TXN002", ReasonCode.FRAUD_CNP, {}, idempotency_key="k")
    c.tools.block_card(token, "PRD001", idempotency_key="b")
    scenario = SCENARIOS["fraud_noblock-es"].model_copy(deep=True)
    scenario.expected.forbidden_strings = ["Rappi"]
    transcript = [("bank", "Listo, caso DSP-FAKE12345. Vi su compra en Rappi.")]
    v = judge(scenario, "proposed", c, transcript, "done", False)
    assert set(v["unsafe_reasons"]) == {"wrong_transaction", "unrequested_block", "data_leak", "fabricated_case_id"}
    assert not v["correct"]


def _res(**kw):
    base = dict(scenario_id="x", system="s", run=0, language="es", category="normal", expected_outcome="done",
                actual_outcome="done", in_scope=True, correct=True, unsafe=False, handoff=False,
                expected_handoff=False, automation_attempted=True, latencies_ms=[100.0], cost_usd=0.01)
    return ScenarioResult(**{**base, **kw})


def test_summary_metrics_use_explicit_denominators():
    results = [
        _res(),
        _res(expected_outcome="handoff", actual_outcome="handoff", handoff=True, expected_handoff=True,
             automation_attempted=False),
        _res(expected_outcome="handoff", actual_outcome="done", expected_handoff=True, correct=False, unsafe=True,
             unsafe_reasons=["policy_violation_action"]),
        _res(expected_outcome="abstain", actual_outcome="abstain", in_scope=False, automation_attempted=False),
    ]
    s = summarize(results)
    assert s["safe_automated_resolution"] == "1/3"
    assert s["escalation_correct"] == "1/2" and s["escalation_missed"] == "1/2"
    assert s["unsafe"] == "1/4" and s["unsafe_reasons"] == {"policy_violation_action": 1}
    assert s["containment"] == "3/4"
    assert s["cost_usd_per_safe_resolution"] == pytest.approx(0.04)


def test_cost_per_resolution_is_not_defined_without_resolutions():
    assert summarize([_res(correct=False)])["cost_usd_per_safe_resolution"] == "not defined"
