"""Figures for the problem analysis and the evaluation (static PNGs in docs/figures).

Data figures read the silver layer (`make data` first); evaluation figures read committed result files.

    python -m dispute_ops.pipeline.figures --silver ../data/silver --out ../docs/figures
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import duckdb
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

INK, MUTED, GRID, SURFACE = "#14201c", "#5a6963", "#e3e8e5", "#fcfcfb"
GREEN, PURPLE, AMBER, GRAY = "#138a72", "#5747b0", "#b07a1f", "#b8c2bd"  # validated categorical set (dataviz check)
ROOT = Path(__file__).resolve().parents[4]

plt.rcParams.update({
    "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
    "font.family": ["Arial", "DejaVu Sans"], "font.size": 10.5,
    "text.color": INK, "axes.labelcolor": MUTED, "xtick.color": MUTED, "ytick.color": MUTED,
    "axes.edgecolor": GRID, "axes.spines.top": False, "axes.spines.right": False, "axes.spines.left": False,
    "axes.grid": True, "grid.color": GRID, "grid.linewidth": .8, "axes.axisbelow": True,
    "axes.titlesize": 12.5, "axes.titleweight": "bold", "axes.titlelocation": "left", "axes.titlepad": 14,
})


def _save(fig, out: Path, name: str, source: str) -> None:
    fig.text(0.01, 0.01, source, fontsize=8.5, color=MUTED, ha="left", va="bottom", parse_math=False)
    fig.tight_layout(rect=(0, 0.07 if "\n" in source else 0.04, 1, 1))
    fig.savefig(out / name, dpi=160)
    plt.close(fig)


def monthly_disputes(silver: Path, out: Path) -> None:
    rows = duckdb.sql(f"""
        SELECT date_trunc('month', creation_date) AS m, count(*) AS n
        FROM '{silver}/complaints.parquet' WHERE category = 'Transactions'
        GROUP BY 1 ORDER BY 1""").fetchall()
    rows = rows[1:-1]  # partial first and last months
    months, n = [r[0] for r in rows], [r[1] for r in rows]
    mean = sum(n) / len(n)
    fig, ax = plt.subplots(figsize=(8, 3.4))
    ax.plot(months, n, color=GREEN, lw=2)
    ax.axhline(mean, color=MUTED, lw=1, ls=(0, (3, 3)))
    ax.text(months[0], mean - 18, f"mean {mean:.0f} per month", color=MUTED, ha="left", va="top", fontsize=9.5)
    ax.set_ylim(0, max(n) * 1.25)
    ax.set_title("Unrecognised-charge complaints arrive at a steady ~380 a month")
    ax.set_ylabel("complaints per month")
    ax.grid(axis="x", visible=False)
    _save(fig, out, "disputes_per_month.png", "LATAM Bank dataset (synthetic), complaints in category Transactions, silver layer.")


def written_complaint_match(out: Path) -> None:
    labels = ["Point to exactly one charge", "Fit several charges", "Fit no charge"]
    share = [15.8, 63.5, 20.7]
    fig, ax = plt.subplots(figsize=(8, 2.6))
    colors = [GREEN, GRAY, GRAY]
    ax.barh(labels[::-1], share[::-1], color=colors[::-1], height=.55)
    for i, v in enumerate(share[::-1]):
        ax.text(v + 1, i, f"{v:.1f}%", va="center", color=INK, fontsize=10)
    ax.set_xlim(0, 80)
    ax.set_title("A written complaint alone rarely identifies the disputed charge")
    ax.set_xlabel("share of 13,580 real dispute complaints")
    ax.grid(axis="y", visible=False)
    _save(fig, out, "written_complaint_match.png", "Backtest of the PQR charge matcher on every dispute complaint (pipeline/pqr_backtest.py).")


def hard_set_before_after(out: Path) -> None:
    rows = [("AI reader (Claude path)", 24, 31), ("Free reader (rules + intent-v2)", 16, 30)]
    fig, ax = plt.subplots(figsize=(8, 2.8))
    for i, (label, before, after) in enumerate(rows):
        ax.plot([before, after], [i, i], color=GRAY, lw=2, zorder=1)
        ax.scatter([before], [i], s=70, color=GRAY, zorder=2)
        ax.scatter([after], [i], s=70, color=GREEN, zorder=3)
        ax.text(before - .6, i, f"{before}", ha="right", va="center", color=MUTED)
        ax.text(after + .6, i, f"{after}", ha="left", va="center", color=INK, fontweight="bold")
    ax.set_yticks(range(len(rows)), [r[0] for r in rows])
    ax.set_xlim(10, 36)
    ax.set_ylim(-.7, len(rows) - .3)
    ax.axvline(36, color=GRID)
    ax.set_xlabel("correct outcomes out of 36 (blind test)")
    ax.set_title("Vague-memory test: correct outcomes before (grey) and after fixes (green)", loc="left", x=-0.3)
    ax.grid(axis="y", visible=False)
    _save(fig, out, "hard_v1_before_after.png",
          "Offline simulation, one run. Claude path read by a Claude subagent given the production prompt (ADR-022).")


def cost_projection(out: Path) -> None:
    disputes, human_cost, model_cost = 4530, 3.0, 0.011
    shares = [s / 100 for s in range(0, 91, 5)]
    cost = [disputes * ((1 - s) * human_cost + s * model_cost) / 1000 for s in shares]
    fig, ax = plt.subplots(figsize=(8, 3.4))
    ax.plot([s * 100 for s in shares], cost, color=GREEN, lw=2)
    for s, label in ((0.63, "63%: hard-v1, free reader"), (0.70, "70%: test-v1")):
        c = disputes * ((1 - s) * human_cost + s * model_cost) / 1000
        ax.scatter([s * 100], [c], s=60, color=PURPLE if s < .7 else AMBER, zorder=3)
        ax.annotate(f"{label}\nUS$ {c:.1f}k", (s * 100, c), textcoords="offset points", xytext=(8, 10 if s < .7 else -30),
                    fontsize=9, color=INK)
    ax.set_xlim(0, 90)
    ax.set_ylim(0, 14.5)
    ax.set_xlabel("share of disputes resolved safely without a person")
    ax.set_ylabel("intake cost per year, US$ thousands")
    ax.set_title("Projection: yearly dispute-intake cost against the share resolved without a person")
    _save(fig, out, "cost_projection.png",
          "PROJECTION, not a measurement: 4,530 disputes/year; US$ 3.00 per human intake (7.2 min measured + 15 min assumed,\n"
          "US$ 8/h); US$ 0.011 model cost per automated case.")


def channels_results(out: Path) -> None:
    path = ROOT / "eval/results/channels-v1-test/results.jsonl"
    if not path.exists():
        return
    rows = [json.loads(line) for line in path.read_text().splitlines()]
    kinds = [("letter", "Written complaints"), ("alert", "Fraud-alert answers")]
    fig, ax = plt.subplots(figsize=(8, 2.9))
    y = 0
    ticks = []
    for kind, label in kinds:
        for system, color, name in (("rules_only", GRAY, "keyword rules"), ("rules_intent_v2", GREEN, "rules + intent-v2")):
            s = [r for r in rows if r["kind"] == kind and r["system"] == system]
            if not s:
                continue
            pct = 100 * sum(r["correct"] for r in s) / len(s)
            ax.barh(y, pct, color=color, height=.6)
            ax.text(pct + 1, y, f"{sum(r['correct'] for r in s)}/{len(s)}", va="center", fontsize=9.5)
            ticks.append((y, f"{label}, {name}"))
            y += 1
        y += .6
    ax.set_yticks([t[0] for t in ticks], [t[1] for t in ticks])
    ax.invert_yaxis()
    ax.set_xlim(0, 110)
    ax.set_xlabel("correct outcome, % of held-out cases")
    ax.set_title("channels-v1 test: the channels without a live conversation")
    ax.grid(axis="y", visible=False)
    _save(fig, out, "channels_v1.png", "Offline, deterministic, no model calls. Texts by an independent author; labels from the policy.")


def disputes_by_channel(silver: Path, out: Path) -> None:
    rows = duckdb.sql(f"""SELECT reception_channel, count(*) FROM '{silver}/complaints.parquet'
        WHERE category = 'Transactions' GROUP BY 1 ORDER BY 2""").fetchall()
    total = sum(r[1] for r in rows)
    fig, ax = plt.subplots(figsize=(8, 3.0))
    names = {"Call Center": "Call center", "Email": "Email", "Web": "Web form", "App": "App", "Branch": "Branch", "Regulator": "Regulator"}
    ax.barh([names.get(r[0], r[0]) for r in rows], [100 * r[1] / total for r in rows],
            color=[AMBER if r[0] == "Call Center" else GREEN for r in rows], height=.6)
    for i, r in enumerate(rows):
        ax.text(100 * r[1] / total + .8, i, f"{100 * r[1] / total:.1f}%", va="center", fontsize=9.5)
    ax.set_xlim(0, 60)
    ax.set_xlabel("share of 13,580 dispute complaints")
    ax.set_title("Half of disputes arrive by phone; the other half are written")
    ax.grid(axis="y", visible=False)
    _save(fig, out, "disputes_by_channel.png", "Complaints in category Transactions by reception channel, silver layer.")


def disputes_by_weekday(silver: Path, out: Path) -> None:
    rows = dict(duckdb.sql(f"""SELECT dayofweek(creation_date), count(*) FROM '{silver}/complaints.parquet'
        WHERE category = 'Transactions' GROUP BY 1""").fetchall())
    order = [1, 2, 3, 4, 5, 6, 0]
    labels = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    vals = [rows.get(d, 0) for d in order]
    fig, ax = plt.subplots(figsize=(8, 3.0))
    ax.bar(labels, vals, color=[GREEN if v >= 2000 else GRAY for v in vals], width=.6)
    for i, v in enumerate(vals):
        ax.text(i, v + 40, f"{v:,}", ha="center", fontsize=9.5)
    ax.set_ylim(0, max(vals) * 1.2)
    ax.set_ylabel("dispute complaints, 3 years")
    ax.set_title("Tuesday to Friday carry twice Sunday's load")
    ax.grid(axis="x", visible=False)
    _save(fig, out, "disputes_by_weekday.png", "Complaints in category Transactions by weekday of creation; hours of the day are flat.")


def amount_vs_threshold(gold: Path, out: Path) -> None:
    vals = [r[0] for r in duckdb.sql(f"""SELECT amount_usd FROM '{gold}/card_transactions.parquet'
        WHERE transaction_type = 'Purchase' AND transaction_status IN ('Approved', 'Pending') AND amount_usd IS NOT NULL
        USING SAMPLE 200000 ROWS (reservoir, 7)""").fetchall()]
    above = 100 * sum(v > 450 for v in vals) / len(vals)
    fig, ax = plt.subplots(figsize=(8, 3.2))
    bins = list(range(0, 526, 25))
    ax.hist(vals, bins=bins, color=GREEN, rwidth=.9)
    ax.axvline(450, color=PURPLE, lw=2)
    ax.text(515, ax.get_ylim()[1] * .9, f"US$ 450 limit:\n{above:.0f}% of purchases\ngo to a person on\namount alone",
            color=INK, fontsize=9.5, va="top")
    ax.set_xlim(0, 680)
    ax.set_xlabel("card purchase amount, US$ (uniform between 0 and 500 in this synthetic data)")
    ax.set_ylabel("purchases (sample)")
    ax.set_title("The amount rule sends one disputable purchase in ten to a person")
    ax.grid(axis="x", visible=False)
    _save(fig, out, "amount_vs_threshold.png", "200,000-row sample of approved/pending card purchases, gold layer; threshold calibrated at p90 (ADR-013).")


def fcr_by_reason(silver: Path, out: Path) -> None:
    rows = duckdb.sql(f"""SELECT contact_reason, 100 * avg(was_resolved::INT) FROM '{silver}/call_center_interactions.parquet'
        GROUP BY 1 ORDER BY 2""").fetchall()
    names = {"Queja": "Complaint", "Retención": "Retention", "Comercial": "Sales", "Técnico": "Technical",
             "Producto": "Product", "Transaccional": "Transactional"}
    fig, ax = plt.subplots(figsize=(8, 3.0))
    ax.barh([names.get(r[0], r[0]) for r in rows], [r[1] for r in rows],
            color=[PURPLE if r[0] == "Queja" else GRAY for r in rows], height=.6)
    for i, r in enumerate(rows):
        ax.text(r[1] + 1, i, f"{r[1]:.1f}%", va="center", fontsize=9.5)
    ax.set_xlim(0, 105)
    ax.set_xlabel("resolved at first contact")
    ax.set_title("Complaints are the contact least often solved on the first call")
    ax.grid(axis="y", visible=False)
    _save(fig, out, "fcr_by_reason.png", "686,296 call-center interactions, silver layer. In this data CSAT follows resolution: 3.0 resolved vs 2.0 not (1-4).")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--silver", default=str(ROOT / "data/silver"))
    ap.add_argument("--out", default=str(ROOT / "docs/figures"))
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    silver = Path(a.silver)
    if (silver / "complaints.parquet").exists():
        monthly_disputes(silver, out)
        disputes_by_channel(silver, out)
        disputes_by_weekday(silver, out)
    if (silver / "call_center_interactions.parquet").exists():
        fcr_by_reason(silver, out)
    if (silver.parent / "gold" / "card_transactions.parquet").exists():
        amount_vs_threshold(silver.parent / "gold", out)
    written_complaint_match(out)
    hard_set_before_after(out)
    cost_projection(out)
    channels_results(out)
    print(sorted(p.name for p in out.glob("*.png")))


if __name__ == "__main__":
    main()
