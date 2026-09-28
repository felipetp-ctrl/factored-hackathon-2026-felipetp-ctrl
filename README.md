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
        │               └ fallback when the model is down or over budget (same fields, US$ 0): rules + our trained
        │                 intent classifier intent-v2 (TF-IDF + logistic regression, ES/PT, 0.2 ms, pure Python)
        │
  state machine ── identify transaction → reason → evidence → policy → confirm → act → verify
        │                                   │
  versioned policy (YAML, rule ids)    bank tools (ownership from session, bounded retry, idempotent)
        │
  reply templates (ES/PT, only verified data) · structured handoff to a human · append-only audit log
```

## Live demo

- Web app: **https://latam-bank-disputes.vercel.app**
- API: **https://latam-bank-dispute-ops-api.onrender.com** (OpenAPI docs at `/docs`; free plan — the first request after
  idle time can take about a minute while the service wakes up)

The page opens on **the bank's case board**; the customer's app is one channel on the side, with a guided dispute form
instead of a chat window. Every case takes the same five steps (Understand, the only AI step → Decide by written policy →
customer confirms → bank tools act → every action read back); click a case to see its path, what an agent needs and the
audit trail ([ADR-024](docs/decisions/ADR-024-bank-first-no-chat.md)). Open **Guided tour** in the top bar for seven
scenarios, each with what to do and what should happen:

| # | Scenario | What to look for |
|---|---|---|
| 1 | Written complaints | *Written complaints* tab → process six letters (email, web, branch, app; ES/PT) → 2 resolved with no person, 4 go to a person with what is still missing ([ADR-023](docs/decisions/ADR-023-case-system-framing.md)) |
| 2 | Fraud alert | The bank asks first → "Não fui eu" → card in hand? → confirm and block → the case walks every step on the board |
| 3 | Normal | "No reconozco" on a purchase → two questions → confirmation → case read back → appears under *Mis disputas* |
| 4 | Ambiguous | Several charges at the same merchant → the app lists them and asks; it never picks for the customer |
| 5 | Out of scope | Balance question → declined without touching any case → polite close |
| 6 | Needs a person | Above US$ 450 → the case lands in *With a person* with verified facts → act on it as the agent → the customer sees it |
| 7 | Attack | Prompt injection + another customer's transaction id → same answer as "not found" → handed off as suspicious access |

Every bank message has a **Why?** link with the rule that decided it. The top bar can expire the session or
**simulate an AI outage** (the rule-based fallback takes over). Each browser tab gets its own copy of the data;
*Reset demo* starts it over. No key is needed: the public deploy runs in demo mode on synthetic data (ADR-016).

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
make test                       # offline tests (no API calls)
make api                        # http://localhost:8000  (OpenAPI docs at /docs)
make web                        # http://localhost:3000  (in another terminal)
```

Open the web app and pick a scenario. Locally the bank side needs `DEMO_MODE=true` (or the agent key in production
mode). Without `ANTHROPIC_API_KEY` the service runs the rule-based NLU only (`NLU_MODE=rules`), so the whole demo
works offline and for free.

Docker: `docker compose up --build` (API on :8000, web on :3000).

Real data: `make data` downloads nothing by itself — sync the organizer bucket to `data/raw/` first (read-only
credentials from the organizers, never committed), then it builds bronze/silver/gold in ~20 s, writes
`docs/data_quality_report.md` and a gold sample for the demo (`DEMO_DB=data/demo/dispute_ops.db make api`).

Deploy: every push to `main` deploys both sides — Render builds the API from `render.yaml` (Docker), Vercel builds the web
app with Root Directory `frontend` and `NEXT_PUBLIC_API_URL` pointing at the API; other branches get Vercel previews.

## Results

Offline simulations on held-out cases; nothing here is a production measurement. Every set, its method and its caveats:
[docs/evaluation.md](docs/evaluation.md).

