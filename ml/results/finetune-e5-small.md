# Fine-tuned transformer vs deployed TF-IDF (`intent-v2`)

> Offline. `intfloat/multilingual-e5-small` (118M parameters) + classification head, fine-tuned 3 epochs on the same 2,808 augmented training examples as intent-v2 (1.1 min on mps). Scored on the held-out sets without any tuning on them.

| Held-out set | n | Fine-tuned e5-small | TF-IDF + LR (intent-v2) | ms/message fine-tuned (CPU) | ms/message TF-IDF |
|---|---|---|---|---|---|
| independent (525) | 525 | 488/525 (93.0%) | 502/525 (95.6%) | 1.9 | 0.13 |
| test-v3 reasons (23) | 23 | 23/23 (100.0%) | 23/23 (100.0%) | 3.3 | 0.26 |
| test-v2 run 3 reasons (23) | 23 | 22/23 (95.7%) | 23/23 (100.0%) | 3.6 | 0.24 |

Deployment needs PyTorch and ~470 MB of weights; the API instance has 512 MB of RAM. The decision rule in ADR-019 applies: deploy the transformer only if it is clearly better on held-out data.
