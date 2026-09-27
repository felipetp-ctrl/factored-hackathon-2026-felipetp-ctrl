"""Learnability scan: which outcomes in the organizer data can be predicted at all?

For every candidate target the same protocol: features known at prediction time, a temporal split where the table
is dated (train before 2025-07-01, test after) or a seeded 80/20 split for snapshot tables, histogram gradient
boosting, and the same model trained on permuted labels as the "no signal" control. Metric: ROC-AUC for binary
targets, Spearman correlation for numeric ones, with bootstrap 95% intervals on the test set.
Report: `ml/results/learnability_scan.md` (+ MLflow experiment `learnability-scan`)."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass

import duckdb
import numpy as np
from scipy.stats import spearmanr
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingClassifier, HistGradientBoostingRegressor
from sklearn.metrics import roc_auc_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import OrdinalEncoder

from dispute_ops.ml.corpus import REPO

RAW, SILVER = REPO / "data" / "raw", REPO / "data" / "silver"
RESULTS = REPO / "ml" / "results"
SPLIT = "2025-07-01"
SEED = 7
MAX_TRAIN = 400_000


def raw(table: str) -> str:
    return f"read_csv('{RAW / table}/**/*.csv', union_by_name=true, header=true)"


CUSTOMERS = f"read_parquet('{SILVER / 'customers.parquet'}')"
AGENTS = f"read_csv('{RAW / 'service_agents.csv'}', header=true)"
CALLS = f"read_parquet('{SILVER / 'call_center_interactions.parquet'}')"
COMPLAINTS = f"read_parquet('{SILVER / 'complaints.parquet'}')"


@dataclass
class Target:
    name: str
    question: str
    kind: str  # binary | numeric
    sql: str  # must return: d (timestamp or NULL), y, and feature columns
    categorical: list[str]
    numeric: list[str]
    dated: bool = True


CUST_COLS = "c.segment, c.country, c.detected_accent AS customer_accent, c.credit_score, c.estimated_monthly_income"
TARGETS = [
    Target("csat_score", "CSAT score after a contact (CSAT surveys only, 1–4)", "numeric", f"""
        SELECT s.survey_date::TIMESTAMP AS d, s.main_score AS y, s.send_channel,
               i.channel, i.contact_reason, i.interaction_type, i.detected_sentiment, i.was_resolved::VARCHAR AS resolved,
               (i.customer_detected_accent = i.agent_used_accent)::VARCHAR AS accent_match, a.experience_level, a.agent_type,
               i.duration_seconds, i.wait_time_seconds, i.sentiment_score, a.avg_csat, {CUST_COLS}
        FROM {raw('satisfaction_surveys')} s LEFT JOIN {CALLS} i USING (interaction_id)
        LEFT JOIN {AGENTS} a ON a.agent_id = s.agent_id LEFT JOIN {CUSTOMERS} c ON c.customer_id = s.customer_id
        WHERE s.survey_type = 'CSAT'""",
           ["send_channel", "channel", "contact_reason", "interaction_type", "detected_sentiment", "resolved",
            "accent_match", "experience_level", "agent_type", "segment", "country", "customer_accent"],
           ["duration_seconds", "wait_time_seconds", "sentiment_score", "avg_csat", "credit_score", "estimated_monthly_income"]),
    Target("first_contact_resolution", "Call resolved at first contact (was_resolved)", "binary", f"""
        SELECT i.interaction_date::TIMESTAMP AS d, i.was_resolved::INT AS y, i.interaction_type, i.channel, i.contact_reason,
               (i.customer_detected_accent = i.agent_used_accent)::VARCHAR AS accent_match, a.experience_level, a.agent_type,
               a.specialty, hour(i.interaction_date)::VARCHAR AS hour, i.wait_time_seconds, a.avg_csat, {CUST_COLS}
        FROM {CALLS} i LEFT JOIN {AGENTS} a USING (agent_id) LEFT JOIN {CUSTOMERS} c USING (customer_id)""",
           ["interaction_type", "channel", "contact_reason", "accent_match", "experience_level", "agent_type", "specialty",
            "hour", "segment", "country", "customer_accent"],
           ["wait_time_seconds", "avg_csat", "credit_score", "estimated_monthly_income"]),
    Target("call_escalated", "Call escalated (was_escalated)", "binary", f"""
        SELECT i.interaction_date::TIMESTAMP AS d, i.was_escalated::INT AS y, i.interaction_type, i.channel, i.contact_reason,
               i.detected_sentiment, (i.customer_detected_accent = i.agent_used_accent)::VARCHAR AS accent_match,
               a.experience_level, a.agent_type, i.wait_time_seconds, i.duration_seconds, i.sentiment_score, {CUST_COLS}
        FROM {CALLS} i LEFT JOIN {AGENTS} a USING (agent_id) LEFT JOIN {CUSTOMERS} c USING (customer_id)""",
           ["interaction_type", "channel", "contact_reason", "detected_sentiment", "accent_match", "experience_level",
            "agent_type", "segment", "country", "customer_accent"],
           ["wait_time_seconds", "duration_seconds", "sentiment_score", "credit_score", "estimated_monthly_income"]),
    Target("complaint_sla_breached", "Complaint breaches its SLA (sla_breached)", "binary", f"""
        SELECT q.creation_date::TIMESTAMP AS d, q.sla_breached::INT AS y, q.case_type, q.category, q.subcategory,
               q.reception_channel, q.priority, q.is_repeat_complainer::VARCHAR AS repeat, q.claimed_amount, {CUST_COLS}
        FROM {COMPLAINTS} q LEFT JOIN {CUSTOMERS} c USING (customer_id)""",
           ["case_type", "category", "subcategory", "reception_channel", "priority", "repeat", "segment", "country",
            "customer_accent"], ["claimed_amount", "credit_score", "estimated_monthly_income"]),
    Target("complaint_resolution_days", "Days to resolve a complaint (resolution_days)", "numeric", f"""
        SELECT q.creation_date::TIMESTAMP AS d, q.resolution_days AS y, q.case_type, q.category, q.subcategory,
               q.reception_channel, q.priority, q.is_repeat_complainer::VARCHAR AS repeat, q.claimed_amount, {CUST_COLS}
        FROM {COMPLAINTS} q LEFT JOIN {CUSTOMERS} c USING (customer_id) WHERE q.resolution_days IS NOT NULL""",
           ["case_type", "category", "subcategory", "reception_channel", "priority", "repeat", "segment", "country",
            "customer_accent"], ["claimed_amount", "credit_score", "estimated_monthly_income"]),
    Target("complaint_resolution_satisfaction", "Satisfaction with the resolution (1–5)", "numeric", f"""
        SELECT q.creation_date::TIMESTAMP AS d, q.resolution_satisfaction AS y, q.case_type, q.category, q.subcategory,
               q.reception_channel, q.priority, q.status, q.compensation_granted::VARCHAR AS compensated,
               q.sla_breached::VARCHAR AS sla_breached, q.resolution_days, {CUST_COLS}
        FROM {COMPLAINTS} q LEFT JOIN {CUSTOMERS} c USING (customer_id) WHERE q.resolution_satisfaction IS NOT NULL""",
           ["case_type", "category", "subcategory", "reception_channel", "priority", "status", "compensated", "sla_breached",
            "segment", "country", "customer_accent"], ["resolution_days", "credit_score", "estimated_monthly_income"]),
    Target("campaign_conversion", "Marketing send converts (had_conversion)", "binary", f"""
        SELECT s.send_date::TIMESTAMP AS d, s.had_conversion::INT AS y, s.send_channel, s.template_used,
               m.campaign_type, m.campaign_objective, m.promoted_product, m.target_segment,
               (m.target_segment = c.segment)::VARCHAR AS segment_match, dayofweek(s.send_date::TIMESTAMP)::VARCHAR AS dow,
               s.send_cost, m.expected_conversion_rate, {CUST_COLS}
        FROM {raw('campaign_sends')} s LEFT JOIN read_csv('{RAW / 'marketing_campaigns.csv'}', header=true) m USING (campaign_id)
        LEFT JOIN {CUSTOMERS} c USING (customer_id) WHERE s.was_delivered""",
           ["send_channel", "template_used", "campaign_type", "campaign_objective", "promoted_product", "target_segment",
            "segment_match", "dow", "segment", "country", "customer_accent"],
           ["send_cost", "expected_conversion_rate", "credit_score", "estimated_monthly_income"]),
    Target("product_past_due", "Product is past due (days_past_due > 0)", "binary", f"""
        SELECT NULL::TIMESTAMP AS d, (p.days_past_due > 0)::INT AS y, p.product_type, p.product_status, p.opening_channel,
               p.has_linked_app::VARCHAR AS app, p.current_balance, p.credit_limit, p.interest_rate,
               date_diff('day', p.opening_date::DATE, DATE '2026-06-17') AS age_days, {CUST_COLS}
        FROM read_parquet('{SILVER / 'products.parquet'}') p LEFT JOIN {CUSTOMERS} c USING (customer_id)""",
           ["product_type", "product_status", "opening_channel", "app", "segment", "country", "customer_accent"],
           ["current_balance", "credit_limit", "interest_rate", "age_days", "credit_score", "estimated_monthly_income"],
           dated=False),
    Target("customer_inactive", "Customer is not active (customer_status)", "binary", f"""
        SELECT NULL::TIMESTAMP AS d, (c.customer_status <> 'Active')::INT AS y, c.segment, c.country,
               c.detected_accent AS customer_accent, c.occupation, c.marital_status, c.education_level, c.gender,
               c.accepts_marketing::VARCHAR AS marketing, c.credit_score, c.estimated_monthly_income,
               date_diff('year', c.date_of_birth, DATE '2026-06-17') AS age,
               date_diff('day', c.registration_date::DATE, DATE '2026-06-17') AS tenure_days
        FROM {CUSTOMERS} c""",
           ["segment", "country", "customer_accent", "occupation", "marital_status", "education_level", "gender", "marketing"],
           ["credit_score", "estimated_monthly_income", "age", "tenure_days"], dated=False),
]


def _model(t: Target):
    pre = ColumnTransformer([("cat", OrdinalEncoder(handle_unknown="use_encoded_value", unknown_value=-1,
                                                    encoded_missing_value=-2), t.categorical),
                             ("num", "passthrough", t.numeric)])
    kw = dict(categorical_features=list(range(len(t.categorical))), max_iter=200, random_state=SEED)
    est = HistGradientBoostingClassifier(**kw) if t.kind == "binary" else HistGradientBoostingRegressor(**kw)
    return make_pipeline(pre, est)


def _score(t: Target, y, s) -> float:
    return float(roc_auc_score(y, s)) if t.kind == "binary" else float(spearmanr(y, s).statistic)


def _boot(t: Target, y, s, n=100) -> tuple[float, float]:
    rng = np.random.default_rng(SEED)
    idx_all = np.arange(len(y)) if len(y) <= 200_000 else rng.choice(len(y), 200_000, replace=False)
    vals = []
    for _ in range(n):
        idx = rng.choice(idx_all, len(idx_all))
        if t.kind == "binary" and len(set(y[idx])) < 2:
            continue
        vals.append(_score(t, y[idx], s[idx]))
    return float(np.percentile(vals, 2.5)), float(np.percentile(vals, 97.5))


def scan_one(t: Target) -> dict:
    df = duckdb.sql(t.sql).df().dropna(subset=["y"])
    for c in t.categorical:
        df[c] = df[c].astype("string").fillna("missing").astype(str)
        top = df[c].value_counts().index[:200]  # gradient boosting takes at most 255 levels
        df.loc[~df[c].isin(top), c] = "other"
    rng = np.random.default_rng(SEED)
    if t.dated and df["d"].notna().any():
        train, test = df[df.d < SPLIT], df[df.d >= SPLIT]
        split = f"temporal at {SPLIT}"
    else:
        mask = rng.random(len(df)) < 0.8
        train, test = df[mask], df[~mask]
        split = "random 80/20 (snapshot table)"
    if len(train) > MAX_TRAIN:
        train = train.sample(MAX_TRAIN, random_state=SEED)
    x_cols = t.categorical + t.numeric
    y_tr, y_te = train.y.values.astype(float), test.y.values.astype(float)
    model = _model(t).fit(train[x_cols], y_tr)
    control = _model(t).fit(train[x_cols], rng.permutation(y_tr))

    def predict(m):
        return m.predict_proba(test[x_cols])[:, 1] if t.kind == "binary" else m.predict(test[x_cols])
    s, sc = predict(model), predict(control)
    # What drives it: permutation importance on a test sample (drop in the metric when a column is shuffled).
    from sklearn.inspection import permutation_importance
    sample = test.sample(min(len(test), 40_000), random_state=SEED)
    scoring = "roc_auc" if t.kind == "binary" else (lambda m, X, y: float(spearmanr(y, m.predict(X)).statistic))
    imp = permutation_importance(model, sample[x_cols], sample.y.values.astype(float), scoring=scoring, n_repeats=3,
                                 random_state=SEED)
    importance = sorted(zip(x_cols, imp.importances_mean), key=lambda kv: -kv[1])[:5]
    # Does the model add anything beyond a one-column lookup table (train mean of y per level of the top feature)?
    top = importance[0][0]
    if top in t.categorical:
        means = train.groupby(top).y.mean()
        lookup = test[top].map(means).fillna(float(train.y.mean())).values
    else:  # numeric: deciles of the train distribution
        edges = np.unique(np.quantile(train[top].dropna(), np.linspace(0, 1, 11)))
        bins = lambda v: np.clip(np.searchsorted(edges, v.fillna(edges[0]).values, side="right") - 1, 0, len(edges) - 1)
        means = train.assign(b=bins(train[top])).groupby("b").y.mean()
        lookup = means.reindex(bins(test[top])).fillna(float(train.y.mean())).values
    return {"importance": [[k, float(v)] for k, v in importance], "lookup_feature": top,
            "lookup": _score(t, y_te, lookup),"target": t.name, "question": t.question, "kind": t.kind, "split": split,
            "train_rows": len(train), "test_rows": len(test),
            "base_rate": float(y_te.mean()), "metric": "ROC-AUC" if t.kind == "binary" else "Spearman ρ",
            "model": _score(t, y_te, s), "model_ci": _boot(t, y_te, s),
            "control": _score(t, y_te, sc), "control_ci": _boot(t, y_te, sc)}


def verdict(r: dict) -> str:
    chance = 0.5 if r["kind"] == "binary" else 0.0
    lo, hi = r["model_ci"]
    if lo <= chance + 0.02 and r["model"] - chance < 0.03:
        return "no signal"
    return "weak signal" if r["model"] - chance < 0.1 else "signal"


def run() -> str:
    import mlflow

    (REPO / "mlruns").mkdir(exist_ok=True)
    mlflow.set_tracking_uri(f"sqlite:///{REPO / 'mlruns' / 'mlflow.db'}")
    mlflow.set_experiment("learnability-scan")
    started = time.perf_counter()
    rows = []
    for t in TARGETS:
        t0 = time.perf_counter()
        r = scan_one(t)
        r["verdict"], r["seconds"] = verdict(r), time.perf_counter() - t0
        rows.append(r)
        with mlflow.start_run(run_name=t.name):
            mlflow.log_params({"target": t.name, "split": r["split"], "metric": r["metric"], "features": ",".join(t.categorical + t.numeric)})
            mlflow.log_metrics({"test_metric": r["model"], "control_metric": r["control"], "base_rate": r["base_rate"]})
        print(f"{t.name}: {r['metric']} {r['model']:.3f} (control {r['control']:.3f}) -> {r['verdict']}", flush=True)
    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS / "learnability_scan.json").write_text(json.dumps(rows, indent=2, default=float))
    text = markdown(rows, time.perf_counter() - started)
    (RESULTS / "learnability_scan.md").write_text(text)
    return text


def markdown(rows: list[dict], seconds: float) -> str:
    lines = [
        "# Learnability scan of the organizer data", "",
        "> Organizer data (synthetic LATAM Bank). Offline. Same protocol for every target: features known at prediction "
        f"time, temporal split at {SPLIT} for dated tables (seeded 80/20 for snapshots), histogram gradient boosting, and "
        "the same model trained on permuted labels as the no-signal control. 95% bootstrap intervals on the test set.", "",
        "| Target | Question | Metric | Model (95% CI) | One-column lookup | Permuted control | Base rate / mean | Test rows | Verdict |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        lines.append(f"| `{r['target']}` | {r['question']} | {r['metric']} | {r['model']:.3f} ({r['model_ci'][0]:.3f}–"
                     f"{r['model_ci'][1]:.3f}) | {r['lookup']:.3f} (`{r['lookup_feature']}`) | {r['control']:.3f} | {r['base_rate']:.3f} | {r['test_rows']:,} | "
                     f"**{r['verdict']}** |")
    lines += ["", "**Reading.** Where there is signal, a lookup table on one column matches the gradient-boosting model: the "
              "generator encodes each outcome as a function of a single field (CSAT of `was_resolved`, first-contact "
              "resolution of `contact_reason`, conversion of `send_channel`). Everything else — escalation, SLA, "
              "resolution time and satisfaction, delinquency, customer status, fraud beyond the score — is noise. "
              "There is no multivariate pattern in this dataset for a trained model to add.", ""]
    lines += ["", "## What drives the targets with signal (permutation importance: drop in the metric)", ""]
    for r in rows:
        if r["verdict"] != "no signal":
            lines.append(f"- `{r['target']}`: " + ", ".join(f"{k} {v:+.3f}" for k, v in r["importance"] if abs(v) >= 0.002))
    lines += ["", "Fraud (`is_fraud`) is covered separately in [fraud_label_audit.md](fraud_label_audit.md): no behavioural "
              "signal; the label follows the organizer's `fraud_score`.", "",
              f"Runtime: {seconds:.0f} s on a laptop.", ""]
    return "\n".join(lines)
