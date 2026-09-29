# Human review of the intent labels (blind)

**Why.** Every intent label in the project came from models: the training corpus was labelled by construction by the
coding assistant, and the independent set was written and re-labelled by model subagents (κ = 1.0 between two models).
The challenge asks for valid labels and a check against human judgment. This is that check.

**Method.**
- Sample: `ml/corpus/human-review.tsv`, 90 messages, 5 per label from each source (45 from the training corpus,
  45 from the independent set), shuffled; 56 Spanish, 34 Portuguese.
- Blind: the project author labelled every message in a web page that hid the model label
  (<https://claude.ai/artifact/Y7kBk8XK92YhCbTYgJDJBg>, answers stored in the page's database), with a one-line
  definition per label and a "can't decide" option. Blind labelling avoids the agree-with-what-you-see bias of a
  "do you agree?" review.
- One annotator, single pass, 2026-09-28.

## Results

| | Decided | Agree | κ (Cohen) |
|---|---|---|---|
| All | 85 of 90 (5 “can't decide”) | **78 (91.8%)** | **0.91** |
| Training corpus | 43 | 40 (93.0%) | 0.92 |
| Independent set | 42 | 38 (90.5%) | 0.89 |
| Spanish / Portuguese | 54 / 31 | 50 / 28 | — |

By the model's label (agree / decided, plus “can't decide”):

| Label | Agree | Can't decide |
|---|---|---|
| FRAUD_CNP | 9/10 | 0 |
| FRAUD_CP | 8/8 | 2 |
| DUPLICATE | 9/10 | 0 |
| INCORRECT_AMOUNT | 9/10 | 0 |
| NOT_RECEIVED | 10/10 | 0 |
| CANCELLED_RECURRING | 10/10 | 0 |
| OUT_OF_SCOPE | 9/9 | 1 |
| HUMAN | 10/10 | 0 |
| **DISPUTE_NO_REASON** | **4/8** | **2** |

## The disagreements

| # | Source | Message | Model | Human | Reading |
|---|---|---|---|---|---|
| 8 | independent | Estoy inconforme con un cargo que aparece hoy en mi cuenta. | DISPUTE_NO_REASON | FRAUD_CNP | boundary: a complaint about a charge with no reason stated |
| 11 | independent | Preciso que investiguem a cobrança do dia 15 de abril no meu cartão. | DISPUTE_NO_REASON | FRAUD_CNP | same boundary |
| 49 | independent | …quiero disputar la compra de \$3,450.90 hecha en "TechStoreMX"… | DISPUTE_NO_REASON | FRAUD_CNP | same boundary |
| 4 | corpus | é sobre uma compra no Mercado Livre da semana passada | DISPUTE_NO_REASON | OUT_OF_SCOPE | a fragment; the label assumes a dispute conversation is already under way |
| 48 | independent | me clonaron la banda magnética, apareció un cargo en otro país | FRAUD_CNP | FRAUD_CP | a counterfeit card is card-present fraud; the human reading is defensible and the model label is arguably wrong |
| 12 | corpus | o táxi cobrou o dobro do que marcava | INCORRECT_AMOUNT | DUPLICATE | “twice the meter” is a wrong amount, not two charges; likely a reading slip |
| 64 | corpus | cargo repetido en mi tarjeta, es la misma compra | DUPLICATE | FRAUD_CNP | the text describes a duplicate; likely a reading slip |

“Can't decide” (5): three DISPUTE_NO_REASON fragments (“la más grande de la semana pasada”, “a do iFood de 56”),
two FRAUD_CP with a lost or reported-stolen card plus unknown charges (#25, #72) — both reasons fit — and one
account closure (#36), which is out of scope for disputes but reads like a request the bank should route.

## What it means

- The labels hold up: 0.91 against a blind human, in line with the 0.89–0.92 range on both sources, so the corpus is
  not only internally consistent.
- **DISPUTE_NO_REASON is the weak definition, not a weak model.** The annotator read “I want to dispute this charge” as an
  unrecognised charge; the label means “the reason is not stated yet”. The system's behaviour on that label is to ask
  what happened, so these disagreements cost one extra question, never a wrong action: the policy requires a stated
  reason and its evidence before anything is opened.
- **FRAUD_CP vs FRAUD_CNP** needs a sharper rule for cloned cards and for “lost card plus charges”. A wrong reading
  here is visible to the customer: the confirmation summary names the reason before anything is opened (ADR-019).
- Nothing here was used to change the model or the corpus; relabelling the corpus from this review would leak it into
  training. The two likely reading slips are left as recorded.

## Limitations
- One annotator, and the project's author; a second independent person would give inter-human agreement.
- 90 messages; per-label counts are 10, so per-label rates carry wide uncertainty.
