"""ASGI entry point: `uvicorn dispute_ops.main:app`."""

import logging
import os

from dotenv import find_dotenv, load_dotenv

from dispute_ops.api import create_app
from dispute_ops.container import Container, Settings, make_budget

load_dotenv(find_dotenv(usecwd=True))
logging.basicConfig(level=logging.INFO, format="%(message)s")

_had_agent_key = bool(os.environ.get("AGENT_API_KEY"))
settings = Settings.from_env()
if not _had_agent_key:
    logging.getLogger("dispute_ops").warning("AGENT_API_KEY not set; generated for this run: %s", settings.agent_api_key)
# Total, daily and all-sources caps for the process (durable with LLM_LEDGER_URL); each demo workspace (browser tab)
# gets its own share (ADR-026).
budget = make_budget(settings, "demo")


def build() -> Container:
    return Container.build(settings, budget=budget.child(settings.llm_workspace_budget_usd))


app = create_app(build(), workspace_factory=build if settings.demo_mode else None)
