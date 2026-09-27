"""Offline estimate of a learned cascade: which customer turns could skip the language model?

Every stored test-v2 conversation of the proposed system is replayed with the language model's recorded readings
(so the flow reaches exactly the same states). At each turn the free NLU (rules + intent-v2) reads the same text
with the same context, and the two readings are compared on the fields the flow acts on. A routing rule then
decides which turns the free NLU would have handled; the report gives the share of model calls saved and how often
the free reading agreed with the model's on those turns.

Agreement with the model is a proxy, not ground truth; a live cascade evaluation needs API credit.

    python -m dispute_ops.evaluation.cascade
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from dispute_ops.container import Settings
from dispute_ops.evaluation.gold_scenarios import load as load_scenarios
from dispute_ops.evaluation.runner import run_scenario
from dispute_ops.evaluation.scripted import DEMO_DB, ScriptedSimulator
from dispute_ops.evaluation.systems import ProposedSystem
from dispute_ops.language.intent_model import IntentModel
from dispute_ops.language.keywords import _norm
from dispute_ops.language.nlu import LlmUsage, NluContext, NluOutcome, NluResult
from dispute_ops.language.rule_nlu import LEARNED_STATES, RuleNlu

REPO = Path(__file__).resolve().parents[4]
RUN = REPO / "eval" / "results" / "20260926T181317Z-test-v2"
SCENARIOS = REPO / "eval" / "scenarios" / "test-v2.json"
OUT = RUN / "cascade_offline.md"
FIELDS = ("intent", "reason_code", "transaction_id", "amount", "merchant", "card_in_possession", "recognizes_merchant",
          "contacted_merchant", "wants_block_card", "duplicate_transaction_id", "expected_amount")
STRUCTURED = ("confirm", "decline", "provide_info")


class ReplayNlu:
    """Returns the recorded model readings in order; reads each turn with the free NLU on the side."""
    mode = "claude"

    def __init__(self, recorded: list[dict], free: RuleNlu) -> None:
        self.recorded, self.free, self.i, self.turns = recorded, free, 0, []

    def interpret(self, text: str, ctx: NluContext) -> NluOutcome:
        if self.i >= len(self.recorded):
            raise RuntimeError("replay out of recorded turns")
        model = NluResult(**self.recorded[self.i])
        self.i += 1
        free = self.free.interpret(text, ctx)
        self.turns.append({"state": ctx.state, "ask_for": list(ctx.ask_for), "text": text, "model": model,
                           "free": free.result, "classifier": free.classifier})
        return NluOutcome(result=model, usage=LlmUsage(model="replay", prompt_version="replay", input_tokens=0,
                                                       output_tokens=0, latency_ms=0.0, cost_usd=0.0))


def _same(field: str, a, b) -> bool:
    if field == "amount" or field == "expected_amount":
        return (a is None and b is None) or (a is not None and b is not None and abs(float(a) - float(b)) < 0.01)
    if field == "merchant":
        return (_norm(a or "") == _norm(b or "")) or not a  # a merchant the model did not name is not a disagreement
    return a == b


_GROUP = {"provide_info": "dispute", "dispute": "dispute"}  # both carry details forward in the free-text states


def relevant_fields(state: str, ask_for: list[str]) -> tuple[str, ...]:
    """The NLU fields the flow acts on in each state (the model also repeats context fields the flow ignores)."""
    if state in ("START", "IDENTIFY_TXN"):
        return ("reason_code", "transaction_id", "amount", "merchant")
    if state == "CLASSIFY":
        return ("reason_code",)
    if state == "COLLECT_EVIDENCE":
        return tuple(ask_for)
    if state in ("CONFIRM", "PROACTIVE_CONFIRM"):
        return ("wants_block_card",)
    return ()


def disagreements(model: NluResult, free: NluResult, state: str = "START", ask_for: list[str] = ()) -> list[str]:
    """Differences on the intent and on the fields the flow uses in this state, where the model set a value
    (and, for the reason, also where only the free NLU set one)."""
    mi, fi = _GROUP.get(model.intent, model.intent), _GROUP.get(free.intent, free.intent)
    out = [] if mi == fi else ["intent"]
    for f in relevant_fields(state, list(ask_for)):
        mv, fv = getattr(model, f, None), getattr(free, f, None)
        if (mv is not None or (f == "reason_code" and fv is not None)) and not _same(f, mv, fv):
            out.append(f)
    return out


def route_to_free(t: dict) -> bool:
    """The cascade rule: the free NLU handles structured answers outside the free-text states, and free-text turns
    where the learned classifier is confident; everything else goes to the model."""
    if t["state"] not in LEARNED_STATES:
        return t["free"].intent in STRUCTURED
    return bool(t["classifier"] and t["classifier"]["accepted"])


def run() -> str:
    scenarios = {s.id: s for s in load_scenarios(SCENARIOS)}
    settings = Settings(session_secret="eval-secret", agent_api_key="eval", demo_db=str(DEMO_DB), nlu_mode="rules")
    turns, faithful, replayed, cost_per_turn = [], 0, 0, []
    for name in ("results.jsonl", "results_aborted_credit.jsonl"):
        for line in (RUN / name).read_text().splitlines():
            r = json.loads(line)
            if r["system"] != "proposed" or r.get("error") or not r.get("nlu_turns") or r["scenario_id"] not in scenarios:
                continue
            sc = scenarios[r["scenario_id"]]
            customer = [t for role, t in r["transcript"] if role == "customer"]
            if sc.opening:
                customer = customer[1:]
            if r["turns"]:
                cost_per_turn.append(r["cost_usd"] / r["turns"])
            holder = {}

            def factory(s, rec=r["nlu_turns"]):
                from dispute_ops.container import Container
                c = Container.build(s, nlu=ReplayNlu(rec, RuleNlu([], intent_model=IntentModel.load())))
                c.conversations.nlu.free = RuleNlu(c.store.distinct_merchants(), intent_model=IntentModel.load())
                holder["nlu"] = c.conversations.nlu
                return c
            res = run_scenario(sc, ProposedSystem, ScriptedSimulator(customer), settings=settings, container_factory=factory)
            replayed += 1
            # Reply templates changed since the run (money formats, v0.0.2), so texts are not compared: a faithful
            # replay has the same number of bank turns, consumed every recorded reading and ends the same way.
            nlu = holder["nlu"]
            same = (res.error is None and nlu.i == len(r["nlu_turns"]) and res.actual_outcome == r["actual_outcome"]
                    and sum(role == "bank" for role, _ in res.transcript) == sum(role == "bank" for role, _ in r["transcript"]))
            faithful += same
            if same:
                turns += holder["nlu"].turns
    routed = [t for t in turns if route_to_free(t)]
    agree = [t for t in routed if not disagreements(t["model"], t["free"], t["state"], t["ask_for"])]
    all_agree = [t for t in turns if not disagreements(t["model"], t["free"], t["state"], t["ask_for"])]
    why = Counter(f for t in routed for f in disagreements(t["model"], t["free"], t["state"], t["ask_for"]))
    by_state = Counter((t["state"], route_to_free(t)) for t in turns)
    avg_cost = sum(cost_per_turn) / len(cost_per_turn) if cost_per_turn else 0.0
    examples = [(t["state"], t["text"][:110], d) for t in routed if (d := disagreements(t["model"], t["free"], t["state"], t["ask_for"]))][:15]
    lines = [
        "# Offline cascade estimate (test-v2, complete runs + run 3)", "",
        "> Replay of the stored conversations with the model's recorded readings; the free NLU (rules + intent-v2) "
        "reads each turn on the side. Agreement with the model is a proxy for correctness, not ground truth.", "",
        f"- Conversations replayed: {replayed}; replayed faithfully (same turns, every recorded reading consumed, same "
        f"outcome): {faithful}. "
        f"Only faithful replays are counted.",
        f"- Customer turns read by the model: {len(turns)}.",
        f"- Free NLU agrees with the model on the intent and the fields the flow uses in that state, over all turns: {len(all_agree)}/{len(turns)} "
        f"({len(all_agree) / max(len(turns), 1):.1%}).", "",
        "## Cascade rule", "",
        "Free NLU for structured answers (confirm, decline, provide-info) outside the free-text states, and for free-text "
        "turns where intent-v2 is confident (≥ 0.60); the model for the rest.", "",
        "| | Value |", "|---|---|",
        f"| Turns routed to the free NLU (model calls saved) | {len(routed)}/{len(turns)} ({len(routed) / max(len(turns), 1):.1%}) |",
        f"| Agreement with the model on routed turns | {len(agree)}/{len(routed)} ({len(agree) / max(len(routed), 1):.1%}) |",
        f"| Model cost per turn in these runs | US$ {avg_cost:.4f} |",
        f"| Estimated saving per 1,000 turns | US$ {avg_cost * len(routed) / max(len(turns), 1) * 1000:.2f} |", "",
        "Disagreeing fields on routed turns: " + (", ".join(f"`{k}` {v}" for k, v in why.most_common()) or "none"), "",
        "| State | Routed to free NLU | Turns |", "|---|---|---|",
        *[f"| {s} | {'yes' if routed_flag else 'no'} | {n} |" for (s, routed_flag), n in sorted(by_state.items())], "",
        "## Disagreements on routed turns (first 15)", "", "| State | Customer message | Fields |", "|---|---|---|",
        *[f"| {s} | {x.replace('|', '/')} | {', '.join(d)} |" for s, x, d in examples], "",
        "## Limitations", "",
        "- test-v2 messages were read during the intent-v1 error analysis (post-hoc for intent-v2).",
        "- A disagreement is not necessarily an error of the free NLU, and agreement does not prove the model was right; "
        "the policy and the confirmation step still guard every action.",
        "- The saving assumes the same turn mix as this evaluation set.", ""]
    OUT.write_text("\n".join(lines))
    return "\n".join(lines)


if __name__ == "__main__":
    print(run())
