"""Rule-based NLU: the free fallback when the language model is unavailable or over budget.

It fills the same `NluResult` as the Claude NLU from keyword rules, a merchant vocabulary, local number
formats and the question the service just asked. It is less capable (no paraphrase understanding), so
the deterministic flow keeps every guard it has: the policy still decides, low-information turns are
clarified at most twice and then handed to a person. Nothing here can grant an action."""

from __future__ import annotations

import re
import time
from collections.abc import Iterable
from datetime import date

from dispute_ops.domain import ReasonCode
from dispute_ops.language.gateway import detect_language
from dispute_ops.language.intent_model import REASON_LABELS, IntentModel, Prediction
from dispute_ops.language.keywords import _norm, classify_reason, is_out_of_scope
from dispute_ops.language.nlu import LlmUsage, NluContext, NluOutcome, NluResult

RULES_MODEL = "rules"


def is_rules_model(model: str) -> bool:
    """True for the free rule NLU, with or without the learned classifier ("rules", "rules+intent-v2")."""
    return model == RULES_MODEL or model.startswith(RULES_MODEL + "+")
RULES_VERSION = "rules-v1"
# Keyword matches are right ~87% of the time on the held-out messages; 0.75 keeps them above the policy's
# 0.6 confidence floor so a matched reason can proceed, while unmatched reasons are asked for.
RULE_CONFIDENCE = 0.75
# States where the customer states what they want (or answers "why?"): the learned classifier reads these.
# Elsewhere the service asked a yes/no or evidence question and the rules read the answer.
LEARNED_STATES = ("START", "IDENTIFY_TXN", "CLASSIFY")

_MONTHS = (
    "enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|setiembre|octubre|noviembre|diciembre|"
    "janeiro|fevereiro|marco|maio|junho|julho|setembro|outubro|novembro|dezembro"
)
_MONTH_NUM = {m: i for i, m in enumerate(
    "enero febrero marzo abril mayo junio julio agosto septiembre octubre noviembre diciembre".split(), 1)}
_MONTH_NUM.update({m: i for i, m in enumerate(
    "janeiro fevereiro marco abril maio junho julho agosto setembro outubro novembro dezembro".split(), 1)})
_MONTH_NUM["setiembre"] = 9

_TXN_ID = re.compile(r"\b(?:TRX|TXN)-?[A-Z0-9]{3,}\b", re.I)
_NOT_AMOUNTS = [
    re.compile(r"\b\d{1,2}[:h]\d{2}\b"),  # times
    re.compile(r"\b\d{4}-\d{2}-\d{2}\b"),  # ISO dates
    re.compile(r"\b\d{1,2}/\d{1,2}(?:/\d{2,4})?\b"),  # dd/mm(/yyyy)
    re.compile(rf"\b\d{{1,2}}\s+(?:de\s+)?(?:{_MONTHS})(?:\s+(?:de\s+)?\d{{4}})?\b"),  # 12 de mayo (de 2026)
    re.compile(rf"\b(?:{_MONTHS})\s+(?:de\s+)?\d{{4}}\b"),  # mayo 2026
]
_NUMBER = re.compile(
    r"(?P<pre>\$|usd|ars|cop|mxn|brl|r\$)?\s*(?P<num>\d[\d.,]*\d|\d)\s*"
    r"(?P<post>usd|ars|cop|mxn|brl|pesos|reais|dolares)?\b"
)

_YES = re.compile(r"^\W*(si|sim|claro|correcto|correto|exacto|exato|isso|confirmo|dale|ok|okay|de acuerdo|por supuesto|pode|puede|va)\b")
_NO = re.compile(r"^\W*(no|nao|nop|negativo|nunca|jamas)\b")
_GREETING = re.compile(
    r"^\W*(hola|oi|ola|buenas|buenos dias|bom dia|boa tarde|boa noite|buenas tardes|buenas noches|hey)"
    r"[\s!,.]*(tudo bem|como estas|como esta|que tal)?[\s!?.]*$")
_DISPUTE_WORDS = re.compile(r"disput|contest|cargo|cobr|compra|reclam")
_NOTHING_TO_DO = re.compile(r"nada (que|para|a) (disputar|contestar)|no necesito nada|nao preciso de nada|no tengo ningun cargo|nao tenho nenhuma")
_BLOCK = re.compile(r"bloque")
_NO_BLOCK = re.compile(
    r"(sin|sem|no|nao)\s+(quiero\s+|quero\s+|precisa\s+|necesito\s+|hace falta\s+|es necesario\s+|e necessario\s+)?(que\s+)?(me\s+)?bloque")
