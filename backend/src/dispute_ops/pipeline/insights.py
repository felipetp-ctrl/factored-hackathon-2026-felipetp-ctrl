"""Operating insights with their statistics: which patterns in the data are real, which are noise, and what each one
changes in how the dispute service is run (docs/analysis/operating-insights.md, figures, and the app's Insights tab).

    python -m dispute_ops.pipeline.insights   (needs `make data`; reads silver, gold and committed evaluation results)

Every number is computed here from the organizer data or from a committed result file; projections say so."""

from __future__ import annotations

import json
from math import sqrt
from pathlib import Path

import duckdb
from scipy import stats

from dispute_ops.domain import FRAUD_ALERT_MIN_SCORE
from dispute_ops.evaluation.uncertainty import wilson
from dispute_ops.pipeline.figures import AMBER, GRAY, GREEN, INK, MUTED, PURPLE, _save, plt

ROOT = Path(__file__).resolve().parents[4]
WEEKDAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]
API_RUN = "eval/results/hard-v1-api/20260930T225007Z/results.jsonl"

# Business-case assumptions (problem_analysis §4): base value and the range tested in the sensitivity analysis.
ASSUMPTIONS = {
    "back_office_minutes": (15.0, 5.0, 30.0, "back-office minutes to rebuild a case (assumed)"),
    "agent_cost_per_hour": (8.0, 5.0, 12.0, "loaded agent cost, US$ per hour (assumed)"),
    "automation_share": (None, None, None, "share resolved safely without a person (hard-v1 API, 95% interval)"),
    "monthly_volume": (377.0, 335.0, 424.0, "disputes per month (lowest and highest month observed)"),
}
CONTACT_MINUTES = 7.2  # measured: complaint contact handle time
MODEL_COST_PER_RESOLUTION = 0.020  # hard-v1 API


def _q(sql: str) -> list[tuple]:
    return duckdb.sql(sql).fetchall()


def weekday_and_trend(silver: Path) -> dict:
    f = f"'{silver}/complaints.parquet'"
    days = dict(_q(f"SELECT dayofweek(creation_date), count(*) FROM {f} WHERE category='Transactions' GROUP BY 1"))
    observed = [days.get(d, 0) for d in range(7)]
    chi_w = stats.chisquare(observed)
    hours = dict(_q(f"SELECT hour(creation_date), count(*) FROM {f} WHERE category='Transactions' GROUP BY 1"))
    chi_h = stats.chisquare([hours.get(h, 0) for h in range(24)])
    months = _q(f"SELECT date_trunc('month', creation_date) m, count(*) FROM {f} WHERE category='Transactions' GROUP BY 1 ORDER BY 1")[1:-1]
    trend = stats.linregress(range(len(months)), [n for _, n in months])
    years = _q(f"SELECT year(creation_date), reception_channel, count(*) FROM {f} WHERE category='Transactions' "
               "AND year(creation_date) IN (2024, 2025) GROUP BY ALL")
    channels = sorted({c for _, c, _ in years})
    table = [[next((n for y2, c2, n in years if y2 == y and c2 == c), 0) for c in channels] for y in (2024, 2025)]
    chi_c = stats.chi2_contingency(table)
    return {
        "weekday_counts": dict(zip(WEEKDAYS, observed)),
        "weekday_chi2": round(chi_w.statistic, 1), "weekday_p": chi_w.pvalue,
        "weekday_ratio_peak_to_sunday": round(max(observed[2:6]) / observed[0], 2),
        "hour_chi2": round(chi_h.statistic, 1), "hour_p": chi_h.pvalue,
        "trend_per_month": round(trend.slope, 2), "trend_p": trend.pvalue, "months": len(months),
        "channel_mix_chi2": round(chi_c.statistic, 1), "channel_mix_p": chi_c.pvalue,
    }


OPEN_STATUSES = ("Open", "In Process", "Escalated")
AGE_BUCKETS = [(0, 30, "< 1 month"), (30, 90, "1–3 months"), (90, 365, "3–12 months"), (365, 730, "1–2 years"),
               (730, 10_000, "> 2 years")]


