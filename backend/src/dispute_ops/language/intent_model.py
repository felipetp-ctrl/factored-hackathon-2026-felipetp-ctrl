"""Learned intent/reason classifier (`intent-v1`), scored in pure Python.

Trained offline (`make train`, `dispute_ops.ml`) as TF-IDF over word and character n-grams followed by a
multinomial logistic regression; exported to JSON (vocabulary, idf, coefficients) so the API needs no ML
library at runtime. `features` is shared by training and serving, so both see exactly the same inputs.

It only reads text: a label and a probability. The rule NLU decides whether to use it (confidence threshold
chosen on cross-validation) and the policy still decides what happens."""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from pathlib import Path

from dispute_ops.language.keywords import _norm

MODELS_DIR = Path(__file__).parent / "models"
DEFAULT_PATH = MODELS_DIR / "intent-v2.json"
REASON_LABELS = ("FRAUD_CNP", "FRAUD_CP", "DUPLICATE", "INCORRECT_AMOUNT", "NOT_RECEIVED", "CANCELLED_RECURRING")
LABELS = (*REASON_LABELS, "OUT_OF_SCOPE", "HUMAN", "DISPUTE_NO_REASON")

_TOKEN = re.compile(r"[a-z]+|\d+")
_DIGITS = re.compile(r"\d")


def features(text: str, kinds: str = "wbc") -> list[str]:
    """Word unigrams (w), word bigrams (b) and character 2–5-grams inside word boundaries (c), on lower-cased,
    accent-free text with digits collapsed to 0 (amounts and dates vary; their presence is what matters)."""
    t = _DIGITS.sub("0", _norm(text))
    words = _TOKEN.findall(t)
    out = [f"w:{w}" for w in words] if "w" in kinds else []
    if "b" in kinds:
        out += [f"b:{a}_{b}" for a, b in zip(words, words[1:])]
    if "c" in kinds:
        for w in words:
            padded = f" {w} "
            for n in range(2, 6):
                out += [f"c:{padded[i:i + n]}" for i in range(len(padded) - n + 1)]
    return out


@dataclass(frozen=True)
class Prediction:
    label: str
    probability: float
    probabilities: dict[str, float]


class IntentModel:
    def __init__(self, spec: dict) -> None:
        self.version: str = spec["version"]
        self.kinds: str = spec["feature_kinds"]
        self.threshold: float = spec["threshold"]
        self.labels: list[str] = spec["labels"]
        self.vocab: dict[str, int] = spec["vocabulary"]
        self.idf: list[float] = spec["idf"]
        self.coef: list[list[float]] = spec["coef"]  # one row per label
        self.intercept: list[float] = spec["intercept"]

    @classmethod
    def load(cls, path: Path = DEFAULT_PATH) -> IntentModel:
        return cls(json.loads(path.read_text()))

    def vector(self, text: str) -> dict[int, float]:
        """Sublinear TF-IDF, L2-normalised — the same transform as the training vectorizer."""
        counts: dict[int, int] = {}
        for f in features(text, self.kinds):
            j = self.vocab.get(f)
            if j is not None:
                counts[j] = counts.get(j, 0) + 1
        v = {j: (1.0 + math.log(c)) * self.idf[j] for j, c in counts.items()}
        norm = math.sqrt(sum(x * x for x in v.values()))
        return {j: x / norm for j, x in v.items()} if norm else {}

    def predict(self, text: str) -> Prediction:
        v = self.vector(text)
        scores = [b + sum(row[j] * x for j, x in v.items()) for row, b in zip(self.coef, self.intercept)]
        top = max(scores)
        exp = [math.exp(s - top) for s in scores]
        total = sum(exp)
        probs = {label: e / total for label, e in zip(self.labels, exp)}
        label = max(probs, key=probs.__getitem__)
        return Prediction(label=label, probability=probs[label], probabilities=probs)
