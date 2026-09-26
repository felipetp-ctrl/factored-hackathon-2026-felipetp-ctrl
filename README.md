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

Docker: `docker compose up --build` (API only; build not yet verified on CI).

## Evaluate it

```bash
make eval                                   # 44 scenarios × {proposed, naive LLM baseline}
make eval ARGS="--systems proposed --only fraud --repeats 3"
```

Scenarios have a persona for an LLM-simulated customer (Claude Sonnet 5) and an expected outcome **derived from
the policy**. A deterministic oracle reads the database to judge correctness and unsafe outcomes. Reports land in
`eval/results/<timestamp>/` (`report.md`, `summary.json`, `results.jsonl` with full transcripts).

Development run `dev-v1-before-fixes` (offline simulation on the synthetic fixture, 1 run, before the fixes it
revealed — **not a held-out result**):

| | Naive LLM baseline | Proposed |
|---|---|---|
| Correct | 29/44 | 37/44 |
| Unsafe outcomes | 10/44 | 4/44 |
| Missed escalations | 6/12 | 2/12 |
| Turn latency p50 / p95 | 3.1 s / 4.8 s | 2.0 s / 2.9 s |
| Cost per safe resolution | US$ 0.026 | US$ 0.017 |

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
