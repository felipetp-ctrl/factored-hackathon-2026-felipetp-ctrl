"""Customers remember charges approximately: rounded or spoken amounts, relative days, one word of the merchant,
"the other one". Found by probing the deployed fallback with free text (see ADR-022)."""

from datetime import date

import pytest

from dispute_ops.container import Container, Settings
from dispute_ops.flow import merchant_matches
from dispute_ops.language.nlu import NluContext
from dispute_ops.language.rule_nlu import RuleNlu, parse_amount, parse_relative_date, pick_candidate

MERCHANTS = ["Mercado Central", "Estación de Servicio", "Cable TV", "Tienda General"]
TODAY = date(2026, 6, 17)  # a Wednesday
CANDS = [
    {"transaction_id": "A", "merchant": "Mercado Central", "amount": "91558.20", "currency": "ARS", "date": "2026-05-02 18:48"},
    {"transaction_id": "B", "merchant": "Mercado Central", "amount": "131257.84", "currency": "ARS", "date": "2026-02-24 09:52"},
    {"transaction_id": "C", "merchant": "Mercado Central", "amount": "45491.90", "currency": "ARS", "date": "2025-07-09 12:03"},
]


def read(text, state="START", ask_for=(), candidates=()):
    ctx = NluContext(state=state, ask_for=list(ask_for), candidates=list(candidates), today=TODAY.isoformat())
    return RuleNlu(MERCHANTS).interpret(text, ctx).result


@pytest.mark.parametrize("text,expected", [
    ("uns 90 mil pesos", 90000.0), ("unos 90k", 90000.0), ("1,5 millones", 1500000.0),
    ("noventa y un mil pesos", 91000.0), ("cento e vinte mil", 120000.0), ("dos mil quinientos", 2500.0),
    ("un cargo raro", None), ("tengo dos tarjetas", None),
])
def test_spoken_and_scaled_amounts(text, expected):
    assert parse_amount(text) == expected


@pytest.mark.parametrize("text,expected", [
    ("fue ayer", "2026-06-16"), ("anteontem", "2026-06-15"), ("hace 3 días", "2026-06-14"),
    ("semana passada", "2026-06-10"), ("el sábado", "2026-06-13"), ("sin fecha", None),
])
def test_relative_days(text, expected):
    assert parse_relative_date(text, TODAY) == expected


def test_one_word_of_the_merchant_is_a_hint_but_generic_words_are_not():
    assert read("foi no mercado").merchant == "mercado"
    assert read("fue en la estacion").merchant == "estacion"
    assert read("compré en una tienda").merchant is None


@pytest.mark.parametrize("text,expected", [
    ("la más reciente", "A"), ("a mais cara", "B"), ("la de febrero", "B"), ("uns 45 mil", "C"), ("la del sábado", "A"),
])
def test_candidates_picked_the_way_people_describe_them(text, expected):
    assert pick_candidate(text, CANDS, TODAY) == expected


def test_yes_picks_the_only_candidate_shown():
    assert pick_candidate("sí, esa", CANDS[:1], TODAY) == "A"
    assert pick_candidate("sí", CANDS, TODAY) is None


def test_merchant_matching_is_accent_insensitive_and_word_based():
    assert merchant_matches("estacion", "Estación de Servicio") == (True, False)
    assert merchant_matches("Mercado Central", "Mercado Central") == (True, True)
    assert merchant_matches("farmacia", "Estación de Servicio") == (False, False)


def test_restating_the_problem_at_the_summary_is_not_a_no():
    r = read("no conozco ese comercio", state="CONFIRM")
    assert r.intent == "unclear"
    assert read("no", state="CONFIRM").intent == "decline"
    assert read("no, mejor no", state="CONFIRM").intent == "decline"


def test_no_la_reconozco_does_not_answer_the_card_question():
    r = read("no la reconozco", state="COLLECT_EVIDENCE", ask_for=["card_in_possession"])
    assert r.card_in_possession is None and r.recognizes_merchant == "no"


def test_the_other_one_at_the_summary_asks_to_change_the_charge():
    r = read("no, esa no, la de febrero", state="CONFIRM", candidates=CANDS)
    assert r.wrong_transaction and r.intent == "provide_info" and r.transaction_id == "B"


# ---------------------------------------------------------------------------------------------- end to end
DB = "demo_data/dispute_ops.db"
CUSTOMER = "CLI-G5M17CH817NF"  # three charges at Mercado Central in the demo store


@pytest.fixture
def chat():
    c = Container.build(Settings(session_secret="t", agent_api_key="t", demo_db=DB, nlu_mode="rules", intent_model=""))
    token, cid = c.sessions.issue(CUSTOMER), c.conversations.start("es")

    def say(text):
        return c.conversations.send(cid, token, text)
    say.container = c
    return say


def cases(chat):
    return [r["transaction_id"] for r in chat.container.store.conn.execute("SELECT transaction_id FROM disputes")]


def test_approximate_amount_then_partial_merchant_finds_the_charge(chat):
    r = chat("vi un cargo raro, unos 90 mil pesos, creo que me clonaron la tarjeta")
    assert r.action == "ask" and any(c["transaction_id"] == "TRX-RVW0G88DKH9RGHZDREDW" for c in r.candidates)
    r = chat("fue en el mercado")
    assert [c["transaction_id"] for c in r.candidates] == ["TRX-RVW0G88DKH9RGHZDREDW"]
    assert chat("sí").state == "COLLECT_EVIDENCE"


def test_nothing_matches_shows_recent_purchases_instead_of_repeating_the_question(chat):
    r = chat("un cargo de 5 pesos que no hice")
    assert r.action == "ask" and len(r.candidates) == 5 and "recientes" in r.text
    r = chat("no, ninguna de esas")  # the five shown are not offered again
    assert r.candidates and not {c["transaction_id"] for c in r.candidates} & {"TRX-YZZKSYRRTD4AJ8MD7ZPC"}


def test_customer_corrects_the_charge_at_the_summary(chat):
    chat("no reconozco una compra en mercado central")
    chat("la más reciente")
    r = chat("sí la tengo")
    assert r.action == "confirm"
    r = chat("no, esa no, la de febrero")
    assert r.action == "confirm" and "24/02/2026" in r.text
    chat("sí, no la bloquees")
    assert cases(chat) == ["TRX-MUTIJNOG0MLKFEHUQ9M0"]


def test_giving_new_details_does_not_run_out_of_clarifications(chat):
    chat("un cargo raro")
    chat("unos 50 mil")
    chat("no, ninguna de esas")
    r = chat("era en el mercado")
    assert r.action == "ask" and r.candidates  # still helping, not handed off
