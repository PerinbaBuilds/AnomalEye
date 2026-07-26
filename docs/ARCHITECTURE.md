# AnomalEye — Architecture & Design Notes

This document explains *how* the agent works and *why* the design choices were
made, for reviewers who want to go beyond the README.

## 1. The agentic loop

```
query ──▶ Planner.plan_query() ──▶ QueryPlan ──▶ Orchestrator._execute() ──▶ result
```

### Planner (`agent/planner.py`)

The planner is a **deterministic natural-language understanding layer**. It uses
regex + keyword rules (no external LLM) to extract:

- **intent** — one of `single_entity`, `threshold_query`, `find_pattern`,
  `high_risk_customers`, `eda`, `full_analysis`.
- **filters** — date range (relative *and* absolute), country, segment,
  transaction type, amount bounds, minimum transaction count.
- **entities** — a specific `customer_id`.
- **typologies** — the AML pattern(s) named or implied.
- **tools** — the ordered list of tool handlers to invoke for *this* query.

Determinism matters in compliance: the same instruction must always yield the
same plan and the same verdict, and every decision must be explainable to an
auditor. An LLM backend could be layered on top later without changing the
`QueryPlan` contract the orchestrator depends on.

**Relative dates** (`"last 30 days"`) are resolved against the *dataset's* most
recent timestamp, not the wall clock, so historical datasets analyse correctly.

### Orchestrator (`agent/orchestrator.py`)

The orchestrator walks `plan.tools` and dispatches to `_tool_<name>` handlers,
threading a shared `ctx` dict between them. Because the tool list comes from the
plan, **no two queries necessarily run the same tools** — a single-entity lookup
never touches the Isolation Forest; a threshold question never runs a detector.

Each handler is small and independent, so tools compose freely:

| Handler | Reads from ctx | Writes to ctx |
|---|---|---|
| `_tool_filter` | dataset | `scope` |
| `_tool_eda` | `scope` | `eda` |
| `_tool_features` | `scope` | `customer_features` |
| `_tool_detect_typologies` | `scope`, `customer_features` | `findings` |
| `_tool_ml_anomaly` | `customer_features` | `findings`, scored features |
| `_tool_aggregate_threshold` | `scope` | `findings`, `threshold_matched` |
| `_tool_classify` | `findings` | `assessments` |
| `_tool_explain` | `assessments` | `explanations` |

## 2. Feature engineering (`tools/features.py`)

Two granularities:

- **Transaction-level:** CTR proximity, "just under CTR" flag, robust amount
  deviation (MAD z-score vs the customer's own history), time-since-previous
  (velocity), rolling 24h count and rolling 7d sum (time-windowed via pandas
  `rolling` on a datetime index).
- **Customer-level fingerprint:** 13 aggregates (volume, dispersion, CTR-band
  counts, rapid follow-ups, 24h burst max, counterparty concentration, inbound
  counterparty count) — the vector the ML model consumes.

## 3. Detection (`tools/anomaly.py`)

A **hybrid** of three paradigms:

1. **Rules** encode the regulator-recognised typologies with explicit windows
   and thresholds. Each detector returns *findings* carrying the evidence that
   triggered it — this is what makes explanations possible.
2. **Statistics** — the velocity detector flags population outliers via z-score;
   amount deviation uses a robust MAD estimator.
3. **Machine learning** — an unsupervised Isolation Forest over the standardised
   customer fingerprint catches anomalies the rules don't encode, with a
   normalised `[0,1]` anomaly score and surfaced outlier features.

A `Finding` is a plain dict (`customer_id`, `typology`, `weight_key`,
`severity`, `evidence`, `transaction_ids`) so every layer downstream stays
decoupled and testable.

## 4. Risk classification (`tools/risk.py`)

For each entity, the strongest finding per signal type is kept, multiplied by
its configured weight, and summed (capped at 100). A high-confidence "hard"
typology (structuring / smurfing / layering / rapid cash-out) floors the score
into at least the medium band so a single strong signal is never diluted to
silence by absent ones. Bands: `low < 40 ≤ medium < 70 ≤ high`.

Escalation mapping:

- **report** — high risk, or high + a reportable typology → recommend SAR.
- **review** — medium, or any reportable typology present → analyst review.
- **monitor** — low → routine monitoring.

## 5. Explanation (`tools/explain.py`)

Deterministic templates turn each finding's evidence into a specific sentence
that quotes the actual numbers (e.g. *"8 cash transactions between $9,000 and
$10,000 within 30 days"*). No free-form generation means explanations are
reproducible and can be tied back to the exact rule and data that fired.

## 6. Evaluation (`evaluate.py`)

The synthetic generator tags every injected laundering transaction, so the
detector is scored honestly: customer-level precision / recall / F1 plus a
per-typology recall breakdown. This doubles as a regression gate in the test
suite (`tests/test_agent.py::test_detection_quality_meets_baseline`).

## 7. Extending

- **New typology:** add a detector to `tools/anomaly.py`, register it in
  `TYPOLOGY_DETECTORS`, add a weight in `config.Weights`, add an explanation
  branch in `tools/explain.py`, and (optionally) synonyms in the planner.
- **New intent:** add a branch in `planner.plan_query` and, if needed, a
  `_tool_*` handler in the orchestrator.
- **Real data:** pass `--transactions/--customers`; the loader validates
  required columns and strips any ground-truth columns before detection.
