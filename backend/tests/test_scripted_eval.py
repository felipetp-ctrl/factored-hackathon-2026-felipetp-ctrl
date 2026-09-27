import pytest

from dispute_ops.evaluation import scripted
from dispute_ops.evaluation.scripted import NeedsMessage, ScriptedSimulator


class Sc:
    def __init__(self, opening=None):
        self.opening = opening


def test_scripted_simulator_returns_messages_in_order_then_asks_for_more():
    sim = ScriptedSimulator(["hola", "sí"])
    assert sim.next_message(Sc(), [("bank", "¿Qué cargo?")]) == "hola"
    assert sim.next_message(Sc(), [("bank", "?"), ("customer", "hola"), ("bank", "?")]) == "sí"
    with pytest.raises(NeedsMessage):
        sim.next_message(Sc(), [("bank", "?"), ("customer", "hola"), ("bank", "?"), ("customer", "sí"), ("bank", "?")])


def test_a_fixed_opening_is_not_counted_as_a_scripted_message():
    sim = ScriptedSimulator(["second"])
    assert sim.next_message(Sc(opening="first"), [("bank", "?"), ("customer", "first"), ("bank", "?")]) == "second"


def test_variants_differ_only_in_the_intent_model():
    a, b = scripted._settings("rules_only"), scripted._settings("rules_intent_v2")
    assert a.nlu_mode == b.nlu_mode == "rules" and a.intent_model == "off" and b.intent_model == ""
