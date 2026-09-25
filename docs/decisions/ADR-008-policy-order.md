# ADR-008 — Ordem de avaliação da política e limiares
- **Status:** aceito · **Data:** 2026-09-25

## Contexto
`PolicyEngine.evaluate` precisa de uma ordem determinística quando várias regras se aplicam ao mesmo caso.

## Decisão
Ordem de avaliação:
1. Pedido de humano (`R-HUMAN-REQUEST`).
2. Disputa já aberta (`R-DUP-OPEN`).
3. Status inelegível (`R-TXN-STATUS`).
4. Fora da janela (`R-WINDOW`).
5. Gatilhos de handoff, todos reportados juntos: `R-HO-AMOUNT`, `R-HO-REPEAT`, `R-HO-VELOCITY`, `R-HO-ATO`, `R-HO-SENTIMENT`, `R-HO-LOWCONF`.
6. Elegível (`R-ELIGIBLE`), com `missing_evidence`.

- O pedido de humano vem primeiro, por respeitar a autonomia do cliente.
- A inelegibilidade vem antes do handoff: explicar a regra ao cliente é uma resolução segura e não precisa de humano.
- Todos os gatilhos de handoff são listados, e não só o primeiro, para dar mais contexto ao agente.

## Limiares (placeholders, `synthetic: true`)
- `amount_usd_threshold`: MX 500, CO 400, AR 300 (padrão 300)
- `max_disputes_30d`: 3
- `min_classifier_confidence`: 0.6
- Janela de disputa: 120 dias (60 para `INCORRECT_AMOUNT` e `CANCELLED_RECURRING`)

Todos serão calibrados no Plano 2 com a distribuição de `claimed_amount` e dos prazos em `complaints`. Qualquer mudança gera `disputes_v2`, e a versão anterior é mantida.

## Consequências
- Cada decisão sai com `rule_ids`, `policy_version` e `inputs`, que servem de explicação auditável.
- Os limiares atuais não têm base empírica até a EDA. Isso é uma limitação declarada.
