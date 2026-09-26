"""python -m dispute_ops.evaluation --systems proposed naive_llm --repeats 1"""

from __future__ import annotations

import argparse
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

from dotenv import find_dotenv, load_dotenv

from dispute_ops.container import Settings
from dispute_ops.evaluation.gold_scenarios import load as load_scenarios
from dispute_ops.evaluation.metrics import breakdown, summarize
from dispute_ops.evaluation.runner import ScenarioResult, run_scenario
from dispute_ops.evaluation.scenarios import SCENARIO_SET_VERSION, build_scenarios
from dispute_ops.evaluation.simulator import SIMULATOR_MODEL, ClaudeSimulator
from dispute_ops.evaluation.systems import BASELINE_MODEL, BASELINE_PROMPT_VERSION, NaiveLlmSystem, ProposedSystem
from dispute_ops.language.nlu import NLU_MODEL, PROMPT_VERSION

SYSTEMS = {"proposed": ProposedSystem, "naive_llm": NaiveLlmSystem}


def render_markdown(meta: dict, results: list[ScenarioResult]) -> str:
    systems = sorted({r.system for r in results})
    summaries = {s: summarize([r for r in results if r.system == s]) for s in systems}
    keys = list(next(iter(summaries.values())).keys())
    lines = [
        "# Evaluation report",
        "",
        f"> **Offline simulation** on the {meta.get('data', 'synthetic seed fixture')} — not production.",
        "> Customers are simulated by an LLM; expected outcomes are derived deterministically from the policy.",
        "",
        "| Item | Value |", "|---|---|",
        *[f"| {k} | {v} |" for k, v in meta.items()],
        "",
        "## Headline metrics",
        "",
        "| Metric | " + " | ".join(systems) + " |",
        "|---|" + "---|" * len(systems),
        *[f"| {k} | " + " | ".join(str(summaries[s][k]) for s in systems) + " |" for k in keys],
    ]
    for key, title in (("language", "By language"), ("category", "By category")):
        lines += ["", f"## {title}", "", "| System | Group | n | correct | safe resolution | unsafe | escalation missed |",
                  "|---|---|---|---|---|---|---|"]
        for s in systems:
            for group, m in breakdown([r for r in results if r.system == s], key).items():
                lines.append(f"| {s} | {group} | {m['n_cases']} | {m['correct']} | {m['safe_automated_resolution']} | "
                             f"{m['unsafe']} | {m['escalation_missed']} |")
    lines += ["", "## Failures (incorrect or unsafe)", "", "| System | Scenario | Run | Expected | Actual | Unsafe | Error |",
              "|---|---|---|---|---|---|---|"]
    for r in sorted(results, key=lambda x: (x.system, x.scenario_id, x.run)):
        if not r.correct or r.unsafe:
            lines.append(f"| {r.system} | {r.scenario_id} | {r.run} | {r.expected_outcome} | {r.actual_outcome} | "
                         f"{', '.join(r.unsafe_reasons) or '-'} | {r.error or '-'} |")
    return "\n".join(lines) + "\n"


def main() -> None:
    load_dotenv(find_dotenv(usecwd=True))
    p = argparse.ArgumentParser()
    p.add_argument("--systems", nargs="+", default=["proposed", "naive_llm"], choices=list(SYSTEMS))
    p.add_argument("--repeats", type=int, default=1)
    p.add_argument("--only", default=None, help="substring filter on scenario id")
    p.add_argument("--workers", type=int, default=6)
    p.add_argument("--out", default=str(Path(__file__).resolve().parents[4] / "eval" / "results"))
    p.add_argument("--scenarios", default=None, help="frozen scenario JSON (default: built-in dev set on the seed fixture)")
    p.add_argument("--demo-db", default=None, help="gold demo SQLite the scenarios refer to")
    args = p.parse_args()

    base = load_scenarios(Path(args.scenarios)) if args.scenarios else build_scenarios()
    scenarios = [s for s in base if not args.only or args.only in s.id]
    settings = Settings(session_secret="eval-secret", agent_api_key="eval", demo_db=args.demo_db or "")
    simulator = ClaudeSimulator()
    jobs = [(s, name, run) for run in range(args.repeats) for name in args.systems for s in scenarios]
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        results = list(pool.map(lambda j: run_scenario(j[0], SYSTEMS[j[1]], simulator, run=j[2], settings=settings), jobs))

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = Path(args.out) / stamp
    out.mkdir(parents=True, exist_ok=True)
    meta = {
        "timestamp_utc": stamp, "scenario_set": Path(args.scenarios).stem if args.scenarios else SCENARIO_SET_VERSION,
        "scenarios": len(scenarios), "data": "gold demo store (organizer data)" if args.demo_db else "synthetic seed fixture",
        "repeats": args.repeats, "systems": ", ".join(args.systems),
        "proposed_nlu": f"{NLU_MODEL} / {PROMPT_VERSION}", "baseline": f"{BASELINE_MODEL} / {BASELINE_PROMPT_VERSION}",
        "customer_simulator": SIMULATOR_MODEL, "simulator_cost_usd": round(simulator.cost_usd, 4),
        "cost_assumptions": "Anthropic list prices (USD/MTok): haiku-4-5 1/5, sonnet-5 2/10; system cost only",
    }
    (out / "results.jsonl").write_text("\n".join(r.model_dump_json() for r in results) + "\n")
    summary = {"meta": meta, "by_system": {s: summarize([r for r in results if r.system == s]) for s in args.systems}}
    (out / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False))
    (out / "report.md").write_text(render_markdown(meta, results))
    print(render_markdown(meta, results))
    print(f"\nWritten to {out}")


if __name__ == "__main__":
    main()
