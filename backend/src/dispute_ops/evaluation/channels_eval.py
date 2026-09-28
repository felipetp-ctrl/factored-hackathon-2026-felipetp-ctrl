"""Run channels-v1: written complaints and fraud-alert answers, end to end, with no language-model calls.

Two readers are compared on the same cases: the deployed free reader (keyword rules + the trained classifier intent-v2)
and the keyword rules alone (baseline). For letters, "everything to a person" (the bank's current process) is reported
as a reference row. Alert conversations are scripted: the customer's lines were written in advance by an independent
author, and the harness picks the line that answers what the bank asked (see `_alert`).

    python -m dispute_ops.evaluation.channels_eval --set ../eval/scenarios/channels-v1.json --split test \\
        --db demo_data/dispute_ops.db --out ../eval/results/channels-v1-test
"""

from __future__ import annotations

import argparse
import json
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

from dispute_ops.channels import process_letter
from dispute_ops.container import Container, Settings
from dispute_ops.language.intent_model import DEFAULT_PATH, IntentModel
from dispute_ops.language.rule_nlu import RuleNlu

TERMINAL = {"done", "handoff", "ineligible", "cancelled"}
AUTOMATED = {"done", "ineligible", "cancelled"}
FALLBACK_LINE = {"es": "no sé", "pt": "não sei"}


def _container(db: str, with_model: bool) -> tuple[Container, RuleNlu]:
    settings = Settings(demo_db=db, session_secret="eval", nlu_mode="rules", demo_now="2026-06-17T12:00:00+00:00",
                        fraud_alert_lookback_hours=24 * 90)
    c = Container.build(settings, sleep=lambda s: None)
    reader = RuleNlu(c.store.distinct_merchants(), intent_model=IntentModel.load(Path(DEFAULT_PATH)) if with_model else None)
    c.conversations.nlu = reader
    return c, reader


def _letter(c: Container, reader: RuleNlu, case: dict[str, Any]) -> dict[str, Any]:
    item = {**case, "complaint_id": case["id"], "description": case["text"]}
    started = time.perf_counter()
    reading, r = process_letter(item, reader, tools=c.tools, store=c.store, policy=c.policy, sessions=c.sessions,
                                clock=c.clock, sleep=lambda s: None)
    return {
        "outcome": r.action, "latency_ms": (time.perf_counter() - started) * 1000, "turns": 0,
        "case_transaction": r.case.transaction_id if r.case else None,
        "case_reason": r.case.reason_code.value if r.case else None,
        "handoff_reasons": r.handoff.reason_for_handoff if r.handoff else [],
        "blocked": False, "script_gaps": 0,
        "reading": {"reason_code": reading.reason_code.value if reading.reason_code else None,
                    "confidence": round(reading.reason_confidence, 3), "evidence": reading.evidence(),
                    "regulatory_threat": reading.regulatory_threat},
        "transcript": [["customer", case["text"]], ["bank", r.action]],
    }


def _alert(c: Container, case: dict[str, Any]) -> dict[str, Any]:
    """Scripted customer: the first line answers the alert; afterwards the harness sends the line for whatever the
    bank asked (card in possession, confirmation, the alert question again). An unexpected question gets "I don't
    know", counted as a script gap."""
    lines, lang = case["text"], case["language"]
    svc = c.conversations
    token = c.sessions.issue(case["customer_id"])
    cid, opening = svc.start_proactive(token, case["transaction_id"], lang)
    transcript: list[list[str]] = [["bank", opening]]
    latencies, gaps = [], 0
    used_again = False

    def say(text: str):
        started = time.perf_counter()
        transcript.append(["customer", text])
        reply = svc.send(cid, token, text)
        latencies.append((time.perf_counter() - started) * 1000)
        transcript.append(["bank", reply.text])
        return reply

    reply = say(lines["first"])
    for _ in range(6):
        if reply.action in TERMINAL or reply.state in ("DONE", "HANDOFF", "INELIGIBLE", "CANCELLED"):
            break
        if reply.action == "confirm" and lines.get("confirm"):
            reply = say(lines["confirm"])
        elif "card_in_possession" in reply.ask_for and lines.get("card"):
            reply = say(lines["card"])
        elif reply.action == "proactive" and lines.get("again") and not used_again:
            used_again = True
            reply = say(lines["again"])
        else:
            gaps += 1
            reply = say(FALLBACK_LINE[lang])
    dispute = c.store.find_open_dispute(case["transaction_id"])
    txn = c.store.get_transaction(case["transaction_id"])
    card = c.store.get_card(txn.product_id) if txn else None
    return {
        "outcome": reply.action if reply.action in TERMINAL else f"stuck:{reply.action}",
        "latency_ms": sum(latencies), "turns": len(latencies),
        "case_transaction": dispute.transaction_id if dispute else None,
        "case_reason": dispute.reason_code.value if dispute else None,
        "handoff_reasons": reply.handoff.reason_for_handoff if reply.handoff else [],
        "blocked": bool(card and card.product_status == "Blocked"), "script_gaps": gaps, "transcript": transcript,
    }


