"""Component-level evaluation: each stage of the pipeline scored against deterministic labels
(the scenario ground truth) and against a rule baseline on the SAME customer messages."""

from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any

from dispute_ops.evaluation.keyword_baseline import classify_reason, is_out_of_scope, wants_human
from dispute_ops.evaluation.runner import ScenarioResult
from dispute_ops.language.gateway import detect_injection, detect_language
from dispute_ops.language.intent_model import IntentModel
from dispute_ops.language.nlu import NluContext
from dispute_ops.language.rule_nlu import RuleNlu

# Fallback NLU, keyword rules only and with the learned classifier (ADR-019); the merchant vocabulary does not
# affect these metrics.
_RULES = RuleNlu([])
_LEARNED = RuleNlu([], intent_model=IntentModel.load())


def _rule_intents(msgs: list[str], nlu: RuleNlu = _RULES) -> list:
    """Fallback NLU read of each message; the first as an opening, later ones as answers to the reason question."""
    return [nlu.interpret(m, NluContext(state="START" if i == 0 else "CLASSIFY")).result for i, m in enumerate(msgs)]


def _rate(hits: int, n: int) -> dict[str, Any]:
    return {"value": round(hits / n, 3) if n else None, "n": n, "hits": hits}


def _customer_msgs(r: ScenarioResult) -> list[str]:
    return [t for role, t in r.transcript if role == "customer"]


def component_report(results: list[ScenarioResult]) -> dict[str, Any]:
    rs = [r for r in results if r.system == "proposed" and r.error is None]
    out: dict[str, Any] = {}

    # 1. Dispute reason: first reason the NLU commits to vs. keyword baseline on the customer's messages so far.
    nlu_hits = kw_hits = rule_hits = learned_hits = n = 0
    confusion: dict[str, Counter] = defaultdict(Counter)
    for r in rs:
        if not r.expected_reason_code or r.category == "adversarial":
            continue
        n += 1
        msgs = _customer_msgs(r)
        nlu_pred = next((t["reason_code"] for t in r.nlu_turns if t.get("reason_code")), None)
        k = next((i for i, t in enumerate(r.nlu_turns) if t.get("reason_code")), len(msgs) - 1)
        kw_pred = classify_reason(" ".join(msgs[: k + 1]))
        nlu_hits += nlu_pred == r.expected_reason_code
        kw_hits += (kw_pred.value if kw_pred else None) == r.expected_reason_code
        rule_pred = next((x.reason_code.value for x in _rule_intents(msgs[: k + 1]) if x.reason_code), None)
        rule_hits += rule_pred == r.expected_reason_code
        learned_pred = next((x.reason_code.value for x in _rule_intents(msgs[: k + 1], _LEARNED) if x.reason_code), None)
        learned_hits += learned_pred == r.expected_reason_code
        confusion[r.expected_reason_code][nlu_pred or "none"] += 1
    out["reason_code_accuracy"] = {"nlu_claude_haiku": _rate(nlu_hits, n), "keyword_baseline": _rate(kw_hits, n),
                                   "rule_nlu_fallback": _rate(rule_hits, n),
                                   "rule_nlu_learned": _rate(learned_hits, n), "nlu_confusion": {k: dict(v) for k, v in confusion.items()}}

    # 2. Out-of-scope detection on the first customer message.
    tp = fp = fn = tn = ktp = kfp = kfn = ktn = rtp = rfp = rfn = rtn = ltp = lfp = lfn = ltn = 0
    for r in rs:
        if not r.nlu_turns:
            continue
        truth = r.category == "out_of_scope"
        pred = r.nlu_turns[0].get("intent") == "out_of_scope"
        kpred = is_out_of_scope(_customer_msgs(r)[0])
        rpred = _rule_intents(_customer_msgs(r)[:1])[0].intent == "out_of_scope"
        rtp += truth and rpred; rfp += (not truth) and rpred; rfn += truth and not rpred; rtn += (not truth) and not rpred
        lpred = _rule_intents(_customer_msgs(r)[:1], _LEARNED)[0].intent == "out_of_scope"
        ltp += truth and lpred; lfp += (not truth) and lpred; lfn += truth and not lpred; ltn += (not truth) and not lpred
        tp += truth and pred; fp += (not truth) and pred; fn += truth and not pred; tn += (not truth) and not pred
        ktp += truth and kpred; kfp += (not truth) and kpred; kfn += truth and not kpred; ktn += (not truth) and not kpred
    out["out_of_scope_detection"] = {
        "nlu": {"recall": _rate(tp, tp + fn), "false_positive_rate": _rate(fp, fp + tn)},
        "keyword_baseline": {"recall": _rate(ktp, ktp + kfn), "false_positive_rate": _rate(kfp, kfp + ktn)},
        "rule_nlu_fallback": {"recall": _rate(rtp, rtp + rfn), "false_positive_rate": _rate(rfp, rfp + rtn)},
        "rule_nlu_learned": {"recall": _rate(ltp, ltp + lfn), "false_positive_rate": _rate(lfp, lfp + ltn)},
    }

    # 3. Explicit human request.
    hr = [r for r in rs if r.expected_handoff_reason == "customer_requested_human"]
    out["human_request_detection"] = {
        "nlu": _rate(sum(any(t.get("intent") == "human" for t in r.nlu_turns) for r in hr), len(hr)),
        "keyword_baseline": _rate(sum(any(wants_human(m) for m in _customer_msgs(r)) for r in hr), len(hr)),
        "rule_nlu_fallback": _rate(sum(any(x.intent == "human" for x in _rule_intents(_customer_msgs(r))) for r in hr), len(hr)),
        "rule_nlu_learned": _rate(sum(any(x.intent == "human" for x in _rule_intents(_customer_msgs(r), _LEARNED))
                                      for r in hr), len(hr)),
    }

    # 4. Transaction identification (NLU extraction + deterministic search) where a transaction is expected.
    ti = [r for r in rs if r.expected_transaction and r.category != "adversarial"]
    out["transaction_identification"] = _rate(sum(r.identified_transaction == r.expected_transaction for r in ti), len(ti))

    # 5. Gateway: injection flags (rule-based) and language detection, on every customer message.
    inj = [m for r in rs if r.category == "adversarial" and "inject" in r.scenario_id for m in _customer_msgs(r)[:1]]
    clean = [m for r in rs if r.category in ("normal", "ineligible", "out_of_scope") for m in _customer_msgs(r)]
    out["injection_flag"] = {"true_positive_rate": _rate(sum(bool(detect_injection(m)) for m in inj), len(inj)),
                             "false_positive_rate": _rate(sum(bool(detect_injection(m)) for m in clean), len(clean))}
    lang_msgs = [(m, r.language) for r in rs if "mixed" not in r.scenario_id for m in _customer_msgs(r)]
    decided = [(detect_language(m), lang) for m, lang in lang_msgs]
    out["language_detection_rules"] = {
        "accuracy_when_decided": _rate(sum(p == lang for p, lang in decided if p), sum(1 for p, _ in decided if p)),
        "undecided_share": _rate(sum(1 for p, _ in decided if p is None), len(decided)),
        "nlu_language_accuracy": _rate(sum(t.get("language") == r.language for r in rs if "mixed" not in r.scenario_id
                                           for t in r.nlu_turns[:1]),
                                       sum(1 for r in rs if "mixed" not in r.scenario_id and r.nlu_turns)),
    }
    return out


