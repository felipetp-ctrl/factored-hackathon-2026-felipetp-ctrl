import pytest

from dispute_ops.domain import ReasonCode
from dispute_ops.language.nlu import NluContext
from dispute_ops.language.rule_nlu import RuleNlu, parse_amount

MERCHANTS = ["Amazon MX", "Netflix", "Mercado Central", "Boutique Moda", "Tienda General", "Conciertos Live"]
CANDIDATES = [
    {"transaction_id": "TXN002", "merchant": "Netflix", "amount": "399.00", "currency": "MXN", "date": "2026-06-14 09:00"},
    {"transaction_id": "TXN003", "merchant": "Netflix", "amount": "399.00", "currency": "MXN", "date": "2026-06-14 09:05"},
]


def read(text, state="START", ask_for=(), candidates=()):
    out = RuleNlu(MERCHANTS).interpret(text, NluContext(state=state, ask_for=list(ask_for), candidates=list(candidates)))
    assert out.usage.model == "rules" and out.usage.cost_usd == 0.0
    return out.result


@pytest.mark.parametrize("text,expected", [
    ("1.575.714,48", 1575714.48), ("91,558.20", 91558.20), ("$452.16", 452.16), ("1250", 1250.0),
    ("164.117,73 ARS", 164117.73), ("un cargo de 1.250 pesos", 1250.0),
    ("cargo de 1250 del 12 de mayo a las 04:25", 1250.0), ("1.575.714,48 COP em 12/05/2026", 1575714.48),
    ("una compra de mayo 2026 por 300", 300.0), ("sin monto", None),
])
def test_amounts_in_local_formats(text, expected):
    assert parse_amount(text) == expected


def test_unrecognised_charge_in_spanish():
    r = read("Hola, no reconozco un cargo de 1.250,00 en Amazon MX")
    assert r.intent == "dispute" and r.language == "es"
    assert r.merchant == "Amazon MX" and r.amount == 1250.0
    assert r.reason_code == ReasonCode.FRAUD_CNP and r.reason_confidence >= 0.6
    assert r.recognizes_merchant == "no" and r.summary


def test_duplicate_in_portuguese_matches_merchant_without_accents_or_case():
    r = read("me cobraram duas vezes na netflix")
    assert r.intent == "dispute" and r.language == "pt"
    assert r.merchant == "Netflix" and r.reason_code == ReasonCode.DUPLICATE


@pytest.mark.parametrize("text,txn", [
    ("la primera", "TXN002"), ("2", "TXN003"), ("é a segunda", "TXN003"), ("la de las 09:05", "TXN003"),
    ("TXN002", "TXN002"),
])
def test_picks_a_candidate(text, txn):
    assert read(text, state="IDENTIFY_TXN", ask_for=["transaction"], candidates=CANDIDATES).transaction_id == txn


def test_transaction_ids_typed_by_the_customer_are_passed_to_the_tool_layer():
    # Ownership is enforced by the tools, not by the NLU; the id is extracted as written.
    assert read("abre a disputa da TRX-RVW0G88DKH9RGHZDREDW").transaction_id == "TRX-RVW0G88DKH9RGHZDREDW"


def test_evidence_answers_follow_the_pending_questions():
    r = read("sí, la tengo conmigo y no conozco esa tienda", state="COLLECT_EVIDENCE",
             ask_for=["card_in_possession", "recognizes_merchant"])
    assert r.intent == "provide_info" and r.card_in_possession == "yes" and r.recognizes_merchant == "no"


def test_bare_answer_fills_the_single_yes_no_question():
    assert read("Não", state="COLLECT_EVIDENCE", ask_for=["contacted_merchant"]).contacted_merchant == "no"
    assert read("sim", state="COLLECT_EVIDENCE", ask_for=["card_in_possession"]).card_in_possession == "yes"


def test_amount_and_date_answers():
    assert read("era 363,88", state="COLLECT_EVIDENCE", ask_for=["expected_amount"]).expected_amount == 363.88
    assert read("el 10/04/2026", state="COLLECT_EVIDENCE", ask_for=["cancellation_date"]).cancellation_date == "2026-04-10"
    assert read("hace unos días", state="COLLECT_EVIDENCE", ask_for=["expected_delivery_date"]).expected_delivery_date


def test_duplicate_partner_is_taken_from_candidates():
    r = read("la otra es la segunda", state="COLLECT_EVIDENCE", ask_for=["duplicate_transaction_id"], candidates=CANDIDATES)
    assert r.duplicate_transaction_id == "TXN003"


