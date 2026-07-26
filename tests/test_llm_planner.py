"""Tests for the LLM planner — mocked so they need no network or API key.

We stub the HTTP layer (`_chat`) to return an OpenAI-style tool-call response
and assert the plan is parsed and sanitised correctly, and that the agent falls
back to the deterministic planner when the LLM is unavailable.
"""

from __future__ import annotations

import json
from datetime import datetime

import pytest

from anomaleye.agent import llm_planner
from anomaleye.agent.orchestrator import Agent


def _tool_response(args: dict) -> dict:
    return {
        "choices": [
            {
                "message": {
                    "tool_calls": [
                        {"function": {
                            "name": "submit_execution_plan",
                            "arguments": json.dumps(args),
                        }}
                    ]
                }
            }
        ]
    }


def test_plan_parsing_and_sanitization(monkeypatch):
    monkeypatch.setattr(
        llm_planner,
        "_chat",
        lambda *a, **k: _tool_response(
            {
                "intent": "find_pattern",
                "customer_id": None,
                "filters": {"date_from": "2024-03-30", "date_to": "2024-04-29"},
                "typologies": ["structuring"],
                "tools": ["detect_typologies"],  # deliberately incomplete
                "rationale": ["Structuring-specific query."],
            }
        ),
    )
    plan = llm_planner.plan_with_llm(
        "find structuring last 30 days",
        datetime(2024, 4, 29), "2024-01-01", "2024-04-29",
    )
    assert plan.planner == "llm"
    assert plan.intent == "find_pattern"
    assert plan.typologies == ["structuring"]
    # Sanitiser must repair the tool list into an executable pipeline.
    assert plan.tools[0] == "filter"
    assert {"features", "classify", "explain"} <= set(plan.tools)
    assert plan.filters.date_from == "2024-03-30"


def test_invalid_intent_raises(monkeypatch):
    monkeypatch.setattr(
        llm_planner, "_chat",
        lambda *a, **k: _tool_response({"intent": "nonsense", "tools": [],
                                       "rationale": []}),
    )
    with pytest.raises(llm_planner.LLMUnavailable):
        llm_planner.plan_with_llm("x", datetime(2024, 4, 29), "a", "b")


def test_single_entity_sanitization(monkeypatch):
    monkeypatch.setattr(
        llm_planner, "_chat",
        lambda *a, **k: _tool_response({
            "intent": "single_entity",
            "customer_id": 4521,
            "tools": ["ml_anomaly", "eda"],  # should be stripped/repaired
            "rationale": ["single entity"],
        }),
    )
    plan = llm_planner.plan_with_llm("is 4521 suspicious", datetime(2024, 4, 29),
                                    "a", "b")
    assert plan.customer_id == 4521
    assert "ml_anomaly" not in plan.tools  # never for a single entity
    assert {"filter", "features", "detect_typologies", "classify",
            "explain"} <= set(plan.tools)


def test_agent_falls_back_when_llm_unavailable(dataset, monkeypatch):
    def boom(*a, **k):
        raise llm_planner.LLMUnavailable("simulated outage")

    monkeypatch.setattr(llm_planner, "plan_with_llm", boom)
    agent = Agent(dataset=dataset, use_llm=True)
    r = agent.run("Flag high-risk customers")
    # Fallback path → deterministic planner, tagged as "rules".
    assert r["execution_summary"]["planner"] == "rules"
    assert r["execution_summary"]["detected_intent"] == "high_risk_customers"


def test_agent_uses_llm_plan_when_available(dataset, monkeypatch):
    monkeypatch.setattr(
        llm_planner, "_chat",
        lambda *a, **k: _tool_response({
            "intent": "high_risk_customers",
            "tools": ["filter", "features", "detect_typologies", "ml_anomaly",
                      "classify", "explain"],
            "rationale": ["Full hybrid sweep for high-risk entities."],
        }),
    )
    # narrate() also calls _chat; make it return a plain message.
    monkeypatch.setattr(
        llm_planner, "narrate", lambda *a, **k: "Narrative summary."
    )
    agent = Agent(dataset=dataset, use_llm=True)
    r = agent.run("who is high risk")
    assert r["execution_summary"]["planner"] == "llm"
    assert r["narrative"] == "Narrative summary."
