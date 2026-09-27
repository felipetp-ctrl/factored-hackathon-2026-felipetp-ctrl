"""Evaluation on an independent message set written by a different author (a Sonnet subagent that never saw the
training corpus), with a second, blind annotator (a Haiku subagent) for label agreement.

    python -m dispute_ops.ml independent prepare   # writes the blind file for the second annotator
    python -m dispute_ops.ml independent evaluate  # kappa, systems on the same messages, cross-author training

Report: `ml/results/independent-v1.md` (+ MLflow experiment `independent-v1`)."""

from __future__ import annotations

import json
import math
import random
from collections import Counter
from functools import partial

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import cohen_kappa_score, confusion_matrix, f1_score

from dispute_ops.language.intent_model import LABELS, IntentModel, features
from dispute_ops.language.nlu import NluContext
from dispute_ops.language.rule_nlu import RuleNlu
from dispute_ops.ml.corpus import REPO, Example, drop_near_duplicates, load_corpus
from dispute_ops.ml.train import keyword_label, wilson

CORPUS_DIR = REPO / "ml" / "corpus"
INDEPENDENT = CORPUS_DIR / "independent-v1.tsv"
BLIND = CORPUS_DIR / "independent-v1.blind.tsv"
ANNOTATOR2 = CORPUS_DIR / "independent-v1.annotator2.tsv"
RESULTS = REPO / "ml" / "results"
SEED = 13


def load_independent() -> list[Example]:
    seen, out = set(), []
    for line in INDEPENDENT.read_text(encoding="utf-8").splitlines():
        if line.strip() and not line.startswith("#"):
            label, lang, text = line.split("\t", 2)
            if text.strip().lower() not in seen:  # exact duplicates written twice count once
                seen.add(text.strip().lower())
                out.append(Example(text.strip(), label.strip(), lang.strip(), "independent"))
    return out


def prepare() -> str:
    items = load_independent()
    order = list(range(len(items)))
    random.Random(SEED).shuffle(order)
    BLIND.write_text("".join(f"{i}\t{items[i].language}\t{items[i].text}\n" for i in order), encoding="utf-8")
    return f"{len(items)} messages → {BLIND.relative_to(REPO)} (id, language, text; shuffled, no labels)"


def _annotator2() -> dict[int, str]:
    out = {}
    for line in ANNOTATOR2.read_text(encoding="utf-8").splitlines():
        if line.strip():
            i, label = line.split("\t")[:2]
            out[int(i)] = label.strip()
    return out


def nlu_label(nlu: RuleNlu, text: str) -> str:
    """What the fallback NLU does with an opening message, mapped to the classifier's labels."""
    r = nlu.interpret(text, NluContext(state="START")).result
    if r.intent == "human":
        return "HUMAN"
    if r.intent == "out_of_scope":
        return "OUT_OF_SCOPE"
    return r.reason_code.value if r.reason_code else "DISPUTE_NO_REASON"


def mcnemar(a: list[bool], b: list[bool]) -> dict:
    """Exact two-sided McNemar test on paired correctness."""
    only_a = sum(x and not y for x, y in zip(a, b))
    only_b = sum(y and not x for x, y in zip(a, b))
    n = only_a + only_b
    p = min(1.0, 2 * sum(math.comb(n, k) for k in range(0, min(only_a, only_b) + 1)) / 2 ** n) if n else 1.0
    return {"only_first_correct": only_a, "only_second_correct": only_b, "p_value": p}


def _fit(x, y):
    vec = TfidfVectorizer(analyzer=partial(features, kinds="wbc"), sublinear_tf=True, min_df=2)
    return vec, LogisticRegression(C=30.0, max_iter=5000).fit(vec.fit_transform(x), y)


