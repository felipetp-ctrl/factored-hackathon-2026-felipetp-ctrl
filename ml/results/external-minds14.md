# Real customer speech: MInDS-14 (es-ES, pt-PT)

> Every other text set in this project was written by a language model. MInDS-14 (PolyAI, CC BY 4.0) is people calling an e-banking line, transcribed by ASR: rambling, mis-heard words, no punctuation. The question is the first one the free reader answers: **start the dispute intake or not?** Offline, no API calls.

- 1090 messages (872 from 11 intents that are never a charge dispute, labelled by the dataset; 196 from 3 mixed intents read one by one under a written criterion: `{'NOT_DISPUTE': 152, 'DISPUTE': 44}`; 22 unsure excluded).
- Misrouted = a message that is not a dispute is answered with "which charge do you want to dispute?". Nothing is written without a confirmation, so this is wasted turns and a confused customer, not an unsafe action.

## Before and after

| Reader | Not a dispute, sent to intake (11 clean intents) | es | pt | Mixed intents: not a dispute → intake | Mixed intents: real disputes → intake |
|---|---|---|---|---|---|
| keyword rules | 587/872 = 67.3% | 244/385 | 343/487 | 142/152 = 93.4% | 42/44 = 95.5% |
| rules + intent-v2 (before) | 271/872 = 31.1% | 100/385 | 171/487 | 79/152 = 52.0% | 42/44 = 95.5% |
| rules + intent-v3 (after) | 0/872 = 0.0% | 0/385 | 0/487 | 41/152 = 27.0% | 37/44 = 84.1% |

The intent-v3 row on the 11 clean intents is **in sample** (it was trained on them). The honest number is the leave-one-intent-out estimate below; the mixed intents were never trained on by any model.

## intent-v3 on topics it has not seen (leave one intent out)

Misrouted: **69/872 = 7.9%** (95% CI 6%–10%) vs intent-v2 271/872 = 31.1% (CI 28%–34%). Paired exact McNemar: only v3 right 208, only v2 right 6, p = 9.7e-54.

| Left-out intent | n | intent-v2 → intake | intent-v3 (never saw this intent) → intake |
|---|---|---|---|
| abroad | 120 | 62 | 13 |
| address | 81 | 6 | 2 |
| app_error | 63 | 36 | 4 |
| atm_limit | 83 | 3 | 2 |
| balance | 78 | 0 | 1 |
| business_loan | 79 | 1 | 0 |
| card_issues | 77 | 62 | 21 |
| cash_deposit | 76 | 3 | 0 |
| high_value_payment | 67 | 53 | 22 |
| joint_account | 80 | 18 | 0 |
| pay_bill | 68 | 27 | 4 |

## The dispute guard: how sure must an out-of-scope reading be?

intent-v3 alone (no guard) still turned real disputes away when a caller mixed a request with an unrecognised payment ("quiero ver mis últimas transacciones, hay un pago que no reconozco"). An out-of-scope reading is now accepted only while the dispute labels together stay below a guard. Chosen on the **Spanish** mixed intents (dev) at a cost fixed beforehand — one dispute turned away = 5 unnecessary questions; the **Portuguese** half is the test. Deployed guard: **0.2**.

| Guard | es (dev): disputes turned away | es: extra questions | es cost | pt (test): disputes turned away | pt: extra questions | Clean intents, left out: misrouted |
|---|---|---|---|---|---|---|
| 1.0 | 9/23 | 9/69 | 54 | 7/21 | 15/83 | 33/872 |
| 0.3 | 8/23 | 9/69 | 49 | 5/21 | 20/83 | 47/872 |
| 0.2 ← | 3/23 | 17/69 | 32 | 4/21 | 24/83 | 69/872 |
| 0.15 | 3/23 | 19/69 | 34 | 3/21 | 28/83 | 94/872 |
| 0.1 | 2/23 | 23/69 | 33 | 3/21 | 33/83 | 133/872 |
| 0.07 | 1/23 | 29/69 | 34 | 3/21 | 39/83 | 159/872 |
| 0.05 | 1/23 | 33/69 | 38 | 3/21 | 40/83 | 190/872 |

## Where intent-v3 is still wrong on the mixed intents

