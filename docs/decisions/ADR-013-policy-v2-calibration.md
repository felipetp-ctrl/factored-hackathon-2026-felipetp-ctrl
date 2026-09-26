# ADR-013 — Política `disputes_v2`: limite único de US$ 450, calibrado nos dados
- **Status:** aceito · **Data:** 2026-09-26 · `disputes_v1` mantida para reprodutibilidade

## Contexto
A `disputes_v1` tinha limites de valor por país escolhidos a priori (MX 500, CO 400, AR 300 USD). Rodando o pipeline completo apareceram dois fatos:
1. **As transações dos clientes mexicanos vêm em moeda USD, com `amount_usd` nulo** (541.812 compras de cartão), e ~5% das transações em ARS/COP também não têm `amount_usd`. Sem correção, nenhuma disputa mexicana acionaria o limite de valor.
2. Depois da correção (gold: valor informado → identidade em USD → câmbio diário, com `amount_usd_source`), o valor em USD das compras de cartão é **~U(0, 500) nos três países** (p50 ≈ 252, p90 ≈ 450, p95 ≈ 475).

## Decisão
- Um limite único de **US$ 450** (p90): cerca de 10% das disputas de compra vão para humano por valor, igualmente em todos os países.
- `max_disputes_30d = 3` foi mantido. Nos dados, o máximo observado é de 2 reclamações de transação por cliente em 30 dias, então a regra é uma salvaguarda que não dispara no histórico.

## Alternativas consideradas
- **Manter os limites por país da v1:** escalaria 0% (MX), 20% (CO) e 40% (AR) das disputas sem diferença de risco nos dados. É uma disparidade injustificável entre segmentos, justamente o que o desafio pede para investigar.
- **Limite no p95 (US$ 475):** automatiza mais, mas deixa uma margem menor para as compras de maior valor.

## Consequências
- A calibração é descritiva (distribuição de valores), não baseada em perda esperada: os dados não trazem um sinal de fraude correlacionado com valor (`is_fraud` ≈ 0,1% em qualquer faixa).
- Os cenários de avaliação são rotulados com a política vigente; o gerador registra a versão usada nos metadados.