def evaluate() -> str:
    import mlflow

    items = load_independent()
    a2 = _annotator2()
    ids = [i for i in range(len(items)) if i in a2]
    intended = [items[i].label for i in ids]
    blind = [a2[i] for i in ids]
    kappa = cohen_kappa_score(intended, blind)
    agree = [i for i in ids if items[i].label == a2[i]]
    gold = [items[i] for i in agree]

    model = IntentModel.load()
    rules, learned = RuleNlu([]), RuleNlu([], intent_model=model)
    systems = {
        "keyword baseline": lambda t: keyword_label(t),
        "fallback NLU, rules only": lambda t: nlu_label(rules, t),
        "fallback NLU, rules + intent-v2": lambda t: nlu_label(learned, t),
        "intent-v2 alone": lambda t: model.predict(t).label,
    }
    res: dict = {}
    for name, fn in systems.items():
        pred = [fn(e.text) for e in gold]
        ok = [p == e.label for p, e in zip(pred, gold)]
        res[name] = {"hits": sum(ok), "n": len(gold), "ci": wilson(sum(ok), len(gold)),
                     "macro_f1": f1_score([e.label for e in gold], pred, average="macro", labels=list(LABELS)),
                     "by_language": {lg: f"{sum(o for o, e in zip(ok, gold) if e.language == lg)}/"
                                         f"{sum(e.language == lg for e in gold)}" for lg in ("es", "pt")},
                     "recall": {lab: f"{sum(o for o, e in zip(ok, gold) if e.label == lab)}/{sum(e.label == lab for e in gold)}"
                                for lab in LABELS},
                     "ok": ok, "pred": pred}
    test = mcnemar(res["fallback NLU, rules + intent-v2"]["ok"], res["fallback NLU, rules only"]["ok"])
    accepted = [(model.predict(e.text), e) for e in gold]
    acc_at_t = [(p, e) for p, e in accepted if p.probability >= model.threshold]

    # Cross-author generalisation: train on one author, test on the other (same model configuration).
    mine = load_corpus()
    overlap_kept, overlap_dropped = drop_near_duplicates(gold, [e.text for e in mine])
    vec, clf = _fit([e.text for e in mine], [e.label for e in mine])
    mine_to_ind = float(np.mean(clf.predict(vec.transform([e.text for e in gold])) == np.array([e.label for e in gold])))
    vec2, clf2 = _fit([e.text for e in gold], [e.label for e in gold])
    ind_to_mine = float(np.mean(clf2.predict(vec2.transform([e.text for e in mine])) == np.array([e.label for e in mine])))

    cm = confusion_matrix([e.label for e in gold], res["fallback NLU, rules + intent-v2"]["pred"], labels=list(LABELS))
    errors = [{"text": e.text, "expected": e.label, "predicted": p}
              for e, p, o in zip(gold, res["fallback NLU, rules + intent-v2"]["pred"], res["fallback NLU, rules + intent-v2"]["ok"])
              if not o]
    summary = {
        "messages": len(items), "annotated": len(ids), "kappa": kappa, "agreement": len(agree) / len(ids),
        "disagreements": [{"text": items[i].text, "writer": items[i].label, "annotator2": a2[i]} for i in ids if items[i].label != a2[i]],
        "gold": len(gold), "gold_labels": dict(Counter(e.label for e in gold)),
        "near_duplicates_of_training_corpus": len(overlap_dropped),
        "systems": {k: {kk: vv for kk, vv in v.items() if kk not in ("ok", "pred")} for k, v in res.items()},
        "mcnemar_learned_vs_rules": test,
        "intent_v2_threshold": {"accepted": len(acc_at_t), "accepted_correct": sum(p.label == e.label for p, e in acc_at_t)},
        "cross_author": {"train_mine_test_independent": mine_to_ind, "train_independent_test_mine": ind_to_mine},
        "confusion_labels": list(LABELS), "confusion": cm.tolist(), "errors": errors,
    }
    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS / "independent-v1.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False, default=float))
    text = markdown(summary)
    (RESULTS / "independent-v1.md").write_text(text)

    (REPO / "mlruns").mkdir(exist_ok=True)
    mlflow.set_tracking_uri(f"sqlite:///{REPO / 'mlruns' / 'mlflow.db'}")
    mlflow.set_experiment("independent-v1")
    with mlflow.start_run(run_name="independent-v1 evaluation"):
        mlflow.log_params({"messages": len(items), "gold": len(gold), "model": model.version})
        mlflow.log_metrics({"kappa": kappa, **{f"acc_{k.replace(' ', '_').replace(',', '').replace('+', 'plus')}": v["hits"] / v["n"]
                                               for k, v in res.items()},
                            "mcnemar_p": test["p_value"], "cross_mine_to_ind": mine_to_ind, "cross_ind_to_mine": ind_to_mine})
    return text


