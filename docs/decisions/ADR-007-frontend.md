# ADR-007 — Frontend: Next.js com linguagem visual inspirada na Factored
- **Status:** aceito · **Data:** 2026-09-25

## Contexto
Juízes vão usar a ferramenta. São necessárias três telas: chat do cliente, console do agente e operações.

## Decisão
Next.js + Tailwind com os tokens visuais de factored.ai: Roboto / Roboto Mono, `#0047e5`, `#f2a100` nos botões primários, `#00f2f2` nos detalhes, preto e branco. **Sem logo nem nome da Factored**: a marca exibida é a do banco fictício "LATAM Bank".

## Alternativas consideradas
- **Streamlit:** cerca de 1 dia mais rápido, mas apresentação inferior.

## Consequências
- Cerca de 1 dia de esforço extra, compensado por D3 ser o primeiro corte.
- Não há risco de confusão de marca.
