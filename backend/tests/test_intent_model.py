import sqlite3
from pathlib import Path

import pytest

from dispute_ops.domain import ReasonCode
from dispute_ops.language.intent_model import DEFAULT_PATH, LABELS, IntentModel, Prediction, features
from dispute_ops.language.keywords import _norm
from dispute_ops.language.nlu import NluContext
from dispute_ops.language.rule_nlu import RuleNlu
from dispute_ops.ml.augment import MERCHANTS, augment
from dispute_ops.ml.corpus import Example, drop_near_duplicates, load_corpus

DEMO_DB = Path(__file__).resolve().parents[1] / "demo_data" / "dispute_ops.db"


class StubModel:
    """Returns a fixed reading, to test how the rule NLU uses the classifier."""
    version = "stub-v0"
    threshold = 0.6

    def __init__(self, label: str, p: float) -> None:
        self.prediction = Prediction(label=label, probability=p, probabilities={label: p})
        self.calls = 0

    def predict(self, text: str) -> Prediction:
        self.calls += 1
        return self.prediction


def read(model, text, state="START", ask_for=()):
    return RuleNlu(["Amazon MX"], intent_model=model).interpret(text, NluContext(state=state, ask_for=list(ask_for)))


# --- the bundled model -------------------------------------------------------------------------------------------

@pytest.fixture(scope="module")
def model():
    return IntentModel.load(DEFAULT_PATH)


def test_bundled_model_is_intent_v2_with_all_labels(model):
    assert model.version == "intent-v2"
    assert set(model.labels) == set(LABELS)
    assert model.threshold >= 0.6  # never below the policy's hand-off floor


@pytest.mark.parametrize("text,label", [
    ("Me cobraron dos veces Netflix este mes", "DUPLICATE"),
    ("perdi minha carteira e usaram o cartão numa loja", "FRAUD_CP"),
    ("Hola, quiero disputar un cargo de 450 en Tienda Luna del 3 de mayo, el pedido nunca llegó", "NOT_RECEIVED"),
    ("cancelei a assinatura e continuam cobrando", "CANCELLED_RECURRING"),
    ("¿cuánto saldo tengo?", "OUT_OF_SCOPE"),
    ("quero falar com um atendente", "HUMAN"),
])
def test_bundled_model_reads_clear_messages(model, text, label):
    p = model.predict(text)
    assert p.label == label and p.probability >= model.threshold
    assert abs(sum(p.probabilities.values()) - 1) < 1e-9


def test_features_ignore_accents_case_and_digit_values():
    assert features("Cobrança de 1.250") == features("cobranca de 9.999")
    assert "w:cobranca" in features("Cobrança") and "b:cobranca_de" in features("cobrança de")
    assert not [f for f in features("hola", kinds="w") if not f.startswith("w:")]


def test_runtime_matches_sklearn_probabilities():
    pytest.importorskip("sklearn")
    from dispute_ops.ml.train import export
    corpus = load_corpus()[::5]
    spec = export("t", "wbc", 10.0, [e.text for e in corpus], [e.label for e in corpus], 0.6,
                  Path(pytest.importorskip("tempfile").mkdtemp()) / "m.json")
    assert spec["parity_max_abs_diff"] < 1e-4


# --- how the rule NLU uses it ------------------------------------------------------------------------------------

def test_confident_reason_replaces_the_keyword_rules():
    out = read(StubModel("NOT_RECEIVED", 0.91), "no reconozco un cargo de Amazon MX")  # keywords would say fraud
    assert out.result.reason_code == ReasonCode.NOT_RECEIVED and out.result.reason_confidence == pytest.approx(0.91)
    assert out.usage.model == "rules+stub-v0" and out.usage.cost_usd == 0.0


def test_below_threshold_the_keyword_rules_stand():
    out = read(StubModel("NOT_RECEIVED", 0.4), "no reconozco un cargo de Amazon MX")
    assert out.result.reason_code == ReasonCode.FRAUD_CNP and out.result.reason_confidence == 0.75


def test_confident_no_reason_clears_a_keyword_guess():
    out = read(StubModel("DISPUTE_NO_REASON", 0.8), "quiero reclamar un cargo de Amazon MX")
    assert out.result.reason_code is None and out.result.intent == "dispute"


def test_classifier_can_route_to_a_person_or_out_of_scope():
    assert read(StubModel("HUMAN", 0.9), "necesito que alguien me explique esto").result.intent == "human"
    assert read(StubModel("OUT_OF_SCOPE", 0.9), "quisiera información de seguros").result.intent == "out_of_scope"


def test_a_no_answer_is_never_read_as_a_human_request():
    assert read(StubModel("HUMAN", 0.9), "no, gracias").result.intent != "human"


def test_classifier_is_not_consulted_on_yes_no_turns():
    stub = StubModel("DUPLICATE", 0.99)
    out = read(stub, "sí, confirmo", state="CONFIRM")
    assert stub.calls == 0 and out.result.intent == "confirm"
    read(stub, "sí, la tengo", state="COLLECT_EVIDENCE", ask_for=["card_in_possession"])
    assert stub.calls == 0


# --- training data hygiene ---------------------------------------------------------------------------------------

def test_near_duplicates_of_evaluation_messages_are_dropped():
    corpus = [Example("No reconozco este cargo de Amazon", "FRAUD_CNP", "es"), Example("quiero un préstamo", "OUT_OF_SCOPE", "es")]
    kept, dropped = drop_near_duplicates(corpus, ["no reconozco este cargo de amazon!"])
    assert [e.label for e in kept] == ["OUT_OF_SCOPE"] and len(dropped) == 1


def test_augmentation_keeps_labels_and_groups_and_uses_no_dataset_merchant():
    base = load_corpus()[:30]
    data, groups = augment(base, per_sentence=2)
    assert len(data) == len(groups) == 90
    assert all(data[i].label == base[groups[i]].label for i in range(len(data)))
    dataset = {_norm(r[0]) for r in sqlite3.connect(DEMO_DB).execute("SELECT DISTINCT merchant_name FROM transactions") if r[0]}
    assert not {_norm(m) for m in MERCHANTS} & dataset


def test_corpus_is_balanced_across_labels_and_languages():
    corpus = load_corpus()
    for label in LABELS:
        for lang in ("es", "pt"):
            assert sum(e.label == label and e.language == lang for e in corpus) >= 45


def test_out_of_scope_keyword_outranks_a_human_reading():
    assert read(StubModel("HUMAN", 0.9), "queria ver sobre um empréstimo pessoal").result.intent == "out_of_scope"
