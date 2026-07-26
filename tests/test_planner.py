"""Tests for the natural-language query planner.

These assert the *adaptive* behaviour the problem statement calls for: the plan
must change with the query, and targeted queries must not drag in every tool.
"""

from __future__ import annotations

from datetime import datetime

import pytest

from anomaleye.agent.planner import plan_query

TODAY = datetime(2024, 4, 1)


def test_single_entity_lookup_skips_eda_and_ml():
    plan = plan_query("Is customer ID 4521 suspicious?", today=TODAY)
    assert plan.intent == "single_entity"
    assert plan.customer_id == 4521
    assert "eda" not in plan.tools
    assert "ml_anomaly" not in plan.tools


@pytest.mark.parametrize(
    "q,cid",
    [
        ("Is customer ID 4521 suspicious?", 4521),
        ("show risk for customer 100", 100),
        ("customer #7788 activity", 7788),
        ("analyse account 3021", 3021),
    ],
)
def test_customer_id_extraction(q, cid):
    assert plan_query(q, today=TODAY).customer_id == cid


def test_threshold_query_uses_aggregation_not_ml():
    plan = plan_query(
        "Which customers made 10+ transactions under $10,000?", today=TODAY
    )
    assert plan.intent == "threshold_query"
    assert plan.filters.min_txn_count == 10
    assert plan.filters.amount_max == 10_000
    assert "aggregate_threshold" in plan.tools
    assert "ml_anomaly" not in plan.tools


def test_pattern_query_selects_only_that_detector():
    plan = plan_query(
        "Find structuring patterns in the last 30 days", today=TODAY
    )
    assert plan.intent == "find_pattern"
    assert plan.typologies == ["structuring"]
    assert "eda" not in plan.tools
    # 30-day window resolves relative to the supplied "today".
    assert plan.filters.date_from == datetime(2024, 3, 2).isoformat()


def test_high_risk_request_runs_full_suite():
    plan = plan_query("Flag high-risk customers", today=TODAY)
    assert plan.intent == "high_risk_customers"
    assert "ml_anomaly" in plan.tools
    assert "detect_typologies" in plan.tools


def test_eda_request():
    plan = plan_query("Give me an overview of the data", today=TODAY)
    assert plan.intent == "eda"
    assert plan.tools == ["filter", "eda"]


def test_full_analysis_default():
    plan = plan_query("Analyse this dataset for suspicious activity",
                     today=TODAY)
    assert plan.intent == "full_analysis"
    assert {"eda", "features", "detect_typologies", "ml_anomaly"} <= set(
        plan.tools
    )


def test_amount_and_count_parsing():
    plan = plan_query("customers with more than 5 transfers over $50k",
                     today=TODAY)
    assert plan.filters.min_txn_count == 5
    assert plan.filters.amount_min == 50_000
    assert plan.filters.txn_type == "transfer"


def test_typology_synonyms():
    assert plan_query("look for smurfing", today=TODAY).typologies == ["smurfing"]
    assert "layering" in plan_query("detect layering chains", today=TODAY).typologies
    assert "rapid_cashout" in plan_query(
        "any rapid cash-out?", today=TODAY
    ).typologies
