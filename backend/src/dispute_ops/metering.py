"""One way to get an Anthropic client, so evaluation runs spend from the shared ledger (ADR-026).

With `LLM_METER_SOURCE=eval` (and `LLM_LEDGER_URL`), every `messages.create`/`messages.parse` checks the evaluation
cap and the all-sources ceiling first and records its cost afterwards; past a cap it raises `BudgetExceeded`, which
is not an API error, so a run stops instead of silently switching to the free reader. The deployed demo leaves the
variable unset: its spend is counted per turn by the conversation budget."""

from __future__ import annotations

import os
from typing import Any

import anthropic

from dispute_ops.language.nlu import PRICES_PER_MTOK


class BudgetExceeded(RuntimeError):
    pass


class _MeteredMessages:
    def __init__(self, inner: Any, budget: Any) -> None:
        self._inner, self._budget = inner, budget

    def _call(self, fn: Any, kwargs: dict[str, Any]) -> Any:
        model = kwargs.get("model", "")
        if model not in PRICES_PER_MTOK:
            raise BudgetExceeded(f"no price for {model!r}; refusing an unmetered call")
        if self._budget.exhausted():
            raise BudgetExceeded(f"evaluation budget reached: {self._budget.status()}")
        resp = fn(**kwargs)
        price_in, price_out = PRICES_PER_MTOK[model]
        self._budget.add(resp.usage.input_tokens * price_in / 1e6 + resp.usage.output_tokens * price_out / 1e6)
        return resp

    def create(self, **kwargs: Any) -> Any:
        return self._call(self._inner.create, kwargs)

    def parse(self, **kwargs: Any) -> Any:
        return self._call(self._inner.parse, kwargs)


class MeteredClient:
    def __init__(self, client: Any, budget: Any) -> None:
        self._client, self._budget = client, budget
        self.messages = _MeteredMessages(client.messages, budget)

    def with_options(self, **kwargs: Any) -> MeteredClient:
        return MeteredClient(self._client.with_options(**kwargs), self._budget)


_eval_budget: Any = None


def api_client() -> Any:
    source = os.environ.get("LLM_METER_SOURCE", "")
    if not source:
        return anthropic.Anthropic()
    global _eval_budget
    if _eval_budget is None:
        from dispute_ops.container import Settings, make_budget

        settings = Settings.from_env()
        if not settings.llm_ledger_url:
            raise BudgetExceeded("LLM_METER_SOURCE is set but LLM_LEDGER_URL is not")
        _eval_budget = make_budget(settings, source)
    return MeteredClient(anthropic.Anthropic(), _eval_budget)
