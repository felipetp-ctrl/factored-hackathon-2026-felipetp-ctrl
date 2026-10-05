"""channels-v1: held-out cases for the two channels without a live conversation — written complaints (PQR letters) and
answers to proactive fraud alerts.

Same discipline as hard-v1: facts come from real organizer transactions in the demo store, the expected outcome from
the PolicyEngine and the channel's own rules (deterministic, computed here), and the customer's words are written by a
separate author (a Claude Sonnet subagent that does not read the system code) from the brief produced here. The set is
split into `dev` (open: may be read to fix the system) and `test` (frozen before any fix, run once).

    python -m dispute_ops.evaluation.channel_set briefs --db demo_data/dispute_ops.db --out ../eval/scenarios/channels-v1-briefs.json
    python -m dispute_ops.evaluation.channel_set merge --briefs ... --texts texts.json --out ../eval/scenarios/channels-v1.json
"""

from __future__ import annotations

import argparse
import json
import random
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

from dispute_ops.channels import PqrComplaint, match_complaint
from dispute_ops.domain import ReasonCode, Transaction
from dispute_ops.evaluation.gold_scenarios import _txns
from dispute_ops.policy.engine import PolicyContext, PolicyEngine
from dispute_ops.store import Store

SET_VERSION = "channels-v1"
AS_OF = "2026-06-17T12:00:00+00:00"
VIA = ["email", "web", "branch", "app"]


def _money(t: Transaction) -> str:
    return f"{t.amount} {t.currency}"


