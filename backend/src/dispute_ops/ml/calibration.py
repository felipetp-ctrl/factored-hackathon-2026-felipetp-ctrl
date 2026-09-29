"""Is intent-v2's confidence trustworthy on text it never saw? Calibration and the 0.60 threshold, checked on the
independent set (another author, blind labels; ml/results/independent-v1.md).

The threshold was chosen on out-of-fold predictions of the team-written corpus. This re-checks it out of sample:
reliability (expected calibration error, reliability diagram), coverage and accuracy at each threshold, and the same
split by language. Nothing here changes the model.

    python -m dispute_ops.ml.calibration   (writes ml/results/calibration.md and docs/figures/intent_calibration.png)
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

from dispute_ops.language.intent_model import DEFAULT_PATH, IntentModel

ROOT = Path(__file__).resolve().parents[4]
SET = ROOT / "ml/corpus/independent-v1.tsv"
THRESHOLD = 0.60
BINS = 10


def load() -> list[tuple[str, str, str]]:
    with SET.open(encoding="utf-8") as f:
        return [(r[0], r[1], r[2]) for r in csv.reader(f, delimiter="\t") if r and not r[0].startswith("#")]


def evaluate(model: IntentModel, rows: list[tuple[str, str, str]]) -> dict:
    preds = []
    for label, lang, text in rows:
        p = model.predict(text)
        preds.append({"label": label, "lang": lang, "pred": p.label, "p": p.probability,
                      "p_true": p.probabilities.get(label, 0.0)})
    n = len(preds)
    acc = sum(x["pred"] == x["label"] for x in preds) / n
    brier = sum((1 - x["p_true"]) ** 2 + sum(v ** 2 for k, v in model.predict(t).probabilities.items() if k != x["label"])
                for x, (_, _, t) in zip(preds, rows)) / n
    bins = []
    ece = 0.0
    for b in range(BINS):
        lo, hi = b / BINS, (b + 1) / BINS
        inb = [x for x in preds if lo <= x["p"] < hi or (b == BINS - 1 and x["p"] == 1.0)]
        if not inb:
            continue
        conf = sum(x["p"] for x in inb) / len(inb)
        a = sum(x["pred"] == x["label"] for x in inb) / len(inb)
        ece += len(inb) / n * abs(conf - a)
        bins.append({"lo": lo, "hi": hi, "n": len(inb), "confidence": conf, "accuracy": a})
    curve = []
    for t in [0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9]:
        acc_ = [x for x in preds if x["p"] >= t]
        curve.append({"threshold": t, "coverage": len(acc_) / n,
                      "accuracy": (sum(x["pred"] == x["label"] for x in acc_) / len(acc_)) if acc_ else None})
    by_lang = {}
    for lang in sorted({x["lang"] for x in preds}):
        s = [x for x in preds if x["lang"] == lang]
        a = [x for x in s if x["p"] >= THRESHOLD]
        by_lang[lang] = {"n": len(s), "accuracy": sum(x["pred"] == x["label"] for x in s) / len(s),
                         "coverage": len(a) / len(s), "accuracy_accepted": sum(x["pred"] == x["label"] for x in a) / len(a)}
    return {"n": n, "accuracy": acc, "brier": brier, "ece": ece, "bins": bins, "curve": curve, "by_language": by_lang}


def figure(r: dict, path: Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    from dispute_ops.pipeline.figures import GREEN, GRID, INK, MUTED, PURPLE, _save  # shared style

    fig, (a1, a2) = plt.subplots(1, 2, figsize=(9, 3.6))
    a1.plot([0, 1], [0, 1], color=GRID, lw=1.5)
    xs = [b["confidence"] for b in r["bins"]]
    ys = [b["accuracy"] for b in r["bins"]]
    a1.plot(xs, ys, color=GREEN, lw=2, marker="o", ms=5)
    a1.set_xlim(0, 1)
    a1.set_ylim(0, 1.02)
    a1.set_xlabel("stated confidence")
    a1.set_ylabel("actual accuracy")
    a1.set_title(f"Reliability (ECE {r['ece']:.3f})", fontsize=11)
    ts = [c["threshold"] for c in r["curve"]]
    a2.plot(ts, [c["coverage"] for c in r["curve"]], color=MUTED, lw=2, marker="o", ms=4, label="coverage")
    a2.plot(ts, [c["accuracy"] for c in r["curve"]], color=GREEN, lw=2, marker="o", ms=4, label="accuracy when accepted")
    a2.axvline(THRESHOLD, color=PURPLE, lw=1.5)
    a2.text(THRESHOLD + .01, .05, "0.60 in use", color=INK, fontsize=9)
    a2.set_ylim(0, 1.02)
    a2.set_xlabel("confidence threshold")
    a2.set_title("Coverage against accuracy", fontsize=11)
    a2.legend(frameon=False, fontsize=9, loc="lower left")
    fig.suptitle("intent-v2 on the independent set (another author, blind labels)", x=0.02, ha="left", fontweight="bold")
    _save(fig, path.parent, path.name, f"n = {r['n']} messages never seen in training; model unchanged.")


def main() -> None:
    r = evaluate(IntentModel.load(Path(DEFAULT_PATH)), load())
    out = ROOT / "ml/results"
    (out / "calibration.json").write_text(json.dumps(r, indent=1))
    at = next(c for c in r["curve"] if c["threshold"] == THRESHOLD)
    lines = ["# intent-v2: calibration and threshold, out of sample", "",
             f"Independent set, n = {r['n']} (another author; labels re-checked blind, κ = 1.0; "
             "[independent-v1](independent-v1.md)). Model unchanged; script `dispute_ops.ml.calibration`.", "",
             f"- Accuracy (model alone, no rules): **{r['accuracy']:.1%}**; multi-class Brier score {r['brier']:.3f}.",
             f"- Expected calibration error (10 bins): **{r['ece']:.3f}**.",
             f"- At the 0.60 threshold in use: coverage **{at['coverage']:.1%}**, accuracy when accepted **{at['accuracy']:.1%}**.",
             ("- Above 0.6 every bin is at least as accurate as its stated confidence: the model under-states its confidence, "
              "the safe direction for a threshold." if all(b["accuracy"] >= b["confidence"] for b in r["bins"] if b["lo"] >= 0.6)
              else "- Some bins above 0.6 are less accurate than their stated confidence: see the table."),
             f"- n = {r['n']} is the whole set; the 94.1% reported in independent-v1 is the full fallback reader (rules + model) on "
             "525 of these messages.", "",
             "![Calibration](../../docs/figures/intent_calibration.png)", "",
             "| Threshold | Coverage | Accuracy when accepted |", "|---|---|---|"]
    lines += [f"| {c['threshold']:.1f} | {c['coverage']:.1%} | {c['accuracy']:.1%} |" for c in r["curve"]]
    lines += ["", "| Confidence bin | n | Mean confidence | Accuracy |", "|---|---|---|---|"]
    lines += [f"| {b['lo']:.1f}–{b['hi']:.1f} | {b['n']} | {b['confidence']:.2f} | {b['accuracy']:.2f} |" for b in r["bins"]]
    lines += ["", "| Language | n | Accuracy | Coverage at 0.60 | Accuracy when accepted |", "|---|---|---|---|---|"]
    lines += [f"| {k} | {v['n']} | {v['accuracy']:.1%} | {v['coverage']:.1%} | {v['accuracy_accepted']:.1%} |"
              for k, v in r["by_language"].items()]
    lines += ["", "Below the threshold the keyword rules keep their reading and the policy's own confidence floor (0.6) sends",
              "an unclear reason to a person; the model never decides alone.", ""]
    (out / "calibration.md").write_text("\n".join(lines))
    figure(r, ROOT / "docs/figures/intent_calibration.png")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
