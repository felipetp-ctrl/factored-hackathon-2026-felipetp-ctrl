# ADR-003 — Sistema multicanal: chat + caixa PQR + alerta proativo
- **Status:** aceito · **Data:** 2026-09-25

## Contexto
Os organizadores pedem "não um chatbot, e sim um sistema de atendimento". O dataset já contém 80 mil reclamações escritas (`complaints`) com resultado humano histórico.

## Decisão
Um núcleo único com três entradas:
- **Chat** ES/PT (requisitos conversacionais);
- **Caixa PQR** (D1): triagem em lote de reclamações escritas; nunca clarifica de forma síncrona e, se faltar informação, faz handoff `async_missing_info`;
- **Proativo** (D3): transações recentes com `fraud_score` alto geram "foi você?". É o primeiro item a cortar se faltar tempo.

## Alternativas consideradas
- **Só chat:** mais barato, mas se aproxima de um chatbot e não usa o texto real do dataset.
- **Transcript pós-ligação como canal:** redundante com o PQR.
- **Voz:** sem áudio no dataset, alto risco.

## Consequências
- O canal PQR dá o baseline humano mais forte: mesmas complaints, comparação direta (spec §6.3).
- Os canais diferem só no estado de entrada da máquina de estados; o custo marginal é pequeno.
