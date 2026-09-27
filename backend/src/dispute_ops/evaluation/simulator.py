"""LLM customer simulator: plays a persona with fixed facts. Same simulator for every system."""

from __future__ import annotations

from typing import Any, Protocol

import anthropic

from dispute_ops.evaluation.scenarios import Scenario
from dispute_ops.language.nlu import PRICES_PER_MTOK

SIMULATOR_MODEL = "claude-sonnet-5"
END = "[END]"
LANG_NAME = {"es": "Spanish (Latin American, informal chat style)", "pt": "Brazilian Portuguese (informal chat style)"}

SIM_SYSTEM = """You role-play a bank customer chatting with LATAM Bank's dispute assistant, to test it.
Write only the customer's next chat message: short (1-2 sentences), natural, {language}.
Your facts (never invent other facts; if asked something not covered, say you don't know):
{persona}
Rules:
- Reveal details progressively, when asked or when natural, like a real customer.
- Answer the assistant's questions truthfully according to your facts. Answer yes/no questions clearly.
- When the assistant says the case was registered, transferred to a person, cannot be done, or asks if you need
  anything else and your goal is finished, reply exactly {end}.
- Never mention that you are a simulation."""


class Simulator(Protocol):
    def next_message(self, scenario: Scenario, transcript: list[tuple[str, str]]) -> str: ...


class ClaudeSimulator:
    def __init__(self, client: Any | None = None, model: str = SIMULATOR_MODEL) -> None:
        self.client = (client or anthropic.Anthropic()).with_options(timeout=120.0, max_retries=2)
        self.model = model
        self.cost_usd = 0.0

    def next_message(self, scenario: Scenario, transcript: list[tuple[str, str]]) -> str:
        # The bank speaks as "user", the simulated customer as "assistant".
        messages: list[dict[str, str]] = []
        for role, text in transcript:
            if role == "system":  # harness events (e.g. re-login) are not part of the chat
                continue
            messages.append({"role": "user" if role == "bank" else "assistant", "content": text})
        if not messages or messages[-1]["role"] != "user":
            messages.append({"role": "user", "content": "(continue)"})
        resp = self.client.messages.create(
            model=self.model, max_tokens=4000,
            system=SIM_SYSTEM.format(language=LANG_NAME[scenario.language], persona=scenario.persona, end=END),
            messages=messages,
        )
        price_in, price_out = PRICES_PER_MTOK[self.model]
        self.cost_usd += resp.usage.input_tokens * price_in / 1e6 + resp.usage.output_tokens * price_out / 1e6
        return "".join(b.text for b in resp.content if b.type == "text").strip()
