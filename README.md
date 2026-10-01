# LATAM Bank — Dispute Operations

An AI-first customer-service **system** (not a chatbot) for one banking workflow: **disputing card charges** —
"cargo no reconocido" / "compra não reconhecida". Built for the Factored AI & Data Hackathon 2026.

Customers reach it in **Spanish or Portuguese** through the app, written complaints (PQR) or a proactive fraud alert.
A deterministic core decides; the language model only interprets.

**Judging in two minutes**
1. Open the [live demo](https://latam-bank-disputes.vercel.app) → *Process written complaints* → *See the cases* →
   click a case. Or read the [walkthrough with screenshots](docs/demo.md).
2. Results in one table: [Results](#results). Every requirement of the challenge → where it is met:
   [traceability](docs/requirements_traceability.md).
3. Why it is built this way: [decisions at a glance](#decisions-at-a-glance), 29 ADRs in [docs/decisions](docs/decisions/).

```
chat / PQR / fraud alert
        │
  gateway ── session check · PII masking · injection signals · language
        │
  Claude Haiku 4.5 ── free text → validated structured fields (never decides, never writes to the customer)
        │               └ fallback when the model is down or over budget (same fields, US$ 0): rules + our trained
        │                 intent classifier intent-v3 (TF-IDF + logistic regression, ES/PT, 0.15 ms, pure Python)
        │
  state machine ── identify transaction → reason → evidence → policy → confirm → act → verify
        │                                   │
  versioned policy (YAML, rule ids)    bank tools (ownership from session, bounded retry, idempotent)
        │
  reply templates (ES/PT, only verified data) · structured handoff to a human · append-only audit log
```

## Live demo

- Web app: **https://latam-bank-disputes.vercel.app**
- API: **https://latam-bank-dispute-ops-api.onrender.com** (OpenAPI docs at `/docs`; free plan, kept warm by a scheduled
  ping during the judging window)

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

Every bank message has a **Why?** link with the rule that decided it. The **⋯** menu can expire the session or
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
| Same blind set on the real API, 2 runs each (`hard-v1` API) | 36 × 2 | 65/72 correct, **4/72 unsafe** (two fixed since, ADR-027) | Plain AI chatbot: 49/72, **11/72 unsafe** |
| Written complaints (`channels-v1`) | 24 | 23/24 correct, 0 unsafe | Keyword rules 19/24; everything to a person 12/24 |
| Fraud-alert answers (`channels-v1`) | 18 | 17/18 correct, 0 unsafe | Keyword rules 17/18 |
| Reading the dispute reason, another author, blind labels (`independent-v1`) | 525 | trained classifier 93.5% | Keyword rules 45.7% |
| **Real customer speech**: should this call start a dispute? (MInDS-14, topics never trained on) | 872 calls | intent-v3 sends 7.9% of non-disputes to the dispute intake | intent-v2 31.1%, keyword rules 67.3% |

Latency per turn p50 2.1 s / p95 3.1 s with Claude (test-v2); cost per safe resolution US$ 0.013 vs US$ 0.033 for the
chatbot. 95% intervals for all of these: [uncertainty](docs/analysis/uncertainty.md). Failures are listed in every report, including the bugs the hard sets found. On the real API
(hard-v1, 2 runs): p50 3.1 s / p95 4.3 s per turn, US$ 0.020 vs US$ 0.033 per safe resolution
([details and the four unsafe cases](docs/evaluation.md#hard-v1-on-the-real-api-2026-09-30)). Limits: sets are small (zero unsafe in 84
conversations does not prove zero risk); intent labels come from models, checked by one blind human reviewer on 90 messages (κ = 0.91,
[review](ml/results/human-review.md)).

![Vague-memory test before and after fixes](docs/figures/hard_v1_before_after.png)

**Machine learning.** A trained reason classifier (TF-IDF + logistic regression, ES/PT, 0.15 ms, pure Python) powers
the free reader; it lost to keywords in its first version and that result is kept ([ADR-019](docs/decisions/ADR-019-learned-intent-classifier.md)).
Tested on **real people** (1,090 bank calls, MInDS-14), intent-v2 started a dispute conversation for 31% of unrelated
requests; intent-v3 adds real out-of-scope calls, spoken-style and mixed-topic training copies and a dispute guard chosen
on a dev half: 7.9% on topics it never saw, at the cost of 7 of 44 real disputes needing one more turn
([ADR-030](docs/decisions/ADR-030-real-speech-and-intent-v3.md)).
There is no fraud model on purpose: the fraud labels have no learnable signal (ROC-AUC 0.50), so the alert threshold was
recalibrated instead ([ADR-020](docs/decisions/ADR-020-fraud-label-audit.md)); a scan of nine other targets found the same
([ADR-021](docs/decisions/ADR-021-learnability-scan.md)). MLflow registry, model card, CI regression gate and drift
monitoring: [docs/evaluation.md](docs/evaluation.md#machine-learning).

**The problem in data.** About 380 unrecognised-charge complaints a month, 37 hours to a first answer, 15 days to resolve, and a
written complaint identifies the charge only 15.8% of the time ([problem analysis](docs/problem_analysis.md)).

**Operating insights, tested.** Disputes follow the working week (χ² p < 0.001) but not the hour; volume and channel mix are flat; every country and segment disputes at the same rate (p = 0.91 / 0.71), so no group needs its own rule; 45% of labelled fraud has no usable score, so the fraud-alert lever is coverage, not the threshold; conversations are lost at finding the charge, not at reading the reason; the projected saving depends most on unmeasured back-office time; and the complaint status is a label, not a lifecycle (a two-year-old complaint is as "open" as last month's), so the "70% open" backlog this project first cited does not exist. Each comes with the decision it changes ([operating insights](docs/analysis/operating-insights.md)) and is in the app's **Insights** tab.

## Decisions at a glance

| Decision | Why | Trade-off | ADR |
|---|---|---|---|
| One workflow: card-charge disputes | 20% of complaints, 37 h to a first answer, 15 days to resolve; the intake is where it breaks | No other workflows | [001](docs/decisions/ADR-001-workflow.md) |
| The model reads, code decides | Permissions and policy outside model prose; write tools never reachable by the model | Fewer phrasings handled than a free agent | [004](docs/decisions/ADR-004-hybrid-orchestration.md), [010](docs/decisions/ADR-010-llm-interprets-templates-speak.md) |
| Versioned YAML policy with rule ids | Every decision explainable by a rule, not by model reasoning | Rules must be maintained | [008](docs/decisions/ADR-008-policy-order.md), [013](docs/decisions/ADR-013-policy-v2-calibration.md) |
| Free fallback reader with a trained classifier | Works when the model is down or over budget, US$ 0 | Understands less than Claude | [017](docs/decisions/ADR-017-rule-fallback-nlu.md), [019](docs/decisions/ADR-019-learned-intent-classifier.md) |
| Test the classifier on real speech; retrain with a dispute guard | Every other text was LLM-written; real calls exposed 31% wrong routing | More disputes need one more turn (7/44 vs 2/44) | [030](docs/decisions/ADR-030-real-speech-and-intent-v3.md) |
| No fraud model | Labels have no learnable signal (AUC 0.50); threshold recalibrated instead | No fraud ML showcase | [020](docs/decisions/ADR-020-fraud-label-audit.md) |
| Three channels, one case engine | Half of disputes are written; the bank can ask first | More surface to evaluate (done: channels-v1) | [023](docs/decisions/ADR-023-case-system-framing.md), [025](docs/decisions/ADR-025-channels-evaluation.md) |
| Bank-first UI, no chat window | A case system, not a chatbot | The conversation is one click away | [024](docs/decisions/ADR-024-bank-first-no-chat.md) |
| DuckDB contracts, bronze/silver/gold, immutable identity | Reproducible, fast, refuses re-deliveries that move cards between customers | Batch only | [012](docs/decisions/ADR-012-data-pipeline.md) |
| Incremental silver + write-audit-publish | Only touched keys recomputed (identical to a rebuild on 5.7M rows, 4.5 s vs 12.1 s); gold published only if row conservation, volume and column-profile gates pass (an emptied column blocks; no false alarm on the real held-back week) | One Parquet per table still rewritten | [028](docs/decisions/ADR-028-incremental-silver-and-gates.md), [032](docs/decisions/ADR-032-column-profile-gate.md), [catalog](docs/data_catalog.md) |
| Spend ledger with caps, shared by the demo and evaluation runs | US$ 10 of credit must last the judging window; caps in code survive restarts | One more moving part; failure degrades to the free reader | [026](docs/decisions/ADR-026-judging-spend-caps.md) |
| Sets built to break the system, frozen before running | Earlier sets scored 100%; honest failure rates need hard cases | Lower headline numbers | [009](docs/decisions/ADR-009-evaluation-method.md), [022](docs/decisions/ADR-022-hard-set-and-fuzzy-references.md) |

## Repository

```
├── backend/                  Python 3.12 service (uv, FastAPI) — deployed to Render from render.yaml
│   ├── src/dispute_ops/      domain, store, auth, flow, channels, tools, API
│   │   ├── policy/           versioned dispute policy (disputes_v2.yaml) and its engine
│   │   ├── language/         gateway, Claude NLU, rule fallback, intent-v3 model, reply templates
│   │   ├── pipeline/         bronze → silver → gold, contracts, quality gates, catalog, figures
│   │   ├── evaluation/       simulator, oracle, baselines, metrics
│   │   └── ml/               training, calibration, real-speech test, fraud audit, learnability scan
│   ├── tests/                offline tests and the labelled synthetic fixture
│   └── demo_data/            gold sample served by the public demo
├── frontend/                 Next.js web app (bank console + customer app) — deployed to Vercel
├── eval/                     frozen evaluation sets and every run's report (index: eval/README.md)
├── ml/                       intent corpora, external real speech and ML reports (index: ml/README.md)
├── docs/                     problem, evaluation, data, operations; decisions/ holds the ADRs (index: docs/README.md)
├── .github/workflows/        CI (lint, tests, pipeline on the fixture, typecheck, build) and keep-warm ping
├── Makefile                  every command — run `make` to list them
├── docker-compose.yml        API + web locally
└── render.yaml               API deploy blueprint
```

Generated files (`uv.lock`, `pnpm-lock.yaml`, `docs/data_catalog.md`, `docs/data_quality_report.md`, `eval/results/`)
are marked in `.gitattributes`; local data (`data/`, `mlruns/`) is never committed.
Conventions: [ADR-029](docs/decisions/ADR-029-repository-layout.md). License: [MIT](LICENSE).

## Data

The organizer dataset (LATAM Bank, synthetic, ~19M rows) is read from S3 and never committed. The public demo runs on
a gold sample of it (`backend/demo_data/dispute_ops.db`); unit tests also use a small **team-generated synthetic
fixture** (`backend/tests/fixtures/seed.json`) shaped after the data dictionary. The intent corpus (`ml/corpus/`) is
team-generated too. Real customer speech comes from a public dataset, MInDS-14 (PolyAI, CC BY 4.0;
[`ml/external/`](ml/external/README.md)).
Findings from the dataset so far: the dispute workflow is backed by the data ("Cargo no reconocido" is the only
sub-category of 20% of complaints), while free text in complaints and transcripts is templated — see the limitations.

## Known limitations

- Portuguese does not exist in the dataset; Portuguese behaviour is evaluated through simulated customers and, for
  the first routing decision only, European Portuguese call transcripts (MInDS-14).
- The policy is synthetic; its amount threshold is calibrated on the data's value distribution (ADR-013), not on
  real dispute outcomes.
- Conversation state, rate limiting, idempotency and demo workspaces live in one process's memory (a restart resets them).
- Demo mode opens the bank-side views without a key (synthetic data only); production mode keeps the agent key.
- The fallback NLU understands fewer phrasings than Claude; its learned classifier is trained on team-written text plus
  real out-of-scope calls, and tested on real speech only for routing (ADR-030). A confident wrong reason reaches the
  confirmation summary, where the customer sees the reason before confirming (ADR-019).
- The Claude path's last API measurement (hard-v1, 65/72) predates ADR-031: about one conversation in six now asks
  where the card is; the conversation-level effect is unit-tested and replayed, not re-measured on the API.
- The complaint status in the organizer data is a label, not a lifecycle (insight 7), so the current backlog and
  service level cannot be measured from it.
- Identity is a test provider (`POST /auth/session`), standing in for the bank's real login.
- Name detection is not part of PII masking; structured identifiers (cards, emails, phones, national ids) are.
