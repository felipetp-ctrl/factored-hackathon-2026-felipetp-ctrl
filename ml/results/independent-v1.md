# Independent message set `independent-v1`

> Written by a different author (Claude Sonnet as a Claude Code subagent that never saw the training corpus or the code), labelled by that author, and re-labelled blind by a second annotator (Claude Haiku subagent, no labels shown). Opening messages only; each is read as a first customer turn. Offline, no API calls.

## Label quality

- 540 messages; Cohen's κ between writer and blind annotator = **1.000** (raw agreement 100.0%). Both are Sonnet instances and the writer was told to rewrite ambiguous messages, so this shows the set is unambiguous under the definitions, not that the labels are human-validated.
- A first blind annotation by Claude Haiku was discarded: κ = 0.475, it labelled most messages with an explicit reason as 'no reason' — it had generated a keyword script instead of reading the messages (file kept: `independent-v1.annotator-haiku-discarded.tsv`). The Sonnet annotator wrote its labels directly.
- 15 messages that are near-duplicates of the training corpus (char 3-gram Jaccard ≥ 0.6) are excluded; gold set = 525 messages.
- Gold labels: `{'FRAUD_CNP': 56, 'FRAUD_CP': 59, 'DUPLICATE': 58, 'INCORRECT_AMOUNT': 60, 'NOT_RECEIVED': 59, 'CANCELLED_RECURRING': 60, 'OUT_OF_SCOPE': 58, 'HUMAN': 57, 'DISPUTE_NO_REASON': 58}`

## Systems on the same gold messages

| System | Accuracy (95% CI) | Macro-F1 | es | pt |
|---|---|---|---|---|
| keyword baseline | 234/525 = 44.6% (40%–49%) | 0.488 | 115/261 | 119/264 |
| fallback NLU, rules only | 240/525 = 45.7% (41%–50%) | 0.500 | 119/261 | 121/264 |
| fallback NLU, rules + intent-v2 | 494/525 = 94.1% (92%–96%) | 0.942 | 243/261 | 251/264 |
| intent-v2 alone | 502/525 = 95.6% (94%–97%) | 0.956 | 250/261 | 252/264 |

Paired exact McNemar test, fallback with intent-v2 vs rules only: only intent-v2 right 260, only rules right 6, p = 8e-69.

intent-v2 at its 0.60 threshold accepts 492 of 525 messages, 480 correctly.

### Recall by label

| Label | keyword baseline | fallback NLU, rules only | fallback NLU, rules + intent-v2 | intent-v2 alone |
|---|---|---|---|---|
| FRAUD_CNP | 26/56 | 31/56 | 54/56 | 56/56 |
| FRAUD_CP | 40/59 | 40/59 | 56/59 | 57/59 |
| DUPLICATE | 29/58 | 29/58 | 56/58 | 57/58 |
| INCORRECT_AMOUNT | 10/60 | 10/60 | 52/60 | 56/60 |
| NOT_RECEIVED | 8/59 | 8/59 | 59/59 | 59/59 |
| CANCELLED_RECURRING | 14/60 | 14/60 | 59/60 | 60/60 |
| OUT_OF_SCOPE | 13/58 | 14/58 | 51/58 | 56/58 |
| HUMAN | 36/57 | 36/57 | 53/57 | 54/57 |
| DISPUTE_NO_REASON | 58/58 | 58/58 | 54/58 | 47/58 |

## Cross-author generalisation (same TF-IDF + LR configuration)

- Trained on our corpus, tested on the independent gold set: 95.6%
- Trained on the independent set, tested on our corpus: 85.5%

## Errors of the fallback NLU with intent-v2

