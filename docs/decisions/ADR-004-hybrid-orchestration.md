# ADR-004 — Orquestração híbrida
- **Status:** aceito · **Data:** 2026-09-25

## Contexto
Permissões e políticas devem ser aplicadas fora do texto gerado pelo modelo, e o sistema só pode reportar ações verificadas.

## Decisão
`DisputeFlow`, uma máquina de estados determinística, é a dona do ciclo de vida do caso e a única que chama tools de escrita (`open_dispute`, `block_card`): só depois de uma decisão do `PolicyEngine`, de confirmação explícita e de leitura de verificação. O LLM (Plano 4) atua só nos estados conversacionais, com tools **somente leitura**, e produz `Turn` estruturados: o flow nunca vê texto livre.

## Alternativas consideradas
- **Máquina de estados pura, com LLM só para NLU/NLG:** a mais previsível, mas a conversa fica rígida.
- **Agente livre com guardrails nas tools:** flexível, mas com maior variância entre execuções e risco de declarar ações não realizadas.

## Consequências
- A fronteira de segurança é testável sem LLM (Plano 1: 69 testes, incluindo acesso cruzado, sessão expirada, falha de tool e verificação).
- Tools recebem o token de sessão; o dono do recurso vem do token, nunca de um id fornecido pelo modelo.
- Explicabilidade vem das regras (`rule_ids`, `policy_version`, `inputs`) e do audit log append-only, não de chain-of-thought.
- Custo: mais código que um agente livre.
