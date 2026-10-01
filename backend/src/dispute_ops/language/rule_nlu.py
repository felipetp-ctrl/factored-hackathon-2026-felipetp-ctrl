"""Rule-based NLU: the free fallback when the language model is unavailable or over budget.

It fills the same `NluResult` as the Claude NLU from keyword rules, a merchant vocabulary, local number
formats and the question the service just asked. It is less capable (no paraphrase understanding), so
the deterministic flow keeps every guard it has: the policy still decides, low-information turns are
clarified at most twice and then handed to a person. Nothing here can grant an action."""

from __future__ import annotations

import re
import time
from collections.abc import Iterable
from datetime import date, timedelta

from dispute_ops.domain import ReasonCode
from dispute_ops.language.gateway import detect_language
from dispute_ops.language.intent_model import REASON_LABELS, IntentModel, Prediction
from dispute_ops.language.keywords import _norm, classify_reason, is_out_of_scope
from dispute_ops.language.nlu import LlmUsage, NluContext, NluOutcome, NluResult

RULES_MODEL = "rules"
# Words of merchant names too generic to point at a merchant on their own.
_MERCHANT_STOP = frozenset({
    "online", "store", "tienda", "loja", "shop", "servicio", "servicios", "servico", "general", "centro", "grupo",
    "empresa", "compra", "pago", "pagos", "banco", "tarjeta", "cartao"})


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
IDENTIFY_THRESHOLD = 0.8

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
_NOTHING_TO_DO = re.compile(
    r"nada (que|para|a) (disputar|contestar)|no necesito nada|nao preciso de nada|no tengo ningun cargo|nao tenho nenhuma|"
    r"(no|nao) (hace falta|precisa|necesita|es necesario|e necessario) (abrir|contestar|disputar|nada)|pode deixar|"
    r"dejalo asi|deja(lo)? nomas|(?<!no )(?<!nao )(?<!nunca )fui (yo|eu)\b|fue mi (hijo|hija|esposo|esposa|marido|mujer)|foi (o )?meu (filho|marido)|"
    r"foi (a )?minha (filha|esposa|mulher)|con (mi )?permiso|com (minha )?permissao|ya me acorde|ja lembrei|agora lembrei")
# "É essa mesmo", "esa es": picking the only charge shown.
_THIS_ONE = re.compile(r"\b(e essa|essa mesm[ao]|isso mesmo|essa ai|e esta|esa es|es esa|esa misma|esa mism[ao]|"
                       r"es la misma|esa exactamente|exacto|exato|justo esa|essa sim|esa si)\b")
_BLOCK = re.compile(r"bloque")
_NO_BLOCK = re.compile(
    r"(sin|sem|no|nao)\s+(quiero\s+|quero\s+|precisa\s+|necesito\s+|hace falta\s+|es necesario\s+|e necessario\s+)?(que\s+)?(me\s+)?bloque")
# Whole words only: the baseline's substring match reads "empréstimo pessoal" (personal loan) as "pessoa".
_NEGATED_BLOCK = re.compile(r"\b(no|nao|sin|sem|nunca|jamas|ni)\b[^.!?;]*\bbloque")
_HUMAN = re.compile(r"\b(humano|asesor|asesora|agente|persona real|una persona|uma pessoa|pessoa|atendente|operador|operadora)\b")
_REGULATOR = re.compile(
    r"condusef|superintendencia|bcra|banco central|procon|defensor(ia)? del consumidor|denunci|abogad|advogad|"
    r"demanda|processar|justicia|prensa|imprensa|reclame aqui|regulador|ouvidoria|consumidor\.gov|"
    r"superintendencia financiera|defensa del consumidor|profeco")
_NEGATIVE = re.compile(r"verguenza|vergonha|estafa|ladron|ladroe|inutil|basura|absurdo|pesimo|pessimo|indignad|furios|harto|lixo")

