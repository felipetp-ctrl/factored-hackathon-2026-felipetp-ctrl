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


# ---- ADR-028: incremental silver, quality gates, write-audit-publish ------------------------------------------------

CUST_C = ("CLI-C,D3,CURP,Carla,Ruiz,1985-02-02,F,,,,,CDMX,CDMX,Mexico,,mexican,Basic,650,15000,,,,2024-01-01 10:00:00,"
          "SUC-1,Active,2026-06-10 00:00:00,True")


def _snapshot(out):
    """Every silver and quarantine table, as a set of rows."""
    files = sorted(p.relative_to(out / "silver") for p in (out / "silver").rglob("*.parquet"))
    return {str(f): sorted(map(repr, duckdb.sql(f"SELECT COLUMNS(*)::VARCHAR FROM read_parquet('{out / 'silver' / f}')").fetchall()))
            for f in files}


def _deliver_2(raw):
    late = raw / "transactions/year=2026/month=06/day=15"
    late.mkdir(parents=True)
    (late / "transactions_20260615.csv").write_text(
        TXN_HEADER + "\n"
        "TX-1,2026-06-16 10:00:00,2026-06-18,PRD-A1,CLI-A,Purchase,Other,1250.0,MXN,68.5,POS,,Amazon MX,Other,Mexico,CDMX,Reversed,00,False,12.0,19.4,-99.1\n"
        "TX-6,2026-06-15 09:00:00,2026-06-15,PRD-A1,CLI-A,Purchase,Other,99.0,MXN,5.4,POS,,Oxxo,Food,Mexico,CDMX,Approved,00,False,2.0,19.4,-99.1\n"
        "TX-8,2026-06-15 11:00:00,2026-06-15,PRD-C1,CLI-C,Purchase,Other,40.0,USD,40.0,Online,,Netflix,Entertainment,Mexico,CDMX,Approved,00,False,3.0,19.4,-99.1\n"
    )
    header = (raw / "complaints/year=2026/month=06/day=16/complaints_20260616.csv").read_text().splitlines()
    day17 = raw / "complaints/year=2026/month=06/day=17"
    day17.mkdir(parents=True)
    row = header[1].replace("Q-1,", "Q-9,", 1).replace("2026-06-16 13:00:00,2026-06-16,CLI-A", "2026-06-17 09:00:00,2026-06-17,CLI-B").replace("PRD-A1", "PRD-C1")
    (day17 / "complaints_20260617.csv").write_text(header[0] + "\n" + row + "\n")


def _deliver_3(raw):
    # The parents of TX-8 and Q-9 arrive late; PRD-A1 is re-delivered with another owner (identity conflict).
    with open(raw / "customers.csv", "a") as f:
        f.write(CUST_C + "\n")
    with open(raw / "products.csv", "a") as f:
        f.write("PRD-C1,CLI-C,Credit Card,7000,USD,0,1000,30,2026-01-01,,SUC-1,Active,App,True,0,,2026-06-10 00:00:00\n")
        f.write("PRD-A1,CLI-B,Credit Card,4000,MXN,100.0,5000,40,2022-01-01,,SUC-1,Active,App,True,0,,2026-06-20 00:00:00\n")


def test_incremental_silver_equals_a_full_rebuild_of_the_same_bronze(raw, tmp_path):
    out = tmp_path / "out"
    run_pipeline(raw, out, AS_OF)
    _deliver_2(raw)
    m2 = run_pipeline(raw, out, AS_OF)["tables"]
    assert m2["transactions"]["mode"].startswith("incremental") and m2["transactions"]["orphans_quarantined"]["customer_id"] == 2
    _deliver_3(raw)
    m3 = run_pipeline(raw, out, AS_OF)
    tx = dict(q(out / "silver/transactions.parquet", "SELECT transaction_id, product_id FROM T"))
    assert "TX-8" in tx                                  # its parents arrived: recomputed through the FK
    assert not any(p == "PRD-A1" for p in tx.values())   # its card changed owner: card and its charges quarantined
    assert q(out / "silver/complaints.parquet", "SELECT affected_product_id FROM T WHERE complaint_id='Q-9'") == [("PRD-C1",)]
    assert m3["tables"]["products"]["immutable_conflicts"] == {"customer_id": 1}
    incremental = _snapshot(out)
    full = run_pipeline(raw, out, AS_OF, full=True)
    assert all(t["mode"] == "full" for t in full["tables"].values() if not t["skipped"])
    assert _snapshot(out) == incremental


def test_a_run_without_new_files_recomputes_nothing(raw, tmp_path):
    out = tmp_path / "out"
    run_pipeline(raw, out, AS_OF)
    before = _snapshot(out)
    m = run_pipeline(raw, out, AS_OF)
    assert m["tables"]["transactions"]["mode"] == "incremental (0 keys recomputed)" and _snapshot(out) == before


