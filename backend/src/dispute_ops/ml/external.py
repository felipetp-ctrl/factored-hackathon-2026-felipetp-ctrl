"""Real customer speech: MInDS-14 (PolyAI, CC BY 4.0), es-ES and pt-PT transcriptions of people calling an e-banking
line with 14 intents (balance, app error, lost card, latest transactions…). Every other text set in this project was
written by a language model; this one was spoken by people and transcribed by ASR, so it carries the noise, the
rambling and the topics the generated sets never had.

The question it answers is the one the fallback reader faces first: **does a message start the dispute intake or
not?** A customer asking about the app must not be asked "which charge do you want to dispute?"; a customer who
says "hay un pago que no reconozco" must be.

    python -m dispute_ops.ml external   # report ml/results/external-minds14.md (+ MLflow experiment)

Protocol (fixed before intent-v3 was trained, see ADR-030):
- labels: the 11 intents that are never a charge dispute take the dataset's human-assigned intent (NOT_DISPUTE);
  the 3 mixed intents (latest_transactions, direct_debit, freeze) were read one by one under a written criterion
  (DISPUTE / NOT_DISPUTE / UNSURE, excluded) and are never used for training;
- intent-v3 = intent-v2's corpus + the 11 clean intents as OUT_OF_SCOPE. Its estimate on topics it has not seen is
  leave-one-intent-out: 11 refits, each scored only on the intent it left out;
- the mixed intents are a test set for every model (real disputes and lost cards, never trained on)."""

from __future__ import annotations

import csv
import json
import tempfile
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from dispute_ops.language.intent_model import IntentModel
from dispute_ops.language.nlu import NluContext
from dispute_ops.language.rule_nlu import RuleNlu
from dispute_ops.ml.corpus import REPO, Example

DATA = REPO / "ml" / "external" / "minds14-es-pt.tsv"
RESULTS = REPO / "ml" / "results"
MIXED = ("latest_transactions", "direct_debit", "freeze")
# Chosen on the Spanish half of the mixed intents only (dev), at a cost ratio fixed beforehand: turning a real
# dispute away costs as much as five unnecessary "which charge?" questions. The Portuguese half is the test.
# The curve for both halves is in the report. ADR-030.
OOS_DISPUTE_GUARD = 0.2
COST_MISSED_DISPUTE = 5
GUARD_GRID = (1.0, 0.3, 0.2, 0.15, 0.1, 0.07, 0.05)
# Routes that do not start the dispute intake. "decline" closes politely; "greeting" asks how to help.
NOT_INTAKE = {"out_of_scope": "redirect", "human": "person", "decline": "closed", "greeting": "asks"}


@dataclass(frozen=True)
class Row:
    row: int
    lang: str
    intent: str
    label: str  # DISPUTE | NOT_DISPUTE | UNSURE
    source: str  # dataset | criterion
    text: str


def load() -> list[Row]:
    lines = [ln for ln in DATA.read_text(encoding="utf-8").splitlines() if not ln.startswith("#")]
    return [Row(int(r["row"]), r["lang"], r["intent"], r["label"], r["label_source"], r["text"])
            for r in csv.DictReader(lines, delimiter="\t")]


def training_rows(rows: list[Row] | None = None, leave_out: str | None = None) -> list[tuple[Example, int]]:
    """The clean intents as OUT_OF_SCOPE examples, grouped by intent (no intent on both sides of a CV split)."""
    rows = load() if rows is None else rows
    clean = sorted({r.intent for r in rows if r.source == "dataset"})
    return [(Example(r.text, "OUT_OF_SCOPE", r.lang, "minds14"), 100_000 + clean.index(r.intent))
            for r in rows if r.source == "dataset" and r.intent != leave_out]


def route(nlu: RuleNlu, text: str) -> str:
    """What the conversation does with an opening message: 'intake' asks which charge to dispute."""
    return NOT_INTAKE.get(nlu.interpret(text, NluContext(state="START")).result.intent, "intake")


