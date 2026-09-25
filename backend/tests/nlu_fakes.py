"""Test doubles for the NLU (no network)."""

from dispute_ops.language.nlu import LlmUsage, NluContext, NluOutcome, NluResult, NluUnavailable

BASE = dict(
    intent="unclear", language="es", transaction_id=None, merchant=None, amount=None,
    reason_code=None, reason_confidence=0.0, card_in_possession=None, recognizes_merchant=None,
    duplicate_transaction_id=None, expected_amount=None, expected_delivery_date=None,
    contacted_merchant=None, cancellation_date=None, wants_block_card=None,
    very_negative_sentiment=False, summary="",
)


def nlu_result(**kw) -> NluResult:
    return NluResult(**{**BASE, **kw})


class ScriptedNlu:
    """Returns queued results in order; an Exception instance in the queue is raised instead."""

    def __init__(self, *results):
        self.queue = list(results)
        self.seen: list[tuple[str, NluContext]] = []

    def interpret(self, text: str, ctx: NluContext) -> NluOutcome:
        self.seen.append((text, ctx))
        item = self.queue.pop(0)
        if isinstance(item, Exception):
            raise item
        usage = LlmUsage(model="fake", prompt_version="test", input_tokens=100, output_tokens=20,
                         latency_ms=5.0, cost_usd=0.0002)
        return NluOutcome(result=item, usage=usage)


def unavailable() -> NluUnavailable:
    return NluUnavailable("test")
