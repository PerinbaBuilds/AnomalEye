# 🦅 AnomalEye — Agentic AI for AML Suspicious-Activity Detection

AnomalEye is an **autonomous, query-driven agent** for Anti-Money-Laundering
(AML) compliance. You give it an instruction in plain English — *"Find
structuring patterns in the last 30 days"* — and it **parses the intent, builds
a dynamic execution plan, invokes only the tools that query needs**, detects
laundering typologies, scores risk, and returns an **explainable** verdict with
a recommended escalation action (`monitor` / `review` / `report`).

It is built to answer the core problem: rule-based AML systems drown analysts in
false positives while sophisticated schemes (structuring, smurfing, layering,
rapid cash-out) slip through. AnomalEye combines **rules + statistics + machine
learning** into a single hybrid engine whose every decision is auditable.

---

## Why this is an *agent*, not a pipeline

The agent does **not** run a fixed sequence. It reads the query, extracts
intent / filters / entities / target typology, and **constructs a plan on the
fly** — running only the necessary tools on the necessary slice of data:

| User query | What the agent decides to do |
|---|---|
| `Analyse this dataset for suspicious activity` | Full pipeline: EDA → features → hybrid detection (rules + ML) → risk → explain |
| `Find structuring patterns in the last 30 days` | Apply 30-day filter → run **only** the structuring detector → skip EDA & ML |
| `Which customers made 10+ transactions under $10,000?` | Pure aggregation rule; **no ML** |
| `Is customer ID 1528 suspicious?` | Single-entity lookup; risk computed on-demand for **that customer only** |
| `Flag high-risk customers` | Full hybrid suite, return **only** the high-risk band |
| `Give me an overview of the data` | EDA / profiling only |

You can see the plan the agent chose in every result under
`execution_summary.tools_invoked` and `planning_rationale`.

---

## Architecture

```
                    ┌─────────────────────────────────────────────┐
   "Find            │                 AGENT                        │
    structuring  ──▶│  Planner  →  Orchestrator                    │
    last 30 days"   │  (intent,     (dynamic plan, selective       │
                    │   filters,     tool invocation)              │
                    │   entities)          │                       │
                    └──────────────────────┼───────────────────────┘
                                           ▼
       ┌───────────┬────────────┬─────────────────┬───────────┬────────────┐
       │  EDA Tool │  Feature   │  Anomaly        │  Risk     │  Explain   │
       │  profiling│  Engineering│  Detection      │  Classify │  Layer     │
       │           │  (AML feats)│  rules+stats+ML │  score→band│  NL reasons│
       └───────────┴────────────┴─────────────────┴───────────┴────────────┘
```

| Component | Module | Responsibility |
|---|---|---|
| **Planner** | `anomaleye/agent/planner.py` | NL → intent, filters, entities, typologies, tool plan |
| **Orchestrator** | `anomaleye/agent/orchestrator.py` | Executes the plan, invokes only needed tools, assembles output |
| **EDA Tool** | `anomaleye/tools/eda.py` | Profiling, amount distribution, CTR-band concentration |
| **Feature Engineering** | `anomaleye/tools/features.py` | Rolling sums, velocity, amount deviation, CTR proximity, counterparty concentration |
| **Anomaly Detection** | `anomaleye/tools/anomaly.py` | Rule typology detectors + Isolation Forest (hybrid) |
| **Risk Classification** | `anomaleye/tools/risk.py` | Weighted blend → low/medium/high → escalation |
| **Explanation Layer** | `anomaleye/tools/explain.py` | Deterministic, evidence-quoting natural-language reasons |

---

## Detection methodology (hybrid)

**Rule + statistical typology detectors** (each emits structured *evidence*):

- **Structuring** — ≥3 cash transactions in the `$9,000–$9,999` band within 30
  days (staying under the `$10,000` CTR reporting line).
- **Smurfing** — ≥6 distinct counterparties sending *small* inbound transfers
  that aggregate above `$10,000` within 7 days (funnel account).
- **Rapid cash-out** — a large credit ≥80% drained by withdrawals within 72h
  (placement → removal).
- **Layering** — value bounced through ≥3 accounts in ≤48h with near-constant
  amounts; **every account in the chain is flagged**.
- **Velocity spike** — 24h transaction burst that is a ≥3σ population outlier.
- **High-risk geography** — exposure to FATF-flagged jurisdictions (amplifier).

**Machine learning:** an unsupervised **Isolation Forest** over a 13-dimensional
per-customer behavioural fingerprint catches anomalies the rules don't encode.