def _score(nlu: RuleNlu, rows: list[Row]) -> dict:
    routes = [route(nlu, r.text) for r in rows]
    neg = [(r, x) for r, x in zip(rows, routes) if r.label == "NOT_DISPUTE"]
    pos = [(r, x) for r, x in zip(rows, routes) if r.label == "DISPUTE"]
    return {
        "not_dispute_n": len(neg), "misrouted_to_intake": sum(x == "intake" for _, x in neg),
        "dispute_n": len(pos), "dispute_to_intake": sum(x == "intake" for _, x in pos),
        "routes": dict(Counter(routes)),
        "by_language": {lg: f"{sum(x == 'intake' for r, x in neg if r.lang == lg)}/{sum(r.lang == lg for r, _ in neg)}"
                        for lg in ("es", "pt")},
        "_routes": routes,
    }


def _fit_model(spec_from: dict, x: list[str], y: list[str]) -> IntentModel:
    """Refit the selected configuration of intent-v3 on another training set (same features, C and threshold)."""
    from dispute_ops.ml.train import export
    with tempfile.TemporaryDirectory() as d:
        export("loio", spec_from["feature_kinds"], spec_from["C"], x, y, spec_from["threshold"], Path(d) / "m.json",
               extra={"oos_dispute_guard": spec_from.get("oos_dispute_guard", 1.0)})
        return IntentModel.load(Path(d) / "m.json")


def evaluate() -> str:
    import mlflow

    from dispute_ops.language.intent_model import MODELS_DIR
    from dispute_ops.ml import corpus as C
    from dispute_ops.ml.augment import augment, compound, speech_style
    from dispute_ops.ml.independent import mcnemar
    from dispute_ops.ml.train import VERSIONS, wilson

    rows = load()
    scored = [r for r in rows if r.label != "UNSURE"]
    clean = [r for r in scored if r.source == "dataset"]
    mixed = [r for r in scored if r.source == "criterion"]
    v2, v3 = IntentModel.load(MODELS_DIR / "intent-v2.json"), IntentModel.load(MODELS_DIR / "intent-v3.json")
    readers = {"keyword rules": RuleNlu([]), "rules + intent-v2 (before)": RuleNlu([], intent_model=v2),
               "rules + intent-v3 (after)": RuleNlu([], intent_model=v3)}
    res = {name: {"clean": _score(n, clean), "mixed": _score(n, mixed)} for name, n in readers.items()}

    # intent-v3 on topics it never saw: leave one clean intent out, refit, score that intent only.
    spec = json.loads((MODELS_DIR / "intent-v3.json").read_text())
    base, _ = C.drop_near_duplicates(C.load_corpus(), C.eval_messages())
    corpus, groups = augment(base, VERSIONS["intent-v2"])
    corpus, _ = speech_style(*compound(corpus, groups))
    loio: dict[str, dict] = {}
    loio_routes: dict[int, str] = {}
    loio_models: dict[str, IntentModel] = {}
    for intent in sorted({r.intent for r in clean}):
        ext = [e for e, _ in training_rows(rows, leave_out=intent)]
        m = _fit_model(spec, [e.text for e in corpus + ext], [e.label for e in corpus + ext])
        held = [r for r in clean if r.intent == intent]
        loio_models[intent] = m
        nlu = RuleNlu([], intent_model=m)
        routes = [route(nlu, r.text) for r in held]
        loio_routes.update({r.row: x for r, x in zip(held, routes)})
        v2_routes = [x for r, x in zip(clean, res["rules + intent-v2 (before)"]["clean"]["_routes"]) if r.intent == intent]
        loio[intent] = {"n": len(held), "v3_unseen_intake": sum(x == "intake" for x in routes),
                        "v2_intake": sum(x == "intake" for x in v2_routes)}
    v2_ok = [x != "intake" for x in res["rules + intent-v2 (before)"]["clean"]["_routes"]]
    loio_ok = [loio_routes[r.row] != "intake" for r in clean]
    test = mcnemar(loio_ok, v2_ok)
    n_clean = len(clean)
    loio_mis = sum(not o for o in loio_ok)

    # The guard's operating curve: routes of the mixed intents (per language) and of the left-out clean intents.
    curve = []
    for g in GUARD_GRID:
        v3.oos_dispute_guard = g
        for m in loio_models.values():
            m.oos_dispute_guard = g
        nlu3 = RuleNlu([], intent_model=v3)
        point: dict = {"guard": g, "loio_misrouted": sum(
            route(RuleNlu([], intent_model=loio_models[r.intent]), r.text) == "intake" for r in clean)}
        for lg in ("es", "pt"):
            part = [(r, route(nlu3, r.text)) for r in mixed if r.lang == lg]
            missed = sum(x != "intake" for r, x in part if r.label == "DISPUTE")
            extra = sum(x == "intake" for r, x in part if r.label == "NOT_DISPUTE")
            point[lg] = {"missed_disputes": missed, "disputes": sum(r.label == "DISPUTE" for r, _ in part),
                         "extra_questions": extra, "not_disputes": sum(r.label == "NOT_DISPUTE" for r, _ in part),
                         "cost": COST_MISSED_DISPUTE * missed + extra}
        curve.append(point)
    v3.oos_dispute_guard = spec.get("oos_dispute_guard", 1.0)

    errors = [{"intent": r.intent, "lang": r.lang, "text": r.text[:160], "route": x}
              for r, x in zip(mixed, res["rules + intent-v3 (after)"]["mixed"]["_routes"])
              if (r.label == "DISPUTE") != (x == "intake")]
    summary = {
        "messages": len(rows), "scored": len(scored), "clean": n_clean, "mixed": len(mixed),
        "unsure_excluded": len(rows) - len(scored),
        "mixed_labels": dict(Counter(r.label for r in mixed)),
        "systems": {k: {part: {kk: vv for kk, vv in v.items() if not kk.startswith("_")} for part, v in d.items()}
                    for k, d in res.items()},
        "loio": loio, "loio_misrouted": loio_mis, "loio_ci": wilson(loio_mis, n_clean),
        "v2_misrouted": sum(not o for o in v2_ok), "v2_ci": wilson(sum(not o for o in v2_ok), n_clean),
        "mcnemar_loio_v3_vs_v2": test, "errors_v3_mixed": errors, "guard": spec.get("oos_dispute_guard"),
        "guard_curve": curve,
    }
    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS / "external-minds14.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False, default=float))
    text = markdown(summary)
    (RESULTS / "external-minds14.md").write_text(text)

    (REPO / "mlruns").mkdir(exist_ok=True)
    mlflow.set_tracking_uri(f"sqlite:///{REPO / 'mlruns' / 'mlflow.db'}")
    mlflow.set_experiment("external-minds14")
    with mlflow.start_run(run_name="MInDS-14 es/pt routing"):
        mlflow.log_params({"messages": len(rows), "clean": n_clean, "mixed": len(mixed), "model": v3.version})
        mlflow.log_metrics({"v2_misroute_rate": summary["v2_misrouted"] / n_clean,
                            "v3_loio_misroute_rate": loio_mis / n_clean,
                            "v3_in_sample_misroute_rate": res["rules + intent-v3 (after)"]["clean"]["misrouted_to_intake"] / n_clean,
                            "mcnemar_p": test["p_value"]})
    return text