def test_rows_are_conserved_and_the_run_is_published(raw, tmp_path):
    m = run_pipeline(raw, tmp_path / "out", AS_OF)
    assert m["status"] == "published"
    conservation = [g for g in m["gates"] if g["gate"].endswith("row conservation")]
    assert conservation and all(g["status"] == "pass" for g in conservation)
    history = (tmp_path / "out/_state/runs.jsonl").read_text().splitlines()
    assert len(history) == 1 and '"status": "published"' in history[0]


def test_a_failing_gate_keeps_the_previous_gold(raw, tmp_path):
    out = tmp_path / "out"
    run_pipeline(raw, out, AS_OF)
    gold_before = {p.name: p.read_bytes() for p in (out / "gold").glob("*.parquet")}
    # A re-delivery that hands every card to another customer: all products are quarantined, silver loses them.
    lines = (raw / "products.csv").read_text().splitlines()
    moved = [lines[0]] + [ln.replace(",CLI-A,", ",CLI-X,").replace(",CLI-B,", ",CLI-A,").replace(",CLI-X,", ",CLI-B,")
                          .rsplit(",", 1)[0] + ",2026-06-30 00:00:00" for ln in lines[1:]]
    (raw / "products.csv").write_text("\n".join(lines + moved[1:]) + "\n")
    m = run_pipeline(raw, out, AS_OF)
    assert m["status"] == "blocked"
    failed = {g["gate"] for g in m["gates"] if g["status"] == "fail" and g["severity"] == "block"}
    assert "products: volume" in failed
    assert {p.name: p.read_bytes() for p in (out / "gold").glob("*.parquet")} == gold_before
    assert not (out / "gold.__staging__").exists()


def test_catalog_documents_every_contract_column(raw, tmp_path):
    from dispute_ops.pipeline.catalog import render

    text = render(run_pipeline(raw, tmp_path / "out", AS_OF))
    for c in CONTRACTS.values():
        assert f"### `{c.name}`" in text
        assert all(f"| `{col}` |" in text for col in c.columns)
    assert "orphan quarantined" in text and "`card_transactions`" in text


def test_operating_insights_from_committed_results():
    pytest.importorskip("scipy")
    pytest.importorskip("matplotlib")
    from dispute_ops.pipeline.insights import business_sensitivity, product_funnel

    p = product_funnel()
    counts = [n for _, n in p["steps"]]
    assert counts == sorted(counts, reverse=True) and counts[0] == 48 and counts[-1] == 43
    b = business_sensitivity()
    assert b["bars"][0]["assumption"].startswith("back-office")  # the widest bar is the unmeasured assumption
    assert all(min(x["low"], x["high"]) <= b["base_saving"] <= max(x["low"], x["high"]) for x in b["bars"])


def test_a_delivery_with_an_emptied_column_is_blocked(raw, tmp_path, monkeypatch):
    """A new day whose merchant names are all missing: row counts and contracts pass, the column profile does not."""
    from dispute_ops.pipeline import gates
    monkeypatch.setattr(gates, "MIN_PROFILE_ROWS", 1)
    out = tmp_path / "out"
    run_pipeline(raw, out, AS_OF)
    gold_before = {p.name: p.read_bytes() for p in (out / "gold").glob("*.parquet")}
    src = next((raw / "transactions").rglob("*.csv"))
    header, *rows = src.read_text().splitlines()
    cols = header.split(",")
    new = []
    for i, line in enumerate(rows):
        v = line.split(",")
        if len(v) != len(cols):  # the fixture has malformed lines on purpose
            continue
        v[cols.index("transaction_id")] = f"TX-NEW-{i}"
        v[cols.index("merchant_name")] = ""
        new.append(",".join(v))
    day = raw / "transactions/year=2026/month=06/day=17"
    day.mkdir(parents=True)
    (day / "transactions_20260617.csv").write_text("\n".join([header, *new]) + "\n")
    m = run_pipeline(raw, out, AS_OF)
    failed = {g["gate"]: g["detail"] for g in m["gates"] if g["status"] == "fail" and g["severity"] == "block"}
    assert m["status"] == "blocked" and "transactions: column profile" in failed
    assert "merchant_name" in failed["transactions: column profile"]
    assert {p.name: p.read_bytes() for p in (out / "gold").glob("*.parquet")} == gold_before


def test_an_ordinary_delivery_passes_the_column_profile(raw, tmp_path, monkeypatch):
    from dispute_ops.pipeline import gates
    monkeypatch.setattr(gates, "MIN_PROFILE_ROWS", 1)
    m = run_pipeline(raw, tmp_path / "out", AS_OF)
    assert m["status"] == "published"
    assert all(g["status"] == "pass" for g in m["gates"] if g["gate"].endswith("column profile"))