def judge(case: dict[str, Any], got: dict[str, Any]) -> dict[str, Any]:
    exp = case["expected"]
    opened = got["case_transaction"] is not None
    unsafe: list[str] = []
    if opened and exp["outcome"] != "done":
        unsafe.append("dispute_opened_against_policy")
    if opened and exp["outcome"] == "done" and got["case_transaction"] != exp["transaction_id"]:
        unsafe.append("wrong_transaction")
    if opened and exp["outcome"] == "done" and got["case_reason"] != exp["reason_code"]:
        unsafe.append("wrong_reason")
    if got["blocked"] and not exp.get("block"):
        unsafe.append("unrequested_block")
    correct = got["outcome"] == exp["outcome"] and not unsafe
    if correct and exp["outcome"] == "done" and exp.get("block") and not got["blocked"]:
        correct = False
    handoff, expected_handoff = got["outcome"] == "handoff", exp["outcome"] == "handoff"
    return {
        "correct": correct, "unsafe": bool(unsafe), "unsafe_reasons": unsafe,
        "handoff": handoff, "expected_handoff": expected_handoff,
        "safe_automated": correct and not handoff and exp["outcome"] in AUTOMATED,
        "handoff_reason_match": (not expected_handoff or not handoff
                                 or bool(set(exp.get("handoff_reasons", [])) & set(got["handoff_reasons"]))),
    }


def run(cases: list[dict[str, Any]], db: str) -> list[dict[str, Any]]:
    rows = []
    for system, with_model in (("rules_intent_v2", True), ("rules_only", False)):
        for case in cases:
            c, reader = _container(db, with_model)
            got = _letter(c, reader, case) if case["kind"] == "letter" else _alert(c, case)
            rows.append({"id": case["id"], "kind": case["kind"], "key": case["key"], "language": case["language"],
                         "system": system, "expected": case["expected"], **got, **judge(case, got)})
    return rows


def _rate(k: int, n: int) -> str:
    return f"{k}/{n} ({100 * k / n:.0f}%)" if n else "0/0"


def _mcnemar(a: list[bool], b: list[bool]) -> str:
    from math import comb
    x = sum(1 for p, q in zip(a, b) if p and not q)
    y = sum(1 for p, q in zip(a, b) if q and not p)
    n = x + y
    if n == 0:
        return "no discordant pairs"
    p = min(1.0, 2 * sum(comb(n, i) for i in range(0, min(x, y) + 1)) / 2 ** n)
    return f"{x} vs {y} discordant, exact p = {p:.3g}"


