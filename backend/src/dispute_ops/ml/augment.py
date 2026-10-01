"""Compositional augmentation of the intent corpus (intent-v2).

Customers rarely state the reason alone: they open with the charge (merchant, amount, date, time) and add the
reason, or give the reason and then the details. intent-v1 was trained on isolated clauses and read the
"I want to dispute a charge of X at Y" opening as *no reason* even when a reason followed. This module
combines each corpus sentence with generic charge descriptions in local formats.

Merchants are invented and deliberately exclude every merchant name that appears in the evaluation sets.
Every generated example keeps the id of the sentence it came from, so cross-validation can keep all variants of
a sentence in the same fold."""

from __future__ import annotations

import random
import re

from dispute_ops.ml.corpus import Example

MERCHANTS = ["Tienda Luna", "ElectroMax", "Café Aurora", "Supermercado El Sol", "Viajes Andes", "Librería Norte",
             "Moda Urbana", "Farmacia Vida", "Gimnasio Pulse", "StreamPlus", "Market Norte", "Pizzería Roma",
             "AutoPartes Sur", "Hotel Brisa", "TecnoShop", "Zapatería Paso", "Óptica Clara", "Juguetes Kiko"]

_AMOUNTS = {
    "es": ["1.250,00 ARS", "$3,450.90 MXN", "89.90 USD", "1.575.000 COP", "$ 780", "12.300 pesos", "45,50 dólares",
           "2.340.500,75 COP", "15.999 ARS", "$129.99"],
    "pt": ["R$ 250,00", "89,90 USD", "1.575.000 COP", "3.450,90 MXN", "R$ 78", "1.230 reais", "45,50 dólares",
           "12.300 ARS", "R$ 1.999,00", "129,99 USD"],
}
_DATES = {
    "es": ["el 12 de mayo", "del 3 de abril de 2026", "el 03/05/2026", "el martes", "ayer", "del 28 de febrero",
           "el 15/06", "la semana pasada"],
    "pt": ["no dia 12 de maio", "de 3 de abril de 2026", "em 03/05/2026", "na terça", "ontem", "de 28 de fevereiro",
           "dia 15/06", "semana passada"],
}
_TIMES = {"es": ["", "", " como a las 21:40", " a las 8:15 am", " por la madrugada"],
          "pt": ["", "", " por volta das 21h40", " às 08:15", " de madrugada"]}
_OPENERS = {
    "es": ["Hola, quiero disputar un cargo de {a} en {m} {d}{t}.", "Buenas, veo un cargo de {a} de \"{m}\" {d}{t}.",
           "Hola, buenas. Hay un cobro de {a} en {m} {d}{t}.", "Quiero reclamar la compra en {m} por {a} {d}.",
           "Hola, es sobre un cargo de {a} en {m} {d}{t}.", "Tengo un consumo de {a} en {m} {d}.",
           "hola quiero disputar un cobro de {a} en {m}", "Buen día, en mi tarjeta aparece {m} por {a} {d}{t}."],
    "pt": ["Oi, quero contestar uma cobrança de {a} na {m} {d}{t}.", "Boa tarde, vi uma cobrança de {a} da \"{m}\" {d}{t}.",
           "Olá, tudo bem? Tem uma cobrança de {a} na {m} {d}{t}.", "Quero reclamar da compra na {m} de {a} {d}.",
           "Oi, é sobre uma cobrança de {a} na {m} {d}{t}.", "Tenho um lançamento de {a} na {m} {d}.",
           "oi quero contestar uma cobranca de {a} na {m}", "Bom dia, no meu cartão aparece {m} de {a} {d}{t}."],
}
_TRAILERS = {"es": ["Fue en {m} por {a}.", "Es el de {a} en {m} {d}.", "El cargo es de {a}, {d}."],
             "pt": ["Foi na {m}, {a}.", "É a de {a} na {m} {d}.", "A cobrança é de {a}, {d}."]}
_GREETINGS = {"es": ["Hola, buenas. ", "Buenas tardes. ", "Hola! ", "Buen día, "],
              "pt": ["Oi, tudo bem? ", "Boa tarde. ", "Olá! ", "Bom dia, "]}


def _details(rng: random.Random, lang: str) -> dict[str, str]:
    return {"m": rng.choice(MERCHANTS), "a": rng.choice(_AMOUNTS[lang]), "d": rng.choice(_DATES[lang]),
            "t": rng.choice(_TIMES[lang])}


def _lower_first(s: str) -> str:
    return s[:1].lower() + s[1:] if s[:2] != s[:2].upper() else s


