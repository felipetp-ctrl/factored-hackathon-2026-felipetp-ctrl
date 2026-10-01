"""Wiring: builds every component from settings. The API and the evaluation harness share it."""

from __future__ import annotations

import os
import secrets
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

from pydantic import BaseModel

from dispute_ops.auth import SessionService
from dispute_ops.conversation import Budget, ConversationService, Nlu
from dispute_ops.language.breaker import CircuitBreaker
from dispute_ops.policy.engine import PolicyEngine
from dispute_ops.store import Store
from dispute_ops.tools import BankingTools, FailureInjector

DEFAULT_SEED = Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "seed.json"


class Settings(BaseModel):
    seed_path: str = str(DEFAULT_SEED)
    db_path: str = ":memory:"
    # Pipeline-exported SQLite (gold sample). When set, a private copy is used and no seed is loaded.
    demo_db: str = ""
    session_secret: str = ""
    session_ttl_minutes: int = 15
    agent_api_key: str = ""
    # The dataset ends on 2026-06-17; the demo runs on a simulated clock anchored there so that
    # dispute windows and fraud-alert look-backs are meaningful.
    demo_now: str = "2026-06-17T12:00:00+00:00"
    rate_limit_per_minute: int = 30
    # Production would alert within 48 h; the demo looks back 30 days because high-risk charges are rare
    # in the dataset (high-score card charges are a few dozen a month; threshold in domain.FRAUD_ALERT_MIN_SCORE).
    fraud_alert_lookback_hours: int = 48
    # Public demo: every browser gets its own copy of the data (workspace) and the bank-side views open without
    # a key, because judges have no staff login. Off by default; production keeps the agent key.
    demo_mode: bool = False
    scenarios_path: str = ""
    # auto = Claude with the free rule-based NLU as fallback (rules only when no API key); claude; rules.
    nlu_mode: str = "auto"
    llm_budget_usd: float | None = 20.0
    # Optional caps on top of the total (ADR-026): per calendar day, and per demo workspace (browser tab).
    llm_daily_budget_usd: float | None = None
    llm_workspace_budget_usd: float | None = None
    # Ceiling for every source together (the project's API credit) and the durable ledger that enforces it.
    llm_global_budget_usd: float | None = None
    llm_ledger_url: str = ""
    # Learned intent/reason classifier inside the rule-based NLU (ADR-019): a model JSON path, "" for the
    # bundled intent-v2, or "off" for keyword rules only.
    intent_model: str = ""

    @classmethod
    def from_env(cls) -> Settings:
        env = os.environ
        return cls(
            seed_path=env.get("SEED_PATH", str(DEFAULT_SEED)),
            db_path=env.get("DB_PATH", ":memory:"),
            demo_db=env.get("DEMO_DB", ""),
            session_secret=env.get("SESSION_SECRET") or secrets.token_hex(32),
            session_ttl_minutes=int(env.get("SESSION_TTL_MINUTES", "15")),
            agent_api_key=env.get("AGENT_API_KEY") or secrets.token_hex(16),
            demo_now=env.get("DEMO_NOW", "2026-06-17T12:00:00+00:00"),
            rate_limit_per_minute=int(env.get("RATE_LIMIT_PER_MINUTE", "30")),
            fraud_alert_lookback_hours=int(env.get("FRAUD_ALERT_LOOKBACK_HOURS", "48")),
            demo_mode=env.get("DEMO_MODE", "false").lower() in ("1", "true", "yes"),
            scenarios_path=env.get("SCENARIOS_PATH", ""),
            nlu_mode=env.get("NLU_MODE", "auto"),
            llm_budget_usd=float(env["LLM_BUDGET_USD"]) if env.get("LLM_BUDGET_USD") else 20.0,
            llm_daily_budget_usd=float(env["LLM_DAILY_BUDGET_USD"]) if env.get("LLM_DAILY_BUDGET_USD") else None,
            llm_workspace_budget_usd=(
                float(env["LLM_WORKSPACE_BUDGET_USD"]) if env.get("LLM_WORKSPACE_BUDGET_USD") else None),
            llm_global_budget_usd=float(env["LLM_GLOBAL_BUDGET_USD"]) if env.get("LLM_GLOBAL_BUDGET_USD") else None,
            llm_ledger_url=env.get("LLM_LEDGER_URL", ""),
            intent_model=env.get("INTENT_MODEL", ""),
        )

    def resolved_scenarios_path(self) -> Path:
        if self.scenarios_path:
            return Path(self.scenarios_path)
        return Path(self.demo_db or self.seed_path).parent / "scenarios.json"


def make_budget(settings: Settings, source: str) -> Budget:
    """The process-wide budget: durable and shared when a ledger URL is set, fail-closed if it cannot connect."""
    ledger = None
    if settings.llm_ledger_url:
        from dispute_ops.spend_ledger import SpendLedger

        ledger = SpendLedger(settings.llm_ledger_url, source)  # unreachable now: closed until a read succeeds
    return Budget(settings.llm_budget_usd, daily_limit_usd=settings.llm_daily_budget_usd,
                  global_limit_usd=settings.llm_global_budget_usd, ledger=ledger)


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
    # flows run outside a conversation (written complaints), kept so the bank's case board can show them
    async_flows: list = field(default_factory=list)

    @classmethod
    def build(
        cls, settings: Settings, *, nlu: Nlu | None = None, sleep: Callable[[float], None] = time.sleep,
        budget: Budget | None = None, fallback: Nlu | None = None,
    ) -> Container:
        clock = SimClock(datetime.fromisoformat(settings.demo_now))
        if settings.demo_db:
            import shutil
            import tempfile

            working_copy = Path(tempfile.mkdtemp()) / "dispute_ops.db"
            shutil.copy(settings.demo_db, working_copy)
            store = Store(working_copy)
        else:
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
            nlu, fallback = _select_nlu(settings, store)
        conversations = ConversationService(
            tools=tools, store=store, policy=policy, nlu=nlu,
            breaker=CircuitBreaker(failure_threshold=3, reset_seconds=60, clock=clock), clock=clock, sleep=sleep,
            fallback=fallback, budget=budget or Budget(settings.llm_budget_usd),
        )
        return cls(settings, clock, store, sessions, policy, failures, tools, conversations)


def _select_nlu(settings: Settings, store: Store) -> tuple[Nlu, Nlu | None]:
    from dispute_ops.language.intent_model import DEFAULT_PATH, IntentModel
    from dispute_ops.language.rule_nlu import RuleNlu

    model = None if settings.intent_model == "off" else IntentModel.load(Path(settings.intent_model or DEFAULT_PATH))
    rules = RuleNlu(store.distinct_merchants(), intent_model=model)
    mode = settings.nlu_mode
    if mode == "auto" and not os.environ.get("ANTHROPIC_API_KEY"):
        mode = "rules"
    if mode == "rules":
        return rules, None
    from dispute_ops.language.nlu import ClaudeNlu

    return ClaudeNlu(), (rules if mode == "auto" else None)
