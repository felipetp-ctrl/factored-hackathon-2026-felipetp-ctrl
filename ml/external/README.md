# External data: real customer speech

`minds14-es-pt.tsv` — the es-ES and pt-PT configurations of **MInDS-14** (PolyAI, [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/),
<https://huggingface.co/datasets/PolyAI/minds14>; Gerz et al., 2021, *Multilingual and Cross-Lingual Intent Detection
from Spoken Data*). 1,090 people calling an e-banking line, transcribed by ASR, each with the intent the dataset
authors assigned. Only the text columns are kept (no audio). Public data, no customer of LATAM Bank.

Used as an **external test of the first routing decision** (start the dispute intake or not) and, for the 11 clean
intents, as real out-of-scope training text for `intent-v3` ([ADR-030](../../docs/decisions/ADR-030-real-speech-and-intent-v3.md),
[report](../results/external-minds14.md)).

| Column | Meaning |
|---|---|
| `row` | Position in the file (dataset ids repeat across speakers) |
| `id` · `locale` · `lang` | Dataset file id, `es-ES`/`pt-PT`, `es`/`pt` |
| `intent` | The dataset's human-assigned intent (14) |
| `label` | `NOT_DISPUTE`, `DISPUTE` or `UNSURE` (excluded) |
| `label_source` | `dataset` (11 intents that are never a card-charge dispute) or `criterion` (read one by one) |
| `text` · `english` | Transcription and the dataset's English translation |

## Labelling criterion for the three mixed intents

`latest_transactions`, `direct_debit` and `freeze` were read message by message before any model was scored on them:

- **DISPUTE** — the caller reports a specific payment, charge or debit they do not recognise, did not authorise, or
  that was not delivered ("hay un pago que no reconozco", "débito direto sem a minha autorização", "o fornecedor não
  cumpriu").
- **UNSURE** (excluded) — garbled or self-contradictory ("…no conozco si reconozco el pavo"), or asks to *return* a
  direct debit without saying why (a legitimate return is not necessarily a dispute).
- **NOT_DISPUTE** — everything else: show my transactions, how direct debits work, freeze or cancel a lost card with no
  charge mentioned.

Result: 44 DISPUTE, 152 NOT_DISPUTE, 22 UNSURE. The labeller was the coding assistant, not a person; the 872 clean-intent
messages depend only on the dataset's labels. These three intents are never used for training.
