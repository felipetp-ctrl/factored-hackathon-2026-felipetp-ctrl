# ADR-011 — API: papéis, identidade de teste e limites
- **Status:** aceito · **Data:** 2026-09-26

## Decisão
- **Endpoints de cliente:** exigem `Authorization: Bearer <token de sessão>`. O token é emitido por um **provedor de identidade de teste** (`POST /auth/session`), claramente rotulado. Em produção seria o login do banco (OIDC/MFA).
- **Endpoints de agente/operações** (`/agent/*`): exigem `X-Agent-Key`. Um papel não alcança os dados do outro. Um caso de outro cliente responde 404, sem revelar que existe.
- **Rate limit** por sessão (30 mensagens/min, em memória), log estruturado JSON com `X-Request-ID`, relógio simulado ancorado no fim do dataset (2026-06-17).
- **Métricas operacionais** (`/agent/metrics`) derivadas do audit log: respostas por ação, handoffs por motivo, ações verificadas/falhas, custo de LLM, latência p50/p95.

## Limitações (trabalho restante para produção)
- O estado de conversa, o rate limit e o cache de idempotência ficam em memória de um processo. Para escalar horizontalmente: Redis/Postgres.
- A chave de agente é compartilhada; em produção seria SSO com papéis por agente.
- OpenTelemetry/Langfuse ainda não estão integrados. O trace hoje é o audit log por conversa, mais os logs de requisição.