def generate(store: Store, as_of: datetime, *, seed: int = 2027) -> list[dict[str, Any]]:
    rng = random.Random(seed)
    policy = PolicyEngine.load_default()
    used: set[str] = set()
    used_customers: set[str] = set()
    items: list[dict[str, Any]] = []

    def pool(lo: int, hi: int, extra: str = "1=1") -> list[Transaction]:
        a, b = (as_of - timedelta(days=hi)).isoformat(), (as_of - timedelta(days=lo)).isoformat()
        rows = [t for t in _txns(store, f"merchant_name IS NOT NULL AND transaction_status='Approved' AND "
                                        f"transaction_date BETWEEN ? AND ? AND {extra}", (a, b))
                if t.transaction_id not in used and t.customer_id not in used_customers]
        rng.shuffle(rows)
        return rows

    def decide(t: Transaction, reason: ReasonCode, evidence: dict[str, str], **flags: Any):
        if evidence.get("expected_amount") == "x":  # the brief asks for about 70% of the charge
            evidence = {**evidence, "expected_amount": str((t.amount * Decimal("0.7")).quantize(Decimal("0.01")))}
        return policy.evaluate(PolicyContext(transaction=t, customer=store.get_customer(t.customer_id),
                                             reason_code=reason, now=as_of, evidence=evidence, **flags))

    def expected_letter(t: Transaction, reason: ReasonCode, evidence: dict[str, str], product: bool, amount: bool,
                        **flags: Any) -> dict[str, Any] | None:
        c = PqrComplaint(complaint_id="x", customer_id=t.customer_id, description="",
                         affected_product_id=t.product_id if product else None,
                         claimed_amount=t.amount if amount else None, created_at=as_of - timedelta(days=1))
        matched, cands = match_complaint(store, c, as_of)
        if matched is None:
            return {"outcome": "handoff", "handoff_reasons": ["async_missing_info"], "transaction_id": None,
                    "reason_code": None, "candidates": len(cands)}
        if matched != t.transaction_id:
            return None  # the structured fields would point at another charge; not a clean case
        d = decide(t, reason, evidence, **flags)
        if d.decision == "ineligible":
            return {"outcome": "ineligible", "rule_ids": d.rule_ids, "transaction_id": t.transaction_id,
                    "reason_code": reason.value}
        if d.decision == "handoff":
            return {"outcome": "handoff", "handoff_reasons": d.handoff_reasons, "transaction_id": t.transaction_id,
                    "reason_code": reason.value}
        if d.missing_evidence:
            return {"outcome": "handoff", "handoff_reasons": ["async_missing_info"], "transaction_id": t.transaction_id,
                    "reason_code": reason.value, "missing": d.missing_evidence}
        return {"outcome": "done", "transaction_id": t.transaction_id, "reason_code": reason.value, "block": False}

    def clean(t: Transaction) -> bool:
        return not store.get_customer(t.customer_id).is_repeat_complainer

    def add(kind: str, key: str, split: str, lang: str, t: Transaction, brief: str, expected: dict[str, Any],
            structured: dict[str, Any]) -> None:
        n = sum(1 for i in items if i["key"] == key and i["split"] == split)
        used.add(t.transaction_id)
        used_customers.add(t.customer_id)
        items.append({
            "id": f"{SET_VERSION}-{split}-{kind}-{key}-{n:02d}-{lang}", "kind": kind, "key": key, "split": split,
            "language": lang, "customer_id": t.customer_id, "transaction_id": t.transaction_id,
            "brief": brief, "expected": expected, **structured,
        })

    # ------------------------------------------------------------------ letters
    def letter(key: str, reason: ReasonCode, evidence: dict[str, str], facts: str, *, product=True, amount=True,
               lo=2, hi=50, extra="amount_usd <= 440", want: str | None = None, **flags: Any):
        for split, lang in [("dev", "es" if len(items) % 2 == 0 else "pt"), ("test", "es"), ("test", "pt")]:
            for t in pool(lo, hi, extra):
                if not clean(t):
                    continue
                exp = expected_letter(t, reason, evidence, product, amount, **flags)
                if exp is None or (want and exp["outcome"] != want):
                    continue
                how = "states the amount" if amount else "does not know the amount"
                brief = (f"A written complaint ({'Spanish' if lang == 'es' else 'Brazilian Portuguese'}) about a card "
                         f"charge of {_money(t)} at {t.transaction_date:%d/%m/%Y} at the merchant “{t.merchant_name}”. "
                         f"The customer {how}. {facts}")
                add("letter", key, split, lang, t, brief, exp, {
                    "received_via": rng.choice(VIA), "affected_product_id": t.product_id if product else None,
                    "claimed_amount": str(t.amount) if amount else None,
                    "created_at": (as_of - timedelta(days=1)).isoformat(),
                })
                break

    cnp = {"card_in_possession": "yes", "recognizes_merchant": "no"}
    letter("fraud-complete", ReasonCode.FRAUD_CNP, cnp,
           "They do not recognise the merchant and say they have the card with them.", want="done")
    letter("fraud-no-card-info", ReasonCode.FRAUD_CNP, {"recognizes_merchant": "no"},
           "They do not recognise the charge. They say nothing about where the card is.", want="handoff")
    letter("stolen-card", ReasonCode.FRAUD_CP, {"card_in_possession": "no"},
           "Their card was stolen (or lost) before this charge; they no longer have it.", want="done")
    letter("duplicate", ReasonCode.DUPLICATE, {},
           "They were charged twice for the same purchase. They do not know any transaction number.", want="handoff")
    letter("wrong-amount", ReasonCode.INCORRECT_AMOUNT, {"expected_amount": "x"},
           "The charge is higher than the price they agreed: the correct amount was about 70% of the charge (state "
           "the correct amount as a number).", want="done")
    letter("not-received", ReasonCode.NOT_RECEIVED, {"expected_delivery_date": "x", "contacted_merchant": "yes"},
           "They paid but never received the product. It should have arrived on a specific date (state it), and they "
           "already contacted the merchant, who did not solve it.", want="done")
    letter("subscription", ReasonCode.CANCELLED_RECURRING, {"cancellation_date": "x"},
           "It is a subscription they had already cancelled; state the day they cancelled it (before the charge).",
           want="done")
    letter("vague", ReasonCode.FRAUD_CNP, cnp,
           "A short, vague letter: an unrecognised charge “this month”, card with them. No amount, no card number.",
           product=False, amount=False, want="handoff")
    letter("above-limit", ReasonCode.FRAUD_CNP, cnp,
           "They do not recognise the merchant and have the card with them.", extra="amount_usd > 460", want="handoff")
    letter("regulator", ReasonCode.FRAUD_CNP, cnp,
           "They do not recognise the merchant, have the card, and say that if the bank does not solve it they will "
           "complain to the banking regulator.", want="handoff", regulatory_threat=True)
    letter("asks-person", ReasonCode.FRAUD_CNP, cnp,
           "They do not recognise the merchant, have the card, and ask for an advisor to call them.",
           want="handoff", human_requested=True)
    letter("late-wrong-amount", ReasonCode.INCORRECT_AMOUNT, {"expected_amount": "x"},
           "The charge is higher than the agreed price: the correct amount was about 70% of the charge (state it as a "
           "number). They only noticed it now, months later.", lo=70, hi=110, want="ineligible")

    # ------------------------------------------------------------------ fraud-alert answers
    def alert(key: str, facts: str, expected: dict[str, Any], *, extra="amount_usd <= 440"):
        for split, lang in [("dev", "es" if len(items) % 2 == 0 else "pt"), ("test", "es"), ("test", "pt")]:
            for t in pool(2, 60, extra):
                if not clean(t):
                    continue
                exp = dict(expected)
                if exp["outcome"] in ("done", "handoff_amount"):
                    d = decide(t, ReasonCode.FRAUD_CNP, cnp)
                    if exp["outcome"] == "done" and not (d.decision == "eligible"):
                        continue
                    if exp["outcome"] == "handoff_amount":
                        if d.decision != "handoff":
                            continue
                        exp = {"outcome": "handoff", "handoff_reasons": d.handoff_reasons}
                exp.setdefault("transaction_id", t.transaction_id if exp["outcome"] == "done" else None)
                if exp["outcome"] == "done":
                    exp.setdefault("reason_code", "FRAUD_CNP")
                brief = (f"The bank's app asks the customer ({'Spanish' if lang == 'es' else 'Brazilian Portuguese'}) "
                         f"whether they recognise a card charge of {_money(t)} at “{t.merchant_name}” on "
                         f"{t.transaction_date:%d/%m/%Y}, flagged by the fraud system. {facts}")
                add("alert", key, split, lang, t, brief, exp, {})
                break

    alert("not-me-block", "They did not make it. The card is with them. When asked to confirm, they confirm and want the "
          "card blocked.", {"outcome": "done", "block": True})
    alert("not-me-keep-card", "They did not make it. The card is with them. They confirm the dispute but do NOT want the "
          "card blocked (they need it this week).", {"outcome": "done", "block": False})
    alert("was-me", "It was them: they recognise it.", {"outcome": "cancelled"})
    alert("was-me-story", "They recognise it only indirectly, with a short story (e.g. a gift or a family dinner) "
          "without saying “yes” plainly.", {"outcome": "cancelled"})
    # Lost card: FRAUD_CP, as the reader prompt and ADR-031 define it (label corrected 2026-10-04, ADR-035).
    alert("lost-card", "They did not make it. They lost the card days ago and do not have it. They confirm and want it "
          "blocked.", {"outcome": "done", "block": True, "reason_code": "FRAUD_CP"})
    alert("above-limit", "They did not make it. The card is with them. They confirm.", {"outcome": "handoff_amount"},
          extra="amount_usd > 460")
    alert("wants-person", "They are unsure and prefer to talk to a person at the bank; they say so.",
          {"outcome": "handoff", "handoff_reasons": ["customer_requested_human"]})
    alert("declines", "They did not make it and the card is with them, but at the confirmation step they decide not to "
          "open anything yet (they want to check with a relative first).", {"outcome": "cancelled"})
    alert("unsure-then-no", "First they are not sure (“let me think…”). When asked again they say they did not make it. "
          "Card with them. They confirm, no block.", {"outcome": "done", "block": False})
    return items


def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("briefs")
    b.add_argument("--db", required=True)
    b.add_argument("--out", required=True)
    m = sub.add_parser("merge")
    m.add_argument("--briefs", required=True)
    m.add_argument("--texts", required=True)
    m.add_argument("--out", required=True)
    a = ap.parse_args()
    if a.cmd == "briefs":
        items = generate(Store(a.db), datetime.fromisoformat(AS_OF))
        Path(a.out).write_text(json.dumps(items, ensure_ascii=False, indent=1) + "\n")
        print(f"{len(items)} briefs -> {a.out}")
    else:
        items = json.loads(Path(a.briefs).read_text())
        texts = json.loads(Path(a.texts).read_text())
        missing = [i["id"] for i in items if i["id"] not in texts]
        if missing:
            raise SystemExit(f"missing texts: {missing}")
        for i in items:
            i["text"] = texts[i["id"]]
        Path(a.out).write_text(json.dumps(items, ensure_ascii=False, indent=1) + "\n")
        print(f"{len(items)} cases -> {a.out}")


if __name__ == "__main__":
    main()
