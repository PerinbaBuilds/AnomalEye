# 🦅 AnomalEye — Agentic AI for AML Suspicious-Activity Detection

AnomalEye is a **full-stack, compliance-grade AML platform**. At its core is an
**autonomous agent**: you give it an instruction in plain English — *"Find
structuring patterns in the last 30 days"* — and it **parses the intent, builds
a dynamic execution plan, invokes only the tools that query needs**, detects
laundering typologies, scores risk, and returns an **explainable** verdict with a
recommended escalation action (`monitor` / `review` / `report`).

It ships as a **React + TypeScript** analyst console on top of a **FastAPI**
service that exposes a hybrid **rules + statistics + machine-learning** detection
engine — every decision auditable, every threshold explicit.

> Built to attack the real problem: rule-based AML systems drown analysts in
> false positives while sophisticated schemes (structuring, smurfing, layering,
> rapid cash-out) slip through.

---

## What's inside

```
┌──────────────────────────── Frontend (React + TS + Vite + Tailwind) ────────────────────────────┐
│  Dashboard · AI Agent Console · Alert Queue · Live Monitor · Link Analysis · Performance · Docs   │
└───────────────────────────────────────────────┬──────────────────────────────────────────────────┘
                                                 │  REST / SSE
┌───────────────────────────────────────────────▼──────────────────────────────────────────────────┐
│  Backend (FastAPI)   /api/overview · /api/agent/query · /api/alerts · /api/customers/{id} ...      │
└───────────────────────────────────────────────┬──────────────────────────────────────────────────┘
                                                 │
┌───────────────────────────────────────────────▼──────────────────────────────────────────────────┐
│  Engine (Python)   Agent(planner + orchestrator)  →  EDA · Features · Anomaly · Risk · Explain     │
└────────────────────────────────────────────────────────────────────────────────────────────────────┘
```

### Six analyst views

| View | What it does |
|---|---|
| **Dashboard** | Portfolio KPIs, risk distribution, typology breakdown, CTR-band histogram, flagged-activity trend, priority cases |
| **AI Agent Console** | The hero: type a query → see the agent's detected intent, filters, **tool pipeline**, planning rationale, and explained findings |
| **Alert Queue** | Case triage — filter by risk band / action / typology, paginate, drill into any entity |
| **Live Monitor** | Real-time transaction blotter scored on the fly over **Server-Sent Events** |
| **Link Analysis** | Counterparty network graphs (funnel = smurfing, chain = layering) + discovered layering chains |
| **Entity 360** | Per-customer risk gauge, plain-English explanation, evidence, network, full transaction history |
| **Model Performance** | Precision / recall / F1 and per-typology recall vs injected ground truth |
| **Methodology** | Every rule, weight and threshold — the auditable rulebook |

---

## Why it's an *agent*, not a pipeline

The agent reads the query, extracts intent / filters / entities / typology, and
**constructs a plan on the fly** — running only the necessary tools on the
necessary slice of data:

| User query | What the agent decides to do |
|---|---|
| `Analyse this dataset for suspicious activity` | Full pipeline: EDA → features → hybrid detection (rules + ML) → risk → explain |
| `Find structuring patterns in the last 30 days` | Apply 30-day filter → run **only** the structuring detector → skip EDA & ML |
| `Which customers made 10+ transactions under $10,000?` | Pure aggregation rule; **no ML** |
| `Is customer ID 1528 suspicious?` | Single-entity lookup; risk computed on-demand for **that customer only** |
| `Flag high-risk customers` | Full hybrid suite, return **only** the high-risk band |

The chosen plan is shown in every response under `tools_invoked` and
`planning_rationale`.

---

## Quick start

**Prerequisites:** Python 3.10+ and Node 18+.

### One command (production build + serve)

```bash
# Windows
scripts\start.bat

# macOS / Linux
./scripts/start.sh
```

This installs deps, builds the React app, and serves the whole product (UI +
API) from FastAPI at **http://localhost:8000**.

### Development (hot reload)

```bash
# Windows
scripts\dev.bat

# macOS / Linux
./scripts/dev.sh
```

