"""Train, select and export the intent classifier; every candidate is an MLflow run.

Selection protocol (no evaluation message is used before the final scoring):
1. drop corpus lines that are near-duplicates of any evaluation message;
2. 5-fold stratified cross-validation on the corpus → out-of-fold predictions for every candidate;
3. pick the candidate with the best out-of-fold macro-F1; pick the confidence threshold on its out-of-fold
   predictions (lowest threshold whose accepted predictions are ≥ 95% accurate, never below the policy's 0.6);
4. refit on the whole corpus, export to JSON, then score once on the held-out evaluation messages."""

from __future__ import annotations

import json
import re
import math
import time
from collections import Counter
from dataclasses import dataclass
from functools import partial
from pathlib import Path
from typing import Callable

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, confusion_matrix, f1_score
from sklearn.model_selection import StratifiedGroupKFold

from dispute_ops.language.intent_model import LABELS, MODELS_DIR, IntentModel, features
from dispute_ops.language.keywords import classify_reason, is_out_of_scope, wants_human
from dispute_ops.ml import corpus as C
from dispute_ops.ml.augment import augment

VERSIONS = {  # version -> compositional augmentation per corpus sentence (0 = none)
    "intent-v1": 0,
    "intent-v2": 2,
}
SEED = 42
TARGET_ACCEPTED_ACCURACY = 0.95
POLICY_MIN_CONFIDENCE = 0.6  # policy R-HO-LOWCONF hands off below this
RESULTS = C.REPO / "ml" / "results"


def keyword_label(text: str) -> str:
    """The keyword baseline mapped to the classifier's labels."""
    if wants_human(text):
        return "HUMAN"
    if (reason := classify_reason(text)) is not None:
        return reason.value
    if is_out_of_scope(text):
        return "OUT_OF_SCOPE"
    return "DISPUTE_NO_REASON"


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return (math.nan, math.nan)
    p, d = k / n, 1 + z * z / n
    c, h = (p + z * z / (2 * n)) / d, z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0.0, c - h), min(1.0, c + h))


def ece(conf: np.ndarray, correct: np.ndarray, bins: int = 10) -> float:
    edges = np.linspace(0, 1, bins + 1)
    total = 0.0
    for lo, hi in zip(edges[:-1], edges[1:]):
        m = (conf > lo) & (conf <= hi)
        if m.any():
            total += m.mean() * abs(correct[m].mean() - conf[m].mean())
    return float(total)


@dataclass
class Candidate:
    name: str
    params: dict
    fit_predict: Callable[[list[str], list[str], list[str]], tuple[list[str], np.ndarray]]  # -> labels, confidence


def _tfidf_lr(kinds: str, c: float):
    def make():
        vec = TfidfVectorizer(analyzer=partial(features, kinds=kinds), sublinear_tf=True, min_df=2)
        clf = LogisticRegression(C=c, max_iter=5000)
        return vec, clf

    def fit_predict(xtr, ytr, xte):
        vec, clf = make()
        clf.fit(vec.fit_transform(xtr), ytr)
        proba = clf.predict_proba(vec.transform(xte))
        return list(clf.classes_[proba.argmax(1)]), proba.max(1)
    return make, fit_predict


def _keyword_fit_predict(xtr, ytr, xte):
    return [keyword_label(x) for x in xte], np.ones(len(xte))


def _embedding_candidate() -> Candidate | None:
    """multilingual-e5-small sentence embeddings + logistic regression (offline comparison only)."""
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError:
        return None
    model = SentenceTransformer("intfloat/multilingual-e5-small")
    cache: dict[str, np.ndarray] = {}

    def embed(texts):
        missing = [t for t in texts if t not in cache]
        if missing:
            for t, v in zip(missing, model.encode([f"query: {t}" for t in missing], normalize_embeddings=True)):
                cache[t] = v
        return np.stack([cache[t] for t in texts])

    def fit_predict(xtr, ytr, xte):
        clf = LogisticRegression(C=10.0, max_iter=5000).fit(embed(xtr), ytr)
        proba = clf.predict_proba(embed(xte))
        return list(clf.classes_[proba.argmax(1)]), proba.max(1)
    return Candidate("e5-small+lr", {"encoder": "intfloat/multilingual-e5-small", "C": 10.0}, fit_predict)


