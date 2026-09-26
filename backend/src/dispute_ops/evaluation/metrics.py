"""Aggregate metrics exactly as the challenge defines them, with denominators."""

from __future__ import annotations

import statistics
from collections import defaultdict
from typing import Any

from dispute_ops.evaluation.runner import ScenarioResult


def _pct(values: list[float], q: int) -> float | None:
    if not values:
        return None
    if len(values) == 1:
        return round(values[0], 1)
    return round(statistics.quantiles(values, n=100, method="inclusive")[q - 1], 1)


def summarize(results: list[ScenarioResult]) -> dict[str, Any]:
    n = len(results)
    in_scope = [r for r in results if r.in_scope]
    safe_resolved = [
        r for r in in_scope
        if r.correct and not r.unsafe and not r.handoff and r.expected_outcome in ("done", "ineligible", "cancelled")
    ]
    attempted = [r for r in in_scope if r.automation_attempted]
    expected_ho = [r for r in results if r.expected_handoff]
    latencies = [x for r in results for x in r.latencies_ms]
    cost_total = sum(r.cost_usd for r in results)
    unsafe_reasons: dict[str, int] = defaultdict(int)
    for r in results:
        for u in r.unsafe_reasons:
            unsafe_reasons[u] += 1
    return {
        "n_cases": n,
        "n_in_scope": len(in_scope),
        "correct": f"{sum(r.correct for r in results)}/{n}",
        "safe_automated_resolution": f"{len(safe_resolved)}/{len(in_scope)}",
        "safe_automated_resolution_rate": round(len(safe_resolved) / len(in_scope), 3) if in_scope else None,
        "automation_attempted": f"{len(attempted)}/{len(in_scope)}",
        "containment": f"{sum(not r.handoff for r in results)}/{n}",
        "escalation_correct": f"{sum(r.handoff for r in expected_ho)}/{len(expected_ho)}",
        "escalation_missed": f"{sum(not r.handoff for r in expected_ho)}/{len(expected_ho)}",
        "escalation_unnecessary": f"{sum(r.handoff and not r.expected_handoff and not r.handoff_acceptable for r in results)}/{n - len(expected_ho)}",
        "unsafe": f"{sum(r.unsafe for r in results)}/{n}",
        "unsafe_reasons": dict(unsafe_reasons),
        "errors": sum(r.error is not None for r in results),
        "turn_latency_ms_p50": _pct(latencies, 50),
        "turn_latency_ms_p95": _pct(latencies, 95),
        "cost_usd_total": round(cost_total, 4),
        "cost_usd_per_attempted_case": round(cost_total / len(attempted), 5) if attempted else "not defined",
        "cost_usd_per_safe_resolution": round(cost_total / len(safe_resolved), 5) if safe_resolved else "not defined",
    }


def breakdown(results: list[ScenarioResult], key: str) -> dict[str, dict[str, Any]]:
    groups: dict[str, list[ScenarioResult]] = defaultdict(list)
    for r in results:
        groups[getattr(r, key)].append(r)
    return {k: summarize(v) for k, v in sorted(groups.items())}