# Whole words only: the baseline's substring match reads "empréstimo pessoal" (personal loan) as "pessoa".
_HUMAN = re.compile(r"\b(humano|asesor|asesora|agente|persona real|una persona|uma pessoa|pessoa|atendente|operador|operadora)\b")
_REGULATOR = re.compile(
    r"condusef|superintendencia|bcra|banco central|procon|defensor(ia)? del consumidor|denunci|abogad|advogad|"
    r"demanda|processar|justicia|prensa|imprensa|reclame aqui")
_NEGATIVE = re.compile(r"verguenza|vergonha|estafa|ladron|ladroe|inutil|basura|absurdo|pesimo|pessimo|indignad|furios|harto|lixo")

_EVIDENCE_RULES: dict[str, tuple[re.Pattern[str], re.Pattern[str]]] = {  # field -> (no, yes)
    "card_in_possession": (
        re.compile(r"perdi|robaron|robad|robo\b|roubad|roubo|extravi|no la tengo|no lo tengo|nao esta comigo|nao tenho o cartao"),
        re.compile(r"la tengo|lo tengo|tengo la tarjeta|conmigo|en mi poder|esta comigo|comigo|tenho o cartao|en la mano|na mao"),
    ),
    "recognizes_merchant": (
        re.compile(r"no (la |lo |a )?(conozco|reconozco)|nao (a |o )?(conheco|reconheco)|nunca (compre|comprei|oi|ouvi)|"
                   r"desconozco|no hice|nao fiz|no fui yo|nao fui eu"),
        re.compile(r"si (la |lo )?(conozco|reconozco)|sim,? (a |o )?(conheco|reconheco)|reconozco (la tienda|el comercio)|reconheco a loja"),
    ),
    "contacted_merchant": (
        re.compile(r"no (he |les |lo )?(contactado|hablado|escrito|llamado)|nao (entrei|falei|liguei|contatei|escrevi)"),
        re.compile(r"ya (me )?(comunique|hable|contacte|escribi|llame)|ja (entrei em contato|falei|liguei|escrevi|contatei)|"
                   r"entrei em contato|contacte al comercio|hable con (la tienda|el comercio)"),
    ),
}
_YES_NO_FIELDS = ("card_in_possession", "recognizes_merchant", "contacted_merchant")
_DATE_FIELDS = ("expected_delivery_date", "cancellation_date")
_ORDINALS = [
    (re.compile(r"\b(primer[ao]?|primeir[ao])\b"), 0), (re.compile(r"\bsegund[ao]\b"), 1),
    (re.compile(r"\b(tercer[ao]?|terceir[ao])\b"), 2), (re.compile(r"\bcuart[ao]\b|\bquart[ao]\b"), 3),
    (re.compile(r"\bultim[ao]\b"), -1),
]


def _to_number(s: str) -> float:
    if "." in s and "," in s:
        dec = "." if s.rfind(".") > s.rfind(",") else ","
        s = s.replace("," if dec == "." else ".", "").replace(dec, ".")
    elif "." in s or "," in s:
        sep = "." if "." in s else ","
        parts = s.split(sep)
        s = f"{parts[0]}.{parts[1]}" if len(parts) == 2 and len(parts[1]) in (1, 2) else s.replace(sep, "")
    return float(s)


def parse_amount(text: str) -> float | None:
    """The amount a customer mentions, in any local format. Dates, times and ids are ignored; a number
    next to a currency wins, otherwise the largest one."""
    t = _TXN_ID.sub(" ", _norm(text))
    for pattern in _NOT_AMOUNTS:
        t = pattern.sub(" ", t)
    found: list[tuple[bool, float]] = []
    for m in _NUMBER.finditer(t):
        try:
            found.append((bool(m.group("pre") or m.group("post")), _to_number(m.group("num"))))
        except ValueError:
            continue
    if not found:
        return None
    with_currency = [v for tagged, v in found if tagged]
    return max(with_currency) if with_currency else max(v for _, v in found)


def parse_date(text: str) -> str | None:
    t = _norm(text)
    if m := re.search(r"\b(\d{4})-(\d{2})-(\d{2})\b", t):
        y, mo, d = map(int, m.groups())
    elif m := re.search(r"\b(\d{1,2})/(\d{1,2})/(\d{2,4})\b", t):
        d, mo, y = map(int, m.groups())
        y += 2000 if y < 100 else 0
    elif m := re.search(rf"\b(\d{{1,2}})\s+(?:de\s+)?({_MONTHS})(?:\s+(?:de\s+)?(\d{{4}}))?", t):
        d, mo, y = int(m.group(1)), _MONTH_NUM[m.group(2)], int(m.group(3) or 2026)
    else:
        return None
    try:
        return date(y, mo, d).isoformat()
    except ValueError:
        return None


