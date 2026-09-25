import pytest

from dispute_ops.store import Store
from helpers import SEED, FakeClock


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def store() -> Store:
    s = Store()
    s.load_seed(SEED)
    return s
