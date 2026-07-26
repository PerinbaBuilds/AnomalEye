"""LLM-backed planner — real tool-calling over an OpenAI-compatible API.

By default this targets **Groq** (``https://api.groq.com/openai/v1``), whose API
is OpenAI-compatible and has a generous free tier serving open models
(Llama etc.). It works with any OpenAI-style chat-completions endpoint, so you
can point the env vars at another provider. The model is asked to *call a
function* that returns a structured execution plan — so this is genuine
tool-calling, not string matching — and a second call turns the results into a
narrative.

Design guarantees
-----------------
* The LLM only decides **intent, filters, entities, typologies and which tools
  to run**. It never computes a risk score or a transaction count — the
  deterministic engine does all detection math, so every number stays
  auditable and reproducible.
* Everything is best-effort: any error (no key, timeout, bad JSON, HTTP error)
  raises :class:`LLMUnavailable`, and the orchestrator falls back to the
  deterministic planner. The product always runs, with or without a key.

Configuration (environment variables)
-------------------------------------
* ``GROQ_API_KEY`` (or ``LLM_API_KEY``) — required to enable. Get a free key at
  https://console.groq.com/keys.
* ``LLM_BASE_URL``  — default ``https://api.groq.com/openai/v1``.
* ``LLM_MODEL``     — default ``llama-3.3-70b-versatile`` (supports tool use).
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from typing import Any, Optional

from anomaleye.agent.planner import Filters, QueryPlan

# Load a local .env (if python-dotenv is installed) so GROQ_API_KEY can live in
# a gitignored file rather than being exported by hand each session.
try:  # pragma: no cover - trivial
    from dotenv import load_dotenv

    load_dotenv()
except Exception:  # dotenv is optional
    pass

# Canonical tool ordering the orchestrator understands.
VALID_TOOLS = [
    "filter",
    "eda",
    "features",
    "detect_typologies",
    "ml_anomaly",
    "aggregate_threshold",
    "classify",
    "explain",
]
VALID_INTENTS = [
    "single_entity",
    "threshold_query",
    "find_pattern",
    "high_risk_customers",
    "eda",
    "full_analysis",
]
VALID_TYPOLOGIES = [
    "structuring",
    "smurfing",
    "rapid_cashout",
    "layering",
    "velocity_spike",
    "high_risk_geography",
]

DEFAULT_BASE_URL = "https://api.groq.com/openai/v1"
DEFAULT_MODEL = "llama-3.3-70b-versatile"


class LLMUnavailable(RuntimeError):
    """Raised when the LLM path cannot be used; triggers rule-based fallback."""


def _api_key() -> Optional[str]:
    for var in ("GROQ_API_KEY", "LLM_API_KEY"):
        val = os.environ.get(var)
        if val:
            return val
    return None


def llm_enabled() -> bool:
    return _api_key() is not None


def model_name() -> str:
    return os.environ.get("LLM_MODEL", DEFAULT_MODEL)


def _base_url() -> str:
    return os.environ.get("LLM_BASE_URL", DEFAULT_BASE_URL).rstrip("/")


def _chat(messages: list[dict], tools: Optional[list] = None,
          tool_choice: Any = None, temperature: float = 0.0) -> dict:
    """POST to the OpenAI-compatible chat-completions endpoint."""
    import httpx

    key = _api_key()
    if not key:
        raise LLMUnavailable("no LLM API key configured")

    payload: dict[str, Any] = {
        "model": model_name(),
        "messages": messages,
        "temperature": temperature,
    }
    if tools:
        payload["tools"] = tools
    if tool_choice:
        payload["tool_choice"] = tool_choice

    try:
        with httpx.Client(timeout=45.0) as client:
            resp = client.post(
                f"{_base_url()}/chat/completions",
                headers={"Authorization": f"Bearer {key}"},
                json=payload,
            )
        if resp.status_code != 200:
            raise LLMUnavailable(
                f"LLM HTTP {resp.status_code}: {resp.text[:200]}"
            )
        return resp.json()
    except LLMUnavailable:
        raise
    except Exception as e:  # network, timeout, json, ...
        raise LLMUnavailable(f"LLM request failed: {e}") from e


# --------------------------------------------------------------------------
# Planning
# --------------------------------------------------------------------------
_PLAN_TOOL = {
    "type": "function",
    "function": {
        "name": "submit_execution_plan",
        "description": (
            "Submit the analysis plan for an AML query: the intent, any data "
            "filters/entities, target laundering typologies, and the exact "
            "ordered list of engine tools to run. Invoke ONLY the tools the "
            "query needs — do not run everything for a targeted question."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "intent": {"type": "string", "enum": VALID_INTENTS},
                "customer_id": {
                    "type": ["integer", "null"],
                    "description": "A single customer id if the query is about "
                    "one specific entity, else null.",
                },
                "filters": {
                    "type": "object",
                    "properties": {
                        "date_from": {"type": ["string", "null"],
                                     "description": "ISO date"},
                        "date_to": {"type": ["string", "null"],
                                   "description": "ISO date"},
                        "country": {"type": ["string", "null"],
                                   "description": "ISO-2 country code"},
                        "segment": {"type": ["string", "null"]},
                        "txn_type": {"type": ["string", "null"]},
                        "amount_min": {"type": ["number", "null"]},
                        "amount_max": {"type": ["number", "null"]},
                        "min_txn_count": {"type": ["integer", "null"]},
                    },
                },
                "typologies": {
                    "type": "array",
                    "items": {"type": "string", "enum": VALID_TYPOLOGIES},
                },
                "tools": {
                    "type": "array",
                    "items": {"type": "string", "enum": VALID_TOOLS},
                },
                "rationale": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Short human-readable reasons for the plan.",
                },
            },
            "required": ["intent", "tools", "rationale"],
        },
    },
}


def _system_prompt(today: datetime, data_start: str, data_end: str) -> str:
    return (
        "You are the planning brain of an AML (anti-money-laundering) "
        "detection agent. Parse the user's natural-language query and decide "
        "how to analyse a transaction dataset by calling "
        "`submit_execution_plan`.\n\n"
        "The engine has these TOOLS (call only the ones needed):\n"
        "- filter: scope the data by entity/date/country/type/amount (almost "
        "always first).\n"
        "- eda: exploratory profiling — only for broad 'overview' requests.\n"
        "- features: engineer AML features (needed before detection/ML).\n"
        "- detect_typologies: run rule detectors for the target typologies.\n"
        "- ml_anomaly: Isolation Forest over the customer fingerprint (only "
        "for broad/high-risk sweeps, not single-entity or pure threshold "
        "questions).\n"
        "- aggregate_threshold: a pure count/amount aggregation rule (for "
        "'customers with N+ transactions under $X' style questions; no ML).\n"
        "- classify: turn signals into risk bands + escalation.\n"
        "- explain: natural-language reasons (include whenever you flag "
        "entities).\n\n"
        "TYPOLOGIES: structuring (cash just under the $10,000 CTR line), "
        "smurfing (many small senders into one account), rapid_cashout (large "
        "credit quickly withdrawn), layering (value hopping through accounts), "
        "velocity_spike, high_risk_geography.\n\n"
        "INTENTS: single_entity, threshold_query, find_pattern, "
        "high_risk_customers, eda, full_analysis.\n\n"
        "GUIDELINES:\n"
        "- Single entity ('is customer 4521 suspicious?'): intent "
        "single_entity, set customer_id, tools filter->features->"
        "detect_typologies->classify->explain (NO eda, NO ml_anomaly).\n"
        "- Threshold ('customers with 10+ transactions under $10k'): intent "
        "threshold_query, set filters.min_txn_count and filters.amount_max, "
        "tools filter->aggregate_threshold->classify->explain (NO ml).\n"
        "- Specific pattern ('find structuring last 30 days'): intent "
        "find_pattern, set typologies + date filters, tools filter->features->"
        "detect_typologies->classify->explain (NO eda).\n"
        "- 'flag high-risk customers': intent high_risk_customers, full hybrid "
        "suite incl. ml_anomaly.\n"
        "- 'overview'/'profile the data': intent eda, tools filter->eda.\n"
        "- Otherwise: full_analysis with the full pipeline.\n\n"
        f"DATE CONTEXT: the dataset spans {data_start} to {data_end}. "
        f"Treat 'today' as {today.date().isoformat()} and resolve relative "
        "ranges like 'last 30 days' into concrete ISO dates in filters "
        "(date_from/date_to).\n"
        "Always put 'filter' first when present, and include 'classify' and "
        "'explain' whenever detection or threshold tools run."
    )


def _sanitize_tools(tools: list[str], intent: str) -> list[str]:
    chosen = {t for t in tools if t in VALID_TOOLS}
    # Guard rails so the plan is always executable.
    if intent == "eda":
        chosen |= {"filter", "eda"}
    if intent == "threshold_query":
        chosen |= {"filter", "aggregate_threshold", "classify", "explain"}
    if intent == "single_entity":
        chosen |= {"filter", "features", "detect_typologies", "classify",
                   "explain"}
        chosen.discard("ml_anomaly")
    detection = {"detect_typologies", "ml_anomaly", "aggregate_threshold"}
    if chosen & detection:
        chosen |= {"classify", "explain"}
    if "detect_typologies" in chosen or "ml_anomaly" in chosen:
        chosen.add("features")
    chosen.add("filter")
    return [t for t in VALID_TOOLS if t in chosen]


def plan_with_llm(
    query: str, today: datetime, data_start: str, data_end: str
) -> QueryPlan:
    """Ask the LLM to build a :class:`QueryPlan` via tool-calling."""
    resp = _chat(
        messages=[
            {"role": "system",
             "content": _system_prompt(today, data_start, data_end)},
            {"role": "user", "content": query},
        ],
        tools=[_PLAN_TOOL],
        tool_choice={"type": "function",
                     "function": {"name": "submit_execution_plan"}},
    )

    try:
        tool_calls = resp["choices"][0]["message"]["tool_calls"]
        args = json.loads(tool_calls[0]["function"]["arguments"])
    except (KeyError, IndexError, json.JSONDecodeError, TypeError) as e:
        raise LLMUnavailable(f"could not parse plan from LLM: {e}") from e

    intent = args.get("intent")
    if intent not in VALID_INTENTS:
        raise LLMUnavailable(f"invalid intent from LLM: {intent!r}")

    f = args.get("filters") or {}
    filters = Filters(
        date_from=f.get("date_from"),
        date_to=f.get("date_to"),
        country=(f.get("country") or None),
        segment=f.get("segment"),
        txn_type=f.get("txn_type"),
        amount_min=f.get("amount_min"),
        amount_max=f.get("amount_max"),
        min_txn_count=f.get("min_txn_count"),
    )
    typologies = [t for t in (args.get("typologies") or [])
                  if t in VALID_TYPOLOGIES]
    tools = _sanitize_tools(args.get("tools") or [], intent)
    rationale = [str(r) for r in (args.get("rationale") or [])] or [
        "Plan produced by the LLM planner."
    ]

    return QueryPlan(
        query=query,
        intent=intent,
        filters=filters,
        customer_id=args.get("customer_id"),
        typologies=typologies,
        tools=tools,
        rationale=rationale,
        planner="llm",
    )


# --------------------------------------------------------------------------
# Narrative
# --------------------------------------------------------------------------
def narrate(query: str, summary: dict) -> Optional[str]:
    """Best-effort natural-language summary of the analysis result."""
    try:
        resp = _chat(
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are an AML compliance analyst. In 2-4 sentences, "
                        "summarise the analysis result for the user's query. "
                        "Be precise and cite the key numbers provided. Do not "
                        "invent facts beyond the data given. Plain text only."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"Query: {query}\n\n"
                        f"Result JSON:\n{json.dumps(summary)[:3500]}"
                    ),
                },
            ],
            temperature=0.2,
        )
        return resp["choices"][0]["message"]["content"].strip()
    except Exception:
        return None