def pick_candidate(text: str, candidates: list[dict[str, str]]) -> str | None:
    if not candidates:
        return None
    ids = {c["transaction_id"].upper(): c["transaction_id"] for c in candidates}
    for m in _TXN_ID.finditer(text):
        if m.group(0).upper() in ids:
            return ids[m.group(0).upper()]
    t = _norm(text)
    for pattern, index in _ORDINALS:
        if pattern.search(t):
            return candidates[index]["transaction_id"] if -len(candidates) <= index < len(candidates) else None
    times = re.findall(r"\b(\d{1,2})[:h](\d{2})\b", t)
    for hh, mm in times:
        hits = [c for c in candidates if c["date"].endswith(f"{int(hh):02d}:{mm}")]
        if len(hits) == 1:
            return hits[0]["transaction_id"]
    bare = re.fullmatch(r"\W*(?:(?:la|el|a|o|opcion|opcao|numero)\s+)?([1-9])\W*", t)
    if bare and int(bare.group(1)) <= len(candidates):
        return candidates[int(bare.group(1)) - 1]["transaction_id"]
    amount = parse_amount(text)
    if amount is not None:
        hits = [c for c in candidates if abs(float(c["amount"]) - amount) < 0.005]
        if len(hits) == 1:
            return hits[0]["transaction_id"]
    return None


class RuleNlu:
    mode = "rules"

    def __init__(self, merchants: Iterable[str], intent_model: IntentModel | None = None) -> None:
        self.intent_model = intent_model
        self._last: Prediction | None = None
        # Global vocabulary of merchant names (no customer data): longest names first so "Tienda General"
        # wins over a shorter overlapping name.
        self.merchants = sorted({(_norm(m), m) for m in merchants if m}, key=lambda x: -len(x[0]))

    def _merchant(self, t: str) -> str | None:
        for normalized, original in self.merchants:
            if re.search(rf"(?<!\w){re.escape(normalized)}(?!\w)", t):
                return original
        return None

    def interpret(self, text: str, ctx: NluContext) -> NluOutcome:
        started = time.perf_counter()
        self._last: Prediction | None = None
        result = self._read(text, ctx)
        model = f"{RULES_MODEL}+{self.intent_model.version}" if self.intent_model else RULES_MODEL
        usage = LlmUsage(model=model, prompt_version=RULES_VERSION, input_tokens=0, output_tokens=0,
                         latency_ms=(time.perf_counter() - started) * 1000, cost_usd=0.0)
        classifier = None if self._last is None else {
            "version": self.intent_model.version, "label": self._last.label, "probability": round(self._last.probability, 4),
            "accepted": self._last.probability >= self.intent_model.threshold}
        return NluOutcome(result=result, usage=usage, classifier=classifier)

    def _read(self, text: str, ctx: NluContext) -> NluResult:
        t = _norm(text)
        language = detect_language(text) or "other"
        yes, no = bool(_YES.search(t)), bool(_NO.search(t))
        fields: dict = dict(
            transaction_id=None, merchant=None, amount=None, reason_code=None, reason_confidence=0.0,
            card_in_possession=None, recognizes_merchant=None, duplicate_transaction_id=None, expected_amount=None,
            expected_delivery_date=None, contacted_merchant=None, cancellation_date=None, wants_block_card=None,
            very_negative_sentiment=bool(_NEGATIVE.search(t)), regulatory_threat=bool(_REGULATOR.search(t)),
        )

        def done(intent: str) -> NluResult:
            return NluResult(intent=intent, language=language, summary=_summary(language, fields), **fields)

        if ctx.state == "CONFIRM":
            if _HUMAN.search(t) and not yes:
                return done("human")
            if _BLOCK.search(t):
                fields["wants_block_card"] = not _NO_BLOCK.search(t)
            if no and not yes:
                return done("decline")
            return done("confirm" if yes or "confirm" in t else "unclear")
        if ctx.state == "PROACTIVE_CONFIRM":
            if _HUMAN.search(t):
                return done("human")
            if no or re.search(r"no fui yo|nao fui eu|no (la |lo )?reconozco|nao reconheco", t):
                fields["recognizes_merchant"] = "no"
                return done("decline")
            return done("confirm" if yes or re.search(r"fui yo|fui eu", t) else "unclear")

        learned = self._learned(text, ctx)
        # Routing precedence: an explicit out-of-scope product word outranks the classifier's "human" reading
        # (the classifier is weaker than the keywords at scope; e.g. "empréstimo pessoal" is not "pessoa").
        learned_human = learned is not None and learned.label == "HUMAN" and not is_out_of_scope(text)
        if (_HUMAN.search(t) or learned_human) and not no:
            return done("human")

        # A confident classifier reading replaces the keyword rules for the reason (it is more accurate on held-out
        # messages, ADR-019); its probability becomes the reason confidence the policy checks (≥ 0.6).
        if learned:
            reason = ReasonCode(learned.label) if learned.label in REASON_LABELS else None
            confidence = learned.probability
        else:
            reason, confidence = classify_reason(text), RULE_CONFIDENCE
        if reason is not None:
            fields.update(reason_code=reason, reason_confidence=confidence)
        fields["merchant"] = self._merchant(t)
        fields["amount"] = parse_amount(text)
        ids = _TXN_ID.findall(text)
        picked = pick_candidate(text, ctx.candidates) if ctx.candidates else None
        fields["transaction_id"] = picked or (ids[0].upper() if ids else None)
        if picked:
            fields["amount"] = None  # the pick already identifies the charge

        answered = self._evidence(text, t, ctx, fields, yes, no)
        if reason is None and fields["recognizes_merchant"] == "no" and ctx.state in ("START", "IDENTIFY_TXN", "CLASSIFY"):
            # "No la reconozco" answers the reason question even without the baseline's exact wording.
            reason = ReasonCode.FRAUD_CNP
            fields.update(reason_code=reason, reason_confidence=RULE_CONFIDENCE)
            answered = answered or "reason_code" in ctx.ask_for
        learned_oos = learned is not None and learned.label == "OUT_OF_SCOPE"
        # A merchant name is not a product request: "Super Ahorro" is a shop, not savings (test-v3 finding, post-hoc).
        scope_text = t.replace(_norm(fields["merchant"]), " ") if fields["merchant"] else text
        if (is_out_of_scope(scope_text) or learned_oos) and not answered and fields["transaction_id"] is None:
            return done("out_of_scope")
        if ctx.ask_for and (answered or picked):
            return done("provide_info")
        cues = reason or fields["merchant"] or fields["amount"] is not None or fields["transaction_id"]
        if (no or _NOTHING_TO_DO.search(t)) and not cues:
            return done("decline")
        if cues or _DISPUTE_WORDS.search(t):
            return done("dispute")
        if _GREETING.search(t):
            return done("greeting")
        return done("unclear")

    def _learned(self, text: str, ctx: NluContext) -> Prediction | None:
        """The classifier's reading when it is confident and the turn is one it was trained for."""
        if self.intent_model is None or ctx.state not in LEARNED_STATES:
            return None
        p = self.intent_model.predict(text)
        self._last = p
        return p if p.probability >= self.intent_model.threshold else None

    @staticmethod
    def _evidence(text: str, t: str, ctx: NluContext, fields: dict, yes: bool, no: bool) -> bool:
        answered = False
        for name, (neg, pos) in _EVIDENCE_RULES.items():
            if neg.search(t):
                fields[name] = "no"
            elif pos.search(t):
                fields[name] = "yes"
            answered = answered or (fields[name] is not None and name in ctx.ask_for)
        pending = [f for f in ctx.ask_for if f in _YES_NO_FIELDS and fields[f] is None]
        if len(pending) == 1 and (yes or no):
            fields[pending[0]] = "yes" if yes else "no"
            answered = True
        if "expected_amount" in ctx.ask_for and (amount := parse_amount(text)) is not None:
            fields["expected_amount"] = amount
            answered = True
        for name in _DATE_FIELDS:
            if name in ctx.ask_for and text.strip() and not (no and len(t) < 6):
                fields[name] = parse_date(text) or text.strip()[:60]
                answered = True
        if "duplicate_transaction_id" in ctx.ask_for and (other := pick_candidate(text, ctx.candidates)):
            fields["duplicate_transaction_id"] = other
            answered = True
        return answered