def candidates(with_embeddings: bool) -> list[Candidate]:
    out = [Candidate("keyword-baseline", {}, _keyword_fit_predict)]
    for kinds in ("wbc", "wb", "c"):
        for c in (1.0, 3.0, 10.0, 30.0):
            out.append(Candidate(f"tfidf[{kinds}]+lr C={c:g}", {"feature_kinds": kinds, "C": c}, _tfidf_lr(kinds, c)[1]))
    if with_embeddings and (emb := _embedding_candidate()):
        out.append(emb)
    return out


def out_of_fold(cand: Candidate, x: list[str], y: list[str], groups: list[int]) -> tuple[list[str], np.ndarray, float]:
    """Folds keep every variant of a corpus sentence together (no augmented twin on both sides)."""
    pred, conf = [""] * len(x), np.zeros(len(x))
    started = time.perf_counter()
    for tr, te in StratifiedGroupKFold(5, shuffle=True, random_state=SEED).split(x, y, groups):
        p, c = cand.fit_predict([x[i] for i in tr], [y[i] for i in tr], [x[i] for i in te])
        for i, pi, ci in zip(te, p, c):
            pred[i], conf[i] = pi, ci
    return pred, conf, time.perf_counter() - started


def choose_threshold(conf: np.ndarray, correct: np.ndarray) -> tuple[float, list[dict]]:
    curve = []
    for t in np.round(np.arange(0.2, 0.96, 0.05), 2):
        acc = conf >= t
        curve.append({"threshold": float(t), "coverage": float(acc.mean()),
                      "accepted_accuracy": float(correct[acc].mean()) if acc.any() else math.nan})
    ok = [c["threshold"] for c in curve if c["accepted_accuracy"] >= TARGET_ACCEPTED_ACCURACY]
    return max(POLICY_MIN_CONFIDENCE, min(ok) if ok else 0.95), curve


def export(version: str, kinds: str, c: float, x: list[str], y: list[str], threshold: float, path: Path,
           reference_conf: np.ndarray | None = None) -> dict:
    vec = TfidfVectorizer(analyzer=partial(features, kinds=kinds), sublinear_tf=True, min_df=2)
    clf = LogisticRegression(C=c, max_iter=5000).fit(vec.fit_transform(x), y)
    vocab = {k: int(v) for k, v in vec.vocabulary_.items()}
    spec = {
        "version": version, "feature_kinds": kinds, "threshold": threshold, "labels": list(clf.classes_),
        "vocabulary": vocab, "idf": [round(float(v), 6) for v in vec.idf_],
        "coef": [[round(float(v), 5) for v in row] for row in clf.coef_],
        "intercept": [round(float(v), 5) for v in clf.intercept_],
        "trained_on": {"examples": len(x), "labels": dict(Counter(y))}, "C": c,
    }
    if reference_conf is not None:  # drift reference for production monitoring (PSI over 10 bins)
        spec["reference_confidence_hist"] = np.histogram(np.clip(reference_conf, 0, 1 - 1e-9), bins=10, range=(0, 1))[0].tolist()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(spec, ensure_ascii=False, separators=(",", ":")))
    # Parity: the pure-Python runtime must reproduce sklearn's probabilities.
    runtime = IntentModel(spec)
    sk = clf.predict_proba(vec.transform(x[:200]))
    diff = max(abs(runtime.predict(t).probabilities[lab] - sk[i][j])
               for i, t in enumerate(x[:200]) for j, lab in enumerate(clf.classes_))
    spec["parity_max_abs_diff"] = diff
    return spec


