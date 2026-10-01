"""Deterministic input gateway: language detection, PII redaction and prompt-injection flags.

Runs before any model call. Everything here is rule-based on purpose: it must keep working
when the LLM is unavailable, and its behaviour must be auditable.
"""

from __future__ import annotations

import re
import unicodedata

_PT_MARKERS = {
    "não", "você", "vocês", "cartão", "obrigado", "obrigada", "compra", "cobrança", "cobrado",
    "fui", "meu", "minha", "reconheço", "estou", "tenho", "quero", "oi", "olá", "conta", "sim",
    "também", "então", "ontem", "semana", "reais", "boleto", "está", "pode", "ajudar", "vezes",
}
_ES_MARKERS = {
    "no", "usted", "tarjeta", "gracias", "cargo", "cobraron", "cobro", "mi", "reconozco", "estoy",
    "tengo", "quiero", "hola", "cuenta", "sí", "también", "entonces", "ayer", "pesos", "qué", "hago",
    "puede", "ayudar", "veces", "compré", "cancelé", "suscripción", "necesito",
}
_WORD = re.compile(r"[a-záéíóúâêôãõçñü]+", re.IGNORECASE)


def detect_language(text: str) -> str | None:
    """Return 'es', 'pt' or None when there is not enough evidence."""
    words = [w.lower() for w in _WORD.findall(text)]
    pt = sum(w in _PT_MARKERS for w in words) + len(re.findall(r"ção|ções|ão\b|ões\b|nh", text.lower()))
    es = sum(w in _ES_MARKERS for w in words) + len(re.findall(r"ción|ñ|¿|¡", text.lower()))
    if pt == es:
        return None
    return "pt" if pt > es else "es"


_PII_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("EMAIL", re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")),
    ("CARD", re.compile(r"\b(?:\d[ -]?){13,19}\b")),
    ("NATIONAL_ID", re.compile(r"\b[A-Z]{4}\d{6}[HM][A-Z]{5}[A-Z0-9]\d\b")),  # CURP (MX)
    ("NATIONAL_ID", re.compile(r"\b\d{3}\.\d{3}\.\d{3}-\d{2}\b")),  # CPF (BR)
    ("PHONE", re.compile(r"\+?\d{1,3}[ -]?\(?\d{2,3}\)?[ -]?\d{3,4}[ -]?\d{4}\b")),
    ("NATIONAL_ID", re.compile(r"\b\d{8,12}\b")),  # DNI (AR) / CC (CO) / long account-like numbers
]


def redact_pii(text: str) -> tuple[str, list[str]]:
    """Mask structured identifiers. Amounts (up to 7 digits) are kept on purpose: the dispute
    workflow needs them. Free-text names are not detected (documented limitation)."""
    found: list[str] = []
    for label, pattern in _PII_PATTERNS:
        text, n = pattern.subn(f"[{label}]", text)
        if n:
            found.append(label)
    return text, found


_INJECTION_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("override_instructions", re.compile(
        r"(ignor\w*|olvid\w*|esque[cç]\w*|disregard|forget)\s+(\w+\s+){0,3}"
        r"(instruc\w*|instru[cç][õo]es|instructions|reglas|regras|rules|prompt)", re.I)),
    ("reveal_prompt", re.compile(r"(system\s*prompt|prompt\s+del\s+sistema|prompt\s+do\s+sistema)", re.I)),
    ("role_play", re.compile(
        r"(act[uú]a\s+como|agora\s+voc[eê]\s+[eé]|ahora\s+eres|you\s+are\s+now|finge\s+ser|pretend\s+to\s+be)", re.I)),
    ("fake_markup", re.compile(r"(</?\s*customer_message\s*>|\bsystem\s*:|\bassistant\s*:|<\s*/?\s*system\s*>)", re.I)),
    ("tool_call", re.compile(r"\b(open_dispute|block_card|search_transactions|get_transaction|get_card)\b", re.I)),
]


def detect_injection(text: str) -> list[str]:
    """Return the names of matched injection heuristics (empty when none).

    Flags never grant or remove permissions: they are logged and passed to the NLU as a signal.
    Security comes from the tool layer, not from this filter."""
    normalized = unicodedata.normalize("NFKC", text)
    return [name for name, pattern in _INJECTION_PATTERNS if pattern.search(normalized)]


# An explicit request to talk to a person (ES/PT). Narrow on purpose: a verb of wanting plus talking to someone, or
# an unambiguous noun ("asesor", "atendente", "humano", "alguien de verdad"). Mentions of "persona"/"pessoa" alone
# do not count ("la persona que me cobró").
_HUMAN_REQUEST = re.compile(
    r"(\b(quiero|quisiera|queria|quería|necesito|deseo|prefiero|quero|gostaria|preciso|prefiro|me\s+pasa|me\s+passa|"
    r"me\s+comunica|pode\s+me\s+passar|puede\s+pasarme)\b[^.?!]{0,40}\b(hablar|falar|conversar|atendid[oa]|"
    r"pasar|passar|comunicar)\b[^.?!]{0,30}\b(alguien|alguém|alguem|una\s+persona|uma\s+pessoa|un\s+asesor|"
    r"uma?\s+atendente|un\s+agente|um\s+agente|un\s+humano|um\s+humano|un\s+ejecutivo|operador[a]?)\b)"
    r"|\b(me\s+)?(pasa|pasen|passa|passe|transfiere|transfieran|transfira|transfere)\s+(con|com|para|pra|a)\s+"
    r"(alguien|alguém|alguem|una\s+persona|uma\s+pessoa|un\s+asesor|uma?\s+atendente|un\s+agente|um\s+agente|"
    r"un\s+humano|um\s+humano)\b"
    r"|\b(alguien\s+de\s+verdad|alguém\s+de\s+verdade|alguem\s+de\s+verdade|persona\s+real|pessoa\s+real|"
    r"persona\s+de\s+verdad|pessoa\s+de\s+verdade|ser\s+humano)\b"
    # someone human / live / from the bank: "un agente humano", "atendente ao vivo", "alguien del banco"
    r"|\b(un|um|una|uma|al|ao|con|com|a)\s+(agente|asesor|atendente|operador|supervisor|representante|ejecutivo)"
    r"\s+(humano|real|en\s+vivo|ao\s+vivo)\b"
    r"|\b(un|um)\s+humano\b"
    r"|\b(alguien|alguém|alguem)\s+(del|do)\s+banco\b"
    r"|\bme\s+atienda\s+una\s+persona\b|\bme\s+atenda\s+uma\s+pessoa\b"
    # imperative transfers: "páseme con", "comuníqueme con", "me coloca em contato com", "transferirme con"
    r"|\b(p[aá]s[ae]me|p[aá]seme|comun[ií]queme|con[eé]cteme|transfi[eé]reme|transferirme|me\s+conecte|"
    r"me\s+coloca[mr]?\s+em\s+contato|me\s+coloquem\s+em\s+contato|me\s+transferir|me\s+transfira)\s+"
    r"(con|com|pra|para|a)\b",
    re.IGNORECASE,
)


def detect_human_request(text: str) -> bool:
    """True when the customer explicitly asks for a person. It outranks the model's reading (ADR-027): a request
    for a person is a handoff trigger in the policy, even in the same sentence as a yes."""
    return bool(_HUMAN_REQUEST.search(unicodedata.normalize("NFKC", text)))
