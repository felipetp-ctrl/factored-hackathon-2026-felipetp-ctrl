import pytest

from dispute_ops.errors import ToolUnavailable
from dispute_ops.retry import call_with_retry


def flaky(failures_before_success):
    calls = {"n": 0}

    def fn():
        calls["n"] += 1
        if calls["n"] <= failures_before_success:
            raise ToolUnavailable("x")
        return "ok"

    return fn, calls


def test_retries_then_succeeds_with_backoff():
    fn, calls = flaky(2)
    sleeps = []
    assert call_with_retry(fn, sleep=sleeps.append) == "ok"
    assert calls["n"] == 3
    assert sleeps == [0.2, 0.4]


def test_gives_up_after_bounded_retries():
    fn, calls = flaky(5)
    with pytest.raises(ToolUnavailable):
        call_with_retry(fn, sleep=lambda s: None)
    assert calls["n"] == 3


def test_does_not_retry_other_errors():
    def boom():
        raise ValueError("no")

    with pytest.raises(ValueError):
        call_with_retry(boom, sleep=lambda s: None)