_REASON_WORDS = {
    "es": {"FRAUD_CNP": "cargo no reconocido", "FRAUD_CP": "cargo no reconocido (tarjeta perdida o robada)",
           "DUPLICATE": "cobro duplicado", "INCORRECT_AMOUNT": "monto incorrecto",
           "NOT_RECEIVED": "producto no recibido", "CANCELLED_RECURRING": "suscripción cancelada"},
    "pt": {"FRAUD_CNP": "compra não reconhecida", "FRAUD_CP": "compra não reconhecida (cartão perdido ou roubado)",
           "DUPLICATE": "cobrança duplicada", "INCORRECT_AMOUNT": "valor incorreto",
           "NOT_RECEIVED": "produto não recebido", "CANCELLED_RECURRING": "assinatura cancelada"},
}


def _summary(language: str, f: dict) -> str:
    lang = "pt" if language == "pt" else "es"
    reason: ReasonCode | None = f["reason_code"]
    what = _REASON_WORDS[lang][reason.value] if reason else ("disputa" if lang == "es" else "contestação")
    parts = [("Cliente quiere disputar: " if lang == "es" else "Cliente quer contestar: ") + what]
    if f["merchant"]:
        parts.append(f"({f['merchant']})")
    if f["amount"] is not None:
        parts.append(f"{f['amount']:.2f}")
    return " ".join(parts)
