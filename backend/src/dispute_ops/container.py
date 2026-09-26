"""Wiring: builds every component from settings. The API and the evaluation harness share it."""

from __future__ import annotations

import os
import secrets
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from pydantic import BaseModel

from dispute_ops.auth import SessionService
from dispute_ops.conversation import ConversationService, Nlu
from dispute_ops.language.breaker import CircuitBreaker
from dispute_ops.policy.engine import PolicyEngine
from dispute_ops.store import Store
from dispute_ops.tools import BankingTools, FailureInjector

DEFAULT_SEED = Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "seed.json"


class Settings(BaseModel):
    seed_path: str = str(DEFAULT_SEED)
    db_path: str = ":memory:"
    session_secret: str = ""
    session_ttl_minutes: int = 15
    agent_api_key: str = ""
    # The dataset ends on 2026-06-17; the demo runs on a simulated clock anchored there so that
    # dispute windows and fraud-alert look-backs are meaningful.
    demo_now: str = "2026-06-17T12:00:00+00:00"
    rate_limit_per_minute: int = 30

    @classmethod
    def from_env(cls) -> Settings:
        env = os.environ
        return cls(
            seed_path=env.get("SEED_PATH", str(DEFAULT_SEED)),
            db_path=env.get("DB_PATH", ":memory:"),
            session_secret=env.get("SESSION_SECRET") or secrets.token_hex(32),
            session_ttl_minutes=int(env.get("SESSION_TTL_MINUTES", "15")),
            agent_api_key=env.get("AGENT_API_KEY") or secrets.token_hex(16),
            demo_now=env.get("DEMO_NOW", "2026-06-17T12:00:00+00:00"),
            rate_limit_per_minute=int(env.get("RATE_LIMIT_PER_MINUTE", "30")),
        )


class SimClock:
    """Simulated wall clock: starts at `start` and advances with real elapsed time."""

    def __init__(self, start: datetime) -> None:
        self.start = start
        self._t0 = time.monotonic()
        self._offset = timedelta()

    def __call__(self) -> datetime:
        return self.start + timedelta(seconds=time.monotonic() - self._t0) + self._offset

    def advance(self, **kw: float) -> None:
        self._offset += timedelta(**kw)


@dataclass
class Container:
    settings: Settings
    clock: SimClock
    store: Store
    sessions: SessionService
    policy: PolicyEngine
    failures: FailureInjector
    tools: BankingTools
    conversations: ConversationService

    @classmethod
    def build(cls, settings: Settings, *, nlu: Nlu | None = None, sleep: Callable[[float], None] = time.sleep) -> Container:
        clock = SimClock(datetime.fromisoformat(settings.demo_now))
        store = Store(settings.db_path)
        if settings.seed_path:
            store.load_seed(settings.seed_path)
        sessions = SessionService(
            settings.session_secret.encode(), timedelta(minutes=settings.session_ttl_minutes), clock
        )
        policy = PolicyEngine.load_default()
        failures = FailureInjector()
        tools = BankingTools(store, sessions, clock, policy_version=policy.version, failures=failures)
        if nlu is None:
            from dispute_ops.language.nlu import ClaudeNlu

            nlu = ClaudeNlu()
        conversations = ConversationService(
            tools=tools, store=store, policy=policy, nlu=nlu,
            breaker=CircuitBreaker(failure_threshold=3, reset_seconds=60, clock=clock), clock=clock, sleep=sleep,
        )
        return cls(settings, clock, store, sessions, policy, failures, tools, conversations)
