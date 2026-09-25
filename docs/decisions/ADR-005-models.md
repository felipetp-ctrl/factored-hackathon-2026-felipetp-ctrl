# ADR-005 — Modelos: Claude + ML local
- **Status:** aceito · **Data:** 2026-09-25

## Contexto
Não há créditos de API. O desafio exige pelo menos um componente aprendido contra baseline, privacidade em chamadas externas e medição de custo e latência.

## Decisão
- Claude Haiku 4.5 para conversa e extração; Sonnet 5 para fallback, simulador de cliente e juiz.
- ML local: classificador de reason code (`multilingual-e5-small` + regressão logística), redação de PII (Presidio + spaCy), filtro de injection e embeddings.
- Cascata: modelo local com confiança ≥ θ → Haiku → clarificação.

## Alternativas consideradas
- **Outros provedores:** sem vantagem clara em ES/PT.
- **Apenas modelos locais:** qualidade conversacional inferior em ES/PT.

## Consequências
- O componente local dá a comparação de acurácia × latência × custo pedida pelo desafio.
- PII é redigida antes de qualquer chamada externa, embora o dataset seja sintético.
- A chave da API fica em variável de ambiente, com limite de gasto.
