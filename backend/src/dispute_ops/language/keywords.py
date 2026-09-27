"""Keyword rules in Spanish and Portuguese: the baseline for the learned NLU and the core of the fallback NLU.

It is the "obvious cheap alternative" the challenge asks the learned component to be compared with."""

from __future__ import annotations

import re
import unicodedata

from dispute_ops.domain import ReasonCode


def _norm(text: str) -> str:
    text = unicodedata.normalize("NFKD", text.lower())
    return "".join(ch for ch in text if not unicodedata.combining(ch))


# Order matters: more specific patterns first.
REASON_PATTERNS: list[tuple[ReasonCode, str]] = [
    # "cobrado 2 veces", not "cobrado 243,12" (test-v3 finding, post-hoc).
    (ReasonCode.DUPLICATE, r"dos veces|duas vezes|duplicad|doble cobr|cobr\w* 2 (veces|vezes)|repetid"),
    (ReasonCode.CANCELLED_RECURRING, r"cancel\w* (la |a |mi |minha )?(suscripcion|assinatura|membresia|plano)|suscripcion|assinatura"),
    (ReasonCode.NOT_RECEIVED, r"no (me )?(llego|ha llegado|recibi)|nao (chegou|recebi)|nunca (llego|chegou)|no lleg|entrega"),
    (ReasonCode.INCORRECT_AMOUNT, r"monto (incorrecto|equivocado|distinto)|valor (errado|incorreto|diferente)|cobraron (de )?mas|cobraram (a )?mais|mas de lo que"),
    (ReasonCode.FRAUD_CP, r"roba|rouba|robo\b|roubo\b|perdi (la |o |minha |mi )?(tarjeta|cartao)|extravi"),
    (ReasonCode.FRAUD_CNP, r"no (lo )?reconozco|nao reconheco|no hice|nao fiz|fraude|no fui yo|nao fui eu|desconozco|clonad"),
]
OUT_OF_SCOPE = r"saldo|prestamo|emprestimo|credito|limite|abrir (una |uma )?cuenta|abrir (una |uma )?conta|ahorro|poupanca|tasa|taxa de juros|inversion|investimento"
HUMAN = r"humano|asesor|agente|persona real|pessoa|atendente|operador"


def classify_reason(text: str) -> ReasonCode | None:
    t = _norm(text)
    for code, pattern in REASON_PATTERNS:
        if re.search(pattern, t):
            return code
    return None


def is_out_of_scope(text: str) -> bool:
    t = _norm(text)
    return bool(re.search(OUT_OF_SCOPE, t)) and classify_reason(text) is None


def wants_human(text: str) -> bool:
    return bool(re.search(HUMAN, _norm(text)))
