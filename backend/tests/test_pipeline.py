import shutil
from datetime import datetime, timezone
from pathlib import Path

import duckdb
import pytest

from dispute_ops.pipeline.contracts import CONTRACTS
from dispute_ops.pipeline.layers import ContractError, run_pipeline

FIXTURE = Path(__file__).parent / "fixtures" / "raw_mini"
AS_OF = datetime(2026, 6, 17, 12, tzinfo=timezone.utc)
TXN_HEADER = (FIXTURE / "transactions/year=2026/month=06/day=16/transactions_20260616.csv").read_text().splitlines()[0]


@pytest.fixture
def raw(tmp_path):
    d = tmp_path / "raw"
    shutil.copytree(FIXTURE, d)
    return d


def q(path, sql):
    return duckdb.sql(sql.replace("FROM T", f"FROM read_parquet('{path}')")).fetchall()


def test_first_run_types_dedups_checks_and_quarantines(raw, tmp_path):
    out = tmp_path / "out"
    m = run_pipeline(raw, out, AS_OF)["tables"]
    cust = m["customers"]
    assert cust["duplicate_rows_removed"] == 1 and cust["silver_rows"] == 2
    assert cust["domain_violations"]["segment"] == {"Gold": 1}
    assert q(out / "silver/customers.parquet", "SELECT segment FROM T WHERE customer_id='CLI-A'") == [("Premium",)]
    assert m["products"]["orphans_quarantined"] == {"customer_id": 1}
    tx = m["transactions"]
    assert tx["rejected_lines"] >= 1
    assert tx["cast_failures"] == {"fraud_score": 1}
    assert tx["orphans_quarantined"] == {"customer_id": 1}
    assert tx["silver_rows"] == 4
    assert m["complaints"]["orphans_nulled"] == {"affected_product_id": 1}
    assert (out / "silver/_quarantine/transactions__customer_id.parquet").exists()


def test_gold_views(raw, tmp_path):
    out = tmp_path / "out"
    gold = run_pipeline(raw, out, AS_OF)["gold_rows"]
    assert gold["fraud_alert_candidates"] == 1  # TX-2, score 91, within 48h
    assert gold["dispute_complaints"] == 2
    assert q(out / "gold/customer_dim.parquet", "SELECT is_repeat_complainer FROM T WHERE customer_id='CLI-B'") == [(True,)]
    # silver keeps (and reports) the raw 'México'; gold normalises it for the policy thresholds
    assert q(out / "silver/customers.parquet", "SELECT country FROM T WHERE customer_id='CLI-A'") == [("México",)]
    assert q(out / "gold/customer_dim.parquet", "SELECT country FROM T WHERE customer_id='CLI-A'") == [("Mexico",)]


def test_rerun_without_new_files_is_idempotent(raw, tmp_path):
    out = tmp_path / "out"
    run_pipeline(raw, out, AS_OF)
    second = run_pipeline(raw, out, AS_OF)["tables"]["transactions"]
    assert second["new_files"] == 0 and second["silver_rows"] == 4
    assert len(list((out / "bronze/transactions").glob("*.parquet"))) == 1


def test_late_arrival_and_corrected_redelivery_are_applied(raw, tmp_path):
    out = tmp_path / "out"
    run_pipeline(raw, out, AS_OF)
    # A late file for an EARLIER day arrives after the first run, re-delivering TX-1 with a corrected
    # status plus a brand-new transaction, and a new column (schema evolution).
    late = raw / "transactions/year=2026/month=06/day=15"
    late.mkdir(parents=True)
    (late / "transactions_20260615.csv").write_text(
        TXN_HEADER + ",channel_detail\n"
        "TX-1,2026-06-16 10:00:00,2026-06-17,PRD-A1,CLI-A,Purchase,Other,1250.0,MXN,68.5,POS,,Amazon MX,Other,Mexico,CDMX,Reversed,00,False,12.0,19.4,-99.1,contactless\n"
        "TX-6,2026-06-15 09:00:00,2026-06-15,PRD-A1,CLI-A,Purchase,Other,99.0,MXN,5.4,POS,,Oxxo,Food,Mexico,CDMX,Approved,00,False,2.0,19.4,-99.1,chip\n"
    )
    m = run_pipeline(raw, out, AS_OF)["tables"]["transactions"]
    assert m["new_files"] == 1 and m["unexpected_columns"] == ["channel_detail"]
    assert m["silver_rows"] == 5
    assert q(out / "silver/transactions.parquet", "SELECT transaction_status FROM T WHERE transaction_id='TX-1'") == [("Reversed",)]


def test_missing_required_column_stops_the_table(raw, tmp_path):
    f = raw / "customers.csv"
    lines = f.read_text().splitlines()
    f.write_text("\n".join(",".join(x.split(",")[1:]) for x in lines) + "\n")  # drop customer_id
    with pytest.raises(ContractError):
        run_pipeline(raw, tmp_path / "out", AS_OF, tables=["customers"])


def test_contracts_cover_every_column_in_the_dictionary_for_core_tables():
    assert len(CONTRACTS["transactions"].columns) == 22
    assert len(CONTRACTS["complaints"].columns) == 27
    assert len(CONTRACTS["customers"].columns) == 27