| What was tested | Cases | This system | Comparison |
|---|---|---|---|
| App conversation, customers who know the charge (`test-v2`) | 42 × 2 runs | 84/84 correct, **0 unsafe**, 71% resolved safely without a person | Plain AI chatbot: 56/84, **13 unsafe**, 44% |
| App conversation, customers with vague memory, blind (`hard-v1`) | 36 | free reader 30/36, Claude path 31/36 after fixes | Same system before fixes: 16/36 and 24/36 |
| Written complaints (`channels-v1`) | 24 | 23/24 correct, 0 unsafe | Keyword rules 19/24; everything to a person 12/24 |
| Fraud-alert answers (`channels-v1`) | 18 | 17/18 correct, 0 unsafe | Keyword rules 17/18 |
| Reading the dispute reason, another author, blind labels (`independent-v1`) | 525 | trained classifier 94.1% | Keyword rules 45.7% |

Latency per turn p50 2.1 s / p95 3.1 s with Claude (test-v2); cost per safe resolution US$ 0.013 vs US$ 0.033 for the
chatbot. Failures are listed in every report, including the bugs the hard sets found. Limits: the Claude path in
`hard-v1` was read by a Claude subagent given the production prompt, not the API; sets are small (zero unsafe in 84
conversations does not prove zero risk); intent labels come from models, with a 90-message human review pending.

![Vague-memory test before and after fixes](docs/figures/hard_v1_before_after.png)

**Machine learning.** A trained reason classifier (TF-IDF + logistic regression, ES/PT, 0.2 ms, pure Python) powers
the free reader; it lost to keywords in its first version and that result is kept ([ADR-019](docs/decisions/ADR-019-learned-intent-classifier.md)).
There is no fraud model on purpose: the fraud labels have no learnable signal (ROC-AUC 0.50), so the alert threshold was
recalibrated instead ([ADR-020](docs/decisions/ADR-020-fraud-label-audit.md)); a scan of nine other targets found the same
([ADR-021](docs/decisions/ADR-021-learnability-scan.md)). MLflow registry, model card, CI regression gate and drift
monitoring: [docs/evaluation.md](docs/evaluation.md#machine-learning).

**The problem in data.** About 380 unrecognised-charge complaints a month, 70% still open, 15 days to resolve, and a
written complaint identifies the charge only 15.8% of the time ([problem analysis](docs/problem_analysis.md)).

## Repository

| Path | What |
|---|---|
| `backend/src/dispute_ops/` | domain, store, auth, policy, tools, flow, channels, language layer, API, evaluation |
| `backend/src/dispute_ops/policy/disputes_v2.yaml` | the synthetic dispute policy (versioned) |
| `frontend/` | Next.js: bank case board and drawer, written complaints, fraud alerts, results; customer app with a guided dispute form |
| `docs/decisions/` | architecture decision records (why each choice, alternatives, trade-offs) |
| `docs/requirements_traceability.md` | every challenge requirement → evidence → how to verify |
| `docs/problem_analysis.md` · `docs/data_quality_report.md` · `docs/operations.md` | the problem in numbers · data quality · running it |
| `eval/results/` · `docs/evaluation.md` | evaluation reports · every set explained |
| `ml/` | intent corpus (team-generated), training and audit reports; code in `backend/src/dispute_ops/ml/` |

## Data

The organizer dataset (LATAM Bank, synthetic, ~19M rows) is read from S3 and never committed. The public demo runs on
a gold sample of it (`backend/demo_data/dispute_ops.db`); unit tests also use a small **team-generated synthetic
fixture** (`backend/tests/fixtures/seed.json`) shaped after the data dictionary. The intent corpus (`ml/corpus/`) is
team-generated too.
Findings from the dataset so far: the dispute workflow is backed by the data ("Cargo no reconocido" is the only
sub-category of 20% of complaints), while free text in complaints and transcripts is templated — see the limitations.

## Known limitations

- Portuguese does not exist in the dataset; Portuguese behaviour is evaluated only through simulated customers.
- The policy is synthetic; its amount threshold is calibrated on the data's value distribution (ADR-013), not on
  real dispute outcomes.
- Conversation state, rate limiting, idempotency and demo workspaces live in one process's memory (a restart resets them).
- Demo mode opens the bank-side views without a key (synthetic data only); production mode keeps the agent key.
- The fallback NLU understands fewer phrasings than Claude; its learned classifier was trained on team-written text
  and evaluated on LLM-simulated customers only. A confident wrong reason reaches the confirmation summary, where the
  customer sees the reason before confirming (ADR-019).
- Identity is a test provider (`POST /auth/session`), standing in for the bank's real login.
- Name detection is not part of PII masking; structured identifiers (cards, emails, phones, national ids) are.