def score_heldout(model: IntentModel) -> dict:
    out: dict = {}
    for name, items in (("test-v2 reason", C.heldout_reason_v2()), ("test-v1 reason", C.heldout_reason_v1()),
                        ("test-v2 run 3 reason (unseen)", C.heldout_reason_v2(C.TEST_V2_RUN3))):
        preds = [model.predict(e.text) for e in items]
        hits = sum(p.label == e.label for p, e in zip(preds, items))
        accepted = [(p, e) for p, e in zip(preds, items) if p.probability >= model.threshold]
        kw = sum(keyword_label(e.text) == e.label for e in items)
        out[name] = {
            "n": len(items), "labels": C.describe(items),
            "model_hits": hits, "model_ci": wilson(hits, len(items)),
            "keyword_hits": kw, "keyword_ci": wilson(kw, len(items)),
            "accepted": len(accepted), "accepted_hits": sum(p.label == e.label for p, e in accepted),
            "errors": [{"text": e.text[:140], "expected": e.label, "predicted": p.label, "p": round(p.probability, 3)}
                       for p, e in zip(preds, items) if p.label != e.label],
            "by_language": {lang: f"{sum(p.label == e.label for p, e in zip(preds, items) if e.language == lang)}/"
                                  f"{sum(1 for e in items if e.language == lang)}" for lang in ("es", "pt")},
        }
    scope = C.heldout_scope_v2()
    pred = [model.predict(e.text) for e in scope]
    is_oos = [p.label == "OUT_OF_SCOPE" and p.probability >= model.threshold for p in pred]
    kw_oos = [keyword_label(e.text) == "OUT_OF_SCOPE" for e in scope]
    truth = [e.label == "OUT_OF_SCOPE" for e in scope]
    for key, flags in (("model", is_oos), ("keyword", kw_oos)):
        tp = sum(f and t for f, t in zip(flags, truth))
        fp = sum(f and not t for f, t in zip(flags, truth))
        out[f"test-v2 out-of-scope ({key})"] = {"recall": f"{tp}/{sum(truth)}", "false_positives": f"{fp}/{len(truth) - sum(truth)}"}
    return out


def _fmt_ci(k: int, n: int) -> str:
    lo, hi = wilson(k, n)
    return f"{k}/{n} = {k / n:.1%} (95% CI {lo:.0%}–{hi:.0%})"