def markdown(s: dict) -> str:
    def pct(k: int, n: int) -> str:
        return f"{k}/{n} = {k / n:.1%}" if n else "—"
    sy = s["systems"]
    lines = [
        "# Real customer speech: MInDS-14 (es-ES, pt-PT)", "",
        "> Every other text set in this project was written by a language model. MInDS-14 (PolyAI, CC BY 4.0) is people "
        "calling an e-banking line, transcribed by ASR: rambling, mis-heard words, no punctuation. The question is the "
        "first one the free reader answers: **start the dispute intake or not?** Offline, no API calls.", "",
        f"- {s['messages']} messages ({s['clean']} from 11 intents that are never a charge dispute, labelled by the dataset; "
        f"{s['mixed']} from 3 mixed intents read one by one under a written criterion: `{s['mixed_labels']}`; "
        f"{s['unsure_excluded']} unsure excluded).",
        "- Misrouted = a message that is not a dispute is answered with \"which charge do you want to dispute?\". Nothing is "
        "written without a confirmation, so this is wasted turns and a confused customer, not an unsafe action.", "",
        "## Before and after", "",
        "| Reader | Not a dispute, sent to intake (11 clean intents) | es | pt | Mixed intents: not a dispute → intake | Mixed intents: real disputes → intake |",
        "|---|---|---|---|---|---|",
        *[f"| {k} | {pct(v['clean']['misrouted_to_intake'], v['clean']['not_dispute_n'])} | {v['clean']['by_language']['es']} | "
          f"{v['clean']['by_language']['pt']} | {pct(v['mixed']['misrouted_to_intake'], v['mixed']['not_dispute_n'])} | "
          f"{pct(v['mixed']['dispute_to_intake'], v['mixed']['dispute_n'])} |" for k, v in sy.items()], "",
        "The intent-v3 row on the 11 clean intents is **in sample** (it was trained on them). The honest number is the "
        "leave-one-intent-out estimate below; the mixed intents were never trained on by any model.", "",
        "## intent-v3 on topics it has not seen (leave one intent out)", "",
        f"Misrouted: **{pct(s['loio_misrouted'], s['clean'])}** (95% CI {s['loio_ci'][0]:.0%}–{s['loio_ci'][1]:.0%}) vs "
        f"intent-v2 {pct(s['v2_misrouted'], s['clean'])} (CI {s['v2_ci'][0]:.0%}–{s['v2_ci'][1]:.0%}). Paired exact McNemar: "
        f"only v3 right {s['mcnemar_loio_v3_vs_v2']['only_first_correct']}, only v2 right "
        f"{s['mcnemar_loio_v3_vs_v2']['only_second_correct']}, p = {s['mcnemar_loio_v3_vs_v2']['p_value']:.2g}.", "",
        "| Left-out intent | n | intent-v2 → intake | intent-v3 (never saw this intent) → intake |", "|---|---|---|---|",
        *[f"| {k} | {v['n']} | {v['v2_intake']} | {v['v3_unseen_intake']} |" for k, v in s["loio"].items()], "",
        "## The dispute guard: how sure must an out-of-scope reading be?", "",
        f"intent-v3 alone (no guard) still turned real disputes away when a caller mixed a request with an unrecognised "
        f"payment (\"quiero ver mis últimas transacciones, hay un pago que no reconozco\"). An out-of-scope reading is now "
        f"accepted only while the dispute labels together stay below a guard. Chosen on the **Spanish** mixed intents "
        f"(dev) at a cost fixed beforehand — one dispute turned away = {COST_MISSED_DISPUTE} unnecessary questions; the "
        f"**Portuguese** half is the test. Deployed guard: **{s['guard']}**.", "",
        "| Guard | es (dev): disputes turned away | es: extra questions | es cost | pt (test): disputes turned away | pt: extra questions | Clean intents, left out: misrouted |",
        "|---|---|---|---|---|---|---|",
        *[f"| {c['guard']}{' ←' if c['guard'] == s['guard'] else ''} | {c['es']['missed_disputes']}/{c['es']['disputes']} | "
          f"{c['es']['extra_questions']}/{c['es']['not_disputes']} | {c['es']['cost']} | {c['pt']['missed_disputes']}/{c['pt']['disputes']} | "
          f"{c['pt']['extra_questions']}/{c['pt']['not_disputes']} | {c['loio_misrouted']}/{s['clean']} |" for c in s["guard_curve"]], "",
        "## Where intent-v3 is still wrong on the mixed intents", "",
        "| Intent | Lang | Message | Route |", "|---|---|---|---|",
        *[f"| {e['intent']} | {e['lang']} | {e['text'].replace('|', '/')} | {e['route']} |" for e in s["errors_v3_mixed"]], "",
        "## Limitations", "",
        "- European Spanish and Portuguese (es-ES, pt-PT); the bank's customers are in Mexico, Colombia and Argentina, and "
        "the app's Portuguese is Brazilian. Vocabulary differs (\"domiciliación\", \"débito direto\", \"telemóvel\").",
        "- The mixed-intent labels were assigned by the coding assistant under the criterion in `ml/external/README.md`, "
        "not by a human; the 11 clean intents carry only the dataset's own labels.",
        "- Opening messages only, read by the free reader. The Claude path was not run on this set (API credit is kept "
        "for the judges, ADR-026).", ""]
    return "\n".join(lines)
