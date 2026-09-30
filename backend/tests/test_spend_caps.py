"""ADR-026: durable spend caps shared by the demo and evaluation runs (ledger faked, no database, no API calls)."""

from types import SimpleNamespace

import pytest

from dispute_ops.conversation import Budget
from dispute_ops.metering import BudgetExceeded, MeteredClient
from dispute_ops.spend_ledger import LedgerError


class FakeLedger:
    """Stands in for the Postgres table: another process's spend shows up in total_all."""

    def __init__(self, others_usd: float = 0.0, fail: bool = False) -> None:
        self.total_all, self.total_source, self.today_source = others_usd, 0.0, 0.0
        self.fail = fail

    def refresh(self, force: bool = False) -> None:
        if self.fail:
            raise LedgerError("connection lost")

    def add(self, usd: float) -> None:
        if self.fail:
            raise LedgerError("connection lost")
        self.total_all += usd
        self.total_source += usd
        self.today_source += usd


def test_global_ceiling_counts_every_source():
    ledger = FakeLedger(others_usd=4.0)  # evaluation runs already spent 4
    demo = Budget(None, global_limit_usd=9.5, ledger=ledger)
    demo.add(5.0)
    assert not demo.exhausted() and demo.status()["all_sources_usd"] == 9.0
    demo.add(0.5)
    assert demo.exhausted()
    assert Budget(None, global_limit_usd=9.5, ledger=FakeLedger(others_usd=9.5)).exhausted()


def test_source_cap_is_read_from_the_ledger_so_a_restart_keeps_it():
    ledger = FakeLedger()
    Budget(4.75, ledger=ledger).add(4.75)
    assert Budget(4.75, ledger=ledger).exhausted()  # a new process sees what the old one spent


def test_ledger_failure_fails_closed():
    ledger = FakeLedger()
    b = Budget(10.0, ledger=ledger)
    assert not b.exhausted()
    ledger.fail = True
    assert b.exhausted() and b.failed


def _fake_client(calls):
    def create(**kw):
        calls.append(kw)
        return SimpleNamespace(usage=SimpleNamespace(input_tokens=1_000_000, output_tokens=0))

    messages = SimpleNamespace(create=create, parse=create)
    return SimpleNamespace(messages=messages, with_options=lambda **kw: SimpleNamespace(messages=messages))


def test_metered_client_records_cost_and_stops_at_the_cap():
    calls: list = []
    budget = Budget(1.5, ledger=FakeLedger())
    client = MeteredClient(_fake_client(calls), budget).with_options(timeout=5)
    client.messages.create(model="claude-haiku-4-5")  # 1M input tokens = US$ 1
    assert budget.ledger.total_source == pytest.approx(1.0)
    client.messages.parse(model="claude-haiku-4-5")
    with pytest.raises(BudgetExceeded):
        client.messages.create(model="claude-haiku-4-5")
    assert len(calls) == 2


def test_metered_client_refuses_a_model_without_a_price():
    with pytest.raises(BudgetExceeded):
        MeteredClient(_fake_client([]), Budget(10.0)).messages.create(model="some-unpriced-model")


def test_budget_exceeded_is_not_an_api_error_so_runs_stop():
    import anthropic

    assert not issubclass(BudgetExceeded, anthropic.APIError)