def run(version: str = "intent-v2", with_embeddings: bool = False, tracking_uri: str | None = None) -> dict:
    import mlflow

    mlflow.set_tracking_uri(tracking_uri or f"sqlite:///{C.REPO / 'mlruns' / 'mlflow.db'}")
    (C.REPO / "mlruns").mkdir(exist_ok=True)
    mlflow.set_experiment("intent-classifier")
    model_path = MODELS_DIR / f"{version}.json"

    raw = C.load_corpus()
    base, dropped = C.drop_near_duplicates(raw, C.eval_messages())
    data, groups = augment(base, VERSIONS[version]) if VERSIONS[version] else (base, list(range(len(base))))
    x, y = [e.text for e in data], [e.label for e in data]
    results = []
    for cand in candidates(with_embeddings):
        pred, conf, secs = out_of_fold(cand, x, y, groups)
        correct = np.array([p == t for p, t in zip(pred, y)])
        row = {"name": cand.name, "params": cand.params, "accuracy": accuracy_score(y, pred),
               "macro_f1": f1_score(y, pred, average="macro"), "ece": ece(conf, correct), "cv_seconds": secs,
               "per_class_recall": {lab: float(np.mean([p == lab for p, t in zip(pred, y) if t == lab])) for lab in LABELS},
               "pred": pred, "conf": conf, "correct": correct}
        results.append(row)
        with mlflow.start_run(run_name=f"{version} {cand.name}"):
            mlflow.log_params({"version": version, "candidate": cand.name, **cand.params, "corpus_examples": len(x),
                               "augmentation_per_sentence": VERSIONS[version],
                               "corpus_dropped_near_duplicates": len(dropped), "cv": "5-fold stratified group", "seed": SEED})
            mlflow.log_metrics({"cv_accuracy": row["accuracy"], "cv_macro_f1": row["macro_f1"], "cv_ece": row["ece"],
                                **{f"cv_recall_{k}": v for k, v in row["per_class_recall"].items()}})

    learned = [r for r in results if r["name"] != "keyword-baseline" and not r["name"].startswith("e5")]
    best = max(learned, key=lambda r: (round(r["macro_f1"], 4), -r["params"]["C"]))
    threshold, curve = choose_threshold(best["conf"], best["correct"])
    spec = export(version, best["params"]["feature_kinds"], best["params"]["C"], x, y, threshold, model_path, best["conf"])
    model = IntentModel.load(model_path)
    started = time.perf_counter()
    for t in x:
        model.predict(t)
    latency_ms = (time.perf_counter() - started) * 1000 / len(x)
    held = score_heldout(model)
    cm = confusion_matrix(y, best["pred"], labels=list(LABELS))

    with mlflow.start_run(run_name=f"{version} (selected: {best['name']})"):
        mlflow.log_params({"version": version, **best["params"], "selected_from": len(learned), "threshold": threshold})
        mlflow.log_metrics({"cv_macro_f1": best["macro_f1"], "cv_accuracy": best["accuracy"], "cv_ece": best["ece"],
                            "runtime_latency_ms": latency_ms, "artifact_kb": model_path.stat().st_size / 1024,
                            "vocabulary": len(spec["vocabulary"]), "parity_max_abs_diff": spec["parity_max_abs_diff"],
                            **{"heldout_" + re.sub(r"\W+", "_", k).strip("_") + "_acc": v["model_hits"] / v["n"]
                               for k, v in held.items() if "reason" in k}})
        mlflow.log_artifact(str(model_path))

    summary = {"version": version, "augmentation_per_sentence": VERSIONS[version],
               "corpus": {"examples": len(raw), "used": len(base), "training_examples": len(x), "dropped_near_duplicates": [
        {"corpus": d[0].text, "eval_message": d[1], "jaccard": round(d[2], 3)} for d in dropped], "labels": C.describe(data)},
        "candidates": [{k: v for k, v in r.items() if k not in ("pred", "conf", "correct")} for r in results],
        "selected": best["name"], "threshold": threshold, "threshold_curve": curve,
        "oof_accepted": {"coverage": float((best["conf"] >= threshold).mean()),
                         "accuracy": float(best["correct"][best["conf"] >= threshold].mean())},
        "confusion_labels": list(LABELS), "confusion": cm.tolist(), "heldout": held,
        "runtime": {"latency_ms_per_message": latency_ms, "artifact_kb": model_path.stat().st_size / 1024,
                    "vocabulary": len(spec["vocabulary"]), "parity_max_abs_diff": spec["parity_max_abs_diff"]}}
    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS / f"{version}.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False, default=float))
    (RESULTS / f"{version}.md").write_text(markdown(summary))
    return summary