@pytest.mark.parametrize("text,intent,block", [
    ("Sí, confirmo y bloqueen la tarjeta", "confirm", True),
    ("sí, pero sin bloquear la tarjeta", "confirm", False),
    ("Sim, confirmo. Não quero bloquear o cartão", "confirm", False),
    ("sim, pode bloquear", "confirm", True),
    ("no, mejor no", "decline", None),
    ("não", "decline", None),
])
def test_confirmation(text, intent, block):
    r = read(text, state="CONFIRM")
    assert r.intent == intent and r.wants_block_card is block


def test_proactive_alert_answers():
    assert read("sí, fui yo", state="PROACTIVE_CONFIRM").intent == "confirm"
    assert read("no, no fui yo", state="PROACTIVE_CONFIRM").intent == "decline"


@pytest.mark.parametrize("text,intent", [
    ("¿cuál es el saldo de mi cuenta?", "out_of_scope"),
    ("quero falar com um atendente", "human"),
    ("na verdade queria um empréstimo pessoal", "out_of_scope"),
    ("hola", "greeting"),
    ("no, gracias, no tengo nada que disputar", "decline"),
    ("asdf", "unclear"),
])
def test_other_intents(text, intent):
    assert read(text).intent == intent


def test_regulatory_threat_and_strong_negative_sentiment():
    r = read("Esto es una vergüenza, voy a denunciar ante la CONDUSEF un cargo de 900 en Boutique Moda que no hice")
    assert r.regulatory_threat and r.very_negative_sentiment and r.intent == "dispute"


def test_amount_starting_with_2_is_not_a_duplicate_charge():
    from dispute_ops.language.keywords import classify_reason
    assert classify_reason("cancelei a assinatura e fui cobrado 243,12 USD") != ReasonCode.DUPLICATE
    assert classify_reason("me cobraron 2 veces lo mismo") == ReasonCode.DUPLICATE


def test_merchant_name_with_a_product_word_is_not_out_of_scope():
    out = RuleNlu(["Super Ahorro"]).interpret("me cobraron de más en Super Ahorro", NluContext(state="START")).result
    assert out.intent != "out_of_scope" and out.merchant == "Super Ahorro"


# channels-v1 dev findings: refusals that start with a polite word, unsure answers to a fraud alert, indirect recognition.
import pytest as _pytest  # noqa: E402

from dispute_ops.language.nlu import NluContext as _Ctx  # noqa: E402
from dispute_ops.language.rule_nlu import RuleNlu as _Rules  # noqa: E402


@_pytest.mark.parametrize("state,text,intent", [
    ("CONFIRM", "Pode deixar, não precisa abrir disputa, era mesmo uma compra minha.", "decline"),
    ("CONFIRM", "Prefiro não abrir nada agora, quero perguntar para um familiar antes.", "decline"),
    ("CONFIRM", "Sim, confirmo, mas prefiro não bloquear", "confirm"),
    ("PROACTIVE_CONFIRM", "Ah, deve ser aquele presente que comprei para minha mãe naquele dia.", "confirm"),
    ("PROACTIVE_CONFIRM", "não sei", "unclear"),
    ("PROACTIVE_CONFIRM", "no sé, déjame revisar", "unclear"),
    ("PROACTIVE_CONFIRM", "No fui yo", "decline"),
])
def test_channels_v1_readings(state, text, intent):
    assert _Rules([]).interpret(text, _Ctx(state=state)).result.intent == intent


def test_stolen_card_letter_is_a_lost_or_stolen_card_dispute():
    r = _Rules([]).interpret("Me robaron la tarjeta y ya no la tengo; aparece un cargo que yo no hice.", _Ctx(state="START")).result
    assert (r.reason_code.value, r.card_in_possession) == ("FRAUD_CP", "no")


def test_pt_regulator_wording():
    r = _Rules([]).interpret("Se não resolverem, vou registrar uma reclamação no órgão regulador bancário.", _Ctx(state="START")).result
    assert r.regulatory_threat


@pytest.mark.parametrize("text", ["não lembro", "no me acuerdo", "no sé"])
def test_dont_remember_is_not_a_date(text):
    r = read(text, state="COLLECT_EVIDENCE", ask_for=["cancellation_date"])
    assert r.cancellation_date is None


def test_correct_amount_is_the_smaller_one_when_both_are_written():
    # channels-v1 letter: the charged amount was read as the correct one (found by the amount check, 04/10).
    r = read("a cobrança foi de USD 288,69, mas o valor combinado era de USD 202,08", state="COLLECT_EVIDENCE",
             ask_for=["expected_amount"])
    assert r.expected_amount == 202.08