_CARD_GONE = re.compile(r"\b(robad|robaron|roubad|roubaram|furtad|perdi|perdid|extravi|extraviad|clonaron el bolso|asaltaron|assaltad)")
_WRONG_ONE = re.compile(
    r"\b(la otra|el otro|a outra|o outro|otra compra|outra compra|no es esa|no es ese|nao e essa|nao e esse|esa no\b|"
    r"essa nao|ese no\b|esse nao|no era esa|nao era essa|me equivoque|me confundi|me enganei|errei|equivocad|ninguna de|"
    r"nenhuma dessas|nenhuma delas)")


_EXPLICIT_DECLINE = re.compile(
    r"^\W*(no|nao)\W*$|cancel|no confirm|nao confirm|no quiero|nao quero|desist|deja(lo)? asi|deixa (pra la|assim)|mejor no|melhor nao")
# A refusal that starts with a polite "yes"-like word ("Pode deixar, não precisa abrir", "Prefiro não abrir nada agora"):
# at the summary these must read as no, never as a confirmation (channels-v1 dev: a dispute was opened on
# "Pode deixar, não precisa abrir disputa, era mesmo uma compra minha").
_REFUSAL = re.compile(
    r"(?:\b(prefiero|prefiro) (no|nao)\b|\b(no|nao) (abra|abras|abran|abrir)\b|"
    r"\b(no|nao) (precisa|necesito|hace falta|quiero|quero|es necesario|e necessario)( de)? "
    r"(abrir|nada|disputa|contest|reclam|isso|eso|seguir)|"
    r"\b(ahora|agora|todavia|ainda) (no|nao)\b|\bantes (quiero|quero|voy|vou)\b|\b(mas|mais) tarde\b|"
    r"\bera (mesmo |si |sim )?(uma |una )?(compra )?(minha|mia|meu|mio)\b)"
    r"(?![^.!?;]*bloque)")  # "sim, mas prefiro não bloquear" is a yes without a block
# Answers to "did you make this purchase?" that are neither yes nor no.
_UNSURE = re.compile(r"\b(no se|nao sei|no estoy segur|nao tenho certeza|no recuerdo|nao lembro|no me acuerdo|"
                     r"dejame (pensar|ver|revisar)|deixa eu (pensar|ver)|tengo que (revisar|ver)|preciso (ver|verificar))\b")
_NOT_ME = re.compile(r"no fui yo|nao fui eu|no (la |lo )?(reconozco|hice|compre)|nao (a |o )?(reconheco|fiz|comprei)|"
                     r"no (es|era) mia|nao (e|era) minha|nunca (la |a )?(hice|fiz|compre|comprei)")
_RECOGNISED = re.compile(
    r"\bfui (yo|eu)\b|\b(yo )?(la|lo) (hice|compre)\b|\beu (fiz|comprei)\b|\bcomprei\b|\bcompre\b|"
    r"\b(deve|debe|debio) (ser|ter sido|haber sido)\b|\bfoi aquilo\b|\bfue eso\b|\bera (mesmo |si )?(minha|mia|meu|mio)\b|"
    r"\b(presente|regalo)\b|\b(ja|agora) lembrei\b|\bya me acorde\b|\bsi,? (la )?reconozco\b|\bsim,? (reconheco|fui)\b")


def _today(ctx: NluContext) -> date | None:
    try:
        return date.fromisoformat(ctx.today) if ctx.today else None
    except ValueError:
        return None


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
# Words that say where the card is, either way: the grounding check for a model's "card in possession" reading.
POSSESSION_CUES = re.compile("|".join([_EVIDENCE_RULES["card_in_possession"][0].pattern,
                                       _EVIDENCE_RULES["card_in_possession"][1].pattern,
                                       r"cartera|billetera|carteira|bolso|bolsa|mochila|guardad|perdid|perdeu|sumi"]))