Backend on `:8000`, Vite dev server with hot reload on **http://localhost:5173**
(it proxies `/api` to the backend).

### Manual

```bash
pip install -r requirements.txt          # Python deps
python -m anomaleye.data.generate        # (optional) regenerate the dataset

cd frontend && npm install && npm run build && cd ..
python -m uvicorn backend.main:app --port 8000   # open http://localhost:8000
```

### CLI (no UI needed)

```bash
python -m anomaleye "Analyse this dataset for suspicious activity"
python -m anomaleye --demo            # run all example queries
python -m anomaleye.evaluate          # detection quality metrics
```

---

## Detection methodology (hybrid)

**Rule + statistical typology detectors** (each emits structured *evidence*):

- **Structuring** — ≥3 cash transactions in `$9,000–$9,999` within 30 days.
- **Smurfing** — ≥6 distinct small senders aggregating above `$10,000` in 7 days.
- **Rapid cash-out** — a large credit ≥80% drained within 72h.
- **Layering** — value through ≥3 accounts in ≤48h; every account flagged.
- **Velocity spike** — 24h burst ≥3σ over the population.
- **High-risk geography** — FATF-flagged jurisdiction exposure (amplifier).

**Machine learning:** an unsupervised **Isolation Forest** over a 13-dimensional
per-customer behavioural fingerprint.

**Risk score:** an auditable weighted blend of the strongest signal per type,
capped at 100, mapped to `low < 40 ≤ medium < 70 ≤ high`. All weights and
thresholds live in `anomaleye/config.py`.

### Measured performance (`python -m anomaleye.evaluate`)

| Metric (customer-level, ≥ medium risk) | Value |
|---|---|
| Precision | **0.77** |
| Recall | **0.91** |
| F1 | **0.84** |

Per-typology recall: structuring **1.0**, smurfing **1.0**, rapid cash-out
**1.0**, layering **0.8**.

---

## API reference (selected)

| Method | Path | Purpose |
|---|---|---|
| `GET`  | `/api/overview` | Dashboard KPIs, distributions, histogram |
| `POST` | `/api/agent/query` | Run a natural-language agent query |
| `GET`  | `/api/alerts?level=&typology=&escalation=` | Filtered alert queue |
| `GET`  | `/api/customers/{id}` | Entity 360 (profile, assessment, timeline, network) |
| `GET`  | `/api/customers/{id}/network` | Counterparty link graph |
| `GET`  | `/api/layering-chains` | Discovered layering paths |
| `GET`  | `/api/performance` | Precision/recall vs ground truth |
| `GET`  | `/api/methodology` | Thresholds, weights, risk bands |
| `GET`  | `/api/stream/transactions` | SSE live scoring feed |

Interactive docs at **http://localhost:8000/docs** when the server is running.

---

## Project layout

```
anomaleye/            # detection engine (importable, tested)
  config.py           # all thresholds & weights (single source of truth)
  agent/              # planner (NL→plan) + orchestrator (dynamic execution)
  tools/              # eda · features · anomaly · risk · explain · network
  data/               # synthetic generator + loader
  cli.py  evaluate.py
backend/              # FastAPI app + cached analysis service
frontend/             # React + TS + Vite + Tailwind console
  src/pages/          # Dashboard, AgentConsole, Alerts, Entity360, ...
  src/components/     # Layout, NetworkGraph, ScoreGauge, ui primitives
scripts/              # start / dev launchers (Windows + Unix)
tests/                # 36 tests: planner, detectors, agent, API, eval gate
```

---

## Tests

```bash
python -m pytest                 # 36 backend/engine tests
cd frontend && npm run typecheck # frontend type safety
```

---

## Design principles

- **Explainable by construction** — every flag quotes the exact numbers that
  triggered it; the risk score breaks down by signal.
- **Auditable** — all business logic in `config.py`, surfaced in the Methodology
  view.
- **Deterministic & offline** — no external API key; the same query always
  yields the same plan and verdict.
- **Ground-truth honest** — the generator labels its injected schemes, so
  detection quality is measured, not asserted.
