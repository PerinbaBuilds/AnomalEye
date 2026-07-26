"""Query planner — natural language in, execution plan out.

This is the "brain" of the agent. It parses a free-text instruction and
extracts:

* **intent**       — what the user is fundamentally asking for
* **filters**      — date range, country, segment, transaction type, amount
* **entities**     — a specific customer id, if any
* **typologies**   — the AML pattern(s) of interest
* **plan**         — the ordered list of tools to invoke for *this* query

Crucially, the plan is *dynamic*: a single-entity lookup skips EDA and ML; a
threshold question runs a pure aggregation rule; "find structuring" runs only
the structuring detector. Not every query touches every tool.

The parser is deterministic (regex + keyword rules) so it needs no API key and
its decisions are fully reproducible and auditable. An optional LLM backend can
be layered on top later without changing the plan contract.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

# Canonical typology vocabulary and the phrases that map to each.
TYPOLOGY_SYNONYMS = {
    "structuring": ["structuring", "structure", "just under", "sub-threshold",
                    "below the threshold", "below the ctr", "avoid reporting",
                    "avoid the report", "ctr avoid"],
    "smurfing": ["smurfing", "smurf", "funnel account", "many small deposits",
                 "mule", "multiple senders"],
    "rapid_cashout": ["rapid cash", "cash out", "cash-out", "cashout",
                      "quick withdrawal", "drain", "placement"],
    "layering": ["layering", "layer", "chain of transfers", "pass through",
                 "pass-through", "hops"],
    "velocity_spike": ["velocity", "burst", "spike", "sudden activity",
                       "rapid transactions"],
    "high_risk_geography": ["high risk country", "high-risk country",
                           "sanctioned", "fatf", "offshore", "geography"],
}

INTENTS = {
    "single_entity",       # "is customer 4521 suspicious?"
    "threshold_query",     # "customers with 10+ txns under $10k"
    "find_pattern",        # "find structuring in the last 30 days"
    "high_risk_customers", # "flag high-risk customers"
    "eda",                 # "give me an overview of the data"
    "full_analysis",       # "analyse this dataset for suspicious activity"
}


@dataclass
class Filters:
    date_from: Optional[str] = None
    date_to: Optional[str] = None
    country: Optional[str] = None
    segment: Optional[str] = None
    txn_type: Optional[str] = None
    amount_min: Optional[float] = None
    amount_max: Optional[float] = None
    min_txn_count: Optional[int] = None

    def is_empty(self) -> bool:
        return all(v is None for v in asdict(self).values())

    def to_dict(self) -> dict[str, Any]:
        return {k: v for k, v in asdict(self).items() if v is not None}


@dataclass
class QueryPlan:
    query: str
    intent: str
    filters: Filters = field(default_factory=Filters)
    customer_id: Optional[int] = None
    typologies: list[str] = field(default_factory=list)
    tools: list[str] = field(default_factory=list)
    rationale: list[str] = field(default_factory=list)
    planner: str = "rules"  # "rules" or "llm"

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["filters"] = {k: v for k, v in d["filters"].items() if v is not None}
        return d


# --------------------------------------------------------------------------
# Extraction helpers
# --------------------------------------------------------------------------
def _extract_customer_id(q: str) -> Optional[int]:
    m = re.search(
        r"(?:customer|client|account|entity|cust)\s*(?:id|#|number|no\.?)?\s*"
        r"[:#]?\s*(\d{2,})",
        q,
        flags=re.IGNORECASE,
    )
    if m:
        return int(m.group(1))
    # "is 4521 suspicious" style.
    m = re.search(r"\bid\s*[:#]?\s*(\d{3,})", q, flags=re.IGNORECASE)
    return int(m.group(1)) if m else None


def _extract_date_range(q: str, today: datetime) -> tuple[Optional[str], Optional[str]]:
    q = q.lower()
    m = re.search(r"last\s+(\d+)\s*(day|week|month|year)s?", q)
    if m:
        n, unit = int(m.group(1)), m.group(2)
        delta = {
            "day": timedelta(days=n),
            "week": timedelta(weeks=n),
            "month": timedelta(days=30 * n),
            "year": timedelta(days=365 * n),
        }[unit]
        return (today - delta).isoformat(), today.isoformat()

    words = {"a": 1, "one": 1, "two": 2, "three": 3, "six": 6}
    m = re.search(r"(?:past|last)\s+(a|one|two|three|six)?\s*(week|month|year)", q)
    if m:
        n = words.get(m.group(1) or "one", 1)
        unit = m.group(2)
        delta = {
            "week": timedelta(weeks=n),
            "month": timedelta(days=30 * n),
            "year": timedelta(days=365 * n),
        }[unit]
        return (today - delta).isoformat(), today.isoformat()

    # Explicit ISO range: "between 2024-01-01 and 2024-02-01".
    m = re.search(r"(\d{4}-\d{2}-\d{2}).{1,10}?(\d{4}-\d{2}-\d{2})", q)
    if m:
        return m.group(1), m.group(2)
    return None, None


def _extract_amounts(q: str) -> tuple[Optional[float], Optional[float]]:
    ql = q.lower()
    amt_min = amt_max = None

    def parse_money(s: str) -> float:
        s = s.replace(",", "").replace("$", "").strip().lower()
        mult = 1.0
        if s.endswith("k"):
            mult, s = 1_000.0, s[:-1]
        elif s.endswith("m"):
            mult, s = 1_000_000.0, s[:-1]
        return float(s) * mult

    for m in re.finditer(
        r"(under|below|less than|<|over|above|more than|greater than|>|at least)\s*"
        r"\$?\s*([\d,]+(?:\.\d+)?\s*[km]?)",
        ql,
    ):
        op, val = m.group(1), parse_money(m.group(2))
        if op in {"under", "below", "less than", "<"}:
            amt_max = val
        else:
            amt_min = val
    return amt_min, amt_max


def _extract_count(q: str) -> Optional[int]:
    m = re.search(r"(\d+)\s*\+", q)  # "10+"
    if m:
        return int(m.group(1))
    m = re.search(
        r"(?:more than|over|at least|>=?)\s*(\d+)\s*(?:transaction|txn|deposit|"
        r"transfer|payment)",
        q.lower(),
    )
    return int(m.group(1)) if m else None


def _extract_country(q: str) -> Optional[str]:
    m = re.search(r"\b(?:in|from|country)\s+([A-Z]{2})\b", q)
    if m:
        return m.group(1).upper()
    return None


def _extract_segment(q: str) -> Optional[str]:
    for seg in ("retail", "sme", "corporate", "private wealth", "private_wealth"):
        if seg in q.lower():
            return seg.replace(" ", "_")
    return None


def _extract_txn_type(q: str) -> Optional[str]:
    ql = q.lower()
    for t in ("deposit", "withdrawal", "transfer", "payment", "cash"):
        if re.search(rf"\b{t}s?\b", ql):
            return t
    return None


def _extract_typologies(q: str) -> list[str]:
    ql = q.lower()
    found = []
    for typ, syns in TYPOLOGY_SYNONYMS.items():
        if any(s in ql for s in syns):
            found.append(typ)
    return found


# --------------------------------------------------------------------------
# Main entry point
# --------------------------------------------------------------------------
def plan_query(query: str, today: Optional[datetime] = None) -> QueryPlan:
    """Parse ``query`` into a :class:`QueryPlan` with a dynamic tool list."""
    today = today or datetime.now(timezone.utc).replace(tzinfo=None)
    ql = query.lower().strip()

    customer_id = _extract_customer_id(query)
    date_from, date_to = _extract_date_range(query, today)
    amt_min, amt_max = _extract_amounts(query)
    count = _extract_count(query)
    typologies = _extract_typologies(query)

    filters = Filters(
        date_from=date_from,
        date_to=date_to,
        country=_extract_country(query),
        segment=_extract_segment(query),
        txn_type=_extract_txn_type(query),
        amount_min=amt_min,
        amount_max=amt_max,
        min_txn_count=count,
    )

    rationale: list[str] = []
    tools: list[str] = []

    # --- Intent resolution (order matters: most specific first) ----------
    is_eda = any(
        w in ql
        for w in ("overview", "profile", "explore", "eda", "summarise",
                  "summarize", "baseline", "describe the data", "distribution")
    )
    is_threshold = (
        count is not None
        and any(w in ql for w in ("which", "list", "who", "how many", "find",
                                  "show", "customers", "made"))
        and not typologies
    )

    if customer_id is not None:
        intent = "single_entity"
        rationale.append(
            f"Detected a single-entity lookup for customer {customer_id}; "
            f"will compute risk on-demand for that customer only and skip "
            f"population EDA / ML."
        )
        tools = ["filter", "features", "detect_typologies", "classify",
                 "explain"]

    elif is_threshold:
        intent = "threshold_query"
        rationale.append(
            f"Detected a threshold/aggregation question "
            f"(>= {count} transactions"
            + (f", amount < ${amt_max:,.0f}" if amt_max else "")
            + (f", amount > ${amt_min:,.0f}" if amt_min else "")
            + "). Running a direct aggregation rule; ML anomaly detection is "
            "not required."
        )
        tools = ["filter", "aggregate_threshold", "classify", "explain"]

    elif typologies:
        intent = "find_pattern"
        rationale.append(
            f"Detected a pattern-specific query for: {', '.join(typologies)}. "
            f"Invoking only the matching detector(s); skipping full EDA."
        )
        tools = ["filter", "features", "detect_typologies", "classify",
                 "explain"]
        if "velocity_spike" in typologies or "high_risk_geography" in typologies:
            pass  # handled inside detect_typologies

    elif "high-risk" in ql or "high risk" in ql or (
        "flag" in ql and "customer" in ql
    ):
        intent = "high_risk_customers"
        rationale.append(
            "Detected a request to surface high-risk customers. Running the "
            "full hybrid detection suite (rules + ML) and returning only "
            "entities in the high-risk band."
        )
        tools = ["filter", "features", "detect_typologies", "ml_anomaly",
                 "classify", "explain"]

    elif is_eda:
        intent = "eda"
        rationale.append(
            "Detected an exploratory request. Running the EDA/profiling tool "
            "and a structuring scan; detection tools are optional."
        )
        tools = ["filter", "eda"]

    else:
        intent = "full_analysis"
        rationale.append(
            "General 'analyse for suspicious activity' request. Running the "
            "full agentic pipeline: EDA -> features -> hybrid detection "
            "(rules + ML) -> risk classification -> explanation."
        )
        tools = ["filter", "eda", "features", "detect_typologies",
                 "ml_anomaly", "classify", "explain"]

    if not filters.is_empty() and "filter" in tools:
        applied = filters.to_dict()
        rationale.append(f"Applying data filters before analysis: {applied}.")

    return QueryPlan(
        query=query,
        intent=intent,
        filters=filters,
        customer_id=customer_id,
        typologies=typologies,
        tools=tools,
        rationale=rationale,
    )