**Risk score:** an auditable weighted blend of the strongest signal per type,
capped at 100, mapped to `low < 40 ≤ medium < 70 ≤ high`. All weights and
thresholds live in one file — `anomaleye/config.py`.

### Measured performance

Because the synthetic generator labels every injected laundering transaction,
detection quality is measured honestly (`python -m anomaleye.evaluate`):

| Metric (customer-level, ≥ medium risk) | Value |
|---|---|
| Precision | **0.77** |
| Recall | **0.91** |
| F1 | **0.84** |

Per-typology recall: structuring **1.0**, smurfing **1.0**, rapid cash-out
**1.0**, layering **0.8**.

---

## Quick start

```bash
# 1. Install
pip install -r requirements.txt

# 2. Generate the synthetic dataset (auto-runs on first use anyway)
python -m anomaleye.data.generate

# 3. Ask the agent something (CLI)
python -m anomaleye "Analyse this dataset for suspicious activity"
python -m anomaleye "Find structuring patterns in the last 30 days"
python -m anomaleye "Is customer ID 1528 suspicious?"

# Run all the example queries at once
python -m anomaleye --demo

# Machine-readable output
python -m anomaleye "Flag high-risk customers" --json

# 4. Interactive dashboard
streamlit run app.py
```

### Example CLI output

```
▸ Execution plan (what the agent decided)
    intent            : single_entity
    customer          : 1528
    tools invoked     : filter -> features -> detect_typologies -> classify -> explain
    transactions used : 47

▸ Top flagged entities
  [MEDIUM] Customer 1528 — score 48.8/100 — action: REVIEW
      • Made 8 cash transactions between $9,000 and $10,000 within 30 days
        (total $76,910.13) — consistent with structuring to stay under the
        $10,000 CTR reporting line.
      • A credit of $111,024.41 was 94% drained ($104,500.90) within 72 hours
        — placement followed by rapid removal of funds.
      → Route to a compliance analyst for manual review before any filing decision.
```

---

## Output format

Every run returns a structured, judge-friendly result:

```jsonc
{
  "execution_summary": {
    "user_query": "...",
    "detected_intent": "find_pattern",
    "detected_filters": { "date_from": "...", "date_to": "..." },
    "detected_typologies": ["structuring"],
    "tools_invoked": ["filter", "features", "detect_typologies", "classify", "explain"],
    "planning_rationale": ["Detected a pattern-specific query ..."],
    "transactions_in_scope": 9924
  },
  "flagged_entities": [
    { "customer_id": 1070, "risk_score": 45.0, "risk_level": "medium",
      "escalation": "review", "typologies": ["structuring"],
      "score_breakdown": { "structuring": 30.0 } }
  ],
  "explanations": [ { "summary": "...", "reasons": ["..."],
                      "escalation_rationale": "..." } ],
  "counts": { "total_flagged": 3, "high": 0, "medium": 3, "low": 0 }
}
```

---

## Using your own data

Point the loader at your CSVs:

```bash
python -m anomaleye "Flag high-risk customers" \
    --transactions path/to/transactions.csv \
    --customers path/to/customers.csv
```

**Required transaction columns:** `transaction_id, customer_id, timestamp,
amount, type`. Optional but recommended: `channel, counterparty_id,
counterparty_country`. Any `is_laundering` / `typology` columns are treated as
held-out ground truth and never shown to the detectors.

---

## Project layout

```
anomaleye/
├── config.py              # all thresholds & weights (single source of truth)
├── cli.py                 # command-line interface
├── evaluate.py            # precision/recall vs injected ground truth
├── data/
│   ├── generate.py        # synthetic dataset w/ injected typologies
│   └── loader.py          # validation + ground-truth separation
├── agent/
│   ├── planner.py         # NL → execution plan
│   └── orchestrator.py    # dynamic tool invocation
└── tools/
    ├── eda.py  features.py  anomaly.py  risk.py  explain.py
app.py                     # Streamlit dashboard
tests/                     # 27 tests (planner, detectors, agent, eval quality)
```

---

## Tests

```bash
python -m pytest
```

27 tests cover query planning, each typology detector, risk banding /
escalation, end-to-end agent behaviour, and a detection-quality regression
gate.

---

## Design principles

- **Explainable by construction** — no black-box scoring; every flag quotes the
  exact numbers that triggered it, and the risk score breaks down by signal.
- **Auditable thresholds** — all business logic in `config.py`, each constant
  documented with its regulatory rationale.
- **Deterministic & offline** — no external API key required; the same query
  always yields the same, reproducible plan and verdict.
- **Ground-truth honest** — the generator labels its injected schemes so
  detection quality is measured, not asserted.
