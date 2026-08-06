# AnomalEye — Architecture

A detailed tour of how the system is built and why, for reviewers who want to go
beyond the README.

---

## 1. High-level shape

```
┌──────────────────────────── Frontend (React + TS + Vite) ────────────────────────────┐
│  Dashboard · AI Agent Console · Alert Queue · Live Monitor · Link Analysis ·          │
│  Entity 360 · Model Performance · Methodology                                         │
└───────────────────────────────────────────┬───────────────────────────────────────────┘
                                             │  REST + Server-Sent Events (JSON)
┌───────────────────────────────────────────▼───────────────────────────────────────────┐
│  Backend (FastAPI)                                                                     │
│    AnalysisService — one cached full-detection pass, shared by every read endpoint     │
│    Agent           — plans a query and executes only the tools it needs                │
└───────────────────────────────────────────┬───────────────────────────────────────────┘
                                             │
┌───────────────────────────────────────────▼───────────────────────────────────────────┐
│  Engine (pure Python, importable, tested)                                              │
│    Planner (LLM tool-call ─or─ rule-based)  →  EDA · Features · Anomaly · Risk · Explain│
│    Data: synthetic generator + loader (ground-truth labels held out)                   │
└────────────────────────────────────────────────────────────────────────────────────────┘
```

Three layers, cleanly separated: a **pure-Python engine** that knows nothing
about HTTP, a **FastAPI service** that caches and exposes it, and a **React
console**. The engine is independently usable from the CLI and the test suite.

---

## 2. The agentic loop

```
query ─► Agent._plan() ─► QueryPlan ─► Agent._execute() ─► structured result
```

### 2.1 Planner — LLM with rule-based fallback

`Agent._plan()` chooses a planner at call time:

- **LLM planner** (`anomaleye/agent/llm_planner.py`) — active when a
  `GROQ_API_KEY` is present. It sends the query to an OpenAI-compatible
  chat-completions endpoint (Groq by default) and **forces a tool call** to
  `submit_execution_plan`, whose typed arguments become the plan: intent,
  filters, target typologies, entity id, the ordered tool list, and a rationale.
  A second, best-effort call produces a natural-language narrative of the
  results.
- **Rule-based planner** (`anomaleye/agent/planner.py`) — a deterministic
  regex/keyword parser. It is the fallback whenever there is no key **or** the
  LLM call fails/times out (`LLMUnavailable` is caught and swallowed).

Either way the output is the same `QueryPlan` dataclass, so the orchestrator is
planner-agnostic. The result's `execution_summary.planner` field records which
one ran.

**Why keep both?** Compliance needs determinism and offline operation; an LLM
adds open-ended language understanding. The fallback guarantees the product
*always* runs and never hard-depends on an external API.

**Guard rails.** LLM output is sanitised (`_sanitize_tools`) into an executable
pipeline: `filter` is forced first, `classify`/`explain` are added whenever a
detector runs, `features` is ensured before ML, and `ml_anomaly` is stripped
from single-entity plans. A hallucinated or partial tool list can't produce a
broken run.

### 2.2 Orchestrator

`Agent._execute()` walks `plan.tools` and dispatches to `_tool_<name>` handlers,
threading a shared `ctx` dict between them. Because the tool list comes from the
plan, **no two queries necessarily run the same tools**:

| Query | Tools invoked |
|---|---|
| "Is customer 1528 suspicious?" | filter → features → detect_typologies → classify → explain |
| "Customers with 10+ txns under $10k" | filter → aggregate_threshold → classify → explain |
| "Find structuring last 30 days" | filter → features → detect_typologies → classify → explain |
| "Flag high-risk customers" | filter → features → detect_typologies → ml_anomaly → classify → explain |
| "Give me an overview" | filter → eda |

Relative dates ("last 30 days") resolve against the **dataset's newest
timestamp**, not the wall clock, so historical data analyses correctly.

### 2.3 Full-scope caching

The expensive parts — rolling-window features on 40k rows and the Isolation
Forest — are computed once for the full dataset and cached on the `Agent`
(`self._cache`). The backend **warms this cache at startup** from the same
analysis `AnalysisService` already runs, so the first broad query is instant
(~0.02 s instead of ~5 s). A *filtered* query (smaller scope) is recomputed on
its slice, so scoped answers are never served stale.

---

## 3. Feature engineering (`tools/features.py`)

Two granularities:

- **Transaction-level:** CTR proximity, a "just under CTR" flag, robust amount
  deviation (MAD z-score vs the customer's own history), time-since-previous
  (velocity), and time-windowed rolling 24h count / 7d sum (pandas `rolling` on
  a datetime index).
- **Customer fingerprint:** 13 aggregates (volume, dispersion, CTR-band counts,
  rapid follow-ups, 24h burst max, counterparty concentration, distinct inbound
  counterparties) — the vector the ML model consumes.

---

## 4. Detection (`tools/anomaly.py`) — hybrid

Three paradigms, each detector returning structured *findings* that carry the
evidence that fired them (this is what makes explanation possible).

| Typology | Rule |
|---|---|
| **structuring** | ≥3 cash transactions in `$9,000–$9,999` within 30 days (sliding window). |
| **smurfing** | ≥6 distinct *small* (<$5k) inbound counterparties aggregating >$10k within 7 days. |
| **rapid_cashout** | a credit ≥$20k with ≥80% withdrawn within 72h. |
| **layering** | ≥3 account hops in ≤48h with amounts within ±15%; every account in the chain is flagged. |
| **velocity_spike** | 24h transaction count ≥3σ above the population mean. |
| **high_risk_geography** | exposure to FATF-flagged jurisdictions (amplifier only). |

Plus an unsupervised **Isolation Forest** (`ml_anomaly`) over the standardised
customer fingerprint, contamination 5%, producing a normalised `[0,1]` anomaly
score and surfacing the features that most exceed the population.

A `Finding` is a plain dict: `customer_id`, `typology`, `weight_key`,
`severity`, `evidence`, `transaction_ids`.

---

## 5. Risk classification (`tools/risk.py`)

For each entity, the strongest finding per signal type is kept, multiplied by its
configured weight, and summed (capped at 100):

```
score = min(100, Σ  weight[k] · severity[strongest finding of type k])
```

A high-confidence hard typology (structuring / smurfing / layering /
rapid_cashout) floors the score into at least the medium band, so a single
strong signal is never diluted to silence by absent ones.

Bands: `low < 40 ≤ medium < 70 ≤ high`. Escalation: **report** (high, or high +
a reportable typology → recommend a SAR), **review** (medium, or any reportable
typology), **monitor** (low). Every weight and threshold lives in
`anomaleye/config.py`, each documented with its rationale, and is surfaced in the
Methodology view.

---

## 6. Explanation (`tools/explain.py`)

Deterministic templates turn each finding's evidence into a specific sentence
that quotes the actual numbers ("8 cash transactions between $9,000 and $10,000
within 30 days"). No free-form generation, so explanations are reproducible and
trace back to the exact rule and data that fired. (The optional LLM narrative in
the Agent Console is separate and clearly labelled as generated.)

---

## 7. Backend service & API (`backend/`)

`AnalysisService` runs one full hybrid pass at startup and caches findings,
assessments, scored features, and per-typology results; it also warms the
`Agent` cache. Selected endpoints:

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/overview` | KPIs, risk/typology distributions, amount histogram |
| GET | `/api/customer-breakdown` | customer/transaction segmentation for the dashboard |
| GET | `/api/timeline` | flagged-vs-total volume over time |
| POST | `/api/agent/query` | run a natural-language agent query |
| GET | `/api/alerts` | filtered alert queue (level / typology / escalation) |
| GET | `/api/customers/{id}` | Entity 360 (profile, assessment, timeline, network) |
| GET | `/api/customers/{id}/network` | counterparty link graph |
| GET | `/api/layering-chains` | discovered layering paths |
| GET | `/api/performance` | precision / recall / F1 vs ground truth |
| GET | `/api/methodology` | thresholds, weights, risk bands |
| GET | `/api/stream/transactions` | SSE live scoring feed |
| GET | `/api/dataset.xlsx` | download the full labelled dataset |

The **live feed** deliberately over-samples flagged transactions (~40%) so the
monitor shows a believable high/medium/low mix rather than the ~0.5% base rate.

FastAPI also serves the built React bundle and falls back to `index.html` for
client-side routes, so the whole product is one process behind one port.

---

## 8. Frontend (`frontend/`)

React + TypeScript + Vite + Tailwind. A typed API client (`src/api`) mirrors the
backend responses (`src/types.ts`); a small `useFetch` hook handles
loading/error state. Charts use Recharts; the counterparty **link chart** is a
dependency-free custom SVG with a deterministic radial layout. The design system
(dark, bank-grade, red accent) lives in `tailwind.config.js` + `index.css`.
Route-level pages compose the analyst console.

---

## 9. Data (`anomaleye/data/`)

`generate.py` builds a customer + transaction dataset with **known** injected
typologies, each transaction tagged with hidden `is_laundering` / `typology`
labels. `loader.py` strips those labels before detection ever sees them and
keeps them aside for evaluation, so `evaluate.py` can score precision/recall/F1
honestly. The committed CSVs (and the exported Excel workbook) make the whole
thing reproducible and inspectable.

---

## 10. Deployment

A single multi-stage `Dockerfile` builds the frontend, then runs FastAPI serving
both the API and the static bundle on the platform-provided `$PORT`. CI
(`.github/workflows/ci.yml`) runs the backend test suite and the frontend
type-check + build on every push. See [`DEPLOYMENT.md`](DEPLOYMENT.md).

---

## 11. Extending

- **New typology:** add a detector in `tools/anomaly.py`, register it in
  `TYPOLOGY_DETECTORS`, add a weight in `config.Weights`, add an explanation
  branch in `tools/explain.py`, and (optionally) synonyms/enum entries in both
  planners.
- **New intent:** add a branch in the rule planner + an enum value in the LLM
  planner, and a `_tool_*` handler in the orchestrator if a new tool is needed.
- **Different LLM provider:** point `LLM_BASE_URL` / `LLM_MODEL` at any
  OpenAI-compatible endpoint; no code change.
- **Real data:** pass `--transactions/--customers`; the loader validates the
  required columns and strips any ground-truth columns before detection.