def status_lifecycle(silver: Path) -> dict:
    """Does the 'open' status behave like a backlog? In a real queue the share still open falls with age."""
    f = f"'{silver}/complaints.parquet'"
    snapshot = _q(f"SELECT max(creation_date) FROM {f}")[0][0]
    rows = _q(f"""SELECT date_diff('day', creation_date, TIMESTAMP '{snapshot}') AS age,
                         status IN {OPEN_STATUSES} AS open, resolution_days
                  FROM {f} WHERE category = 'Transactions'""")
    durations = sorted(d for _, _, d in rows if d is not None)

    def still_open(age: int) -> float:  # share of the recorded resolution times longer than this age
        return sum(d > age for d in durations) / len(durations)

    buckets = []
    for lo, hi, label in AGE_BUCKETS:
        ages = [a for a, _, _ in rows if lo <= a < hi]
        part = [o for a, o, _ in rows if lo <= a < hi]
        k, n = sum(part), len(part)
        implied = sum(still_open(a) for a in ages) / n
        buckets.append({"age": label, "n": n, "open": k, "share": k / n, "ci": wilson(k, n), "implied": implied})
    table = [[b["open"], b["n"] - b["open"]] for b in buckets]
    chi = stats.chi2_contingency(table)
    # Trend: change in the probability of being open per year of age (linear probability model, slope and 95% CI).
    trend = stats.linregress([a / 365 for a, _, _ in rows], [1.0 if o else 0.0 for _, o, _ in rows])
    resolved = [(a, d) for a, _, d in rows if d is not None]
    rho = stats.spearmanr([a for a, _ in resolved], [d for _, d in resolved])
    k_all, n_all = sum(o for _, o, _ in rows), len(rows)
    return {"snapshot": str(snapshot)[:10], "buckets": buckets, "chi2": round(chi.statistic, 1), "p": chi.pvalue,
            "dof": chi.dof, "open_share": k_all / n_all, "n": n_all,
            "trend_per_year": trend.slope, "trend_ci": [trend.slope - 1.96 * trend.stderr, trend.slope + 1.96 * trend.stderr],
            "trend_p": trend.pvalue,
            "resolution_age_rho": round(rho.statistic, 3), "resolution_age_p": rho.pvalue,
            "resolution_days_median": float(sorted(d for _, d in resolved)[len(resolved) // 2])}


def rates_by_group(gold: Path) -> dict:
    out = {}
    for col in ("country", "segment"):
        rows = _q(f"""SELECT c.{col}, count(DISTINCT c.customer_id), count(q.complaint_id)
                      FROM '{gold}/customer_dim.parquet' c LEFT JOIN '{gold}/dispute_complaints.parquet' q USING (customer_id)
                      GROUP BY 1 ORDER BY 1""")
        # Disputes per customer as a rate; test homogeneity of disputes against customers across groups.
        total_c, total_d = sum(r[1] for r in rows), sum(r[2] for r in rows)
        expected = [total_d * r[1] / total_c for r in rows]
        chi = stats.chisquare([r[2] for r in rows], expected)
        out[col] = {"groups": [{"group": g, "customers": c, "disputes": d, "per_1000": round(1000 * d / c, 1),
                                "ci": [round(1000 * (d / c - 1.96 * sqrt(d) / c), 1), round(1000 * (d / c + 1.96 * sqrt(d) / c), 1)]}
                               for g, c, d in rows],
                    "chi2": round(chi.statistic, 2), "p": chi.pvalue}
    return out


def fraud_threshold(gold: Path) -> dict:
    f = f"'{gold}/card_transactions.parquet'"
    days = _q(f"SELECT date_diff('day', min(transaction_date), max(transaction_date)) FROM {f}")[0][0]
    # "No usable score": null, or below 30 where the score mixes these frauds into ~1.1M legitimate transactions
    # (precision ~0.03%): no workable threshold reaches them.
    total_fraud, no_score, null_score, low_legit = _q(f"""SELECT count(*) FILTER (WHERE is_fraud),
            count(*) FILTER (WHERE is_fraud AND (fraud_score IS NULL OR fraud_score < 30)),
            count(*) FILTER (WHERE is_fraud AND fraud_score IS NULL),
            count(*) FILTER (WHERE NOT is_fraud AND fraud_score < 30)
            FROM {f} WHERE transaction_status = 'Approved'""")[0]
    curve = []
    for t in range(0, 101, 5):
        alerts, caught = _q(f"""SELECT count(*), count(*) FILTER (WHERE is_fraud) FROM {f}
                                WHERE transaction_status = 'Approved' AND fraud_score >= {t}""")[0]
        curve.append({"threshold": t, "alerts_per_day": round(alerts / days, 2), "precision": round(caught / alerts, 3) if alerts else None,
                      "recall": round(caught / total_fraud, 3)})
    at = next(c for c in curve if c["threshold"] == (FRAUD_ALERT_MIN_SCORE // 5) * 5)
    best_recall = max(c["recall"] for c in curve if c["precision"] and c["precision"] >= 0.5)
    return {"days": days, "fraud": total_fraud, "fraud_without_score": no_score, "fraud_null_score": null_score,
            "legit_below_30": low_legit, "curve": curve, "current": FRAUD_ALERT_MIN_SCORE,
            "at_current": at, "max_recall_at_half_precision": best_recall}


def product_funnel() -> dict:
    rows = [json.loads(x) for x in (ROOT / API_RUN).read_text().splitlines() if x.strip()]
    s = [r for r in rows if r["system"] == "proposed"]
    done = [r for r in s if r["expected_outcome"] == "done"]
    steps = [
        ("Conversations where the right ending is an opened case", len(done)),
        ("Right charge found (from vague memory)", sum(r["identified_transaction"] == r["expected_transaction"] for r in done)),
        ("Case opened and read back", sum(bool(r["case_transactions"]) for r in done)),
        ("Right charge, right reason, card handled as asked", sum(r["correct"] for r in done)),
    ]
    turns = sorted(r["turns"] for r in done if r["correct"])
    handoffs: dict[str, int] = {}
    for r in s:
        for h in r["handoff_reasons"]:
            handoffs[h] = handoffs.get(h, 0) + 1
    return {"steps": steps, "turns_median": turns[len(turns) // 2], "turns_range": [turns[0], turns[-1]],
            "handoff_reasons": dict(sorted(handoffs.items(), key=lambda kv: -kv[1])), "n": len(s)}


def business_sensitivity() -> dict:
    rows = [json.loads(x) for x in (ROOT / API_RUN).read_text().splitlines() if x.strip()]
    s = [r for r in rows if r["system"] == "proposed" and r["in_scope"]]
    safe = sum(r["correct"] and not r["unsafe"] and not r["handoff"] and r["expected_outcome"] in ("done", "ineligible", "cancelled")
               for r in s)
    lo, hi = wilson(safe, len(s))
    base = {k: v[0] for k, v in ASSUMPTIONS.items()}
    base["automation_share"] = safe / len(s)
    ranges = {k: (v[1], v[2]) for k, v in ASSUMPTIONS.items()}
    ranges["automation_share"] = (lo, hi)

    def saving(p: dict) -> float:
        per_case = (CONTACT_MINUTES + p["back_office_minutes"]) / 60 * p["agent_cost_per_hour"]
        n = 12 * p["monthly_volume"]
        return n * p["automation_share"] * (per_case - MODEL_COST_PER_RESOLUTION)

    center = saving(base)
    bars = []
    for k, (a, b) in ranges.items():
        low, high = saving({**base, k: a}), saving({**base, k: b})
        bars.append({"assumption": ASSUMPTIONS[k][3], "low_value": a, "high_value": b, "low": round(low), "high": round(high)})
    bars.sort(key=lambda x: -(abs(x["high"] - x["low"])))
    return {"base_saving": round(center), "bars": bars, "automation_share": round(base["automation_share"], 3),
            "automation_ci": [round(lo, 3), round(hi, 3)], "n": len(s)}


# ---------------------------------------------------------------------------------------------- figures
def fig_fraud(f: dict, out: Path) -> None:
    c = [x for x in f["curve"] if x["precision"] is not None]
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(9.6, 3.6))
    t = [x["threshold"] for x in c]
    a1.plot(t, [x["recall"] * 100 for x in c], color=GREEN, lw=2, label="fraud caught (recall)")
    a1.plot(t, [x["precision"] * 100 for x in c], color=PURPLE, lw=2, label="alerts that are fraud (precision)")
    a1.axvline(f["current"], color=MUTED, lw=1, ls=(0, (3, 3)))
    a1.text(f["current"] + 1.5, 8, f"threshold {f['current']}", color=MUTED, fontsize=9)
    a1.set_ylim(0, 105)
    a1.set_xlabel("fraud_score threshold")
    a1.set_ylabel("%")
    a1.legend(frameon=False, fontsize=9, loc="upper right", bbox_to_anchor=(1.0, 0.86))
    a1.set_title("No threshold catches more than about half")
    covered = f["fraud"] - f["fraud_without_score"]
    a2.barh([0, 1], [covered, f["fraud_without_score"]], color=[GREEN, GRAY], height=0.55)
    a2.set_yticks([0, 1], ["score 30 or more", "no usable score"])
    for i, v in enumerate([covered, f["fraud_without_score"]]):
        a2.text(v + 15, i, f"{v:,} ({v / f['fraud']:.0%})", va="center", fontsize=9.5, color=INK)
    a2.set_xlim(0, f["fraud"] * 0.85)
    a2.grid(axis="y", visible=False)
    a2.set_title("…because many frauds have no score")
    _save(fig, out, "fraud_threshold_capacity.png",
          f"Approved card transactions, {f['days']:,} days; labelled fraud {f['fraud']:,}. 'No usable score' = null, or below 30 where frauds are 0.03% of transactions.")


def fig_rates(r: dict, out: Path) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(9.6, 3.2), sharex=True)
    for ax, key, title in ((axes[0], "country", "By country"), (axes[1], "segment", "By segment")):
        g = r[key]["groups"]
        y = range(len(g))
        ax.errorbar([x["per_1000"] for x in g], list(y), xerr=[[x["per_1000"] - x["ci"][0] for x in g], [x["ci"][1] - x["per_1000"] for x in g]],
                    fmt="o", color=GREEN, ecolor=GRAY, elinewidth=2, capsize=0, ms=7)
        ax.set_yticks(list(y), [x["group"] for x in g])
        ax.set_title(f"{title}: p = {r[key]['p']:.2f}")
        ax.grid(axis="y", visible=False)
        ax.set_xlim(75, 105)
        ax.set_xlabel("unrecognised-charge complaints per 1,000 customers (3 years)")
    _save(fig, out, "dispute_rate_by_group.png", "Gold customer_dim and dispute_complaints; 95% Poisson intervals; chi-square test of equal rates.")


def fig_funnel(p: dict, out: Path) -> None:
    fig, ax = plt.subplots(figsize=(8.6, 2.9))
    labels = [s for s, _ in p["steps"]][::-1]
    vals = [n for _, n in p["steps"]][::-1]
    ax.barh(range(len(vals)), vals, color=[GREEN if i == 0 else GRAY for i in range(len(vals))], height=0.6)
    ax.set_yticks(range(len(vals)), labels)
    for i, v in enumerate(vals):
        ax.text(v + 0.6, i, f"{v}", va="center", fontsize=10, color=INK)
    ax.set_xlim(0, max(vals) * 1.15)
    ax.grid(axis="y", visible=False)
    ax.set_title("Conversations are lost at the charge, not at the reason")
    _save(fig, out, "product_funnel.png", f"hard-v1 on the real API, this system, 2 runs; conversations whose right ending is an opened case. "
          f"Median {p['turns_median']} customer messages to a case.")


def fig_lifecycle(s: dict, out: Path) -> None:
    fig, ax = plt.subplots(figsize=(7.2, 3.4))
    labels = [b["age"] for b in s["buckets"]]
    shares = [b["share"] for b in s["buckets"]]
    err = [[b["share"] - b["ci"][0] for b in s["buckets"]], [b["ci"][1] - b["share"] for b in s["buckets"]]]
    ax.bar(labels, shares, color=GRAY, yerr=err, capsize=3, ecolor=MUTED)
    implied = [b["implied"] for b in s["buckets"]]
    ax.plot(labels, implied, color=PURPLE, marker="o", lw=1.5,
            label="still open if cases took the resolution times the data records")
    for i, v in enumerate(shares):
        ax.text(i + 0.22, v + 0.03, f"{v:.0%}", ha="center", color=INK, fontsize=9)
    ax.set_ylim(0, 1.05)
    ax.set_ylabel("share still open")
    ax.set_xlabel("age of the complaint at the data snapshot")
    ax.legend(frameon=False, fontsize=8, loc="upper right")
    ax.set_title("'Open' does not age: a 2-year-old dispute is as open as last month's", fontsize=11, loc="left")
    _save(fig, out, "status_does_not_age.png",
          f"Card-charge complaints, n = {s['n']:,}; trend {s['trend_per_year']:+.1%} per year of age (p {_p(s['trend_p'])}). Bars: 95% intervals.")


def fig_tornado(b: dict, out: Path) -> None:
    fig, ax = plt.subplots(figsize=(9.6, 3.2))
    base = b["base_saving"]
    for i, x in enumerate(b["bars"][::-1]):
        lo, hi = sorted((x["low"], x["high"]))
        ax.barh(i, hi - lo, left=lo, color=AMBER if i == len(b["bars"]) - 1 else GRAY, height=0.55)
        ax.text(lo - 250, i, f"{lo:,.0f}", va="center", ha="right", fontsize=9, color=MUTED)
        ax.text(hi + 120, i, f"{hi:,.0f}", va="center", ha="left", fontsize=9, color=MUTED)
    ax.axvline(base, color=INK, lw=1)
    ax.set_yticks(range(len(b["bars"])), [x["assumption"] for x in b["bars"][::-1]], fontsize=9)
    ax.set_xlabel("projected yearly intake saving, US$")
    ax.grid(axis="y", visible=False)
    ax.set_title(f"Saving ≈ US$ {base:,.0f} a year; back-office time decides it")
    ax.set_xlim(0, max(max(x["low"], x["high"]) for x in b["bars"]) * 1.15)
    _save(fig, out, "saving_sensitivity.png", "Projection, not a measurement: one assumption moved at a time across its range; others at base. problem_analysis §4.")


# ---------------------------------------------------------------------------------------------- report
def _pct(x: float | None) -> str:
    return "—" if x is None else f"{x:.0%}"


def _p(p: float) -> str:
    return "< 0.001" if p < 0.001 else f"{p:.2f}"


def render(w: dict, r: dict, f: dict, p: dict, b: dict, s: dict) -> str:
    cur = f["at_current"]
    lines = [
        "# Operating insights — what is real, what is noise, what it changes", "",
        "Generated by `python -m dispute_ops.pipeline.insights` from the silver and gold layers (organizer data, synthetic) "
        "and committed evaluation results. Tests are run on purpose: in a synthetic dataset a pattern can be an artefact of the "
        "generator, and a staffing decision should not rest on one.", "",
        "| # | Insight | Evidence | Decision it changes |", "|---|---|---|---|",
        f"| 1 | **Disputes follow the working week, not the hour.** Tuesday to Friday carry {w['weekday_ratio_peak_to_sunday']}× Sunday's volume; hours are flat. | weekday χ² = {w['weekday_chi2']:,} (6 df, p {_p(w['weekday_p'])}); hour χ² = {w['hour_chi2']} (23 df, p {_p(w['hour_p'])}) | Staff the human queue on a weekly curve; no shift-level peak to plan for |",
        f"| 2 | **Volume is flat.** No trend over {w['months']} months; the channel mix did not move between 2024 and 2025. | slope {w['trend_per_month']:+} complaints/month (p {_p(w['trend_p'])}); channel × year χ² = {w['channel_mix_chi2']} (p {_p(w['channel_mix_p'])}) | Capacity is a constant, not a forecast problem; the business case can use the observed range ({ASSUMPTIONS['monthly_volume'][1]:.0f}–{ASSUMPTIONS['monthly_volume'][2]:.0f}/month) |",
        f"| 3 | **Every country and segment disputes at the same rate** (~{r['country']['groups'][0]['per_1000']:.0f} per 1,000 customers in three years). | country χ² p = {r['country']['p']:.2f}; segment χ² p = {r['segment']['p']:.2f} | No segment-specific risk rule is justified; the one country-specific rule (amount threshold in local currency) was replaced by a single USD threshold (ADR-013) |",
        f"| 4 | **The fraud-alert threshold is not the lever; coverage is.** {f['fraud_without_score']:,} of {f['fraud']:,} labelled frauds ({f['fraud_without_score'] / f['fraud']:.0%}) have no usable score ({f['fraud_null_score']} null, the rest below 30 among {f['legit_below_30']:,} legitimate transactions), so no workable threshold alerts on them. At the current threshold ({f['current']}) the bank sends {cur['alerts_per_day']} alerts a day at {cur['precision']:.0%} precision and catches {cur['recall']:.0%} of fraud; the best any threshold does at ≥ 50% precision is {f['max_recall_at_half_precision']:.0%}. | approved card transactions over {f['days']:,} days ([figure](../figures/fraud_threshold_capacity.png)) | The alert channel costs almost no agent time; the next investment is scoring the unscored transactions, and the customer-initiated dispute path remains the safety net for the other half |",
        f"| 5 | **The service loses conversations at the charge, not at the reason.** Of {p['steps'][0][1]} conversations that should end in a case, {p['steps'][1][1]} found the right charge from vague memory, {p['steps'][2][1]} opened and verified a case, {p['steps'][3][1]} were fully right. A case takes a median of {p['turns_median']} customer messages ({p['turns_range'][0]}–{p['turns_range'][1]}). | hard-v1 on the real API ([figure](../figures/product_funnel.png)) | Improve charge search (amount and date tolerance, merchant aliases) before the reader; a registered case in about four messages replaces a 37-hour wait for a first answer |",
        f"| 6 | **The business case depends most on back-office time, which nobody has measured.** Base projection ≈ US$ {b['base_saving']:,} a year at the observed volume. | one-at-a-time sensitivity ([figure](../figures/saving_sensitivity.png)); automation share {b['automation_share']:.0%} (95% interval {b['automation_ci'][0]:.0%}–{b['automation_ci'][1]:.0%}, hard-v1 API, n = {b['n']}) | Measure the back-office minutes per case in the pilot before promising savings |",
        f"| 7 | **The complaint status is a label, not a lifecycle: the '{s['open_share']:.0%} still open' backlog does not exist.** A complaint older than two years is as likely to be open ({s['buckets'][-1]['share']:.0%}) as one from the last month ({s['buckets'][0]['share']:.0%}); the resolution times recorded on the same complaints (median {s['resolution_days_median']:.0f} days) imply that {s['buckets'][0]['implied']:.0%} of last month's and {s['buckets'][-1]['implied']:.0%} of the two-year-old ones would still be open. Resolution time does not depend on age either. | change in the open share per year of age {s['trend_per_year']:+.1%} (95% CI {s['trend_ci'][0]:+.1%} to {s['trend_ci'][1]:+.1%}, p {_p(s['trend_p'])}); age buckets χ² = {s['chi2']} ({s['dof']} df, p {_p(s['p'])}: small differences, no decline); resolution days vs age Spearman ρ = {s['resolution_age_rho']} ([figure](../figures/status_does_not_age.png)) | The status field cannot measure the backlog or the service level; this project stopped citing it as one. The case system records its own lifecycle (opened, verified, handed off, resolved, with timestamps in the audit log), which is what a pilot should measure |",
        "", "## Details", "",
        "### Complaint status by age", "",
        f"Snapshot {s['snapshot']}, card-charge complaints. Open = {', '.join(OPEN_STATUSES)}.", "",
        "| Age at snapshot | Complaints | Still open | Share (95% interval) | Implied by the recorded resolution times |", "|---|---|---|---|---|",
        *[f"| {x['age']} | {x['n']:,} | {x['open']:,} | {x['share']:.1%} ({x['ci'][0]:.1%}–{x['ci'][1]:.1%}) | {x['implied']:.1%} |" for x in s["buckets"]], "",
        "![Status does not age](../figures/status_does_not_age.png)", "",
        "### Dispute rate by group", "",
        "| Group | Customers | Disputes | Per 1,000 | 95% interval |", "|---|---|---|---|---|",
    ]
    for key in ("country", "segment"):
        lines += [f"| {g['group']} | {g['customers']:,} | {g['disputes']:,} | {g['per_1000']} | {g['ci'][0]}–{g['ci'][1]} |" for g in r[key]["groups"]]
    lines += ["", "![Dispute rate by group](../figures/dispute_rate_by_group.png)", "",
              "### Fraud-alert threshold", "", "| Threshold | Alerts per day | Precision | Recall |", "|---|---|---|---|"]
    lines += [f"| {c['threshold']} | {c['alerts_per_day']} | {_pct(c['precision'])} | {_pct(c['recall'])} |"
              for c in f["curve"] if c["threshold"] in (0, 20, 25, 30, 35, 40, 50, 70, 90)]
    lines += ["", "![Fraud threshold](../figures/fraud_threshold_capacity.png)", "",
              "### Product funnel and hand-offs", "", "| Step | Conversations |", "|---|---|"]
    lines += [f"| {s} | {n} |" for s, n in p["steps"]]
    lines += ["", "Hand-off reasons across all 72 conversations: " + ", ".join(f"{k} {v}" for k, v in p["handoff_reasons"].items()) + ".", "",
              "![Funnel](../figures/product_funnel.png)", "",
              "### Business-case sensitivity (projection)", "", "| Assumption | Range | Saving at low | Saving at high |", "|---|---|---|---|"]
    lines += [f"| {x['assumption']} | {x['low_value']:.3g}–{x['high_value']:.3g} | US$ {x['low']:,} | US$ {x['high']:,} |" for x in b["bars"]]
    lines += ["", "![Sensitivity](../figures/saving_sensitivity.png)", "",
              "Limits: synthetic data (outcome fields are generator noise, ADR-021); the funnel comes from simulated customers; "
              "savings are projections from stated assumptions, never measurements."]
    return "\n".join(lines) + "\n"


def app_json(w: dict, r: dict, f: dict, p: dict, b: dict, s: dict) -> dict:
    """The few numbers the bank's Insights tab shows (frontend/lib/insights.json)."""
    cur = f["at_current"]
    return {
        "weekday": {"counts": w["weekday_counts"], "ratio": w["weekday_ratio_peak_to_sunday"]},
        "rates": {"country": [{"group": g["group"], "per_1000": g["per_1000"]} for g in r["country"]["groups"]],
                  "segment": [{"group": g["group"], "per_1000": g["per_1000"]} for g in r["segment"]["groups"]],
                  "p_country": round(r["country"]["p"], 2), "p_segment": round(r["segment"]["p"], 2)},
        "fraud": {"no_score_share": round(f["fraud_without_score"] / f["fraud"], 3), "fraud": f["fraud"],
                  "alerts_per_day": cur["alerts_per_day"], "precision": cur["precision"], "recall": cur["recall"],
                  "threshold": f["current"], "max_recall": f["max_recall_at_half_precision"]},
        "funnel": {"steps": [{"label": s, "n": n} for s, n in p["steps"]], "turns_median": p["turns_median"]},
        "status": {"buckets": [{"age": x["age"], "share": round(x["share"], 3)} for x in s["buckets"]], "p": s["p"]},
        "saving": {"base": b["base_saving"], "top_driver": b["bars"][0]["assumption"],
                   "range": [min(b["bars"][0]["low"], b["bars"][0]["high"]), max(b["bars"][0]["low"], b["bars"][0]["high"])]},
    }


def main() -> None:
    silver, gold, figs = ROOT / "data" / "silver", ROOT / "data" / "gold", ROOT / "docs" / "figures"
    w, r, f = weekday_and_trend(silver), rates_by_group(gold), fraud_threshold(gold)
    p, b, s = product_funnel(), business_sensitivity(), status_lifecycle(silver)
    fig_lifecycle(s, figs)
    fig_fraud(f, figs)
    fig_rates(r, figs)
    fig_funnel(p, figs)
    fig_tornado(b, figs)
    (ROOT / "docs" / "analysis" / "operating-insights.md").write_text(render(w, r, f, p, b, s))
    (ROOT / "frontend" / "lib" / "insights.json").write_text(json.dumps(app_json(w, r, f, p, b, s), indent=1) + "\n")
    print(render(w, r, f, p, b, s))


if __name__ == "__main__":
    main()