_DATE_FIELDS = ("expected_delivery_date", "cancellation_date")
_ORDINALS = [
    (re.compile(r"\b(primer[ao]?|primeir[ao])\b"), 0), (re.compile(r"\bsegund[ao]\b"), 1),
    (re.compile(r"\b(tercer[ao]?|terceir[ao])\b"), 2), (re.compile(r"\bcuart[ao]\b|\bquart[ao]\b"), 3),
    (re.compile(r"\bultim[ao]\b"), -1),
]


_UNITS = {
    "cero": 0, "zero": 0, "un": 1, "uno": 1, "una": 1, "um": 1, "uma": 1, "dos": 2, "dois": 2, "duas": 2, "tres": 3,
    "cuatro": 4, "quatro": 4, "cinco": 5, "seis": 6, "siete": 7, "sete": 7, "ocho": 8, "oito": 8, "nueve": 9, "nove": 9,
    "diez": 10, "dez": 10, "once": 11, "onze": 11, "doce": 12, "doze": 12, "trece": 13, "treze": 13, "catorce": 14,
    "catorze": 14, "quatorze": 14, "quince": 15, "quinze": 15, "dieciseis": 16, "dezesseis": 16, "diecisiete": 17,
    "dezessete": 17, "dieciocho": 18, "dezoito": 18, "diecinueve": 19, "dezenove": 19, "veinte": 20, "vinte": 20,
    "veintiuno": 21, "veintiun": 21, "veintidos": 22, "veintitres": 23, "veinticuatro": 24, "veinticinco": 25,
    "veintiseis": 26, "veintisiete": 27, "veintiocho": 28, "veintinueve": 29, "treinta": 30, "trinta": 30,
    "cuarenta": 40, "quarenta": 40, "cincuenta": 50, "cinquenta": 50, "sesenta": 60, "sessenta": 60, "setenta": 70,
    "ochenta": 80, "oitenta": 80, "noventa": 90, "cien": 100, "ciento": 100, "cem": 100, "cento": 100,
    "doscientos": 200, "duzentos": 200, "trescientos": 300, "trezentos": 300, "cuatrocientos": 400,
    "quatrocentos": 400, "quinientos": 500, "quinhentos": 500, "seiscientos": 600, "seiscentos": 600,
    "setecientos": 700, "setecentos": 700, "ochocientos": 800, "oitocentos": 800, "novecientos": 900,
    "novecentos": 900,
}
_SCALES = {"mil": 1_000, "millon": 1_000_000, "millones": 1_000_000, "milhao": 1_000_000, "milhoes": 1_000_000}
_NUMBER_WORD = re.compile(r"\b(?:" + "|".join(sorted(list(_UNITS) + list(_SCALES), key=len, reverse=True))
                          + r")\b(?:\s+(?:y|e)?\s*\b(?:" + "|".join(sorted(list(_UNITS) + list(_SCALES), key=len,
                                                                          reverse=True)) + r")\b)*")
# "90 mil", "1,5 millones", "90k"
_SCALED = re.compile(r"(\d+(?:[.,]\d+)?)\s*(mil\b|k\b|millon(?:es)?\b|milh(?:ao|oes)\b|lucas?\b|palos?\b)")
_WEEKDAYS = {"lunes": 0, "segunda": 0, "martes": 1, "terca": 1, "miercoles": 2, "quarta": 2, "jueves": 3, "quinta": 3,
             "viernes": 4, "sexta": 4, "sabado": 5, "domingo": 6}


def _words_value(phrase: str) -> int | None:
    total, current, seen = 0, 0, False
    for w in re.findall(r"[a-z]+", phrase):
        if w in _UNITS:
            current += _UNITS[w]
            seen = True
        elif w in _SCALES:
            scale = _SCALES[w]
            current = max(current, 1) * scale
            if scale >= 1_000:
                total += current
                current = 0
            seen = True
    return total + current if seen else None


