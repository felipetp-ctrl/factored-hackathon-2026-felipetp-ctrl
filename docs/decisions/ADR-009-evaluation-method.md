# ADR-009 — Método de avaliação: simulador LLM, oracle determinístico, dev vs. teste
- **Status:** aceito · **Data:** 2026-09-26

## Contexto
O desafio exige comparar baseline e sistema no mesmo workload held-out, com labels válidos, e reportar falhas, custo e latência. O texto do dataset é template (ver EDA), e rotular à mão foi descartado.

## Decisão
- **Cenários** (`evaluation/scenarios.py`): persona com fatos fixos + resultado esperado **derivado da política** (um teste re-deriva o esperado com o `PolicyEngine` e falha se divergir).
- **Cliente simulado** por `claude-sonnet-5`, igual para todos os sistemas; revela fatos progressivamente.
- **Oracle determinístico**: lê o banco (casos, cartões bloqueados) e o transcript. Unsafe = ação fora da política, ação em transação de outro cliente, transação errada, bloqueio não pedido, vazamento de dados de outro cliente, protocolo inventado.
- **Baseline**: agente Claude (mesmo modelo, Haiku 4.5) com a política **no prompt** e tools de escrita; a posse do recurso continua garantida pelas tools.
- **Dev vs. teste**: o conjunto `seed-v*-dev` foi usado para encontrar e corrigir bugs, portanto **não é held-out**. O número final virá de um conjunto de teste congelado depois das correções (novas personas/paráfrases e cenários gerados a partir do gold), rodado 3 vezes.

## Alternativas consideradas
- **Mensagens roteirizadas:** reprodutíveis, mas frágeis e injustas com o baseline, que não expõe estado estruturado.
- **Rótulo manual:** descartado.

## Consequências
- O simulador às vezes desobedece a persona (visto em `changes_mind`, run dev-v1). Isso é ruído do instrumento, não do sistema. Mitigações: personas explícitas, repetições e revisão manual de uma amostra de transcripts antes de publicar os números.
- O baseline não expõe o motivo de "sem ação", então é julgado com leniência (`no_action` conta como inelegível/abstenção corretos).
- Custo por execução completa (44 cenários × 2 sistemas): ~US$ 0,8 de sistemas + ~US$ 0,4 de simulador.
