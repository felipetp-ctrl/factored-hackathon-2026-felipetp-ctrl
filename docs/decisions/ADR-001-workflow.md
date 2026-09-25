# ADR-001 — Workflow: intake de disputa de transação
- **Status:** aceito · **Data:** 2026-09-25

## Contexto
O desafio pede um único workflow bancário coerente; mais workflows não dão bônus. As opções sugeridas: consultas de conta/pagamento, suporte a cartão, disputa de transação, elegibilidade de crédito. O time é uma pessoa em tempo parcial por 10 dias.

## Decisão
Intake de disputa de transação.

## Alternativas consideradas
- **Suporte a cartão:** ações verificáveis simples, mas componente de ML mais pobre.
- **Conta/pagamentos:** o mais simples e o mais "típico"; os organizadores pediram criatividade.
- **Crédito:** rico em ML, mas exige serviço de política sintético elaborado e separação conversa/risco/elegibilidade; arriscado solo.

## Consequências
- Dados ricos: `transactions` (status, `is_fraud`, `fraud_score`) + `complaints` (texto, categoria, resolução, SLA) + interações.
- Os três caminhos obrigatórios aparecem naturalmente (normal, ambíguo, humano).
- Domínio sensível: exige política determinística, confirmação e verificação (ver ADR-002 e ADR-004).
- A escolha será revalidada pela EDA; se os dados a contradisserem, reabrimos antes do dia 3.