def _spoken_numbers(t: str) -> str:
    """Rewrite spoken amounts as digits: "noventa y un mil" -> 91000, "90 mil" -> 90000, "90k" -> 90000."""
    def scaled(m: re.Match[str]) -> str:
        base = float(m.group(1).replace(",", "."))
        unit = m.group(2)
        mult = 1_000_000 if unit.startswith(("millon", "milh", "palo")) else 1_000
        return f" {int(round(base * mult))} "

    t = _SCALED.sub(scaled, t)

    def words(m: re.Match[str]) -> str:
        v = _words_value(m.group(0))
        # a lone "un"/"uma"/"dos" is an article or a count, not an amount
        return f" {v} " if v is not None and (v >= 10 or " " in m.group(0).strip()) else m.group(0)

    return _NUMBER_WORD.sub(words, t)


def parse_relative_date(text: str, today: date | None) -> str | None:
    """The day a customer refers to, relative to today: "ayer", "semana passada", "el sábado", "hace 3 días"."""
    if today is None:
        return None
    t = _norm(text)
    if re.search(r"\b(anteayer|antier|anteontem)\b", t):
        return (today - timedelta(days=2)).isoformat()
    if re.search(r"\b(ayer|ontem)\b", t):
        return (today - timedelta(days=1)).isoformat()
    if re.search(r"\b(hoy|hoje|esta manana|esta manha)\b", t):
        return today.isoformat()
    if m := re.search(r"\b(?:hace|ha|faz)\s+(\d+|un|una|uma|dos|dois|tres)\s+(dia|dias|semana|semanas)\b", t):
        n = {"un": 1, "una": 1, "uma": 1, "dos": 2, "dois": 2, "tres": 3}.get(m.group(1)) or int(m.group(1))
        return (today - timedelta(days=n * (7 if m.group(2).startswith("semana") else 1))).isoformat()
    for name, wd in _WEEKDAYS.items():
        if re.search(rf"\b{name}(-feira)?\b", t):
            back = (today.weekday() - wd) % 7 or 7
            if re.search(r"pasad|passad|anterior", t) and back < 7:
                back += 7 if re.search(r"semana pasad|semana passad", t) else 0
            return (today - timedelta(days=back)).isoformat()
    if re.search(r"semana pasad|semana passad|la otra semana|outra semana", t):
        return (today - timedelta(days=7)).isoformat()
    if re.search(r"mes pasad|mes passad", t):
        return (today - timedelta(days=30)).isoformat()
    return None


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
    t = _spoken_numbers(t)
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


def pick_candidate(text: str, candidates: list[dict[str, str]], today: date | None = None) -> str | None:
    if not candidates:
        return None
    t0 = _norm(text)
    if len(candidates) == 1 and (_YES.search(t0) or _THIS_ONE.search(t0)) and not _NO.search(t0):
        return candidates[0]["transaction_id"]
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
    by_date = sorted(candidates, key=lambda c: c["date"])
    if re.search(r"mas recient|mais recent|la ultima vez|mas nuev|mais nov|la de ayer|a de ontem", t):
        return by_date[-1]["transaction_id"]
    if re.search(r"mas antigu|mais antig|la primera vez", t):
        return by_date[0]["transaction_id"]
    by_amount = sorted(candidates, key=lambda c: float(c["amount"]))
    if re.search(r"mas car[ao]|mais car[ao]|mayor|maior|mas grande|mais alt[ao]|mas alt[ao]", t):
        return by_amount[-1]["transaction_id"]
    if re.search(r"mas barat[ao]|mais barat[ao]|menor|mas pequen|mais pequen|mas baj[ao]|mais baix[ao]", t):
        return by_amount[0]["transaction_id"]
    day = parse_date(text) or parse_relative_date(text, today)
    if day:
        hits = [c for c in candidates if _candidate_day(c) == day]
        if len(hits) == 1:
            return hits[0]["transaction_id"]
    months = {_MONTH_NUM[m] for m in re.findall(rf"\b({_MONTHS})\b", t)}
    if len(months) == 1:
        hits = [c for c in candidates if (d := _candidate_date(c)) is not None and d.month in months]
        if len(hits) == 1:
            return hits[0]["transaction_id"]
    for name, wd in _WEEKDAYS.items():
        if re.search(rf"\b{name}(-feira)?\b", t):
            hits = [c for c in candidates if (d := _candidate_date(c)) is not None and d.weekday() == wd]
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
        near = sorted(candidates, key=lambda c: abs(float(c["amount"]) - amount))
        if abs(float(near[0]["amount"]) - amount) <= 0.25 * amount and (
                len(near) == 1 or abs(float(near[1]["amount"]) - amount) > 2 * abs(float(near[0]["amount"]) - amount)):
            return near[0]["transaction_id"]
    return None