def report(rows: list[dict[str, Any]], cases: list[dict[str, Any]], split: str) -> str:
    out = [f"# channels-v1 · {split}", "",
           "Written complaints and fraud-alert answers, run end to end with no language-model calls. Expected outcomes "
           "from the policy on real transactions; customer text by an independent author. Offline simulation.", ""]
    for kind, title in (("letter", "Written complaints"), ("alert", "Fraud-alert answers")):
        ks = [r for r in rows if r["kind"] == kind]
        if not ks:
            continue
        n_cases = len({r["id"] for r in ks})
        out += [f"## {title} (n = {n_cases})", "",
                "| Reader | Correct outcome | Safe automated resolution | Unsafe | Missed handoffs | Unnecessary handoffs | Handoff reason matches | Script gaps |",
                "|---|---|---|---|---|---|---|---|"]
        for system in ("rules_intent_v2", "rules_only"):
            s = [r for r in ks if r["system"] == system]
            exp_h = [r for r in s if r["expected_handoff"]]
            not_h = [r for r in s if not r["expected_handoff"]]
            out.append(
                f"| {'rules + intent-v2 (deployed)' if system == 'rules_intent_v2' else 'keyword rules only (baseline)'} | "
                f"{_rate(sum(r['correct'] for r in s), len(s))} | {_rate(sum(r['safe_automated'] for r in s), len(s))} | "
                f"{sum(r['unsafe'] for r in s)}/{len(s)} | {sum(not r['handoff'] for r in exp_h)}/{len(exp_h)} | "
                f"{sum(r['handoff'] for r in not_h)}/{len(not_h)} | "
                f"{sum(r['handoff_reason_match'] for r in exp_h if r['handoff'])}/{sum(r['handoff'] for r in exp_h)} | "
                f"{sum(r['script_gaps'] for r in s)} |")
        if kind == "letter":
            exp_h = sum(1 for c in cases if c["kind"] == kind and c["expected"]["outcome"] == "handoff")
            out.append(f"| everything to a person (current process) | {_rate(exp_h, n_cases)} | 0/{n_cases} (0%) | 0/{n_cases} | 0/{exp_h} | "
                       f"{n_cases - exp_h}/{n_cases - exp_h} | — | — |")
        a = [r["correct"] for r in sorted(ks, key=lambda r: r["id"]) if r["system"] == "rules_intent_v2"]
        b = [r["correct"] for r in sorted(ks, key=lambda r: r["id"]) if r["system"] == "rules_only"]
        out += ["", f"Paired comparison of correct outcomes (deployed vs baseline): {_mcnemar(a, b)}.", ""]
        by = defaultdict(lambda: [0, 0])
        for r in ks:
            if r["system"] == "rules_intent_v2":
                by[r["language"]][0] += r["correct"]
                by[r["language"]][1] += 1
        out.append("By language, deployed reader: " + ", ".join(f"{k} {v[0]}/{v[1]}" for k, v in sorted(by.items())) + ".")
        out += ["", "| Case | Expected | Deployed | Baseline |", "|---|---|---|---|"]
        for cid in sorted({r["id"] for r in ks}):
            d = next(r for r in ks if r["id"] == cid and r["system"] == "rules_intent_v2")
            bl = next(r for r in ks if r["id"] == cid and r["system"] == "rules_only")
            exp = d["expected"]["outcome"] + (" + block" if d["expected"].get("block") else "")
            cell = lambda r: ("✓ " if r["correct"] else "✗ ") + r["outcome"] + (" + block" if r["blocked"] else "") + (  # noqa: E731
                f" ({', '.join(r['unsafe_reasons'])})" if r["unsafe"] else "")
            out.append(f"| `{cid.split('-', 3)[3]}` | {exp} | {cell(d)} | {cell(bl)} |")
        out.append("")
    lat = [r["latency_ms"] for r in rows if r["system"] == "rules_intent_v2"]
    lat.sort()
    out += ["## Latency and cost", "",
            f"Whole case, deployed reader, this machine: p50 {lat[len(lat) // 2]:.1f} ms, p95 {lat[int(len(lat) * .95) - 1]:.1f} ms. "
            "Model cost US$ 0 (no model calls). Excludes network and the bank's real systems.", "",
            "## Limitations", "",
            "- Small sets (letters and alerts each under 30 cases per split); one run (deterministic, so repeats are identical).",
            "- Alert conversations are scripted: lines are written in advance and picked by what the bank asks, so a "
            "question the author did not foresee gets “I don't know” (counted as script gaps).",
            "- The Claude reader is not evaluated here (no API credit); these are the free readers only.",
            "- Structured PQR fields (card, claimed amount) are taken as given by the intake form; only the free text is read.", ""]
    return "\n".join(out)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--set", required=True)
    ap.add_argument("--split", required=True, choices=["dev", "test"])
    ap.add_argument("--db", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    cases = [c for c in json.loads(Path(a.set).read_text()) if c["split"] == a.split]
    rows = run(cases, a.db)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "results.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))
    (out / "report.md").write_text(report(rows, cases, a.split))
    print((out / "report.md").read_text())


if __name__ == "__main__":
    main()
