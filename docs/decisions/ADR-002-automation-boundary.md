# ADR-002 — Fronteira de automação: intake completo + bloqueio de cartão confirmado
- **Status:** aceito · **Data:** 2026-09-25

## Contexto
É preciso definir o que o sistema resolve sozinho, o que exige confirmação e o que vai para humano. O desafio não autoriza movimentação de dinheiro.

## Decisão
O sistema autentica, identifica a transação, classifica o reason code, coleta evidências, checa elegibilidade por política, abre o caso e verifica que ele existe. Em fraude, oferece bloquear o cartão; o bloqueio só ocorre com confirmação explícita e é verificado por leitura.

| Automático | Com confirmação | Humano |
|---|---|---|
| Consultar transações, checar política, classificar, abrir caso | Abrir a disputa (resumo confirmado), bloquear cartão | Valor acima do limiar, reincidência, velocidade de disputas, sinais de ATO, pedido explícito, sentimento muito negativo, baixa confiança, falha de tool/verificação |

## Alternativas consideradas
- **Só intake:** mais seguro, mas sem ciclo act→verify real.
- **Crédito provisório simulado:** configura movimentação de dinheiro, que está fora do escopo; abre flanco de segurança.

## Consequências
- "Resolução segura" = caso aberto com reason code e evidências corretos, ou recusa correta por política com a regra explicada.
- Nenhuma ação monetária; o canal assíncrono nunca bloqueia cartão (não há confirmação síncrona).
