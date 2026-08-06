# 👁 AnomalEye &nbsp;[![CI](https://github.com/PerinbaBuilds/AnomalEye/actions/workflows/ci.yml/badge.svg)](https://github.com/PerinbaBuilds/AnomalEye/actions/workflows/ci.yml)

**Ask _"which customers are laundering money?"_ in plain English, and it runs the
investigation — flagging suspicious accounts, scoring the risk, and explaining
every decision.**

> **Live demo:** [anomaleye.onrender.com](https://anomaleye.onrender.com) &nbsp;·&nbsp; _free-tier host — first request may take ~50s to wake_

![Python](https://img.shields.io/badge/Python-2b3138?style=for-the-badge&logo=python&logoColor=3776AB)
![FastAPI](https://img.shields.io/badge/FastAPI-2b3138?style=for-the-badge&logo=fastapi&logoColor=009688)
![NumPy](https://img.shields.io/badge/NumPy-2b3138?style=for-the-badge&logo=numpy&logoColor=4DABCF)
![pandas](https://img.shields.io/badge/pandas-2b3138?style=for-the-badge&logo=pandas&logoColor=E70488)
![scikit-learn](https://img.shields.io/badge/scikit--learn-2b3138?style=for-the-badge&logo=scikitlearn&logoColor=F7931E)
![Groq LLM](https://img.shields.io/badge/Groq_LLM-2b3138?style=for-the-badge&logoColor=white)
![React](https://img.shields.io/badge/React-2b3138?style=for-the-badge&logo=react&logoColor=61DAFB)
![Docker](https://img.shields.io/badge/Docker-2b3138?style=for-the-badge&logo=docker&logoColor=2496ED)
![Render](https://img.shields.io/badge/Render-2b3138?style=for-the-badge&logo=render&logoColor=46E3B7)

---

## Why this exists

Traditional anti-money-laundering systems bury analysts in false positives while
genuinely sophisticated schemes slip past fixed rules. I wanted to find out
whether a language model could *drive* the investigation — deciding what to check
from a plain-English question — while the actual detection stays deterministic,
so every flagged account is reproducible and defensible to a regulator.

## How It Works

You type an instruction. An LLM agent parses it, builds an execution plan by
**calling a planning function**, and runs only the tools that specific question
needs — nothing more.

```
"Find structuring in the last 30 days"
        │
        ▼
  LLM planner ──► plan: {intent, filters, typologies, tools}
        │            (falls back to a rule-based parser with no API key)
        ▼
  filter ─► features ─► detect (rules + Isolation Forest) ─► risk score ─► explain
        │
        ▼
  Flagged customers · risk band · escalation (monitor / review / report) · reasons
```

The key decision: **the LLM decides *what* to analyse, never *what the answer
is*.** All detection math — feature engineering, typology rules, the anomaly
model, the risk score — is deterministic and auditable. The model can pick the
tools, but it can't invent a number.

## Features

- **Ask in plain English** — the agent reads your intent and decides which
  analyses to run, instead of following a fixed pipeline.
- **Detects the classic laundering typologies** — structuring, smurfing,
  layering, and rapid cash-out.
- **Scores every customer** low / medium / high and recommends an action:
  monitor, review, or file a report.
- **Explains each flag** with the exact figures that triggered it — no black box.
- **Live transaction monitor** and **counterparty link-analysis** graphs for
  spotting funnels and chains.
- **Runs with or without an LLM key** — the deterministic rule engine is the
  automatic fallback.

## Tech Stack

| Layer | Choice | Why |
|---|---|---|
| Backend | FastAPI | Serves the API *and* the built UI from one process; async streaming for the live feed. |
| Detection | scikit-learn + pandas | Isolation Forest + rule detectors kept deterministic so results are auditable. |
| LLM planner | Groq (Llama 3.3), OpenAI-compatible tool-calling | Free, fast inference; used only to plan, never to compute. Swappable via env vars. |
| Frontend | React + TypeScript + Vite | — |
| Charts | Recharts + hand-rolled SVG | The counterparty graph is custom SVG — clearer than a physics blob for funnel/chain shapes. |
| Deploy | Docker (single image) → Render | One container builds the UI and runs the API. |

## Architecture

```
 Browser (React SPA)
        │  REST + Server-Sent Events
        ▼
 FastAPI  ──► AnalysisService (runs one full detection pass at startup, cached)
        │            │
        │            ▼
        │      Agent ──► Planner (LLM tool-call ─┐  or  rule-based fallback)
        │                                        │
        ▼                                        ▼
   /api/*  tools:  EDA · Features · Anomaly (rules + Isolation Forest) · Risk · Explain
```

- **AnalysisService**: runs detection once on boot and caches it, so the
  dashboard, alerts, and broad agent queries are instant.
- **Agent**: turns a query into a plan and executes only the needed tools.
- **Tools**: small, single-responsibility units the agent composes in any order.

One interesting trade-off: the agent **caches the full-dataset analysis** and
reuses it for any query over the whole portfolio, dropping a broad request from
~5 s to ~0.02 s — but a *filtered* query recomputes on its smaller slice, so
scoped questions stay correct rather than served from a stale cache.

A deeper write-up lives in [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

## Getting Started

```bash
git clone https://github.com/PerinbaBuilds/AnomalEye
cd AnomalEye
cp .env.example .env          # add your free Groq key (optional — see below)

pip install -r requirements.txt
cd frontend && npm install && npm run build && cd ..

python -m uvicorn backend.main:app --port 8000   # open http://localhost:8000
```

**Requirements:** Python 3.10+, Node 18+.

**Windows:** `scripts\start.bat` does all of the above in one command;
`scripts\dev.bat` runs it with hot reload.

**The Groq key is optional.** Without it, the agent uses the deterministic
rule-based planner and everything still works offline. With it (free at
<https://console.groq.com/keys>), the Agent Console understands open-ended
queries and writes a natural-language summary.

## Usage

Ask the agent from the command line:

```bash
python -m anomaleye "Find structuring patterns in the last 30 days"
python -m anomaleye "Is customer ID 1528 suspicious?"
python -m anomaleye --demo          # run all the example queries
```

Or open the web app and type in the **AI Agent Console**. Measure detection
quality against the injected ground truth:

```bash
python -m anomaleye.evaluate         # precision / recall / F1
python -m pytest                     # 41 tests
```

## Known Limitations / What I'd Do Differently

- **The dataset is synthetic** — generated with deliberately injected laundering
  typologies (labelled for evaluation), not real transactions.
- **No authentication** — the hosted demo is fully public; I'd add auth and
  per-analyst case ownership before anything real.
- **Risk weights are hand-tuned** in `config.py`, not learned from labelled
  data. A supervised layer on top would likely beat the fixed weights.
- **The LLM only plans.** If Groq is unreachable it silently falls back to
  rules — great for reliability, but the "agentic" feel needs the key.
- **No frontend test coverage yet** — the backend has 41 tests; the React app
  is only type-checked.
- **Free Render instances sleep** after ~15 min idle, so the first request
  cold-starts (~30 s). Not a bug, just the free tier.

## License

[MIT](LICENSE) © Perinba Athiban
