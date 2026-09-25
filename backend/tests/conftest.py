from datetime import timedelta

import pytest

from dispute_ops.auth import SessionService
from dispute_ops.store import Store
from dispute_ops.tools import BankingTools, FailureInjector
from helpers import SEED, FakeClock


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def store() -> Store:
    s = Store()
    s.load_seed(SEED)
    return s


@pytest.fixture
def sessions(clock) -> SessionService:
    return SessionService(b"test-secret", timedelta(minutes=15), clock)


@pytest.fixture
def failures() -> FailureInjector:
    return FailureInjector()


@pytest.fixture
def tools(store, sessions, clock, failures) -> BankingTools:
    return BankingTools(store, sessions, clock, policy_version="disputes_v1", failures=failures)