| Message | Expected | Predicted |
|---|---|---|
| Sigo con la tarjeta en mi poder pero me cobraron algo raro anoche. | FRAUD_CNP | DISPUTE_NO_REASON |
| me clonaron la banda magnetica, aparecio un cargo en otro pais | FRAUD_CNP | DISPUTE_NO_REASON |
| Se llevaron mi cartera en un robo y ahora hay una compra que no reconozco. | FRAUD_CP | FRAUD_CNP |
| Perdi meu cartão de crédito na academia e apareceu um pagamento numa loja de roupa. | FRAUD_CP | OUT_OF_SCOPE |
| Levaram minha carteira num roubo e agora tem uma compra que eu não reconheço. | FRAUD_CP | FRAUD_CNP |
| me aparecen 2 cargos iguales de la pizzeria del sabado | DUPLICATE | DISPUTE_NO_REASON |
| O restaurante cobrou a conta e depois de novo o mesmo valor exato. | DUPLICATE | INCORRECT_AMOUNT |
| Reconozco la compra pero el monto está mal. | INCORRECT_AMOUNT | FRAUD_CNP |
| Reconozco el cargo del hotel pero el monto no coincide con lo reservado. | INCORRECT_AMOUNT | DISPUTE_NO_REASON |
| Sí hice la compra en "SuperMercadoUno" pero el total no cuadra con lo que pagué. | INCORRECT_AMOUNT | DISPUTE_NO_REASON |
| Buenas tardes, reservé el hotel por $3,450.90 pero en mi estado de cuenta aparece $4,100.00. | INCORRECT_AMOUNT | DISPUTE_NO_REASON |
| La suscripción anual decía $99 y me cobraron $149. | INCORRECT_AMOUNT | CANCELLED_RECURRING |
| Fui yo quien reservó el cuarto de hotel pero el cargo final no coincide con la tarifa acordada. | INCORRECT_AMOUNT | DISPUTE_NO_REASON |
| Boa tarde, reservei o hotel por R$ 345,90 mas na minha fatura aparece R$ 410,00. | INCORRECT_AMOUNT | DISPUTE_NO_REASON |
| A assinatura anual dizia R$ 99 e me cobraram R$ 149. | INCORRECT_AMOUNT | CANCELLED_RECURRING |
| Solicité la baja del club de descuentos hace semanas, sigo pagando. | CANCELLED_RECURRING | DISPUTE_NO_REASON |
| ¿Dónde puedo ver mi estado de cuenta de este mes? | OUT_OF_SCOPE | DISPUTE_NO_REASON |
| Necesito bloquear temporalmente mi tarjeta porque no la encuentro en casa. | OUT_OF_SCOPE | DISPUTE_NO_REASON |
| Disculpe, soy mayor y no sé cómo usar la app, ¿me pueden ayudar? | OUT_OF_SCOPE | DISPUTE_NO_REASON |
| quiero cancelar mi cuenta de banco, ya no la uso | OUT_OF_SCOPE | CANCELLED_RECURRING |
| Preciso bloquear temporariamente meu cartão porque não acho ele em casa. | OUT_OF_SCOPE | DISPUTE_NO_REASON |
| Desculpa, já sou de idade e não sei usar o aplicativo, podem me ajudar? | OUT_OF_SCOPE | DISPUTE_NO_REASON |
| quero cancelar minha conta do banco, nao uso mais | OUT_OF_SCOPE | DISPUTE_NO_REASON |
| No quiero seguir con el chatbot, deseo hablar con una persona. | HUMAN | DISPUTE_NO_REASON |
| Solicito hablar con un ejecutivo de cuenta cuanto antes. | HUMAN | OUT_OF_SCOPE |
| Não quero continuar com o chatbot, quero falar com uma pessoa. | HUMAN | DISPUTE_NO_REASON |
| Solicito falar com um gerente de conta o quanto antes. | HUMAN | DISPUTE_NO_REASON |
| Tengo dudas sobre una compra que aparece hoy en mi resumen. | DISPUTE_NO_REASON | FRAUD_CNP |
| É a cobrança de R$ 56 que saiu na quinta passada. | DISPUTE_NO_REASON | INCORRECT_AMOUNT |
| Preciso que me ajudem com uma cobrança estranha na minha conta. | DISPUTE_NO_REASON | FRAUD_CNP |
| quero reportar uma cobranca estranha dessa semana | DISPUTE_NO_REASON | FRAUD_CNP |

## Writer vs blind annotator disagreements

| Message | Writer | Annotator 2 |
|---|---|---|

## Limitations

- Both annotators are language models; a human review sample is still the reference for label quality.
- Opening messages only; the conversation-level effect is measured in test-v3.
