# Offline cascade estimate (test-v2, complete runs + run 3)

> Replay of the stored conversations with the model's recorded readings; the free NLU (rules + intent-v2) reads each turn on the side. Agreement with the model is a proxy for correctness, not ground truth.

- Conversations replayed: 118; replayed faithfully (same turns, every recorded reading consumed, same outcome): 107. Only faithful replays are counted.
- Customer turns read by the model: 250.
- Free NLU agrees with the model on the intent and the fields the flow uses in that state, over all turns: 200/250 (80.0%).

## Cascade rule

Free NLU for structured answers (confirm, decline, provide-info) outside the free-text states, and for free-text turns where intent-v2 is confident (≥ 0.60); the model for the rest.

| | Value |
|---|---|
| Turns routed to the free NLU (model calls saved) | 229/250 (91.6%) |
| Agreement with the model on routed turns | 193/229 (84.3%) |
| Model cost per turn in these runs | US$ 0.0032 |
| Estimated saving per 1,000 turns | US$ 2.91 |

Disagreeing fields on routed turns: `reason_code` 24, `merchant` 14, `amount` 13, `expected_delivery_date` 4, `expected_amount` 3, `card_in_possession` 3, `wants_block_card` 1

| State | Routed to free NLU | Turns |
|---|---|---|
| CLASSIFY | yes | 12 |
| COLLECT_EVIDENCE | no | 4 |
| COLLECT_EVIDENCE | yes | 33 |
| CONFIRM | yes | 56 |
| IDENTIFY_TXN | no | 10 |
| IDENTIFY_TXN | yes | 28 |
| START | no | 7 |
| START | yes | 100 |

## Disagreements on routed turns (first 15)

| State | Customer message | Fields |
|---|---|---|
| START | oi, tem uma cobranca estranha aqui no meu cartao, ta esquisito isso | reason_code |
| IDENTIFY_TXN | foi na "mercado central", valor 91.558,20 ARS, dia 02/05/2026 la pelas 18:48 | reason_code |
| IDENTIFY_TXN | es de "mercado central", 251,776.37 cop, fue el 08 de mayo 2026 como a las 00:03 | reason_code |
| COLLECT_EVIDENCE | Debía llegar 3 días después de la compra, o sea alrededor del 5 de mayo. Y sí, ya contacté al comercio pero no | expected_delivery_date |
| IDENTIFY_TXN | Sí, es la primera, la de 91,558.20 ARS del 2 de mayo. | reason_code, amount, merchant |
| IDENTIFY_TXN | É a de 202.57 USD, do dia 27 de março às 13:37. | reason_code, amount, merchant |
| IDENTIFY_TXN | Sí, es la primera, la de 204.24 USD del 2 de abril a las 03:45. | reason_code, amount, merchant |
| IDENTIFY_TXN | É a primeira, a de 361.45 USD do dia 09 de maio. | reason_code, amount, merchant |
| IDENTIFY_TXN | É a primeira, do dia 24/03/2026 às 12:53, no valor de 37.120,43 ARS. | reason_code, amount, merchant |
| START | hola, tengo un cargo raro en mi tarjeta no se q es | reason_code |
| START | oi td bem, tem uma cobranca estranha aq no meu cartao | reason_code |
| IDENTIFY_TXN | foi na mercado central, valor de 91.558,20 ARS, dia 02/05/2026 mais ou menos 18:48 | reason_code |
| START | holaa tengo un cargo raro en mi cuenta, no se que es | reason_code |
| COLLECT_EVIDENCE | Era pra chegar 3 dias depois da compra, então uns dias depois de 12/05. E sim, já entrei em contato com a loja | expected_delivery_date |
| COLLECT_EVIDENCE | La compra fue el 02 de mayo de 2026 alrededor de las 18:48, así que debía llegar el 05 de mayo más o menos. | expected_delivery_date |

## Limitations

- test-v2 messages were read during the intent-v1 error analysis (post-hoc for intent-v2).
- A disagreement is not necessarily an error of the free NLU, and agreement does not prove the model was right; the policy and the confirmation step still guard every action.
- The saving assumes the same turn mix as this evaluation set.
