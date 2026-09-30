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
from dispute_ops.evaluation.components import component_markdown, component_report
from dispute_ops.evaluation.metrics import breakdown, summarize
from dispute_ops.evaluation.runner import ScenarioResult, run_scenario
from dispute_ops.evaluation.scenarios import SCENARIO_SET_VERSION, build_scenarios
from dispute_ops.evaluation.simulator import SIMULATOR_MODEL, ClaudeSimulator
from dispute_ops.evaluation.systems import (
    BASELINE_MODEL, BASELINE_PROMPT_VERSION, NaiveLlmSystem, ProposedSystem, StrongLlmSystem,
)
from dispute_ops.language.nlu import NLU_MODEL, PROMPT_VERSION
from dispute_ops.metering import BudgetExceeded

RESCORE_NOTES = """## Leakage notes

- **Rule NLU, out-of-scope.** The first re-scoring gave the rule NLU 75.0% (6/8) out-of-scope recall on the complete
  runs: it read "empréstimo pessoal" (personal loan) as a request for a person ("pessoa"). That rule was fixed after
  looking at these two test-v2 messages, so the rule NLU's out-of-scope figure is no longer a held-out measurement.
  Its dispute-reason accuracy is the keyword baseline's and was not tuned on this set.
- **intent-v2 on the complete runs is post-hoc.** intent-v1 (no augmentation) scored 34/46 on these reason messages;
  reading its errors motivated intent-v2's compositional augmentation (ADR-019), so the complete-run numbers for
  intent-v2 are optimistic. The run-3 messages were never opened, and `test-v3` was frozen before intent-v2 was trained.
- **One run-3 message was then opened.** The first run-3 re-scoring gave the fallback with intent-v2 2/3 out-of-scope
  recall: the classifier read "empréstimo pessoal" as a request for a person. The integration now lets an explicit
  out-of-scope keyword outrank the classifier's "human" reading (the classifier had already been weaker than the
  keywords at scope on the complete runs: 5/8 vs 6/8 standalone). The run-3 out-of-scope figure is therefore post-hoc
  too; its reason accuracy is not affected (the model and the threshold did not change).
"""

SYSTEMS = {"proposed": ProposedSystem, "naive_llm": NaiveLlmSystem, "naive_sonnet": StrongLlmSystem}


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
    for key, title in (("run", "By run (repeated-run variability)"), ("language", "By language"), ("country", "By country"),
                       ("segment", "By customer segment"), ("category", "By category")):
        lines += ["", f"## {title}", "", "| System | Group | n | correct | safe resolution | unsafe | escalation missed |",
                  "|---|---|---|---|---|---|---|"]
        for s in systems:
            for group, m in breakdown([r for r in results if r.system == s], key).items():
                lines.append(f"| {s} | {group} | {m['n_cases']} | {m['correct']} | {m['safe_automated_resolution']} | "
                             f"{m['unsafe']} | {m['escalation_missed']} |")
    if any(r.system == "proposed" for r in results):
        lines += ["", component_markdown(component_report(results))]
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
    p.add_argument("--rescore", default=None,
                   help="results folder: recompute the component report from stored messages (no model calls)")
    args = p.parse_args()
    if args.rescore:
        folder = Path(args.rescore)
        sections = []
        for name, title in (("results.jsonl", "Complete runs"), ("results_aborted_credit.jsonl", "Run 3, cut by exhausted credit")):
            if not (folder / name).exists():
                continue
            stored = [ScenarioResult.model_validate_json(x) for x in (folder / name).read_text().splitlines() if x]
            sections.append(f"# {title} (`{name}`)\n\n" + component_markdown(component_report(stored)))
        text = "\n".join(["# Component re-scoring (offline)\n",
                          "Recomputed from the stored customer messages of this run; no model was called. Adds the "
                          "rule-based fallback NLU (v0.0.2) and the fallback NLU with the learned intent classifier "
                          "intent-v2 (ADR-019).\n", *sections, RESCORE_NOTES])
        (folder / "components_rescored.md").write_text(text)
        print(text)
        return

    base = load_scenarios(Path(args.scenarios)) if args.scenarios else build_scenarios()
    scenarios = [s for s in base if not args.only or args.only in s.id]
    settings = Settings(session_secret="eval-secret", agent_api_key="eval", demo_db=args.demo_db or "")
    simulator = ClaudeSimulator()
    jobs = [(s, name, run) for run in range(args.repeats) for name in args.systems for s in scenarios]
    def job(j):
        try:
            return run_scenario(j[0], SYSTEMS[j[1]], simulator, run=j[2], settings=settings)
        except BudgetExceeded as e:  # credit cap reached (ADR-026): the job is not run, and the report says so
            print(f"stopped by the spend cap: {e}")
            return None

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        ran = list(pool.map(job, jobs))
    results = [r for r in ran if r is not None]

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = Path(args.out) / stamp
    out.mkdir(parents=True, exist_ok=True)
    meta = {
        "timestamp_utc": stamp, "scenario_set": Path(args.scenarios).stem if args.scenarios else SCENARIO_SET_VERSION,
        "scenarios": len(scenarios), "data": "gold demo store (organizer data)" if args.demo_db else "synthetic seed fixture",
        "repeats": args.repeats, "systems": ", ".join(args.systems),
        "jobs_not_run_spend_cap": len(ran) - len(results),
        "proposed_nlu": f"{NLU_MODEL} / {PROMPT_VERSION}", "baseline": f"{BASELINE_MODEL} / {BASELINE_PROMPT_VERSION}",
        "customer_simulator": SIMULATOR_MODEL, "simulator_cost_usd": round(simulator.cost_usd, 4),
        "cost_assumptions": "Anthropic list prices (USD/MTok): haiku-4-5 1/5, sonnet-5 2/10; system cost only",
    }
    (out / "results.jsonl").write_text("\n".join(r.model_dump_json() for r in results) + "\n")
    names = sorted({r.system for r in results})
    summary = {"meta": meta, "by_system": {s: summarize([r for r in results if r.system == s]) for s in names}}
    (out / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False))
    (out / "report.md").write_text(render_markdown(meta, results))
    print(render_markdown(meta, results))
    print(f"\nWritten to {out}")


if __name__ == "__main__":
    main()