def augment(corpus: list[Example], per_sentence: int = 2, seed: int = 11) -> tuple[list[Example], list[int]]:
    """Originals plus `per_sentence` composites each; returns the examples and their group (base sentence) ids."""
    rng = random.Random(seed)
    out, groups = [], []
    for gid, ex in enumerate(corpus):
        out.append(ex)
        groups.append(gid)
        lang = ex.language
        for _ in range(per_sentence):
            d = _details(rng, lang)
            if ex.label == "OUT_OF_SCOPE":
                text = rng.choice(_GREETINGS[lang]) + ex.text
            elif ex.label == "DISPUTE_NO_REASON":
                text = rng.choice(_OPENERS[lang]).format(**d)
            elif rng.random() < 0.7:  # details first, then the reason (or the human request)
                text = f"{rng.choice(_OPENERS[lang]).format(**d)} {_lower_first(ex.text)}"
            else:  # reason first, then the details
                text = f"{ex.text.rstrip('.!')}. {rng.choice(_TRAILERS[lang]).format(**d)}"
            out.append(Example(text=" ".join(text.split()), label=ex.label, language=lang, source="augmented"))
            groups.append(gid)
    return out, groups


# Spoken-style variants (intent-v3, ADR-030). Real out-of-scope speech is lower-case, unpunctuated and opens with a
# call greeting; if only the out-of-scope class looked like that, the model would learn "sounds like a phone call →
# out of scope" (it did: 33 of 44 real disputes sent away on the first intent-v3 fit). Giving every label the same
# style removes the shortcut. Openers are generic call phrases, not taken from any evaluation message.
_CALL_OPENERS = {
    "es": ["hola buenos días llamaba porque", "hola buenas mira te llamo porque", "sí hola buenas tardes",
           "buenos días soy cliente del banco y", "hola qué tal mire", "buenas tardes es que", ""],
    "pt": ["bom dia estou a ligar porque", "olá boa tarde", "bom dia eu queria dizer que", "boa tarde liguei porque",
           "oi bom dia é que", "olá tudo bem olha", ""],
}
_CALL_CLOSERS = {"es": ["", "", "gracias", "muchas gracias", "por favor"],
                 "pt": ["", "", "obrigado", "obrigada", "se faz favor", "por favor"]}
_PUNCT = re.compile(r"[^\w\s$€%/,]")


def speech_style(examples: list[Example], groups: list[int], seed: int = 17) -> tuple[list[Example], list[int]]:
    """One spoken-style copy of every example (same label and group): lower case, no punctuation, call phrases."""
    rng = random.Random(seed)
    out, out_groups = [], []
    for ex, gid in zip(examples, groups):
        lang = ex.language if ex.language in _CALL_OPENERS else "es"
        body = _PUNCT.sub(" ", ex.text.lower()).replace(",", " ")
        text = " ".join(f"{rng.choice(_CALL_OPENERS[lang])} {body} {rng.choice(_CALL_CLOSERS[lang])}".split())
        out.append(Example(text=text, label=ex.label, language=ex.language, source="spoken"))
        out_groups.append(gid)
    return examples + out, groups + out_groups


_JOINS = {"es": ["y además", "y también", "porque", "es que", "y"], "pt": ["e também", "porque", "é que", "e além disso", "e"]}
REASONS = {"FRAUD_CNP", "FRAUD_CP", "DUPLICATE", "INCORRECT_AMOUNT", "NOT_RECEIVED", "CANCELLED_RECURRING", "DISPUTE_NO_REASON"}


def compound(examples: list[Example], groups: list[int], seed: int = 19) -> tuple[list[Example], list[int]]:
    """An out-of-scope request followed by a dispute keeps the dispute's label (intent-v3, ADR-030).

    Callers mix topics ("show me my latest transactions, there is a payment I don't recognise"); a one-label model
    trained only on single-topic messages lets the out-of-scope half win, and the dispute is turned away. Both
    halves come from the training corpus."""
    rng = random.Random(seed)
    oos = {lang: [e.text for e in examples if e.label == "OUT_OF_SCOPE" and e.language == lang and e.source == "corpus"]
           for lang in ("es", "pt")}
    out, out_groups = [], []
    for ex, gid in zip(examples, groups):
        if ex.label in REASONS and ex.source == "corpus" and oos.get(ex.language):
            first = rng.choice(oos[ex.language]).rstrip(".!?")
            text = f"{first} {rng.choice(_JOINS[ex.language])} {_lower_first(ex.text)}"
            out.append(Example(text=" ".join(text.split()), label=ex.label, language=ex.language, source="compound"))
            out_groups.append(gid)
    return examples + out, groups + out_groups