def _candidate_date(c: dict[str, str]) -> date | None:
    """Candidates carry dd/mm/yyyy or ISO dates (see conversation._candidate)."""
    raw = c.get("date", "")
    try:
        if m := re.match(r"(\d{2})/(\d{2})/(\d{4})", raw):
            return date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
        return date.fromisoformat(raw[:10])
    except ValueError:
        return None


def _candidate_day(c: dict[str, str]) -> str | None:
    d = _candidate_date(c)
    return d.isoformat() if d else None


class RuleNlu:
    mode = "rules"

    def __init__(self, merchants: Iterable[str], intent_model: IntentModel | None = None) -> None:
        self.intent_model = intent_model
        self._last: Prediction | None = None
        # Global vocabulary of merchant names (no customer data): longest names first so "Tienda General"
        # wins over a shorter overlapping name.
        self.merchants = sorted({(_norm(m), m) for m in merchants if m}, key=lambda x: -len(x[0]))
        # Significant words of merchant names ("mercado", "estacion"): customers often remember only one. The flow
        # shows the matching charges for the customer to pick; a word alone never identifies a charge silently.
        self.merchant_words = {w for n, _ in self.merchants for w in re.findall(r"[a-z]+", n)
                               if len(w) >= 4 and w not in _MERCHANT_STOP}

    def _merchant(self, t: str) -> str | None:
        for normalized, original in self.merchants:
            if re.search(rf"(?<!\w){re.escape(normalized)}(?!\w)", t):
                return original
        words = [w for w in re.findall(r"[a-z]+", t) if w in self.merchant_words]
        return max(words, key=len) if words else None

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
            purchase_date=None, wrong_transaction=False,
        )

        def done(intent: str) -> NluResult:
            return NluResult(intent=intent, language=language, summary=_summary(language, fields), **fields)

        if ctx.state == "CONFIRM":
            if _HUMAN.search(t) and not yes:
                return done("human")
            if _WRONG_ONE.search(t):
                fields["wrong_transaction"] = True
                fields["transaction_id"] = pick_candidate(text, ctx.candidates, _today(ctx)) if ctx.candidates else None
                fields["merchant"], fields["amount"] = self._merchant(t), parse_amount(text)
                fields["purchase_date"] = parse_date(text) or parse_relative_date(text, _today(ctx))
                return done("provide_info")
            if _BLOCK.search(t):
                # Blocking is a write action: any negation before "bloque..." in the same sentence means no
                # ("no la bloqueen", "no quiero que la bloqueen" were read as yes; hard-v1 test, fixed post-hoc).
                fields["wants_block_card"] = not (_NO_BLOCK.search(t) or _NEGATED_BLOCK.search(t))
            # "No conozco ese comercio" at the summary restates the problem; it is not a "no" to the summary.
            if _NOTHING_TO_DO.search(t) or _REFUSAL.search(t):
                return done("decline")
            restates = any(neg.search(t) or pos.search(t) for neg, pos in _EVIDENCE_RULES.values())
            if no and not yes and restates and not _EXPLICIT_DECLINE.search(t):
                return done("unclear")
            if no and not yes:
                return done("decline")
            return done("confirm" if yes or "confirm" in t else "unclear")
        if ctx.state == "PROACTIVE_CONFIRM":
            if _HUMAN.search(t):
                return done("human")
            # Order matters: "no fui yo" contains "fui yo"; "no sé" starts with "no" but is not a no.
            if _NOT_ME.search(t):
                fields["recognizes_merchant"] = "no"
                return done("decline")
            if _UNSURE.search(t):
                return done("unclear")
            if _RECOGNISED.search(t) or _NOTHING_TO_DO.search(t):
                return done("confirm")
            if no:
                fields["recognizes_merchant"] = "no"
                return done("decline")
            return done("confirm" if yes else "unclear")

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
        if ctx.state in ("START", "IDENTIFY_TXN", "CLASSIFY") and "reason_code" not in ctx.ask_for:
            fields["purchase_date"] = parse_date(text) or parse_relative_date(text, _today(ctx))
        ids = _TXN_ID.findall(text)
        picked = pick_candidate(text, ctx.candidates, _today(ctx)) if ctx.candidates else None
        if _NOTHING_TO_DO.search(t) and not _WRONG_ONE.search(t):
            fields["transaction_id"] = None
            return done("decline")
        if ctx.candidates and not picked and (_WRONG_ONE.search(t) or (no and not yes)):
            fields["wrong_transaction"] = True  # "no, none of those" / "no es esa"
            return done("provide_info")
        fields["transaction_id"] = picked or (ids[0].upper() if ids else None)
        if picked:
            fields["amount"] = None  # the pick already identifies the charge

        answered = self._evidence(text, t, ctx, fields, yes, no)
        if (fields["reason_code"] == ReasonCode.FRAUD_CNP and fields["card_in_possession"] == "no"
                and _CARD_GONE.search(t)):
            # "Me robaron la tarjeta y aparece un cargo" is a lost/stolen card, not card-not-present fraud (channels-v1 dev).
            fields.update(reason_code=ReasonCode.FRAUD_CP, reason_confidence=max(fields["reason_confidence"], RULE_CONFIDENCE))
            reason = ReasonCode.FRAUD_CP
        if reason is None and fields["recognizes_merchant"] == "no" and ctx.state in ("START", "IDENTIFY_TXN", "CLASSIFY"):
            # "No la reconozco" answers the reason question even without the baseline's exact wording.
            reason = ReasonCode.FRAUD_CNP
            fields.update(reason_code=reason, reason_confidence=RULE_CONFIDENCE)
            answered = answered or "reason_code" in ctx.ask_for
        learned_oos = learned is not None and self.intent_model is not None and self.intent_model.confident_out_of_scope(learned)
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
        # Answers to "which purchase?" are short references the classifier was not trained on ("era en el
        # mercado" read as INCORRECT_AMOUNT at 0.70 in a dev probe): there it needs a surer reading.
        threshold = self.intent_model.threshold
        if ctx.state == "IDENTIFY_TXN" and "transaction" in ctx.ask_for:
            threshold = max(threshold, IDENTIFY_THRESHOLD)
        return p if p.probability >= threshold else None

    @staticmethod
    def _evidence(text: str, t: str, ctx: NluContext, fields: dict, yes: bool, no: bool) -> bool:
        answered = False
        other_statement = False
        for name, (neg, pos) in _EVIDENCE_RULES.items():
            if neg.search(t):
                fields[name] = "no"
            elif pos.search(t):
                fields[name] = "yes"
            answered = answered or (fields[name] is not None and name in ctx.ask_for)
            other_statement = other_statement or (fields[name] is not None and name not in ctx.ask_for)
        pending = [f for f in ctx.ask_for if f in _YES_NO_FIELDS and fields[f] is None]
        # A bare "sí"/"no" answers the one pending question, unless the "no" belongs to another statement
        # ("no la reconozco" answers the merchant, not "do you have the card?").
        if len(pending) == 1 and (yes or no) and not other_statement:
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
