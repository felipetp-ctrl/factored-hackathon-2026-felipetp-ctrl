# LATAM Bank — Dispute Operations

An AI-first customer-service **system** (not a chatbot) for one banking workflow: **disputing card charges** —
"cargo no reconocido" / "compra não reconhecida". Built for the Factored AI & Data Hackathon 2026.

Customers talk in **Spanish or Portuguese** through chat, written complaints (PQR) or a proactive fraud alert.
A deterministic core decides; the language model only interprets.

```
chat / PQR / fraud alert
        │
  gateway ── session check · PII masking · injection signals · language
        │
  Claude Haiku 4.5 ── free text → validated structured fields (never decides, never writes to the customer)
        │
  state machine ── identify transaction → reason → evidence → policy → confirm → act → verify
        │                                   │
  versioned policy (YAML, rule ids)    bank tools (ownership from session, bounded retry, idempotent)
        │
  reply templates (ES/PT, only verified data) · structured handoff to a human · append-only audit log
```

## What it does

| Path | Example | Result |
|---|---|---|
| Normal | "No reconozco un cargo de 1250 en Amazon" | Finds the charge, asks for missing evidence, confirms, opens the case, offers to block the card, **reads both back before saying they happened** |
| Ambiguous / unsupported | "Me cobraron dos veces Netflix" · "¿cuánto saldo tengo?" | Lists candidates with date and time; declines out-of-scope requests without touching the case |
| Human required | Amount above limit, repeat complainer, regulator threat, "quero um atendente" | Hands off with verified facts, actions taken, policy decision and open questions — no raw transcript |

Safety properties, all covered by tests:
- Write tools (`open_dispute`, `block_card`) are never exposed to the model; only the state machine calls them, after a policy decision and explicit confirmation.
- Tools resolve the customer from the session token, never from an id the model supplies. "Not yours" and "does not exist" get the same answer.
- Expired, forged or swapped sessions are rejected before any model call.
- Nothing is reported as done unless it was verified by reading it back.

## Run it