def markdown(s: dict) -> str:
    cands = sorted(s["candidates"], key=lambda r: -r["macro_f1"])
    lines = [
        f"# Intent classifier `{s['version']}` — training and evaluation", "",
        "> Offline. Corpus is **team-generated** (written by the coding assistant, labelled by construction). "
        "Held-out messages come from the frozen test-v2/test-v1 runs (LLM-simulated customers) and are labelled by "
        "the scenario ground truth. No evaluation message was used for fitting, model selection or the threshold.", "",
        "## Data", "",
        f"- Corpus: {s['corpus']['examples']} messages (ES/PT), {s['corpus']['used']} used after dropping "
        f"{len(s['corpus']['dropped_near_duplicates'])} near-duplicate(s) of evaluation messages (char 3-gram Jaccard ≥ 0.6); "
        f"{s['corpus']['training_examples']} training examples after compositional augmentation "
        f"({s['augmentation_per_sentence']} per sentence).",
        f"- Labels: `{s['corpus']['labels']}`", "",
        "## Model selection — 5-fold stratified cross-validation on the corpus, grouped by source sentence", "",
        "| Candidate | Accuracy | Macro-F1 | ECE | CV time (s) |", "|---|---|---|---|---|",
        *[f"| {r['name']}{' **(selected)**' if r['name'] == s['selected'] else ''} | {r['accuracy']:.3f} | "
          f"{r['macro_f1']:.3f} | {r['ece']:.3f} | {r['cv_seconds']:.1f} |" for r in cands], "",
        "Only TF-IDF + logistic regression candidates are eligible for deployment: they export to a JSON the API "
        "scores in pure Python. The sentence-embedding candidate (when run with `--embeddings`) needs PyTorch and a "
        "470 MB encoder, which the free API instance (512 MB RAM) cannot hold; it is trained for comparison only.", "",
        "Per-class out-of-fold recall of the selected model:", "",
        "| " + " | ".join(s["confusion_labels"]) + " |", "|" + "---|" * len(s["confusion_labels"]),
        "| " + " | ".join(f"{next(r for r in s['candidates'] if r['name'] == s['selected'])['per_class_recall'][lab]:.2f}"
                          for lab in s["confusion_labels"]) + " |", "",
        "## Confidence threshold", "",
        f"Chosen on out-of-fold predictions: lowest threshold with ≥ 95% accuracy on accepted predictions, never below "
        f"the policy's 0.6 hand-off floor → **{s['threshold']:.2f}** (accepts {s['oof_accepted']['coverage']:.1%} of "
        f"corpus messages at {s['oof_accepted']['accuracy']:.1%} accuracy). Below it the rule NLU's reading stands.", "",
        "| Threshold | Coverage | Accuracy on accepted |", "|---|---|---|",
        *[f"| {c['threshold']:.2f} | {c['coverage']:.1%} | {c['accepted_accuracy']:.1%} |" for c in s["threshold_curve"]], "",
        "## Held-out evaluation (scored after selection)", "",
        *([] if s["version"] == "intent-v1" else [
            "> **Post-hoc caveat.** The test-v2 and test-v1 messages were read during the intent-v1 error analysis that "
            "motivated this version's augmentation, so their numbers are optimistic. `test-v2 run 3 (unseen)` holds "
            "messages from the credit-aborted third run that were never opened; `test-v3` (frozen before this version "
            "was trained) is the clean held-out set once it is run.", ""]),
        f"| Set | n | Labels | {s['version']} | Keyword baseline | {s['version']} accepted at threshold | By language ({s['version']}) |",
        "|---|---|---|---|---|---|---|",
    ]
    for name, h in s["heldout"].items():
        if "reason" in name:
            lines.append(f"| {name} | {h['n']} | `{h['labels']}` | {_fmt_ci(h['model_hits'], h['n'])} | "
                         f"{_fmt_ci(h['keyword_hits'], h['n'])} | {h['accepted_hits']}/{h['accepted']} | "
                         f"es {h['by_language']['es']} · pt {h['by_language']['pt']} |")
    lines += ["", "| Out-of-scope detection, test-v2 first messages | Recall | False positives |", "|---|---|---|"]
    lines += [f"| {k.split('(')[1][:-1]} | {v['recall']} | {v['false_positives']} |"
              for k, v in s["heldout"].items() if "out-of-scope" in k]
    lines += ["", f"### Held-out errors ({s['version']})", "", "| Set | Message | Expected | Predicted | p |", "|---|---|---|---|---|"]
    for name, h in s["heldout"].items():
        for e in h.get("errors", []):
            lines.append(f"| {name} | {e['text'].replace('|', '/')} | {e['expected']} | {e['predicted']} | {e['p']} |")
    r = s["runtime"]
    lines += ["", "## Runtime", "",
              f"- Pure-Python scoring from JSON: {r['latency_ms_per_message']:.2f} ms per message, {r['artifact_kb']:.0f} KB, "
              f"{r['vocabulary']:,} features; max |p_runtime − p_sklearn| = {r['parity_max_abs_diff']:.1e}.",
              "- No ML library in the API image; `scikit-learn` and `mlflow` live in the `ml` dependency group.", "",
              "## Limitations", "",
              "- The corpus author also wrote the system and saw a few evaluation transcripts while reviewing reports; "
              "the near-duplicate filter bounds verbatim leakage, not stylistic familiarity.",
              "- Held-out reason labels cover four of the six reasons (no DUPLICATE or FRAUD_CP in test-v2) and repeat "
              "scenarios across runs (n counts messages, not independent scenarios).",
              "- Held-out customers are simulated by an LLM, not real customers; Portuguese is not in the organizer data.", ""]
    return "\n".join(lines)