def component_markdown(rep: dict[str, Any]) -> str:
    def f(x: dict) -> str:
        return "—" if x["value"] is None else f"{x['value']:.1%} ({x['hits']}/{x['n']})"
    rc, oos, hr = rep["reason_code_accuracy"], rep["out_of_scope_detection"], rep["human_request_detection"]
    lines = [
        "## Component evaluation (proposed system)", "",
        "| Component | Claude Haiku NLU | Keyword baseline | Rule NLU (fallback, rules only) | Rule NLU + intent-v2 (fallback) |",
        "|---|---|---|---|---|",
        f"| Dispute reason accuracy | {f(rc['nlu_claude_haiku'])} | {f(rc['keyword_baseline'])} | {f(rc['rule_nlu_fallback'])} | {f(rc['rule_nlu_learned'])} |",
        f"| Out-of-scope recall | {f(oos['nlu']['recall'])} | {f(oos['keyword_baseline']['recall'])} | {f(oos['rule_nlu_fallback']['recall'])} | {f(oos['rule_nlu_learned']['recall'])} |",
        f"| Out-of-scope false-positive rate | {f(oos['nlu']['false_positive_rate'])} | {f(oos['keyword_baseline']['false_positive_rate'])} | {f(oos['rule_nlu_fallback']['false_positive_rate'])} | {f(oos['rule_nlu_learned']['false_positive_rate'])} |",
        f"| Human-request detection | {f(hr['nlu'])} | {f(hr['keyword_baseline'])} | {f(hr['rule_nlu_fallback'])} | {f(hr['rule_nlu_learned'])} |",
        "", "| Component | Result |", "|---|---|",
        f"| Transaction identification (NLU + search) | {f(rep['transaction_identification'])} |",
        f"| Injection flag true-positive rate (rules) | {f(rep['injection_flag']['true_positive_rate'])} |",
        f"| Injection flag false-positive rate (rules) | {f(rep['injection_flag']['false_positive_rate'])} |",
        f"| Language rules accuracy when decided | {f(rep['language_detection_rules']['accuracy_when_decided'])} |",
        f"| Language rules undecided share | {f(rep['language_detection_rules']['undecided_share'])} |",
        f"| NLU language accuracy (first turn) | {f(rep['language_detection_rules']['nlu_language_accuracy'])} |",
        "", f"Reason confusion (expected → NLU prediction): `{rc['nlu_confusion']}`",
    ]
    return "\n".join(lines) + "\n"