def markdown(s: dict) -> str:
    def f(v):
        return f"{v['hits']}/{v['n']} = {v['hits'] / v['n']:.1%} ({v['ci'][0]:.0%}–{v['ci'][1]:.0%})"
    sy = s["systems"]
    lines = [
        "# Independent message set `independent-v1`", "",
        "> Written by a different author (Claude Sonnet as a Claude Code subagent that never saw the training corpus or "
        "the code), labelled by that author, and re-labelled blind by a second annotator (Claude Haiku subagent, "
        "no labels shown). Opening messages only; each is read as a first customer turn. Offline, no API calls.", "",
        "## Label quality", "",
        f"- {s['messages']} messages; Cohen's κ between writer and blind annotator = **{s['kappa']:.3f}** "
        f"(raw agreement {s['agreement']:.1%}). The {s['gold']} messages both agree on are the gold set below.",
        f"- Near-duplicates of the training corpus (char 3-gram Jaccard ≥ 0.6): {s['near_duplicates_of_training_corpus']}.",
        f"- Gold labels: `{s['gold_labels']}`", "",
        "## Systems on the same gold messages", "",
        "| System | Accuracy (95% CI) | Macro-F1 | es | pt |", "|---|---|---|---|---|",
        *[f"| {k} | {f(v)} | {v['macro_f1']:.3f} | {v['by_language']['es']} | {v['by_language']['pt']} |" for k, v in sy.items()], "",
        f"Paired exact McNemar test, fallback with intent-v2 vs rules only: only intent-v2 right "
        f"{s['mcnemar_learned_vs_rules']['only_first_correct']}, only rules right "
        f"{s['mcnemar_learned_vs_rules']['only_second_correct']}, p = {s['mcnemar_learned_vs_rules']['p_value']:.2g}.", "",
        f"intent-v2 at its 0.60 threshold accepts {s['intent_v2_threshold']['accepted']} of {s['gold']} messages, "
        f"{s['intent_v2_threshold']['accepted_correct']} correctly.", "",
        "### Recall by label", "",
        "| Label | " + " | ".join(sy) + " |", "|---|" + "---|" * len(sy),
        *[f"| {lab} | " + " | ".join(sy[k]["recall"][lab] for k in sy) + " |" for lab in s["confusion_labels"]], "",
        "## Cross-author generalisation (same TF-IDF + LR configuration)", "",
        f"- Trained on our corpus, tested on the independent gold set: {s['cross_author']['train_mine_test_independent']:.1%}",
        f"- Trained on the independent set, tested on our corpus: {s['cross_author']['train_independent_test_mine']:.1%}", "",
        "## Errors of the fallback NLU with intent-v2", "",
        "| Message | Expected | Predicted |", "|---|---|---|",
        *[f"| {e['text'].replace('|', '/')} | {e['expected']} | {e['predicted']} |" for e in s["errors"]], "",
        "## Writer vs blind annotator disagreements", "",
        "| Message | Writer | Annotator 2 |", "|---|---|---|",
        *[f"| {d['text'].replace('|', '/')} | {d['writer']} | {d['annotator2']} |" for d in s["disagreements"]], "",
        "## Limitations", "",
        "- Both annotators are language models; a human review sample is still the reference for label quality.",
        "- Opening messages only; the conversation-level effect is measured in test-v3.", ""]
    return "\n".join(lines)


def main(cmd: str) -> str:
    return prepare() if cmd == "prepare" else evaluate()
