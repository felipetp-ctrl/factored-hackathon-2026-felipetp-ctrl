# ADR-011 — API: roles, test identity and limits
- **Status:** accepted · **Date:** 2026-09-26

## Decision
- **Customer endpoints** require `Authorization: Bearer <session token>`. The token is issued by a clearly labelled **test identity provider** (`POST /auth/session`); in production this would be the bank's login (OIDC/MFA).
- **Agent/operations endpoints** (`/agent/*`) require `X-Agent-Key`. Neither role reaches the other's data. Another customer's case returns 404 without revealing that it exists.
- **Rate limit** per session (30 messages/min, in memory), structured JSON logs with `X-Request-ID`, a simulated clock anchored at the end of the dataset (2026-06-17).
- **Operational metrics** (`/agent/metrics`) derived from the audit log: replies by outcome, handoffs by reason, verified/failed actions, model cost, latency p50/p95.

## Limitations (remaining work for production)
- Conversation state, rate limit and idempotency cache live in one process's memory. Horizontal scaling needs Redis/Postgres.
- The agent key is shared; production needs SSO with per-agent roles.
- OpenTelemetry/Langfuse are not wired yet; today's trace is the per-conversation audit log plus request logs.
