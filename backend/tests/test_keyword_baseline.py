import pytest

from dispute_ops.domain import ReasonCode
from dispute_ops.evaluation.keyword_baseline import classify_reason, is_out_of_scope, wants_human


@pytest.mark.parametrize(("text", "code"), [
    ("Me cobraron dos veces Netflix", ReasonCode.DUPLICATE),
    ("Fui cobrado duas vezes", ReasonCode.DUPLICATE),
    ("Cancelé la suscripción y me siguen cobrando", ReasonCode.CANCELLED_RECURRING),
    ("O produto nunca chegou", ReasonCode.NOT_RECEIVED),
    ("Me cobraron más de lo que era", ReasonCode.INCORRECT_AMOUNT),
    ("Me robaron la tarjeta", ReasonCode.FRAUD_CP),
    ("Não reconheço essa compra", ReasonCode.FRAUD_CNP),
    ("hola", None),
])
def test_classify_reason(text, code):
    assert classify_reason(text) == code


def test_out_of_scope_and_human():
    assert is_out_of_scope("¿Cuál es mi saldo?") and not is_out_of_scope("No reconozco un cargo")
    assert wants_human("quero falar com um atendente")