| Intent | Lang | Message | Route |
|---|---|---|---|
| freeze | es | por favor quiero bloquear mi tarjeta | intake |
| freeze | es | hola buenos días me gustaría congelar mi tarjeta ya que últimamente he estado que han estado realizando unos pagos en mi nombre que no son míos | redirect |
| freeze | es | necesito que me bloqueen mi tarjeta | intake |
| freeze | es | necesito que tener todas las transacciones de mi tarjeta dejarla bloqueada | intake |
| freeze | es | hola buenos días es que me gustaría cancelar la tarjeta terminada en 47 porque es que me acaban de robar pero quiero darla de baja quiero cancelarlo ahora mismo | intake |
| freeze | es | buenos días he perdido la cartera y que me gustará congelar mi tarjeta por favor | intake |
| freeze | es | he tenido un problema con mi tarjeta no la encuentro y quiero bloquear todas las transacciones | intake |
| freeze | es | hola buenos días mira te ha llamado porque tenía un problema y me han robado la cartera y me gustaría bloquear todas mis tarjetas | intake |
| freeze | es | hola buenos días nada yo me voy porque tuve un problema con mi tarjeta y que la extravié y quería bloquear totalmente las transacciones que se pueden realizar c | intake |
| freeze | es | quería que pudieran caer congelar mi tarjeta a ser posible bastante pronto porque he perdido la cartera y tenía toda mi tenía mi tarjeta quiero congelarlas para | intake |
| freeze | es | quiero detener todas las transacciones en mi tarjeta | intake |
| freeze | es | hola buenos días llamaba porque quiero bloquear mi tarjeta ya que no quiero volver a usar muchas gracias | intake |
| freeze | es | detener todas las sangres en mi tarjeta de vida robo de la misma | intake |
| freeze | es | mira acabo de perder mi tarjeta en la calle y quiero congelar para que no curres mucho | intake |
| freeze | es | tarjeta me bloquea favor por tarjeta me congelar tarjeta las | intake |
| direct_debit | es | hola buenos días me ha llegado en la aplicación del móvil una notificación de una domiciliación bancaria y realmente no sé qué y me gustaría que me pudiera guia | redirect |
| latest_transactions | es | hola m llamado porque quería saber mis últimas transacciones con la con la tarjeta gracias | intake |
| latest_transactions | es | muéstrame mis últimos movimientos mi últimas transacciones | intake |
| latest_transactions | es | quiero ver mis últimas transacciones | intake |
| latest_transactions | es | hola muy buenas he recibido un poco que no reconozco me gustaría ver las últimas acciones que están en mi cuenta | redirect |
| latest_transactions | pt | mostra-me as minhas últimas transações | intake |
| latest_transactions | pt | quando eu tento levantar um extrato da minha conta aparece uma operação não autorizada | redirect |
| latest_transactions | pt | Boa tarde eu sou ligar porque tenho aqui falta de informação sobre uma das minhas últimas transações que fiz | intake |
| latest_transactions | pt | mostra-me as minhas últimas transações por favor | intake |
| latest_transactions | pt | Boa tarde sou ligar porquê gostaria de ser as minhas transações recentes poderíamos mostrar e Sim eu conheço | intake |
| latest_transactions | pt | por favor mostra-me as minhas últimas transações | intake |
| latest_transactions | pt | Bom dia eu estou a ligar para saber se podiam podiam Mostrar nas transações ou lideram instalações as últimas a um uma transferência uma transferência de dinhei | redirect |
| latest_transactions | pt | eu gostaria que me mostrassem as últimas transações efetuadas na minha conta Por favor | intake |
| latest_transactions | pt | Quero ver as transações correntes | intake |
| latest_transactions | pt | Bom dia Gostaria de mostrar as minhas últimas transações acredito que exista um pagamento que não conheço e gostaria de saber de onde é que veio | redirect |
| latest_transactions | pt | queria mostrar as minhas últimas transações por favor | intake |
| latest_transactions | pt | queria mostrar as últimas transações feitas com o meu cartão por favor | intake |
| direct_debit | pt | Bom dia Olha eu queria aceder aos débitos diretos da minha conta Está a haver um problema Eu acho que tu me estão a tirar dinheiro indevidamente | redirect |
| direct_debit | pt | Olá boa tarde sábado vou ver um débito direto é | intake |
| freeze | pt | eu queria te contar todas as transações do meu cartão em casa | intake |
| freeze | pt | congelar o meu cartão a interromper todas as transações com o cartão foi roubado Então queria cancelar o cartão | intake |
| freeze | pt | estou a ligar porque queria bloquear no cartão sempre que razão é que ele foi roubado e portanto que eu bloquear porque não pudesse ser feita qualquer tipo de t | intake |
| freeze | pt | temos competições no meu cartão ou seja bloquear o cartão congelar | intake |
| freeze | pt | Boa tarde preciso de cancelar o meu cartão por favor | intake |
| freeze | pt | assim eu gostava de descongelar o meu cartão e por favor e aquele para bloquear o cartão porque foi roubado e percebo que eu desativei que é para eu não perder  | intake |
| freeze | pt | o cenário é é congelar o cartão por exemplo interromper todas as Nações do cartão ou do roubado tens que me bloqueie ao gênero | intake |
| freeze | pt | Por favor quero congelar o meu cartão | intake |
| freeze | pt | quero cancelar o meu cartão | intake |
| freeze | pt | quero congelar o meu cartão | intake |
| freeze | pt | Bom dia gostaria de cancelar o meu cartão de débito se faz favor obrigado | intake |
| freeze | pt | as minhas transações do cartão eu queria cancelar o meu cartão por favor eu quero cancelar o meu cartão por favor | intake |
| freeze | pt | interromper todas as transações do meu cartão | intake |
| freeze | pt | congelar meu cartão | intake |

## Limitations

- European Spanish and Portuguese (es-ES, pt-PT); the bank's customers are in Mexico, Colombia and Argentina, and the app's Portuguese is Brazilian. Vocabulary differs ("domiciliación", "débito direto", "telemóvel").
- The mixed-intent labels were assigned by the coding assistant under the criterion in `ml/external/README.md`, not by a human; the 11 clean intents carry only the dataset's own labels.
- Opening messages only, read by the free reader. The Claude path was not run on this set (API credit is kept for the judges, ADR-026).
