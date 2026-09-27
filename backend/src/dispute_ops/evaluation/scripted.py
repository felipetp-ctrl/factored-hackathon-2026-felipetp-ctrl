"""Scripted customer simulation: an outside agent plays the customer turn by turn, without API calls from here.

The system is deterministic given the customer's messages, so every step replays each conversation from the start
with the messages written so far and stops where the next customer message is needed. Conversations whose
transcripts are identical so far (the two system variants before they diverge) are shown once and receive the
same message, so both variants face the same customer until their replies differ.

    python -m dispute_ops.evaluation.scripted status   --dir OUT   # pending conversations, grouped
    python -m dispute_ops.evaluation.scripted apply    --dir OUT --answers answers.json   # {group_id: message}
    python -m dispute_ops.evaluation.scripted finalize --dir OUT   # results.jsonl + report.md
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from dispute_ops.container import Settings
from dispute_ops.evaluation.gold_scenarios import load as load_scenarios
from dispute_ops.evaluation.runner import ScenarioResult, run_scenario
from dispute_ops.evaluation.scenarios import Scenario
from dispute_ops.evaluation.systems import ProposedSystem

REPO = Path(__file__).resolve().parents[4]
SCENARIOS = REPO / "eval" / "scenarios" / "test-v3.json"
DEMO_DB = REPO / "backend" / "demo_data" / "dispute_ops.db"
VARIANTS = {"rules_only": "off", "rules_intent_v2": ""}  # system name -> INTENT_MODEL setting


class NeedsMessage(Exception):
    pass


class ScriptedSimulator:
    def __init__(self, messages: list[str]) -> None:
        self.messages = messages

    def next_message(self, scenario: Scenario, transcript: list[tuple[str, str]]) -> str:
        i = sum(1 for role, _ in transcript if role == "customer") - (1 if scenario.opening else 0)
        if i < len(self.messages):
            return self.messages[i]
        raise NeedsMessage()


def _system(name: str):
    return type(f"System_{name}", (ProposedSystem,), {"name": name})


def _settings(variant: str) -> Settings:
    return Settings(session_secret="eval-secret", agent_api_key="eval", demo_db=str(DEMO_DB), nlu_mode="rules",
                    intent_model=VARIANTS[variant])


def _state(out: Path) -> dict[str, list[str]]:
    f = out / "messages.json"
    return json.loads(f.read_text()) if f.exists() else {}


def replay(out: Path) -> tuple[list[ScenarioResult], dict[str, dict]]:
    """All conversations replayed; returns finished results and pending groups {group_id: {...}}."""
    state = _state(out)
    finished, groups = [], {}
    for sc in load_scenarios(SCENARIOS):
        for variant in VARIANTS:
            key = f"{sc.id}|{variant}"
            r = run_scenario(sc, _system(variant), ScriptedSimulator(state.get(key, [])), settings=_settings(variant))
            if r.error and r.error.startswith("NeedsMessage"):
                visible = [(role, t) for role, t in r.transcript if role != "system"]
                gid = hashlib.sha1(json.dumps([sc.id, visible]).encode()).hexdigest()[:8]
                g = groups.setdefault(gid, {"scenario": sc.id, "language": sc.language, "persona": sc.persona,
                                            "transcript": visible, "keys": []})
                g["keys"].append(key)
            else:
                finished.append(r)
    return finished, groups


def status(out: Path) -> str:
    finished, groups = replay(out)
    lines = [f"finished conversations: {len(finished)} · pending groups: {len(groups)}", ""]
    for gid, g in groups.items():
        lines += [f"=== GROUP {gid} · scenario {g['scenario']} · language {g['language']} · {len(g['keys'])} conversation(s)",
                  f"PERSONA: {g['persona']}", "TRANSCRIPT:"]
        lines += [f"  {'BANK' if role == 'bank' else 'CUSTOMER'}: {t}" for role, t in g["transcript"]]
        lines.append("")
    return "\n".join(lines)


def apply(out: Path, answers: dict[str, str]) -> str:
    _, groups = replay(out)
    state = _state(out)
    unknown = [gid for gid in answers if gid not in groups]
    for gid, text in answers.items():
        if gid in groups:
            for key in groups[gid]["keys"]:
                state.setdefault(key, []).append(text.strip())
    (out / "messages.json").write_text(json.dumps(state, ensure_ascii=False, indent=1))
    return f"applied {len(answers) - len(unknown)} answer(s)" + (f"; unknown group ids ignored: {unknown}" if unknown else "")


def finalize(out: Path, simulator_note: str) -> str:
    from dispute_ops.evaluation.__main__ import render_markdown

    finished, groups = replay(out)
    if groups:
        raise SystemExit(f"{len(groups)} conversation group(s) still pending")
    (out / "results.jsonl").write_text("\n".join(r.model_dump_json() for r in finished) + "\n")
    meta = {
        "timestamp_utc": datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"), "scenario_set": "test-v3",
        "scenarios": len(load_scenarios(SCENARIOS)), "data": "gold demo store (organizer data)",
        "repeats": "1 run per system variant (same customer until the variants' replies diverge)",
        "systems": "rules_only (fallback NLU, keyword rules) · rules_intent_v2 (fallback NLU + intent-v2 classifier)",
        "nlu_mode": "rules (no language-model call in the system under test)",
        "customer_simulator": simulator_note, "api_calls": "none from the harness",
    }
    text = render_markdown(meta, finished)
    (out / "report.md").write_text(text)
    return text


def main() -> None:
    p = argparse.ArgumentParser(prog="dispute_ops.evaluation.scripted")
    p.add_argument("cmd", choices=["status", "apply", "finalize"])
    p.add_argument("--dir", required=True)
    p.add_argument("--answers")
    p.add_argument("--simulator-note", default="Claude Sonnet run as a Claude Code subagent, persona + transcript only")
    a = p.parse_args()
    out = Path(a.dir)
    out.mkdir(parents=True, exist_ok=True)
    if a.cmd == "status":
        print(status(out))
    elif a.cmd == "apply":
        print(apply(out, json.loads(Path(a.answers).read_text())))
    else:
        print(finalize(out, a.simulator_note))


if __name__ == "__main__":
    main()