Requirements: Python 3.12+ with [uv](https://docs.astral.sh/uv/), Node 22 + pnpm, an Anthropic API key.

```bash
cp .env.example .env            # set ANTHROPIC_API_KEY and AGENT_API_KEY
make install                    # backend dependencies
make test                       # 140+ offline tests (no API calls)
make api                        # http://localhost:8000  (OpenAPI docs at /docs)
make web                        # http://localhost:3000  (in another terminal)
```

Open the web app, type the agent key in the top bar, pick a test customer and start a conversation. The right
pane shows what the bank understood and decided at every step.

Docker: `docker compose up --build` (API on :8000, web on :3000).

Real data: `make data` downloads nothing by itself — sync the organizer bucket to `data/raw/` first (read-only
credentials from the organizers, never committed), then it builds bronze/silver/gold in ~20 s, writes
`docs/data_quality_report.md` and a gold sample for the demo (`DEMO_DB=data/demo/dispute_ops.db make api`).

Deploy: `render.yaml` (API, Docker) + Vercel for `frontend/` with `NEXT_PUBLIC_API_URL` pointing at the API.

## Evaluate it

```bash
make eval                                   # 44 scenarios × {proposed, naive LLM baseline}
make eval ARGS="--systems proposed --only fraud --repeats 3"
```

Scenarios have a persona for an LLM-simulated customer (Claude Sonnet 5) and an expected outcome **derived from
the policy**. A deterministic oracle reads the database to judge correctness and unsafe outcomes. Reports land in
`eval/results/<timestamp>/` (`report.md`, `summary.json`, `results.jsonl` with full transcripts).

**Held-out result, `test-v1`** — 35 scenarios generated from real transactions of the organizer dataset, labelled by
the policy and committed before any run; 3 runs per system = 105 simulated conversations each (offline simulation):

| | Naive LLM baseline | Proposed |
|---|---|---|
| Correct outcome | 66/105 | **105/105** |
| Safe automated resolution (in-scope) | 30/81 (37%) | **57/81 (70%)** |
| Unsafe outcomes | 12/105 (disputes opened against policy, cards blocked without being asked) | **0/105** |
| Escalations missed | 11/24 | **0/24** |
| Unnecessary escalations | 24/81 | 12/81 (all cross-customer attempts sent to a person) |
| Turn latency p50 / p95 | 3.3 s / 5.2 s | **2.0 s / 3.0 s** |
| Cost per safe resolution | US$ 0.041 | **US$ 0.011** |
| By language (correct) | es 36/54 · pt 30/51 | es 54/54 · pt 51/51 |

**Harder held-out set, `test-v2`** — 42 scenarios from real transactions: every dispute reason, vague and typo-laden
customers, several charges at the same merchant, per-reason windows, every handoff trigger and the attack cases;
2 complete runs per system = 84 conversations each (run 3 and the Sonnet baseline were cut by exhausted API credit and
will be re-run):

| | Naive LLM baseline | Proposed |
|---|---|---|
| Correct outcome | 56/84 | **84/84** |
| Safe automated resolution (in-scope) | 31/70 (44%) | **50/70 (71%)** |
| Unsafe outcomes | 13/84 | **0/84** |
| Escalations missed / unnecessary | 8/20 · 12/64 | **0/20 · 0/64** |
| Turn latency p50 / p95 | 3.1 s / 4.6 s | **2.1 s / 3.1 s** |
| Cost per safe resolution | US$ 0.033 | **US$ 0.013** |

Component evaluation on the same conversations (`test-v2`, proposed system):

| Component | Claude Haiku NLU | Keyword baseline |
|---|---|---|
| Dispute-reason accuracy (4 reasons) | **100% (46/46)** | 87.0% (40/46) — misses 4/8 incorrect-amount, 1/4 not-received, 1/30 fraud |
| Out-of-scope recall / false-positive rate | 100% / 0% | 100% / 0% |
| Transaction identification (NLU + search) | 100% (46/46) | — |
| Injection flag (rules) TPR / FPR | 100% (6/6) / 0% (0/98) | — |
| Language rules accuracy when decided | 98.3% (5.3% undecided → the model decides) | — |

Small samples: zero observed unsafe outcomes in 105 + 84 conversations does not establish zero risk; the component
baseline shows the language model's margin is on the less common reasons, not on fraud.
Full report: [`eval/results/20260926T175451Z-test-v1/report.md`](eval/results/20260926T175451Z-test-v1/report.md).
The development run (`dev-v1-before-fixes`, synthetic fixture) found 3 bugs that were fixed before `test-v1` was frozen.

See [ADR-009](docs/decisions/ADR-009-evaluation-method.md) for method and limitations.

## Repository

| Path | What |
|---|---|
| `backend/src/dispute_ops/` | domain, store, auth, policy, tools, flow, channels, language layer, API, evaluation |
| `backend/src/dispute_ops/policy/disputes_v1.yaml` | the synthetic dispute policy (versioned) |
| `frontend/` | Next.js: customer chat + decision inspector, agent console, operations |
| `docs/decisions/` | architecture decision records (why each choice, alternatives, trade-offs) |
| `eval/results/` | evaluation reports |

## Data

The organizer dataset (LATAM Bank, synthetic, ~19M rows) is read from S3 and never committed. The demo and tests run
on a small **team-generated synthetic fixture** (`backend/tests/fixtures/seed.json`) shaped after the data dictionary.
Findings from the dataset so far: the dispute workflow is backed by the data ("Cargo no reconocido" is the only
sub-category of 20% of complaints), while free text in complaints and transcripts is templated — see the limitations.

## Known limitations

- Portuguese does not exist in the dataset; Portuguese behaviour is evaluated only through simulated customers.
- The policy is synthetic; thresholds are placeholders to be calibrated with the data.
- Conversation state, rate limiting and idempotency live in one process's memory.
- Identity is a test provider (`POST /auth/session`), standing in for the bank's real login.
- Name detection is not part of PII masking; structured identifiers (cards, emails, phones, national ids) are.