def test_export_demo_store_feeds_the_service(raw, tmp_path):
    from dispute_ops.pipeline.export import export_demo_store
    from dispute_ops.store import Store

    out = tmp_path / "out"
    run_pipeline(raw, out, AS_OF)
    counts = export_demo_store(out / "gold", tmp_path / "demo.db", AS_OF, n_customers=10)
    assert counts == {"customers": 2, "products": 2, "transactions": 4}
    store = Store(tmp_path / "demo.db")
    t = store.get_transaction("TX-2")
    assert t.amount_usd == 822 and str(t.fraud_score) == "91.00"
    assert store.get_customer("CLI-B").is_repeat_complainer is True


def test_container_runs_on_exported_gold_store_without_touching_it(raw, tmp_path):
    from dispute_ops.container import Container, Settings
    from dispute_ops.pipeline.export import export_demo_store
    from nlu_fakes import ScriptedNlu

    out = tmp_path / "out"
    run_pipeline(raw, out, AS_OF)
    export_demo_store(out / "gold", tmp_path / "demo.db", AS_OF)
    before = (tmp_path / "demo.db").read_bytes()
    c = Container.build(Settings(session_secret="s", demo_db=str(tmp_path / "demo.db")), nlu=ScriptedNlu())
    token = c.sessions.issue("CLI-A")
    assert [t.transaction_id for t in c.tools.search_transactions(token)] == ["TX-2", "TX-7", "TX-1"]
    c.tools.block_card(token, "PRD-A1", idempotency_key="k")
    assert (tmp_path / "demo.db").read_bytes() == before


def test_gold_scenario_generation_labels_with_policy(raw, tmp_path):
    from dispute_ops.evaluation.gold_scenarios import generate, load, save
    from dispute_ops.pipeline.export import export_demo_store
    from dispute_ops.store import Store

    out = tmp_path / "out"
    run_pipeline(raw, out, AS_OF)
    export_demo_store(out / "gold", tmp_path / "demo.db", AS_OF)
    scenarios = generate(Store(tmp_path / "demo.db"), AS_OF, per_category=2)
    by_txn = {s.expected.transaction_id: s.expected.outcome for s in scenarios if s.category in ("normal", "human_required")}
    assert by_txn.get("TX-1") == "done"          # 68.5 USD, eligible
    assert by_txn.get("TX-2") == "handoff"       # 822 USD > MX threshold
    save(scenarios, tmp_path / "s.json", {"x": 1})
    assert load(tmp_path / "s.json") == scenarios


def test_gold_fills_amount_usd_from_currency_or_daily_fx(raw, tmp_path):
    out = tmp_path / "out"
    run_pipeline(raw, out, AS_OF)
    rows = dict((r[0], (r[1], r[2])) for r in q(out / "gold/card_transactions.parquet",
                "SELECT transaction_id, amount_usd, amount_usd_source FROM T"))
    assert rows["TX-1"] == (68.5, "reported")
    assert rows["TX-7"] == (640.0, "identity_usd")
    assert rows["TX-3"][0] == pytest.approx(22.5) and rows["TX-3"][1] == "fx_daily"


def test_a_redelivery_that_moves_a_card_to_another_customer_is_quarantined(raw, tmp_path):
    """Identity columns are immutable: every product id the organizer's backup shares with the current delivery has a
    different owner, and newest-wins would silently hand a card (and its charges) to someone else."""
    import csv

    out = tmp_path / "out"
    run_pipeline(raw, out, AS_OF, tables=["branches", "customers", "products"])
    rows = list(csv.DictReader(open(raw / "products.csv", encoding="utf-8-sig")))
    customers = sorted({r["customer_id"] for r in rows})
    moved = dict(rows[0])
    moved["customer_id"] = next(c for c in customers if c != moved["customer_id"])
    moved["last_updated"] = "2026-12-31 00:00:00"
    kept = dict(rows[1])
    kept["current_balance"] = "123.45"  # a mutable field may change
    kept["last_updated"] = "2026-12-31 00:00:00"
    with open(raw / "products_redelivery.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows([moved, kept])
    from dataclasses import replace

    from dispute_ops.pipeline import contracts

    original = contracts.CONTRACTS["products"]
    contracts.CONTRACTS["products"] = replace(original, source="products*.csv")
    try:
        m = run_pipeline(raw, out, AS_OF, tables=["products"])["tables"]["products"]
    finally:
        contracts.CONTRACTS["products"] = original
    assert m["immutable_conflicts"] == {"customer_id": 1}
    silver = duckdb.sql(f"SELECT product_id, current_balance FROM '{out}/silver/products.parquet'").fetchall()
    ids = {r[0] for r in silver}
    assert moved["product_id"] not in ids and kept["product_id"] in ids
    assert dict(silver)[kept["product_id"]] == 123.45
    assert (out / "silver/_quarantine/products__immutable_customer_id.parquet").exists()


def test_freshness_is_reported_per_fact_table(raw, tmp_path):
    f = run_pipeline(raw, tmp_path / "out", AS_OF)["freshness"]
    assert f["transactions"]["status"] in ("fresh", "stale") and f["transactions"]["lag_days"] is not None
    assert "late_rows" in f["transactions"]
